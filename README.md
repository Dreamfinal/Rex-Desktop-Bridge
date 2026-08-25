# Rex Desktop Bridge

**Rex Desktop Bridge** is a Windows control center for three independent local MCP capabilities used with ChatGPT through OpenAI Secure MCP Tunnel:

- **Serena (Code/Repo)** — semantic code/repository work.
- **RDC (OS/CLI)** — filesystem, shell, process, and operating-system work.
- **Rex Desktop (GUI + Vision)** — screenshots, Windows UI Automation, mouse, keyboard, window control, and visual workflows.

The prototype deliberately keeps **three tunnels and three visible terminal windows**. The GUI starts/stops them together, but each tunnel remains an independent process/failure domain.

## What the GUI shows

Each worker has its own panel with:

- worker/tunnel state;
- configured Tunnel ID status;
- Start / Restart / Stop controls;
- session and all-time usage counters;
- live MCP task stream;
- a `Current:` line showing the active tool, or the last completed tool when idle;
- yellow `RUNNING`, green `SUCCESS`, and red `FAILED` task state;
- timestamps rendered in the Windows user's local timezone;
- per-task duration;
- automatic suppression of recovered `-32602 Invalid request parameters` adapter retries from operational failure counters while preserving raw JSONL trace data.

The top of the GUI manages:

- Runtime API Key — required to run tunnels;
- Admin API Key — optional, used only to create missing tunnels automatically;
- Organization/Workspace scope used when creating tunnels;
- beginner Help with direct OpenAI links;
- automatic or manual Tunnel ID setup;
- `Clear Logs`, which clears task/activity history only and preserves configuration, credentials, Tunnel IDs, and profiles.

## Distribution safety

This repository intentionally contains **no user's API keys, Tunnel IDs, generated profiles, or runtime state**.

Per-machine state is created outside Git:

```text
%LOCALAPPDATA%\Rex-Desktop-Bridge\
├── config.json              # local Tunnel IDs and provisioning scope
├── secrets.json             # DPAPI-encrypted credentials
├── state\
└── activity\
    ├── serena.jsonl
    ├── rdc.jsonl
    └── desktop.jsonl

%APPDATA%\tunnel-client\
├── rex-serena.yaml
├── rex-rdc.yaml
└── rex-desktop.yaml
```

Runtime/Admin API keys are encrypted with Windows DPAPI for the current Windows user. Plaintext keys are not written to Git or tunnel profile YAML. Runtime keys are injected into tunnel subprocess environments when they start; Admin keys are injected only into tunnel-management subprocess environments.

## Fresh Windows setup

Recommended clone path:

```powershell
git clone https://github.com/Dreamfinal/Rex-Desktop-Bridge.git "$env:USERPROFILE\Documents\AI_Workspace\MCP\Rex-Desktop-Bridge"
cd "$env:USERPROFILE\Documents\AI_Workspace\MCP\Rex-Desktop-Bridge"
.\Setup-All.cmd
```

`Setup-All.cmd`:

1. checks/installs Git, Node.js LTS, and `uv` when needed;
2. downloads the pinned official OpenAI `tunnel-client` and verifies SHA256;
3. installs the pinned RDC/Desktop Commander runtime and applies guarded config-isolation and MCP-UI-suppression patches;
4. installs the pinned Rex Desktop Worker Python environment;
5. installs the lightweight Tk GUI environment;
6. creates a **Rex Desktop Bridge** Desktop shortcut that launches the GUI directly through `pythonw.exe` (no extra bootstrap-console taskbar icon);
7. runs local smoke tests.

Setup does **not** ask for an API key or Tunnel ID. Those are per-user values and are handled by the GUI after setup.

## First run

Open **Rex Desktop Bridge** from the Desktop.

A fresh user sees missing configuration in red. The app guides the user through:

1. **Runtime API Key** — required for normal tunnel operation.
2. **Admin API Key** — only if the user wants the app to create missing tunnels automatically.
3. **Organization ID / Workspace ID** — scope required by tunnel creation.
4. **Create Missing Tunnels** — creates separate Serena/RDC/Desktop tunnels, or the user can create tunnels manually and paste each `tunnel_...` ID.
5. Once configured, the GUI opens one visible terminal for each tunnel.
6. In ChatGPT Apps/Connectors, bind the matching app to its tunnel and scan MCP tools.

Use the built-in **Beginner Help** button at any point. It includes direct links to OpenAI API Keys, Admin Keys, Organization Settings, Tunnel Settings, Secure MCP Tunnel documentation, and ChatGPT Apps/Connectors.

See `docs/FIRST_RUN.md` for a longer walkthrough.

## Existing machine migration

If the Windows user already has older `serena-local`, `rdc-local`, or `desktop-local` profiles, the Bridge can discover their Tunnel IDs locally and reuse the endpoints with its new profile names:

```text
rex-serena
rex-rdc
rex-desktop
```

The old profiles are not overwritten, and discovered IDs remain local-only.

If an older `CONTROL_PLANE_API_KEY` exists in the Windows user environment, the first-run GUI can offer to import it into the new DPAPI store without displaying the value.

## Why three tunnels?

The system intentionally does not collapse everything into one tunnel:

```text
                 Rex Desktop Bridge
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
 Serena (Code/Repo)  RDC (OS/CLI)  Rex Desktop (GUI + Vision)
          │             │             │
      Tunnel #1       Tunnel #2      Tunnel #3
```

This is **capability isolation**, not three identical mirrors. If one tunnel is unavailable, other capabilities can remain reachable, but RDC does not become Serena's semantic engine and Desktop does not become a shell replacement.

## Task telemetry

The Bridge wraps each local MCP worker with a transparent stdio proxy. It observes `tools/call` requests/responses and writes only local task metadata:

- worker;
- tool name;
- running/success/failed state;
- start/finish timestamp;
- duration;
- short error summary when needed.

Tool arguments and API credentials are not intentionally logged by the activity layer. The GUI can clear all activity history without touching configuration or secrets.

## Security model

- No secret in Git.
- No secret in generated tunnel YAML.
- No Admin key in normal runtime terminals.
- No API key passed as a command-line argument.
- DPAPI encryption is scoped to the current Windows user.
- Three distinct `channel=main` tunnel profiles.
- Visible foreground terminal supervisors in the prototype.
- No Windows Service, Task Scheduler autostart, hidden tray daemon, or background resurrection.
- Closing the GUI stops the terminal supervisors it started.

See `docs/SECURITY.md`.

## Verification

After setup or code changes:

```powershell
.\tests\run-smoke.ps1 -SkipTunnelLive
```

For transport/provisioning changes, also perform live three-tunnel acceptance before declaring a release stable.

## Upstream pins

Exact tested component versions and provenance are stored in `versions.json`. Do not blindly update Serena, Desktop Commander, or `tunnel-client` to `latest`; rebase deliberately and rerun smoke/live acceptance.
