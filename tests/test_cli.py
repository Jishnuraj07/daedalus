"""``emit`` is the hot path: every hook goes through it, on every event.

Two contracts matter here. It must never fail loudly -- a hook that errors is
worse than one that stays quiet -- and it must not do work the daemon won't use.
"""

import io

import pytest
from daedalus import cli


class FakeStdin:
    def __init__(self, raw: bytes) -> None:
        self.buffer = io.BytesIO(raw)


@pytest.fixture
def sent(monkeypatch):
    """Capture what ``emit`` would put on the wire, without a daemon."""
    calls = []
    monkeypatch.setattr(cli, "send", lambda request, **kw: calls.append(request))
    return calls


def run(monkeypatch, kind, raw=b"{}"):
    monkeypatch.setattr(cli.sys, "stdin", FakeStdin(raw))
    return cli.main(["emit", kind])


class TestNeverFailsLoudly:
    """A session with a broken hook should behave as if Daedalus weren't installed."""

    @pytest.mark.parametrize(
        "raw",
        [b"{}", b"", b"   ", b"not json at all", b"[1,2,3]", b'\xef\xbb\xbf{"session_id":"s"}'],
    )
    def test_every_payload_exits_zero(self, monkeypatch, sent, raw):
        assert run(monkeypatch, "stop", raw) == 0

    def test_an_unknown_kind_still_exits_zero(self, monkeypatch, sent):
        assert run(monkeypatch, "nonsense") == 0

    def test_no_daemon_still_exits_zero(self, monkeypatch):
        """``send`` returns None when nothing is listening; that is not an error."""
        monkeypatch.setattr(cli, "send", lambda request, **kw: None)
        assert run(monkeypatch, "stop") == 0

    def test_it_prints_nothing(self, monkeypatch, sent, capsys):
        run(monkeypatch, "stop")
        assert capsys.readouterr().out == ""

    def test_a_mangled_payload_travels_as_a_reason(self, monkeypatch, sent):
        """So it shows up in the log instead of vanishing."""
        run(monkeypatch, "stop", b"not json at all")
        assert sent[0]["parse_error"]

    def test_a_bom_is_handled_rather_than_losing_every_field(self, monkeypatch, sent):
        run(monkeypatch, "stop", b'\xef\xbb\xbf{"session_id":"abc"}')
        assert sent[0]["session_id"] == "abc"
        assert not sent[0]["parse_error"]


class TestViewerIsOnlyResolvedWhenUsed:
    """Resolving the viewer costs a ``ps`` on macOS and Windows, and two tmux
    queries inside tmux. ``busy`` fires on every tool batch, so it must not pay."""

    @pytest.mark.parametrize("kind", ["flush", "busy"])
    def test_kinds_answered_before_focus_skip_it(self, monkeypatch, sent, kind):
        monkeypatch.setattr(cli, "viewer", lambda pid: pytest.fail("should not be called"))
        run(monkeypatch, kind)
        assert sent[0]["ancestors"] == []
        assert sent[0]["on_screen"] is None
        assert sent[0]["via"] is None

    @pytest.mark.parametrize("kind", ["stop", "fail", "perm", "notify"])
    def test_kinds_that_reach_a_focus_decision_resolve_it(self, monkeypatch, sent, kind):
        monkeypatch.setattr(cli, "viewer", lambda pid: cli.Viewer([11, 22]))
        run(monkeypatch, kind)
        assert sent[0]["ancestors"] == [11, 22]
        assert sent[0]["on_screen"] is None, "no multiplexer means the question doesn't arise"

    def test_a_multiplexer_verdict_reaches_the_wire(self, monkeypatch, sent):
        """The daemon cannot work this out for itself, so it has to travel."""
        monkeypatch.setattr(cli, "viewer", lambda pid: cli.Viewer([7], on_screen=False, via="tmux"))
        run(monkeypatch, "stop")
        assert sent[0]["on_screen"] is False
        assert sent[0]["via"] == "tmux"

    def test_the_cheap_set_is_exactly_what_the_daemon_answers_early(self):
        """Both are handled before ``_focus_for`` is ever reached; anything else
        in here would silently break focus detection."""
        assert sorted(cli.NO_FOCUS_NEEDED) == ["busy", "flush"]


class TestUsage:
    @pytest.mark.parametrize("args", [[], ["--help"], ["-h"], ["help"]])
    def test_help_exits_zero(self, args, capsys):
        assert cli.main(args) == 0
        assert "daedalus" in capsys.readouterr().out

    def test_an_unknown_command_is_an_error(self, capsys):
        assert cli.main(["nonsense"]) == 2

    def test_usage_names_exactly_the_kinds_the_hooks_emit(self):
        """Usage drifting from the manifest means it lies in one direction or
        the other: a kind nobody knows they can pass, or one that does nothing.
        """
        import json
        from pathlib import Path

        hooks = json.loads(
            (Path(__file__).resolve().parents[1] / "plugins/daedalus/hooks/hooks.json").read_text(
                "utf-8"
            )
        )["hooks"]
        emitted = {
            hook["command"].rsplit(" ", 1)[-1]
            for entries in hooks.values()
            for entry in entries
            for hook in entry["hooks"]
        }
        line = next(ln for ln in cli.USAGE.splitlines() if "kinds:" in ln)
        listed = set(line.split("kinds:")[1].split())
        assert listed == emitted
