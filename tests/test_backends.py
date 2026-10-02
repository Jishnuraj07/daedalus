"""Backend behaviour that doesn't need the real hardware.

The resolvers are smoke-tested on the actual platform by ``tools/ci_probe.py``.
What's here is the logic around them: text sanitising, and the probe reasons,
which ``/daedalus:doctor`` prints and users paste into bug reports.
"""

import pytest
from daedalus.backends import focus, speech
from daedalus.backends.speech import MAX_CHARS, sanitize


class TestSanitize:
    def test_whitespace_is_collapsed(self):
        assert sanitize("Should  I\n\tpush?") == "Should I push?"

    def test_control_characters_go(self):
        assert sanitize("push\x00\x07 it?") == "push it?"

    def test_length_is_capped(self):
        assert len(sanitize("word " * 500)) <= MAX_CHARS

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("-- or should I wait?", "or should I wait?"),
            ("-v hello", "v hello"),
            ("  --force it?", "force it?"),
            ("a - b", "a - b"),  # only a *leading* dash is a problem
            ("done - finally?", "done - finally?"),
        ],
    )
    def test_leading_dashes_are_dropped(self, text, expected):
        """Text is passed as an argv parameter.

        macOS ``say`` carries no ``--`` terminator, so a leading dash was read
        as an option flag and the whole utterance was silently dropped.
        """
        assert sanitize(text) == expected

    def test_an_ordinary_question_is_left_alone(self):
        assert sanitize("Should I push?") == "Should I push?"

    def test_all_dashes_does_not_crash(self):
        assert sanitize("---") == ""


class TestSpeechArgv:
    def test_no_candidate_can_be_fed_a_leading_dash(self):
        """Whatever ``sanitize`` returns must be safe as the final argv word."""
        for candidates in speech.CommandSpeech.CANDIDATES.values():
            for exe, args in candidates:
                word = sanitize("--rate 500 should I push?")
                assert not word.startswith("-"), f"{exe} {args} would see an option flag"


class TestX11Probe:
    def test_wayland_is_reported_as_wayland(self, monkeypatch):
        monkeypatch.setattr(focus.sys, "platform", "linux")
        monkeypatch.setattr(focus.shutil, "which", lambda _: "/usr/bin/xprop")
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        monkeypatch.setenv("DISPLAY", ":0")  # XWayland sets this too
        ok, why = focus.X11Focus.probe()
        assert ok is False
        assert "Wayland" in why, "the Wayland reason is the useful one here"

    def test_no_display_is_reported_rather_than_claimed_to_work(self, monkeypatch):
        """xprop installed but no display: focus can never resolve.

        The probe used to report success, so ``doctor`` claimed focus detection
        was working while every event came back unknown.
        """
        monkeypatch.setattr(focus.sys, "platform", "linux")
        monkeypatch.setattr(focus.shutil, "which", lambda _: "/usr/bin/xprop")
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.delenv("DISPLAY", raising=False)
        ok, why = focus.X11Focus.probe()
        assert ok is False
        assert "DISPLAY" in why

    def test_an_x11_display_resolves(self, monkeypatch):
        monkeypatch.setattr(focus.sys, "platform", "linux")
        monkeypatch.setattr(focus.shutil, "which", lambda _: "/usr/bin/xprop")
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.setenv("DISPLAY", ":0")
        assert focus.X11Focus.probe() == (True, "_NET_WM_PID via xprop")

    def test_a_failed_probe_still_yields_a_working_backend(self, monkeypatch):
        """Nothing hard-fails when a backend is missing; policy goes conservative."""
        monkeypatch.setattr(focus.sys, "platform", "linux")
        monkeypatch.setattr(focus.shutil, "which", lambda _: None)
        backend, why = focus.resolve()
        assert isinstance(backend, focus.NullFocus)
        assert "conservative" in why
        assert focus.classify(backend, [1, 2, 3]) is focus.Focus.UNKNOWN
