# Upstream Modifications and Product Additions

This document records what Rex Desktop Bridge changes relative to upstream components and to the earlier `RDC_Serena_Modify` baseline.

## Product provenance

Initial tested code baseline:

- repository: `https://github.com/Dreamfinal/RDC_Serena_Modify`
- baseline commit: `e2c344f`

Only code/pins were carried forward. User-specific Tunnel IDs, API keys, generated profiles, runtime state, and activity data are deliberately excluded from this product repository.

---

## 1. Serena

### Upstream baseline

- repository: `https://github.com/oraios/serena`
- pinned commit: `7fcbca7e62555ec2287ddb2f083caee805848ea6`
- observed runtime version: `1.7.1.dev0`

### Upstream files modified on disk

None. The uv/Serena installation remains untouched.

The runtime wrapper is loaded through:

- `serena/sitecustomize.py`
- `serena/top_serena_patch.py`

The legacy internal filename `top_serena_patch.py` is retained because this is the patch family already validated before the product rename.

### Wrapper behavior

Selected generic filesystem tools are extended while semantic/LSP tools stay project-scoped:

- `ReadFileTool.apply`
- `CreateTextFileTool.apply`
- `ListDirTool.apply`
- `FindFileTool.apply`
- `ReplaceContentTool.apply`

Supported targeting forms include active-project relative paths, guarded absolute paths, and registered-project filesystem targeting without silently changing Serena's semantic project.

`TOP_FS_ALLOWED_ROOTS` remains the cross-repo filesystem security boundary and defaults to `%USERPROFILE%` in the launcher.

The wrapper also adds a `health` tool and prevents recursive monkey-patching of child Python/LSP processes.

### Product-layer addition

`serena/start-serena-observed-mcp.cmd` starts Serena through the Bridge MCP activity proxy. The proxy does not modify Serena protocol messages; it observes `tools/call` request/response lifecycle for local GUI telemetry.

---

## 2. Desktop Commander / RDC

### Upstream baseline

- repository: `https://github.com/wonderwhy-er/DesktopCommanderMCP`
- npm package: `@wonderwhy-er/desktop-commander`
- pinned version: `0.2.47`

### Runtime mode

RDC uses Desktop Commander's normal local stdio MCP entry, not Desktop Commander's remote-device authentication mode.

### Guarded upstream file patch

Only the upstream config-directory line is patched after `npm ci`:

File:

`rdc/app/node_modules/@wonderwhy-er/desktop-commander/dist/config.js`

Purpose: allow `DESKTOP_COMMANDER_CONFIG_DIR` to select a Bridge-specific config directory outside the upstream default.

The patch is applied only by:

`rdc/patches/apply-config-dir-patch.ps1`

The patcher is fail-closed: an unexpected upstream baseline must be manually rebased instead of guessed.

### Product runtime config

RDC config is generated outside Git under:

`%LOCALAPPDATA%\Rex-Desktop-Bridge\rdc\config\config.json`

Defaults preserve:

- telemetry disabled;
- filesystem scope `%USERPROFILE%`;
- upstream destructive/system denylist;
- `--no-onboarding` runtime mode.

### Product-layer addition

`rdc/start-rdc-observed-mcp.cmd` routes RDC stdio through the same activity proxy used by the GUI.

---

## 3. Rex Desktop Worker

Rex Desktop Worker is a local MCP server added by this project rather than an upstream fork.

Pinned product worker version: `2026.08.25.1`

Primary dependencies are pinned in `desktop/uv.lock`, including:

- MCP Python SDK `1.29.0`
- `mss 10.2.0`
- `pywinauto 0.6.9`

Capabilities include:

- screen/monitor metadata;
- PNG screenshot capture returned as MCP image content;
- visible-window enumeration/focus/wait;
- UI Automation inspection and deterministic control click when available;
- mouse movement/click/scroll fallback;
- keyboard/hotkey/text input;
- input enable/disable guard.

Vision inference is not a local model dependency. Screenshots are returned to the calling multimodal model through MCP.

`desktop/start-desktop-observed-mcp.cmd` adds task telemetry through the shared MCP proxy.

---

## 4. OpenAI tunnel-client

### Tested baseline

- upstream: `https://github.com/openai/tunnel-client`
- pinned version: `0.0.11`
- Windows AMD64 release ZIP and tested EXE hashes are recorded in `versions.json`

The binary is not committed. Setup downloads the official release and verifies hashes before use.

### Bridge profile model

The product generates three separate local profiles:

- `rex-serena`
- `rex-rdc`
- `rex-desktop`

Each profile has one `channel=main` local stdio command and references:

`api_key: "env:CONTROL_PLANE_API_KEY"`

No real Tunnel ID is stored in repository source. The GUI writes user-specific IDs only to local config and generated profiles.

### Automatic provisioning

The GUI can invoke `tunnel-client admin tunnels create` for missing endpoints.

The Admin API key is supplied as `OPENAI_ADMIN_KEY` in the management subprocess environment, not through a command-line secret argument.

---

## 5. Rex Desktop Bridge application layer

New product code under `app/` provides:

- native Tk GUI;
- DPAPI credential storage;
- first-run/key/tunnel Help;
- local tunnel configuration;
- automatic/manual tunnel provisioning;
- three visible terminal process ownership;
- tunnel health display;
- per-worker activity counters and task lists;
- transparent MCP activity proxy.

The app is a supervisor/control center, not a source-code monolith: Serena, RDC, and Desktop remain independent workers.

---

## 6. Foreground security supervisors

`secure-tunnel-supervisor.ps1` retains Windows Job Object `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` protection around each tunnel-client/MCP child tree.

The GUI prototype starts a separate visible PowerShell supervisor terminal per worker and tracks the supervisors it owns. Closing the GUI stops those terminal/process trees.

No Windows Service, Task Scheduler autostart, hidden tray daemon, or background resurrection is part of the prototype.
