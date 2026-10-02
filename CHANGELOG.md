# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

### Added

- **`/daedalus:doctor` lists anything in your config file it ignored**, with
  what it expected and what it found, so a misspelled key is visible rather
  than a setting that appears not to work. Also logged at daemon start.

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

[Unreleased]: https://github.com/Jishnuraj07/daedalus/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Jishnuraj07/daedalus/releases/tag/v0.1.0
