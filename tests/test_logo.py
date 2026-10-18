"""The logo is generated from code, like the sound packs. These keep it that way."""

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "build_logo.py"
ASSETS = ROOT / "assets" / "logo"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("build_logo", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_committed_svgs_are_what_the_generator_writes(tool, tmp_path):
    """A hand edit to an SVG would be lost on the next regeneration, so the
    generator has to stay the source of truth."""
    written = tool.build_svgs(tmp_path)
    for name in written:
        assert (tmp_path / name).read_text("utf-8") == (ASSETS / name).read_text("utf-8"), name


def test_every_svg_is_committed(tool, tmp_path):
    for name in tool.build_svgs(tmp_path):
        assert (ASSETS / name).is_file(), name


def test_the_generator_needs_only_the_standard_library():
    """The project has no dependencies, dev included. The wordmark was outlined
    once and baked in so that regenerating the logo doesn't break that."""
    tree = ast.parse(TOOL.read_text("utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")])
    }
    imported.discard("__future__")
    assert imported <= set(sys.stdlib_module_names), imported - set(sys.stdlib_module_names)


def test_the_wordmark_is_paths_not_text(tool, tmp_path):
    """SVG text renders in whatever fonts the viewer has, which on GitHub is
    rarely Charter."""
    tool.build_svgs(tmp_path)
    for name in ("daedalus-logo.svg", "daedalus-logo-dark.svg"):
        assert "<text" not in (tmp_path / name).read_text("utf-8")


def test_the_pngs_ship_at_every_icon_size():
    for n in (1024, 512, 256, 128, 64, 48, 32, 16):
        assert (ASSETS / f"daedalus-icon-{n}.png").is_file(), n
    assert (ASSETS / "favicon.ico").is_file()
