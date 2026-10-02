"""Speech, for the rare moment the session is blocked and you're not at the screen.

Spoken text originates in hook payloads, so it is never interpolated into a
shell command. macOS and Linux take it as an argv parameter; Windows reads it
from a file whose path travels in an environment variable. Nothing here builds
a command string out of untrusted text.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import ClassVar

_QUIET = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}

MAX_CHARS = 300
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# Text is passed as an argv parameter, so a leading dash reads as an option
# flag. ``spd-say`` and ``espeak`` are guarded by a ``--`` terminator, but
# macOS ``say`` takes none, and a rejected argument means silence.
_LEADING_DASHES_RE = re.compile(r"^-+\s*")

_PS_SPEAK = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$s.Speak([IO.File]::ReadAllText($env:DAEDALUS_SPEECH_FILE))"
)


def sanitize(text: str) -> str:
    """Collapse whitespace, drop control characters and leading dashes, cap the length.

    A dash carries no sound, so dropping it costs nothing and keeps the text
    from being mistaken for a command-line flag.
    """
    text = _CONTROL_RE.sub(" ", text)
    text = " ".join(text.split())
    text = _LEADING_DASHES_RE.sub("", text)
    return text[:MAX_CHARS]


class SapiSpeech:
    """Windows System.Speech. Built in, and a PowerShell start costs a few hundred
    milliseconds -- acceptable here, because speech only fires when you're away.
    """

    name = "sapi"

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._file: Path | None = None

    @staticmethod
    def probe() -> tuple[bool, str]:
        if sys.platform != "win32":
            return False, "not Windows"
        if not shutil.which("powershell"):
            return False, "powershell not on PATH"
        return True, "System.Speech via PowerShell"

    def say(self, text: str) -> None:
        self.stop()
        fd, name = tempfile.mkstemp(prefix="daedalus-", suffix=".txt", text=True)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(sanitize(text))
        self._file = Path(name)
        env = {**os.environ, "DAEDALUS_SPEECH_FILE": name}
        self._proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_SPEAK],
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            **_QUIET,
        )

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc and proc.poll() is None:
            proc.terminate()
        stale, self._file = self._file, None
        if stale:
            stale.unlink(missing_ok=True)


class CommandSpeech:
    """``say`` on macOS; ``spd-say`` or ``espeak`` on Linux. Text passed as argv."""

    CANDIDATES: ClassVar[dict[str, list[tuple[str, list[str]]]]] = {
        "darwin": [("say", [])],
        "linux": [("spd-say", ["--wait", "--"]), ("espeak", ["--"])],
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
            return False, f"no speech command known for {sys.platform}"
        found = cls._find()
        if not found:
            names = ", ".join(exe for exe, _ in cls.CANDIDATES[sys.platform])
            return False, f"none of {names} on PATH -- install one for speech"
        return True, found[0]

    def say(self, text: str) -> None:
        self.stop()
        self._proc = subprocess.Popen([self._exe, *self._args, sanitize(text)], **_QUIET)

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc and proc.poll() is None:
            proc.terminate()


class NullSpeech:
    """No speech available. Earcons keep working; blocked states still get a tone."""

    name = "null"

    @staticmethod
    def probe() -> tuple[bool, str]:
        return True, "no-op"

    def say(self, text: str) -> None:
        pass

    def stop(self) -> None:
        pass


def resolve() -> tuple[object, str]:
    ok, why = SapiSpeech.probe()
    if ok:
        return SapiSpeech(), why
    ok, why = CommandSpeech.probe()
    if ok:
        found = CommandSpeech._find()
        assert found is not None
        return CommandSpeech(*found), why
    return NullSpeech(), f"speech disabled ({why})"
