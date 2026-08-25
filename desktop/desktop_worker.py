from __future__ import annotations

import ctypes
import json
import os
import platform
import time
from collections import deque
from ctypes import wintypes
from typing import Any

# Import mss before UI automation libraries. mss documents that this avoids
# DPI-awareness conflicts with some desktop automation packages.
import mss
from mss.tools import to_png
from mcp.server.fastmcp import FastMCP, Image
from pywinauto import Desktop, keyboard, mouse

WORKER_VERSION = "2026.08.25.1"
INPUT_ENV = "REX_DESKTOP_INPUT_ENABLED"
MAX_WINDOW_LIMIT = 200
MAX_UI_ITEMS = 1000

mcp = FastMCP("Rex Desktop Worker")


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_RETURN = 0x0D
VK_TAB = 0x09


def _require_windows() -> None:
    if os.name != "nt":
        raise RuntimeError("Rex Desktop Worker is Windows-only.")


def _input_enabled() -> bool:
    return os.environ.get(INPUT_ENV, "1").strip().lower() not in {"0", "false", "no", "off"}


def _require_input_enabled() -> None:
    if not _input_enabled():
        raise RuntimeError(f"Desktop input is disabled. Set {INPUT_ENV}=1 before launching the worker.")


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _rect_dict(rect: Any) -> dict[str, int]:
    return {
        "left": int(rect.left),
        "top": int(rect.top),
        "right": int(rect.right),
        "bottom": int(rect.bottom),
        "width": int(rect.width()),
        "height": int(rect.height()),
    }


def _monitor_dict(index: int, monitor: dict[str, int]) -> dict[str, int]:
    return {
        "index": index,
        "left": int(monitor["left"]),
        "top": int(monitor["top"]),
        "width": int(monitor["width"]),
        "height": int(monitor["height"]),
    }


def _capture_png(
    monitor: int = 0,
    left: int | None = None,
    top: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> bytes:
    _require_windows()
    region_values = (left, top, width, height)
    if any(value is not None for value in region_values) and not all(value is not None for value in region_values):
        raise ValueError("left, top, width, and height must be supplied together for a region capture.")

    with mss.MSS() as sct:
        if all(value is not None for value in region_values):
            assert left is not None and top is not None and width is not None and height is not None
            if width <= 0 or height <= 0:
                raise ValueError("width and height must be greater than zero.")
            target = {"left": int(left), "top": int(top), "width": int(width), "height": int(height)}
        else:
            if monitor < 0 or monitor >= len(sct.monitors):
                raise ValueError(f"monitor must be between 0 and {len(sct.monitors) - 1}.")
            target = sct.monitors[monitor]

        shot = sct.grab(target)
        return to_png(shot.rgb, shot.size)


def _top_windows(title_contains: str = "", limit: int = 50) -> list[Any]:
    _require_windows()
    limit = max(1, min(int(limit), MAX_WINDOW_LIMIT))
    needle = title_contains.casefold().strip()
    results: list[Any] = []
    for window in Desktop(backend="uia").windows(visible_only=True, enabled_only=False):
        try:
            title = window.window_text().strip()
        except Exception:
            title = ""
        if needle and needle not in title.casefold():
            continue
        results.append(window)
        if len(results) >= limit:
            break
    return results


def _find_window(title_contains: str) -> Any:
    needle = title_contains.strip()
    if not needle:
        raise ValueError("title_contains must not be empty.")
    windows = _top_windows(needle, MAX_WINDOW_LIMIT)
    if not windows:
        raise RuntimeError(f"No visible window contains title: {title_contains!r}")
    return windows[0]


def _control_info(control: Any) -> dict[str, Any]:
    info = control.element_info
    try:
        rect = _rect_dict(control.rectangle())
    except Exception:
        rect = None
    try:
        title = control.window_text()
    except Exception:
        title = getattr(info, "name", "") or ""
    return {
        "name": title,
        "control_type": getattr(info, "control_type", None),
        "automation_id": getattr(info, "automation_id", None),
        "class_name": getattr(info, "class_name", None),
        "handle": getattr(info, "handle", None),
        "process_id": getattr(info, "process_id", None),
        "rectangle": rect,
    }


def _walk_controls(root: Any, max_depth: int, max_items: int) -> list[tuple[Any, int]]:
    max_depth = max(0, min(int(max_depth), 12))
    max_items = max(1, min(int(max_items), MAX_UI_ITEMS))
    queue: deque[tuple[Any, int]] = deque([(root, 0)])
    output: list[tuple[Any, int]] = []

    while queue and len(output) < max_items:
        current, depth = queue.popleft()
        output.append((current, depth))
        if depth >= max_depth:
            continue
        try:
            children = current.children()
        except Exception:
            children = []
        for child in children:
            queue.append((child, depth + 1))
    return output


def _send_keyboard_input(vk: int, scan: int, flags: int) -> None:
    item = _INPUT(type=INPUT_KEYBOARD, ki=_KEYBDINPUT(vk, scan, flags, 0, 0))
    sent = ctypes.windll.user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(_INPUT))
    if sent != 1:
        raise ctypes.WinError()


def _send_virtual_key(vk: int) -> None:
    _send_keyboard_input(vk, 0, 0)
    _send_keyboard_input(vk, 0, KEYEVENTF_KEYUP)


def _send_unicode_text(text: str, interval: float = 0.0) -> None:
    _require_windows()
    interval = max(0.0, min(float(interval), 1.0))
    for char in text:
        if char == "\n":
            _send_virtual_key(VK_RETURN)
        elif char == "\t":
            _send_virtual_key(VK_TAB)
        else:
            encoded = char.encode("utf-16-le")
            for offset in range(0, len(encoded), 2):
                unit = int.from_bytes(encoded[offset : offset + 2], "little")
                _send_keyboard_input(0, unit, KEYEVENTF_UNICODE)
                _send_keyboard_input(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
        if interval:
            time.sleep(interval)


def _foreground_window() -> dict[str, Any]:
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return {"handle": 0, "title": ""}
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return {"handle": int(hwnd), "title": buffer.value}


def _cursor_position() -> dict[str, int]:
    point = wintypes.POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        raise ctypes.WinError()
    return {"x": int(point.x), "y": int(point.y)}


@mcp.tool()
def desktop_health() -> str:
    """Report desktop-worker version, foreground state, and whether input actions are enabled."""
    _require_windows()
    with mss.MSS() as sct:
        monitors = [_monitor_dict(index, value) for index, value in enumerate(sct.monitors)]
    return _json(
        {
            "worker": "Rex Desktop Worker",
            "worker_version": WORKER_VERSION,
            "platform": platform.platform(),
            "pid": os.getpid(),
            "input_enabled": _input_enabled(),
            "foreground_window": _foreground_window(),
            "monitors": monitors,
        }
    )


@mcp.tool()
def desktop_screen_info() -> str:
    """Return monitor geometry, foreground-window title, and current cursor coordinates without taking a screenshot."""
    _require_windows()
    with mss.MSS() as sct:
        monitors = [_monitor_dict(index, value) for index, value in enumerate(sct.monitors)]
    return _json(
        {
            "monitors": monitors,
            "cursor": _cursor_position(),
            "foreground_window": _foreground_window(),
        }
    )


@mcp.tool()
def desktop_capture_screen(
    monitor: int = 0,
    left: int | None = None,
    top: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> Image:
    """Capture the virtual desktop (monitor=0), one monitor, or an explicit screen region and return PNG pixels for model vision."""
    return Image(data=_capture_png(monitor, left, top, width, height), format="png")


@mcp.tool()
def desktop_list_windows(title_contains: str = "", limit: int = 50) -> str:
    """List visible top-level Windows UI Automation windows, optionally filtered by a title substring."""
    windows = _top_windows(title_contains, limit)
    return _json({"count": len(windows), "windows": [_control_info(window) for window in windows]})


@mcp.tool()
def desktop_focus_window(title_contains: str) -> str:
    """Focus the first visible top-level window whose title contains the supplied text."""
    _require_input_enabled()
    window = _find_window(title_contains)
    window.set_focus()
    return _json({"focused": _control_info(window)})


@mcp.tool()
def desktop_wait_for_window(title_contains: str, timeout_seconds: float = 10.0, poll_seconds: float = 0.25) -> str:
    """Wait for a visible top-level window title to appear. Useful after launching apps without repeatedly taking screenshots."""
    timeout_seconds = max(0.1, min(float(timeout_seconds), 120.0))
    poll_seconds = max(0.05, min(float(poll_seconds), 2.0))
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        windows = _top_windows(title_contains, 1)
        if windows:
            return _json({"found": True, "window": _control_info(windows[0])})
        time.sleep(poll_seconds)
    return _json({"found": False, "title_contains": title_contains, "timeout_seconds": timeout_seconds})


@mcp.tool()
def desktop_inspect_window(title_contains: str, max_depth: int = 4, max_items: int = 250) -> str:
    """Inspect a bounded Windows UI Automation tree for one visible window. Prefer this before vision when controls are discoverable."""
    window = _find_window(title_contains)
    controls = []
    for control, depth in _walk_controls(window, max_depth, max_items):
        item = _control_info(control)
        item["depth"] = depth
        controls.append(item)
    return _json({"window": _control_info(window), "count": len(controls), "controls": controls})


@mcp.tool()
def desktop_uia_click(
    name: str,
    window_title: str = "",
    control_type: str = "",
    automation_id: str = "",
    index: int = 0,
    max_depth: int = 8,
    max_items: int = 600,
) -> str:
    """Click a UI Automation control by accessible name/type/id. Prefer this deterministic path over coordinate clicks when possible."""
    _require_input_enabled()
    if not any(value.strip() for value in (name, control_type, automation_id)):
        raise ValueError("At least one of name, control_type, or automation_id must be supplied.")
    root = _find_window(window_title) if window_title.strip() else Desktop(backend="uia")
    name_fold = name.casefold().strip()
    type_fold = control_type.casefold().strip()
    id_fold = automation_id.casefold().strip()
    matches: list[Any] = []

    if window_title.strip():
        candidates = (control for control, _depth in _walk_controls(root, max_depth, max_items))
    else:
        candidates = iter(_top_windows("", min(max_items, MAX_WINDOW_LIMIT)))

    for control in candidates:
        info = _control_info(control)
        candidate_name = str(info.get("name") or "").casefold()
        candidate_type = str(info.get("control_type") or "").casefold()
        candidate_id = str(info.get("automation_id") or "").casefold()
        if name_fold and name_fold not in candidate_name:
            continue
        if type_fold and type_fold != candidate_type:
            continue
        if id_fold and id_fold != candidate_id:
            continue
        matches.append(control)

    if not matches:
        raise RuntimeError("No UI Automation control matched the supplied selector.")
    if index < 0 or index >= len(matches):
        raise ValueError(f"index must be between 0 and {len(matches) - 1} for this selector.")

    target = matches[index]
    target.set_focus()
    target.click_input()
    return _json({"clicked": _control_info(target), "match_count": len(matches), "selected_index": index})


@mcp.tool()
def desktop_click(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
    """Fallback coordinate click. Use UI Automation first when a stable accessible control exists."""
    _require_input_enabled()
    normalized = button.strip().lower()
    if normalized not in {"left", "right", "middle"}:
        raise ValueError("button must be left, right, or middle.")
    clicks = max(1, min(int(clicks), 5))
    for _ in range(clicks):
        mouse.click(button=normalized, coords=(int(x), int(y)))
    return _json({"clicked": True, "x": int(x), "y": int(y), "button": normalized, "clicks": clicks})


@mcp.tool()
def desktop_move_mouse(x: int, y: int) -> str:
    """Move the mouse pointer to an absolute virtual-desktop coordinate without clicking."""
    _require_input_enabled()
    mouse.move(coords=(int(x), int(y)))
    return _json({"moved": True, "x": int(x), "y": int(y)})


@mcp.tool()
def desktop_scroll(wheel_dist: int, x: int | None = None, y: int | None = None) -> str:
    """Scroll at the current pointer or an explicit coordinate. Positive values scroll up and negative values scroll down."""
    _require_input_enabled()
    coords = None if x is None or y is None else (int(x), int(y))
    mouse.scroll(coords=coords, wheel_dist=int(wheel_dist))
    return _json({"scrolled": True, "wheel_dist": int(wheel_dist), "coords": coords})


@mcp.tool()
def desktop_send_keys(keys: str, pause: float = 0.02) -> str:
    """Send pywinauto key syntax for shortcuts/special keys, for example '^s', '%{F4}', or '{ENTER}'. Use desktop_type_text for literal text."""
    _require_input_enabled()
    pause = max(0.0, min(float(pause), 1.0))
    keyboard.send_keys(keys, pause=pause, with_spaces=True, with_tabs=True, with_newlines=True)
    return _json({"sent": True, "keys": keys, "pause": pause})


@mcp.tool()
def desktop_type_text(text: str, interval: float = 0.0) -> str:
    """Type literal Unicode text into the focused control using Windows SendInput. Newline and tab are emitted as real keys."""
    _require_input_enabled()
    _send_unicode_text(text, interval)
    return _json({"typed": True, "characters": len(text), "interval": max(0.0, min(float(interval), 1.0))})


def main() -> None:
    _require_windows()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
