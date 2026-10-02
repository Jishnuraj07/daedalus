"""Platform backends, resolved once at daemon start.

Each resolver returns the backend plus a human-readable reason, which is what
``/daedalus:doctor`` prints. Most support questions for a cross-platform plugin
are "which backend did it pick, and why not the other one" -- so the reason is
part of the contract, not a debugging afterthought.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import audio, focus, speech


@dataclass
class Backends:
    audio: object
    audio_reason: str
    speech: object
    speech_reason: str
    focus: object
    focus_reason: str

    @classmethod
    def resolve(cls) -> Backends:
        a, a_why = audio.resolve()
        s, s_why = speech.resolve()
        f, f_why = focus.resolve()
        return cls(a, a_why, s, s_why, f, f_why)

    def report(self) -> str:
        return "\n".join(
            [
                f"  audio   {self.audio.name:<10} {self.audio_reason}",
                f"  speech  {self.speech.name:<10} {self.speech_reason}",
                f"  focus   {self.focus.name:<10} {self.focus_reason}",
            ]
        )


__all__ = ["Backends", "audio", "focus", "speech"]
