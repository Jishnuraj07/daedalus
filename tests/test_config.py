"""``~/.daedalus.toml`` is hand-edited, so every value in it arrives untrusted.

A bad value must fall back to the default and *say so*. Silently doing nothing
is the one outcome that looks like broken software rather than a typo.
"""

import pytest
from daedalus.config import Config


@pytest.fixture
def write_config(isolated_home):
    def write(text: str) -> Config:
        (isolated_home / ".daedalus.toml").write_text(text, "utf-8")
        return Config.load()

    return write


class TestDefaults:
    def test_no_file_means_defaults(self):
        config = Config.load()
        assert config.min_turn_seconds == 3.0
        assert config.pack == "default"
        assert config.ignored == {}

    def test_valid_file_is_applied(self, write_config):
        config = write_config('pack = "soft"\nmin_turn_seconds = 10\nspeak = false\n')
        assert (config.pack, config.min_turn_seconds, config.speak) == ("soft", 10.0, False)
        assert config.ignored == {}

    def test_integers_become_floats(self, write_config):
        """TOML ``10`` and ``10.0`` must behave identically; the policy compares floats."""
        assert isinstance(write_config("min_turn_seconds = 10\n").min_turn_seconds, float)

    def test_zero_is_a_legitimate_value(self, write_config):
        """Zero means "no quiet window" -- a real choice, not a bad value."""
        config = write_config("min_turn_seconds = 0\n")
        assert config.min_turn_seconds == 0.0
        assert config.ignored == {}

    def test_false_is_not_mistaken_for_a_bad_value(self, write_config):
        """``speak = false`` is falsy; the check must not read that as a rejection."""
        config = write_config("speak = false\n")
        assert config.speak is False
        assert config.ignored == {}


class TestBadValues:
    """Each of these used to be applied as-is, and the daemon crashed later on."""

    @pytest.mark.parametrize(
        "line,field,default",
        [
            ('min_turn_seconds = "ten"', "min_turn_seconds", 3.0),  # crashed every decision
            ("min_turn_seconds = -1", "min_turn_seconds", 3.0),
            ("min_turn_seconds = nan", "min_turn_seconds", 3.0),
            ("min_turn_seconds = true", "min_turn_seconds", 3.0),  # bool is an int subclass
            ("escalate_after = -5", "escalate_after", 30.0),  # fired the repeat instantly
            ('escalate_after = "soon"', "escalate_after", 30.0),
            ("debounce_seconds = -1", "debounce_seconds", 0.3),
            ('speak = "yes"', "speak", True),
            ("speak = 1", "speak", True),
            ("pack = 7", "pack", "default"),  # crashed the daemon at startup
            ('pack = ""', "pack", "default"),
            ('pack = "  "', "pack", "default"),
        ],
    )
    def test_bad_value_falls_back_and_is_reported(self, write_config, line, field, default):
        config = write_config(line + "\n")
        assert getattr(config, field) == default
        key = line.split("=")[0].strip()
        assert key in config.ignored, f"{key} fell back silently"
        assert "expected" in config.ignored[key]

    @pytest.mark.parametrize("name", ["../soft", "../../etc", "a/b", "sub\\pack", ".", ".."])
    def test_a_pack_name_cannot_escape_the_packs_directory(self, write_config, name):
        """Outside that directory the earcons aren't found and everything goes quiet."""
        # A TOML literal string, so the backslash case stays a backslash.
        config = write_config(f"pack = '{name}'\n")
        assert config.pack == "default"
        assert "pack" in config.ignored

    def test_a_bad_value_does_not_discard_the_good_ones(self, write_config):
        config = write_config('min_turn_seconds = "ten"\npack = "soft"\n')
        assert config.pack == "soft"
        assert config.min_turn_seconds == 3.0

    def test_unparseable_file_runs_on_defaults_and_says_so(self, write_config):
        config = write_config("this is not toml = = =\n")
        assert config.min_turn_seconds == 3.0
        assert config.ignored, "an unreadable config must not be silent"


class TestUnknownKeys:
    def test_a_typo_is_reported_rather_than_swallowed(self, write_config):
        """``min_turn`` silently did nothing, which reads as "the setting is broken"."""
        config = write_config("min_turn = 30\n")
        assert config.min_turn_seconds == 3.0
        assert config.ignored == {"min_turn": "not a Daedalus setting"}

    def test_every_documented_setting_is_accepted(self, write_config):
        """The block in docs/configuration.md must load with nothing ignored."""
        config = write_config(
            'pack = "default"\n'
            "min_turn_seconds = 3.0\n"
            "speak = true\n"
            "escalate_after = 30.0\n"
            "debounce_seconds = 0.3\n"
        )
        assert config.ignored == {}
