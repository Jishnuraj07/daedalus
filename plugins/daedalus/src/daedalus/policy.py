"""The decision layer: silence, a tone, or speech.

One rule governs everything here:

    Make Claude Code audible exactly when it is waiting on you.
    Stay silent otherwise.

Pure functions over plain data, so the whole product is testable without a
sound card or a window manager. The daemon supplies focus and config; this
module decides and explains itself via ``Decision.reason``, which is what
``--dry-run`` and ``/daedalus:doctor`` print.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .config import Config


class Focus(Enum):
    FOCUSED = "focused"
    UNFOCUSED = "unfocused"
    UNKNOWN = "unknown"  # Wayland, headless, or a backend that failed


class Kind(Enum):
    STOP = "stop"  # turn finished; may carry a trailing question
    FAIL = "fail"  # turn ended on an API error
    PERM = "perm"  # blocked on a permission prompt
    IDLE = "idle"  # waiting for input
    FLUSH = "flush"  # user submitted a new prompt; cancel pending audio


# Kinds where the session is hard-stopped and cannot proceed without you.
# These still speak when focus can't be determined; softer kinds don't.
HARD_BLOCKED = frozenset({Kind.PERM, Kind.FAIL})

# Preemption order for the daemon's single audio slot: a "needs you" must
# never wait behind a queued "done".
PRIORITY = {
    Kind.FLUSH: 3,
    Kind.PERM: 2,
    Kind.FAIL: 2,
    Kind.IDLE: 1,
    Kind.STOP: 0,
}


@dataclass(frozen=True)
class Event:
    kind: Kind
    turn_seconds: float | None = None
    # Spoken content, when the event carries any. For STOP this is the trailing
    # question if the reply ended in one, and None otherwise.
    text: str | None = None

    @property
    def priority(self) -> int:
        return PRIORITY.get(self.kind, 0)


@dataclass(frozen=True)
class Decision:
    earcon: str | None = None
    speech: str | None = None
    flush: bool = False
    reason: str = ""

    @property
    def silent(self) -> bool:
        return self.earcon is None and self.speech is None and not self.flush


def decide(event: Event, *, focus: Focus, config: Config, muted: bool = False) -> Decision:
    """Map an event plus context onto silence, a tone, or a tone with speech.

    A spoken decision always carries its earcon too: the tone cues you to
    listen, which makes the speech land far better than speech alone.
    """
    if event.kind is Kind.FLUSH:
        # A command, not a sound. Honoured even while muted.
        return Decision(flush=True, reason="new prompt submitted")

    if muted:
        return Decision(reason="muted")

    # Rule 1 applies to completion only. A turn that ends by asking you
    # something is waiting on you no matter how fast it was.
    if event.kind is Kind.STOP and not event.text:
        if event.turn_seconds is not None and event.turn_seconds < config.min_turn_seconds:
            return Decision(
                reason=f"turn took {event.turn_seconds:.1f}s, under the "
                f"{config.min_turn_seconds:.1f}s threshold; you never looked away"
            )
        return Decision(earcon="done", reason="turn finished")

    earcon = "failed" if event.kind is Kind.FAIL else "needs_you"

    if not config.speak:
        return Decision(earcon=earcon, reason="speech disabled in config")
    if not event.text:
        return Decision(earcon=earcon, reason="nothing worth saying")

    # Rule 2: if you can see the screen, a tone is enough.
    if focus is Focus.FOCUSED:
        return Decision(earcon=earcon, reason="terminal focused; a tone is enough")

    if focus is Focus.UNKNOWN and event.kind not in HARD_BLOCKED:
        return Decision(earcon=earcon, reason="focus unknown; staying conservative")

    return Decision(earcon=earcon, speech=event.text, reason="waiting on you, and you're away")
