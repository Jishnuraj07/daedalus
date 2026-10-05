# Daedalus

> **Claude Code, audible.** A tone when it's done. A voice when it's blocked.
> Silence while it works.

Claude Code can't tell you when it's waiting on you. You start a long task, look
away, and either keep checking the terminal or come back to find it stalled on a
permission prompt from four minutes ago. Daedalus fixes exactly that, and nothing
else — it does **not** read replies aloud.

```
claude plugin marketplace add Jishnuraj07/daedalus
claude plugin install daedalus@daedalus
```

**No dependencies at all** — standard library Python 3.11+ and tools already on
your OS. No pip, no virtualenv, no build step.

## What you hear

| Situation | Waiting on you? | What happens |
| :- | :- | :- |
| Blocked on a permission prompt | **Yes** | Speech — *"run npm install?"* |
| It ended by asking you something | **Yes** | Speech — the question, verbatim |
| The turn failed (rate limit, auth, billing) | **Yes** | Speech — *"rate limited"* |
| The turn finished · waiting for input | Maybe | A tone |
| Working, calling tools, writing prose | **No** | **Nothing** |

That last row is most of a session, and it stays quiet. One rule governs
everything: **is the session waiting on me?** On top of that, a focused terminal
never speaks — you can see the screen, so a tone is enough.

Run `/daedalus:test` to learn the three tones, and `/daedalus:doctor` when
something's wrong.

## Claude Code only

This plugin ships executables in `bin/`, so chat and Cowork won't install it —
adding this marketplace there fails with "Marketplace sync failed", which is
about the `bin/` directory rather than the URL the message blames. It
needs them: every sound comes from a player already on your machine, and the
daemon reads your window manager to know whether you're looking at the screen.
Neither has any meaning outside a terminal session.

## Documentation

Full documentation, configuration and platform support live in the
[repository](https://github.com/Jishnuraj07/daedalus):

- [Configuration](https://github.com/Jishnuraj07/daedalus/blob/main/docs/configuration.md) — `~/.daedalus.toml`; `min_turn_seconds` is the dial that matters
- [Platform support](https://github.com/Jishnuraj07/daedalus/blob/main/docs/platform-support.md) — Windows, macOS, Linux, and what degrades where
- [Troubleshooting](https://github.com/Jishnuraj07/daedalus/blob/main/docs/troubleshooting.md) — start with `/daedalus:doctor`
- [Sound packs](https://github.com/Jishnuraj07/daedalus/blob/main/docs/sound-packs.md) — add your own

MIT licensed.
