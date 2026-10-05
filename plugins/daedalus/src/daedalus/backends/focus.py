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
from dataclasses import dataclass, field
from pathlib import Path

from ..policy import Focus

# Capture stdout, discard stderr, give the child no stdin.
#
# Written out rather than using subprocess's capture-output shortcut, because
# that shortcut sets stderr itself and refuses to be combined with a stderr of
# our own -- it raises ValueError. Every reader below catches ValueError, and
# legitimately so, since it also means "that wasn't a number". So the misuse was
# swallowed: focus came back unknown every single time, on macOS and X11 alike,
# while probe() went on reporting that the backend had resolved.
_READ = {"stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
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
            ["ps", "-eo", "pid=,ppid="], text=True, timeout=_TIMEOUT, **_READ
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
# Multiplexers
#
# Inside tmux the walk above answers the wrong question. tmux starts its
# "server as a daemon", so a pane's processes descend from that server and not
# from the terminal emulator -- the emulator is never an ancestor, the
# foreground PID therefore never matches, and Daedalus concludes you are always
# away. That is the worst direction to be wrong in: it speaks over your
# shoulder while you are watching the screen.
#
# tmux can answer both halves, and more precisely than a bare terminal can:
#
#   - whose window to check. "PID of client process" is the tmux *client*, and
#     that one really is a child of the terminal emulator.
#   - whether this session is on screen at all. A pane in a background window,
#     behind another pane, or in a detached session cannot be seen however
#     focused the terminal is -- something the plain path cannot know.
#
# Only tmux is handled. GNU screen exposes nothing equivalent, and guessing
# would reintroduce the bug this fixes.
# --------------------------------------------------------------------------

# session_name goes last on purpose: a session name may contain a comma.
TMUX_PANE_FORMAT = "#{pane_active},#{window_active},#{session_name}"


@dataclass(frozen=True)
class Viewer:
    """Whose foreground-ness decides focus, and whether this session is on screen.

    ``on_screen`` is None when nothing can say: outside a multiplexer the
    question doesn't arise and the window check decides alone. ``via`` names the
    multiplexer that answered, which also tells the daemon not to cache any of
    this -- detaching and reattaching moves the client, and which pane is on
    screen changes constantly.
    """

    ancestors: list[int] = field(default_factory=list)
    on_screen: bool | None = None
    via: str | None = None


def _tmux(*args: str) -> str | None:
    """Run a tmux query, or None if tmux can't answer."""
    if not shutil.which("tmux"):
        return None
    try:
        done = subprocess.run(["tmux", *args], text=True, timeout=_TIMEOUT, **_READ)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _tmux_viewer(pane: str) -> Viewer | None:
    """Ask tmux where this pane is and who, if anyone, is looking at it."""
    line = _tmux("display-message", "-p", "-t", pane, TMUX_PANE_FORMAT)
    if not line or not line.strip():
        return None
    fields = line.strip().split(",")
    if len(fields) < 3:
        return None
    pane_active, window_active = fields[0], fields[1]
    session = ",".join(fields[2:])  # rejoined: the name may contain commas
    if not session:
        # tmux answered but told us nothing usable. Better unknown than a
        # verdict we can't support.
        return None

    if pane_active != "1" or window_active != "1":
        # A verdict, not a guess: this pane is not the one on screen, so you
        # cannot be looking at it whatever the window manager reports.
        return Viewer(on_screen=False, via="tmux")

    chain: list[int] = []
    for raw in (_tmux("list-clients", "-t", session, "-F", "#{client_pid}") or "").split():
        try:
            client = int(raw)
        except ValueError:
            continue
        for pid in ancestors(client):
            if pid not in chain:
                chain.append(pid)
    if not chain:
        # Nothing attached. The session is running with nobody watching it.
        return Viewer(on_screen=False, via="tmux")
    return Viewer(chain, on_screen=True, via="tmux")


def viewer(pid: int) -> Viewer:
    """Ask the focus question of whatever is actually displaying the session."""
    pane = os.environ.get("TMUX_PANE")
    if os.environ.get("TMUX") and pane:
        answer = _tmux_viewer(pane)
        if answer is not None:
            return answer
        # tmux is in the environment but did not answer. Falling through to the
        # plain walk would report you away for the entire session, so say
        # nothing instead of something wrong.
        return Viewer(via="tmux")
    return Viewer(ancestors(pid))


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
                text=True,
                timeout=_TIMEOUT,
                **_READ,
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
        if not os.environ.get("DISPLAY"):
            # Checked last: XWayland sets DISPLAY too, and the Wayland reason
            # above is the more useful one to report.
            return False, "DISPLAY not set -- xprop has no display to read; usual over SSH"
        return True, "_NET_WM_PID via xprop"

    @staticmethod
    def foreground_pid() -> int | None:
        try:
            root = subprocess.run(
                ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
                text=True,
                timeout=_TIMEOUT,
                **_READ,
            ).stdout
            window = root.strip().split()[-1]
            if not window.startswith("0x"):
                return None
            out = subprocess.run(
                ["xprop", "-id", window, "_NET_WM_PID"],
                text=True,
                timeout=_TIMEOUT,
                **_READ,
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
