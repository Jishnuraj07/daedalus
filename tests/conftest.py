import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "plugins" / "daedalus" / "src"
sys.path.insert(0, str(SRC))

PACK = Path(__file__).resolve().parent.parent / "plugins" / "daedalus" / "sounds" / "packs" / "default"


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Keep every test off the real ``~/.daedalus``.

    ``config.home()`` honours DAEDALUS_HOME, so state writes and config reads
    land in a temp directory instead of the developer's own setup.
    """
    monkeypatch.setenv("DAEDALUS_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def pack_dir():
    return PACK
