from __future__ import annotations

import subprocess

import bridge.tunnels as tunnels
from bridge.constants import WORKERS


def main() -> None:
    original = tunnels._run_tunnel_client
    captured: dict[str, object] = {}

    def fake_run(args: list[str], env: dict[str, str], timeout: int = 45) -> subprocess.CompletedProcess[str]:
        captured["args"] = list(args)
        captured["env_admin"] = env.get("OPENAI_ADMIN_KEY")
        captured["timeout"] = timeout
        return subprocess.CompletedProcess(args=args, returncode=0, stdout='{"id":"tunnel_abc"}', stderr="")

    tunnels._run_tunnel_client = fake_run
    try:
        result = tunnels.create_tunnel(
            WORKERS[0],
            admin_key="not-a-real-admin-key",
            organization_ids=["org_example"],
            workspace_ids=["ws_example"],
        )
    finally:
        tunnels._run_tunnel_client = original

    assert result == "tunnel_abc"
    args = captured["args"]
    assert isinstance(args, list)
    assert "not-a-real-admin-key" not in args
    assert captured["env_admin"] == "not-a-real-admin-key"
    assert "--organization-id" in args and "org_example" in args
    assert "--workspace-id" in args and "ws_example" in args

    try:
        tunnels.create_tunnel(
            WORKERS[0],
            admin_key="not-a-real-admin-key",
            organization_ids=["org_example"],
            workspace_ids=[],
        )
    except ValueError as exc:
        assert "Workspace ID" in str(exc)
    else:
        raise AssertionError("ChatGPT workspace scope was not required")

    print("TUNNEL_PROVISIONING_INTERFACE_SMOKE_OK")


if __name__ == "__main__":
    main()
