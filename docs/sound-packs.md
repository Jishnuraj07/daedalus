# Sound packs

A pack is a directory with three WAV files and a description. Adding one is the
easiest useful contribution to Daedalus, and new packs are welcome.

```
plugins/daedalus/sounds/packs/<name>/
├── pack.json
├── done.wav         rising, or otherwise "fine"
├── needs_you.wav    falling, or otherwise "you're required"
└── failed.wav       low, or otherwise "broken"
```

Select it with `pack = "<name>"` in `~/.daedalus.toml`.

## `pack.json`

```json
{
  "name": "my-pack",
  "description": "One line on what it sounds like and who it's for.",
  "author": "your-handle",
  "license": "MIT"
}
```

`name` must match the directory name.

## Audio requirements

- **WAV, mono, 16-bit.** The Windows player is `winsound`, which is the
  strictest of the three backends; anything else risks silence there.
- **Peak below 0.75 of full scale.** Enforced by the test suite. A loud pack is
  the fastest way to get the plugin uninstalled, and people hear these hundreds
  of times a day.
- **Short.** Under about 400 ms. The daemon assumes a tone is done after 400 ms
  when deciding whether a new sound can preempt it; much longer and a `done`
  will cut off mid-ring.

## Keep the three gestures distinguishable

This matters more than how nice they sound. The point of an earcon is that after
a week you stop consciously hearing it and still know what happened — and that
only works if the three are unmistakable from each other **across the room,
while you're thinking about something else**.

The shipped packs use pitch direction, because it survives bad speakers and
background noise: **rising** = fine, **falling** = you're needed, **one low
note** = broken. You don't have to use pitch, but do use *something* structural.
Three sounds that differ only in timbre, or only in volume, won't work.

Test yours properly: run `/daedalus:test`, then go and do something else for an
afternoon and see whether you can still tell them apart without thinking.

## Generating a pack with the bundled tool

`tools/build_sounds.py` generates the two shipped packs with nothing but the
standard library — `math`, `struct` and `wave`, no numpy. If a variation on the
default suits you, add an entry to `PACKS`:

```python
PACKS = {
    "default": {},
    "soft": {"gain": 0.65, "octave": 0.5, "decay": 1.4},
    "mine": {"gain": 0.8, "octave": 2.0},
}
```

Then `python tools/build_sounds.py`. The three parameters vary gain, pitch and
decay length; the gestures stay fixed, since those are the part people learn.

For something further from the default, write the WAVs however you like and drop
them in. Nothing requires them to come from the generator.

## Checking it

```bash
python -m pytest tests/test_manifests.py -q
```

That verifies every pack has all three earcons, that each is mono 16-bit and
readable, that peaks are in range, and that `pack.json` describes it.
