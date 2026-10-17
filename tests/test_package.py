"""The skill package, for marketplaces that take a SKILL.md zip.

Users unzip it into ``~/.claude/skills/``, where Claude Code loads a directory
holding ``.claude-plugin/plugin.json`` as a full plugin. These pin the ways a
package can be wrong while every file in it still looks fine.
"""

import importlib.util
import json
import py_compile
import re
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "daedalus"
TOOL = ROOT / "tools" / "package_skill.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("package_skill", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def package(tmp_path_factory):
    # Make sure there is bytecode to leave out, rather than relying on whether
    # this run happened to write any.
    py_compile.compile(str(PLUGIN / "src" / "daedalus" / "__init__.py"))
    out = tmp_path_factory.mktemp("dist")
    subprocess.run([sys.executable, str(TOOL), "--out", str(out)], check=True, capture_output=True)
    (zip_path,) = out.glob("*.zip")
    return zipfile.ZipFile(zip_path)


@pytest.fixture(scope="module")
def meta():
    return load_tool().frontmatter(PLUGIN / "SKILL.md")


class TestSkillMd:
    def test_name_follows_the_spec(self, meta):
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", meta["name"])
        assert len(meta["name"]) <= 64

    def test_name_matches_its_directory(self, meta):
        """The spec requires it, and it's how the unzipped folder is named."""
        assert meta["name"] == PLUGIN.name

    def test_name_matches_the_plugin_manifest(self, meta):
        """Two names for one thing drift; this keeps them one."""
        manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text("utf-8"))
        assert meta["name"] == manifest["name"]

    def test_field_lengths(self, meta):
        assert 0 < len(meta["description"]) <= 1024
        assert len(meta.get("compatibility", "")) <= 500

    def test_it_never_claims_to_work_outside_claude_code(self, meta):
        """Skill marketplaces advertise cross-agent support. Daedalus is hooks
        and a monitor, which only Claude Code loads -- on any other agent it does
        nothing at all, so the listing must say so."""
        assert "Claude Code only" in meta["compatibility"]

    def test_it_discloses_what_it_runs(self):
        """Marketplace scans look for commands and network access; the file
        should declare both before a scanner has to find them."""
        body = (PLUGIN / "SKILL.md").read_text("utf-8")
        assert "127.0.0.1" in body, "the only socket it opens"
        assert "No external network access" in body


class TestPackage:
    def test_one_top_level_folder_named_after_the_skill(self, package):
        assert {n.split("/")[0] for n in package.namelist()} == {"daedalus"}

    def test_skill_md_sits_directly_inside_it(self, package):
        assert "daedalus/SKILL.md" in package.namelist()

    def test_the_plugin_manifest_ships(self, package):
        """Without it, ~/.claude/skills/ loads a skill and none of the hooks."""
        assert "daedalus/.claude-plugin/plugin.json" in package.namelist()
        assert "daedalus/hooks/hooks.json" in package.namelist()
        assert "daedalus/monitors/monitors.json" in package.namelist()

    def test_no_bytecode(self, package):
        """Compiled bytecode is what a scan reads as obfuscated code."""
        assert not [n for n in package.namelist() if n.endswith((".pyc", ".pyo")) or "__pycache__" in n]

    def test_the_launcher_stays_executable(self, package):
        """Every hook runs bin/daedalus directly; without the bit, every event fails."""
        mode = package.getinfo("daedalus/bin/daedalus").external_attr >> 16
        assert mode & stat.S_IXUSR

    def test_everything_the_plugin_needs_is_there(self, package):
        shipped = {n.removeprefix("daedalus/") for n in package.namelist()}
        for need in ("bin/daedalus", "bin/daedalus.cmd", "src/daedalus/speakd.py",
                     "sounds/packs/default/done.wav", "commands/say.md"):
            assert need in shipped, need
