from __future__ import annotations

import base64
import ctypes
import json
import os
import tempfile
import winreg
from ctypes import wintypes
from pathlib import Path
from typing import Final

from .constants import SECRETS_PATH

CRYPTPROTECT_UI_FORBIDDEN: Final[int] = 0x1
RUNTIME_KEY_NAME: Final[str] = "runtime_api_key"
ADMIN_KEY_NAME: Final[str] = "admin_api_key"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


_crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_crypt32.CryptProtectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    wintypes.LPCWSTR,
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
]
_crypt32.CryptProtectData.restype = wintypes.BOOL
_crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    ctypes.POINTER(wintypes.LPWSTR),
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
]
_crypt32.CryptUnprotectData.restype = wintypes.BOOL
_kernel32.LocalFree.argtypes = [ctypes.c_void_p]
_kernel32.LocalFree.restype = ctypes.c_void_p

_ENTROPY = b"Rex-Desktop-Bridge/v1"


def _input_blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data)
    blob = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _protect(data: bytes) -> bytes:
    in_blob, in_buffer = _input_blob(data)
    entropy_blob, entropy_buffer = _input_blob(_ENTROPY)
    out_blob = DATA_BLOB()
    _ = (in_buffer, entropy_buffer)  # keep buffers alive through the Win32 call
    ok = _crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "Rex Desktop Bridge credential",
        ctypes.byref(entropy_blob),
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        _kernel32.LocalFree(out_blob.pbData)


def _unprotect(data: bytes) -> bytes:
    in_blob, in_buffer = _input_blob(data)
    entropy_blob, entropy_buffer = _input_blob(_ENTROPY)
    out_blob = DATA_BLOB()
    description = wintypes.LPWSTR()
    _ = (in_buffer, entropy_buffer)
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        ctypes.byref(description),
        ctypes.byref(entropy_blob),
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        if description:
            _kernel32.LocalFree(description)
        _kernel32.LocalFree(out_blob.pbData)


class CredentialStore:
    """Small Windows-user-scoped DPAPI store.

    Only encrypted ciphertext is written to disk. Plaintext is kept in memory only
    for the duration of the current process or child-process launch.
    """

    def __init__(self, path: Path = SECRETS_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return {str(k): str(v) for k, v in raw.items() if isinstance(v, str)}

    def _write(self, values: dict[str, str]) -> None:
        payload = json.dumps(values, indent=2, sort_keys=True)
        fd, temp_name = tempfile.mkstemp(prefix="secrets-", suffix=".tmp", dir=self.path.parent)
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            temp_path.write_text(payload, encoding="utf-8")
            os.replace(temp_path, self.path)
        finally:
            temp_path.unlink(missing_ok=True)

    def set(self, name: str, value: str) -> None:
        value = value.strip()
        if not value:
            raise ValueError("Credential value must not be empty.")
        values = self._read()
        values[name] = base64.b64encode(_protect(value.encode("utf-8"))).decode("ascii")
        self._write(values)

    def get(self, name: str) -> str | None:
        encoded = self._read().get(name)
        if not encoded:
            return None
        try:
            protected = base64.b64decode(encoded, validate=True)
            return _unprotect(protected).decode("utf-8")
        except Exception:
            return None

    def has(self, name: str) -> bool:
        return self.get(name) is not None

    def delete(self, name: str) -> None:
        values = self._read()
        if name in values:
            del values[name]
            self._write(values)


def read_legacy_user_environment(name: str) -> str | None:
    """Read a pre-Bridge user environment value without printing it.

    This exists only to migrate the previous recovery stack. The GUI can import the
    old value into DPAPI once; new installs never need a persistent plaintext user
    environment variable.
    """

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as key:
            value, _kind = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    value = str(value).strip()
    return value or None
