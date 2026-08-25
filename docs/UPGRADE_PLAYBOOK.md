# Upgrade Playbook

Rex Desktop Bridge intentionally pins upstream components. Do not replace pins with `latest` in the normal branch.

## Before changing a pin

1. Read `versions.json`.
2. Read `docs/UPSTREAM_MODIFICATIONS.md`.
3. Create an isolated upgrade branch.
4. Record the exact upstream version/commit being evaluated.
5. Never copy local keys, Tunnel IDs, generated profiles, or runtime config into the branch.

## Serena upgrade

1. Change the pinned Serena commit only in the isolated branch.
2. Re-run the wrapper smoke through `serena/start-serena-observed-mcp.cmd`.
3. Verify wrapper patch points still exist and generic cross-repo filesystem behavior remains guarded.
4. Verify semantic project state is preserved across cross-repo filesystem operations.
5. Verify activity proxy telemetry records Serena tool calls without altering MCP responses.

## RDC / Desktop Commander upgrade

1. Change the npm pin deliberately.
2. Run `npm ci`.
3. Run `rdc/patches/apply-config-dir-patch.ps1 -CheckOnly` before applying changes.
4. If the exact upstream config line moved/changed, stop and manually rebase the patch; do not guess.
5. Re-run RDC local MCP and filesystem guard smoke through the observed launcher.
6. Review production dependency audit state and document material changes.

## Rex Desktop Worker upgrade

1. Change dependencies in `desktop/pyproject.toml`.
2. regenerate `desktop/uv.lock` intentionally;
3. test screenshot MCP image output;
4. test UI Automation/window inspection paths;
5. keep computer-input safety guards disabled during smoke tests;
6. verify Desktop activity telemetry still records tool lifecycle.

## tunnel-client upgrade

Treat a tunnel-client bump as a transport/security change.

1. Download the exact release candidate.
2. record ZIP and EXE SHA256 in `versions.json`;
3. run local `doctor` against throwaway/non-secret test configuration when possible;
4. verify the three separate profile model remains supported;
5. verify environment-referenced Runtime key behavior;
6. verify `admin tunnels create` flags/output used by automatic provisioning;
7. run live three-tunnel coexistence acceptance;
8. close the GUI/supervisors and verify no protected tunnel/MCP descendants remain.

## Bridge GUI / credential changes

1. Run DPAPI round-trip tests.
2. run source scan for real-looking Tunnel IDs and secret-like API keys;
3. verify Runtime/Admin key values never enter command-line arguments;
4. verify Admin key removal does not stop configured runtime tunnels;
5. verify Runtime key removal stops GUI-owned terminals;
6. verify first-run Help links remain current;
7. verify worker labels remain exactly as specified in `AGENTS.md`.

## Required local verification

```powershell
.\tests\run-smoke.ps1 -SkipTunnelLive
```

## Required live verification for transport/provisioning changes

With user-specific local config outside Git:

1. start all three terminals from the GUI;
2. confirm `Serena (Code/Repo)` is ready;
3. confirm `RDC (OS/CLI)` is ready;
4. confirm `Rex Desktop (GUI + Vision)` is ready;
5. invoke at least one harmless tool through each ChatGPT app;
6. verify each GUI task stream increments independently;
7. stop one tunnel and verify the other two remain available;
8. close the GUI and verify all terminal supervisors it started are terminated.

Only after those gates pass should the version pin be merged/tagged.
