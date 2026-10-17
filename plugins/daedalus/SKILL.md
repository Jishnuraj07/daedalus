---
name: daedalus
description: Diagnose, configure and explain Daedalus, the Claude Code plugin that plays a tone when a turn finishes and speaks when the session is blocked on you. Use when the user asks why Daedalus made a sound or stayed silent, wants it quieter or chattier, wants to mute it or change its sound pack, or has missing audio or speech.
license: MIT
compatibility: Claude Code only — it works through Claude Code hooks and a background monitor, which other agents don't load. Needs Python 3.11+ and the OS's own audio tools; on Linux, speech-dispatcher or espeak for speech and x11-utils for focus. No network access beyond a loopback socket.
---

# Daedalus

Daedalus makes a Claude Code session audible only when it is waiting on the
user: a tone when a turn finishes, speech when it is blocked on a permission
prompt, a question, or an API failure, and silence while it works. It never
reads replies aloud on its own.

The sounds come from the bundled plugin — its hooks and a small daemon — not
from this skill. This skill is for helping the user understand and tune it.

## Install

Unzip into the skills folder **in your home directory**, then start a new Claude
Code session:

```bash
unzip daedalus-*.zip -d ~/.claude/skills/
```

It has to be `~/.claude/skills/`, not a project's `.claude/skills/`. Claude Code
loads a plugin's hooks from either, but its background monitor only from your
home folder — and without the monitor the daemon never starts, so nothing ever
makes a sound. If you also installed Daedalus with `claude plugin install`, that
copy is the one that loads; remove one of them.

## Diagnose

Start every investigation here, and show the output verbatim:

```bash
daedalus doctor
```

It reports which audio, speech and focus backends resolved and why the others
didn't, whether the daemon is running, and any lines in the config file that
were ignored. A backend of `null` names what to install.

Then read the log. Every decision is recorded with the reason it was made:

```bash
tail -n 40 ~/.daedalus/daedalus.log
```

Lines look like `perm focus=unfocused label=- -> earcon=needs_you speech=True
(waiting on you, and you're away)`. Read the reason in parentheses back to the
user — it answers "why did it do that" directly:

- `turn took 0.4s, under the 3.0s threshold` — short turns are silent by design.
- `terminal focused; a tone is enough` — it never speaks to a focused terminal.
- `focus unknown; staying conservative` — focus can't be read (Wayland, SSH, or
  a missing tool), so it speaks only for hard blocks.
- `via=tmux` — focus was asked of tmux; a hidden pane counts as away.
- `label=<project>` — more than one project is live, so speech names this one.

## Configure

Settings live in `~/.daedalus.toml`. Every key is optional:

| Key | Default | Effect |
| :- | :- | :- |
| `min_turn_seconds` | `3.0` | Turns shorter than this make no sound. **The dial that matters** — raise it first if Daedalus feels chatty. |
| `speak` | `true` | `false` keeps every tone and drops the speech. |
| `pack` | `"default"` | `"soft"` is quieter and an octave down. |
| `escalate_after` | `30.0` | Seconds before an unanswered permission prompt repeats, once. |

Changes apply when the daemon next starts, which is the next Claude Code
session. After editing, run `daedalus doctor` — a misspelled key or a bad value
appears under "ignored in your config file" instead of silently doing nothing.

## Commands

`daedalus mute` and `daedalus unmute` (persistent), `daedalus test` (plays the
three tones), and `daedalus say "text"`. Only use `say` when the user asks for
something to be read aloud.

## What it runs

So the user can see exactly what they are installing:

- **Hooks**, all asynchronous, on Stop, StopFailure, PermissionRequest,
  Notification (idle only), UserPromptSubmit and PostToolBatch. They observe;
  they never answer a permission prompt.
- **A daemon** listening on `127.0.0.1:47113` only, guarded by a token in
  `~/.daedalus/state.json`. It never writes to stdout.
- **The OS's own tools** as subprocesses: `afplay`, `say` and `osascript` on
  macOS; `paplay` or `aplay`, `spd-say` or `espeak`, and `xprop` on Linux;
  `winsound` and PowerShell's System.Speech on Windows; `tmux` inside tmux.
- **Files**: it writes only under `~/.daedalus/`, and reads `~/.daedalus.toml`.

No external network access, no model calls, no dependencies to install.

Source and full documentation: https://github.com/Jishnuraj07/daedalus
