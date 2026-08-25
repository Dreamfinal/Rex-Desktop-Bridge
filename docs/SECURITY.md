# Security Model

## Secret storage

Rex Desktop Bridge stores Runtime and Admin API keys with Windows DPAPI for the current Windows user.

Encrypted ciphertext is kept outside Git at:

`%LOCALAPPDATA%\Rex-Desktop-Bridge\secrets.json`

Plaintext credentials are decrypted only when the running GUI needs them.

## Runtime API Key

The Runtime key is passed to each tunnel supervisor through its child-process environment as `CONTROL_PLANE_API_KEY`.

It is not intentionally written to:

- Git;
- tunnel YAML;
- command-line arguments;
- activity telemetry;
- console log messages.

## Admin API Key

The Admin key is optional. It is used only for tunnel-management operations such as automatic tunnel creation.

When used, it is passed to `tunnel-client admin ...` through the management subprocess environment as `OPENAI_ADMIN_KEY`, not as `--admin-key <secret>` on the command line.

Removing the Admin key does not remove or disable existing tunnels.

## Tunnel IDs

Tunnel IDs are identifiers rather than authentication secrets. Even so, this distributable project treats them as user-specific local configuration and does not store real user Tunnel IDs in Git.

Local Tunnel IDs live in:

`%LOCALAPPDATA%\Rex-Desktop-Bridge\config.json`

Generated tunnel profiles live in:

`%APPDATA%\tunnel-client\rex-serena.yaml`

`%APPDATA%\tunnel-client\rex-rdc.yaml`

`%APPDATA%\tunnel-client\rex-desktop.yaml`

The generated profiles reference `env:CONTROL_PLANE_API_KEY`; they do not contain the plaintext Runtime key.

## Capability separation

The system intentionally uses three separate tunnel profiles:

- `rex-serena`
- `rex-rdc`
- `rex-desktop`

This prevents one tunnel/process failure from necessarily removing every local capability. It is capability isolation, not full mirror redundancy.

## Foreground process ownership

Prototype behavior is intentionally visible:

- one GUI;
- up to three visible PowerShell tunnel terminals;
- no Windows Service;
- no scheduled-task autostart;
- no hidden tray daemon;
- no background resurrection.

The GUI tracks the terminal supervisors it starts and stops their process trees when the GUI closes.

Each tunnel supervisor additionally uses a Windows Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` for the tunnel/MCP descendants it owns.

## Activity telemetry

The MCP proxy records local task metadata only:

- worker;
- tool name;
- status;
- timestamps;
- duration;
- a short error result when a tool fails.

The activity layer does not intentionally record tool arguments, screenshots, file contents, API keys, or tunnel credentials.

Activity logs stay local under:

`%LOCALAPPDATA%\Rex-Desktop-Bridge\activity`

## Repository scanning

The smoke suite scans source text for:

- real-looking `tunnel_...` IDs;
- secret-like OpenAI API key prefixes.

A finding fails the smoke suite before release/commit acceptance.

## Upstream boundary

- Serena's upstream installation stays unmodified; behavior changes are wrapper/runtime patches under `serena/`.
- RDC's pinned upstream package patch is applied only through its guarded patch script.
- Downloaded tunnel-client binaries and runtime dependencies are not committed.
