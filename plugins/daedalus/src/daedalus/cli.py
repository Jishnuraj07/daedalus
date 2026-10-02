"""Command line entry point, used by the hooks, the monitor, and the commands.

``emit`` is the hot path: it reads a hook payload on stdin, hands it to the
daemon, and exits. It must be fast and it must never fail loudly -- a hook that
errors is worse than one that stays quiet, so every failure path exits 0.
"""

from __future__ import annotations

import json
import os
import sys

from .backends import Backends
from .backends.focus import ancestors
from .config import PORT, Config, config_path, state_dir
from .speakd import send, serve

USAGE = """daedalus -- Claude Code, audible

  serve [--dry-run]   run the daemon (started automatically as a monitor)
  emit <kind>         forward a hook payload from stdin
                      kinds: stop fail perm notify flush
  doctor              show which backends resolved, and why
  test                play the three earcons
  mute | unmute       toggle all output
  say [text]          speak text (or stdin) on demand
  status              print daemon status as JSON
"""


def _read_payload() -> tuple[dict, str | None]:
    """Parse the hook payload from stdin, returning the reason on failure.

    Decoded as utf-8-sig: a BOM on stdin is a real possibility on Windows, and
    an unhandled one loses every field while the event still fires, which looks
    like working software behaving strangely. The reason travels to the daemon
    so a mangled payload shows up in the log instead of vanishing.
    """
    try:
        raw = sys.stdin.buffer.read()
    except (OSError, ValueError):
        return {}, "stdin unreadable"
    if not raw.strip():
        return {}, None
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as exc:
        return {}, f"unparseable payload: {type(exc).__name__}"
    if not isinstance(payload, dict):
        return {}, "payload was not a JSON object"
    return payload, None


def _emit(kind: str) -> int:
    payload, error = _read_payload()
    send(
        {
            "cmd": "emit",
            "kind": kind,
            "session_id": str(payload.get("session_id") or "-"),
            "ancestors": ancestors(os.getpid()),
            "payload": payload,
            "parse_error": error,
        }
    )
    # Deliberately silent and always successful: if the daemon isn't up, the
    # session should carry on exactly as if Daedalus weren't installed.
    return 0


def _doctor() -> int:
    backends = Backends.resolve()
    config = Config.load()
    print("daedalus doctor\n")
    print("backends")
    print(backends.report())
    print("\nconfig")
    cfg = config_path()
    print(f"  file      {cfg}{'' if cfg.is_file() else '  (not present, using defaults)'}")
    print(f"  pack      {config.pack}")
    print(f"  min turn  {config.min_turn_seconds:g}s  (shorter turns make no sound)")
    print(f"  speak     {config.speak}")
    print(f"  escalate  {config.escalate_after:g}s")
    print("\ndaemon")
    reply = send({"cmd": "status"}, timeout=1.0)
    if not reply or not reply.get("ok"):
        print(f"  not running  (nothing listening on 127.0.0.1:{PORT})")
        print("  it starts with your next Claude Code session, or run: daedalus serve")
    else:
        status = json.loads(reply["result"])
        print(f"  running on 127.0.0.1:{PORT}")
        print(f"  muted     {status['muted']}")
    print(f"\nlogs\n  {state_dir() / 'daedalus.log'}")
    return 0


def _simple(cmd: str, **extra: object) -> int:
    reply = send({"cmd": cmd, **extra}, timeout=10.0)
    if not reply or not reply.get("ok"):
        print("daemon not running; start a Claude Code session or run: daedalus serve")
        return 1
    print(reply["result"])
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        print(USAGE)
        return 0

    cmd, rest = args[0], args[1:]

    if cmd == "serve":
        return serve(dry_run="--dry-run" in rest)
    if cmd == "emit":
        return _emit(rest[0] if rest else "")
    if cmd == "doctor":
        return _doctor()
    if cmd in {"test", "mute", "unmute", "status"}:
        return _simple(cmd)
    if cmd == "say":
        text = " ".join(rest).strip() or sys.stdin.read().strip()
        return _simple("say", text=text)

    print(USAGE)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
