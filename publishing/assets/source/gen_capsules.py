#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Steam capsule and library art for Conversation Simulator — full game and demo.

v3 (Valve store-presence review, Jul 2026): store capsules may contain ONLY
game artwork + the game name, and library assets only the game title
(https://partner.steamgames.com/doc/store/assets/rules).  The tagline
("The simulator for conversations.") and the OUTRIGHT MENTAL publisher
wordmark were removed from header_capsule, main_capsule, vertical_capsule,
and library_header; compositions re-centred to absorb the removed lines.

v4 (issue #551): two editions, written into the repo.

  full  App 4963030, Conversation Simulator       -> publishing/assets/capsules/
  demo  App 5343430, Conversation Simulator Demo  -> publishing/assets/capsules/demo/

v5: one mark.  The art used to carry a capsule-only drawing — a purple bubble
with typing dots under a green one with text lines — that matched neither the
app icon nor the website.  Every asset now draws the official mark,
docs/assets/brand/mark.svg, through gen_icons.mark_markup(), so the capsules,
the icons and the websites cannot drift apart again.

The demo set is the full game's art with one addition, the same one the demo
icon makes: gen_icons' amber "DEMO" badge, pinned to the lower-right corner of
every asset Valve lets carry the name (``BADGED`` below).  "Demo" is part of
this app's name, so it stays inside the artwork-plus-name rule.  Per asset:

  * header, small, main, vertical, library_capsule, library_header: the full
    game's art plus the badge.
  * library_hero: the full game's, unchanged.  Valve's library hero takes no
    text or logo (Steam lays the library logo over it), so no badge.
  * library_logo: the full game's, unchanged: it has no corner of its own, and
    the library shows the app's name beside it.
  * page_background: not drawn.  It is optional and Valve wants it ambient
    and textless; the full game's is the right file if the demo ever needs one.
  * community icon: not drawn here, for either edition.  The App Icon and the
    Shortcut Icon come from gen_icons.py — publishing/assets/icons/.

The hero and the logo are therefore byte-identical in both directories.  They
are still written to demo/ so that it holds the demo app's complete upload set.

Regenerating
------------
    python3 publishing/assets/source/gen_capsules.py                  # full, into the repo
    python3 publishing/assets/source/gen_capsules.py --edition demo   # demo, into the repo
    python3 publishing/assets/source/gen_capsules.py --edition demo --out /tmp/demo

Default output directories are resolved from this file's location, not the
working directory.  Needs librsvg's ``rsvg-convert`` (Ubuntu ``librsvg2-bin``,
macOS ``brew install librsvg``), ImageMagick (``magick`` or ``convert``) for
reading the render back, and the Carlito font (Ubuntu
``fonts-crosextra-carlito``) for the logotype.

The output is deterministic on one machine but not across librsvg, pango and
font builds: a regeneration on another machine moves anti-aliased edge pixels
without changing the drawing.  Judge a regeneration by eye and by
tests/acceptance/test_demo_branding.py, not by ``git diff``, and do not commit
that churn unless the drawing changed.

Commit what a regeneration adds or changes on purpose, then upload by hand:
each set on its app in Steamworks, Store Presence → Graphical Assets, the
store capsules under Store Assets and the library ones under Library Assets.
The field for each file is tabulated in publishing/STEAM_ASSETS_SPEC.md
(Capsule art → Production) and the demo's steps are in
publishing/STEAM_NEXT_FEST_DEMO.md §4.2.
"""
from __future__ import annotations

import argparse
import functools
import importlib.util
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
CAPSULE_DIR = HERE.parent / "capsules"
DEFAULT_OUT = {"full": CAPSULE_DIR, "demo": CAPSULE_DIR / "demo"}


def _load_gen_icons():
    """gen_icons.py by path: the mark and the badge live there."""
    spec = importlib.util.spec_from_file_location("convsim_gen_icons", HERE / "gen_icons.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ICONS = _load_gen_icons()

# ── Palette ────────────────────────────────────────────────────────────────
WHITE = "#F4F4F5"
F = "Carlito"
STAGE = "#0d0d15"          # the stage, and the lower 45 % band
STAGE_TOP = "#151522"      # the upper 55 % band, laid over the stage ...
STAGE_TOP_OPACITY = "0.55"  # ... at this opacity


def base(w, h):
    return (f'<rect width="{w}" height="{h}" fill="{STAGE}"/>'
            f'<rect width="{w}" height="{h*0.55:.0f}" fill="{STAGE_TOP}" opacity="{STAGE_TOP_OPACITY}"/>'
            f'<rect y="{h*0.55:.0f}" width="{w}" height="{h*0.45:.0f}" fill="{STAGE}"/>')


def mark(x, y, h):
    """The official mark with its bubbles' bounding box at (x, y), ``h`` px square."""
    return ICONS.mark_at(x, y, h)


def words(cx, y, size):
    """Stacked logotype (game name ONLY — Steam asset rules) at cx; y = baseline of line 1."""
    gap = size * 1.06
    return f'''
  <g text-anchor="middle" font-family="{F}" font-weight="700">
    <text x="{cx}" y="{y}" font-size="{size}" fill="{WHITE}">CONVERSATION</text>
    <text x="{cx}" y="{y+gap:.0f}" font-size="{size}" fill="{WHITE}">SIMULATOR</text>
  </g>'''


def svg(w, h, body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">{base(w,h)}{body}</svg>'


# ── "DEMO" badge ───────────────────────────────────────────────────────────
# The demo icon's badge, sized as if a demo icon BADGE_ICON_SIDE times the
# capsule's geometric-mean side sat in the capsule's lower-right corner: about
# 380 px on the 920 x 430 header, so the pill is 66 px tall there and 30 px on
# the 462 x 174 small capsule.  The geometric mean keeps the badge the same
# visual weight on wide, tall and square assets.
BADGE_ICON_SIDE = 0.6

# Store capsules and the two library capsules carry the game name, so they
# may carry "DEMO".  The hero must stay textless; the logo has no corner.
BADGED = ("header_capsule", "small_capsule", "main_capsule", "vertical_capsule",
          "library_capsule", "library_header")

# Nothing of the composition may come within this fraction of the pill's
# height of the pill.  Checked on every render; see _check_clear.
BADGE_CLEARANCE = 0.25


def badge_box(w: int, h: int) -> "ICONS.Pill":
    """The pill's rectangle on a w x h capsule."""
    side = BADGE_ICON_SIDE * math.sqrt(w * h)
    p = ICONS.badge_box(side)
    return ICONS.Pill(p.x + w - side, p.y + h - side, p.w, p.h)


def badge_svg(w: int, h: int) -> str:
    return ICONS.badge_at(badge_box(w, h))


# ── Jobs ───────────────────────────────────────────────────────────────────
class Job(NamedTuple):
    w: int
    h: int
    body: str            # everything above the stage
    transparent: bool = False


def jobs() -> dict[str, Job]:
    j = {}
    # Header 920x430 — mark left, name right-centre
    j["header_capsule"] = Job(920, 430, mark(78, 92, 246) + words(628, 197, 62))
    # Small 462x174 — mark left, name right
    j["small_capsule"] = Job(462, 174, mark(22, 25, 124) + words(312, 77, 40))
    # Main 1232x706 — mark top-centre, name below
    j["main_capsule"] = Job(1232, 706, mark(476, 84, 280) + words(616, 468, 82))
    # Vertical 748x896
    j["vertical_capsule"] = Job(748, 896, mark(234, 196, 280) + words(374, 590, 68))
    # Library capsule 600x900
    j["library_capsule"] = Job(600, 900, mark(170, 206, 260) + words(300, 590, 56))
    # Library header 920x430 — same as header
    j["library_header"] = j["header_capsule"]
    # Library hero 3840x1240 — pure graphic, no text (Steam overlays the logo)
    j["library_hero"] = Job(3840, 1240, mark(1770, 470, 300))
    # Library logo 1280x720 transparent — mark + words
    j["library_logo"] = Job(1280, 720, mark(500, 40, 280) + words(640, 430, 92),
                            transparent=True)
    # Page background 1438x810 — very subtle
    j["page_background"] = Job(1438, 810,
        f'<g opacity="0.14">{mark(1040, 120, 250)}</g><g opacity="0.09">{mark(190, 440, 180)}</g>')
    return j


EDITION_JOBS = {
    "full": ("header_capsule", "small_capsule", "main_capsule", "vertical_capsule",
             "library_capsule", "library_header", "library_hero", "library_logo",
             "page_background"),
    "demo": ("header_capsule", "small_capsule", "main_capsule", "vertical_capsule",
             "library_capsule", "library_header", "library_hero", "library_logo"),
}


def job_svg(edition: str, name: str, badge: bool | None = None) -> str:
    """The SVG for one asset; ``badge`` defaults to what the edition draws."""
    job = jobs()[name]
    if badge is None:
        badge = edition == "demo" and name in BADGED
    body = job.body + (badge_svg(job.w, job.h) if badge else "")
    if job.transparent:
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {job.w} {job.h}">{body}</svg>'
    return svg(job.w, job.h, body)


# ── Rasterisation ──────────────────────────────────────────────────────────
def _need(cmd: str, hint: str) -> str:
    path = shutil.which(cmd)
    if path is None:
        sys.exit(f"gen_capsules.py needs `{cmd}` on PATH: {hint}")
    return path


@functools.lru_cache(maxsize=1)
def _magick() -> str:
    """`magick` on ImageMagick 7, `convert` on 6 (checked: Windows has a convert.exe)."""
    for candidate in ("magick", "convert"):
        path = shutil.which(candidate)
        if path is None:
            continue
        probe = subprocess.run([path, "-version"], capture_output=True, text=True)
        if "ImageMagick" in probe.stdout:
            return path
    sys.exit("gen_capsules.py needs ImageMagick on PATH (`apt-get install "
             "imagemagick`, `brew install imagemagick`) to encode the PNGs.")


def _check_font() -> None:
    """Fail rather than silently set the logotype in a fallback face."""
    fc_match = shutil.which("fc-match")
    if fc_match is None:
        print("warning: fc-match not found; cannot confirm the Carlito font is "
              "installed", file=sys.stderr)
        return
    family = subprocess.run([fc_match, "-f", "%{family}", f"{F}:bold"],
                            capture_output=True, text=True).stdout
    if F not in family.split(","):
        sys.exit(f"the {F} font is not installed (fontconfig offers {family!r} "
                 "instead); Ubuntu: apt-get install fonts-crosextra-carlito")


def _render(code: str, w: int, h: int, dest: Path) -> None:
    rsvg = _need("rsvg-convert", "Ubuntu `apt-get install librsvg2-bin`, macOS "
                                 "`brew install librsvg`")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.svg"
        src.write_text(code)
        subprocess.run([rsvg, "--width", str(w), "--height", str(h), "--format", "png",
                        "--output", str(dest), str(src)], check=True)


def _pixels(png: Path, w: int, h: int, alpha: bool = False) -> bytes:
    """The PNG's raw 8-bit RGB (or RGBA) samples, row by row, via ImageMagick."""
    fmt = "RGBA" if alpha else "RGB"
    flags = [] if alpha else ["-alpha", "off"]
    raw = subprocess.run([_magick(), "PNG:" + str(png), *flags, "-depth", "8", fmt + ":-"],
                         check=True, capture_output=True).stdout
    assert len(raw) == w * h * len(fmt), f"{png}: expected {w}x{h} {fmt}"
    return raw


def _encode(raw: Path, dest: Path, w: int, h: int, transparent: bool) -> None:
    """Write the render as an 8-bit RGB PNG (RGBA for the logo), by hand.

    No ancillary chunks — no timestamp, no gamma, no profile — so the bytes
    depend on the pixels alone, and every row uses filter type 0.  On flat
    art that costs little against adaptive filtering, and it keeps the files
    readable by the acceptance suite's pure-Python PNG reader at a usable
    speed, even the 3840 x 1240 hero.  ImageMagick is not asked to do this
    because its PNG coder ignores a filter request for truecolour images.
    """
    channels = 4 if transparent else 3
    data = _pixels(raw, w, h, alpha=transparent)
    stride = w * channels
    rows = b"".join(b"\x00" + data[y * stride:(y + 1) * stride] for y in range(h))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6 if transparent else 2, 0, 0, 0)
    dest.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def _hex(colour: str) -> tuple[int, int, int]:
    colour = colour.lstrip("#")
    return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))


def _stage_colours() -> list[tuple[int, int, int]]:
    bg, top, op = _hex(STAGE), _hex(STAGE_TOP), float(STAGE_TOP_OPACITY)
    return [bg, tuple(round(t * op + b * (1 - op)) for t, b in zip(top, bg))]


def _check_clear(name: str, png: Path, w: int, h: int) -> None:
    """Nothing but the stage under the badge, nor within BADGE_CLEARANCE of it.

    Run on a render without the badge, so a mark or a line of the logotype
    that strays into the corner is caught here rather than half hidden under
    the pill, where it is easy to miss by eye.
    """
    raw = _pixels(png, w, h)
    p = badge_box(w, h)
    pad = BADGE_CLEARANCE * p.h
    stage = _stage_colours()
    bad = 0
    for y in range(max(0, int(p.y - pad)), h):
        for x in range(max(0, int(p.x - pad)), w):
            i = (y * w + x) * 3
            px = raw[i:i + 3]
            if min(max(abs(a - b) for a, b in zip(px, c)) for c in stage) > 8:
                bad += 1
    if bad:
        sys.exit(f"{name}: {bad} pixels of artwork lie under the DEMO badge or "
                 "within its clearance; move the composition or shrink "
                 "BADGE_ICON_SIDE")


def build(edition: str, out: Path) -> list[Path]:
    _check_font()
    out.mkdir(parents=True, exist_ok=True)
    table = jobs()
    written = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for name in EDITION_JOBS[edition]:
            job = table[name]
            if edition == "demo" and name in BADGED:
                bare = tmp / f"{name}.bare.png"
                _render(job_svg(edition, name, badge=False), job.w, job.h, bare)
                _check_clear(name, bare, job.w, job.h)
            raw = tmp / f"{name}.png"
            _render(job_svg(edition, name), job.w, job.h, raw)
            dest = out / f"{name}.png"
            _encode(raw, dest, job.w, job.h, job.transparent)
            written.append(dest)
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--edition", choices=tuple(EDITION_JOBS), default="full")
    ap.add_argument("--out", type=Path,
                    help="write here instead of publishing/assets/capsules/ "
                         "(full) or publishing/assets/capsules/demo/ (demo)")
    args = ap.parse_args()
    out = args.out if args.out is not None else DEFAULT_OUT[args.edition]
    for path in build(args.edition, out):
        w, h = struct.unpack(">II", path.read_bytes()[16:24])   # the IHDR
        print(f"{args.edition}: {path}  {w}x{h}  {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
