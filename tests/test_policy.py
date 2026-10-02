"""The policy table. This is where the product lives, so it's tested hardest."""

import pytest
from daedalus.config import Config
from daedalus.policy import PRIORITY, Event, Focus, Kind, decide

FOCUSED, UNFOCUSED, UNKNOWN = Focus.FOCUSED, Focus.UNFOCUSED, Focus.UNKNOWN

QUESTION = "Should I also update the tests?"

# (label, event, focus, expected earcon, expected speech)
CASES = [
    # Rule 1: completion under the threshold makes no sound, whatever the focus.
    ("short turn, focused", Event(Kind.STOP, 0.5), FOCUSED, None, False),
    ("short turn, away", Event(Kind.STOP, 0.5), UNFOCUSED, None, False),
    # Completion over the threshold is a tone, never speech.
    ("long turn, focused", Event(Kind.STOP, 10.0), FOCUSED, "done", False),
    ("long turn, away", Event(Kind.STOP, 10.0), UNFOCUSED, "done", False),
    # Unknown duration must not be mistaken for a short turn.
    ("unknown duration", Event(Kind.STOP, None), UNKNOWN, "done", False),
    # A turn that ends by asking you something is waiting on you, however fast.
    ("fast question, away", Event(Kind.STOP, 0.5, QUESTION), UNFOCUSED, "needs_you", True),
    # Rule 2: if you can see the screen, a tone is enough.
    ("question, focused", Event(Kind.STOP, 10.0, QUESTION), FOCUSED, "needs_you", False),
    # Soft-blocked with unknown focus stays conservative.
    ("question, focus unknown", Event(Kind.STOP, 10.0, QUESTION), UNKNOWN, "needs_you", False),
    # Hard-blocked speaks even when focus can't be determined.
    ("permission, focus unknown", Event(Kind.PERM, None, "run npm install?"), UNKNOWN, "needs_you", True),
    ("permission, away", Event(Kind.PERM, None, "run npm install?"), UNFOCUSED, "needs_you", True),
    ("permission, focused", Event(Kind.PERM, None, "run npm install?"), FOCUSED, "needs_you", False),
    ("failure, focus unknown", Event(Kind.FAIL, None, "rate limited"), UNKNOWN, "failed", True),
    ("failure, focused", Event(Kind.FAIL, None, "rate limited"), FOCUSED, "failed", False),
    # Nothing worth saying falls back to the tone.
    ("idle, away", Event(Kind.IDLE, None, None), UNFOCUSED, "needs_you", False),
]


@pytest.mark.parametrize("label,event,focus,earcon,speaks", CASES, ids=[c[0] for c in CASES])
def test_policy_table(label, event, focus, earcon, speaks):
    decision = decide(event, focus=focus, config=Config(), muted=False)
    assert decision.earcon == earcon, f"{label}: {decision.reason}"
    assert bool(decision.speech) is speaks, f"{label}: {decision.reason}"


@pytest.mark.parametrize("label,event,focus,earcon,speaks", CASES, ids=[c[0] for c in CASES])
def test_muted_is_always_silent(label, event, focus, earcon, speaks):
    decision = decide(event, focus=focus, config=Config(), muted=True)
    assert decision.silent, f"{label} should be silent when muted"


def test_flush_is_honoured_even_when_muted():
    """Mute silences output; it must not strand a pending sound."""
    decision = decide(Event(Kind.FLUSH), focus=Focus.FOCUSED, config=Config(), muted=True)
    assert decision.flush
    assert decision.earcon is None and decision.speech is None


def test_speak_disabled_keeps_earcons():
    config = Config(speak=False)
    decision = decide(
        Event(Kind.PERM, None, "run npm install?"), focus=Focus.UNFOCUSED, config=config, muted=False
    )
    assert decision.earcon == "needs_you"
    assert decision.speech is None


def test_threshold_is_configurable():
    event = Event(Kind.STOP, 5.0)
    assert decide(event, focus=FOCUSED, config=Config(min_turn_seconds=3.0), muted=False).earcon == "done"
    assert decide(event, focus=FOCUSED, config=Config(min_turn_seconds=10.0), muted=False).silent


def test_needs_you_outranks_done():
    """A blocked state must never wait behind a queued completion tone."""
    assert PRIORITY[Kind.PERM] > PRIORITY[Kind.STOP]
    assert PRIORITY[Kind.FAIL] > PRIORITY[Kind.STOP]
    assert PRIORITY[Kind.IDLE] > PRIORITY[Kind.STOP]
    assert Event(Kind.PERM).priority > Event(Kind.STOP).priority


class TestSpokenLabel:
    """A label introduces the question; it never replaces or reorders it."""

    def test_no_label_says_exactly_the_text(self):
        assert Event(Kind.PERM, None, "run npm install?").spoken == "run npm install?"

    def test_a_label_introduces_the_text(self):
        event = Event(Kind.PERM, None, "run npm install?", label="daedalus")
        assert event.spoken == "daedalus, run npm install?"

    def test_the_comma_is_there_for_the_pause(self):
        """Every backend reads it as a pause, which is what keeps the two apart."""
        assert ", " in Event(Kind.PERM, None, "go?", label="web api").spoken

    def test_a_label_cannot_conjure_speech_from_nothing(self):
        """IDLE carries no text, so there is nothing to introduce."""
        assert Event(Kind.IDLE, None, None, label="daedalus").spoken is None

    def test_the_label_reaches_the_decision(self):
        decision = decide(
            Event(Kind.PERM, None, "run npm install?", label="daedalus"),
            focus=UNFOCUSED,
            config=Config(),
            muted=False,
        )
        assert decision.speech == "daedalus, run npm install?"

    def test_a_focused_terminal_still_never_speaks(self):
        decision = decide(
            Event(Kind.PERM, None, "run npm install?", label="daedalus"),
            focus=FOCUSED,
            config=Config(),
            muted=False,
        )
        assert decision.speech is None


def test_every_decision_explains_itself():
    """``reason`` feeds --dry-run and the log, so it is never allowed to be empty."""
    for _, event, focus, _, _ in CASES:
        assert decide(event, focus=focus, config=Config(), muted=False).reason
