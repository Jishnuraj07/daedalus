"""Earcon playback. One sound at a time, interruptible, never blocking.

Every backend is built on something already present on the platform, so the
plugin installs with no dependencies at all.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

# Subprocess output is always discarded. The daemon runs as a Claude Code
# monitor, and anything a monitor prints reaches Claude as a notification, so a
# stray byte on stdout would quietly pollute every session's context.
_QUIET = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}


class WinsoundAudio:
    """``winsound`` is in the standard library and already single-slot:
    a new async play replaces the previous one, which is the semantics we want.
    """

    name = "winsound"

    def __init__(self) -> None:
        import winsound

        self._winsound = winsound

    @staticmethod
    def probe() -> tuple[bool, str]:
        if sys.platform != "win32":
            return False, "not Windows"
        try:
            import winsound  # noqa: F401
        except ImportError:
            return False, "winsound unavailable"
        return True, "stdlib winsound"

    def play(self, path: Path) -> None:
        ws = self._winsound
        ws.PlaySound(str(path), ws.SND_FILENAME | ws.SND_ASYNC | ws.SND_NODEFAULT)

    def stop(self) -> None:
        self._winsound.PlaySound(None, self._winsound.SND_PURGE)


class CommandAudio:
    """A player invoked as a subprocess: ``afplay`` on macOS, ``paplay``/``aplay`` on Linux."""

    CANDIDATES: ClassVar[dict[str, list[tuple[str, list[str]]]]] = {
        "darwin": [("afplay", [])],
        "linux": [("paplay", []), ("aplay", ["-q"])],
    }

    def __init__(self, exe: str, args: list[str]) -> None:
        self.name = exe
        self._exe = exe
        self._args = args
        self._proc: subprocess.Popen | None = None

    @classmethod
    def _find(cls) -> tuple[str, list[str]] | None:
        for exe, args in cls.CANDIDATES.get(sys.platform, []):
            if shutil.which(exe):
                return exe, args
        return None

    @classmethod
    def probe(cls) -> tuple[bool, str]:
        if sys.platform not in cls.CANDIDATES:
            return False, f"no player known for {sys.platform}"
        found = cls._find()
        if not found:
            names = ", ".join(exe for exe, _ in cls.CANDIDATES[sys.platform])
            return False, f"none of {names} on PATH"
        return True, found[0]

    def play(self, path: Path) -> None:
        self.stop()
        self._proc = subprocess.Popen([self._exe, *self._args, str(path)], **_QUIET)

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc and proc.poll() is None:
            proc.terminate()


class NullAudio:
    """No audio available. Everything still runs; nothing is heard."""

    name = "null"

    @staticmethod
    def probe() -> tuple[bool, str]:
        return True, "no-op"

    def play(self, path: Path) -> None:
        pass

    def stop(self) -> None:
        pass


def resolve() -> tuple[object, str]:
    """Pick the best available backend, with a reason for ``/daedalus:doctor``."""
    ok, why = WinsoundAudio.probe()
    if ok:
        return WinsoundAudio(), why
    ok, why = CommandAudio.probe()
    if ok:
        found = CommandAudio._find()
        assert found is not None
        return CommandAudio(*found), why
    return NullAudio(), f"falling back to silence ({why})"
