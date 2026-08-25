from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import BridgeConfig
from .constants import CONTROL_PLANE_BASE_URL, PROFILE_ROOT, STATE_ROOT, TUNNEL_CLIENT, WorkerSpec

_TUNNEL_RE = re.compile(r"^tunnel_[A-Za-z0-9]+$")


@dataclass(frozen=True)
class TunnelStatus:
    state: str
    detail: str
    ready: bool


def profile_path(worker: WorkerSpec) -> Path:
    return PROFILE_ROOT / f"{worker.profile}.yaml"


def health_url_path(worker: WorkerSpec) -> Path:
    return STATE_ROOT / f"{worker.profile}-health.url"


def write_profile(worker: WorkerSpec, tunnel_id: str) -> Path:
    tunnel_id = tunnel_id.strip()
    if not _TUNNEL_RE.fullmatch(tunnel_id):
        raise ValueError("Tunnel ID must look like tunnel_...")
    if not worker.observed_launcher.exists():
        raise FileNotFoundError(f"Observed MCP launcher not found: {worker.observed_launcher}")

    PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    command = f'cmd.exe /d /c "{worker.observed_launcher.as_posix()}"'
    yaml_command = command.replace("'", "''")
    health_file = health_url_path(worker).as_posix()
    yaml = f'''config_version: 1
control_plane:
  base_url: "{CONTROL_PLANE_BASE_URL}"
  tunnel_id: "{tunnel_id}"
  api_key: "env:CONTROL_PLANE_API_KEY"
health:
  listen_addr: "127.0.0.1:0"
  url_file: "{health_file}"
admin_ui:
  open_browser: false
log:
  level: info
  format: json
mcp:
  commands:
    - channel: main
      command: '{yaml_command}'
'''
    path = profile_path(worker)
    path.write_text(yaml, encoding="utf-8")
    return path


def delete_profile(worker: WorkerSpec) -> None:
    profile_path(worker).unlink(missing_ok=True)
    health_url_path(worker).unlink(missing_ok=True)


def _run_tunnel_client(args: list[str], env: dict[str, str], timeout: int = 45) -> subprocess.CompletedProcess[str]:
    if not TUNNEL_CLIENT.exists():
        raise FileNotFoundError(f"tunnel-client.exe is missing: {TUNNEL_CLIENT}. Run Setup-All.cmd first.")
    return subprocess.run(
        [str(TUNNEL_CLIENT), *args],
        cwd=str(TUNNEL_CLIENT.parent.parent.parent),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def doctor(worker: WorkerSpec, runtime_key: str) -> tuple[bool, str]:
    env = os.environ.copy()
    env["CONTROL_PLANE_API_KEY"] = runtime_key
    result = _run_tunnel_client(["doctor", "--profile", worker.profile, "--explain"], env=env, timeout=30)
    output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    ok = result.returncode == 0 and "RESULT ok" in output
    return ok, output[-4000:]


def _extract_tunnel_id(payload: Any) -> str | None:
    if isinstance(payload, str) and _TUNNEL_RE.fullmatch(payload):
        return payload
    if isinstance(payload, dict):
        for key in ("id", "tunnel_id", "tunnelId"):
            value = payload.get(key)
            if isinstance(value, str) and _TUNNEL_RE.fullmatch(value):
                return value
        for value in payload.values():
            found = _extract_tunnel_id(value)
            if found:
                return found
    if isinstance(payload, list):
        for value in payload:
            found = _extract_tunnel_id(value)
            if found:
                return found
    return None


def create_tunnel(
    worker: WorkerSpec,
    admin_key: str,
    organization_ids: list[str],
    workspace_ids: list[str],
) -> str:
    if not organization_ids and not workspace_ids:
        raise ValueError("At least one Organization ID or Workspace ID is required to create a tunnel.")

    args = [
        "admin",
        "tunnels",
        "create",
        "--name",
        worker.label,
        "--description",
        f"Rex Desktop Bridge: {worker.description}",
        "--json",
    ]
    for organization_id in organization_ids:
        args.extend(["--organization-id", organization_id])
    for workspace_id in workspace_ids:
        args.extend(["--workspace-id", workspace_id])

    env = os.environ.copy()
    env["OPENAI_ADMIN_KEY"] = admin_key
    result = _run_tunnel_client(args, env=env, timeout=60)
    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()
    if result.returncode != 0:
        raise RuntimeError(error or output or f"tunnel-client exited {result.returncode}")

    payload: Any
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        payload = output
    tunnel_id = _extract_tunnel_id(payload)
    if not tunnel_id:
        raise RuntimeError(f"Tunnel was created but no tunnel_id was found in tunnel-client output: {output[-1000:]}")
    return tunnel_id


def create_missing_tunnels(config: BridgeConfig, admin_key: str) -> dict[str, str]:
    from .constants import WORKERS

    created: dict[str, str] = {}
    for worker in WORKERS:
        if config.tunnel_id(worker.key):
            continue
        tunnel_id = create_tunnel(worker, admin_key, config.organization_ids(), config.workspace_ids())
        config.set_tunnel_id(worker.key, tunnel_id)
        write_profile(worker, tunnel_id)
        created[worker.key] = tunnel_id
    return created


def ensure_profiles(config: BridgeConfig) -> list[str]:
    from .constants import WORKERS

    written: list[str] = []
    for worker in WORKERS:
        tunnel_id = config.tunnel_id(worker.key)
        if not tunnel_id:
            continue
        write_profile(worker, tunnel_id)
        written.append(worker.key)
    return written


def probe_health(worker: WorkerSpec, process_running: bool, runtime_key_present: bool, tunnel_id: str) -> TunnelStatus:
    if not runtime_key_present:
        return TunnelStatus("red", "Runtime API Key missing", False)
    if not tunnel_id:
        return TunnelStatus("red", "Tunnel not configured", False)
    if not profile_path(worker).exists():
        return TunnelStatus("red", "Tunnel profile missing", False)
    if not process_running:
        return TunnelStatus("gray", "Stopped", False)

    url_path = health_url_path(worker)
    if not url_path.exists():
        return TunnelStatus("yellow", "Starting / waiting for health endpoint", False)
    try:
        base = url_path.read_text(encoding="utf-8").strip().rstrip("/")
    except OSError:
        return TunnelStatus("yellow", "Starting / health file unreadable", False)
    if not base:
        return TunnelStatus("yellow", "Starting / health URL not ready", False)

    ready_url = base if base.endswith("/readyz") else base + "/readyz"
    try:
        with urllib.request.urlopen(ready_url, timeout=1.0) as response:
            body = response.read(1000).decode("utf-8", errors="replace")
            if 200 <= response.status < 300:
                return TunnelStatus("green", "Online / ready", True)
            return TunnelStatus("yellow", f"Health HTTP {response.status}: {body[:120]}", False)
    except (urllib.error.URLError, TimeoutError, OSError):
        return TunnelStatus("yellow", "Process running / tunnel not ready yet", False)
