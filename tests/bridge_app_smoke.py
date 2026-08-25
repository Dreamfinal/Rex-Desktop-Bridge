from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from bridge.activity import clear_activity_logs, format_local_time
from bridge.constants import CONFIG_PATH, PROFILE_ROOT, ROOT, SECRETS_PATH, WORKERS
from bridge.credentials import CredentialStore
from bridge.help_text import HELP_TEXT


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
    finally:
        for child in root.iterdir():
            child.unlink(missing_ok=True)
        root.rmdir()


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
    assert "Runtime API Key" in HELP_TEXT
    assert "Admin API Key" in HELP_TEXT
    assert "Tunnel ID" in HELP_TEXT
    serena_launcher = (ROOT / "serena" / "start-serena-mcp.cmd").read_text(encoding="utf-8")
    assert "--enable-web-dashboard false" in serena_launcher
    assert "--enable-gui-log-window false" in serena_launcher
    assert "--open-web-dashboard false" in serena_launcher
    setup_text = (ROOT / "setup.ps1").read_text(encoding="utf-8")
    assert "pythonw.exe" in setup_text
    gui_text = (ROOT / "app" / "bridge" / "gui.py").read_text(encoding="utf-8")
    assert "Clear Logs" in gui_text
    assert "Current: idle" in gui_text
    assert "format_local_time" in gui_text
    json.loads((ROOT / "versions.json").read_text(encoding="utf-8"))
    test_dpapi()
    test_activity_helpers()
    scan_repository()
    print("BRIDGE_APP_SMOKE_OK")


if __name__ == "__main__":
    main()
