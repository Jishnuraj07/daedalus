"""Build the Daedalus logo set from code, like tools/build_sounds.py builds the tones.

The mark is a circular labyrinth -- Daedalus built the labyrinth -- drawn as
broken concentric rings, which is also what sound looks like: rings radiating
from a centre tone, with one way out. The exit faces upper right, the same
direction the "done" tone rises. Two short radial walls are what make it a maze
rather than a target.

Three rings stop resolving below about 48px, so icons at 32px and under use a
simplified two-ring mark with the same openings, exit and wall.

Standard library only. The wordmark is Bitstream Charter Bold, outlined once
into the path below so the logo renders identically everywhere without the
font -- GitHub, for one, renders SVG text in whatever fonts the viewer has.
Charter is licensed "for any purpose and without restriction".

    python tools/build_logo.py          # SVGs into assets/logo/
    python tools/build_logo.py --png    # also PNGs and favicon.ico, via a headless Chromium

PNG export needs chrome-headless-shell, the screenshot build Playwright and
Puppeteer install: set CHROME to it, or have it on PATH. Not full Chrome -- its
headless mode keeps room for an invisible toolbar, so a 128px window holds only
40px of page and every icon comes out as a sliver of the right dimensions. Each
PNG is checked after rendering for exactly that. Everything else needs nothing.
"""

from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "logo"

NAVY = "#121A2E"   # the tile, and the wordmark on light backgrounds
GOLD = "#E9B44C"   # the mark -- brass, for a craftsman; 8.8:1 against the navy
PAPER = "#F1ECE2"  # the wordmark on dark backgrounds

C = 256  # every mark is drawn on a 512 canvas, centred here

# Bitstream Charter Bold, "Daedalus", 1000 units per em, baseline at y=0.
WORDMARK = (
    "M321 -671H29V-622L90 -617L106 -601V-70L90 -54L29 -49V0H321C421 0 496 -15 558 -63C639 -125 681 "
    "-217 681 -335C681 -545 553 -671 321 -671ZM238 -615H296C455 -615 532 -524 532 -336C532 -148 455 "
    "-56 296 -56H238Z M1059 -57 1072 0H1250V-44L1197 -49L1184 -63V-322C1184 -450 1137 -499 997 "
    "-499C865 -499 779 -440 779 -383C779 -356 795 -346 825 -346H917V-440C935 -444 950 -446 965 "
    "-446C1031 -446 1060 -414 1060 -342V-312C851 -265 756 -236 756 -121C756 -45 810 9 887 9C941 9 995 "
    "-14 1059 -57ZM1059 -98C1020 -78 988 -68 962 -68C916 -68 888 -97 888 -143C888 -209 941 -235 1059 "
    "-261Z M1751 -124C1693 -87 1639 -69 1586 -69C1487 -69 1425 -137 1425 -252C1425 -253 1425 -254 "
    "1425 -255H1752C1752 -261 1752 -268 1752 -274C1752 -418 1675 -500 1544 -500C1400 -500 1297 -395 "
    "1297 -242C1297 -91 1395 9 1544 9C1614 9 1684 -11 1751 -50ZM1621 -308H1430C1433 -395 1474 -445 "
    "1534 -445C1589 -445 1621 -402 1621 -319C1621 -315 1621 -312 1621 -308Z M2173 -652V-490C2137 -497 "
    "2106 -500 2079 -500C1927 -500 1821 -393 1821 -232C1821 -88 1903 9 2015 9C2066 9 2116 -14 2173 "
    "-56V0H2360V-44L2309 -48L2295 -64V-739H2249L2100 -692V-652ZM2173 -95C2141 -83 2113 -76 2089 "
    "-76C2006 -76 1955 -141 1955 -253C1955 -372 2014 -444 2099 -444C2120 -444 2144 -439 2173 -429Z "
    "M2723 -57 2736 0H2914V-44L2861 -49L2848 -63V-322C2848 -450 2801 -499 2661 -499C2529 -499 2443 "
    "-440 2443 -383C2443 -356 2459 -346 2489 -346H2581V-440C2599 -444 2614 -446 2629 -446C2695 -446 "
    "2724 -414 2724 -342V-312C2515 -265 2420 -236 2420 -121C2420 -45 2474 9 2551 9C2605 9 2659 -14 "
    "2723 -57ZM2723 -98C2684 -78 2652 -68 2626 -68C2580 -68 2552 -97 2552 -143C2552 -209 2605 -235 "
    "2723 -261Z M2947 0H3215V-44L3157 -50L3142 -66V-739H3098L2947 -691V-652H3019V-64L3005 -50L2947 "
    "-44Z M3392 -499 3251 -451V-412H3316V-162C3316 -47 3360 9 3453 9C3506 9 3558 -14 3621 "
    "-55V0H3810V-45L3758 -49L3744 -64V-499H3698L3556 -451V-412H3621V-93C3588 -83 3560 -77 3535 "
    "-77C3466 -77 3440 -111 3440 -189V-499Z M4223 -475C4172 -492 4122 -500 4072 -500C3949 -500 3876 "
    "-437 3876 -351C3876 -291 3914 -256 3988 -219C4066 -180 4120 -170 4120 -116C4120 -72 4089 -44 "
    "4035 -44C4005 -44 3977 -51 3951 -65L3941 -76L3930 -162H3869V-14C3931 3 3986 11 4034 11C4163 11 "
    "4238 -53 4238 -154C4238 -226 4181 -253 4092 -296C4033 -325 3999 -342 3999 -384C3999 -421 4026 "
    "-444 4075 -444C4098 -444 4120 -438 4141 -428L4153 -417L4163 -342H4223Z "
).strip()
WORDMARK_ADVANCE = 4275
CAP_HEIGHT = 672


def _pt(r: float, deg: float) -> tuple[float, float]:
    a = math.radians(deg)  # 0 = east, 90 = south: screen coordinates
    return C + r * math.cos(a), C + r * math.sin(a)


def _ring(r: float, gap_at: float, gap: float) -> str:
    """A ring with one opening, drawn clockwise from one side of the gap to the other."""
    a1, a2 = gap_at + gap / 2, gap_at - gap / 2 + 360
    (x1, y1), (x2, y2) = _pt(r, a1), _pt(r, a2)
    large = 1 if (a2 - a1) % 360 > 180 else 0
    return f"M{x1:.2f} {y1:.2f}A{r:g} {r:g} 0 {large} 1 {x2:.2f} {y2:.2f}"


def _wall(r1: float, r2: float, deg: float) -> str:
    (x1, y1), (x2, y2) = _pt(r1, deg), _pt(r2, deg)
    return f"M{x1:.2f} {y1:.2f}L{x2:.2f} {y2:.2f}"


def _strokes(paths: list[str], width: int, ink: str, dot: int) -> str:
    body = "".join(f'<path d="{p}"/>' for p in paths)
    return (
        f'<g fill="none" stroke="{ink}" stroke-width="{width}" stroke-linecap="round">{body}</g>'
        f'<circle cx="{C}" cy="{C}" r="{dot}" fill="{ink}"/>'
    )


def mark(ink: str) -> str:
    """The full labyrinth: three rings, two walls, the centre tone."""
    r1, r2, r3 = 64, 108, 152
    paths = [
        _ring(r1, 90, 52),    # out of the centre, downwards
        _ring(r2, 270, 40),   # round, and up
        _ring(r3, 315, 34),   # round again, and out to the upper right
        _wall(r1, r2, 50),
        _wall(r2, r3, 230),
    ]
    return _strokes(paths, 22, ink, 26)


def mark_small(ink: str) -> str:
    """Two heavier rings for 32px and under, keeping the exit and a wall."""
    return _strokes([_ring(92, 90, 58), _ring(164, 315, 40), _wall(92, 164, 230)], 38, ink, 40)


def _svg(viewbox: str, body: str, title: str = "Daedalus") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" role="img" aria-label="{title}">'
        f"<title>{title}</title>{body}</svg>\n"
    )


def _tile(body: str) -> str:
    return f'<rect width="512" height="512" rx="112" fill="{NAVY}"/>{body}'


def lockup(text: str) -> tuple[str, int]:
    """Icon and wordmark side by side; returns the SVG and its width."""
    scale = 0.37                 # wordmark caps at about half the tile's height
    x = 512 + 150                # tile, then a gap of roughly a third of it
    baseline = C + CAP_HEIGHT * scale / 2
    width = round(x + WORDMARK_ADVANCE * scale)
    words = (
        f'<path fill="{text}" transform="translate({x} {baseline:.1f}) scale({scale})" d="{WORDMARK}"/>'
    )
    return _svg(f"0 0 {width} 512", _tile(mark(GOLD)) + words), width


def build_svgs(out: Path = OUT) -> dict[str, tuple[int, int]]:
    """Write every SVG; return each one's natural size, for the PNG step."""
    out.mkdir(parents=True, exist_ok=True)
    sizes: dict[str, tuple[int, int]] = {}

    def write(name: str, svg: str, size: tuple[int, int]) -> None:
        (out / name).write_text(svg, "utf-8")
        sizes[name] = size

    write("daedalus-icon.svg", _svg("0 0 512 512", _tile(mark(GOLD))), (512, 512))
    write("daedalus-icon-small.svg", _svg("0 0 512 512", _tile(mark_small(GOLD))), (512, 512))
    # Bare marks, cropped to the rings. Gold reads on dark backgrounds only.
    write("daedalus-mark.svg", _svg("88 88 336 336", mark(GOLD)), (336, 336))
    write("daedalus-mark-ink.svg", _svg("88 88 336 336", mark(NAVY)), (336, 336))
    svg, w = lockup(NAVY)
    write("daedalus-logo.svg", svg, (w, 512))
    svg, w = lockup(PAPER)
    write("daedalus-logo-dark.svg", svg, (w, 512))
    return sizes


def _chrome() -> str | None:
    """chrome-headless-shell, wherever Playwright, Puppeteer or a package put it."""
    candidates = [os.environ.get("CHROME")]
    candidates += [shutil.which(n) for n in ("chrome-headless-shell", "headless_shell")]
    for base in ("/opt/pw-browsers", str(Path.home() / ".cache" / "ms-playwright")):
        candidates += sorted(str(p) for p in Path(base).glob("chromium_headless_shell-*/*/headless_shell"))
    return next((c for c in candidates if c and Path(c).is_file()), None)


def _alpha_at(png: Path, x: int, y: int) -> int:
    """Alpha of one pixel in an 8-bit RGBA PNG -- enough to tell a render from a sliver."""
    data = png.read_bytes()
    w, _, depth, colour = struct.unpack(">IIBB", data[16:26])
    if (depth, colour) != (8, 6):
        raise SystemExit(f"{png.name}: expected 8-bit RGBA")
    pos, idat = 8, b""
    while pos < len(data):
        (n,) = struct.unpack(">I", data[pos : pos + 4])
        if data[pos + 4 : pos + 8] == b"IDAT":
            idat += data[pos + 8 : pos + 8 + n]
        pos += 12 + n
    raw, stride, prev = zlib.decompress(idat), w * 4, bytearray(w * 4)
    for row in range(y + 1):  # unfilter down to the row we need
        start = row * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1 : start + 1 + stride])
        for i in range(stride):
            a = line[i - 4] if i >= 4 else 0
            b, c = prev[i], prev[i - 4] if i >= 4 else 0
            if kind == 1:
                line[i] = (line[i] + a) & 255
            elif kind == 2:
                line[i] = (line[i] + b) & 255
            elif kind == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif kind == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
    return prev[x * 4 + 3]


def _render(chrome: str, svg: Path, png: Path, w: int, h: int, tile_w: int) -> None:
    """Rasterise at the true target size, so small icons are drawn small, not shrunk.

    ``tile_w`` is the rendered width of the navy tile, whose bottom edge must
    come out opaque: if it doesn't, the page was clipped.
    """
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "page.html"
        page.write_text(
            "<!doctype html><style>html,body{margin:0;background:transparent}img{display:block}</style>"
            f'<img src="{svg.as_uri()}" width="{w}" height="{h}">',
            "utf-8",
        )
        subprocess.run(
            [chrome, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
             "--default-background-color=00000000", f"--window-size={w},{h}",
             f"--screenshot={png}", page.as_uri()],
            check=True, capture_output=True, timeout=60,
        )
    if not _alpha_at(png, tile_w // 2, h - 1 - max(1, h // 64)):
        png.unlink()
        raise SystemExit(
            f"{png.name} rendered clipped -- this browser's headless mode doesn't give the page "
            "the full window. Use chrome-headless-shell (see the top of this file)."
        )


def _ico(pngs: list[Path], target: Path) -> None:
    """A favicon.ico holding PNG images -- the format every current browser reads."""
    blobs = [p.read_bytes() for p in pngs]
    head = struct.pack("<HHH", 0, 1, len(blobs))
    offset, entries = 6 + 16 * len(blobs), b""
    for blob in blobs:
        w, h = struct.unpack(">II", blob[16:24])
        entries += struct.pack("<BBBBHHII", w % 256, h % 256, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    target.write_bytes(head + entries + b"".join(blobs))


def build_pngs() -> None:
    chrome = _chrome()
    if not chrome:
        raise SystemExit("--png needs Chromium or Chrome: set CHROME, or put one on PATH")
    icon, small = OUT / "daedalus-icon.svg", OUT / "daedalus-icon-small.svg"
    for n in (1024, 512, 256, 128, 64, 48):
        _render(chrome, icon, OUT / f"daedalus-icon-{n}.png", n, n, n)
    for n in (32, 16):
        _render(chrome, small, OUT / f"daedalus-icon-{n}.png", n, n, n)
    _ico([OUT / f"daedalus-icon-{n}.png" for n in (16, 32, 48)], OUT / "favicon.ico")
    for name in ("daedalus-logo", "daedalus-logo-dark"):
        svg = OUT / f"{name}.svg"
        w = round(float(svg.read_text("utf-8").split('viewBox="0 0 ')[1].split()[0]))
        # 256px tall: crisp in a README. The tile is the first 512 of w units.
        _render(chrome, svg, OUT / f"{name}.png", w // 2, 256, 256)


def main(argv: list[str]) -> int:
    sizes = build_svgs()
    print(f"wrote {len(sizes)} SVGs to {OUT.relative_to(ROOT)}/")
    if "--png" in argv:
        build_pngs()
        print("wrote PNGs and favicon.ico")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
