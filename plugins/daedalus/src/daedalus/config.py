"""User configuration and runtime state.

Two separate files, because they change for different reasons:

- ``~/.daedalus.toml``   hand-edited preferences, read-only to us
- ``~/.daedalus/state.json``  runtime state (mute, daemon token) we write

Plugin-level ``settings.json`` only honours ``agent`` and ``subagentStatusLine``,
so none of this can live there.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.10 and older
    # Reading ~/.daedalus.toml needs 3.11+. Rather than take the daemon down,
    # run on defaults: tones and speech still work, the config file is ignored.
    tomllib = None  # type: ignore[assignment]

PORT = 47113  # fixed loopback port; also serves as the singleton lock


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
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> Config:
        path = config_path()
        if tomllib is None or not path.is_file():
            return cls()
        try:
            with path.open("rb") as fh:
                raw = tomllib.load(fh)
        except (OSError, ValueError):
            # A broken config must not take the daemon down; defaults are fine.
            return cls()
        known = {f for f in cls.__dataclass_fields__ if f != "extra"}
        kwargs = {k: v for k, v in raw.items() if k in known}
        return cls(**kwargs, extra={k: v for k, v in raw.items() if k not in known})


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
