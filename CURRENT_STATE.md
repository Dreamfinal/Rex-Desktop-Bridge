# Rex Desktop Bridge — Current State

Updated: 2026-08-25

## Canonical repository

`https://github.com/Dreamfinal/Rex-Desktop-Bridge`

Recommended local checkout:

`%USERPROFILE%\Documents\AI_Workspace\MCP\Rex-Desktop-Bridge`

## Product version

Prototype: `0.1.5`

The code baseline was carried forward from the tested `RDC_Serena_Modify` recovery stack at commit `e2c344f`, then converted into a distribution-safe product repository. No user-specific Tunnel IDs, API keys, generated tunnel profiles, or runtime state are part of this repository.

## Architecture

```text
                 Rex Desktop Bridge GUI
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
 Serena (Code/Repo)  RDC (OS/CLI)  Rex Desktop (GUI + Vision)
          │             │             │
      rex-serena      rex-rdc       rex-desktop
      Tunnel #1       Tunnel #2      Tunnel #3
          │             │             │
     Task Stream      Task Stream    Task Stream
```

Each tunnel is an independent GUI-owned headless process tree. Terminal log viewers are hidden by default and open only when the user clicks `Show Terminal`.

## Implemented

- Native Windows Tk GUI control center.
- Exact worker labels:
  - `Serena (Code/Repo)`
  - `RDC (OS/CLI)`
  - `Rex Desktop (GUI + Vision)`
- DPAPI-encrypted per-Windows-user credential store for Runtime and optional Admin API keys.
- Add/replace/remove key controls.
- Beginner Help window with direct OpenAI Platform/documentation links.
- Local-only Tunnel ID/config storage under `%LOCALAPPDATA%\Rex-Desktop-Bridge`.
- Distinct generated profiles `rex-serena`, `rex-rdc`, `rex-desktop`; legacy profiles are never overwritten.
- Existing-machine migration discovery can reuse legacy local Tunnel IDs without writing them to Git.
- Automatic creation of missing tunnels through `tunnel-client admin tunnels create` when an Admin key and org/workspace scope are provided.
- Manual Tunnel ID binding per worker.
- Three headless tunnel supervisors start automatically once local configuration is complete; `Show Terminal` opens a live log viewer only on demand.
- Runtime key passed to tunnel processes only through child environments.
- Admin key passed to tunnel-management subprocesses only through environment, never command-line arguments.
- Transparent MCP activity proxy around each worker.
- Per-worker live task events: current/last tool, running, success/failure, duration.
- Task timestamps render in the Windows user's local timezone while durable logs remain UTC.
- Per-worker session/all-time usage counters.
- Adapter retry noise (`-32602 Invalid request parameters`) is excluded from operational Failed counters only when the same tool succeeds within 5 seconds; unrecovered validation errors remain real failures.
- `Clear Logs` removes all Bridge activity history without deleting configuration, keys, Tunnel IDs, or profiles.
- RDC embedded MCP UI previews are suppressed at two layers: the pinned upstream patch removes tool UI metadata, and the Bridge proxy strips Desktop Commander UI resources/structured UI payloads before they reach ChatGPT.
- The Desktop shortcut launches the Tk GUI directly with `pythonw.exe`, avoiding a separate bootstrap-console taskbar icon.
- Setup no longer requires API keys or Tunnel IDs; first-run credentials/tunnel setup happens in the GUI.

## Local verification completed

On Windows 11 on 2026-08-25:

- fresh `setup.ps1 -SkipSmoke` path completed successfully from the new repo/runtime root;
- pinned tunnel-client download/hash verification passed;
- RDC runtime install/config patch passed;
- Desktop Worker and GUI uv environments installed from lockfiles;
- GUI widget construction smoke passed with three worker panels;
- DPAPI encrypt/decrypt/delete smoke passed;
- distribution source scan passed with no real-looking Tunnel ID or secret-like API key in source;
- automatic tunnel provisioning interface smoke confirmed the Admin key is passed via environment, not command-line arguments;
- real `tunnel-client admin tunnels create` parser accepted the provisioning flag shape and stopped only because no Admin key was supplied to that parser check;
- RDC observed MCP smoke passed with tool UI metadata absent, `ui://desktop-commander/*` resources hidden, cached UI resource reads neutralized, and model-facing structured UI payloads stripped;
- GUI activity helper smoke passed for local-time rendering and log clearing;
- Serena observed MCP wrapper smoke passed;
- Rex Desktop observed MCP smoke passed with real PNG screenshot content;
- MCP proxy task-start/task-finish telemetry passed;
- tunnel Job Object kill-on-close smoke passed;
- complete local suite ended with `SMOKE_ALL_OK`.

## Local-only state

Never commit:

- Runtime API Key;
- Admin API Key;
- user Tunnel IDs;
- `%LOCALAPPDATA%\Rex-Desktop-Bridge\config.json`;
- `%LOCALAPPDATA%\Rex-Desktop-Bridge\secrets.json`;
- `%LOCALAPPDATA%\Rex-Desktop-Bridge\activity\*.jsonl`;
- generated `%APPDATA%\tunnel-client\rex-*.yaml`;
- downloaded `tools\tunnel-client\tunnel-client.exe`;
- `node_modules` / `.venv`.

## Pinned component baseline

See `versions.json` for exact pins. Current baseline includes:

- Serena upstream commit `7fcbca7e62555ec2287ddb2f083caee805848ea6`
- Serena wrapper patch `2026.08.21.2`
- Desktop Commander `0.2.47`
- Rex Desktop Worker `2026.08.25.1`
- OpenAI tunnel-client `0.0.11`

## Remaining acceptance before stable release

Prototype code and local smoke gates are complete. Stable release still requires a user-specific **live** acceptance outside Git:

1. provision/configure all three real tunnels;
2. start all three headless tunnels from the GUI and verify each optional `Show Terminal` live-log viewer can open on demand;
3. connect/scan all three matching ChatGPT apps;
4. invoke at least one harmless tool through each live tunnel and confirm the three task streams increment independently;
5. stop one live tunnel and confirm the other two remain reachable;
6. close the GUI and confirm all GUI-owned terminal/tunnel process trees terminate.

Until those live gates pass, version `0.1.5` remains a locally verified prototype rather than a stable release.
