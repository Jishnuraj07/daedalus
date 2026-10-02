"""Generate the default Daedalus earcon pack as 16-bit mono WAV files.

Dev-only tool. The generated .wav files are committed, so nothing here runs at
install time and the runtime stays stdlib-only. Run it after changing a tone:

    python tools/build_sounds.py

Design notes, since these are sounds someone hears a few hundred times a day:

- Struck, not beeped. Each note gets an exponential decay rather than a flat
  envelope, which reads as a plucked or struck object instead of an alarm.
- A couple of quiet harmonics on top of the fundamental, for a little warmth.
- Notes in a gesture overlap and ring into each other, so a two-note earcon
  lands as one event rather than two beeps.
- Deliberately quiet. Peak amplitudes sit well under full scale; raising the
  system volume is the user's call, and a loud default is the fastest way to
  make someone uninstall this.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

RATE = 44100
ATTACK = 0.004  # seconds; long enough to avoid a click, short enough to feel instant

# Fundamental plus two quiet partials. More than this starts to sound like an organ.
HARMONICS = ((1.0, 1.0), (2.0, 0.28), (3.0, 0.09))

# Equal-tempered pitches used below.
A3 = 220.00
C5 = 523.25
E5 = 659.25


def render_note(freq: float, dur: float, amp: float, decay: float) -> list[float]:
    """One struck note: harmonic stack under an attack ramp and exponential decay."""
    out = []
    total = int(dur * RATE)
    attack = max(1, int(ATTACK * RATE))
    for i in range(total):
        t = i / RATE
        env = math.exp(-decay * t)
        if i < attack:
            env *= i / attack
        sample = sum(level * math.sin(2 * math.pi * freq * mult * t) for mult, level in HARMONICS)
        out.append(amp * env * sample / sum(level for _, level in HARMONICS))
    return out


def mix(layers: list[tuple[float, list[float]]]) -> list[float]:
    """Sum notes at their onset offsets (seconds), so they ring into each other."""
    length = max(int(at * RATE) + len(samples) for at, samples in layers)
    buf = [0.0] * length
    for at, samples in layers:
        start = int(at * RATE)
        for i, s in enumerate(samples):
            buf[start + i] += s
    return buf


def write_wav(path: Path, samples: list[float]) -> None:
    peak = max((abs(s) for s in samples), default=0.0)
    if peak > 1.0:  # only ever scale down; never normalise quiet tones up
        samples = [s / peak for s in samples]
    frames = struct.pack(f"<{len(samples)}h", *(int(max(-1.0, min(1.0, s)) * 32767) for s in samples))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)


def build(gain: float = 1.0, octave: float = 1.0, decay: float = 1.0) -> dict[str, list[float]]:
    """The three earcons: rising = fine, falling = you're needed, low = broken.

    The three parameters are what a pack varies. The *gestures* stay put,
    because the rising/falling/low distinction is the part you actually learn.
    """
    return {
        # Done: two notes rising, quiet and unobtrusive. The one you hear most.
        "done": mix(
            [
                (0.000, render_note(C5 * octave, 0.18, 0.40 * gain, 14.0 / decay)),
                (0.055, render_note(E5 * octave, 0.20, 0.40 * gain, 13.0 / decay)),
            ]
        ),
        # Needs you: the same interval inverted and louder. Attention, not alarm.
        "needs_you": mix(
            [
                (0.000, render_note(E5 * octave, 0.18, 0.58 * gain, 13.0 / decay)),
                (0.060, render_note(C5 * octave, 0.26, 0.58 * gain, 10.0 / decay)),
            ]
        ),
        # Failed: one low note, slower decay. Unmistakable, never shrill.
        "failed": mix([(0.0, render_note(A3 * octave, 0.34, 0.52 * gain, 7.0 / decay))]),
    }


PACKS = {
    "default": {},
    # Same gestures an octave down, quieter and mellower, for anyone who finds
    # the default too present over a long day.
    "soft": {"gain": 0.65, "octave": 0.5, "decay": 1.4},
}


def main() -> None:
    root = Path(__file__).resolve().parent.parent / "plugins" / "daedalus" / "sounds" / "packs"
    for pack, params in PACKS.items():
        out_dir = root / pack
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"{pack}/")
        for name, samples in build(**params).items():
            path = out_dir / f"{name}.wav"
            write_wav(path, samples)
            peak = max(abs(s) for s in samples)
            print(f"  {path.name:<14} {len(samples) / RATE * 1000:>4.0f} ms, peak {peak:.2f}")


if __name__ == "__main__":
    main()
