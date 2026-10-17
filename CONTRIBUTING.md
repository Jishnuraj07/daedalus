# Contributing

Thanks for looking. The easiest useful contribution is a
[sound pack](docs/sound-packs.md) — three WAV files and a description.

## Getting set up

There's nothing to install. Daedalus runs on the Python standard library, so you
only need dev tools:

```bash
git clone https://github.com/Jishnuraj07/daedalus
cd daedalus
python -m pip install pytest ruff
python -m pytest
python -m ruff check .
```

To run your working copy in a real session, point Claude Code at the directory
instead of installing from a marketplace:

```bash
claude --plugin-dir ./plugins/daedalus
```

Validate the manifests before you push:

```bash
claude plugin validate ./plugins/daedalus
claude plugin validate .
```

## Layout

```
plugins/daedalus/
├── hooks/hooks.json       which events fire
├── monitors/monitors.json starts the daemon with the session
├── commands/              the /daedalus:* commands
├── bin/daedalus{,.cmd}    launchers, one per platform family
├── sounds/packs/          the earcons
└── src/daedalus/
    ├── policy.py          silence | tone | speech  <- the product
    ├── extract.py         payload -> spoken string
    ├── speakd.py          daemon: audio slot, timing, escalation
    ├── cli.py             entry point for hooks and commands
    ├── config.py          ~/.daedalus.toml and runtime state
    └── backends/          audio, speech, focus, per platform + fakes
tools/
├── build_sounds.py        regenerates the packs (stdlib only)
└── ci_probe.py            exercises the real backends
```

## How it's built, and why

Three constraints shape everything. Please keep to them:

**Zero dependencies, including dev.** Standard library and tools already on the
OS. This is what makes `claude plugin install` the entire setup, and it's most of
why anyone will try it. A pull request that adds a runtime dependency needs to
clear a high bar.

**No model in the hot path.** Every spoken string is already a human-written
sentence in the hook payload, a static lookup, or one regex away. Daedalus costs
nothing to run and adds no latency. Please don't introduce an API call.

**It must never break a session.** Backends degrade, they don't fail: the
launcher exits 0 when there's no Python, the daemon swallows bad events, a
missing backend falls back to null. A plugin that's quieter than it could be is
fine. One that breaks someone's session because they're on Wayland is not.

## Testing

```bash
python -m pytest          # the whole suite, a couple of seconds
```

Everything runs headless against fake audio, speech and focus backends, so no
sound card or window manager is needed, on any platform.

If you change behaviour, `tests/test_policy.py` is the file to extend. It's a
table of `(event, turn duration, focus, muted) -> silence | tone | speech`, and
it is the product specification in executable form. A behaviour change should be
visible as a diff in that table.

Two tests are worth knowing about before you trip over them:

- `test_logging_never_targets_a_stream` — the daemon runs as a Claude Code
  monitor, and **a monitor's stdout reaches Claude as notifications.** Printing
  anything would quietly pollute every session's context. That's the worst bug
  this project can have, because it's invisible, so logging is file-only and
  asserted.
- `test_all_hooks_are_async` — `async: true` means a hook's stdout is ignored,
  which is what guarantees Daedalus can never answer a permission prompt on your
  behalf. Don't make the `PermissionRequest` hook synchronous.

## Things that are deliberately not configurable

Worth reading before proposing one of these, since each has been considered:

- **Narrating replies.** Your screen renders them better than a speech
  synthesiser can. Compressing them would need a model, latency and money, and
  would risk mangling content. `/daedalus:say` covers the on-demand case.
- **Speaking while the terminal is focused.** If you can see the screen, a tone
  is enough.
- **Sounds for tool calls.** Noise. The screen already shows them.

## Packaging for skill marketplaces

Some marketplaces, such as Agensi, take skills as a zip containing `SKILL.md`
rather than as a plugin marketplace. Build one with:

```bash
python tools/package_skill.py        # writes dist/daedalus-<version>.zip
```

Upload that file as it is. The zip holds one `daedalus/` folder with
`SKILL.md` directly inside it, which is the layout the [Agent Skills
spec](https://github.com/agentskills/agentskills) and Agensi both require — and
because that folder also holds `.claude-plugin/plugin.json`, Claude Code loads it
from `~/.claude/skills/` as the full plugin, hooks and monitor included.

Zipping by hand gets two things wrong that the script handles: it sweeps in
`__pycache__`, which a security scan reads as obfuscated code, and it can drop
the executable bit on `bin/daedalus`, which every hook runs directly. The script
also checks `SKILL.md` against the spec before writing anything, so a rejection
shows up locally rather than after an upload.

Keep `SKILL.md`'s `compatibility` line saying Claude Code only. Skill
marketplaces advertise cross-agent support, and on any other agent Daedalus does
nothing at all.

## Pull requests

- One change per PR.
- `ruff check .` and `pytest` green.
- If it changes what someone hears, say so in the PR and update
  [docs/configuration.md](docs/configuration.md).
- New platform backend? Add it to [docs/platform-support.md](docs/platform-support.md)
  and make sure `tools/ci_probe.py` covers it.
