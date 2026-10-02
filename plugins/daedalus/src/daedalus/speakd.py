"""The Daedalus daemon.

Started as a Claude Code *monitor*, so it comes up with the session and goes
down with it. One daemon serves the whole machine: several sessions each try to
start one, the first binds the port and the rest exit immediately, which keeps
audio coordinated instead of three processes talking over each other.

It never writes to stdout. A monitor's output reaches Claude as notifications,
so a stray byte here would quietly pollute every session's context. All
diagnostics go to a log file.
"""

from __future__ import annotations

import contextlib
import json
import logging
import socket
import socketserver
import threading
import time
from pathlib import Path

from .backends import Backends
from .backends.focus import classify
from .config import PORT, Config, load_state, save_state, state_dir
from .extract import from_payload
from .policy import PRIORITY, Decision, Event, Focus, Kind, decide

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
LOG_MAX_BYTES = 1_000_000

# The daemon can live for days across many sessions, so the per-session maps
# are bounded rather than left to grow.
MAX_SESSIONS = 64
RECENT_TTL = 60.0

log = logging.getLogger("daedalus")


def _evict(mapping: dict, limit: int = MAX_SESSIONS) -> None:
    """Drop oldest entries once a per-session map outgrows its limit."""
    while len(mapping) > limit:
        mapping.pop(next(iter(mapping)))


def setup_logging() -> None:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / "daedalus.log"
    if path.is_file() and path.stat().st_size > LOG_MAX_BYTES:
        path.unlink(missing_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
    log.addHandler(handler)  # file only -- never a StreamHandler
    log.setLevel(logging.INFO)
    log.propagate = False


class AudioSlot:
    """One sound at a time, with preemption by priority.

    Playback is asynchronous on every backend, so rather than tracking real
    stream state we hold the priority of what's playing and a conservative
    estimate of when it ends. A higher-or-equal priority always wins, so a
    "needs you" never waits behind a queued "done".
    """

    EARCON_SECONDS = 0.4

    def __init__(self, backends: Backends, pack_dir: Path) -> None:
        self._backends = backends
        self._pack = pack_dir
        self._lock = threading.Lock()
        self._priority = -1
        self._until = 0.0

    def _claim(self, priority: int) -> bool:
        now = time.monotonic()
        if now >= self._until or priority >= self._priority:
            self._priority, self._until = priority, now
            return True
        return False

    def flush(self) -> None:
        with self._lock:
            self._backends.audio.stop()
            self._backends.speech.stop()
            self._priority, self._until = -1, 0.0

    def play(self, decision: Decision, priority: int) -> bool:
        with self._lock:
            if not self._claim(priority):
                log.info("skipped (busy with higher priority): %s", decision.reason)
                return False
            self._backends.audio.stop()
            self._backends.speech.stop()

            if decision.earcon:
                path = self._pack / f"{decision.earcon}.wav"
                if path.is_file():
                    self._backends.audio.play(path)
                    self._until = time.monotonic() + self.EARCON_SECONDS
                else:
                    log.warning("missing earcon: %s", path)

            if decision.speech:
                words = len(decision.speech.split())
                self._backends.speech.say(decision.speech)
                self._until = time.monotonic() + max(2.0, words * 0.4)
            return True


class Daemon:
    def __init__(self, config: Config, backends: Backends, dry_run: bool = False) -> None:
        self.config = config
        self.backends = backends
        self.dry_run = dry_run
        self.slot = AudioSlot(backends, PLUGIN_ROOT / "sounds" / "packs" / config.pack)
        self.muted = bool(load_state().get("muted", False))
        self._turn_started: dict[str, float] = {}
        self._ancestry: dict[str, list[int]] = {}
        self._escalations: dict[str, threading.Timer] = {}
        self._recent: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()

    # -- focus -------------------------------------------------------------

    def _focus_for(self, session: str, chain: list[int]) -> Focus:
        """The client sends its own process ancestry.

        It has to: a hook process is short-lived, and if the daemon walked the
        tree itself the process could already be gone. Cached per session, since
        the terminal and Claude Code PIDs don't change while it runs.
        """
        with self._lock:
            cached = self._ancestry.get(session)
            if cached is None and chain:
                self._ancestry[session] = cached = chain
                _evict(self._ancestry)
                log.info("session %s ancestry %s", session[:8], chain)
        if not cached:
            return Focus.UNKNOWN
        return classify(self.backends.focus, cached)

    # -- escalation --------------------------------------------------------

    def _cancel_escalation(self, session: str) -> None:
        with self._lock:
            timer = self._escalations.pop(session, None)
        if timer:
            timer.cancel()

    def _cancel_all_escalations(self) -> None:
        """Used by mute: a repeat already in flight must not outlive it."""
        with self._lock:
            timers, self._escalations = list(self._escalations.values()), {}
        for timer in timers:
            timer.cancel()

    def _schedule_escalation(self, session: str) -> None:
        """Repeat an unanswered permission prompt exactly once, then never again."""
        self._cancel_escalation(session)

        def fire() -> None:
            with self._lock:
                self._escalations.pop(session, None)
            # Mute can land in the window between scheduling and firing, and
            # cancelling races with a timer already on its way to this line.
            # Rule 6 says mute always works, so check again here.
            if self.muted:
                log.info("escalation for session %s dropped; muted", session[:8])
                return
            log.info("escalating unanswered prompt for session %s", session[:8])
            self.slot.play(Decision(earcon="needs_you", reason="still waiting"), PRIORITY[Kind.PERM])

        timer = threading.Timer(self.config.escalate_after, fire)
        timer.daemon = True
        with self._lock:
            self._escalations[session] = timer
        timer.start()

    # -- events ------------------------------------------------------------

    def _debounced(self, session: str, kind: str) -> bool:
        key = (session, kind)
        now = time.monotonic()
        with self._lock:
            last = self._recent.get(key, 0.0)
            if now - last < self.config.debounce_seconds:
                return True
            self._recent = {k: t for k, t in self._recent.items() if now - t < RECENT_TTL}
            self._recent[key] = now
        return False

    def handle_emit(self, kind: str, session: str, chain: list[int], payload: dict) -> str:
        event = from_payload(kind, payload)
        if event is None:
            return "ignored"

        if event.kind is Kind.FLUSH:
            with self._lock:
                self._turn_started[session] = time.monotonic()
                _evict(self._turn_started)
            self._cancel_escalation(session)
            self.slot.flush()
            log.info("flush; turn clock started for session %s", session[:8])
            return "flushed"

        if self._debounced(session, kind):
            log.info("debounced duplicate %s for session %s", kind, session[:8])
            return "debounced"

        if event.kind is Kind.STOP:
            with self._lock:
                started = self._turn_started.pop(session, None)
            # No recorded start means the daemon came up mid-turn. Unknown
            # duration must not silence the event, so leave it None.
            if started is not None:
                event = Event(kind=event.kind, turn_seconds=time.monotonic() - started, text=event.text)
            self._cancel_escalation(session)

        focus = self._focus_for(session, chain)
        decision = decide(event, focus=focus, config=self.config, muted=self.muted)
        log.info(
            "%s focus=%s -> earcon=%s speech=%s (%s)",
            kind,
            focus.value,
            decision.earcon,
            bool(decision.speech),
            decision.reason,
        )

        if self.dry_run or decision.silent:
            return decision.reason or "silent"

        self.slot.play(decision, event.priority)
        if event.kind is Kind.PERM and not self.muted:
            self._schedule_escalation(session)
        return decision.reason

    def handle_command(self, cmd: str, payload: dict) -> str:
        if cmd == "mute":
            self.muted = True
            save_state({**load_state(), "muted": True})
            self._cancel_all_escalations()
            self.slot.flush()
            return "muted"
        if cmd == "unmute":
            self.muted = False
            save_state({**load_state(), "muted": False})
            return "unmuted"
        if cmd == "status":
            return json.dumps(
                {
                    "muted": self.muted,
                    "pack": self.config.pack,
                    "min_turn_seconds": self.config.min_turn_seconds,
                    "speak": self.config.speak,
                    "backends": {
                        "audio": [self.backends.audio.name, self.backends.audio_reason],
                        "speech": [self.backends.speech.name, self.backends.speech_reason],
                        "focus": [self.backends.focus.name, self.backends.focus_reason],
                    },
                }
            )
        if cmd == "test":
            for name in ("done", "needs_you", "failed"):
                self.slot.flush()
                self.slot.play(Decision(earcon=name, reason="test"), 99)
                time.sleep(0.8)
            return "played done, needs_you, failed"
        if cmd == "say":
            text = str(payload.get("text") or "").strip()
            if not text:
                return "nothing to say"
            self.slot.play(Decision(speech=text, reason="requested"), 99)
            return "speaking"
        return f"unknown command: {cmd}"


class Handler(socketserver.StreamRequestHandler):
    timeout = 5
    daemon: Daemon
    token: str

    def handle(self) -> None:
        try:
            raw = self.rfile.readline(65536)
            request = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return
        # A fixed loopback port is reachable by any local process; the shared
        # token keeps a stray one from driving the speakers.
        if request.get("token") != self.token:
            log.warning("rejected request with bad token")
            return
        try:
            cmd = str(request.get("cmd") or "emit")
            if cmd == "emit":
                raw_chain = request.get("ancestors") or []
                chain = [int(p) for p in raw_chain if isinstance(p, int)]
                if request.get("parse_error"):
                    log.warning("client reported %s", request["parse_error"])
                result = self.daemon.handle_emit(
                    str(request.get("kind") or ""),
                    str(request.get("session_id") or "-"),
                    chain,
                    request.get("payload") or {},
                )
            else:
                result = self.daemon.handle_command(cmd, request)
            self.wfile.write(json.dumps({"ok": True, "result": result}).encode() + b"\n")
        except Exception:  # a bad event must never take the daemon down
            log.exception("error handling %s", request.get("cmd"))
            with contextlib.suppress(OSError):
                self.wfile.write(b'{"ok": false}\n')


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = False  # the bind IS the singleton lock
    daemon_threads = True


def serve(dry_run: bool = False) -> int:
    setup_logging()
    config = Config.load()
    backends = Backends.resolve()
    daemon = Daemon(config, backends, dry_run=dry_run)

    from .config import token

    handler = type("BoundHandler", (Handler,), {"daemon": daemon, "token": token()})

    try:
        server = Server(("127.0.0.1", PORT), handler)
    except OSError:
        # Another session already started one. That's the intended outcome.
        log.info("daemon already running on port %d; exiting", PORT)
        return 0

    log.info("daemon listening on 127.0.0.1:%d\n%s", PORT, backends.report())
    # Logged by the daemon that won the port, not by every session that stood
    # down, so one bad config line produces one warning rather than a dozen.
    for key, why in sorted(config.ignored.items()):
        log.warning("ignoring config %s: %s", key, why)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        log.info("daemon stopped")
    return 0


def send(request: dict, timeout: float = 2.0) -> dict | None:
    """Client side: one JSON line in, one JSON line out."""
    from .config import token

    payload = json.dumps({**request, "token": token()}).encode() + b"\n"
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=timeout) as sock:
            sock.sendall(payload)
            with sock.makefile("rb") as fh:
                line = fh.readline()
        return json.loads(line.decode("utf-8")) if line else None
    except (OSError, ValueError):
        return None
