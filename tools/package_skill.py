"""Package the plugin as a skill zip, for marketplaces that take SKILL.md uploads.

Some marketplaces, Agensi among them, distribute skills as a zip that users
unzip into ``~/.claude/skills/``. Claude Code loads a directory there that holds
a ``.claude-plugin/plugin.json`` as a full plugin -- hooks and monitor included
-- so the same tree works as both a plugin and a skill upload.

Two things go wrong when this is zipped by hand, and both are handled here:

- ``__pycache__`` gets swept in. Compiled bytecode is what a security scan reads
  as obfuscated code, and it is machine-specific besides.
- the executable bit is dropped. Every hook runs ``bin/daedalus`` directly, so a
  launcher unzipped without it fails on every event.

The checks before writing mirror the Agent Skills spec and the marketplace's
stated scan, so a rejection shows up here instead of after an upload.

    python tools/package_skill.py               # writes dist/daedalus-<version>.zip
    python tools/package_skill.py --out DIR
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "daedalus"

SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
SKIP_NAMES = {".DS_Store", "Thumbs.db"}
MAX_FILE_BYTES = 1_000_000  # nothing in the plugin comes close; anything that does is a mistake
NAME_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text("utf-8")
    if not text.startswith("---\n"):
        raise SystemExit(f"{path.name}: must open with YAML frontmatter")
    block = text[4:].split("\n---", 1)[0]
    # Flat "key: value" lines are all this file uses; a YAML parser would be a dependency.
    pairs = (line.split(": ", 1) for line in block.splitlines() if ": " in line and not line.startswith(" "))
    return dict(pairs)


def check(files: list[Path]) -> str:
    """Fail loudly on anything the spec or the scan would reject; return the name."""
    meta = frontmatter(PLUGIN / "SKILL.md")
    name = meta.get("name", "")
    problems = []
    if not NAME_RE.fullmatch(name) or len(name) > 64:
        problems.append(f"name {name!r} must be lowercase letters, digits and single hyphens, max 64")
    if name != PLUGIN.name:
        problems.append(f"name {name!r} must match its directory, {PLUGIN.name!r}")
    if not 0 < len(meta.get("description", "")) <= 1024:
        problems.append("description must be 1-1024 characters")
    if len(meta.get("compatibility", "")) > 500:
        problems.append("compatibility must be at most 500 characters")
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    if manifest["name"] != name:
        problems.append(f"SKILL.md name {name!r} differs from plugin.json name {manifest['name']!r}")
    for f in files:
        if f.stat().st_size > MAX_FILE_BYTES:
            problems.append(f"{f.relative_to(PLUGIN)} is {f.stat().st_size} bytes")
    if problems:
        raise SystemExit("not packaged:\n  " + "\n  ".join(problems))
    return name


def collect() -> list[Path]:
    keep = []
    for f in sorted(PLUGIN.rglob("*")):
        rel = f.relative_to(PLUGIN)
        if not f.is_file() or SKIP_DIRS.intersection(rel.parts):
            continue
        if f.suffix in SKIP_SUFFIXES or f.name in SKIP_NAMES:
            continue
        keep.append(f)
    return keep


def main(argv: list[str]) -> int:
    out_dir = Path(argv[argv.index("--out") + 1]) if "--out" in argv else ROOT / "dist"
    files = collect()
    name = check(files)
    version = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text("utf-8"))["version"]

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{name}-{version}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            # One top-level folder named after the skill, SKILL.md directly inside it.
            info = zipfile.ZipInfo.from_file(f, arcname=f"{name}/{f.relative_to(PLUGIN).as_posix()}")
            info.compress_type = zipfile.ZIP_DEFLATED
            # from_file already records the mode; say so explicitly, since losing
            # it is the failure that matters.
            info.external_attr = (f.stat().st_mode & 0xFFFF) << 16
            zf.writestr(info, f.read_bytes())

    print(f"wrote {target.relative_to(ROOT) if target.is_relative_to(ROOT) else target}")
    print(f"  {len(files)} files, {target.stat().st_size:,} bytes, top-level folder {name}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
