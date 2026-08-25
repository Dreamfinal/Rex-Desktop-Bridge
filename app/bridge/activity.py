from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .constants import ACTIVITY_ROOT, WORKERS


_LOCK = threading.Lock()


def utc_now() -> str:
    """Return an offset-aware UTC timestamp for durable activity records."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def format_local_time(value: str) -> str:
    """Render an ISO timestamp in the Windows user's current local timezone."""
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone().strftime("%H:%M:%S")
    except ValueError:
        return value[11:19] if len(value) >= 19 else value


def activity_path(worker_key: str) -> Path:
    ACTIVITY_ROOT.mkdir(parents=True, exist_ok=True)
    return ACTIVITY_ROOT / f"{worker_key}.jsonl"


def append_event(worker_key: str, event: dict[str, Any]) -> None:
    record = dict(event)
    record.setdefault("worker", worker_key)
    record.setdefault("timestamp", utc_now())
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    path = activity_path(worker_key)
    with _LOCK:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
            handle.flush()


def reset_session_markers() -> None:
    for worker in WORKERS:
        append_event(worker.key, {"event": "session_start", "status": "session", "pid": os.getpid()})


def clear_activity_logs(root: Path = ACTIVITY_ROOT) -> None:
    """Delete Bridge activity/history logs while preserving every config and credential."""
    root.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        for path in root.iterdir():
            if not path.is_file():
                continue
            for attempt in range(5):
                try:
                    path.unlink(missing_ok=True)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.05)


@dataclass(frozen=True)
class TaskView:
    task_id: str
    tool: str
    status: str
    started_at: str
    finished_at: str | None
    duration_ms: int | None
    error: str | None


@dataclass(frozen=True)
class ActivitySnapshot:
    worker: str
    tasks: tuple[TaskView, ...]
    session_total: int
    session_success: int
    session_failed: int
    all_total: int
    all_success: int
    all_failed: int


def _tail_json(path: Path, limit: int = 4000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines: deque[str] = deque(maxlen=limit)
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.strip():
                    lines.append(line)
    except OSError:
        return []
    result: list[dict[str, Any]] = []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            result.append(item)
    return result


def _event_time(event: dict[str, Any]) -> datetime | None:
    value = str(event.get("finished_at") or event.get("timestamp") or "")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _suppressed_retry_task_ids(events: Iterable[dict[str, Any]], retry_window_seconds: float = 5.0) -> set[str]:
    pending: dict[str, list[tuple[str, datetime]]] = {}
    suppressed: set[str] = set()
    for event in events:
        if event.get("event") != "task_finished":
            continue
        tool = str(event.get("tool", "unknown"))
        status = str(event.get("status", "failed"))
        when = _event_time(event)
        if when is None:
            continue
        error = str(event.get("error") or "")
        if status == "failed" and '"code": -32602' in error and "Invalid request parameters" in error:
            task_id = str(event.get("task_id", ""))
            if task_id:
                pending.setdefault(tool, []).append((task_id, when))
            continue
        if status != "success" or tool not in pending:
            continue
        survivors: list[tuple[str, datetime]] = []
        for task_id, failed_at in pending[tool]:
            age = (when - failed_at).total_seconds()
            if 0 <= age <= retry_window_seconds:
                suppressed.add(task_id)
            elif age < 0:
                survivors.append((task_id, failed_at))
        pending[tool] = survivors
    return suppressed


def snapshot(worker_key: str, task_limit: int = 40) -> ActivitySnapshot:
    events = _tail_json(activity_path(worker_key))
    suppressed_retry_ids = _suppressed_retry_task_ids(events)
    session_index = 0
    for index, event in enumerate(events):
        if event.get("event") == "session_start":
            session_index = index
    session_events = events[session_index:]

    states: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    all_total = all_success = all_failed = 0
    session_total = session_success = session_failed = 0

    def consume(items: Iterable[dict[str, Any]], session: bool) -> None:
        nonlocal all_total, all_success, all_failed, session_total, session_success, session_failed
        for event in items:
            if event.get("event") != "task_finished":
                continue
            if str(event.get("task_id", "")) in suppressed_retry_ids:
                continue
            status = str(event.get("status", "failed"))
            if session:
                session_total += 1
                if status == "success":
                    session_success += 1
                else:
                    session_failed += 1
            else:
                all_total += 1
                if status == "success":
                    all_success += 1
                else:
                    all_failed += 1

    consume(events, session=False)
    consume(session_events, session=True)

    for event in session_events:
        kind = event.get("event")
        if kind not in {"task_started", "task_finished"}:
            continue
        task_id = str(event.get("task_id", ""))
        if not task_id or task_id in suppressed_retry_ids:
            continue
        if task_id not in states:
            states[task_id] = {
                "task_id": task_id,
                "tool": str(event.get("tool", "unknown")),
                "status": "running",
                "started_at": str(event.get("started_at") or event.get("timestamp") or ""),
                "finished_at": None,
                "duration_ms": None,
                "error": None,
            }
            order.append(task_id)
        state = states[task_id]
        if kind == "task_finished":
            state["status"] = str(event.get("status", "failed"))
            state["finished_at"] = str(event.get("finished_at") or event.get("timestamp") or "")
            duration = event.get("duration_ms")
            state["duration_ms"] = int(duration) if isinstance(duration, (int, float)) else None
            error = event.get("error")
            state["error"] = str(error) if error else None

    tasks = tuple(TaskView(**states[task_id]) for task_id in reversed(order[-task_limit:]))
    return ActivitySnapshot(
        worker=worker_key,
        tasks=tasks,
        session_total=session_total,
        session_success=session_success,
        session_failed=session_failed,
        all_total=all_total,
        all_success=all_success,
        all_failed=all_failed,
    )
