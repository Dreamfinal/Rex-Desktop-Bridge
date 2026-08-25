# Security Model (Compatibility Entry)

The canonical security document for Rex Desktop Bridge is:

`docs/SECURITY.md`

This compatibility filename is retained so older links do not point to stale `RDC_Serena_Modify` runtime paths.

Key product invariants:

- no user API key or Tunnel ID in Git;
- DPAPI-encrypted user credential storage outside the repo;
- Runtime key injected only into tunnel process environments;
- optional Admin key used only for management operations;
- separate `rex-serena`, `rex-rdc`, and `rex-desktop` profiles;
- visible foreground terminal supervisors in the prototype;
- local-only task activity telemetry;
- no Windows Service, Task Scheduler autostart, or hidden daemon.
