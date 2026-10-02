"""Recording test doubles.

CI runners have no sound card and no window manager, so the policy and daemon
layers are exercised entirely through these.
"""

from __future__ import annotations

from pathlib import Path


class FakeAudio:
    name = "fake"

    def __init__(self) -> None:
        self.played: list[str] = []
        self.stops = 0

    @staticmethod
    def probe() -> tuple[bool, str]:
        return True, "fake"

    def play(self, path: Path) -> None:
        self.played.append(Path(path).stem)

    def stop(self) -> None:
        self.stops += 1


class FakeSpeech:
    name = "fake"

    def __init__(self) -> None:
        self.said: list[str] = []
        self.stops = 0

    @staticmethod
    def probe() -> tuple[bool, str]:
        return True, "fake"

    def say(self, text: str) -> None:
        self.said.append(text)

    def stop(self) -> None:
        self.stops += 1


class FakeFocus:
    """Pretends a given PID owns the foreground window. ``None`` means unknown."""

    name = "fake"

    def __init__(self, pid: int | None = None) -> None:
        self.pid = pid

    @staticmethod
    def probe() -> tuple[bool, str]:
        return True, "fake"

    def foreground_pid(self) -> int | None:
        return self.pid
