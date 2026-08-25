"""Serena compatibility patch.

Loaded through sitecustomize by the Serena launcher.
Keeps Serena semantic tools project-scoped while extending selected generic
filesystem tools with absolute-path and explicit-project targeting.

This file intentionally does not modify Serena's installed/uv-cached files.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Literal

_PATCH_VERSION = "2026.08.21.2"


def _normalise(path: str | os.PathLike[str]) -> Path:
    return Path(path).expanduser().resolve()


def _is_within(path: Path, root: Path) -> bool:
    path = path.resolve()
    root = root.resolve()
    return path == root or path.is_relative_to(root)


def _allowed_roots(extra_root: Path | None = None) -> list[Path]:
    raw = os.environ.get("TOP_FS_ALLOWED_ROOTS", "").strip()
    if raw:
        roots = [_normalise(part) for part in raw.split(os.pathsep) if part.strip()]
    else:
        roots = [_normalise(Path.home())]
    if extra_root is not None:
        root = _normalise(extra_root)
        if root not in roots:
            roots.append(root)
    return roots


def _ensure_allowed(path: Path, extra_root: Path | None = None) -> None:
    resolved = path.resolve()
    roots = _allowed_roots(extra_root)
    if not any(_is_within(resolved, root) for root in roots):
        rendered = ", ".join(str(root) for root in roots)
        raise ValueError(f"Path {resolved} is outside TOP_FS_ALLOWED_ROOTS: {rendered}")


def _find_git_root(path: Path) -> Path | None:
    """Return the nearest Git worktree root for a filesystem target."""
    current = path if path.is_dir() else path.parent
    current = current.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _project_for_git_target(tool, target: Path):
    """Resolve/register a Git-root project for an absolute filesystem target without activating it."""
    git_root = _find_git_root(target)
    if git_root is None:
        return None

    config = tool.agent.serena_config
    existing = config.get_project(str(git_root))
    if existing is not None:
        return existing

    if os.environ.get("TOP_FS_AUTO_REGISTER", "1").strip().lower() not in {"1", "true", "yes", "on"}:
        return None

    # Avoid recreating the duplicate-name ambiguity that this repair removed.
    # If another registered project already owns the default root basename,
    # leave the filesystem operation in absolute mode instead of registering.
    existing_names = {item.project_name for item in config.projects}
    if git_root.name in existing_names:
        return None

    try:
        return config.add_project_from_path(git_root, asynchronous_autogen=False)
    except FileExistsError:
        return config.get_project(str(git_root))


def _get_registered_project(tool, project_ref: str):
    config = tool.agent.serena_config
    project = config.get_project(project_ref)
    if project is not None:
        return project

    # Explicit project paths may auto-register a Git repository without
    # changing the agent's semantic active project.
    if os.path.isdir(project_ref):
        project_root = _normalise(project_ref)
        _ensure_allowed(project_root)
        project = _project_for_git_target(tool, project_root)
        if project is not None and _normalise(project.project_root) == project_root:
            return project

    names = ", ".join(sorted({item.project_name for item in config.projects}))
    raise ValueError(
        f"Project {project_ref!r} is not registered. "
        f"Registered project names: {names}. "
        "Use an absolute project path to auto-register a Git repository, "
        "or use absolute_path for a non-project filesystem target."
    )

def _resolve_target(
    tool,
    *,
    relative_path: str | None,
    absolute_path: str | None,
    project: str | None,
    default_relative: str | None = None,
) -> tuple[Path, object | None, str]:
    """Resolve a non-default filesystem request.

    Returns (absolute_path, target_project_or_none, mode), where mode is
    "absolute" or "project". Existing active-project behavior is intentionally
    handled by the original Serena methods, not by this helper.
    """
    if relative_path and os.path.isabs(relative_path):
        if absolute_path is not None or project is not None:
            raise ValueError(
                "An absolute relative_path cannot be combined with absolute_path or project."
            )
        absolute_path = relative_path
        relative_path = None

    if absolute_path is not None and project is not None:
        raise ValueError("Pass either absolute_path or project, not both.")

    if absolute_path is not None:
        target = _normalise(absolute_path)
        _ensure_allowed(target)
        target_project = _project_for_git_target(tool, target)
        return target, target_project, "absolute"

    if project is not None:
        target_project = _get_registered_project(tool, project)
        project_root = _normalise(target_project.project_root)
        rel = relative_path if relative_path not in (None, "") else default_relative
        if rel is None:
            raise ValueError("relative_path is required when project is provided.")
        target = _normalise(project_root / rel)
        if not _is_within(target, project_root):
            raise ValueError(
                f"relative_path={rel!r} points outside project root {project_root}"
            )
        _ensure_allowed(target, project_root)
        return target, target_project, "project"

    raise RuntimeError("default-active-project")


def _encoding(project_obj) -> str:
    if project_obj is None:
        return "utf-8"
    return project_obj.project_config.encoding


def _write_text_exact(path: Path, content: str, encoding: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=encoding, newline="") as handle:
        handle.write(content)


def install() -> None:
    from serena.tools import SUCCESS_RESULT
    from serena.tools.file_tools import (
        CreateTextFileTool,
        FindFileTool,
        ListDirTool,
        ReadFileTool,
        ReplaceContentTool,
    )
    from serena.util.text_utils import ContentReplacer
    from solidlsp.ls_utils import TextUtils

    if getattr(ReadFileTool.apply, "__top_wrapper_patch__", False):
        return

    original_read_file = ReadFileTool.apply
    original_create_text_file = CreateTextFileTool.apply
    original_list_dir = ListDirTool.apply
    original_find_file = FindFileTool.apply
    original_replace_content = ReplaceContentTool.apply

    def read_file(
        self,
        relative_path: str | None = None,
        start_line: int = 0,
        end_line: int | None = None,
        max_answer_chars: int = -1,
        absolute_path: str | None = None,
        project: str | None = None,
    ) -> str:
        """Read a file.

        Existing behavior is preserved when only relative_path is provided.
        For cross-repo access, pass absolute_path, pass an absolute path in
        relative_path for backwards compatibility, or pass project together
        with relative_path. Cross-repo reads do not change the semantic active
        project.
        """
        use_extended = absolute_path is not None or project is not None or (
            relative_path is not None and os.path.isabs(relative_path)
        )
        if not use_extended:
            if relative_path is None:
                raise ValueError("relative_path is required.")
            return original_read_file(
                self,
                relative_path=relative_path,
                start_line=start_line,
                end_line=end_line,
                max_answer_chars=max_answer_chars,
            )

        target, target_project, _mode = _resolve_target(
            self,
            relative_path=relative_path,
            absolute_path=absolute_path,
            project=project,
        )
        if not target.is_file():
            raise FileNotFoundError(f"File not found: {target}")
        result = target.read_text(encoding=_encoding(target_project))
        result_lines = TextUtils.split_lines(result)
        if end_line is None:
            result_lines = result_lines[start_line:]
        else:
            result_lines = result_lines[start_line : end_line + 1]
        return self._limit_length("\n".join(result_lines), max_answer_chars)

    def create_text_file(
        self,
        content: str,
        relative_path: str | None = None,
        absolute_path: str | None = None,
        project: str | None = None,
    ) -> str:
        """Create or overwrite a text file.

        Existing behavior is preserved when only relative_path is provided.
        For cross-repo access, use absolute_path (or an absolute relative_path)
        or project + relative_path. Cross-repo writes do not change the
        semantic active project.
        """
        use_extended = absolute_path is not None or project is not None or (
            relative_path is not None and os.path.isabs(relative_path)
        )
        if not use_extended:
            if relative_path is None:
                raise ValueError("relative_path is required.")
            return original_create_text_file(
                self, relative_path=relative_path, content=content
            )

        target, target_project, _mode = _resolve_target(
            self,
            relative_path=relative_path,
            absolute_path=absolute_path,
            project=project,
        )
        existed = target.exists()
        if existed and not target.is_file():
            raise IsADirectoryError(f"Target is not a file: {target}")
        _write_text_exact(target, content, _encoding(target_project))
        answer = f"File created: {target}."
        if existed:
            answer += " Overwrote existing file."
        if target_project is not None and target_project is not getattr(self, "project", None):
            answer += " Non-active project write completed without changing semantic active project."
        return answer

    def list_dir(
        self,
        relative_path: str | None = ".",
        recursive: bool = False,
        skip_ignored_files: bool = False,
        max_answer_chars: int = -1,
        absolute_path: str | None = None,
        project: str | None = None,
    ) -> str:
        """List directory contents.

        Existing active-project behavior is preserved by default. Use
        absolute_path or project + relative_path for cross-repo listing.
        """
        use_extended = absolute_path is not None or project is not None or (
            relative_path is not None and os.path.isabs(relative_path)
        )
        if not use_extended:
            return original_list_dir(
                self,
                relative_path=relative_path or ".",
                recursive=recursive,
                skip_ignored_files=skip_ignored_files,
                max_answer_chars=max_answer_chars,
            )

        target, target_project, mode = _resolve_target(
            self,
            relative_path=relative_path,
            absolute_path=absolute_path,
            project=project,
            default_relative=".",
        )
        if not target.is_dir():
            raise FileNotFoundError(f"Directory not found: {target}")

        dirs: list[str] = []
        files: list[str] = []

        def ignored(path: Path) -> bool:
            if not skip_ignored_files or target_project is None:
                return False
            try:
                return target_project.is_ignored_path(str(path))
            except Exception:
                return False

        def render(path: Path) -> str:
            if mode == "project" and target_project is not None:
                return os.path.relpath(path, target_project.project_root)
            return str(path)

        if recursive:
            for root, dirnames, filenames in os.walk(target):
                root_path = Path(root)
                dirnames[:] = [
                    name for name in dirnames
                    if not ignored(root_path / name)
                ]
                for name in dirnames:
                    dirs.append(render(root_path / name))
                for name in filenames:
                    path = root_path / name
                    if not ignored(path):
                        files.append(render(path))
        else:
            for path in target.iterdir():
                if ignored(path):
                    continue
                if path.is_dir():
                    dirs.append(render(path))
                else:
                    files.append(render(path))

        result = self._to_json({"dirs": sorted(dirs), "files": sorted(files)})
        return self._limit_length(result, max_answer_chars)

    def find_file(
        self,
        file_mask: str,
        relative_path: str | None = ".",
        absolute_path: str | None = None,
        project: str | None = None,
    ) -> str:
        """Find files by filename mask.

        Existing behavior is preserved by default. Use absolute_path or
        project + relative_path for cross-repo search.
        """
        use_extended = absolute_path is not None or project is not None or (
            relative_path is not None and os.path.isabs(relative_path)
        )
        if not use_extended:
            return original_find_file(
                self, file_mask=file_mask, relative_path=relative_path or "."
            )

        target, target_project, mode = _resolve_target(
            self,
            relative_path=relative_path,
            absolute_path=absolute_path,
            project=project,
            default_relative=".",
        )
        if not target.exists():
            raise FileNotFoundError(f"Path not found: {target}")

        matches: list[str] = []

        def render(path: Path) -> str:
            if mode == "project" and target_project is not None:
                return os.path.relpath(path, target_project.project_root)
            return str(path)

        if target.is_file():
            if fnmatch.fnmatch(target.name, file_mask):
                matches.append(render(target))
        else:
            for root, _dirs, filenames in os.walk(target):
                root_path = Path(root)
                for name in filenames:
                    if fnmatch.fnmatch(name, file_mask):
                        matches.append(render(root_path / name))

        return self._to_json({"files": sorted(matches)})

    def replace_content(
        self,
        needle: str,
        repl: str,
        mode: Literal["literal", "regex"],
        relative_path: str | None = None,
        allow_multiple_occurrences: bool = False,
        absolute_path: str | None = None,
        project: str | None = None,
    ) -> str:
        """Replace content in one text file.

        Existing behavior is preserved by default. Cross-repo mode uses the
        same Serena ContentReplacer semantics but intentionally skips LSP
        diagnostics so the semantic active project is not changed.
        """
        use_extended = absolute_path is not None or project is not None or (
            relative_path is not None and os.path.isabs(relative_path)
        )
        if not use_extended:
            if relative_path is None:
                raise ValueError("relative_path is required.")
            return original_replace_content(
                self,
                relative_path=relative_path,
                needle=needle,
                repl=repl,
                mode=mode,
                allow_multiple_occurrences=allow_multiple_occurrences,
            )

        target, target_project, _mode = _resolve_target(
            self,
            relative_path=relative_path,
            absolute_path=absolute_path,
            project=project,
        )
        if not target.is_file():
            raise FileNotFoundError(f"File not found: {target}")
        encoding = _encoding(target_project)
        original_content = target.read_text(encoding=encoding)
        replacer = ContentReplacer(
            mode=mode,
            allow_multiple_occurrences=allow_multiple_occurrences,
        )
        updated_content = replacer.replace(original_content, needle, repl)
        _write_text_exact(target, updated_content, encoding)
        return (
            f"{SUCCESS_RESULT} Cross-repo replacement completed without "
            "changing semantic active project; LSP diagnostics were not run "
            "for the non-active target."
        )

    for patched in (read_file, create_text_file, list_dir, find_file, replace_content):
        setattr(patched, "__top_wrapper_patch__", True)

    ReadFileTool.apply = read_file
    CreateTextFileTool.apply = create_text_file
    ListDirTool.apply = list_dir
    FindFileTool.apply = find_file
    ReplaceContentTool.apply = replace_content


def version() -> str:
    return _PATCH_VERSION
