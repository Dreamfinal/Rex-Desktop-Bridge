from __future__ import annotations

HELP_TEXT = """Rex Desktop Bridge uses three separate Secure MCP tunnels:

  • Serena (Code/Repo)
  • RDC (OS/CLI)
  • Rex Desktop (GUI + Vision)

1) Runtime API Key — required for normal use
Create/manage the Runtime/API key in the OpenAI Platform API key settings. The key must belong to the organization/workspace that can use your tunnels. Rex Desktop Bridge encrypts the saved value with Windows DPAPI for the current Windows user. It is never written to Git or to the tunnel YAML profile.

2) Admin API Key — only required to create missing tunnels automatically
OpenAI Admin API keys have elevated organization permissions. Current OpenAI documentation says Organization Owners create/manage Admin API keys. You can remove this key from Rex Desktop Bridge after all three tunnels have been created; existing tunnels can still run with the Runtime key.

3) Organization ID / Workspace ID — required scope for automatic tunnel creation
For ChatGPT connector use, enter the target ChatGPT Workspace ID in Bridge Settings before automatic tunnel creation. You may also add Platform Organization IDs as extra scope. A tunnel associated only with a Platform organization may not appear in the target ChatGPT workspace.

4) Tunnel ID — not a password
A Tunnel ID looks like tunnel_... . It identifies a tunnel endpoint; it is not an API secret. You can let this app create missing tunnels using the Admin key, or create them yourself on the Tunnels page and paste each Tunnel ID into the matching worker card.

5) Connect the tunnels to ChatGPT
Order matters: first create or bind the Tunnel ID in Rex Desktop Bridge, then start that tunnel and wait until its card says Online / ready and ChatGPT READY. Only then open ChatGPT Apps/Connectors, create or edit the app, choose the matching tunnel, and scan its MCP tools. Keep the three capabilities separate so one tunnel failure does not remove every local capability at once.

Security notes
  • Never commit Runtime or Admin keys.
  • Do not paste an Admin key where a Runtime key is requested.
  • Removing the Admin key does not delete already-created tunnels.
  • Closing Rex Desktop Bridge stops the terminal supervisors started by this GUI.
"""
