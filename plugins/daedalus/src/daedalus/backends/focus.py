"""Is the terminal running this session the foreground window?

Two halves:

1. Which process owns the foreground window.
2. The emitting hook's process ancestry -- Claude Code, and the terminal hosting
   it, are both ancestors of any hook process.

If the foreground PID appears in that ancestry, you are looking at the session.
The daemon caches the ancestry per session, so the walk is paid once.

Everything here fails to ``UNKNOWN`` rather than raising. The policy layer
treats unknown focus conservatively, so a platform we can't read degrades to
tones instead of breaking.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..policy import Focus

_QUIET = {"stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
_TIMEOUT = 2.0

MAX_DEPTH = 12  # guards against a cycle in a malformed process table


# --------------------------------------------------------------------------
# Process ancestry
# --------------------------------------------------------------------------


def _ppid_map_windows() -> dict[int, int]:
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snapshot == -1:
        return {}
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        out: dict[int, int] = {}
        if not kernel32.Process32First(snapshot, ctypes.byref(entry)):
            return {}
        while True:
            out[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                break
        return out
    finally:
        kernel32.CloseHandle(snapshot)


def _ppid_linux(pid: int) -> int | None:
    try:
        # Field 4 of /proc/<pid>/stat. The comm field can contain spaces and
        # parentheses, so split after the final ')'.
        raw = Path(f"/proc/{pid}/stat").read_text("utf-8", errors="replace")
        return int(raw[raw.rindex(")") + 1 :].split()[1])
    except (OSError, ValueError):
        return None


def _ppid_map_posix() -> dict[int, int]:
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid=,ppid="], capture_output=True, text=True, timeout=_TIMEOUT
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    table: dict[int, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            try:
                table[int(parts[0])] = int(parts[1])
            except ValueError:
                continue
    return table


def ancestors(pid: int) -> list[int]:
    """``pid`` and every parent above it, nearest first."""
    chain = [pid]
    if sys.platform == "linux":
        current = pid
        for _ in range(MAX_DEPTH):
            parent = _ppid_linux(current)
            if not parent or parent in chain:
                break
            chain.append(parent)
            current = parent
        return chain

    table = _ppid_map_windows() if sys.platform == "win32" else _ppid_map_posix()
    current = pid
    for _ in range(MAX_DEPTH):
        parent = table.get(current)
        if not parent or parent in chain:
            break
        chain.append(parent)
        current = parent
    return chain


# --------------------------------------------------------------------------
# Foreground window owner
# --------------------------------------------------------------------------


class WindowsFocus:
    name = "win32"

    @staticmethod
    def probe() -> tuple[bool, str]:
        if sys.platform != "win32":
            return False, "not Windows"
        return True, "GetForegroundWindow via ctypes"

    @staticmethod
    def foreground_pid() -> int | None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) or None


class MacFocus:
    name = "osascript"
    _SCRIPT = 'tell application "System Events" to get unix id of first process whose frontmost is true'

    @staticmethod
    def probe() -> tuple[bool, str]:
        if sys.platform != "darwin":
            return False, "not macOS"
        if not shutil.which("osascript"):
            return False, "osascript not on PATH"
        return True, "frontmost process via osascript"

    @classmethod
    def foreground_pid(cls) -> int | None:
        try:
            out = subprocess.run(
                ["osascript", "-e", cls._SCRIPT],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                **_QUIET,
            )
            return int(out.stdout.strip())
        except (OSError, subprocess.SubprocessError, ValueError):
            return None


class X11Focus:
    name = "xprop"

    @staticmethod
    def probe() -> tuple[bool, str]:
        if sys.platform != "linux":
            return False, "not Linux"
        if not shutil.which("xprop"):
            return False, "xprop not on PATH -- install x11-utils for focus detection"
        if os_env_is_wayland():
            return False, "Wayland exposes no focus API; running conservative"
        return True, "_NET_WM_PID via xprop"

    @staticmethod
    def foreground_pid() -> int | None:
        try:
            root = subprocess.run(
                ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                **_QUIET,
            ).stdout
            window = root.strip().split()[-1]
            if not window.startswith("0x"):
                return None
            out = subprocess.run(
                ["xprop", "-id", window, "_NET_WM_PID"],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                **_QUIET,
            ).stdout
            return int(out.strip().split()[-1])
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            return None


class NullFocus:
    """Focus can't be determined here. Policy stays conservative as a result."""

    name = "null"

    @staticmethod
    def probe() -> tuple[bool, str]:
        return True, "unavailable"

    @staticmethod
    def foreground_pid() -> int | None:
        return None


def os_env_is_wayland() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY")) or os.environ.get("XDG_SESSION_TYPE") == "wayland"


_BACKENDS = {"win32": WindowsFocus, "darwin": MacFocus, "linux": X11Focus}


def resolve() -> tuple[object, str]:
    backend = _BACKENDS.get(sys.platform)
    if backend is None:
        return NullFocus(), f"conservative mode (no backend for {sys.platform})"
    ok, why = backend.probe()
    if ok:
        return backend(), why
    return NullFocus(), f"conservative mode ({why})"


def classify(backend: object, session_ancestors: list[int]) -> Focus:
    """``FOCUSED`` when the foreground window belongs to this session's process tree."""
    if isinstance(backend, NullFocus):
        return Focus.UNKNOWN
    pid = backend.foreground_pid()  # type: ignore[attr-defined]
    if pid is None:
        return Focus.UNKNOWN
    return Focus.FOCUSED if pid in session_ancestors else Focus.UNFOCUSED
