"""Daemon behaviour: timing, preemption, escalation, the singleton, and silence."""

import logging
import time

import pytest
from daedalus.backends import Backends
from daedalus.backends.fake import FakeAudio, FakeFocus, FakeSpeech
from daedalus.config import Config, load_state
from daedalus.speakd import Daemon, Handler, Server, setup_logging

SESSION = "s1"
CHAIN = [100, 200, 300]  # pretend process ancestry for the session
QUESTION = {"last_assistant_message": "Updated it. Shall I push?"}


def make_daemon(config: Config | None = None, foreground_pid: int | None = None) -> Daemon:
    backends = Backends(
        FakeAudio(), "fake", FakeSpeech(), "fake", FakeFocus(foreground_pid), "fake"
    )
    return Daemon(config or Config(), backends)


def emit(daemon: Daemon, kind: str, payload: dict | None = None, session: str = SESSION) -> str:
    return daemon.handle_emit(kind, session, CHAIN, payload or {})


class TestTurnTiming:
    def test_short_turn_is_silent(self):
        daemon = make_daemon(foreground_pid=200)
        emit(daemon, "flush")
        emit(daemon, "stop", {"last_assistant_message": "Done."})
        assert daemon.backends.audio.played == []

    def test_long_turn_plays_done(self):
        daemon = make_daemon(foreground_pid=200)
        emit(daemon, "flush")
        daemon._turn_started[SESSION] = time.monotonic() - 30
        emit(daemon, "stop", {"last_assistant_message": "Done."})
        assert daemon.backends.audio.played == ["done"]

    def test_unknown_duration_still_sounds(self):
        """The daemon can start mid-turn; that must not swallow the event."""
        daemon = make_daemon(foreground_pid=200)
        emit(daemon, "stop", {"last_assistant_message": "Done."})
        assert daemon.backends.audio.played == ["done"]

    def test_flush_cancels_pending_audio(self):
        daemon = make_daemon(foreground_pid=200)
        emit(daemon, "stop", {"last_assistant_message": "Done."})
        emit(daemon, "flush")
        assert daemon.backends.audio.stops >= 1


class TestFocus:
    def test_focused_terminal_never_speaks(self):
        daemon = make_daemon(foreground_pid=200)  # 200 is in CHAIN
        emit(daemon, "stop", QUESTION)
        assert daemon.backends.audio.played == ["needs_you"]
        assert daemon.backends.speech.said == []

    def test_away_speaks(self):
        daemon = make_daemon(foreground_pid=999)  # not in CHAIN
        emit(daemon, "stop", QUESTION)
        assert daemon.backends.audio.played == ["needs_you"]
        assert daemon.backends.speech.said == ["Shall I push?"]

    def test_unknown_focus_stays_conservative_for_soft_events(self):
        daemon = make_daemon(foreground_pid=None)
        emit(daemon, "stop", QUESTION)
        assert daemon.backends.speech.said == []

    def test_unknown_focus_still_speaks_hard_blocks(self):
        daemon = make_daemon(foreground_pid=None)
        emit(daemon, "perm", {"tool_name": "Bash", "tool_input": {"command": "npm install"}})
        assert daemon.backends.speech.said == ["run npm install?"]

    def test_ancestry_is_cached_per_session(self):
        daemon = make_daemon(foreground_pid=200)
        emit(daemon, "stop", {"last_assistant_message": "a"})
        # A later event for the same session keeps the first chain, because the
        # terminal and Claude Code PIDs don't change while the session runs.
        daemon.handle_emit("stop", SESSION, [777], {"last_assistant_message": "b"})
        assert daemon._ancestry[SESSION] == CHAIN


class TestPreemption:
    def test_needs_you_preempts_a_queued_done(self):
        daemon = make_daemon(foreground_pid=200)
        emit(daemon, "stop", {"last_assistant_message": "Done."})
        emit(daemon, "perm", {"tool_name": "Bash", "tool_input": {"command": "ls"}}, session="s2")
        assert daemon.backends.audio.played == ["done", "needs_you"]

    def test_done_does_not_interrupt_needs_you(self):
        daemon = make_daemon(foreground_pid=200)
        emit(daemon, "perm", {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        emit(daemon, "stop", {"last_assistant_message": "Done."}, session="s2")
        assert daemon.backends.audio.played == ["needs_you"]


class TestDebounce:
    def test_duplicate_within_the_window_is_dropped(self):
        daemon = make_daemon(foreground_pid=200)
        emit(daemon, "stop", {"last_assistant_message": "Done."})
        emit(daemon, "stop", {"last_assistant_message": "Done."})
        assert daemon.backends.audio.played == ["done"]

    def test_different_kinds_are_not_debounced(self):
        daemon = make_daemon(foreground_pid=200)
        emit(daemon, "stop", {"last_assistant_message": "Done."})
        emit(daemon, "fail", {"error_type": "rate_limit"})
        assert daemon.backends.audio.played == ["done", "failed"]


class TestEscalation:
    # Generous margins relative to ESCALATE: a loaded CI runner can be slow to
    # get round to a timer thread, and a flaky timing test is worse than none.
    ESCALATE = 0.15
    MARGIN = 1.0

    def test_repeats_once_then_never_again(self):
        daemon = make_daemon(Config(escalate_after=self.ESCALATE), foreground_pid=200)
        emit(daemon, "perm", {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        assert daemon.backends.audio.played == ["needs_you"]
        time.sleep(self.MARGIN)
        assert daemon.backends.audio.played == ["needs_you", "needs_you"], "should repeat once"
        time.sleep(self.MARGIN)
        assert len(daemon.backends.audio.played) == 2, "must never nag a third time"

    def test_answering_cancels_the_repeat(self):
        daemon = make_daemon(Config(escalate_after=self.ESCALATE), foreground_pid=200)
        emit(daemon, "perm", {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        emit(daemon, "flush")  # you came back and typed something
        time.sleep(self.MARGIN)
        assert daemon.backends.audio.played == ["needs_you"]

    def test_answering_by_finishing_the_turn_cancels_it_too(self):
        daemon = make_daemon(Config(escalate_after=self.ESCALATE), foreground_pid=200)
        emit(daemon, "perm", {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        emit(daemon, "stop", {"last_assistant_message": "Installed."})
        time.sleep(self.MARGIN)
        assert daemon.backends.audio.played == ["needs_you"]

    def test_muted_does_not_schedule_one(self):
        daemon = make_daemon(Config(escalate_after=self.ESCALATE), foreground_pid=200)
        daemon.muted = True
        emit(daemon, "perm", {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        time.sleep(self.MARGIN)
        assert daemon.backends.audio.played == []

    def test_muting_mid_window_cancels_the_repeat(self):
        """Rule 6: mute always works.

        A repeat scheduled before the mute used to fire regardless, so muting
        in response to the first tone still got you a second one.
        """
        daemon = make_daemon(Config(escalate_after=self.ESCALATE), foreground_pid=200)
        emit(daemon, "perm", {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        assert daemon.backends.audio.played == ["needs_you"]
        daemon.handle_command("mute", {})
        time.sleep(self.MARGIN)
        assert daemon.backends.audio.played == ["needs_you"], "mute must silence the repeat"

    def test_a_timer_already_running_still_checks_mute(self):
        """Cancelling races with a timer already past its wait, so ``fire`` re-checks."""
        daemon = make_daemon(Config(escalate_after=self.ESCALATE), foreground_pid=200)
        emit(daemon, "perm", {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        timer = daemon._escalations[SESSION]
        daemon.muted = True  # mute without going through the command, so nothing is cancelled
        timer.join(self.MARGIN)
        assert daemon.backends.audio.played == ["needs_you"]

    def test_unmuting_does_not_resurrect_a_cancelled_repeat(self):
        daemon = make_daemon(Config(escalate_after=self.ESCALATE), foreground_pid=200)
        emit(daemon, "perm", {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        daemon.handle_command("mute", {})
        daemon.handle_command("unmute", {})
        time.sleep(self.MARGIN)
        assert daemon.backends.audio.played == ["needs_you"]


class TestCommands:
    def test_mute_survives_a_restart(self):
        daemon = make_daemon()
        daemon.handle_command("mute", {})
        assert load_state()["muted"] is True
        assert make_daemon().muted is True

    def test_unmute(self):
        daemon = make_daemon()
        daemon.handle_command("mute", {})
        daemon.handle_command("unmute", {})
        assert make_daemon().muted is False

    def test_status_reports_backends(self):
        import json

        status = json.loads(make_daemon().handle_command("status", {}))
        assert status["backends"]["audio"][0] == "fake"
        assert status["muted"] is False

    def test_say_on_demand(self):
        daemon = make_daemon()
        daemon.handle_command("say", {"text": "hello there"})
        assert daemon.backends.speech.said == ["hello there"]

    def test_say_with_nothing_to_say(self):
        daemon = make_daemon()
        assert daemon.handle_command("say", {"text": "  "}) == "nothing to say"
        assert daemon.backends.speech.said == []

    def test_unknown_command(self):
        assert "unknown" in make_daemon().handle_command("nope", {})


class TestRobustness:
    def test_empty_and_malformed_payloads(self):
        daemon = make_daemon(foreground_pid=200)
        for kind in ("stop", "fail", "perm", "notify", "flush", "", "garbage"):
            emit(daemon, kind, {}, session=f"sess-{kind}")

    def test_session_maps_stay_bounded(self):
        daemon = make_daemon(foreground_pid=200)
        for i in range(200):
            emit(daemon, "flush", {}, session=f"session-{i}")
        assert len(daemon._ancestry) <= 64
        assert len(daemon._turn_started) <= 64


class TestSingleton:
    def test_second_bind_on_the_same_port_fails(self):
        """The bind *is* the lock: later sessions find the port taken and exit."""
        first = Server(("127.0.0.1", 0), Handler)
        port = first.server_address[1]
        try:
            with pytest.raises(OSError):
                Server(("127.0.0.1", port), Handler)
        finally:
            first.server_close()


class TestStdoutSilence:
    def test_logging_never_targets_a_stream(self, isolated_home):
        """A monitor's output reaches Claude as notifications.

        A StreamHandler here would quietly pollute every session's context, so
        every handler must be a file handler.
        """
        log = logging.getLogger("daedalus")
        for handler in list(log.handlers):
            log.removeHandler(handler)
        setup_logging()
        assert log.handlers, "logging should be configured"
        assert all(isinstance(h, logging.FileHandler) for h in log.handlers)
        assert log.propagate is False, "propagation would reach the root stream handler"

    def test_a_full_event_sequence_prints_nothing(self, capsys):
        daemon = make_daemon(foreground_pid=999)
        emit(daemon, "flush")
        emit(daemon, "stop", QUESTION)
        emit(daemon, "perm", {"tool_name": "Bash", "tool_input": {"command": "ls"}}, session="s2")
        emit(daemon, "fail", {"error_type": "rate_limit"}, session="s3")
        emit(daemon, "notify", {"notification_type": "idle_prompt"}, session="s4")
        assert capsys.readouterr().out == ""
