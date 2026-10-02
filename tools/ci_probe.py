"""Resolve the real platform backends and print what was chosen.

The test suite runs entirely on fakes, so nothing else exercises the actual
ctypes calls, ``shutil.which`` probes and subprocess lookups. This catches an
import error or a broken probe on a platform the author doesn't run.

A CI runner legitimately has no sound card and no window manager, so a ``null``
backend is a pass here. Only a raised exception is a failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "daedalus" / "src"))

from daedalus.backends import Backends
from daedalus.backends.focus import ancestors
from daedalus.config import Config
from daedalus.policy import Event, Focus, Kind, decide


def main() -> int:
    print(f"platform: {sys.platform}, python {sys.version.split()[0]}")

    backends = Backends.resolve()
    print("backends:")
    print(backends.report())

    # Process ancestry uses ctypes on Windows and /proc or ps elsewhere, so it
    # is worth proving on every platform.
    import os

    chain = ancestors(os.getpid())
    print(f"ancestry: {chain}")
    assert chain and chain[0] == os.getpid(), "ancestry must start at this process"

    # The real focus backend must answer without raising, whatever it answers.
    from daedalus.backends.focus import classify

    focus = classify(backends.focus, chain)
    print(f"focus:    {focus.value}")

    # And a decision must still come out the other side.
    decision = decide(
        Event(Kind.PERM, None, "run npm install?"),
        focus=Focus.UNKNOWN,
        config=Config(),
        muted=False,
    )
    print(f"decision: earcon={decision.earcon} speech={bool(decision.speech)} ({decision.reason})")
    assert decision.earcon == "needs_you"

    print("\nok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
