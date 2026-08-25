from __future__ import annotations

import json
import os
import re
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from .constants import CONFIG_PATH, PROFILE_ROOT, WORKERS

_TUNNEL_RE = re.compile(r"^\s*tunnel_id:\s*[\"']?(tunnel_[A-Za-z0-9]+)[\"']?\s*$", re.MULTILINE)


def _default_config() -> dict[str, Any]:
    return {
        "config_version": 1,
        "legacy_key_migration_done": False,
        "tunnels": {
            worker.key: {
                "tunnel_id": "",
                "profile": worker.profile,
                "label": worker.label,
            }
            for worker in WORKERS
        },
        "provisioning": {
            "organization_ids": [],
            "workspace_ids": [],
        },
    }


class BridgeConfig:
    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()
        changed = self._merge_defaults()
        changed = self._discover_existing_profiles() or changed
        if changed or not self.path.exists():
            self.save()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return _default_config()
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _default_config()
        return loaded if isinstance(loaded, dict) else _default_config()

    def _merge_defaults(self) -> bool:
        changed = False
        defaults = _default_config()
        for key, value in defaults.items():
            if key not in self.data:
                self.data[key] = deepcopy(value)
                changed = True
        if not isinstance(self.data.get("tunnels"), dict):
            self.data["tunnels"] = deepcopy(defaults["tunnels"])
            changed = True
        for worker in WORKERS:
            if worker.key not in self.data["tunnels"] or not isinstance(self.data["tunnels"][worker.key], dict):
                self.data["tunnels"][worker.key] = deepcopy(defaults["tunnels"][worker.key])
                changed = True
            entry = self.data["tunnels"][worker.key]
            for key, value in defaults["tunnels"][worker.key].items():
                if key not in entry:
                    entry[key] = value
                    changed = True
        if not isinstance(self.data.get("provisioning"), dict):
            self.data["provisioning"] = deepcopy(defaults["provisioning"])
            changed = True
        for key in ("organization_ids", "workspace_ids"):
            value = self.data["provisioning"].get(key)
            if not isinstance(value, list):
                self.data["provisioning"][key] = []
                changed = True
        return changed

    def _discover_existing_profiles(self) -> bool:
        """Import tunnel IDs from current or legacy profiles when config is blank.

        New Bridge profiles use rex-* names and never overwrite the older
        legacy profiles from the earlier recovery stack. On an upgrading machine we can
        still reuse those same OpenAI tunnel IDs without changing the old profiles.
        """

        changed = False
        for worker in WORKERS:
            entry = self.data["tunnels"][worker.key]
            if str(entry.get("tunnel_id", "")).strip():
                continue
            for profile_name in (worker.profile, worker.legacy_profile):
                profile_path = PROFILE_ROOT / f"{profile_name}.yaml"
                if not profile_path.exists():
                    continue
                try:
                    text = profile_path.read_text(encoding="utf-8")
                except OSError:
                    continue
                match = _TUNNEL_RE.search(text)
                if match:
                    entry["tunnel_id"] = match.group(1)
                    changed = True
                    break
        return changed

    def save(self) -> None:
        payload = json.dumps(self.data, indent=2, sort_keys=True)
        fd, temp_name = tempfile.mkstemp(prefix="config-", suffix=".tmp", dir=self.path.parent)
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            temp_path.write_text(payload, encoding="utf-8")
            os.replace(temp_path, self.path)
        finally:
            temp_path.unlink(missing_ok=True)

    def tunnel_id(self, worker_key: str) -> str:
        return str(self.data["tunnels"][worker_key].get("tunnel_id", "")).strip()

    def set_tunnel_id(self, worker_key: str, tunnel_id: str) -> None:
        tunnel_id = tunnel_id.strip()
        if tunnel_id and not re.fullmatch(r"tunnel_[A-Za-z0-9]+", tunnel_id):
            raise ValueError("Tunnel ID must look like tunnel_... .")
        self.data["tunnels"][worker_key]["tunnel_id"] = tunnel_id
        self.save()

    def organization_ids(self) -> list[str]:
        return [str(v).strip() for v in self.data["provisioning"].get("organization_ids", []) if str(v).strip()]

    def workspace_ids(self) -> list[str]:
        return [str(v).strip() for v in self.data["provisioning"].get("workspace_ids", []) if str(v).strip()]

    def set_scopes(self, organization_ids: list[str], workspace_ids: list[str]) -> None:
        self.data["provisioning"]["organization_ids"] = [value.strip() for value in organization_ids if value.strip()]
        self.data["provisioning"]["workspace_ids"] = [value.strip() for value in workspace_ids if value.strip()]
        self.save()

    @property
    def legacy_key_migration_done(self) -> bool:
        return bool(self.data.get("legacy_key_migration_done", False))

    def mark_legacy_key_migration_done(self) -> None:
        self.data["legacy_key_migration_done"] = True
        self.save()
