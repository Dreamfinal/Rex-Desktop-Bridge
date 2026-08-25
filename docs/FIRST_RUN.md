# First Run — Beginner Guide

This guide assumes a fresh Windows machine and no existing tunnels.

## 1. Install the Bridge

```powershell
git clone https://github.com/Dreamfinal/Rex-Desktop-Bridge.git "$env:USERPROFILE\Documents\AI_Workspace\MCP\Rex-Desktop-Bridge"
cd "$env:USERPROFILE\Documents\AI_Workspace\MCP\Rex-Desktop-Bridge"
.\Setup-All.cmd
```

Setup installs/verifies the local software. It does **not** ask for your OpenAI keys or Tunnel IDs.

Open the **Rex Desktop Bridge** shortcut after setup.

## 2. Runtime API Key

The Runtime/API key is required whenever the three tunnel terminals connect to OpenAI.

Open:

`https://platform.openai.com/settings/organization/api-keys`

Create/use a key in the organization that should own/use the tunnels, then paste it into **Runtime API Key → Add / Replace**.

If you are not sure what to create, click **Help** beside the key field first.

The Bridge stores the key encrypted by Windows DPAPI for the current Windows user. It does not put the plaintext key in Git or tunnel YAML.

## 3. Decide how to create tunnels

You need three tunnel endpoints:

- `Serena (Code/Repo)`
- `RDC (OS/CLI)`
- `Rex Desktop (GUI + Vision)`

You can either let the app create them or create them manually.

### Option A — automatic creation

Automatic creation needs an **Admin API Key** because creating tunnels is a management operation.

Open:

`https://platform.openai.com/settings/organization/admin-keys`

OpenAI Admin API keys are elevated organization credentials; current OpenAI documentation states Organization Owners create/manage them. Save the Admin key in the Bridge only for as long as you need automatic tunnel management. It is not required to run already-created tunnels.

Next click **Set Org / Workspace IDs**. `tunnel-client` requires at least one organization or workspace attachment when creating a tunnel.

Useful settings page:

`https://platform.openai.com/settings/organization/general`

Then click **Create Missing Tunnels**. The Bridge creates each missing endpoint separately and stores the resulting Tunnel IDs only in local config.

### Option B — manual creation

Open:

`https://platform.openai.com/settings/organization/tunnels`

Create the three tunnels yourself. Copy each `tunnel_...` identifier and use **Set Tunnel ID** on the matching worker card.

A Tunnel ID identifies an endpoint. It is not a password/API key, but this project still treats it as user-specific local configuration and does not ship it in Git.

## 4. What happens when configuration is complete

When the Runtime key and all three Tunnel IDs are configured, the prototype automatically opens three visible PowerShell terminals:

```text
Serena (Code/Repo)          → rex-serena
RDC (OS/CLI)                → rex-rdc
Rex Desktop (GUI + Vision)  → rex-desktop
```

The GUI stays open as the control center.

Status meanings:

- green — ready/success;
- yellow — starting/running;
- red — missing configuration/failure;
- gray — stopped.

The Admin key may show as not saved while all three runtime tunnels remain green. That is expected: the Admin key is not needed for normal runtime operation.

## 5. Connect the tunnels to ChatGPT

Open ChatGPT Apps/Connectors:

`https://chatgpt.com/#settings/Connectors`

For each capability:

1. create/edit the corresponding app;
2. choose the matching Secure MCP tunnel;
3. scan tools;
4. keep the capability names distinct so you can tell which tool family is being invoked.

The Bridge GUI then shows task activity independently in the three panels.

## 6. Built-in Help links

The GUI **Beginner Help** window links directly to:

- Runtime/API Keys;
- Admin Keys;
- Organization Settings;
- Tunnel Settings;
- Secure MCP Tunnel docs;
- ChatGPT Apps/Connectors.

Use Help before pasting a key if you are unsure which credential is being requested.

## 7. Removing keys

### Remove Admin API Key

Safe after tunnels are created if you do not need automatic tunnel management. Existing tunnels still use the Runtime key.

### Remove Runtime API Key

The Bridge stops tunnels it owns before deleting the saved Runtime key. Runtime tunnel status becomes unavailable/red until a Runtime key is saved again.

## 8. Existing-machine migration

If older local tunnel profiles exist, the Bridge can discover their Tunnel IDs locally and reuse the same endpoints under new `rex-*` profile names without overwriting the old profiles.

If an older `CONTROL_PLANE_API_KEY` exists in the Windows user environment, first run can offer to import it into the DPAPI store without displaying its value.

None of this migration data is written into the Git repository.
