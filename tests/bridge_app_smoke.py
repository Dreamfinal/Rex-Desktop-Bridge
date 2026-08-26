from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from bridge.activity import clear_activity_logs, format_local_time
from bridge.constants import CONFIG_PATH, LOG_ROOT, PROFILE_ROOT, ROOT, SECRETS_PATH, WORKERS
from bridge.credentials import CredentialStore
import bridge.activity as activity
from bridge.help_text import HELP_TEXT
from bridge.mcp_proxy import _sanitize_rdc_response
from bridge.processes import clear_tunnel_logs


REAL_TUNNEL_ID = re.compile(r"tunnel_[A-Za-z0-9]{16,}")
SECRET_PREFIX = re.compile(r"\b(sk-(?:admin-|proj-)?[A-Za-z0-9_-]{16,})")


def scan_repository() -> None:
    skip_parts = {".git", ".serena", ".venv", "node_modules", "__pycache__", "tools"}
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in skip_parts for part in path.parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".zip", ".exe", ".dll", ".pyc"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if REAL_TUNNEL_ID.search(text):
            findings.append(f"tunnel id in {path.relative_to(ROOT)}")
        if SECRET_PREFIX.search(text):
            findings.append(f"secret-like API key in {path.relative_to(ROOT)}")
    assert not findings, findings


def test_dpapi() -> None:
    path = Path(tempfile.gettempdir()) / "rex-desktop-bridge-smoke-secrets.json"
    path.unlink(missing_ok=True)
    store = CredentialStore(path)
    store.set("smoke", "not-a-real-api-key")
    encrypted_text = path.read_text(encoding="utf-8")
    assert "not-a-real-api-key" not in encrypted_text
    assert store.get("smoke") == "not-a-real-api-key"
    store.delete("smoke")
    assert store.get("smoke") is None
    path.unlink(missing_ok=True)


def test_activity_helpers() -> None:
    sample = "2026-08-25T09:00:00+00:00"
    rendered = format_local_time(sample)
    assert len(rendered) == 8 and rendered.count(":") == 2

    root = Path(tempfile.mkdtemp(prefix="rex-bridge-activity-smoke-"))
    try:
        (root / "serena.jsonl").write_text("test\n", encoding="utf-8")
        (root / "rdc.jsonl").write_text("test\n", encoding="utf-8")
        clear_activity_logs(root)
        assert not list(root.iterdir())

        tunnel_root = root / "tunnel-logs"
        clear_tunnel_logs(tunnel_root)
        assert sorted(path.name for path in tunnel_root.iterdir()) == ["desktop.log", "rdc.log", "serena.log"]
        assert all(path.read_text(encoding="utf-8") == "" for path in tunnel_root.iterdir())
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)


def test_retry_noise_filter() -> None:
    original_root = activity.ACTIVITY_ROOT
    root = Path(tempfile.mkdtemp(prefix="rex-activity-retry-smoke-"))
    activity.ACTIVITY_ROOT = root
    try:
        activity.append_event("serena", {"event": "session_start", "status": "session"})
        activity.append_event("serena", {
            "event": "task_started", "task_id": "retry-1", "tool": "health",
            "status": "running", "started_at": "2026-08-25T12:00:00+00:00"
        })
        activity.append_event("serena", {
            "event": "task_finished", "task_id": "retry-1", "tool": "health",
            "status": "failed", "started_at": "2026-08-25T12:00:00+00:00",
            "finished_at": "2026-08-25T12:00:00.010+00:00", "duration_ms": 10,
            "error": '{"code": -32602, "message": "Invalid request parameters", "data": ""}'
        })
        activity.append_event("serena", {
            "event": "task_started", "task_id": "retry-2", "tool": "health",
            "status": "running", "started_at": "2026-08-25T12:00:01+00:00"
        })
        activity.append_event("serena", {
            "event": "task_finished", "task_id": "retry-2", "tool": "health",
            "status": "success", "started_at": "2026-08-25T12:00:01+00:00",
            "finished_at": "2026-08-25T12:00:01.050+00:00", "duration_ms": 50, "error": None
        })
        snap = activity.snapshot("serena")
        assert snap.session_total == 1 and snap.session_success == 1 and snap.session_failed == 0
        assert [task.task_id for task in snap.tasks] == ["retry-2"]
    finally:
        activity.ACTIVITY_ROOT = original_root
        import shutil
        shutil.rmtree(root, ignore_errors=True)


def test_rdc_proxy_ui_sanitizer() -> None:
    listed = {
        "result": {
            "tools": [
                {"name": "read_file", "_meta": {"ui/resourceUri": "ui://desktop-commander/file-preview", "keep": "yes"}},
            ]
        }
    }
    _sanitize_rdc_response("tools/list", {}, listed)
    assert listed["result"]["tools"][0]["_meta"] == {"keep": "yes"}

    resources = {
        "result": {
            "resources": [
                {"uri": "ui://desktop-commander/file-preview"},
                {"uri": "file:///keep-me"},
            ]
        }
    }
    _sanitize_rdc_response("resources/list", {}, resources)
    assert resources["result"]["resources"] == [{"uri": "file:///keep-me"}]

    cached = {"result": {"contents": [{"uri": "ui://desktop-commander/file-preview", "text": "widget"}]}}
    _sanitize_rdc_response("resources/read", {"uri": "ui://desktop-commander/file-preview"}, cached)
    assert cached["result"] == {"contents": []}

    call = {
        "result": {
            "content": [{"type": "text", "text": "plain result"}],
            "structuredContent": {"fileName": "x"},
            "_meta": {"openai/outputTemplate": "ui://desktop-commander/file-preview"},
        }
    }
    _sanitize_rdc_response("tools/call", {}, call)
    assert "structuredContent" not in call["result"]
    assert "_meta" not in call["result"]


def main() -> None:
    assert [worker.label for worker in WORKERS] == [
        "Serena (Code/Repo)",
        "RDC (OS/CLI)",
        "Rex Desktop (GUI + Vision)",
    ]
    assert [worker.profile for worker in WORKERS] == ["rex-serena", "rex-rdc", "rex-desktop"]
    assert CONFIG_PATH.is_absolute() and ROOT not in CONFIG_PATH.parents
    assert SECRETS_PATH.is_absolute() and ROOT not in SECRETS_PATH.parents
    assert PROFILE_ROOT.is_absolute() and ROOT not in PROFILE_ROOT.parents
    assert LOG_ROOT.is_absolute() and ROOT not in LOG_ROOT.parents
    assert "Runtime API Key" in HELP_TEXT
    assert "Admin API Key" in HELP_TEXT
    assert "Tunnel ID" in HELP_TEXT
    serena_launcher = (ROOT / "serena" / "start-serena-mcp.cmd").read_text(encoding="utf-8")
    assert "--enable-web-dashboard false" in serena_launcher
    assert "--enable-gui-log-window false" in serena_launcher
    assert "--open-web-dashboard false" in serena_launcher
    setup_text = (ROOT / "setup.ps1").read_text(encoding="utf-8")
    assert "sys._base_executable" in setup_text
    assert "Bridge base pythonw runtime missing" in setup_text
    gui_text = (ROOT / "app" / "bridge" / "gui.py").read_text(encoding="utf-8")
    assert "Clear Logs" in gui_text
    assert "Current: idle" in gui_text
    assert "Show Terminal" in gui_text
    assert 'text="Restart"' not in gui_text
    assert "Tunnels run headless by default" in gui_text
    processes_text = (ROOT / "app" / "bridge" / "processes.py").read_text(encoding="utf-8")
    assert "CREATE_NO_WINDOW" in processes_text
    assert "stdout=subprocess.PIPE" in processes_text
    assert "Get-Content -LiteralPath" in processes_text
    assert "format_local_time" in gui_text
    json.loads((ROOT / "versions.json").read_text(encoding="utf-8"))
    test_dpapi()
    test_retry_noise_filter()
    test_activity_helpers()
    test_rdc_proxy_ui_sanitizer()
    scan_repository()
    print("BRIDGE_APP_SMOKE_OK")


if __name__ == "__main__":
    main()
