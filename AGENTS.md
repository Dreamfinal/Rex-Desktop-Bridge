# Rex-Desktop-Bridge — Agent Entry Point

This repository is the canonical source for the distributable Windows **Rex Desktop Bridge** application.

It combines three independent MCP capabilities behind one user-facing GUI while preserving separate tunnel/process failure domains:

- `Serena (Code/Repo)`
- `RDC (OS/CLI)`
- `Rex Desktop (GUI + Vision)`

## Optional Staff binding

This Project may start in the runtime's `BASE_MODEL` without loading permanent Staff `SOUL.md`, `MEMORY.md`, or `SKILLS.md`. When Staff context is useful or a named Staff authority is required, `/a <staff>` (or an equivalent natural-language request) overlays that permanent Staff **without changing this Project Repo or working directory**.

Resolve the canonical Team Repo from `AGENT_TEAM_HOME` when configured. In the standard owner workspace layout, fall back to `../../Agent-Team` from `Documents/AI_Workspace/Projects/<project>`. Then read `BOOTSTRAP.md` and execute `skills/staff-load/SKILL.md` from that Team Repo.

`/a` changes `ACTIVE_ACTOR` only and preserves `ACTIVE_PROJECT` plus `ACTIVE_EXECUTION_MODE`. `/p` changes Project only. Do not search this Project Repo for Staff identity as the source of truth, and never copy permanent Staff identity/memory into the Project Repo.

## Read first

1. `CURRENT_STATE.md`
2. `versions.json`
3. `docs/FIRST_RUN.md`
4. `docs/SECURITY.md`
5. `docs/UPSTREAM_MODIFICATIONS.md` before changing pinned upstream components

## Hard rules

- This is a distributable repo. **Never commit any user's Runtime API Key, Admin API Key, Tunnel ID, generated tunnel profile, DPAPI ciphertext, runtime config, activity log, or local state.**
- Tunnel profiles are generated per machine under `%APPDATA%\tunnel-client` using `rex-serena`, `rex-rdc`, and `rex-desktop` names.
- User config, activity data, and DPAPI-encrypted credentials live outside Git under `%LOCALAPPDATA%\Rex-Desktop-Bridge`.
- Runtime API keys may be decrypted only in memory and passed to tunnel processes through their environment.
- Admin API keys are optional and used only for tunnel-management operations such as creating missing tunnels. Do not require an Admin key for normal runtime use.
- Do not place secrets in command-line arguments, logs, YAML, Git, screenshots, or task telemetry.
- Preserve three independent tunnel profiles. Do not collapse all workers into one `channel=main` tunnel.
- Preserve GUI-owned process lifetime: the visible Rex Desktop Bridge GUI owns three headless tunnel supervisors, and optional terminal log viewers open only on explicit user request. No Windows Service, scheduled-task autostart, hidden tray daemon, or background resurrection.
- Closing the GUI must stop terminal supervisors started by that GUI.
- Keep Serena upstream code unmodified; wrapper changes belong in `serena/`.
- Keep the RDC upstream patch fail-closed through `rdc/patches/apply-config-dir-patch.ps1`.
- Keep Desktop Worker input safety controls and do not bypass `REX_DESKTOP_INPUT_ENABLED` guards in tests.
- Do not replace pinned versions with `latest` without an isolated upgrade/rebase and smoke tests.

## Product invariants

- GUI labels are exactly:
  - `Serena (Code/Repo)`
  - `RDC (OS/CLI)`
  - `Rex Desktop (GUI + Vision)`
- Each worker has its own live task stream and usage counters.
- Task status semantics: running = yellow, success = green, failure = red.
- First-run UX must provide beginner help and direct links before or while asking users for OpenAI credentials/tunnel configuration.
- A missing Runtime key makes runtime tunnel status unavailable/red.
- A missing Admin key must **not** make already-configured runtime tunnels red; it only disables automatic tunnel management.
- Tunnel IDs are identifiers, not passwords, but they are still user-specific local configuration and must not be shipped in Git.

## Verification

After setup or a functional change, run:

```powershell
.\tests\run-smoke.ps1 -SkipTunnelLive
```

For tunnel-client/profile/provisioning changes, additionally perform live tunnel acceptance before declaring a release stable.
