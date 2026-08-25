from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from .activity import append_event
from .constants import ROOT, WORKERS, WorkerSpec

CREATE_NEW_CONSOLE = 0x00000010
SUPERVISOR = ROOT / "secure-tunnel-supervisor.ps1"


@dataclass
class WorkerProcess:
    worker: WorkerSpec
    process: subprocess.Popen[bytes]


class BridgeProcessManager:
    """Owns the three visible tunnel terminals for the GUI prototype."""

    def __init__(self) -> None:
        self._processes: dict[str, WorkerProcess] = {}
        self._lock = threading.Lock()

    def is_running(self, worker_key: str) -> bool:
        with self._lock:
            item = self._processes.get(worker_key)
            return bool(item and item.process.poll() is None)

    def pid(self, worker_key: str) -> int | None:
        with self._lock:
            item = self._processes.get(worker_key)
            if not item or item.process.poll() is not None:
                return None
            return item.process.pid

    def start(self, worker: WorkerSpec, runtime_key: str) -> int:
        if not runtime_key.strip():
            raise ValueError("Runtime API Key is required before starting a tunnel.")
        if not SUPERVISOR.exists():
            raise FileNotFoundError(f"Missing tunnel supervisor: {SUPERVISOR}")
        if self.is_running(worker.key):
            pid = self.pid(worker.key)
            return int(pid) if pid is not None else 0

        env = os.environ.copy()
        env["CONTROL_PLANE_API_KEY"] = runtime_key
        title = worker.label.replace("'", "''")
        script = str(SUPERVISOR).replace("'", "''")
        profile = worker.profile.replace("'", "''")
        state_name = f"rex-{worker.state_name}".replace("'", "''")
        display = worker.label.replace("'", "''")
        command = (
            f"$Host.UI.RawUI.WindowTitle='{title} - Tunnel'; "
            f"& '{script}' -Profile '{profile}' -DisplayName '{display}' -StateName '{state_name}'"
        )
        process = subprocess.Popen(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            cwd=str(ROOT),
            env=env,
            creationflags=CREATE_NEW_CONSOLE,
        )
        with self._lock:
            self._processes[worker.key] = WorkerProcess(worker=worker, process=process)
        append_event(worker.key, {"event": "session_start", "status": "session", "terminal_pid": process.pid})
        return process.pid

    def stop(self, worker_key: str) -> None:
        with self._lock:
            item = self._processes.pop(worker_key, None)
        if not item:
            return
        process = item.process
        if process.poll() is not None:
            return
        subprocess.run(
            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()

    def restart(self, worker: WorkerSpec, runtime_key: str) -> int:
        self.stop(worker.key)
        return self.start(worker, runtime_key)

    def start_all(self, runtime_key: str, tunnel_ids: dict[str, str]) -> dict[str, int]:
        started: dict[str, int] = {}
        for worker in WORKERS:
            if not tunnel_ids.get(worker.key, "").strip():
                continue
            started[worker.key] = self.start(worker, runtime_key)
        return started

    def stop_all(self) -> None:
        for worker in WORKERS:
            self.stop(worker.key)
