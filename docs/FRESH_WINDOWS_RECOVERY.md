# Fresh Windows Recovery

Rex Desktop Bridge is designed so a new Windows installation can rebuild the full local stack from this repository without carrying another user's keys or Tunnel IDs.

## Clone

```powershell
git clone https://github.com/Dreamfinal/Rex-Desktop-Bridge.git "$env:USERPROFILE\Documents\AI_Workspace\MCP\Rex-Desktop-Bridge"
cd "$env:USERPROFILE\Documents\AI_Workspace\MCP\Rex-Desktop-Bridge"
.\Setup-All.cmd
```

## What setup restores

- pinned OpenAI tunnel-client binary with hash verification;
- pinned Desktop Commander/RDC runtime and guarded config patch;
- pinned Serena wrapper launch path;
- Rex Desktop Worker environment;
- Rex Desktop Bridge GUI environment;
- Desktop shortcut.

Setup intentionally does not restore a previous user's:

- Runtime API Key;
- Admin API Key;
- Tunnel IDs;
- generated `rex-*` tunnel profiles;
- activity logs;
- local config.

## First launch

Open **Rex Desktop Bridge** and follow `docs/FIRST_RUN.md`.

A genuinely fresh user starts with missing keys/tunnels shown in red. The GUI includes direct Help links for creating the correct OpenAI credentials and tunnel endpoints.

## Recovering the same user's old endpoints

If you are reinstalling Windows and want to reuse previously created Tunnel IDs, keep those IDs in your own secure recovery notes and paste them into the three worker panels after reinstall.

The public/distributable Git repository is intentionally not the backup location for user-specific Tunnel IDs or credentials.

## Existing machine upgrade

When installing the new Bridge on a machine that already has the older local `serena-local`, `rdc-local`, or `desktop-local` profiles, the GUI can discover their Tunnel IDs locally and create separate new `rex-*` profiles without modifying the old files.
