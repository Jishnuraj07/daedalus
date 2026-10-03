"""Manifest and asset checks, so a malformed plugin never lands on main.

These mirror what ``claude plugin validate`` enforces, plus the invariants that
only matter for this plugin -- every hook points at the launcher, every earcon
the policy can name actually exists, and the daemon's hooks stay asynchronous.
"""

import json
import struct
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "daedalus"
EARCONS = ("done", "needs_you", "failed")


def read_json(path: Path):
    return json.loads(path.read_text("utf-8"))


class TestPluginManifest:
    def test_required_fields(self):
        manifest = read_json(PLUGIN / ".claude-plugin" / "plugin.json")
        assert manifest["name"] == "daedalus"
        assert manifest["version"]
        assert manifest["description"]

    def test_version_matches_the_package(self):
        manifest = read_json(PLUGIN / ".claude-plugin" / "plugin.json")
        source = (PLUGIN / "src" / "daedalus" / "__init__.py").read_text("utf-8")
        assert f'__version__ = "{manifest["version"]}"' in source


class TestMarketplace:
    def test_entry_name_matches_the_manifest_name(self):
        """A mismatch here makes installs fail with a confusing 'not found'."""
        market = read_json(ROOT / ".claude-plugin" / "marketplace.json")
        manifest = read_json(PLUGIN / ".claude-plugin" / "plugin.json")
        entry = market["plugins"][0]
        assert entry["name"] == manifest["name"]

    def test_required_fields(self):
        market = read_json(ROOT / ".claude-plugin" / "marketplace.json")
        assert market["name"] and market["owner"]["name"]
        assert market["plugins"]

    def test_source_is_a_clean_relative_path(self):
        market = read_json(ROOT / ".claude-plugin" / "marketplace.json")
        source = market["plugins"][0]["source"]
        assert source.startswith("./"), "must be relative to the marketplace root"
        assert ".." not in source, "validate rejects a source containing '..'"
        assert (ROOT / source).is_dir()


EXPECTED_EVENTS = frozenset(
    {
        "Stop",
        "StopFailure",
        "PermissionRequest",
        "Notification",
        "UserPromptSubmit",
        # The only signal that a permission prompt was answered: if tools ran,
        # nothing is waiting on you.
        "PostToolBatch",
    }
)


class TestHooks:
    @property
    def hooks(self):
        return read_json(PLUGIN / "hooks" / "hooks.json")["hooks"]

    def test_every_expected_event_is_wired(self):
        assert set(self.hooks) == set(EXPECTED_EVENTS)

    def test_all_hooks_are_async(self):
        """Two reasons this matters.

        A blocking hook would stall the turn, and an async PermissionRequest
        hook has its stdout ignored -- which is what guarantees Daedalus can
        never answer a permission prompt on your behalf.
        """
        for event, entries in self.hooks.items():
            for entry in entries:
                for hook in entry["hooks"]:
                    assert hook.get("async") is True, f"{event} must be async"

    def test_hooks_invoke_the_launcher_by_plugin_relative_path(self):
        for event, entries in self.hooks.items():
            for entry in entries:
                for hook in entry["hooks"]:
                    command = hook["command"]
                    assert "${CLAUDE_PLUGIN_ROOT}" in command, f"{event} must not hardcode a path"
                    assert command.startswith('"'), f"{event} path must be quoted for spaces"
                    assert "/bin/daedalus" in command

    def test_notification_is_scoped_to_idle(self):
        """Unscoped, it would also fire for permission prompts -- which
        PermissionRequest already covers, with the real command in it.
        """
        assert self.hooks["Notification"][0]["matcher"] == "idle_prompt"

    def test_emitted_kinds_are_ones_extract_understands(self):
        """Every hook's trailing argument must be a kind extract.py handles.

        A typo here would be silent: the hook fires, the daemon shrugs, and
        nothing ever makes a sound.
        """
        from daedalus.extract import from_payload

        # Payloads that make each kind produce an event, so an unrecognised
        # kind is distinguishable from one that simply had nothing to report.
        samples = {
            "stop": {"last_assistant_message": "done"},
            "fail": {"error_type": "rate_limit"},
            "perm": {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            "notify": {"notification_type": "idle_prompt"},
            "flush": {},
            "busy": {},
        }
        for entries in self.hooks.values():
            for entry in entries:
                for hook in entry["hooks"]:
                    kind = hook["command"].rsplit(" ", 1)[-1]
                    assert kind in samples, f"hook emits unknown kind: {kind}"
                    assert from_payload(kind, samples[kind]) is not None


class TestMonitor:
    def test_starts_the_daemon(self):
        monitors = read_json(PLUGIN / "monitors" / "monitors.json")
        assert isinstance(monitors, list) and len(monitors) == 1
        monitor = monitors[0]
        assert monitor["name"] == "daedalus"
        assert "${CLAUDE_PLUGIN_ROOT}" in monitor["command"]
        assert monitor["command"].rstrip().endswith("serve")


class TestLaunchers:
    def test_both_platform_launchers_exist(self):
        """cmd.exe resolves the extensionless hook path to the .cmd via PATHEXT,
        which is what lets one hooks.json work on every platform.
        """
        assert (PLUGIN / "bin" / "daedalus").is_file()
        assert (PLUGIN / "bin" / "daedalus.cmd").is_file()

    def test_posix_launcher_has_a_shebang(self):
        first = (PLUGIN / "bin" / "daedalus").read_text("utf-8").splitlines()[0]
        assert first.startswith("#!")


class TestSoundPacks:
    @property
    def packs(self):
        return sorted(p for p in (PLUGIN / "sounds" / "packs").iterdir() if p.is_dir())

    def test_at_least_the_default_pack_ships(self):
        assert any(p.name == "default" for p in self.packs)

    @pytest.mark.parametrize("earcon", EARCONS)
    def test_every_pack_has_every_earcon(self, earcon):
        for pack in self.packs:
            path = pack / f"{earcon}.wav"
            assert path.is_file(), f"{pack.name} is missing {earcon}.wav"

    def test_wavs_are_readable_mono_16_bit(self):
        for pack in self.packs:
            for earcon in EARCONS:
                with wave.open(str(pack / f"{earcon}.wav"), "rb") as w:
                    assert w.getnchannels() == 1
                    assert w.getsampwidth() == 2
                    assert w.getnframes() > 0

    def test_every_pack_is_described(self):
        for pack in self.packs:
            meta = read_json(pack / "pack.json")
            assert meta["name"] == pack.name
            assert meta["description"]

    def test_tones_stay_quiet(self):
        """A loud default is the fastest way to get uninstalled."""
        for pack in self.packs:
            for earcon in EARCONS:
                with wave.open(str(pack / f"{earcon}.wav"), "rb") as w:
                    frames = w.readframes(w.getnframes())
                samples = struct.unpack(f"<{len(frames) // 2}h", frames)
                peak = max(abs(s) for s in samples) / 32768
                assert peak < 0.75, f"{pack.name}/{earcon} peaks at {peak:.2f}"


class TestCommands:
    def test_each_command_declares_a_description(self):
        for path in (PLUGIN / "commands").glob("*.md"):
            text = path.read_text("utf-8")
            assert text.startswith("---\n"), f"{path.name} needs frontmatter"
            assert "description:" in text.split("---")[1], f"{path.name} needs a description"
