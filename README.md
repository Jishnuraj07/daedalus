# Daedalus

> **Claude Code, audible.** A tone when it's done. A voice when it's blocked. Silence while it works.

Claude Code can't tell you when it's waiting on you. You start a long task, look
away, and either keep checking the terminal or come back to find it stalled on a
permission prompt from four minutes ago.

Daedalus fixes exactly that, and nothing else. It does **not** read replies
aloud — your screen already renders them perfectly. It makes a session audible
only at the moments you'd otherwise miss.

```
claude plugin marketplace add Jishnuraj07/daedalus
claude plugin install daedalus@daedalus
```

Two commands. **No dependencies at all** — standard library Python 3.11+ and
tools already on your OS. No pip, no virtualenv, no build step.

---

## What you hear

| Situation | Waiting on you? | What happens |
| :- | :- | :- |
| Blocked on a permission prompt | **Yes** | Speech — *"run npm install?"* |
| It ended by asking you something | **Yes** | Speech — the question, verbatim |
| The turn failed (rate limit, auth, billing) | **Yes** | Speech — *"rate limited"* |
| The turn finished | Maybe | A tone |
| Waiting for input | Maybe | A tone |
| Working, calling tools, writing prose | **No** | **Nothing** |

That last row is most of a session, and it stays quiet.

Three tones, pitch-coded so they're learnable in a day and unnoticeable in a
week: **rising** = fine, **falling** = you're needed, **one low note** = broken.
Run `/daedalus:test` to hear them.

## How it decides

One rule governs everything: **is the session waiting on me?** Nothing else —
not what you asked, not what the reply says.

On top of that, Daedalus checks whether your terminal is the foreground window:

- **Focused** → you can see the screen, so a tone is enough. It never speaks.
- **Not focused** → you actually left, so it speaks.

That's why there are no wake words, no cue phrases and no modes to toggle. And
a few rules keep it from becoming an annoyance, which is the entire difference
between a product and a gadget:

1. **Turns under 3 seconds make no sound at all.** You never looked away.
2. A focused terminal never speaks.
3. One sound at a time — a *needs-you* preempts a queued *done*.
4. An unanswered permission prompt repeats **once** — saying what it's still
   waiting for — then never again. Answering it stops the repeat.
5. Submitting a new prompt cancels pending audio.
6. `/daedalus:mute` always works, and persists.

One last thing shapes what it says rather than whether it speaks: **when more
than one session is live, speech names the project first** — *"daedalus, run npm
install?"*. Heard from the next room, that tells you which terminal to walk back
to, which is the whole point. With a single session, or several in the same
project, nothing is added: a name that can't tell them apart would be words
carrying no information.

## Commands

| Command | What it does |
| :- | :- |
| `/daedalus:doctor` | Which backends resolved, and why the others didn't. Start here when something's wrong |
| `/daedalus:test` | Play the three tones, to learn them and set your volume |
| `/daedalus:mute` · `/daedalus:unmute` | Silence it, persistently |
| `/daedalus:say` | Read the last reply aloud, on demand |

The same things work in a shell as `daedalus doctor`, `daedalus test`, and so on.

## Configuration

Everything has a sensible default; the file is optional. Create
`~/.daedalus.toml` to change anything:

```toml
pack = "default"          # "default" or "soft"; or add your own
min_turn_seconds = 3.0    # turns shorter than this are silent
speak = true              # false keeps the tones, drops the speech
escalate_after = 30.0     # seconds before an unanswered prompt repeats once
```

**`min_turn_seconds` is the dial that matters.** It's the one thing worth tuning
from real use — if Daedalus ever feels chatty, raise it before changing anything
else. Plenty of people will want 10 or more.

## Platform support

Every backend is something already on your machine.

| | Tones | Speech | Focus |
| :- | :- | :- | :- |
| **Windows** | `winsound` (stdlib) | System.Speech | `GetForegroundWindow` |
| **macOS** | `afplay` | `say` | `osascript` |
| **Linux / X11** | `paplay` or `aplay` | `spd-say` or `espeak` *(optional)* | `xprop` *(needs `x11-utils`)* |
| **Linux / Wayland** | `paplay` | as above | **not available** |

Python 3.11 or newer. It runs on 3.10 too, but ignores `~/.daedalus.toml`, since
reading that needs `tomllib`.

Nothing hard-fails when a backend is missing. Where focus can't be determined,
Daedalus runs in **conservative mode**: tones still work, and it speaks only for
hard-blocked states. Where speech is unavailable, you still get every tone.
`/daedalus:doctor` tells you exactly what resolved and why. Full detail in
[docs/platform-support.md](docs/platform-support.md).

## How it works

Claude Code hooks fire on the events that matter and hand them to a small
daemon, which owns the audio and makes the decision.

```
hooks (async)          ──► bin/daedalus emit ──► 127.0.0.1:47113 ──► speakd
  Stop                                                                │
  StopFailure                                                   focused?
  PermissionRequest                                             how long?
  Notification (idle)                                           muted?
  UserPromptSubmit                                                    │
  PostToolBatch                                     silence │ tone │ tone+speech
```

A few things worth knowing:

- **The daemon starts itself.** It's declared as a Claude Code *monitor*, so it
  comes up with your session and goes down with it.
- **One daemon per machine, not per session.** Several sessions each try to start
  one; the first binds the port and the rest exit immediately. Audio stays
  coordinated instead of three processes talking over each other — and because
  one process sees them all, it knows when to name the project it's speaking
  for.
- **It never writes to stdout.** A monitor's output reaches Claude as
  notifications, so anything printed there would quietly pollute every session's
  context. Diagnostics go to `~/.daedalus/daedalus.log`.
- **No model is ever called.** Every spoken string is already a human-written
  sentence in the hook payload, a static lookup, or one regex away — the project
  name included, which is just the basename of `cwd`. Zero cost, zero added
  latency, and nothing to mangle your content.
- **`PermissionRequest` is observed, never answered.** Its hook is `async`, so
  its output is ignored by design — Daedalus cannot approve a tool call for you.
- **`PostToolBatch` is how it learns you said yes.** Nothing tells Daedalus that
  a permission prompt was answered, so without it the repeat fired whether or
  not you'd approved. Tools having run is the proof. It makes no sound of its own
  — it's the most frequent hook by a wide margin, so a tone there would turn the
  quietest part of a session into the loudest, and it skips the process walk the
  others pay for.

## Pairs well with `/voice`

Claude Code already has voice *input* — `/voice` for hold- or tap-to-talk, and
`"autoSubmit": true` to send on release. Daedalus is the other half of that
loop, and together they're a hands-free session.

Worth knowing: `/voice` needs a claude.ai account — it doesn't work with a
direct API key, Bedrock, Vertex or Foundry, nor over SSH. **Daedalus itself has
no such requirement and needs no API key.**

## Contributing

Sound packs are the easy, welcome contribution: a directory under
`plugins/daedalus/sounds/packs/<name>/` with `done.wav`, `needs_you.wav`,
`failed.wav` and a `pack.json`. See [docs/sound-packs.md](docs/sound-packs.md).

For code, [CONTRIBUTING.md](CONTRIBUTING.md) has the layout and how to run the
tests. The policy layer is pure functions over plain data, so the whole product
is testable without a sound card or a window manager.

## License

MIT. See [LICENSE](LICENSE).
