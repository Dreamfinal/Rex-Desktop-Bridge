from __future__ import annotations

import anyio
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


HERE = Path(__file__).resolve().parent
REPO = HERE.parent
LAUNCHER = REPO / "serena" / "start-serena-observed-mcp.cmd"
VERSIONS = REPO / "versions.json"


async def call_text(session: ClientSession, name: str, arguments: dict) -> tuple[bool, str]:
    result = await session.call_tool(name, arguments=arguments)
    text = "\n".join(
        item.text for item in result.content if getattr(item, "text", None) is not None
    )
    return bool(getattr(result, "isError", False)), text


async def main() -> None:
    params = StdioServerParameters(command="cmd.exe", args=["/d", "/c", str(LAUNCHER)])
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            listed = await session.list_tools()
            tools = {tool.name: tool for tool in listed.tools}
            required = {"health", "read_file", "list_dir", "activate_project", "get_current_config"}
            missing = sorted(required - set(tools))
            assert not missing, f"missing tools: {missing}"

            props = tools["read_file"].inputSchema.get("properties", {})
            assert "absolute_path" in props, props.keys()
            assert "project" in props, props.keys()

            err, health_text = await call_text(session, "health", {})
            assert not err, health_text
            health0 = json.loads(health_text)
            assert health0["server"] == "ok"
            assert health0["wrapper_patch"] == "2026.08.21.2"
            active0 = health0["active_project"]

            err, versions_text = await call_text(
                session,
                "read_file",
                {"absolute_path": str(VERSIONS), "start_line": 0, "end_line": 20},
            )
            assert not err, versions_text
            expected_repo_version = json.loads(VERSIONS.read_text(encoding="utf-8"))["repo_version"]
            assert f'"repo_version": "{expected_repo_version}"' in versions_text

            err, compat_text = await call_text(
                session,
                "read_file",
                {"relative_path": str(VERSIONS), "start_line": 0, "end_line": 5},
            )
            assert not err, compat_text

            err, health_text = await call_text(session, "health", {})
            assert not err, health_text
            health1 = json.loads(health_text)
            assert health1["active_project"] == active0

            blocked_err, blocked_text = await call_text(
                session,
                "read_file",
                {"absolute_path": r"C:\Windows\win.ini", "start_line": 0, "end_line": 2},
            )
            assert blocked_err, "C:\\Windows escaped TOP_FS_ALLOWED_ROOTS"
            assert "TOP_FS_ALLOWED_ROOTS" in blocked_text or "outside" in blocked_text.lower()

            print("SERENA_MCP_SMOKE_OK")
            print(f"active_project_preserved={active0}")
            print(f"allowed_root={os.environ.get('USERPROFILE', str(Path.home()))}")


anyio.run(main)
