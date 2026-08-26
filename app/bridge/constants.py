from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Rex Desktop Bridge"
APP_VERSION = "0.1.5-prototype"
RUNTIME_DIR_NAME = "Rex-Desktop-Bridge"
CONTROL_PLANE_BASE_URL = "https://api.openai.com"
OPENAI_API_KEYS_URL = "https://platform.openai.com/settings/organization/api-keys"
OPENAI_ADMIN_KEYS_URL = "https://platform.openai.com/settings/organization/admin-keys"
OPENAI_ORG_SETTINGS_URL = "https://platform.openai.com/settings/organization/general"
OPENAI_TUNNELS_URL = "https://platform.openai.com/settings/organization/tunnels"
OPENAI_SECURE_TUNNEL_DOCS_URL = "https://developers.openai.com/api/docs/guides/secure-mcp-tunnels"
CHATGPT_PLUGINS_URL = "https://chatgpt.com/#settings/Connectors"

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / RUNTIME_DIR_NAME
STATE_ROOT = RUNTIME_ROOT / "state"
ACTIVITY_ROOT = RUNTIME_ROOT / "activity"
LOG_ROOT = RUNTIME_ROOT / "logs"
CONFIG_PATH = RUNTIME_ROOT / "config.json"
SECRETS_PATH = RUNTIME_ROOT / "secrets.json"
PROFILE_ROOT = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "tunnel-client"
TUNNEL_CLIENT = ROOT / "tools" / "tunnel-client" / "tunnel-client.exe"


@dataclass(frozen=True)
class WorkerSpec:
    key: str
    label: str
    profile: str
    legacy_profile: str
    state_name: str
    launcher: Path
    observed_launcher: Path
    description: str


WORKERS = (
    WorkerSpec(
        key="serena",
        label="Serena (Code/Repo)",
        profile="rex-serena",
        legacy_profile="serena-local",
        state_name="serena",
        launcher=ROOT / "serena" / "start-serena-mcp.cmd",
        observed_launcher=ROOT / "serena" / "start-serena-observed-mcp.cmd",
        description="Semantic code/repository intelligence, symbol-aware edits, diagnostics, and project context.",
    ),
    WorkerSpec(
        key="rdc",
        label="RDC (OS/CLI)",
        profile="rex-rdc",
        legacy_profile="rdc-local",
        state_name="rdc",
        launcher=ROOT / "rdc" / "start-rdc-local-mcp.cmd",
        observed_launcher=ROOT / "rdc" / "start-rdc-observed-mcp.cmd",
        description="Filesystem, shell, process, and operating-system execution.",
    ),
    WorkerSpec(
        key="desktop",
        label="Rex Desktop (GUI + Vision)",
        profile="rex-desktop",
        legacy_profile="desktop-local",
        state_name="desktop",
        launcher=ROOT / "desktop" / "start-desktop-mcp.cmd",
        observed_launcher=ROOT / "desktop" / "start-desktop-observed-mcp.cmd",
        description="Windows GUI automation, screenshots, visual inspection, mouse, keyboard, and window control.",
    ),
)

WORKER_BY_KEY = {worker.key: worker for worker in WORKERS}

for directory in (RUNTIME_ROOT, STATE_ROOT, ACTIVITY_ROOT, LOG_ROOT, PROFILE_ROOT):
    directory.mkdir(parents=True, exist_ok=True)
