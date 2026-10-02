# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.0]: https://github.com/Jishnuraj07/daedalus/releases/tag/v0.1.0
