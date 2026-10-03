"""Turn a raw hook payload into an :class:`Event`.

This is the entire text-processing surface of the project. No model, no
summarising: every spoken string is either already a human-written sentence in
the payload, a static lookup, or one regex away.
"""

from __future__ import annotations

import re

from .policy import Event, Kind

# A question longer than this isn't worth speaking: the tone already told you to
# look, and a 40-word spoken question is worse than silence.
MAX_QUESTION_WORDS = 40

# Keep spoken commands short enough to parse by ear.
MAX_COMMAND_WORDS = 8

# A project label is a directory basename, so it is short already. This is a
# guard against a pathological one, not a real trim.
MAX_LABEL_WORDS = 4

FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`([^`]*)`")
EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_)")
LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+", re.MULTILINE)
HEADING_RE = re.compile(r"^\s*#+\s*", re.MULTILINE)
# Sentence enders, or a blank line. Deliberately NOT every newline: Claude wraps
# sentences across lines, and splitting on a soft wrap truncates a question to
# its last fragment ("continue?" instead of "Should I continue?"). A blank line
# is a real paragraph break, which is what makes the markdown-list case work.
SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n\s*\n")

# StopFailure.error_type is a fixed set, so a table beats any cleverness.
FAILURE_PHRASES = {
    "rate_limit": "rate limited",
    "overloaded": "the API is overloaded",
    "authentication_failed": "authentication failed",
    "oauth_org_not_allowed": "your organization isn't allowed",
    "account_on_hold": "your account is on hold",
    "billing_error": "a billing problem",
    "invalid_request": "an invalid request",
    "model_not_found": "the model wasn't found",
    "server_error": "a server error",
    "max_output_tokens": "it hit the output limit",
    "cloud_credential_error": "a cloud credential problem",
    "unknown": "something went wrong",
}


def _strip_markdown(text: str) -> str:
    """Drop what shouldn't be read aloud, keep what carries meaning.

    Fenced code goes first: a ``?`` inside a code block is not a question
    addressed to you.
    """
    text = FENCE_RE.sub(" ", text)
    text = INLINE_CODE_RE.sub(r"\1", text)  # keep the identifier, lose the backticks
    text = HEADING_RE.sub("", text)
    text = LIST_MARKER_RE.sub("", text)
    text = EMPHASIS_RE.sub("", text)
    return text.strip()


def trailing_question(message: str | None) -> str | None:
    """The final sentence, but only if the message actually ends by asking you something.

    A question in the *middle* of a reply that then ends on a statement is not a
    question for you, and must not trigger speech.
    """
    if not message:
        return None
    text = _strip_markdown(message)
    if not text.endswith("?"):
        return None
    parts = [p.strip() for p in SPLIT_RE.split(text) if p.strip()]
    if not parts:
        return None
    question = parts[-1]
    if not question.endswith("?"):
        return None
    if len(question.split()) > MAX_QUESTION_WORDS:
        return None
    return " ".join(question.split())


def _shorten(command: str, limit: int = MAX_COMMAND_WORDS) -> str:
    words = command.split()
    if len(words) <= limit:
        return " ".join(words)
    return " ".join(words[:limit]) + ", and more"


def permission_text(payload: dict) -> str:
    """What the agent wants to do, phrased so it's actionable by ear.

    "run npm install?" tells you something; "permission for Bash" does not.
    """
    tool = str(payload.get("tool_name") or "a tool")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    if tool == "Bash":
        command = str(tool_input.get("command") or "").strip()
        if command:
            return f"run {_shorten(command)}?"
    if tool in {"Edit", "Write", "NotebookEdit"}:
        path = str(tool_input.get("file_path") or "").strip()
        if path:
            name = re.split(r"[\\/]", path)[-1]
            verb = "write" if tool == "Write" else "edit"
            return f"{verb} {name}?"
    return f"permission for {tool}?"


def project_label(cwd: object) -> str | None:
    """Which project a session is in, as something a synthesiser can read.

    The directory basename, with separators turned into spaces: a voice reads
    ``my_api-v2`` as punctuation and ``my api v2`` as words. Both kinds of path
    separator are split on, whatever platform this runs on, since the payload
    reports whatever Claude Code saw.
    """
    if not isinstance(cwd, str):
        return None
    path = cwd.strip().rstrip("/\\")
    if not path:
        return None
    name = re.split(r"[\\/]+", path)[-1]
    name = " ".join(re.sub(r"[-_.]+", " ", name).split())
    if not name:
        return None
    return " ".join(name.split()[:MAX_LABEL_WORDS])


def from_payload(kind: str, payload: dict) -> Event | None:
    """Map a hook invocation to an event, or ``None`` when there's nothing to do."""
    if kind == "flush":
        return Event(kind=Kind.FLUSH)

    if kind == "busy":
        # PostToolBatch: a batch of tool calls resolved. Proof the session is
        # working, which is how an answered permission prompt becomes knowable
        # -- nothing else tells us you said yes.
        return Event(kind=Kind.BUSY)

    if kind == "stop":
        return Event(kind=Kind.STOP, text=trailing_question(payload.get("last_assistant_message")))

    if kind == "fail":
        error = str(payload.get("error_type") or "unknown")
        return Event(kind=Kind.FAIL, text=FAILURE_PHRASES.get(error, FAILURE_PHRASES["unknown"]))

    if kind == "perm":
        return Event(kind=Kind.PERM, text=permission_text(payload))

    if kind == "notify":
        # Only idle matters here. Notification also fires for permission prompts,
        # but PermissionRequest describes the same moment with the actual command
        # in it, so taking both would mean two sounds for one event.
        if payload.get("notification_type") == "idle_prompt":
            return Event(kind=Kind.IDLE)
        return None

    return None
