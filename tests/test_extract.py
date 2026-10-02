"""Payload to spoken string. No model involved, so the edge cases are all here."""

import pytest
from daedalus.extract import (
    FAILURE_PHRASES,
    MAX_QUESTION_WORDS,
    from_payload,
    permission_text,
    trailing_question,
)
from daedalus.policy import Kind


class TestTrailingQuestion:
    def test_plain_question(self):
        assert trailing_question("I updated the config. Should I update the tests?") == (
            "Should I update the tests?"
        )

    def test_statement_is_not_a_question(self):
        assert trailing_question("I updated the config and the tests.") is None

    def test_question_in_the_middle_is_not_for_you(self):
        """The trap case: it asked, then answered itself and ended on a statement."""
        assert trailing_question("Should I refactor? I went ahead and did it.") is None

    def test_question_mark_inside_a_code_fence_is_not_a_question(self):
        message = "Here you go:\n```py\nx = input('ready?')\n```\nThat covers it."
        assert trailing_question(message) is None

    def test_code_fence_before_a_real_question(self):
        message = "Here:\n```py\nprint(1)\n```\nWant me to run it?"
        assert trailing_question(message) == "Want me to run it?"

    def test_inline_code_keeps_its_contents(self):
        assert trailing_question("Should I edit `config.py`?") == "Should I edit config.py?"

    def test_markdown_list_question(self):
        assert trailing_question("Options:\n- a\n- b\n\nWhich one?") == "Which one?"

    def test_overlong_question_is_dropped(self):
        """Too long to speak cleanly: the tone already said to look."""
        long = " ".join(["word"] * (MAX_QUESTION_WORDS + 5)) + "?"
        assert trailing_question(long) is None

    def test_whitespace_is_collapsed(self):
        assert trailing_question("Done.  Should   I\n  continue?") == "Should I continue?"

    def test_soft_wrapped_question_survives_intact(self):
        """A single newline is a wrap, not a sentence end.

        Splitting on it would truncate this to "the tests?".
        """
        message = "I updated the config.\nShould I also update\nthe tests?"
        assert trailing_question(message) == "Should I also update the tests?"

    def test_blank_line_is_a_real_boundary(self):
        message = "I finished the refactor.\n\nWant me to run the suite?"
        assert trailing_question(message) == "Want me to run the suite?"

    @pytest.mark.parametrize("value", [None, "", "   ", "\n\n"])
    def test_empty_input(self, value):
        assert trailing_question(value) is None

    def test_bare_question_mark_does_not_crash(self):
        assert trailing_question("?") == "?"


class TestPermissionText:
    def test_bash_speaks_the_actual_command(self):
        text = permission_text({"tool_name": "Bash", "tool_input": {"command": "npm install"}})
        assert text == "run npm install?"

    def test_long_command_is_shortened(self):
        command = "docker compose -f docker-compose.prod.yml up -d --build --force-recreate web"
        text = permission_text({"tool_name": "Bash", "tool_input": {"command": command}})
        assert text.startswith("run docker compose")
        assert text.endswith("and more?")
        assert len(text.split()) <= 12

    def test_edit_uses_the_basename(self):
        text = permission_text(
            {"tool_name": "Edit", "tool_input": {"file_path": "E:/app/src/api/middleware.ts"}}
        )
        assert text == "edit middleware.ts?"

    def test_write_says_write(self):
        text = permission_text({"tool_name": "Write", "tool_input": {"file_path": "/tmp/a/new.py"}})
        assert text == "write new.py?"

    def test_windows_path_separators(self):
        text = permission_text({"tool_name": "Edit", "tool_input": {"file_path": r"C:\app\src\main.rs"}})
        assert text == "edit main.rs?"

    def test_other_tools_name_the_tool(self):
        assert permission_text({"tool_name": "WebFetch", "tool_input": {}}) == "permission for WebFetch?"

    def test_missing_fields_do_not_crash(self):
        assert permission_text({}) == "permission for a tool?"
        assert permission_text({"tool_name": "Bash"}) == "permission for Bash?"
        assert permission_text({"tool_name": "Bash", "tool_input": "not a dict"}) == "permission for Bash?"


class TestFromPayload:
    def test_stop_without_question(self):
        event = from_payload("stop", {"last_assistant_message": "All done."})
        assert event.kind is Kind.STOP and event.text is None

    def test_stop_with_question(self):
        event = from_payload("stop", {"last_assistant_message": "Ready. Shall I push?"})
        assert event.text == "Shall I push?"

    def test_failure_maps_to_plain_words(self):
        assert from_payload("fail", {"error_type": "rate_limit"}).text == "rate limited"

    def test_unknown_failure_falls_back(self):
        assert from_payload("fail", {"error_type": "nonsense"}).text == FAILURE_PHRASES["unknown"]
        assert from_payload("fail", {}).text == FAILURE_PHRASES["unknown"]

    def test_every_documented_error_type_has_a_phrase(self):
        for error_type in FAILURE_PHRASES:
            assert from_payload("fail", {"error_type": error_type}).text

    def test_idle_notification_has_no_speech(self):
        """Saying "Claude is waiting for input" adds nothing you don't know."""
        event = from_payload("notify", {"notification_type": "idle_prompt"})
        assert event.kind is Kind.IDLE and event.text is None

    def test_permission_prompt_notification_is_ignored(self):
        """PermissionRequest covers the same moment with the real command in it.

        Taking both would mean two sounds for one event.
        """
        assert from_payload("notify", {"notification_type": "permission_prompt"}) is None

    def test_flush(self):
        assert from_payload("flush", {}).kind is Kind.FLUSH

    def test_unknown_kind_is_ignored(self):
        assert from_payload("nonsense", {}) is None

    def test_empty_payload_never_crashes(self):
        for kind in ("stop", "fail", "perm", "notify", "flush"):
            from_payload(kind, {})
