#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Every Conversation Simulator icon, favicon and logo, from one source.

There is exactly one Conversation Simulator icon: the violet and emerald
speech bubbles on a dark radial-gradient square, checked in as

    docs/assets/brand/ConversationSimulatorIcon.svg   (the icon)
    docs/assets/brand/mark.svg                        (the same bubbles, no square)

and exactly one demo icon: that icon with an amber "DEMO" badge in its
lower-right corner.  This script reads those two files and writes every
rendition the project ships, so that no platform can drift onto a different
drawing again.  (Before this, the app bundle and the store logos had a teal
plate with a white bubble, the demo a purple one, the Steam capsules a third
design and the favicons an older cut of the bubbles.)

Edit the source SVGs, never the outputs, then re-run:

    python3 publishing/assets/source/gen_icons.py              # write into the repo
    python3 publishing/assets/source/gen_icons.py --out /tmp/x # write a copy elsewhere

What it writes, per edition (``base`` is the full game, ``demo`` the demo):

  Brand masters
    docs/assets/brand/ConversationSimulatorDemoIcon.svg / .png (2048)
        The demo icon.  The base icon's masters are the checked-in sources.

  Desktop app bundles (Tauri ``bundle.icon``)
    apps/desktop/src-tauri/icons/       base:  32x32.png 128x128.png
    apps/desktop/src-tauri/icons-demo/  demo:  128x128@2x.png icon.ico icon.icns

  Steamworks, Store Presence -> Graphical Assets -> Community and Client Icons
    publishing/assets/icons/<edition>_app_icon.jpg       App Icon, 184 JPG
    publishing/assets/icons/<edition>_shortcut_icon.png  Shortcut Icon, 256 PNG
    publishing/assets/icons/<edition>_icon.svg           the app icon, as vector
    (The Mac Icon field takes the bundle's icon.icns as-is.)

  Microsoft Store package logos
    publishing/microsoft-store/Assets/       base:  Square150x150Logo.png
    publishing/microsoft-store/Assets-demo/  demo:  Square44x44Logo.png StoreLogo.png

  Social media (base only; see publishing/assets/social/README.md)
    publishing/assets/social/avatar.png      1024 square, every profile picture
    publishing/assets/social/banner.png      1500 x 500, every profile header

  Websites and the in-app web UI (base only)
    website/static/       favicon.svg favicon.ico apple-touch-icon.png
    docs-site/public/     favicon.svg favicon.ico apple-touch-icon.png
    apps/web/public/      favicon.svg
    website/layouts/partials/logo.svg   the bubbles, inline beside the wordmark
    docs-site/src/assets/logo.svg       the bubbles, Starlight's site logo

Three shapes of the same drawing, because platforms frame icons differently:

  * ``square`` — the source exactly, full bleed.  For opaque targets that get
    their own mask or none: the Steam App Icon (a JPG), social avatars (which
    the platforms crop to a circle — the bubbles sit inside it), the
    apple-touch-icon (iOS masks it).
  * ``tile`` — the same square with rounded corners (``TILE_RADIUS``) and
    transparent outside them.  For every icon a desktop or a browser draws
    as-is: the Windows .ico, the Linux PNGs, the Steam shortcut, the Microsoft
    Store logos, the favicons.
  * ``macos`` — the tile laid on Apple's icon grid: the art scaled to
    824/1024 of the canvas with a 185.4/1024 corner radius.  Only the .icns.
    A full-bleed square would sit oversized in the Dock, and macOS 26 puts an
    icon that does not fill the standard shape inside a grey plate of its own.

The demo badge is part of the drawing, not an overlay a renderer may drop:
an amber (``--cs-event``) pill carrying "DEMO" as vector outlines, so no
renderer needs a font.  It is drawn at every size.  At 16-32 px the word is
not legible, but the amber pill is, and colour is what tells two rows of a
Steam library list apart.

Rasterising needs librsvg's ``rsvg-convert`` (Ubuntu ``librsvg2-bin``,
macOS ``brew install librsvg``) and ImageMagick (``magick`` or ``convert``)
for the JPEG and for reading pixels back into the ICNS's ARGB chunks.  The
SVG outputs are plain text and reproduce byte for byte anywhere; the rasters
are deterministic for a given librsvg build but move anti-aliased edge pixels
between builds.  Judge a regeneration by
``tests/acceptance/test_demo_branding.py`` and ``test_brand_icon.py`` and by
eye, not by ``git diff``, and do not commit raster churn unless the drawing
changed.  When you do, name the librsvg build (``rsvg-convert --version``)
in the commit message.

gen_capsules.py imports this module for ``mark_markup()`` and the badge, so a
change to either restyles the Steam capsules too: re-run it after this.
"""
from __future__ import annotations

import argparse
import functools
import math
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[3]
BRAND_DIR = REPO_ROOT / "docs" / "assets" / "brand"
ICON_SOURCE = BRAND_DIR / "ConversationSimulatorIcon.svg"
MARK_SOURCE = BRAND_DIR / "mark.svg"

EDITIONS = ("base", "demo")
NAME = {"base": "Conversation Simulator", "demo": "Conversation Simulator Demo"}

# ── Palette ────────────────────────────────────────────────────────────────
# The badge is "the moment" in the brand palette (docs/brand.md: --cs-event)
# with the stage colour (--cs-stage) for the lettering.  Neither is a voice
# colour, so the badge cannot be read as the player or the character.
BADGE_FILL = "#FBBF24"
BADGE_INK = "#0F0F11"
# The flat colour behind anything that must be opaque around the icon (the
# JPEG's corners, were there any): the source's own outer gradient stop.
STAGE = "#292929"

# ── Shapes ─────────────────────────────────────────────────────────────────
TILE_RADIUS = 0.18                  # corner radius / side, for the tile
MACOS_ART = 824.0 / 1024.0          # Apple's icon grid: art side / canvas side
MACOS_RADIUS = 185.4 / 1024.0       # Apple's corner radius / canvas side
SHAPES = ("square", "tile", "macos")

# ── The DEMO badge, in fractions of the icon's side ────────────────────────
# Sized against the source's 864-unit square: an 88-unit cap height, a
# 150-unit pill, 52 units of margin to the right and bottom edges.  That keeps
# the pill clear of the emerald tail's tip (53 units above it) and of the
# violet tail (over 60 units to its left), and inside the rounded corner of
# both the tile and the macOS shape — see _check_badge_fits, which fails the
# run if a change breaks that.
BADGE_CAP = 88.0 / 864.0
BADGE_HEIGHT = 150.0 / 864.0
BADGE_PAD_X = 44.0 / 864.0
BADGE_MARGIN = 52.0 / 864.0
BADGE_CORNER_AIR = 12.0 / 864.0    # least gap between the pill and a corner arc

# "DEMO" in Carlito Bold (SIL OFL 1.1, metric-compatible with Calibri, the
# face the Steam capsules' logotype is set in), outlined with fontTools'
# SVGPathPen, letter-spaced by 0.06 cap heights.  Units: cap height = 1,
# baseline at y = 0, y down.  Outlines, not <text>, so that a favicon, an
# .icns frame and a store logo all draw the same letters without a font.
DEMO_GLYPHS = (
    "M0.9367 -0.5008Q0.9367 -0.3908 0.9021 -0.2986"
    "Q0.8675 -0.2063 0.8038 -0.1401Q0.7402 -0.0738 0.6506 -0.0369"
    "Q0.561 0 0.4518 0H0.0873V-1H0.4518Q0.561 -1 0.6506 -0.9631"
    "Q0.7402 -0.9262 0.8038 -0.8599Q0.8675 -0.7937 0.9021 -0.7018"
    "Q0.9367 -0.6099 0.9367 -0.5008ZM0.7357 -0.5008"
    "Q0.7357 -0.5806 0.7161 -0.6438Q0.6965 -0.7071 0.66 -0.7515"
    "Q0.6235 -0.7959 0.5708 -0.8197Q0.5181 -0.8434 0.4518 -0.8434"
    "H0.2861V-0.1574H0.4518Q0.5181 -0.1574 0.5708 -0.1807"
    "Q0.6235 -0.2041 0.66 -0.2485Q0.6965 -0.2929 0.7161 -0.3566"
    "Q0.7357 -0.4202 0.7357 -0.5008ZM1.7309 -1V-0.8426H1.3198V-0.5783"
    "H1.6398V-0.427H1.3198V-0.1574H1.7317L1.7309 0H1.121V-1Z"
    "M2.4754 -0.427Q2.501 -0.3795 2.5198 -0.3283"
    "Q2.5304 -0.3547 2.5409 -0.3799Q2.5515 -0.4051 2.5643 -0.4285"
    "L2.8723 -0.9691Q2.8783 -0.9804 2.8847 -0.9868"
    "Q2.8911 -0.9932 2.8986 -0.9959Q2.9061 -0.9985 2.9159 -0.9992"
    "Q2.9257 -1 2.9385 -1H3.0876V0H2.9137V-0.6258"
    "Q2.9137 -0.6461 2.9148 -0.6698Q2.9159 -0.6935 2.9182 -0.7184"
    "L2.6027 -0.1596Q2.5793 -0.116 2.5342 -0.116H2.5063"
    "Q2.4604 -0.116 2.437 -0.1596L2.1177 -0.7214"
    "Q2.1208 -0.6958 2.1223 -0.6713Q2.1238 -0.6468 2.1238 -0.6258V0"
    "H1.9491V-1H2.0989Q2.1117 -1 2.1211 -0.9992"
    "Q2.1305 -0.9985 2.1384 -0.9955Q2.1464 -0.9925 2.1528 -0.9864"
    "Q2.1592 -0.9804 2.1652 -0.9691L2.4754 -0.427Z"
    "M4.2598 -0.5008Q4.2598 -0.3908 4.2252 -0.2971"
    "Q4.1905 -0.2033 4.1269 -0.1348Q4.0633 -0.0663 3.9737 -0.0279"
    "Q3.8841 0.0105 3.7749 0.0105Q3.6657 0.0105 3.5761 -0.0279"
    "Q3.4865 -0.0663 3.4225 -0.1348Q3.3585 -0.2033 3.3234 -0.2971"
    "Q3.2884 -0.3908 3.2884 -0.5008Q3.2884 -0.6099 3.3234 -0.7037"
    "Q3.3585 -0.7974 3.4225 -0.8656Q3.4865 -0.9337 3.5761 -0.9725"
    "Q3.6657 -1.0113 3.7749 -1.0113Q3.8841 -1.0113 3.9737 -0.9725"
    "Q4.0633 -0.9337 4.1269 -0.8652Q4.1905 -0.7967 4.2252 -0.7033"
    "Q4.2598 -0.6099 4.2598 -0.5008ZM4.058 -0.5008"
    "Q4.058 -0.5806 4.0384 -0.6438Q4.0189 -0.7071 3.9823 -0.7515"
    "Q3.9458 -0.7959 3.8935 -0.8197Q3.8411 -0.8434 3.7749 -0.8434"
    "Q3.7086 -0.8434 3.6559 -0.8197Q3.6032 -0.7959 3.5667 -0.7515"
    "Q3.5302 -0.7071 3.5106 -0.6438Q3.491 -0.5806 3.491 -0.5008"
    "Q3.491 -0.4202 3.5106 -0.3566Q3.5302 -0.2929 3.5667 -0.2489"
    "Q3.6032 -0.2048 3.6559 -0.1815Q3.7086 -0.1581 3.7749 -0.1581"
    "Q3.8411 -0.1581 3.8935 -0.1815Q3.9458 -0.2048 3.9823 -0.2489"
    "Q4.0189 -0.2929 4.0384 -0.3566Q4.058 -0.4202 4.058 -0.5008Z"
)
# The outlines' ink extent along x, in the same units: D's stem to O's bowl.
DEMO_INK_X = (0.0873, 4.2598)


# ── Reading the sources ────────────────────────────────────────────────────
_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"
_SKIP = {"title", "desc", "metadata", "style"}
_SHAPES = {"rect", "path", "polygon", "polyline", "circle", "ellipse", "line", "g"}
_GRADIENTS = {"linearGradient", "radialGradient"}
_PAINT_PROPS = ("fill", "fill-opacity", "fill-rule", "opacity",
                "stroke", "stroke-width", "stroke-opacity")


class Artwork(NamedTuple):
    """A source SVG reduced to plain markup: no CSS, no title, scoped ids."""
    side: float      # the square viewBox's side, in source units
    defs: str        # gradients, ids prefixed
    body: str        # the drawing, every paint as an attribute


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _css_rules(root: ET.Element) -> dict[str, dict[str, str]]:
    """``.class{prop:value;...}`` rules from the source's <style> blocks.

    Design tools export paint as classes; resolving them here keeps a
    ``<style>`` out of every output, where an inlined copy would restyle any
    page that happens to use the same class names (``.cls-1`` is common).
    """
    rules: dict[str, dict[str, str]] = {}
    for style in root.iter(f"{{{_SVG_NS}}}style"):
        text = style.text or ""
        for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", text):
            props = dict(
                (k.strip(), v.strip())
                for k, v in (d.split(":", 1) for d in body.split(";") if ":" in d)
            )
            for sel in selectors.split(","):
                sel = sel.strip()
                if not re.fullmatch(r"\.[\w-]+", sel):
                    sys.exit(f"unsupported CSS selector {sel!r} in a brand source; "
                             "only plain .class rules are understood")
                rules.setdefault(sel[1:], {}).update(props)
    return rules


@functools.lru_cache(maxsize=None)
def load_artwork(path: Path, prefix: str) -> Artwork:
    """Parse a brand source into an :class:`Artwork`, scoping its ids.

    Only what the brand sources actually use is understood — basic shapes,
    groups, linear and radial gradients, class-based paint — and anything else
    stops the run with the element named, rather than being dropped from
    every icon without a word.
    """
    root = ET.parse(path).getroot()
    view = [float(v) for v in root.get("viewBox", "").replace(",", " ").split()]
    if len(view) != 4 or view[0] or view[1] or view[2] != view[3]:
        sys.exit(f"{path}: the viewBox must be a square starting at 0 0, got {view}")
    rules = _css_rules(root)

    def attrs(el: ET.Element) -> str:
        out: dict[str, str] = {}
        for cls in (el.get("class") or "").split():
            for prop, value in rules.get(cls, {}).items():
                if prop in _PAINT_PROPS:
                    out[prop] = value
        for key, value in el.attrib.items():
            key = _local(key)
            if key in ("class", "id", "style"):
                continue
            out[key] = value
        for prop, value in list(out.items()):
            out[prop] = re.sub(r"url\(#([^)]+)\)", rf"url(#{prefix}-\1)", value)
        return "".join(f' {k}="{v}"' for k, v in out.items())

    defs: list[str] = []

    def emit(el: ET.Element) -> str:
        tag = _local(el.tag)
        if tag in _SKIP:
            return ""
        if tag == "defs":
            for child in el:
                emit(child)
            return ""
        if tag in _GRADIENTS:
            stops = "".join(f"<stop{attrs(s)}/>" for s in el if _local(s.tag) == "stop")
            defs.append(f'<{tag} id="{prefix}-{el.get("id")}"{attrs(el)}>{stops}</{tag}>')
            return ""
        if tag not in _SHAPES:
            sys.exit(f"{path}: unsupported element <{tag}> in a brand source")
        if tag == "g":
            inner = "".join(emit(child) for child in el)
            own = attrs(el)
            # A layer group that only carried an id (ART, GUIDES) is unwrapped.
            return f"<g{own}>{inner}</g>" if inner and own else inner
        return f"<{tag}{attrs(el)}/>"

    body = "".join(emit(child) for child in root)
    return Artwork(side=view[2], defs="".join(defs), body=body)


def icon_artwork() -> Artwork:
    return load_artwork(ICON_SOURCE, "csi")


def mark_artwork() -> Artwork:
    return load_artwork(MARK_SOURCE, "csm")


def mark_markup(x: float, y: float, size: float) -> str:
    """The bubbles (mark.svg) scaled so the source square is ``size`` wide at (x, y)."""
    art = mark_artwork()
    k = size / art.side
    return f'<g transform="translate({_n(x)} {_n(y)}) scale({_n(k, 6)})">{art.body}</g>'


@functools.lru_cache(maxsize=1)
def mark_ink_box() -> tuple[float, float, float, float]:
    """The bubbles' bounding box in mark.svg's own units: (x0, y0, x1, y1).

    Read off every coordinate pair in the source's path data and polygon
    points.  The bubbles' Bézier control points lie on their bounding box (the
    corners are quarter-ellipses), so this is the ink's extent exactly.  Only
    absolute coordinates are understood, which is what the source uses.
    """
    body = mark_artwork().body
    xs: list[float] = []
    ys: list[float] = []
    for chunk in re.findall(r'\s(?:d|points)="([^"]+)"', body):
        if re.search(r"[a-z]", chunk):
            sys.exit("mark.svg uses relative path commands; export it with absolute ones")
        nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", chunk)]
        xs += nums[0::2]
        ys += nums[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def mark_at(x: float, y: float, h: float) -> str:
    """The mark with its bubbles' bounding box at (x, y), ``h`` units square.

    Placed by the ink, not by mark.svg's square: the source keeps the icon's
    margin around the bubbles, which a composition (a capsule, a banner, the
    share card) does not want.
    """
    x0, y0, x1, y1 = mark_ink_box()
    side = mark_artwork().side
    k = h / max(x1 - x0, y1 - y0)
    return mark_markup(x - x0 * k, y - y0 * k, side * k)


def _n(value: float, places: int = 3) -> str:
    """A number for SVG: fixed places, trailing zeros and a bare point dropped."""
    text = f"{value:.{places}f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


# ── The badge ──────────────────────────────────────────────────────────────
class Pill(NamedTuple):
    x: float
    y: float
    w: float
    h: float


def badge_box(side: float) -> Pill:
    """The pill's rectangle on an icon of side ``side``, lower-right corner."""
    cap = BADGE_CAP * side
    ink = (DEMO_INK_X[1] - DEMO_INK_X[0]) * cap
    w = ink + 2 * BADGE_PAD_X * side
    h = BADGE_HEIGHT * side
    x = side - BADGE_MARGIN * side - w
    y = side - BADGE_MARGIN * side - h
    return Pill(x, y, w, h)


def badge_at(pill: Pill) -> str:
    """The amber pill with "DEMO" centred in it, for any rectangle of the
    badge's proportions — the icons place it with :func:`badge_box`, the
    capsules pin it to their own lower-right corner."""
    cap = pill.h * BADGE_CAP / BADGE_HEIGHT
    ink_w = (DEMO_INK_X[1] - DEMO_INK_X[0]) * cap
    tx = pill.x + (pill.w - ink_w) / 2 - DEMO_INK_X[0] * cap
    ty = pill.y + (pill.h + cap) / 2          # baseline: cap box centred
    return (
        f'<rect x="{_n(pill.x)}" y="{_n(pill.y)}" width="{_n(pill.w)}" '
        f'height="{_n(pill.h)}" rx="{_n(pill.h / 2)}" fill="{BADGE_FILL}"/>'
        f'<path transform="translate({_n(tx)} {_n(ty)}) scale({_n(cap, 4)})" '
        f'fill="{BADGE_INK}" d="{DEMO_GLYPHS}"/>'
    )


def _check_badge_fits(side: float) -> None:
    """The badge stays inside every shape's rounded corner and clear of the
    bubbles.

    Checked against the geometry, not a render, so a change to the badge
    constants or to a shape's corner radius fails here with the reason.  The
    pill's right end-cap is a circle; it must sit inside the corner arc of the
    tile and of the macOS shape (whose radius, in the art's own units, is the
    larger of the two) with at least ``BADGE_CORNER_AIR`` of the side to spare.
    """
    p = badge_box(side)
    r = p.h / 2
    cap_centre = (p.x + p.w - r, p.y + r)
    for shape, radius in (("tile", TILE_RADIUS), ("macos", MACOS_RADIUS / MACOS_ART)):
        corner = side * (1 - radius)
        reach = math.dist(cap_centre, (corner, corner)) + r
        if reach > side * (radius - BADGE_CORNER_AIR):
            sys.exit(f"the DEMO badge runs into the {shape} shape's rounded corner")
    if p.x < side * 0.25 or p.y < side * 0.6:
        sys.exit("the DEMO badge has grown into the bubbles; shrink BADGE_*")


# ── Composing an icon ──────────────────────────────────────────────────────
def icon_svg(edition: str, shape: str, *, header: bool = False) -> str:
    """One edition of the icon, in one shape, as a standalone SVG string."""
    if edition not in EDITIONS or shape not in SHAPES:
        raise ValueError((edition, shape))
    art = icon_artwork()
    s = art.side
    _check_badge_fits(s)
    drawing = art.body + (badge_at(badge_box(s)) if edition == "demo" else "")
    defs = art.defs
    if shape == "tile":
        defs += (f'<clipPath id="csi-shape"><rect width="{_n(s)}" height="{_n(s)}" '
                 f'rx="{_n(s * TILE_RADIUS)}"/></clipPath>')
        drawing = f'<g clip-path="url(#csi-shape)">{drawing}</g>'
    elif shape == "macos":
        k = MACOS_ART
        offset = s * (1 - k) / 2
        defs += (f'<clipPath id="csi-shape"><rect width="{_n(s)}" height="{_n(s)}" '
                 f'rx="{_n(s * MACOS_RADIUS / k)}"/></clipPath>')
        drawing = (f'<g transform="translate({_n(offset)} {_n(offset)}) scale({_n(k, 6)})">'
                   f'<g clip-path="url(#csi-shape)">{drawing}</g></g>')
    comment = ""
    if header:
        comment = ("<!-- SPDX-License-Identifier: CC-BY-4.0 -->\n"
                   "<!-- Generated by publishing/assets/source/gen_icons.py from "
                   "docs/assets/brand/ConversationSimulatorIcon.svg; edit that, "
                   "not this. -->\n")
    return (
        f'{comment}<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_n(s)} {_n(s)}" '
        f'role="img" aria-label="{NAME[edition]}"><defs>{defs}</defs>{drawing}</svg>\n'
    )


def mark_svg(*, inline_class: str | None = None, px: int | None = None,
             header: bool = False) -> str:
    """The bubbles alone, transparent, cropped to their own square — the mark
    beside a wordmark.

    Cropped because mark.svg keeps the icon's margin around the bubbles, which
    beside a wordmark would only shrink them: at the website header's 28 px the
    bubbles get all 28 rather than 20.  ``inline_class`` and ``px`` make the
    Hugo partial's form: decorative (``aria-hidden``) because the wordmark
    next to it carries the name.
    """
    art = mark_artwork()
    x0, y0, x1, y1 = mark_ink_box()
    side = max(x1 - x0, y1 - y0)
    view = (f"{_n(x0 - (side - (x1 - x0)) / 2)} {_n(y0 - (side - (y1 - y0)) / 2)} "
            f"{_n(side)} {_n(side)}")
    if inline_class is not None:
        open_tag = (f'<svg class="{inline_class}" xmlns="http://www.w3.org/2000/svg" '
                    f'viewBox="{view}" width="{px}" height="{px}" aria-hidden="true">')
    else:
        open_tag = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" '
                    f'role="img" aria-label="{NAME["base"]}">')
    comment = ""
    if header:
        comment = ("<!-- SPDX-License-Identifier: CC-BY-4.0 -->\n"
                   "<!-- Generated by publishing/assets/source/gen_icons.py from "
                   "docs/assets/brand/mark.svg; edit that, not this. -->\n")
    defs = f"<defs>{art.defs}</defs>" if art.defs else ""
    return f"{comment}{open_tag}{defs}{art.body}</svg>\n"


# ── Rasterisation ──────────────────────────────────────────────────────────
def _need(cmd: str, hint: str) -> str:
    path = shutil.which(cmd)
    if path is None:
        sys.exit(f"gen_icons.py needs `{cmd}` on PATH: {hint}")
    return path


@functools.lru_cache(maxsize=1)
def _rsvg() -> str:
    return _need("rsvg-convert", "Ubuntu `apt-get install librsvg2-bin`, "
                                 "macOS `brew install librsvg`")


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
    sys.exit("gen_icons.py needs ImageMagick on PATH (`apt-get install "
             "imagemagick`, `brew install imagemagick`).")


def render_svg(svg: str, width: int, height: int, dest: Path) -> Path:
    """Rasterise SVG markup to an 8-bit RGBA PNG of exactly width x height."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.svg"
        src.write_text(svg)
        raw = Path(tmp) / "out.png"
        subprocess.run([_rsvg(), "--width", str(width), "--height", str(height),
                        "--format", "png", "--output", str(raw), str(src)], check=True)
        # Through ImageMagick once more: PNG32 pins 8-bit RGBA whatever cairo
        # chose, and -strip drops the ancillary chunks a reader does not need.
        subprocess.run([_magick(), "PNG:" + str(raw), "-strip", "-depth", "8",
                        "PNG32:" + str(dest)], check=True)
    return dest


def render_png(edition: str, shape: str, size: int, dest: Path) -> Path:
    return render_svg(icon_svg(edition, shape), size, size, dest)


ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
FAVICON_ICO_SIZES = (16, 32, 48)

# ICNS chunk type -> pixel size, for the types that carry a plain PNG payload.
ICNS_PNG_TYPES = (
    (b"ic11", 32), (b"ic12", 64), (b"ic07", 128), (b"ic13", 256),
    (b"ic08", 256), (b"ic14", 512), (b"ic09", 512), (b"ic10", 1024),
)

# The 1x 16 pt and 32 pt representations.  The ICNS format does define
# PNG-capable types at these two sizes (icp4/icp5), but neither Apple's
# `iconutil` nor a typical app's icon.icns uses them: both carry ic04/ic05,
# which are run-length-encoded ARGB.  Omitting them is not fatal — macOS
# scales the nearest representation down — but it costs exactly the
# small-size sharpness an icon exists to provide, on every 1x display.
ICNS_ARGB_TYPES = ((b"ic04", 16), (b"ic05", 32))

ICNS_SIZES = tuple(sorted(
    {s for _, s in ICNS_PNG_TYPES} | {s for _, s in ICNS_ARGB_TYPES}
))


def write_ico(frames: dict[int, Path], dest: Path, sizes: tuple[int, ...]) -> None:
    """Assemble an ICO holding each frame as its PNG bytes.

    Written here rather than handed to ImageMagick because its ICO coder
    stores every frame as an uncompressed DIB — a 256 px frame alone costs
    256 KB.  PNG payloads are what Windows has read since Vista.
    """
    payloads = [frames[s].read_bytes() for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = len(header) + 16 * len(sizes)
    entries, body = b"", b""
    for size, payload in zip(sizes, payloads):
        # 256 is encoded as 0 in the single-byte width/height fields. Planes
        # and bit depth are ignored for PNG payloads; 0/32 is conventional.
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 0, 32, len(payload), offset)
        body += payload
        offset += len(payload)
    dest.write_bytes(header + entries + body)


def _rgba_bytes(png: Path) -> bytes:
    """The frame's raw, straight-alpha RGBA samples, row by row."""
    return subprocess.run(
        [_magick(), "PNG:" + str(png), "-depth", "8", "RGBA:-"],
        check=True, capture_output=True,
    ).stdout


def _packbits(data: bytes, tail_literal: bool = False) -> bytes:
    """ICNS run-length encoding of one colour channel.

    The variant ICNS uses, not the QuickTime one: a control byte below 128
    introduces ``n + 1`` literal bytes, and one at or above 128 repeats the
    next byte ``n - 125`` times — so a run only pays for itself at three.
    The decoder stops once it has the channel's pixel count, so there is no
    terminator; the channels are concatenated in A, R, G, B order.

    ``tail_literal`` spends two bytes to encode the channel's last sample as a
    one-byte literal rather than letting it fall inside a run. Only the final
    channel of a chunk asks for it, and only to be kind to a decoder that
    stops one byte short of the payload — see ``_argb_chunk``.
    """
    if tail_literal and data:
        return _packbits(data[:-1]) + b"\x00" + data[-1:]
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        run = 1
        while run < 130 and i + run < n and data[i + run] == data[i]:
            run += 1
        if run >= 3:
            out += bytes((run + 125, data[i]))
            i += run
            continue
        # Literals, up to 128, ending as soon as a run worth encoding starts.
        start = i
        while i < n and i - start < 128:
            if i + 2 < n and data[i] == data[i + 1] == data[i + 2]:
                break
            i += 1
        out += bytes((i - start - 1,)) + data[start:i]
    return bytes(out)


def _argb_chunk(png: Path, size: int) -> bytes:
    """An ``ic04``/``ic05`` payload: the "ARGB" magic, then A, R, G and B.

    The samples are straight-alpha, not premultiplied — the same thing
    ``iconutil`` itself writes.  The blue channel — the last one, so the one
    whose final byte is also the payload's — is encoded with
    ``tail_literal``: ``iconutil``'s reader stops one byte short of the
    payload, on Apple's own files too, which costs one sample when the channel
    ends on a literal and up to 130 when it ends on a run.

    Do not check these two chunks with ``iconutil -c iconset``: it
    un-premultiplies on the way out, so every partly transparent pixel comes
    back blown out toward white, on Apple's own output as much as this.  Check
    with ``NSImage(contentsOfFile:)`` and ``colorAt`` instead.
    """
    rgba = _rgba_bytes(png)
    assert len(rgba) == size * size * 4, f"{png}: expected {size}x{size} RGBA"
    channels = (rgba[3::4], rgba[0::4], rgba[1::4], rgba[2::4])
    return b"ARGB" + b"".join(
        _packbits(c, tail_literal=i == len(channels) - 1)
        for i, c in enumerate(channels)
    )


def write_icns(frames: dict[int, Path], dest: Path) -> None:
    """Assemble an ICNS from PNG frames: a four-byte magic, a big-endian total
    length, then one ``[type][length][payload]`` chunk per representation."""
    chunks = b""
    for kind, size in ICNS_PNG_TYPES:
        payload = frames[size].read_bytes()
        chunks += kind + struct.pack(">I", len(payload) + 8) + payload
    for kind, size in ICNS_ARGB_TYPES:
        payload = _argb_chunk(frames[size], size)
        chunks += kind + struct.pack(">I", len(payload) + 8) + payload
    dest.write_bytes(b"icns" + struct.pack(">I", len(chunks) + 8) + chunks)


def write_jpeg(png: Path, dest: Path) -> None:
    """Flatten onto the stage and write a JPEG, as Steamworks' App Icon wants.

    4:4:4 sampling, because chroma subsampling on a 184 px icon smears the
    bubbles' edges and the badge's lettering; ``-strip`` drops the profile
    and any timestamp, and optimised Huffman tables keep the bytes from
    depending on which default a libjpeg build carries.
    """
    subprocess.run(
        [_magick(), "PNG:" + str(png), "-background", STAGE,
         "-alpha", "remove", "-alpha", "off", "-strip",
         "-sampling-factor", "1x1", "-quality", "95",
         "-define", "jpeg:optimize-coding=true", "JPEG:" + str(dest)],
        check=True,
    )


# ── Where everything goes ──────────────────────────────────────────────────
# The PNG members of Tauri's five-file `bundle.icon` list, by pixel size;
# icon.ico and icon.icns are the other two and are assembled below.
BUNDLE_PNGS = ((32, "32x32.png"), (128, "128x128.png"), (256, "128x128@2x.png"))
BUNDLE_DIR = {
    "base": Path("apps/desktop/src-tauri/icons"),
    "demo": Path("apps/desktop/src-tauri/icons-demo"),
}

# Steamworks "Community and Client Icons".
STEAM_ICON_DIR = Path("publishing/assets/icons")
APP_ICON_PX = 184       # App Icon: 184x184 JPG — the library list, chat, notifications
SHORTCUT_ICON_PX = 256  # Shortcut Icon: 256x256 (512 also taken) .ico/.png

# Microsoft Store package logos (AppxManifest.xml), by file name.
MSSTORE_DIR = {
    "base": Path("publishing/microsoft-store/Assets"),
    "demo": Path("publishing/microsoft-store/Assets-demo"),
}
MSSTORE_LOGOS = (("Square150x150Logo.png", 150), ("Square44x44Logo.png", 44),
                 ("StoreLogo.png", 50))

DEMO_MASTER_SVG = Path("docs/assets/brand/ConversationSimulatorDemoIcon.svg")
DEMO_MASTER_PNG = Path("docs/assets/brand/ConversationSimulatorDemoIcon.png")
MASTER_PX = 2048        # the checked-in ConversationSimulatorIcon.png's size

SOCIAL_AVATAR = Path("publishing/assets/social/avatar.png")
SOCIAL_AVATAR_PX = 1024
SOCIAL_BANNER = Path("publishing/assets/social/banner.png")
SOCIAL_BANNER_SIZE = (1500, 500)   # Bluesky, X and Mastodon headers are all 3:1


def banner_svg() -> str:
    """A profile header: the share card's stage, the mark centred, no text.

    No text because every platform prints the account's name under or over
    its header, and centred because each crops a 3:1 header differently on
    phones and lays the avatar over a different corner.  The stage is the
    share card's (website/static/images/og-card.svg): near-black with a violet
    glow from the top left and an emerald one from the bottom right.
    """
    w, h = SOCIAL_BANNER_SIZE
    ink = 300
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">'
        '<defs><radialGradient id="glowV" cx="0.12" cy="0" r="0.9">'
        '<stop offset="0" stop-color="#7c5cdb" stop-opacity="0.22"/>'
        '<stop offset="1" stop-color="#7c5cdb" stop-opacity="0"/></radialGradient>'
        '<radialGradient id="glowE" cx="0.95" cy="1.05" r="0.85">'
        '<stop offset="0" stop-color="#10b981" stop-opacity="0.16"/>'
        '<stop offset="1" stop-color="#10b981" stop-opacity="0"/></radialGradient></defs>'
        f'<rect width="{w}" height="{h}" fill="#0a0a0c"/>'
        f'<rect width="{w}" height="{h}" fill="url(#glowV)"/>'
        f'<rect width="{w}" height="{h}" fill="url(#glowE)"/>'
        f'{mark_at((w - ink) / 2, (h - ink) / 2, ink)}</svg>\n'
    )

# Web favicons.  The SVG is what every current browser uses; the .ico is what
# a browser, crawler or feed reader asks for at /favicon.ico without reading
# the page; the apple-touch-icon is iOS's home-screen and share-sheet icon,
# opaque and unmasked because iOS applies its own corner mask.
FAVICON_SVG = (Path("website/static/favicon.svg"), Path("docs-site/public/favicon.svg"),
               Path("apps/web/public/favicon.svg"))
FAVICON_ICO = (Path("website/static/favicon.ico"), Path("docs-site/public/favicon.ico"))
APPLE_TOUCH = (Path("website/static/apple-touch-icon.png"),
               Path("docs-site/public/apple-touch-icon.png"))
APPLE_TOUCH_PX = 180

# The bubbles beside the wordmark.
WEBSITE_LOGO_PARTIAL = Path("website/layouts/partials/logo.svg")
WEBSITE_LOGO_PX = 28
DOCS_LOGO = Path("docs-site/src/assets/logo.svg")


def text_outputs() -> dict[Path, str]:
    """Every generated file that is SVG text, by repo-relative path.

    These need no renderer, so the acceptance suite regenerates them and
    compares byte for byte: a hand-edited favicon or a stale demo master
    fails CI rather than quietly becoming a second logo.
    """
    out = {
        DEMO_MASTER_SVG: icon_svg("demo", "square", header=True),
        WEBSITE_LOGO_PARTIAL: mark_svg(inline_class="logo-mark", px=WEBSITE_LOGO_PX),
        DOCS_LOGO: mark_svg(header=True),
    }
    for edition in EDITIONS:
        out[STEAM_ICON_DIR / f"{edition}_icon.svg"] = icon_svg(edition, "tile", header=True)
    for path in FAVICON_SVG:
        out[path] = icon_svg("base", "tile")
    return out


def build(root: Path) -> list[Path]:
    """Write every output under ``root`` (the repo, or a scratch copy of its layout)."""
    written: list[Path] = []

    def dest(rel: Path) -> Path:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        written.append(path)
        return path

    for rel, text in text_outputs().items():
        dest(rel).write_text(text)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for edition in EDITIONS:
            # Every tile frame the bundle, the Steam shortcut and the Store
            # logos need, rendered once.
            tile_sizes = sorted({*ICO_SIZES, *(s for s, _ in BUNDLE_PNGS),
                                 SHORTCUT_ICON_PX, *(s for _, s in MSSTORE_LOGOS),
                                 *FAVICON_ICO_SIZES})
            tile = {s: render_png(edition, "tile", s, tmp / f"{edition}-tile-{s}.png")
                    for s in tile_sizes}
            mac = {s: render_png(edition, "macos", s, tmp / f"{edition}-mac-{s}.png")
                   for s in ICNS_SIZES}

            bundle = BUNDLE_DIR[edition]
            for size, name in BUNDLE_PNGS:
                dest(bundle / name).write_bytes(tile[size].read_bytes())
            write_ico(tile, dest(bundle / "icon.ico"), ICO_SIZES)
            write_icns(mac, dest(bundle / "icon.icns"))

            square_184 = render_png(edition, "square", APP_ICON_PX, tmp / f"{edition}-184.png")
            write_jpeg(square_184, dest(STEAM_ICON_DIR / f"{edition}_app_icon.jpg"))
            # The Shortcut Icon is the frame the app itself installs, byte for
            # byte, so the desktop shortcut and the app cannot drift apart.
            dest(STEAM_ICON_DIR / f"{edition}_shortcut_icon.png").write_bytes(
                tile[SHORTCUT_ICON_PX].read_bytes())

            for name, size in MSSTORE_LOGOS:
                dest(MSSTORE_DIR[edition] / name).write_bytes(tile[size].read_bytes())

            if edition == "base":
                for rel in FAVICON_ICO:
                    write_ico(tile, dest(rel), FAVICON_ICO_SIZES)
                touch = render_png("base", "square", APPLE_TOUCH_PX, tmp / "touch.png")
                for rel in APPLE_TOUCH:
                    dest(rel).write_bytes(touch.read_bytes())
                render_png("base", "square", SOCIAL_AVATAR_PX, dest(SOCIAL_AVATAR))
                render_svg(banner_svg(), *SOCIAL_BANNER_SIZE, dest(SOCIAL_BANNER))
            else:
                render_png("demo", "square", MASTER_PX, dest(DEMO_MASTER_PNG))
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path,
                    help="write under this directory, mirroring the repo's layout, "
                         "instead of into the repo")
    args = ap.parse_args()
    root = args.out if args.out is not None else REPO_ROOT
    for path in build(root):
        print(path.relative_to(root) if path.is_relative_to(root) else path)


if __name__ == "__main__":
    main()
