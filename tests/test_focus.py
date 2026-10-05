"""Focus resolution: the window check, and asking tmux instead when inside it.

Two bugs are pinned here. Both made Daedalus speak at the wrong time, which is
the one failure that gets it uninstalled.
"""

import subprocess

import pytest
from daedalus.backends import focus
from daedalus.backends.focus import Focus, MacFocus, Viewer, X11Focus, classify, viewer


@pytest.fixture
def fake_run(monkeypatch):
    """Stand in for the real tools, while exercising the real argument handling.

    The calls are recorded, so a test can assert on the command line as well as
    the result -- which is where the first of these two bugs lived.
    """
    calls = []
    real = subprocess.run

    def run(cmd, **kwargs):
        calls.append(list(cmd))
        text = replies.get(cmd[0], "")
        if cmd[0] == "tmux":
            text = replies.get(f"tmux {cmd[1]}", "")
        elif cmd[0] == "xprop":
            text = replies["xprop -id"] if "-id" in cmd else replies["xprop -root"]
        return real(["printf", "%s", text], **kwargs)

    replies: dict[str, str] = {}
    monkeypatch.setattr(focus.subprocess, "run", run)
    monkeypatch.setattr(focus.shutil, "which", lambda _: "/usr/bin/tool")
    run.calls = calls
    run.replies = replies
    return run


class TestTheWindowCheckActuallyRuns:
    """It never did. The readers combined subprocess's capture-output shortcut
    with a stderr of their own, which raises ValueError -- and they all catch
    ValueError, because it also means "that wasn't a number". So focus came back
    unknown every single time while probe() reported the backend had resolved.
    """

    def test_macos_reads_the_frontmost_pid(self, fake_run, monkeypatch):
        monkeypatch.setattr(focus.sys, "platform", "darwin")
        fake_run.replies["osascript"] = "4242\n"
        assert MacFocus.foreground_pid() == 4242

    def test_x11_reads_the_active_window_pid(self, fake_run, monkeypatch):
        monkeypatch.setattr(focus.sys, "platform", "linux")
        fake_run.replies["xprop -root"] = "_NET_ACTIVE_WINDOW(WINDOW): window id # 0x5a\n"
        fake_run.replies["xprop -id"] = "_NET_WM_PID(CARDINAL) = 4242\n"
        assert X11Focus.foreground_pid() == 4242

    def test_a_resolved_pid_produces_a_real_verdict(self, fake_run, monkeypatch):
        monkeypatch.setattr(focus.sys, "platform", "darwin")
        fake_run.replies["osascript"] = "4242\n"
        assert classify(MacFocus(), [1, 4242, 3]) is Focus.FOCUSED
        assert classify(MacFocus(), [1, 2, 3]) is Focus.UNFOCUSED

    def test_garbage_output_is_still_unknown(self, fake_run, monkeypatch):
        """The ValueError the readers legitimately catch."""
        monkeypatch.setattr(focus.sys, "platform", "darwin")
        fake_run.replies["osascript"] = "not a pid\n"
        assert MacFocus.foreground_pid() is None
        assert classify(MacFocus(), [1, 2, 3]) is Focus.UNKNOWN

    def test_no_reader_uses_the_shortcut_that_caused_this(self):
        from pathlib import Path

        source = Path(focus.__file__).read_text("utf-8")
        assert "capture_output=True" not in source


class TestOutsideAMultiplexer:
    def test_the_viewer_is_this_process_tree(self, monkeypatch):
        monkeypatch.delenv("TMUX", raising=False)
        monkeypatch.delenv("TMUX_PANE", raising=False)
        monkeypatch.setattr(focus, "ancestors", lambda pid: [pid, 99])
        seen = viewer(1234)
        assert seen.ancestors == [1234, 99]
        assert seen.on_screen is None, "nothing can say, so the window check decides alone"
        assert seen.via is None


class TestInsideTmux:
    """tmux starts its server as a daemon, so a pane's processes do not descend
    from the terminal emulator. The emulator is never an ancestor, the foreground
    PID never matches, and Daedalus used to conclude you were always away --
    speaking over your shoulder while you watched the screen.
    """

    @pytest.fixture(autouse=True)
    def in_tmux(self, monkeypatch):
        monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,1234,0")
        monkeypatch.setenv("TMUX_PANE", "%3")

    def test_the_attached_client_is_what_gets_checked(self, fake_run, monkeypatch):
        """Not our own ancestry: the client is the child of the terminal."""
        monkeypatch.setattr(focus, "ancestors", lambda pid: [pid, 500, 1])
        fake_run.replies["tmux display-message"] = "1,1,main\n"
        fake_run.replies["tmux list-clients"] = "777\n"
        seen = viewer(4321)
        assert seen.ancestors == [777, 500, 1], "the client's tree, not the hook's"
        assert seen.on_screen is True
        assert seen.via == "tmux"

    def test_it_asks_tmux_the_documented_way(self, fake_run, monkeypatch):
        monkeypatch.setattr(focus, "ancestors", lambda pid: [pid])
        fake_run.replies["tmux display-message"] = "1,1,main\n"
        fake_run.replies["tmux list-clients"] = "777\n"
        viewer(1)
        assert fake_run.calls[0] == [
            "tmux", "display-message", "-p", "-t", "%3", focus.TMUX_PANE_FORMAT,
        ]
        assert fake_run.calls[1] == ["tmux", "list-clients", "-t", "main", "-F", "#{client_pid}"]

    @pytest.mark.parametrize(
        "reply,why",
        [("0,1,main", "another pane is on top"), ("1,0,main", "another window is showing")],
    )
    def test_a_hidden_pane_is_not_on_screen(self, fake_run, reply, why):
        """Something the plain path cannot know, so this is better than parity."""
        fake_run.replies["tmux display-message"] = reply + "\n"
        seen = viewer(1)
        assert seen.on_screen is False, why
        assert seen.via == "tmux"

    def test_a_detached_session_is_not_on_screen(self, fake_run):
        fake_run.replies["tmux display-message"] = "1,1,main\n"
        fake_run.replies["tmux list-clients"] = ""
        assert viewer(1).on_screen is False

    def test_several_clients_are_all_considered(self, fake_run, monkeypatch):
        """The same session can be attached from two terminals."""
        monkeypatch.setattr(focus, "ancestors", lambda pid: [pid, pid + 1])
        fake_run.replies["tmux display-message"] = "1,1,main\n"
        fake_run.replies["tmux list-clients"] = "700\n800\n"
        assert viewer(1).ancestors == [700, 701, 800, 801]

    def test_a_session_name_containing_a_comma_survives(self, fake_run, monkeypatch):
        """session_name is last in the format for exactly this reason."""
        monkeypatch.setattr(focus, "ancestors", lambda pid: [pid])
        fake_run.replies["tmux display-message"] = "1,1,work,notes\n"
        fake_run.replies["tmux list-clients"] = "777\n"
        viewer(1)
        assert fake_run.calls[1][3] == "work,notes"

    def test_tmux_not_answering_says_nothing_rather_than_something_wrong(self, monkeypatch):
        """Falling back to the plain walk would report you away all session."""
        monkeypatch.setattr(focus.shutil, "which", lambda _: None)
        seen = viewer(1)
        assert seen.ancestors == []
        assert seen.on_screen is None
        assert seen.via == "tmux", "so the daemon still knows not to cache"

    @pytest.mark.parametrize("reply", ["nonsense", "1,1,", "", "1,1"])
    def test_unusable_output_is_not_treated_as_a_verdict(self, fake_run, reply):
        fake_run.replies["tmux display-message"] = reply + "\n"
        assert viewer(1).on_screen is None, "a verdict needs an answer to rest on"


class TestViewerDefaults:
    def test_an_empty_viewer_claims_nothing(self):
        seen = Viewer()
        assert seen.ancestors == [] and seen.on_screen is None and seen.via is None
