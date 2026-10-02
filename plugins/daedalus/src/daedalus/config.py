"""User configuration and runtime state.

Two separate files, because they change for different reasons:

- ``~/.daedalus.toml``   hand-edited preferences, read-only to us
- ``~/.daedalus/state.json``  runtime state (mute, daemon token) we write

Plugin-level ``settings.json`` only honours ``agent`` and ``subagentStatusLine``,
so none of this can live there.
"""

from __future__ import annotations

import json
import math
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.10 and older
    # Reading ~/.daedalus.toml needs 3.11+. Rather than take the daemon down,
    # run on defaults: tones and speech still work, the config file is ignored.
    tomllib = None  # type: ignore[assignment]

PORT = 47113  # fixed loopback port; also serves as the singleton lock


# --------------------------------------------------------------------------
# Field validation
#
# ``~/.daedalus.toml`` is hand-edited, so every value in it is a guess until
# checked. A seconds field holding a string used to crash the daemon on the
# next decision, and a typo'd key was swallowed in silence -- both of which
# look like broken software rather than a typo. Each value is now checked, bad
# ones fall back to the default, and the reason lands in ``Config.ignored``
# for ``/daedalus:doctor`` to print.
# --------------------------------------------------------------------------


def _seconds(value: object) -> float | None:
    """A finite, non-negative number of seconds.

    ``bool`` is rejected deliberately: it is a subclass of ``int``, and
    ``min_turn_seconds = true`` is a mistake, not a request for 1 second.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    seconds = float(value)
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return seconds


def _flag(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _pack_name(value: object) -> str | None:
    """One directory name under ``sounds/packs``, never a path.

    A name containing a separator would resolve outside the packs directory,
    where the earcons simply aren't found and every event goes quiet with
    nothing but a log line to explain it.

    Both separators are rejected on every platform, not just the local one: the
    same config file gets carried between machines, and a name that is merely
    odd on Linux escapes the directory on Windows. ``Path.name`` then catches
    what is left, such as a Windows drive prefix.
    """
    if not isinstance(value, str):
        return None
    name = value.strip()
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        return None
    if Path(name).name != name:
        return None
    return name


# field -> (checker, what a good value looks like, for the doctor report).
# A checker returns the value to use, or None to reject it -- so every checker
# must reject by type, never by falsiness: ``speak = false`` and
# ``min_turn_seconds = 0`` are both legitimate.
_CHECKS: dict[str, tuple[Callable[[object], object | None], str]] = {
    "pack": (_pack_name, "a sound pack directory name"),
    "min_turn_seconds": (_seconds, "seconds, zero or more"),
    "speak": (_flag, "true or false"),
    "escalate_after": (_seconds, "seconds, zero or more"),
    "debounce_seconds": (_seconds, "seconds, zero or more"),
}


def home() -> Path:
    return Path(os.environ.get("DAEDALUS_HOME") or Path.home())


def config_path() -> Path:
    return home() / ".daedalus.toml"


def state_dir() -> Path:
    return home() / ".daedalus"


@dataclass
class Config:
    """Defaults chosen to err quiet. A loud default gets the plugin uninstalled."""

    pack: str = "default"
    # Turns shorter than this make no sound at all: you never looked away.
    # Expect to raise this well above 3s once you've used it for a day.
    min_turn_seconds: float = 3.0
    # Master switch for speech. Earcons keep working with this off.
    speak: bool = True
    # An unanswered permission prompt repeats once after this long, then never again.
    escalate_after: float = 30.0
    # Ignore a repeat of the same event inside this window (belt and braces
    # against two hooks describing one underlying thing).
    debounce_seconds: float = 0.3
    # Anything in ~/.daedalus.toml that was not applied, mapped to why.
    # Printed by /daedalus:doctor and logged at daemon start, so a typo'd key
    # or an out-of-range value is visible instead of silently doing nothing.
    ignored: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls) -> Config:
        path = config_path()
        if tomllib is None or not path.is_file():
            return cls()
        try:
            with path.open("rb") as fh:
                raw = tomllib.load(fh)
        except (OSError, ValueError) as exc:
            # A broken config must not take the daemon down; defaults are fine.
            return cls(ignored={"(whole file)": f"unreadable ({type(exc).__name__}); using defaults"})

        kwargs: dict[str, object] = {}
        ignored: dict[str, str] = {}
        for key, value in raw.items():
            check = _CHECKS.get(key)
            if check is None:
                ignored[key] = "not a Daedalus setting"
                continue
            checker, expected = check
            checked = checker(value)
            if checked is None:
                ignored[key] = f"expected {expected}, got {value!r}"
            else:
                kwargs[key] = checked
        return cls(**kwargs, ignored=ignored)


def load_state() -> dict:
    path = state_dir() / "state.json"
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "state.json.tmp"
    tmp.write_text(json.dumps(state, indent=2), "utf-8")
    tmp.replace(d / "state.json")


def token() -> str:
    """Shared secret so only our own clients can make the machine play sounds.

    A fixed loopback port is reachable by any local process; this keeps a stray
    one from driving your speakers. Created on first use.
    """
    state = load_state()
    tok = state.get("token")
    if not tok:
        tok = secrets.token_hex(16)
        state["token"] = tok
        save_state(state)
    return tok
