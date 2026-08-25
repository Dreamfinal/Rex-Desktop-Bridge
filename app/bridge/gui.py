from __future__ import annotations

import os
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, simpledialog, ttk
from typing import Callable

from .activity import clear_activity_logs, format_local_time, snapshot
from .config import BridgeConfig
from .constants import (
    APP_NAME,
    APP_VERSION,
    CHATGPT_PLUGINS_URL,
    OPENAI_ADMIN_KEYS_URL,
    OPENAI_API_KEYS_URL,
    OPENAI_ORG_SETTINGS_URL,
    OPENAI_SECURE_TUNNEL_DOCS_URL,
    OPENAI_TUNNELS_URL,
    TUNNEL_CLIENT,
    WORKERS,
    WORKER_BY_KEY,
)
from .credentials import ADMIN_KEY_NAME, RUNTIME_KEY_NAME, CredentialStore, read_legacy_user_environment
from .help_text import HELP_TEXT
from .processes import BridgeProcessManager, clear_tunnel_logs
from .tunnels import create_missing_tunnels, delete_profile, ensure_profiles, probe_health, write_profile


STATUS_COLORS = {
    "green": "#16803c",
    "yellow": "#b7791f",
    "red": "#c53030",
    "gray": "#6b7280",
}


class CredentialDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        description: str,
        help_callback: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: str | None = None

        frame = ttk.Frame(self, padding=18)
        frame.grid(sticky="nsew")
        ttk.Label(frame, text=title, font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(frame, text=description, wraplength=520, justify="left").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(8, 12)
        )
        self.value = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=self.value, width=72, show="•")
        entry.grid(row=2, column=0, columnspan=3, sticky="ew")
        entry.focus_set()

        ttk.Button(frame, text="Open Help", command=help_callback).grid(row=3, column=0, sticky="w", pady=(14, 0))
        ttk.Button(frame, text="Cancel", command=self.destroy).grid(row=3, column=1, sticky="e", padx=(8, 0), pady=(14, 0))
        ttk.Button(frame, text="Save", command=self._save).grid(row=3, column=2, sticky="e", padx=(8, 0), pady=(14, 0))
        self.bind("<Return>", lambda _event: self._save())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _save(self) -> None:
        value = self.value.get().strip()
        if not value:
            messagebox.showerror("Missing value", "Paste the key before saving.", parent=self)
            return
        self.result = value
        self.destroy()


class HelpWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("Rex Desktop Bridge — Beginner Setup Help")
        self.geometry("820x700")
        self.transient(parent)

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="First-time OpenAI Tunnel Setup", font=("Segoe UI", 15, "bold")).pack(anchor="w")

        text = tk.Text(outer, wrap="word", height=28, padx=10, pady=10)
        text.pack(fill="both", expand=True, pady=(10, 10))
        text.insert("1.0", HELP_TEXT)
        text.configure(state="disabled")

        links = ttk.Frame(outer)
        links.pack(fill="x")
        buttons = (
            ("Runtime/API Keys", OPENAI_API_KEYS_URL),
            ("Admin Keys", OPENAI_ADMIN_KEYS_URL),
            ("Organization Settings", OPENAI_ORG_SETTINGS_URL),
            ("Tunnel Settings", OPENAI_TUNNELS_URL),
            ("Secure MCP Tunnel Docs", OPENAI_SECURE_TUNNEL_DOCS_URL),
            ("ChatGPT Apps/Connectors", CHATGPT_PLUGINS_URL),
        )
        for index, (label, url) in enumerate(buttons):
            ttk.Button(links, text=label, command=lambda target=url: webbrowser.open(target)).grid(
                row=index // 3, column=index % 3, sticky="ew", padx=4, pady=4
            )
            links.columnconfigure(index % 3, weight=1)


class ScopeDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, config: BridgeConfig, help_callback: Callable[[], None]) -> None:
        super().__init__(parent)
        self.title("Tunnel Creation Scope")
        self.transient(parent)
        self.grab_set()
        self.result: tuple[list[str], list[str]] | None = None

        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Tunnel Creation Scope", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            frame,
            text="Automatic tunnel creation requires at least one Organization ID or Workspace ID. Separate multiple IDs with commas.",
            wraplength=620,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 12))

        self.org = tk.StringVar(value=", ".join(config.organization_ids()))
        self.workspace = tk.StringVar(value=", ".join(config.workspace_ids()))
        ttk.Label(frame, text="Organization ID(s)").grid(row=2, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.org, width=70).grid(row=2, column=1, sticky="ew", padx=(10, 0))
        ttk.Label(frame, text="Workspace ID(s)").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.workspace, width=70).grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=(8, 0))

        controls = ttk.Frame(frame)
        controls.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        ttk.Button(controls, text="Open Help", command=help_callback).pack(side="left")
        ttk.Button(controls, text="Cancel", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(controls, text="Save", command=self._save).pack(side="right")
        frame.columnconfigure(1, weight=1)

    @staticmethod
    def _split(value: str) -> list[str]:
        return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]

    def _save(self) -> None:
        orgs = self._split(self.org.get())
        workspaces = self._split(self.workspace.get())
        if not orgs and not workspaces:
            messagebox.showerror("Scope required", "Enter at least one Organization ID or Workspace ID.", parent=self)
            return
        self.result = (orgs, workspaces)
        self.destroy()


class WorkerPanel(ttk.LabelFrame):
    def __init__(self, parent: tk.Misc, worker_key: str, app: "BridgeApp") -> None:
        self.worker = WORKER_BY_KEY[worker_key]
        super().__init__(parent, text=self.worker.label, padding=10)
        self.app = app

        self.status_dot = tk.Label(self, text="●", fg=STATUS_COLORS["gray"], font=("Segoe UI", 15, "bold"))
        self.status_dot.grid(row=0, column=0, sticky="w")
        self.status_text = ttk.Label(self, text="Stopped")
        self.status_text.grid(row=0, column=1, columnspan=2, sticky="w", padx=(4, 0))

        self.tunnel_text = ttk.Label(self, text="Tunnel: checking...")
        self.tunnel_text.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 2))
        self.count_text = ttk.Label(self, text="Session 0 | Success 0 | Failed 0 | All-time 0")
        self.count_text.grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self.current_text = tk.Label(self, text="Current: idle", fg=STATUS_COLORS["gray"], anchor="w")
        self.current_text.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 6))

        controls = ttk.Frame(self)
        controls.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        ttk.Button(controls, text="Start", command=lambda: app.start_worker(worker_key)).pack(side="left")
        ttk.Button(controls, text="Restart", command=lambda: app.restart_worker(worker_key)).pack(side="left", padx=(4, 0))
        ttk.Button(controls, text="Stop", command=lambda: app.stop_worker(worker_key)).pack(side="left", padx=(4, 0))
        ttk.Button(controls, text="Show Terminal", command=lambda: app.show_terminal(worker_key)).pack(side="left", padx=(4, 0))
        ttk.Button(controls, text="Set Tunnel ID", command=lambda: app.set_tunnel_id(worker_key)).pack(side="right")

        self.tree = ttk.Treeview(self, columns=("time", "tool", "status", "duration"), show="headings", height=14)
        for name, label, width in (
            ("time", "Time", 80),
            ("tool", "Task / Tool", 180),
            ("status", "Status", 70),
            ("duration", "ms", 60),
        ):
            self.tree.heading(name, text=label)
            self.tree.column(name, width=width, anchor="w")
        self.tree.grid(row=5, column=0, columnspan=3, sticky="nsew")
        self.tree.tag_configure("running", foreground=STATUS_COLORS["yellow"])
        self.tree.tag_configure("success", foreground=STATUS_COLORS["green"])
        self.tree.tag_configure("failed", foreground=STATUS_COLORS["red"])
        self.rowconfigure(5, weight=1)
        self.columnconfigure(1, weight=1)
        self._last_task_state: tuple[tuple[str, str, int | None], ...] = ()

    def update_status(self, state: str, detail: str, tunnel_id: str, snapshot_data) -> None:
        self.status_dot.configure(fg=STATUS_COLORS.get(state, STATUS_COLORS["gray"]))
        connector_state = "READY" if state == "green" else "BLOCKED"
        self.status_text.configure(text=f"{detail} | ChatGPT {connector_state}")
        if tunnel_id:
            rendered = tunnel_id if len(tunnel_id) <= 32 else tunnel_id[:18] + "…" + tunnel_id[-8:]
            self.tunnel_text.configure(text=f"Tunnel: {rendered}")
        else:
            self.tunnel_text.configure(text="Tunnel: NOT CONFIGURED")
        self.count_text.configure(
            text=(
                f"Session {snapshot_data.session_total} | Success {snapshot_data.session_success} | "
                f"Failed {snapshot_data.session_failed} | All-time {snapshot_data.all_total}"
            )
        )

        running_tasks = [task for task in snapshot_data.tasks if task.status == "running"]
        if running_tasks:
            names = ", ".join(task.tool for task in running_tasks[:3])
            suffix = "" if len(running_tasks) <= 3 else f" +{len(running_tasks) - 3}"
            self.current_text.configure(text=f"Current: {names}{suffix} (RUNNING)", fg=STATUS_COLORS["yellow"])
        elif snapshot_data.tasks:
            latest = snapshot_data.tasks[0]
            self.current_text.configure(
                text=f"Current: idle | Last: {latest.tool} {latest.status.upper()}",
                fg=STATUS_COLORS["gray"],
            )
        else:
            self.current_text.configure(text="Current: idle", fg=STATUS_COLORS["gray"])

        task_state = tuple((task.task_id, task.status, task.duration_ms) for task in snapshot_data.tasks)
        if task_state == self._last_task_state:
            return
        self._last_task_state = task_state
        for item in self.tree.get_children():
            self.tree.delete(item)
        for task in snapshot_data.tasks:
            time_text = format_local_time(task.started_at)
            duration = "" if task.duration_ms is None else str(task.duration_ms)
            self.tree.insert("", "end", values=(time_text, task.tool, task.status.upper(), duration), tags=(task.status,))

    def clear_view(self) -> None:
        self._last_task_state = ()
        self.count_text.configure(text="Session 0 | Success 0 | Failed 0 | All-time 0")
        self.current_text.configure(text="Current: idle", fg=STATUS_COLORS["gray"])
        for item in self.tree.get_children():
            self.tree.delete(item)


class BridgeApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} — {APP_VERSION}")
        self.geometry("1420x820")
        self.minsize(1120, 680)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.config_store = BridgeConfig()
        self.credentials = CredentialStore()
        self.processes = BridgeProcessManager()
        self.busy = False
        self._poll_tick = 0
        self._connection_cache: dict[str, tuple[str, str, bool]] = {}

        ensure_profiles(self.config_store)
        self._build_ui()
        self.after(400, self._first_run_assistant)
        self.after(500, self._poll)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x")
        ttk.Label(header, text="Rex Desktop Bridge", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Label(header, text="3 independent MCP tunnels · foreground prototype", foreground="#555").pack(side="left", padx=(12, 0))
        ttk.Button(header, text="Beginner Help", command=self.show_help).pack(side="right")

        key_frame = ttk.LabelFrame(root, text="Keys & Provisioning", padding=10)
        key_frame.pack(fill="x", pady=(10, 10))

        self.runtime_status = ttk.Label(key_frame, text="Runtime API Key: checking...")
        self.runtime_status.grid(row=0, column=0, sticky="w")
        ttk.Button(key_frame, text="Add / Replace", command=lambda: self.edit_key(RUNTIME_KEY_NAME)).grid(row=0, column=1, padx=5)
        ttk.Button(key_frame, text="Remove", command=lambda: self.remove_key(RUNTIME_KEY_NAME)).grid(row=0, column=2, padx=5)
        ttk.Button(key_frame, text="Help", command=self.show_help).grid(row=0, column=3, padx=5)

        self.admin_status = ttk.Label(key_frame, text="Admin API Key: checking...")
        self.admin_status.grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Button(key_frame, text="Add / Replace", command=lambda: self.edit_key(ADMIN_KEY_NAME)).grid(row=1, column=1, padx=5, pady=(6, 0))
        ttk.Button(key_frame, text="Remove", command=lambda: self.remove_key(ADMIN_KEY_NAME)).grid(row=1, column=2, padx=5, pady=(6, 0))
        ttk.Button(key_frame, text="Help", command=self.show_help).grid(row=1, column=3, padx=5, pady=(6, 0))

        self.scope_status = ttk.Label(key_frame, text="Tunnel creation scope: not set")
        self.scope_status.grid(row=0, column=4, rowspan=2, sticky="w", padx=(24, 8))
        ttk.Button(key_frame, text="Set Org / Workspace IDs", command=self.edit_scope).grid(row=0, column=5, padx=5)
        self.create_button = ttk.Button(key_frame, text="Create Missing Tunnels", command=self.create_missing)
        self.create_button.grid(row=1, column=5, padx=5, pady=(6, 0))
        ttk.Button(key_frame, text="Open Tunnel Settings", command=lambda: webbrowser.open(OPENAI_TUNNELS_URL)).grid(row=0, column=6, rowspan=2, padx=(5, 0))
        key_frame.columnconfigure(4, weight=1)

        bridge_controls = ttk.Frame(root)
        bridge_controls.pack(fill="x", pady=(0, 8))
        ttk.Button(bridge_controls, text="Start All Configured Tunnels", command=self.start_all).pack(side="left")
        ttk.Button(bridge_controls, text="Stop All", command=self.stop_all).pack(side="left", padx=(6, 0))
        ttk.Button(bridge_controls, text="Clear Logs", command=self.clear_logs).pack(side="left", padx=(6, 0))
        self.global_status = ttk.Label(bridge_controls, text="")
        self.global_status.pack(side="left", padx=(14, 0))
        ttk.Label(
            bridge_controls,
            text="Tunnels run headless by default; Show Terminal opens a live log viewer on demand.",
            foreground="#555",
        ).pack(side="right")

        panels = ttk.Frame(root)
        panels.pack(fill="both", expand=True)
        self.panels: dict[str, WorkerPanel] = {}
        for index, worker in enumerate(WORKERS):
            panel = WorkerPanel(panels, worker.key, self)
            panel.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 5, 0 if index == 2 else 5))
            panels.columnconfigure(index, weight=1, uniform="worker")
            self.panels[worker.key] = panel
        panels.rowconfigure(0, weight=1)

    def show_help(self) -> None:
        HelpWindow(self)

    def edit_key(self, key_name: str) -> None:
        if key_name == RUNTIME_KEY_NAME:
            title = "Runtime API Key"
            description = (
                "Required to run the three Secure MCP tunnels. Paste the Runtime/API key here. "
                "Use Open Help if this is your first time creating one. The saved value is encrypted with Windows DPAPI."
            )
        else:
            title = "Admin API Key"
            description = (
                "Needed only when Rex Desktop Bridge must create missing tunnels automatically. "
                "This is an elevated organization credential; open Help before creating one if you are unsure."
            )
        dialog = CredentialDialog(self, title, description, self.show_help)
        self.wait_window(dialog)
        if dialog.result:
            try:
                self.credentials.set(key_name, dialog.result)
                self._refresh_top_status()
            except Exception as exc:
                messagebox.showerror("Could not save key", str(exc), parent=self)

    def remove_key(self, key_name: str) -> None:
        label = "Runtime API Key" if key_name == RUNTIME_KEY_NAME else "Admin API Key"
        if not self.credentials.has(key_name):
            return
        if not messagebox.askyesno("Remove key", f"Remove the saved {label} from this Windows user?", parent=self):
            return
        if key_name == RUNTIME_KEY_NAME:
            self.stop_all()
        self.credentials.delete(key_name)
        self._refresh_top_status()

    def edit_scope(self) -> None:
        dialog = ScopeDialog(self, self.config_store, self.show_help)
        self.wait_window(dialog)
        if dialog.result:
            self.config_store.set_scopes(*dialog.result)
            self._refresh_top_status()

    def set_tunnel_id(self, worker_key: str) -> None:
        worker = WORKER_BY_KEY[worker_key]
        current = self.config_store.tunnel_id(worker_key)
        value = simpledialog.askstring(
            f"{worker.label} Tunnel ID",
            "Paste the tunnel_... ID. Tunnel IDs are identifiers, not API secrets.\nLeave blank to remove the local binding.",
            initialvalue=current,
            parent=self,
        )
        if value is None:
            return
        try:
            self.config_store.set_tunnel_id(worker_key, value)
            if value.strip():
                write_profile(worker, value.strip())
            else:
                self.processes.stop(worker_key)
                delete_profile(worker)
            self._refresh_top_status()
        except Exception as exc:
            messagebox.showerror("Invalid Tunnel ID", str(exc), parent=self)

    def _runtime_key(self) -> str | None:
        return self.credentials.get(RUNTIME_KEY_NAME)

    def _admin_key(self) -> str | None:
        return self.credentials.get(ADMIN_KEY_NAME)

    def _first_run_assistant(self) -> None:
        if not self.config_store.legacy_key_migration_done and not self.credentials.has(RUNTIME_KEY_NAME):
            legacy = read_legacy_user_environment("CONTROL_PLANE_API_KEY")
            if legacy:
                if messagebox.askyesno(
                    "Existing Runtime Key Found",
                    "An existing Runtime API Key was found in your Windows user environment from an older setup. "
                    "Import it into Rex Desktop Bridge's DPAPI-encrypted store? The key itself will not be displayed.",
                    parent=self,
                ):
                    try:
                        self.credentials.set(RUNTIME_KEY_NAME, legacy)
                    except Exception as exc:
                        messagebox.showerror("Import failed", str(exc), parent=self)
            self.config_store.mark_legacy_key_migration_done()

        if not self.credentials.has(RUNTIME_KEY_NAME):
            self.edit_key(RUNTIME_KEY_NAME)

        missing = [worker for worker in WORKERS if not self.config_store.tunnel_id(worker.key)]
        if missing:
            labels = "\n".join(f"• {worker.label}" for worker in missing)
            if messagebox.askyesno(
                "Missing Tunnels",
                "These tunnels are not configured yet:\n\n"
                + labels
                + "\n\nOpen the beginner help before provisioning?",
                parent=self,
            ):
                self.show_help()
        self._refresh_top_status()
        if not missing and self.credentials.has(RUNTIME_KEY_NAME):
            self.after(300, self.start_all)

    def create_missing(self) -> None:
        if self.busy:
            return
        missing = [worker for worker in WORKERS if not self.config_store.tunnel_id(worker.key)]
        if not missing:
            messagebox.showinfo("Nothing missing", "All three Tunnel IDs are already configured.", parent=self)
            return
        admin_key = self._admin_key()
        if not admin_key:
            self.edit_key(ADMIN_KEY_NAME)
            admin_key = self._admin_key()
            if not admin_key:
                return
        if not self.config_store.workspace_ids():
            self.edit_scope()
            if not self.config_store.workspace_ids():
                messagebox.showerror(
                    "ChatGPT workspace required",
                    "Automatic tunnel creation for ChatGPT requires the target ChatGPT Workspace ID. Open Beginner Help for the required order and setup links.",
                    parent=self,
                )
                return
        if not TUNNEL_CLIENT.exists():
            messagebox.showerror("Setup required", "tunnel-client.exe is not installed yet. Run Setup-All.cmd first.", parent=self)
            return

        self.busy = True
        self.create_button.configure(state="disabled")
        self.global_status.configure(text="Creating missing tunnels...")

        def worker_thread() -> None:
            try:
                created = create_missing_tunnels(self.config_store, admin_key)
                result = (True, created)
            except Exception as exc:
                result = (False, exc)
            self.after(0, lambda: self._create_finished(result))

        threading.Thread(target=worker_thread, daemon=True).start()

    def _create_finished(self, result) -> None:
        self.busy = False
        self.create_button.configure(state="normal")
        ok, value = result
        if ok:
            created = value
            self.global_status.configure(text="Tunnel creation complete. New tunnels may take a short time to become active.")
            messagebox.showinfo(
                "Tunnels created",
                "Created: " + ", ".join(WORKER_BY_KEY[key].label for key in created) + "\n\nYou can now start the configured terminals.",
                parent=self,
            )
        else:
            self.global_status.configure(text="Tunnel creation failed.")
            messagebox.showerror("Tunnel creation failed", str(value), parent=self)
        self._refresh_top_status()
        if ok and all(self.config_store.tunnel_id(worker.key) for worker in WORKERS):
            self.after(300, self.start_all)

    def start_worker(self, worker_key: str) -> None:
        worker = WORKER_BY_KEY[worker_key]
        runtime_key = self._runtime_key()
        if not runtime_key:
            self.edit_key(RUNTIME_KEY_NAME)
            runtime_key = self._runtime_key()
        if not runtime_key:
            return
        tunnel_id = self.config_store.tunnel_id(worker_key)
        if not tunnel_id:
            messagebox.showerror("Tunnel missing", f"{worker.label} has no Tunnel ID yet. Use Set Tunnel ID or Create Missing Tunnels.", parent=self)
            return
        try:
            write_profile(worker, tunnel_id)
            self.processes.start(worker, runtime_key)
        except Exception as exc:
            messagebox.showerror(f"Could not start {worker.label}", str(exc), parent=self)

    def restart_worker(self, worker_key: str) -> None:
        worker = WORKER_BY_KEY[worker_key]
        runtime_key = self._runtime_key()
        if not runtime_key:
            self.edit_key(RUNTIME_KEY_NAME)
            runtime_key = self._runtime_key()
        if not runtime_key:
            return
        tunnel_id = self.config_store.tunnel_id(worker_key)
        if not tunnel_id:
            messagebox.showerror("Tunnel missing", f"{worker.label} has no Tunnel ID.", parent=self)
            return
        try:
            write_profile(worker, tunnel_id)
            self.processes.restart(worker, runtime_key)
        except Exception as exc:
            messagebox.showerror(f"Could not restart {worker.label}", str(exc), parent=self)

    def stop_worker(self, worker_key: str) -> None:
        try:
            self.processes.stop(worker_key)
        except Exception as exc:
            messagebox.showerror("Stop failed", str(exc), parent=self)

    def show_terminal(self, worker_key: str) -> None:
        try:
            self.processes.show_terminal(WORKER_BY_KEY[worker_key])
        except Exception as exc:
            messagebox.showerror("Could not open terminal", str(exc), parent=self)

    def start_all(self) -> None:
        runtime_key = self._runtime_key()
        if not runtime_key:
            self.edit_key(RUNTIME_KEY_NAME)
            runtime_key = self._runtime_key()
        if not runtime_key:
            return
        tunnel_ids = {worker.key: self.config_store.tunnel_id(worker.key) for worker in WORKERS}
        if not any(tunnel_ids.values()):
            messagebox.showerror("No tunnels", "No Tunnel IDs are configured yet.", parent=self)
            return
        try:
            ensure_profiles(self.config_store)
            self.processes.start_all(runtime_key, tunnel_ids)
        except Exception as exc:
            messagebox.showerror("Could not start bridge", str(exc), parent=self)

    def stop_all(self) -> None:
        try:
            self.processes.stop_all()
        except Exception as exc:
            messagebox.showerror("Stop failed", str(exc), parent=self)

    def clear_logs(self) -> None:
        if not messagebox.askyesno(
            "Clear activity logs",
            "Clear all task/activity history and tunnel output logs for all three workers?\n\nConfiguration, API keys, Tunnel IDs, and profiles will be preserved.",
            parent=self,
        ):
            return
        try:
            clear_activity_logs()
            clear_tunnel_logs()
            for panel in self.panels.values():
                panel.clear_view()
            self.global_status.configure(text="Activity and tunnel logs cleared; configuration preserved.")
        except Exception as exc:
            messagebox.showerror("Clear logs failed", str(exc), parent=self)

    def _refresh_top_status(self) -> None:
        runtime_saved = self.credentials.has(RUNTIME_KEY_NAME)
        admin_saved = self.credentials.has(ADMIN_KEY_NAME)
        self.runtime_status.configure(text=f"Runtime API Key: {'SAVED' if runtime_saved else 'MISSING'}")
        self.admin_status.configure(
            text=f"Admin API Key: {'SAVED' if admin_saved else 'NOT SAVED'} {'(tunnel management ready)' if admin_saved else '(only needed to create tunnels)'}"
        )
        orgs = self.config_store.organization_ids()
        workspaces = self.config_store.workspace_ids()
        if orgs or workspaces:
            self.scope_status.configure(text=f"Tunnel scope: {len(orgs)} org ID(s), {len(workspaces)} workspace ID(s)")
        else:
            self.scope_status.configure(text="Tunnel scope: NOT SET")

    def _poll(self) -> None:
        try:
            self._poll_tick += 1
            self._refresh_top_status()
            runtime_present = self.credentials.has(RUNTIME_KEY_NAME)
            health_due = self._poll_tick % 4 == 1 or not self._connection_cache
            running_count = 0
            ready_count = 0
            for worker in WORKERS:
                running = self.processes.is_running(worker.key)
                running_count += int(running)
                tunnel_id = self.config_store.tunnel_id(worker.key)
                if health_due:
                    tunnel_status = probe_health(worker, running, runtime_present, tunnel_id)
                    self._connection_cache[worker.key] = (
                        tunnel_status.state, tunnel_status.detail, tunnel_status.ready
                    )
                state, detail, ready = self._connection_cache.get(
                    worker.key, ("gray", "Checking...", False)
                )
                ready_count += int(ready)
                data = snapshot(worker.key)
                self.panels[worker.key].update_status(state, detail, tunnel_id, data)
            if running_count:
                self.global_status.configure(text=f"Tunnels running: {running_count}/3 · Ready: {ready_count}/3")
            elif not self.busy:
                self.global_status.configure(text="Bridge stopped")
        except Exception as exc:
            self.global_status.configure(text=f"Status refresh error: {exc}")
        finally:
            self.after(250, self._poll)

    def _on_close(self) -> None:
        self.stop_all()
        self.destroy()


def main() -> int:
    app = BridgeApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
