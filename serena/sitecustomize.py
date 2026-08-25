"""Load the local Serena compatibility patch only in the dedicated MCP process."""

from __future__ import annotations

import datetime
import json
import os
import traceback
from pathlib import Path


def _log(message: str) -> None:
    try:
        root = Path(os.environ.get("SERENA_MOD_LOG_DIR", "")) if os.environ.get("SERENA_MOD_LOG_DIR") else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Rex-Desktop-Bridge" / "serena"
        root.mkdir(parents=True, exist_ok=True)
        with (root / "wrapper.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.datetime.now().isoformat()} {message}\n")
    except Exception:
        pass


if os.environ.get("TOP_SERENA_PATCH_ENABLED") == "1":
    try:
        import top_serena_patch

        top_serena_patch.install()

        from serena.tools import Tool, ToolMarkerDoesNotRequireActiveProject

        class HealthTool(Tool, ToolMarkerDoesNotRequireActiveProject):
            """Lightweight Top/Serena diagnostic tool."""

            __module__ = "serena.tools.top_wrapper"

            def apply(self) -> str:
                """Return server, wrapper, project, registry, context, and LSP state."""
                active = getattr(self.agent, "_active_project", None)
                context = getattr(self.agent, "_context", None)
                registered = [
                    {"name": item.project_name, "root": str(item.project_root)}
                    for item in self.agent.serena_config.projects
                ]
                payload = {
                    "server": "ok",
                    "wrapper_patch": top_serena_patch.version(),
                    "pid": os.getpid(),
                    "active_project": getattr(active, "project_name", None),
                    "active_project_root": (
                        str(active.project_root) if active is not None else None
                    ),
                    "registered_projects": registered,
                    "language_server": (
                        active.get_language_server_manager_status()
                        if active is not None
                        else None
                    ),
                    "context": getattr(context, "name", None),
                }
                return json.dumps(payload, ensure_ascii=False)

        _log(f"loaded patch {top_serena_patch.version()} with health tool")
    except Exception:
        _log("patch load failed\n" + traceback.format_exc())
        raise
    finally:
        # Prevent this PYTHONPATH hook from patching Python processes spawned by
        # Serena (for example language servers started through uvx).
        os.environ["TOP_SERENA_PATCH_ENABLED"] = "0"
