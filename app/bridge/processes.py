from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from .activity import append_event
from .constants import LOG_ROOT, ROOT, WORKERS, WorkerSpec

CREATE_NEW_CONSOLE = 0x00000010
CREATE_NO_WINDOW = 0x08000000
SUPERVISOR = ROOT / "secure-tunnel-supervisor.ps1"
_LOG_LOCK = threading.Lock()


def tunnel_log_path(worker_key: str, root: Path = LOG_ROOT) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{worker_key}.log"


def clear_tunnel_logs(root: Path = LOG_ROOT) -> None:
    """Clear supervisor/tunnel output logs without touching config or running workers."""
    root.mkdir(parents=True, exist_ok=True)
    with _LOG_LOCK:
        for worker in WORKERS:
            tunnel_log_path(worker.key, root).write_text("", encoding="utf-8")


def _append_log(path: Path, text: str) -> None:
    with _LOG_LOCK:
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()


@dataclass
class WorkerProcess:
    worker: WorkerSpec
    process: subprocess.Popen[str]
    log_path: Path


class BridgeProcessManager:
    """Owns three headless tunnel supervisors plus optional user-opened log terminals."""

    def __init__(self) -> None:
        self._processes: dict[str, WorkerProcess] = {}
        self._viewers: dict[str, subprocess.Popen[str]] = {}
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

    def _pump_output(self, process: subprocess.Popen[str], log_path: Path) -> None:
        stream = process.stdout
        if stream is None:
            return
        try:
            for line in iter(stream.readline, ""):
                if not line:
                    break
                _append_log(log_path, line)
        finally:
            stream.close()

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
        script = str(SUPERVISOR).replace("'", "''")
        profile = worker.profile.replace("'", "''")
        state_name = f"rex-{worker.state_name}".replace("'", "''")
        display = worker.label.replace("'", "''")
        command = f"& '{script}' -Profile '{profile}' -DisplayName '{display}' -StateName '{state_name}'"
        log_path = tunnel_log_path(worker.key)
        _append_log(log_path, f"\n=== {worker.label} supervisor start ===\n")
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
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=CREATE_NO_WINDOW,
        )
        with self._lock:
            self._processes[worker.key] = WorkerProcess(worker=worker, process=process, log_path=log_path)
        threading.Thread(target=self._pump_output, args=(process, log_path), daemon=True).start()
        append_event(worker.key, {"event": "session_start", "status": "session", "supervisor_pid": process.pid})
        return process.pid

    def show_terminal(self, worker: WorkerSpec) -> int:
        """Open a visible read-only PowerShell terminal that follows one worker's live supervisor log."""
        log_path = tunnel_log_path(worker.key)
        log_path.touch(exist_ok=True)
        with self._lock:
            existing = self._viewers.get(worker.key)
            if existing and existing.poll() is None:
                return existing.pid

        title = (worker.label + " - Live Log").replace("'", "''")
        rendered_path = str(log_path).replace("'", "''")
        command = (
            f"$Host.UI.RawUI.WindowTitle='{title}'; "
            f"Write-Host 'Live log: {rendered_path}'; "
            f"Get-Content -LiteralPath '{rendered_path}' -Tail 120 -Wait"
        )
        viewer = subprocess.Popen(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            cwd=str(ROOT),
            creationflags=CREATE_NEW_CONSOLE,
        )
        with self._lock:
            self._viewers[worker.key] = viewer
        return viewer.pid

    def _stop_viewers(self) -> None:
        with self._lock:
            viewers = list(self._viewers.values())
            self._viewers.clear()
        for viewer in viewers:
            if viewer.poll() is None:
                subprocess.run(
                    ["taskkill.exe", "/PID", str(viewer.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=10,
                )

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
        self._stop_viewers()
