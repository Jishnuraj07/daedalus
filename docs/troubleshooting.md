# Troubleshooting

Start with `/daedalus:doctor`, or `daedalus doctor` in a shell. It reports which
backend was chosen for audio, speech and focus, and the reason for each —
including why a backend was *not* chosen. Most problems are answered by that
output alone, so paste it into any bug report.

The log is at `~/.daedalus/daedalus.log`. Every decision is recorded there with
the reason it was made, so you can see exactly why something was or wasn't
heard.

## No sound at all

**Check the daemon is running.** `daedalus doctor` says so near the bottom. It
starts automatically with a Claude Code session, as a monitor. If it isn't
running, start one manually to see the error:

```bash
daedalus serve
```

**Check you aren't muted.** Mute persists across restarts, so one from last week
is still in effect. `daedalus doctor` reports it; `daedalus unmute` clears it.

**Check your config file was understood.** If `doctor` prints an **ignored in
your config file** section, those lines had no effect — a misspelled key, or a
value of the wrong type. It says what it expected and what it found.

**Check you aren't in the quiet window.** Turns shorter than
`min_turn_seconds` (default 3s) make no sound by design. The log will say
`turn took 0.4s, under the 3.0s threshold`. That's working correctly.

**Check audio directly**, bypassing all policy:

```bash
daedalus test
```

If that's silent but the rest looks healthy, it's the audio backend — see below.

## It never speaks, only plays tones

Usually correct behaviour: **a focused terminal never speaks.** If you can see
the screen, a tone is enough. The log says `terminal focused; a tone is enough`.
Click another window and try again.

Other causes, in order of likelihood:

- `speak = false` in `~/.daedalus.toml`.
- The speech backend is `null` — `doctor` says why. On Linux, install
  `speech-dispatcher` or `espeak`.
- Focus is `unknown`, so Daedalus is in **conservative mode**: it speaks only
  for hard-blocked states (permission prompts and failures), not for questions.
  This is expected on Wayland.

## Focus is reported as unknown

Daedalus can't tell whether your terminal is in front, so it stays conservative.
It still works; it's just more reserved.

- **Wayland** exposes no focus API. There is no fix, and `xprop` won't help.
- **Linux/X11** needs `xprop`: `sudo apt install x11-utils`.
- **No `DISPLAY`** means `xprop` has no display to read, even when it's
  installed. Usual over SSH. `doctor` says so explicitly.
- **macOS** needs `osascript`, which is built in. If it's failing, check whether
  your terminal has been granted Automation permission under System Settings →
  Privacy & Security.
- **SSH or a container** has no window to be focused. Expected.

## It speaks when I *am* at the screen

Focus detection is reporting the wrong thing. The log line for the event shows
the ancestry chain it compared against:

```
session a1b2c3d4 ancestry [17984, 18024, 8140, 17296, 1080]
```

Daedalus treats you as focused when the foreground window's process is one of
those. That can miss in a few setups — a terminal multiplexer, a terminal whose
window is owned by a separate process, or a session started from a different
shell than the one you're looking at.

Workarounds: `speak = false` keeps the tones and drops the speech, which usually
gives you what you want anyway. If you can describe your setup, a bug report
with that ancestry line is genuinely useful.

## It said "still waiting" when I'd already approved

Daedalus is told when a prompt *appears*, never when you answer it, so it infers
the answer from tools having run. That arrives when the tool batch finishes — so
approving one slow command (a long build, a full test run) can let the repeat
fire before the evidence lands.

Raise `escalate_after` past your slowest routine command. The log shows which
happened:

```
session a1b2c3d4 answered its prompt; repeat cancelled
escalating session a1b2c3d4 -> earcon=needs_you speech=True
```

## It says a project name before everything

That's deliberate, and it only happens when more than one session is live in
more than one project — otherwise the name would tell you nothing you don't
already know. It's there so a prompt heard from another room says which terminal
to walk back to.

The log line for each event records what it decided:

```
perm focus=unfocused label=daedalus -> earcon=needs_you speech=True
perm focus=unfocused label=-        -> earcon=needs_you speech=True
```

`label=-` means it saw no reason to name anything. If you're seeing a name with
only one session open, a second one is still counted as live — a session stops
counting 15 minutes after its last activity.

## A setting in `~/.daedalus.toml` seems to do nothing

Run `daedalus doctor`. Anything it couldn't apply is listed under **ignored in
your config file**, with the reason — most often a misspelled key, or a number
written as a string (`min_turn_seconds = "10"` rather than `min_turn_seconds =
10`).

Remember that changes apply when the daemon next starts, which means your next
Claude Code session. See [configuration.md](configuration.md).

## Too noisy

Raise `min_turn_seconds` in `~/.daedalus.toml` before changing anything else.
The default of 3 is conservative; 10 or 30 is a reasonable setting for a busy
day. See [configuration.md](configuration.md).

Then try `pack = "soft"`, which is the same gestures quieter and an octave down.

## Stopping the daemon

It exits with your last Claude Code session. To stop it now:

```bash
# macOS / Linux
pkill -f "daedalus.cli serve"
```

```powershell
# Windows
Get-NetTCPConnection -LocalPort 47113 -State Listen |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

It will start again with your next session.

## Several sessions, one daemon

That's by design. Each session tries to start one; the first binds port 47113
and the rest exit immediately. Audio stays coordinated across every session
instead of three processes talking over each other. The log records
`daemon already running on port 47113; exiting` for the ones that stood down.

## Nothing happens on any event

Check the hooks are actually loaded:

```bash
claude plugin details daedalus
```

The component inventory should list **Hooks (6)** and **Skills (5)** — the five
commands load as skills. Monitors aren't shown in the inventory at all, so don't
read their absence as a problem; `daedalus doctor` is what tells you whether the
daemon came up. If the hooks are missing, the plugin is installed but not enabled
— `claude plugin list` shows its status.

If hooks are loaded and the daemon is up but the log stays empty, the launcher
probably can't find Python. The launchers exit quietly on purpose, so this looks
exactly like nothing happening.

Installed plugins live under `~/.claude/plugins/`. Find the launcher and run it
directly — it should print the doctor report:

```bash
~/.claude/plugins/**/daedalus/bin/daedalus doctor
```

If it prints nothing at all, no interpreter was found. Set `DAEDALUS_PYTHON` to
the full path of your Python and try again:

```bash
DAEDALUS_PYTHON=/usr/bin/python3.12 daedalus doctor
```

On Windows, set it in your environment variables rather than inline.

## Reporting a bug

Please include:

1. The full output of `daedalus doctor`.
2. The relevant lines from `~/.daedalus/daedalus.log`, which state the reason
   for every decision.
3. Your OS, and on Linux whether you're on X11 or Wayland.
4. What you expected to hear, and what you heard instead.
