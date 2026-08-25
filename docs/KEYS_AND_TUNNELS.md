# Keys and Tunnels

This repository ships no user-specific key or Tunnel ID.

## Runtime API Key

Normal tunnel operation uses a Runtime/API key made available to `tunnel-client` as:

`CONTROL_PLANE_API_KEY`

GUI page:

`https://platform.openai.com/settings/organization/api-keys`

The GUI saves the value with Windows DPAPI, then injects plaintext only into the environment of tunnel processes it starts.

## Admin API Key

Automatic tunnel creation uses an Admin API key made available only to the management subprocess as:

`OPENAI_ADMIN_KEY`

GUI page:

`https://platform.openai.com/settings/organization/admin-keys`

OpenAI Admin API keys are elevated organization credentials. The Bridge never requires an Admin key just to run already-configured tunnels.

## Tunnel scope

Current pinned `tunnel-client` requires tunnel creation to include at least one organization or workspace attachment.

The GUI stores those IDs locally in `%LOCALAPPDATA%\Rex-Desktop-Bridge\config.json`.

Useful organization settings page:

`https://platform.openai.com/settings/organization/general`

## Tunnel endpoints

The Bridge expects three separate endpoint identities on each user's machine:

| Capability | Local profile | Tunnel ID source |
| --- | --- | --- |
| Serena (Code/Repo) | `rex-serena` | local config / created by user |
| RDC (OS/CLI) | `rex-rdc` | local config / created by user |
| Rex Desktop (GUI + Vision) | `rex-desktop` | local config / created by user |

Tunnel management page:

`https://platform.openai.com/settings/organization/tunnels`

## Automatic creation flow

When **Create Missing Tunnels** runs:

1. the GUI confirms an Admin key exists;
2. the GUI confirms at least one Organization ID or Workspace ID exists;
3. each missing capability invokes `tunnel-client admin tunnels create` separately;
4. the Admin key is supplied through `OPENAI_ADMIN_KEY` in the subprocess environment;
5. the returned `tunnel_...` identifier is stored only in local config;
6. the corresponding `rex-*` YAML profile is generated;
7. the YAML references `env:CONTROL_PLANE_API_KEY` rather than embedding a Runtime key.

## Manual creation flow

Users who do not want to save an Admin key can create tunnels on the OpenAI tunnel settings page and paste each resulting Tunnel ID into **Set Tunnel ID** on the matching worker panel.

## Existing profile migration

For migration from the older recovery stack only, the app may read local profile files named:

- `serena-local.yaml`
- `rdc-local.yaml`
- `desktop-local.yaml`

If a local config entry is blank, it can reuse a discovered Tunnel ID under the new `rex-*` profile name. It does not edit the legacy profile.

This discovery happens on the user's machine. No discovered identifier is written back into Git.

## ChatGPT binding

After a tunnel terminal is ready, connect the matching ChatGPT app/connector to that tunnel and scan tools.

ChatGPT Apps/Connectors:

`https://chatgpt.com/#settings/Connectors`
