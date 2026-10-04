# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] - 2026-10-04

Reported from real use: *"`/daedalus:say` just says spoken and doesn't do
anything."* Three faults of ours combined to produce that, and all three are
fixed here. Nothing else changes.

### Fixed

- **`say` and `test` no longer claim to have made a sound they couldn't.** With
  no speech backend on the machine, `daedalus say` discarded the text and still
  replied `speaking`; `daedalus test` reported `played done, needs_you, failed`
  with no audio backend at all. Reporting a sound that cannot be made is worse
  than making none — it sends you to check your speakers instead of your PATH.
  Both now name the missing backend and what to install.

- **`/daedalus:say` surfaces that message instead of hiding it.** The command
  told Claude to reply with "a short confirmation", so a session reported
  "Spoken." whatever the CLI actually printed — including a failure. It now
  passes the real result through, verbatim when it isn't a success.

- **`/daedalus:say <text>` speaks the text you give it.** The shell command
  always accepted an argument; the slash command ignored one and read the last
  reply regardless, so asking for something specific silently did something
  else. Given text it now speaks that, word for word, and falls back to
  summarising the last reply when called bare.

## [0.3.0] - 2026-10-03

A release about the moments Daedalus actually speaks: which session it's talking
about, and whether it should be speaking at all.

The permission repeat changes for everyone — it no longer fires once you've
approved, and when it does fire it says what it's waiting for instead of playing
a bare tone. Naming the project only shows up if you run more than one session
at a time, which is when it starts to matter.

### Fixed

- **The permission repeat no longer fires after you've approved.** Only the turn
  ending or a new prompt used to cancel it, so approving a prompt and letting
  the agent work on for a few minutes still produced a "you're blocked" tone
  when nothing was blocked — a false alarm in the one signal the product exists
  to make trustworthy.

  Nothing tells Daedalus that a prompt was answered, so it now infers it from
  `PostToolBatch`: if a batch of tool calls resolved, the session is working.
  That hook makes no sound of its own and skips the process walk the others pay
  for, since it is by far the most frequent one.

  One case remains, and can't be closed with the signals available: approving a
  *single* tool that then runs for longer than `escalate_after` means the
  evidence arrives after the repeat. `docs/configuration.md` says so.

### Added

- **The repeat now says what it's still waiting for.** *"still waiting. run npm
  install?"* rather than a bare tone. It fires at the one moment we know for
  certain you missed the first announcement, and it was the moment that said the
  least.

  It is re-decided against fresh focus rather than replayed, so it obeys the
  same rules as everything else: back at the screen half a minute later, and you
  get the tone alone.

- **Speech names the project when more than one session is live.** *"daedalus,
  run npm install?"* rather than *"run npm install?"*, so a prompt heard from
  another room tells you which terminal to go back to. The README sells one
  daemon serving every session, but what that daemon said was ambiguous across
  them.

  It stays quiet about it when naming wouldn't help: a single session needs no
  introduction, and several sessions in the *same* project can't be told apart
  by name, so the label is suppressed rather than spoken to no purpose. A
  session idle for more than 15 minutes stops counting, so a window you've
  forgotten doesn't make every other session's speech longer.

  The name is the basename of `cwd`, which every hook payload already carries,
  with separators read as spaces (`my_api-v2` → "my api v2"). No model, no
  added latency, consistent with everything else Daedalus says.

## [0.2.0] - 2026-10-02

A maintenance release. Five bugs, all found by re-reading the 0.1.0 code rather
than from reports. Four of them need a mistake in `~/.daedalus.toml` to reach,
so on a valid config the one change you'll notice is that mute now also
silences a repeat it had already scheduled.

### Added

- **`/daedalus:doctor` lists anything in your config file it ignored**, with
  what it expected and what it found, so a misspelled key is visible rather
  than a setting that appears not to work. The same lines are logged when the
  daemon starts.

### Fixed

- **A bad value in `~/.daedalus.toml` no longer breaks the daemon.** Every
  setting is checked as it's read: a seconds field holding a string used to
  raise on the next decision, and a non-string `pack` stopped the daemon at
  startup. Bad values now fall back to the default.
- **Mute cancels a repeat already scheduled.** Muting in response to the first
  permission tone still got you the escalation tone ~30s later, which broke the
  rule that `/daedalus:mute` always works.
- **A `pack` name can no longer resolve outside `sounds/packs/`.** It must be a
  single directory name; a path silently found no earcons and went quiet.
  Rejected on every platform, since the same config file travels between them.
- **Speech no longer drops text beginning with a dash.** It's passed as an argv
  parameter, and macOS `say` has no `--` terminator, so a leading dash was read
  as an option flag and the utterance was lost.
- **`/daedalus:doctor` no longer claims X11 focus detection works without a
  `DISPLAY`.** Installed `xprop` with no display — the usual case over SSH —
  reports why instead.

## [0.1.0] - 2026-10-02

First release. Makes a Claude Code session audible when it's waiting on you, and
silent otherwise.

### Added

- **Three earcons** — rising for a finished turn, falling for needs-you, one low
  note for a failure. Generated from the standard library; no numpy.
- **Speech for blocked states only** — a permission prompt speaks the real
  command (*"run npm install?"*, not *"permission for Bash"*), a trailing
  question is read verbatim, and a failure is named in plain words.
- **Focus awareness** — a focused terminal never speaks, because you can already
  see the screen. Replaces wake words and mode toggles with something that needs
  no configuration.
- **Six smoothness rules** — short turns are silent, focused never speaks, one
  sound at a time with priority preemption, escalate once then never again,
  flush on new input, and a persistent mute.
- **Self-starting daemon**, declared as a Claude Code monitor: up with the
  session, down with it. One per machine, so several sessions share coordinated
  audio rather than talking over each other.
- **Commands** — `/daedalus:doctor`, `:test`, `:mute`, `:unmute`, `:say`.
- **Two sound packs** — `default` and `soft`.
- **Three platforms** — Windows, macOS, Linux, each on backends already present
  on the system. Conservative mode where focus can't be read, including Wayland.
- Configuration via `~/.daedalus.toml`; every setting optional.

### Notes

- **No dependencies at all**, dev included. Standard library Python plus tools
  that ship with the OS.
- **No model is ever called.** Zero cost, no added latency, and nothing that can
  mangle your content.
- Replies are never narrated, by design — the screen already renders them. Use
  `/daedalus:say` for the on-demand case.
- Python 3.11+ for `~/.daedalus.toml` support; 3.10 runs on defaults.

[0.3.1]: https://github.com/Jishnuraj07/daedalus/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/Jishnuraj07/daedalus/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Jishnuraj07/daedalus/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Jishnuraj07/daedalus/releases/tag/v0.1.0
