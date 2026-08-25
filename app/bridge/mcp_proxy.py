from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .activity import append_event, utc_now
from .constants import WORKER_BY_KEY


def _request_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _parse_message(line: bytes) -> dict[str, Any] | None:
    try:
        decoded = line.decode("utf-8").strip()
        if not decoded:
            return None
        message = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return message if isinstance(message, dict) else None


class McpActivityProxy:
    """Transparent newline-delimited MCP stdio proxy with per-worker task telemetry.

    The proxy never writes telemetry to stdout. Stdout remains byte-for-byte MCP
    traffic so tunnel-client sees the same protocol it would see from the worker.
    """

    def __init__(self, worker_key: str, launcher: Path) -> None:
        self.worker_key = worker_key
        self.launcher = launcher
        self.pending: dict[str, dict[str, Any]] = {}
        self.pending_lock = threading.Lock()
        self.instance = uuid.uuid4().hex[:10]
        self.sequence = 0

    def _child_command(self) -> list[str]:
        return ["cmd.exe", "/d", "/c", str(self.launcher)]

    def _record_request(self, message: dict[str, Any]) -> None:
        if message.get("method") != "tools/call" or "id" not in message:
            return
        params = message.get("params")
        tool = "unknown"
        if isinstance(params, dict):
            tool = str(params.get("name") or "unknown")
        self.sequence += 1
        task_id = f"{self.worker_key}-{self.instance}-{self.sequence}"
        started_at = utc_now()
        entry = {
            "task_id": task_id,
            "tool": tool,
            "started_at": started_at,
            "started_monotonic": time.monotonic(),
        }
        with self.pending_lock:
            self.pending[_request_key(message["id"])] = entry
        append_event(
            self.worker_key,
            {
                "event": "task_started",
                "task_id": task_id,
                "tool": tool,
                "status": "running",
                "started_at": started_at,
                "proxy_pid": os.getpid(),
            },
        )

    def _record_response(self, message: dict[str, Any]) -> None:
        if "id" not in message:
            return
        key = _request_key(message["id"])
        with self.pending_lock:
            entry = self.pending.pop(key, None)
        if not entry:
            return

        status = "success"
        error_text: str | None = None
        if message.get("error") is not None:
            status = "failed"
            error_text = json.dumps(message.get("error"), ensure_ascii=False)[:1000]
        else:
            result = message.get("result")
            if isinstance(result, dict) and bool(result.get("isError", False)):
                status = "failed"
                content = result.get("content")
                error_text = json.dumps(content, ensure_ascii=False)[:1000] if content is not None else "MCP tool returned isError=true"

        duration_ms = max(0, round((time.monotonic() - float(entry["started_monotonic"])) * 1000))
        append_event(
            self.worker_key,
            {
                "event": "task_finished",
                "task_id": entry["task_id"],
                "tool": entry["tool"],
                "status": status,
                "started_at": entry["started_at"],
                "finished_at": utc_now(),
                "duration_ms": duration_ms,
                "error": error_text,
                "proxy_pid": os.getpid(),
            },
        )

    def _copy_child_stdout(self, child: subprocess.Popen[bytes]) -> None:
        assert child.stdout is not None
        out = sys.stdout.buffer
        for line in iter(child.stdout.readline, b""):
            message = _parse_message(line)
            if message is not None:
                self._record_response(message)
            out.write(line)
            out.flush()

    @staticmethod
    def _copy_child_stderr(child: subprocess.Popen[bytes]) -> None:
        assert child.stderr is not None
        err = sys.stderr.buffer
        for chunk in iter(lambda: child.stderr.read(4096), b""):
            err.write(chunk)
            err.flush()

    def run(self) -> int:
        if not self.launcher.exists():
            print(f"Missing worker launcher: {self.launcher}", file=sys.stderr, flush=True)
            return 2

        child = subprocess.Popen(
            self._child_command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.launcher.parent.parent),
            bufsize=0,
        )
        stdout_thread = threading.Thread(target=self._copy_child_stdout, args=(child,), daemon=True)
        stderr_thread = threading.Thread(target=self._copy_child_stderr, args=(child,), daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        assert child.stdin is not None
        try:
            for line in iter(sys.stdin.buffer.readline, b""):
                message = _parse_message(line)
                if message is not None:
                    self._record_request(message)
                child.stdin.write(line)
                child.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                child.stdin.close()
            except OSError:
                pass

        try:
            return child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.terminate()
            try:
                return child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                return child.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description="Rex Desktop Bridge MCP activity proxy")
    parser.add_argument("--worker", required=True, choices=sorted(WORKER_BY_KEY))
    parser.add_argument("--launcher", default="")
    args = parser.parse_args()

    worker = WORKER_BY_KEY[args.worker]
    launcher = Path(args.launcher).resolve() if args.launcher else worker.launcher
    return McpActivityProxy(args.worker, launcher).run()


if __name__ == "__main__":
    raise SystemExit(main())
