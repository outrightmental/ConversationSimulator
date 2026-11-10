#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Steam capsule and library art for Conversation Simulator — full game and demo.

v3 (Valve store-presence review, Jul 2026): store capsules may contain ONLY
game artwork + the game name, and library assets only the game title
(https://partner.steamgames.com/doc/store/assets/rules).  The tagline
("The simulator for conversations.") and the OUTRIGHT MENTAL publisher
wordmark were removed from header_capsule, main_capsule, vertical_capsule,
and library_header; compositions re-centred to absorb the removed lines.
Flat fills only, no letter-spacing or gradients.

v4 (issue #551): two editions, written into the repo.

  full  App 4963030, Conversation Simulator       -> publishing/assets/capsules/
  demo  App 5343430, Conversation Simulator Demo  -> publishing/assets/capsules/demo/

The demo app had no artwork of its own, so its library entry and store
presence rendered blank.  Its set is the full game's, changed in three ways
that all come from the demo icon (gen_icons.py), so the capsules and the App
Icon read as one family:

  1. The near-black stage becomes the demo plate, PLATE["demo"] (#6D28D9),
     with the lower 45 % a step darker in the place of the full game's
     slightly darker lower band.
  2. On that plate the player bubble — #6D28D9 in the full game — would
     vanish, so it turns white with plate-coloured dots: the demo icon's own
     mark.  The NPC bubble and the logotype are untouched.
  3. The icon's "DEMO" corner ribbon, from gen_icons.ribbon_shapes(), pinned
     to the capsule's lower-right corner at a size that scales with the
     capsule (RIBBON_ICON_SIDE).  It is drawn only on the assets Valve lets
     carry the name — RIBBONED below — and "Demo" is part of this app's
     name, so it stays inside the artwork-plus-name rule.

Per asset, for the demo:

  * header, small, main, vertical, library_capsule, library_header: plate,
    demo mark, ribbon.
  * library_hero: plate and demo mark only.  Valve's library hero takes no
    text or logo (Steam lays the library logo over it), so no ribbon.
  * library_logo: the same logo, transparent, with the demo mark: it is
    drawn over the demo hero, whose plate would swallow a purple bubble.
    No ribbon and no "DEMO": the library shows the app's name beside it.
  * page_background: not drawn.  It is optional, Valve wants it ambient and
    textless, and on the purple plate it would be neither; the full game's
    near-black one is the right file if the demo ever needs one.
  * community icon: not drawn here, for either edition.  The App Icon and the
    Shortcut Icon come from gen_icons.py — publishing/assets/icons/.

Regenerating
------------
    python3 publishing/assets/source/gen_capsules.py                  # full, into the repo
    python3 publishing/assets/source/gen_capsules.py --edition demo   # demo, into the repo
    python3 publishing/assets/source/gen_capsules.py --edition demo --out /tmp/demo

Default output directories are resolved from this file's location, not the
working directory.  Needs librsvg's ``rsvg-convert`` (Ubuntu ``librsvg2-bin``,
macOS ``brew install librsvg``), ImageMagick (``magick`` or ``convert``) for
the PNG encoding, and the Carlito font (Ubuntu ``fonts-crosextra-carlito``).
rsvg-convert is called by name because the drawing needs it: it is what
ImageMagick hands SVG to when librsvg is present, it is what produced the
committed full-edition set, and ImageMagick's own MSVG renderer — what you
get without librsvg — ignores the group transforms the mark is placed with.

The output is deterministic on one machine but not across librsvg, pango and
font builds: a regeneration moves anti-aliased edge pixels without changing
the drawing.  On Ubuntu 24.04's librsvg 2.58 the committed header, main,
vertical and library_header capsules come back with 43-77 pixels outside a
2 % tolerance, all on anti-aliased edges, and about 2,800 that differ by a
level or two (the committed files are palette-quantised).  So judge a
regeneration by eye and by
tests/acceptance/test_demo_branding.py, not by ``git diff``, and do not
commit that churn unless the drawing changed.  The committed
small_capsule.png predates this script's small_capsule job, which now
reproduces its composition rather than its exact pixels; leave it alone for
the same reason.

Commit what a regeneration adds or changes on purpose, then upload by hand:
the demo set on App 5343430 in Steamworks, Store Presence → Graphical
Assets, the store capsules under Store Assets and the library ones under
Library Assets.  The field for each file is tabulated in
publishing/STEAM_ASSETS_SPEC.md (Capsule art → Production) and the demo's
steps are in publishing/STEAM_NEXT_FEST_DEMO.md §4.2.
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
    """gen_icons.py by path: the demo plate colour and the ribbon live there."""
    spec = importlib.util.spec_from_file_location("convsim_gen_icons", HERE / "gen_icons.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ICONS = _load_gen_icons()

# ── Palette ────────────────────────────────────────────────────────────────
GRN = "#15803D"
WHITE = "#F4F4F5"
F = "Carlito"


# NamedTuples rather than dataclasses: the acceptance suite imports this file
# by path, without a sys.modules entry, which @dataclass cannot resolve.
class Palette(NamedTuple):
    bg: str            # the stage; also the lower 45 % band
    bg_top: str        # the upper 55 % band, laid over bg at top_opacity
    top_opacity: str
    player: str        # player bubble body and tail
    player_hi: str     # its highlight strip ...
    player_hi_opacity: str  # ... at this opacity
    player_dot: str    # its three typing dots


PALETTES = {
    "full": Palette(bg="#0d0d15", bg_top="#151522", top_opacity="0.55",
                    player="#6D28D9", player_hi="#7E3BF2", player_hi_opacity="0.6",
                    player_dot="#ffffff"),
    # The upper band is the icon plate exactly, and the larger of the two, so
    # the plate is the dominant colour of every demo capsule — the cue that
    # separates the two library entries at a glance, as on the App Icon.  The
    # lower band is violet-800, a step darker, as the full game's is.
    #
    # The white bubble drops the highlight strip: its 24 x 14 elliptical
    # corners overhang the bubble's round ones, which on the dark stage reads
    # as a lip and on the plate as a pale smudge at both top corners.  The
    # demo icon's bubble is flat white too.
    "demo": Palette(bg="#5B21B6", bg_top=ICONS.PLATE["demo"], top_opacity="1",
                    player="#ffffff", player_hi="#ffffff", player_hi_opacity="0",
                    player_dot=ICONS.PLATE["demo"]),
}


def base(w, h, p):
    return (f'<rect width="{w}" height="{h}" fill="{p.bg}"/>'
            f'<rect width="{w}" height="{h*0.55:.0f}" fill="{p.bg_top}" opacity="{p.top_opacity}"/>'
            f'<rect y="{h*0.55:.0f}" width="{w}" height="{h*0.45:.0f}" fill="{p.bg}"/>')


def mark(x, y, s, p):
    """Conversation mark. Footprint ~ (340w x 250h) * s at (x,y)."""
    return f'''
  <g transform="translate({x},{y}) scale({s})">
    <rect x="122" y="0" width="218" height="126" rx="26" fill="{GRN}"/>
    <rect x="122" y="0" width="218" height="30" rx="26" fill="#1D9C4B" opacity="0.6"/>
    <path d="M 296 124 L 296 160 L 260 124 Z" fill="{GRN}"/>
    <rect x="152" y="32" width="118" height="13" rx="6.5" fill="#ffffff" opacity="0.95"/>
    <rect x="152" y="57" width="158" height="13" rx="6.5" fill="#ffffff" opacity="0.60"/>
    <rect x="152" y="82" width="86"  height="13" rx="6.5" fill="#ffffff" opacity="0.32"/>
    <rect x="0" y="92" width="198" height="116" rx="24" fill="{p.player}"/>
    <rect x="0" y="92" width="198" height="28" rx="24" fill="{p.player_hi}" opacity="{p.player_hi_opacity}"/>
    <path d="M 40 206 L 40 242 L 76 206 Z" fill="{p.player}"/>
    <circle cx="64" cy="150" r="11" fill="{p.player_dot}"/>
    <circle cx="99" cy="150" r="11" fill="{p.player_dot}" opacity="0.70"/>
    <circle cx="134" cy="150" r="11" fill="{p.player_dot}" opacity="0.42"/>
  </g>'''


def words(cx, y, size):
    """Stacked logotype (game name ONLY — Steam asset rules) at cx; y = baseline of line 1."""
    gap = size * 1.06
    return f'''
  <g text-anchor="middle" font-family="{F}" font-weight="700">
    <text x="{cx}" y="{y}" font-size="{size}" fill="{WHITE}">CONVERSATION</text>
    <text x="{cx}" y="{y+gap:.0f}" font-size="{size}" fill="{WHITE}">SIMULATOR</text>
  </g>'''


def svg(w, h, body, p):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">{base(w,h,p)}{body}</svg>'


# ── "DEMO" ribbon ──────────────────────────────────────────────────────────
# gen_icons.ribbon_shapes() draws the band in the icon's 256-unit frame,
# against the plate's lower-right corner at (PLATE_X + PLATE_WH) on both axes.
# Here that corner is pinned to the capsule's own, and the frame is scaled as
# if a demo icon RIBBON_ICON_SIDE times the capsule's geometric-mean side sat
# in it: about 380 px on the 920 x 430 header, so the word's cap height is
# 38 px there and 17 px on the 462 x 174 small capsule.  The geometric mean
# keeps the tag the same visual weight on wide, tall and square assets.
RIBBON_ICON_SIDE = 0.6
_CORNER = ICONS.PLATE_X + ICONS.PLATE_WH

# Store capsules and the two library capsules carry the game name, so they
# may carry "DEMO".  The hero must stay textless; the logo has no corner.
RIBBONED = ("header_capsule", "small_capsule", "main_capsule", "vertical_capsule",
            "library_capsule", "library_header")

# Nothing of the composition may come within this fraction of the band's
# width of the band's inner edge.  Checked on every render; see _check_clear.
# The tightest fit is the small capsule, whose "SIMULATOR" ends half a band
# width (14 px) short of the ribbon.
RIBBON_CLEARANCE = 0.4


def ribbon_scale(w: int, h: int) -> float:
    """Capsule pixels per unit of the icon's 256-unit frame."""
    return RIBBON_ICON_SIDE * math.sqrt(w * h) / ICONS.VIEW


def ribbon_band(w: int, h: int) -> tuple[float, float]:
    """The band's (inner, outer) edges on the capsule, as values of x + y."""
    k = ribbon_scale(w, h)
    r2 = math.sqrt(2.0)
    return (w + h - (2 * _CORNER - ICONS.RIBBON_U_INNER * r2) * k,
            w + h - (2 * _CORNER - ICONS.RIBBON_U_OUTER * r2) * k)


def ribbon_svg(w: int, h: int) -> str:
    k = ribbon_scale(w, h)
    out = []
    for points, fill in ICONS.ribbon_shapes():
        moved = ((w - (_CORNER - x) * k, h - (_CORNER - y) * k) for x, y in points)
        body = " ".join(f"{x:.2f},{y:.2f}" for x, y in moved)
        out.append(f'<polygon points="{body}" fill="{fill}"/>')
    return "".join(out)


# ── Jobs ───────────────────────────────────────────────────────────────────
class Job(NamedTuple):
    w: int
    h: int
    body: str            # everything above the stage
    transparent: bool = False


def jobs(p: Palette) -> dict[str, Job]:
    j = {}
    # Header 920x430 — mark left, name right-center
    j["header_capsule"] = Job(920, 430, mark(52, 96, 0.92, p) + words(628, 197, 62))
    # Small 462x174 — mark left, name right: the composition of the
    # small_capsule.png committed in #450, which replaced the earlier
    # words-only drawing.
    j["small_capsule"] = Job(462, 174, mark(17.5, 27, 0.445, p) + words(316, 81, 41))
    # Main 1232x706 — mark top-center, name below
    j["main_capsule"] = Job(1232, 706, mark(452, 96, 0.98, p) + words(616, 468, 82))
    # Vertical 748x896
    j["vertical_capsule"] = Job(748, 896, mark(202, 200, 1.0, p) + words(374, 590, 68))
    # Library capsule 600x900
    j["library_capsule"] = Job(600, 900, mark(136, 200, 0.96, p) + words(300, 590, 56))
    # Library header 920x430 — same as header
    j["library_header"] = j["header_capsule"]
    # Library hero 3840x1240 — pure graphic, no text (Steam overlays the logo)
    j["library_hero"] = Job(3840, 1240, mark(1748, 480, 1.05, p))
    # Library logo 1280x720 transparent — mark + words
    j["library_logo"] = Job(1280, 720, mark(478, 60, 0.95, p) + words(640, 430, 92),
                            transparent=True)
    # Page background 1438x810 — very subtle
    j["page_background"] = Job(1438, 810,
        f'<g opacity="0.14">{mark(1010, 130, 0.85, p)}</g><g opacity="0.09">{mark(180, 430, 0.62, p)}</g>')
    return j


EDITION_JOBS = {
    "full": ("header_capsule", "small_capsule", "main_capsule", "vertical_capsule",
             "library_capsule", "library_header", "library_hero", "library_logo",
             "page_background"),
    "demo": ("header_capsule", "small_capsule", "main_capsule", "vertical_capsule",
             "library_capsule", "library_header", "library_hero", "library_logo"),
}


def job_svg(edition: str, name: str, ribbon: bool | None = None) -> str:
    """The SVG for one asset; ``ribbon`` defaults to what the edition draws."""
    p = PALETTES[edition]
    job = jobs(p)[name]
    if ribbon is None:
        ribbon = edition == "demo" and name in RIBBONED
    body = job.body + (ribbon_svg(job.w, job.h) if ribbon else "")
    if job.transparent:
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {job.w} {job.h}">{body}</svg>'
    return svg(job.w, job.h, body, p)


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


def _stage_colours(p: Palette) -> list[tuple[int, int, int]]:
    bg, top, op = _hex(p.bg), _hex(p.bg_top), float(p.top_opacity)
    return [bg, tuple(round(t * op + b * (1 - op)) for t, b in zip(top, bg))]


def _check_clear(name: str, png: Path, w: int, h: int, p: Palette) -> None:
    """Nothing but the stage under the ribbon, nor within RIBBON_CLEARANCE of it.

    Run on a render without the ribbon, so a mark or a line of the logotype
    that strays into the corner is caught here rather than half hidden under
    the band, where it is easy to miss by eye.
    """
    raw = _pixels(png, w, h)
    inner, outer = ribbon_band(w, h)
    limit = inner - RIBBON_CLEARANCE * (outer - inner)
    stage = _stage_colours(p)
    span = int(w + h - limit) + 1
    bad = 0
    for y in range(max(0, h - span), h):
        for x in range(max(0, int(limit - y)), w):
            if x + y + 1 < limit:
                continue
            i = (y * w + x) * 3
            px = raw[i:i + 3]
            if min(max(abs(a - b) for a, b in zip(px, c)) for c in stage) > 8:
                bad += 1
    if bad:
        sys.exit(f"{name}: {bad} pixels of artwork lie under the DEMO ribbon or "
                 "within its clearance; move the composition or shrink "
                 "RIBBON_ICON_SIDE")


def build(edition: str, out: Path) -> list[Path]:
    _check_font()
    out.mkdir(parents=True, exist_ok=True)
    p = PALETTES[edition]
    table = jobs(p)
    written = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for name in EDITION_JOBS[edition]:
            job = table[name]
            ribbon = edition == "demo" and name in RIBBONED
            if ribbon:
                bare = tmp / f"{name}.bare.png"
                _render(job_svg(edition, name, ribbon=False), job.w, job.h, bare)
                _check_clear(name, bare, job.w, job.h, p)
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
