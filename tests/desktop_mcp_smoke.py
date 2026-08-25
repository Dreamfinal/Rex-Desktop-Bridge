from __future__ import annotations

import anyio
import base64
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


HERE = Path(__file__).resolve().parent
REPO = HERE.parent
LAUNCHER = REPO / "desktop" / "start-desktop-observed-mcp.cmd"
ACTIVITY = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Rex-Desktop-Bridge" / "activity" / "desktop.jsonl"


async def call_text(session: ClientSession, name: str, arguments: dict) -> tuple[bool, str]:
    result = await session.call_tool(name, arguments=arguments)
    text = "\n".join(item.text for item in result.content if getattr(item, "text", None) is not None)
    return bool(getattr(result, "isError", False)), text


def assert_activity_logged() -> None:
    assert ACTIVITY.exists(), f"activity log missing: {ACTIVITY}"
    recent = ACTIVITY.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
    events = []
    for line in recent:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    assert any(item.get("event") == "task_started" and item.get("tool") == "desktop_health" for item in events), events[-10:]
    assert any(item.get("event") == "task_finished" and item.get("tool") == "desktop_health" for item in events), events[-10:]


async def main() -> None:
    env = dict(os.environ)
    env["REX_DESKTOP_INPUT_ENABLED"] = "0"
    params = StdioServerParameters(command="cmd.exe", args=["/d", "/c", str(LAUNCHER)], env=env)

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            listed = await session.list_tools()
            tools = {tool.name: tool for tool in listed.tools}
            required = {
                "desktop_health",
                "desktop_screen_info",
                "desktop_capture_screen",
                "desktop_list_windows",
                "desktop_focus_window",
                "desktop_wait_for_window",
                "desktop_inspect_window",
                "desktop_uia_click",
                "desktop_click",
                "desktop_move_mouse",
                "desktop_scroll",
                "desktop_send_keys",
                "desktop_type_text",
            }
            missing = sorted(required - set(tools))
            assert not missing, f"missing desktop tools: {missing}"

            err, health_text = await call_text(session, "desktop_health", {})
            assert not err, health_text
            health = json.loads(health_text)
            assert health["worker"] == "Rex Desktop Worker"
            assert health["worker_version"] == "2026.08.25.1"
            assert health["input_enabled"] is False
            assert health["monitors"], "monitor list is empty"

            err, screen_text = await call_text(session, "desktop_screen_info", {})
            assert not err, screen_text
            screen_info = json.loads(screen_text)
            assert "cursor" in screen_info
            assert "foreground_window" in screen_info

            capture = await session.call_tool("desktop_capture_screen", arguments={"monitor": 0})
            assert not bool(getattr(capture, "isError", False)), capture.content
            images = [item for item in capture.content if getattr(item, "type", None) == "image"]
            assert images, f"capture returned no image content: {capture.content!r}"
            image = images[0]
            raw = base64.b64decode(image.data)
            assert raw.startswith(b"\x89PNG\r\n\x1a\n"), "capture is not PNG"
            assert len(raw) > 1024, f"capture unexpectedly small: {len(raw)} bytes"

            err, windows_text = await call_text(session, "desktop_list_windows", {"limit": 10})
            assert not err, windows_text
            windows = json.loads(windows_text)
            assert "windows" in windows

            blocked_err, blocked_text = await call_text(
                session, "desktop_click", {"x": 0, "y": 0, "button": "left", "clicks": 1}
            )
            assert blocked_err, "desktop input was not blocked while REX_DESKTOP_INPUT_ENABLED=0"
            assert "disabled" in blocked_text.lower(), blocked_text

    assert_activity_logged()
    print("DESKTOP_MCP_PROXY_SMOKE_OK")
    print(f"capture_bytes={len(raw)}")
    print(f"visible_windows={windows['count']}")


anyio.run(main)
