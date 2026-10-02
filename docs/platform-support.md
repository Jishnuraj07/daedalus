# Platform support

Every backend is something already present on the platform. That's the whole
reason Daedalus installs with no dependencies: there is nothing to build and
nothing to fetch.

| | Tones | Speech | Focus |
| :- | :- | :- | :- |
| **Windows** | `winsound` (stdlib) | System.Speech via PowerShell | `GetForegroundWindow` via ctypes |
| **macOS** | `afplay` | `say` | `osascript` |
| **Linux / X11** | `paplay`, else `aplay` | `spd-say`, else `espeak` | `xprop` |
| **Linux / Wayland** | `paplay`, else `aplay` | `spd-say`, else `espeak` | **unavailable** |

Python 3.11 or newer. Daedalus runs on 3.10 but ignores `~/.daedalus.toml`,
since reading it needs `tomllib`.

## Degradation is a feature, not an afterthought

Nothing hard-fails when a backend is missing, because the alternative — a plugin
that breaks your session because you're on Wayland — is much worse than one
that's a bit quieter than it could be.

- **No focus backend** → **conservative mode.** Tones work normally. Speech
  fires only for hard-blocked states: permission prompts and failures. A
  trailing question gets a tone rather than being read out, since Daedalus can't
  tell whether you're already looking at it.
- **No speech backend** → every tone still plays. You lose the detail, not the
  signal.
- **No audio backend** → everything still runs and decides; nothing is heard.
  `doctor` tells you why.
- **No Python** → the launcher exits 0 silently, and your session behaves
  exactly as if the plugin weren't installed. A hook that fails loudly is worse
  than one that stays quiet.

`/daedalus:doctor` always names the chosen backend and the reason, including why
a better one wasn't available.

## Per-platform notes

### Windows

Everything works out of the box. `winsound` and `ctypes` are standard library,
and System.Speech ships with Windows.

Speech costs a PowerShell start, a few hundred milliseconds before the first
word. That's acceptable here because speech only fires when you're away from the
screen, and the tone plays immediately either way.

### macOS

Everything works out of the box, and `say` is the best-sounding of the three
speech backends by some distance.

If focus detection fails, check that your terminal has Automation permission
under System Settings → Privacy & Security — `osascript` needs it to ask which
application is frontmost.

### Linux

Audio generally works out of the box; `paplay` comes with PulseAudio or
PipeWire. For the rest:

```bash
sudo apt install x11-utils          # focus detection (xprop)
sudo apt install speech-dispatcher  # speech (spd-say)
```

**Wayland cannot report the focused window** to an ordinary client — there is no
API for it by design, and no workaround. Daedalus runs in conservative mode
there. Tones are unaffected, and permission prompts and failures still speak.

### SSH, containers, cloud sessions

There's no local audio device and no window, so Daedalus has nothing to work
with. It resolves to null backends, stays silent, and doesn't interfere.

This is also true of `/voice`, which doesn't work over SSH either.

## Adding a platform or a backend

Each concern is one small module under
`plugins/daedalus/src/daedalus/backends/`, and each backend is a class with a
`probe()` returning `(available, reason)` plus one or two methods. Add a class,
add it to that module's resolver, and the policy layer is untouched.

The `reason` string is part of the contract, not a debug aid — it's what
`doctor` prints, and for a cross-platform plugin that string is the difference
between a useful bug report and a guess.

Tests run against fakes, so they don't need your platform. `tools/ci_probe.py`
exercises the real backends and runs on every OS in CI.
