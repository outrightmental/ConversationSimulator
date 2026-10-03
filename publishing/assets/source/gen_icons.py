#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Application-icon set for Conversation Simulator — base and demo editions.

Issue #499: the Steam Demo app (App 5343430) shipped the base app's icon, so
the demo and the full game were indistinguishable in the Steam client. This
script is the single source of truth for the app mark and emits, per edition:

  32x32.png 128x128.png 128x128@2x.png icon.ico icon.icns  -> apps/desktop/
                                                              src-tauri/icons-demo/
  <edition>_app_icon.jpg (184), <edition>_shortcut_icon.png (256),
  <edition>_icon.svg                                       -> publishing/assets/icons/

The bundle set is what ``bundle.icon`` in tauri.demo.conf.json points at.  The
other two go to Steamworks, under Store Presence -> Graphical Assets ->
Community and Client Icons, and they are two different fields:

  * **App Icon** — 184x184 JPG.  Valve: "used in the library list view,
    'favorites' in chat, and notifications across the Steam client, mobile
    client, and Deck."  This is the one in the issue's screenshot: the sidebar
    row where the demo and the full game read as the same product.  JPG has no
    alpha, so the plate is flattened onto the capsule set's near-black.
  * **Shortcut Icon** — 256x256 (or 512x512) .ico or .png, for the desktop
    shortcut Steam creates.  Valve generates the .ico from a PNG, so a PNG is
    what this emits, at 256: that is byte-identical to the frame the app
    itself installs, so the two cannot drift apart.

macOS shortcuts additionally need an ICNS in Steamworks' **Mac Icon** field;
that is ``icons-demo/icon.icns`` from the bundle set, uploaded as-is.

The demo differs from the base in two ways, in this order of importance:

  1. Plate colour.  Teal (#147A84) for the full game, deep purple (#6D28D9,
     the player-voice purple the capsule set already uses) for the demo.  Hue
     is the only thing that survives the 16-32 px the Steam client library
     list actually renders, so it carries the distinction on its own.
  2. A "DEMO" corner ribbon, drawn only at >= 128 px (``RIBBON_MIN_PX``).
     WORD_HEIGHT is 26 of the viewBox's 256 units, so the cap height is a
     tenth of the frame: 13 px at 128, 6 px at 64, 3 px at 32.  Below 128
     the word turns to mush, so the small frames stay clean and let the
     colour do the work.

The mark itself — white speech bubble, three dots — is identical in both
editions: the demo must read as the same product, not a different one.

Everything is drawn as explicit polygons, circles and rounded rects, and the
"DEMO" word is vector letterforms rather than text.  ImageMagick's built-in
SVG renderer — what you get when librsvg is not installed, which is the common
case — silently ignores ``clip-path`` and ``transform`` and cannot resolve a
font at all; gen_capsules.py's reliance on an installed Carlito is exactly the
sort of thing that makes a generator irreproducible.  Nothing here needs more
than ImageMagick's own rasteriser, which ``render_png`` asks for by name
(``MSVG:``) so that an installed librsvg cannot quietly re-render the set:
the committed PNGs rebuild byte-for-byte on any machine with the same
ImageMagick build, with no font to install.  The ICO and ICNS are assembled
from those same bytes here, so they inherit it.

The one output that does **not** carry that promise is the App Icon, because
Steamworks wants it as a JPG.  Its encoder settings are pinned below, but
quantisation and Huffman tables still differ between libjpeg and
libjpeg-turbo and across their versions, so a machine that reproduces every
PNG exactly can still emit a byte-different .jpg.  That is why the suite
checks it by content — size, opacity, plate colour, ribbon — and not by
comparing it to a regenerated copy.

Usage:
    python3 publishing/assets/source/gen_icons.py            # write into the repo
    python3 publishing/assets/source/gen_icons.py --edition base --out /tmp/base

Only the demo set is committed.  The base set in apps/desktop/src-tauri/icons/
is the original `tauri icon` output and is deliberately left alone; rendering
it here is for side-by-side comparison when the mark changes — and for the
full game's own Steamworks icons, which come from `--edition base` and not
from gen_capsules.py's `community_icon`.  That one is also 184 x 184, so it
looks like the right file, but it draws a #6D28D9 bubble on the near-black
with no plate: #6D28D9 is the demo's plate colour, and uploading it against
the full game would hand the demo's distinguishing hue to the app it is meant
to be told apart from.
"""
from __future__ import annotations

import argparse
import functools
import math
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# ── Palette ────────────────────────────────────────────────────────────────
PLATE = {
    "base": "#147A84",  # sampled from the committed icons/128x128@2x.png
    # gen_capsules.py's PURP: the player bubble in the capsule mark.  The UI's
    # own player token (--cs-you, #A78BFA) is a tint meant for text on a dark
    # stage and is far too light to sit behind a white speech bubble.
    "demo": "#6D28D9",
}
WHITE = "#FFFFFF"
RIBBON_BG = "#0D0D15"   # the capsule-set base colour
RIBBON_FG = "#F4F4F5"

# Below this pixel size the ribbon is dropped: the word is illegible and only
# muddies the silhouette.  The Steam App Icon (184) and Shortcut Icon (256) are
# both above it; the bundle's 16-64 px frames are deliberately below.
RIBBON_MIN_PX = 128

# Supersampling, expressed as the square the render is forced to before the
# final Lanczos step down.  Note that this is *not* the size MSVG rasterises
# at — see render_png, where it is also handed to -density and ImageMagick
# scales the 256-unit viewBox by density/96 on top.
SUPERSAMPLE = 4
SUPERSAMPLE_CAP = 1024

# ── Geometry, in a 256-unit viewBox ────────────────────────────────────────
# Measured off the committed base icon so the demo plate lines up pixel for
# pixel with the full game's.
VIEW = 256.0
PLATE_X, PLATE_Y, PLATE_WH, PLATE_R = 9.5, 9.5, 236.0, 44.3
BUBBLE = (49.5, 64.5, 156.2, 95.2, 24.0)   # x, y, w, h, rx
# The tail's top edge is tucked inside the bubble, so only the pointer shows.
TAIL = ((79.5, 140.0), (79.5, 199.8), (113.0, 159.7))
DOTS_CY, DOTS_R = 117.1, 10.65
DOTS_CX = (89.7, 127.7, 165.7)

# Ribbon band, expressed as distance along the lower-right diagonal:
# u(x, y) = (x + y) / sqrt(2).  The plate's far corner sits at u = 329.
RIBBON_U_INNER, RIBBON_U_OUTER = 266.0, 308.0
WORD_HEIGHT = 26.0       # cap height of "DEMO" inside the band
WORD_TRACKING = 4.0      # gap between letterforms


def _rot45(x: float, y: float) -> tuple[float, float]:
    """Rotate (x, y) by -45 degrees about the plate centre.

    Lets the ribbon be laid out in a comfortable upright frame and then be
    mapped onto the lower-right diagonal, without asking the SVG renderer to
    honour a transform attribute.
    """
    c = VIEW / 2.0
    k = math.sqrt(0.5)
    dx, dy = x - c, y - c
    return c + (dx + dy) * k, c + (dy - dx) * k


def _poly(points: list[tuple[float, float]], fill: str, rotate: bool) -> str:
    pts = [_rot45(x, y) if rotate else (x, y) for x, y in points]
    body = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
    return f'<polygon points="{body}" fill="{fill}"/>'


def _rect_poly(x: float, y: float, w: float, h: float) -> list[tuple[float, float]]:
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def _plate_outline(arc_steps: int = 12) -> list[tuple[float, float]]:
    """The rounded-square plate traced as a polygon, corners included.

    The ribbon is intersected with this in Python rather than with an SVG
    ``clip-path``: ImageMagick's built-in SVG renderer silently ignores
    clip-path, which let an unclipped band run square out to the canvas corner.
    """
    x0, y0 = PLATE_X, PLATE_Y
    x1, y1 = PLATE_X + PLATE_WH, PLATE_Y + PLATE_WH
    r = PLATE_R
    corners = (                       # (centre, start angle) going clockwise
        ((x1 - r, y0 + r), -90.0),    # top-right
        ((x1 - r, y1 - r), 0.0),      # bottom-right
        ((x0 + r, y1 - r), 90.0),     # bottom-left
        ((x0 + r, y0 + r), 180.0),    # top-left
    )
    points = [(x0 + r, y0)]
    for (cx, cy), start in corners:
        for i in range(arc_steps + 1):
            a = math.radians(start + 90.0 * i / arc_steps)
            points.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return points


def _clip_halfplane(
    poly: list[tuple[float, float]], a: float, b: float, c: float
) -> list[tuple[float, float]]:
    """Sutherland-Hodgman clip of ``poly`` to the half-plane a*x + b*y <= c."""
    out: list[tuple[float, float]] = []
    for i, current in enumerate(poly):
        previous = poly[i - 1]
        d_cur = a * current[0] + b * current[1] - c
        d_prev = a * previous[0] + b * previous[1] - c
        if (d_cur <= 0) != (d_prev <= 0):
            t = d_prev / (d_prev - d_cur)
            out.append((previous[0] + t * (current[0] - previous[0]),
                        previous[1] + t * (current[1] - previous[1])))
        if d_cur <= 0:
            out.append(current)
    return out


# ── "DEMO" letterforms ─────────────────────────────────────────────────────
# Each letter is a list of (points, is_counter) shapes on a 0..WORD_HEIGHT
# vertical box.  Counters (the holes in D and O) are painted in the ribbon
# colour over the solid outer shape — the ribbon is a flat fill, so the result
# is identical to a real hole and needs no fill-rule support.
def _letter_d(h: float) -> tuple[float, list[tuple[list[tuple[float, float]], bool]]]:
    w, s, c = 0.77 * h, 0.19 * h, 0.23 * h
    outer = [(0, 0), (w - c, 0), (w, c), (w, h - c), (w - c, h), (0, h)]
    inner = [(s, s), (w - c - s * 0.4, s), (w - s, c + s * 0.4),
             (w - s, h - c - s * 0.4), (w - c - s * 0.4, h - s), (s, h - s)]
    return w, [(outer, False), (inner, True)]


def _letter_e(h: float) -> tuple[float, list[tuple[list[tuple[float, float]], bool]]]:
    w, s = 0.66 * h, 0.19 * h
    return w, [
        (_rect_poly(0, 0, w, s), False),
        (_rect_poly(0, (h - s) / 2, w * 0.82, s), False),
        (_rect_poly(0, h - s, w, s), False),
        (_rect_poly(0, 0, s, h), False),
    ]


def _letter_m(h: float) -> tuple[float, list[tuple[list[tuple[float, float]], bool]]]:
    w, s = 0.94 * h, 0.19 * h
    mid = w / 2.0
    outer = [
        (0, 0), (s * 1.2, 0), (mid, 0.46 * h), (w - s * 1.2, 0), (w, 0),
        (w, h), (w - s, h), (w - s, 0.36 * h), (mid + s * 0.55, 0.74 * h),
        (mid - s * 0.55, 0.74 * h), (s, 0.36 * h), (s, h), (0, h),
    ]
    return w, [(outer, False)]


def _letter_o(h: float) -> tuple[float, list[tuple[list[tuple[float, float]], bool]]]:
    w, s, c = 0.80 * h, 0.19 * h, 0.23 * h
    outer = [(c, 0), (w - c, 0), (w, c), (w, h - c), (w - c, h), (c, h), (0, h - c), (0, c)]
    inner = [(c + s * 0.4, s), (w - c - s * 0.4, s), (w - s, c + s * 0.4),
             (w - s, h - c - s * 0.4), (w - c - s * 0.4, h - s), (c + s * 0.4, h - s),
             (s, h - c - s * 0.4), (s, c + s * 0.4)]
    return w, [(outer, False), (inner, True)]


_GLYPHS = {"D": _letter_d, "E": _letter_e, "M": _letter_m, "O": _letter_o}


def _word(text: str, cx: float, cy: float, h: float) -> str:
    """Render ``text`` centred on (cx, cy) in the upright pre-rotation frame."""
    glyphs = [_GLYPHS[ch](h) for ch in text]
    total = sum(w for w, _ in glyphs) + WORD_TRACKING * (len(glyphs) - 1)
    pen, top = cx - total / 2.0, cy - h / 2.0
    out = []
    for w, shapes in glyphs:
        for points, is_counter in shapes:
            moved = [(pen + px, top + py) for px, py in points]
            out.append(_poly(moved, RIBBON_BG if is_counter else RIBBON_FG, rotate=True))
        pen += w + WORD_TRACKING
    return "".join(out)


def _ribbon() -> str:
    """The lower-right "DEMO" corner band, already clipped to the plate."""
    k = math.sqrt(2.0)
    band = _plate_outline()
    band = _clip_halfplane(band, 1.0, 1.0, RIBBON_U_OUTER * k)    # x + y <= outer
    band = _clip_halfplane(band, -1.0, -1.0, -RIBBON_U_INNER * k)  # x + y >= inner
    assert band, "ribbon band does not intersect the plate — check RIBBON_U_*"

    # The word is laid out upright and then rotated onto the diagonal, centred
    # on the band.  In the rotated frame the band's distance from the plate
    # centre along y is just u minus the centre's own u.
    c = VIEW / 2.0
    u_centre = (c + c) / k
    y_word = c + ((RIBBON_U_INNER + RIBBON_U_OUTER) / 2.0 - u_centre)
    return (_poly(band, RIBBON_BG, rotate=False)
            + _word("DEMO", c, y_word, WORD_HEIGHT))


def icon_svg(edition: str, ribbon: bool) -> str:
    """The full icon as an SVG string."""
    plate = PLATE[edition]
    bx, by, bw, bh, brx = BUBBLE
    body = [
        f'<rect x="{PLATE_X}" y="{PLATE_Y}" width="{PLATE_WH}" height="{PLATE_WH}"'
        f' rx="{PLATE_R}" fill="{plate}"/>',
        f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="{brx}" fill="{WHITE}"/>',
        _poly(list(TAIL), WHITE, rotate=False),
    ]
    body += [
        f'<circle cx="{cx}" cy="{DOTS_CY}" r="{DOTS_R}" fill="{plate}"/>'
        for cx in DOTS_CX
    ]
    if ribbon:
        body.append(_ribbon())
    # Every shape is drawn inside the plate on purpose — no clip-path, no
    # group transform, nothing the simplest SVG renderer could drop.
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW:.0f} {VIEW:.0f}">'
        f'{"".join(body)}</svg>'
    )


# ── Rasterisation ──────────────────────────────────────────────────────────
@functools.lru_cache(maxsize=1)
def _magick() -> str:
    """The ImageMagick entry point: `magick` on v7, `convert` on v6."""
    for candidate in ("magick", "convert"):
        try:
            subprocess.run([candidate, "-version"], check=True, capture_output=True)
            return candidate
        except (OSError, subprocess.CalledProcessError):
            continue
    sys.exit("gen_icons.py needs ImageMagick on PATH (`brew install imagemagick`).")


def render_png(edition: str, size: int, dest: Path) -> Path:
    """Rasterise one edition at ``size`` px; only the demo gets the ribbon."""
    svg = icon_svg(edition, ribbon=edition == "demo" and size >= RIBBON_MIN_PX)
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as fh:
        fh.write(svg)
        src = Path(fh.name)
    try:
        # Supersample and filter down: ImageMagick's built-in SVG renderer
        # anti-aliases poorly, and at 32 px the dots are three pixels across.
        render_at = min(size * SUPERSAMPLE, max(size, SUPERSAMPLE_CAP))
        # -density is dots per inch, not a pixel count: this SVG declares no
        # width or height, so MSVG scales the 256-unit viewBox by density/96
        # and actually rasterises at 8/3 x render_at before the forced resize
        # brings it back.  That is where most of the supersampling happens, and
        # it is why SUPERSAMPLE_CAP earns its keep: the uncapped 4096 that the
        # 1024 px frame would otherwise ask for is a 10922-square canvas —
        # gigabytes under a Q16-HDRI build — not the 4096-square one the
        # arithmetic above reads like.  Raise the cap only with that in mind.
        #
        # MSVG: pins ImageMagick's own rasteriser.  Plain `foo.svg` hands the
        # file to librsvg — compiled in, or shelled out to as the `svg:decode`
        # delegate — whenever it is present, and librsvg anti-aliases
        # differently, so the committed PNGs would come back changed on a
        # machine that happens to have it.  This drawing needs nothing librsvg
        # offers, so asking for the simple renderer by name costs nothing and
        # makes the output depend on the ImageMagick build alone.
        subprocess.run(
            [_magick(), "-background", "none", "-density", str(render_at),
             "MSVG:" + str(src), "-resize", f"{render_at}x{render_at}!",
             "-filter", "Lanczos", "-resize", f"{size}x{size}!",
             "-depth", "8", "-strip", "PNG32:" + str(dest)],
            check=True,
        )
    finally:
        src.unlink(missing_ok=True)
    return dest


ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

# ICNS chunk type -> pixel size, for the types that carry a plain PNG payload.
ICNS_PNG_TYPES = (
    (b"ic11", 32), (b"ic12", 64), (b"ic07", 128), (b"ic13", 256),
    (b"ic08", 256), (b"ic14", 512), (b"ic09", 512), (b"ic10", 1024),
)

# The 1x 16 pt and 32 pt representations.  The ICNS format does define
# PNG-capable types at these two sizes (icp4/icp5), but neither Apple's
# `iconutil` nor the base app's committed icon.icns uses them: both carry
# ic04/ic05, which are run-length-encoded ARGB.  Omitting them is not fatal
# — macOS scales the nearest representation down — but it costs exactly the
# small-size sharpness this icon exists to provide, on every 1x display.
ICNS_ARGB_TYPES = ((b"ic04", 16), (b"ic05", 32))

ICNS_SIZES = tuple(sorted(
    {s for _, s in ICNS_PNG_TYPES} | {s for _, s in ICNS_ARGB_TYPES}
))

def write_ico(frames: dict[int, Path], dest: Path, sizes: tuple[int, ...]) -> None:
    """Assemble an ICO holding each frame as its PNG bytes.

    Written here rather than handed to ImageMagick because its ICO coder
    stores every frame as an uncompressed DIB — a 256 px frame alone costs
    256 KB, which is how a seven-frame icon turns into a third of a megabyte.
    PNG payloads are what Windows has read since Vista and what the base app's
    committed `icon.ico` already carries, so the demo's matches it.

    Nothing Steamworks takes is built here: its Shortcut Icon field accepts a
    plain PNG and generates the .ico itself, so this writer only ever produces
    the bundle's `icon.ico`.
    """
    payloads = [frames[s].read_bytes() for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = len(header) + 16 * len(sizes)
    entries, body = b"", b""
    for size, payload in zip(sizes, payloads):
        # 256 is encoded as 0 in the single-byte width/height fields. Planes
        # and bit depth are ignored for PNG payloads; 0/32 is what the base
        # app's working icon.ico carries.
        dim = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII", dim, dim, 0, 0, 0, 32, len(payload), offset
        )
        body += payload
        offset += len(payload)
    dest.write_bytes(header + entries + body)


def _rgba_bytes(png: Path) -> bytes:
    """The frame's raw, straight-alpha RGBA samples, row by row."""
    return subprocess.run(
        [_magick(), "PNG:" + str(png), "-depth", "8", "RGBA:-"],
        check=True, capture_output=True,
    ).stdout


def _packbits(data: bytes) -> bytes:
    """ICNS run-length encoding of one colour channel.

    The variant ICNS uses, not the QuickTime one: a control byte below 128
    introduces ``n + 1`` literal bytes, and one at or above 128 repeats the
    next byte ``n - 125`` times — so a run only pays for itself at three.
    The decoder stops once it has the channel's pixel count, so there is no
    terminator; the channels are concatenated in A, R, G, B order.
    """
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
    ``iconutil`` itself writes.

    Do not check these two chunks with ``iconutil -c iconset``. It un-
    premultiplies on the way out, so every partly transparent pixel comes back
    blown out toward white — a 16 px edge pixel of this icon reads
    (255, 159, 255) instead of (109, 40, 217). That is an artefact of the
    export path, not of the file: build an ICNS from these same frames with
    ``iconutil -c icns`` and extract it again and Apple's own output is damaged
    identically. Check with the renderer macOS actually draws icons through
    instead — ``NSImage(contentsOfFile:)``, then ``colorAt`` on the
    representation of the size you care about — which reads these chunks back
    exactly, and reads Apple's own within a level or two.
    """
    rgba = _rgba_bytes(png)
    assert len(rgba) == size * size * 4, f"{png}: expected {size}x{size} RGBA"
    channels = (rgba[3::4], rgba[0::4], rgba[1::4], rgba[2::4])
    return b"ARGB" + b"".join(_packbits(c) for c in channels)


def write_icns(frames: dict[int, Path], dest: Path) -> None:
    """Assemble an ICNS from PNG frames.

    The format is a four-byte magic, a big-endian total length, then one
    ``[type][length][payload]`` chunk per representation.  Most types take the
    PNG bytes verbatim; ``ic04``/``ic05`` are the two that do not, and are
    built from the same frames as run-length-encoded ARGB.  No platform
    tooling is needed either way, so the set builds on Linux and Windows too.
    """
    chunks = b""
    for kind, size in ICNS_PNG_TYPES:
        payload = frames[size].read_bytes()
        chunks += kind + struct.pack(">I", len(payload) + 8) + payload
    for kind, size in ICNS_ARGB_TYPES:
        payload = _argb_chunk(frames[size], size)
        chunks += kind + struct.pack(">I", len(payload) + 8) + payload
    dest.write_bytes(b"icns" + struct.pack(">I", len(chunks) + 8) + chunks)


# The PNG members of Tauri's five-file `bundle.icon` list, by pixel size;
# icon.ico and icon.icns are the other two and are assembled below.
BUNDLE_PNGS = ((32, "32x32.png"), (128, "128x128.png"), (256, "128x128@2x.png"))

# Steamworks "Community and Client Icons".  Both are required fields, and they
# are the pair that issue #499 is actually about: the App Icon is what the
# Steam client draws in the library list, where the demo and the full game
# looked the same, and the Shortcut Icon is what lands on the desktop.
APP_ICON_PX = 184       # App Icon: 184x184 JPG
SHORTCUT_ICON_PX = 256  # Shortcut Icon: 256x256 (512 also taken) .ico/.png


def write_app_icon(png: Path, dest: Path) -> None:
    """Flatten a frame onto the capsule base colour and write it as JPEG.

    Steamworks wants this one as a JPG, which has no alpha channel, so the
    plate's rounded corners have to be composited against something. They go
    onto RIBBON_BG — the near-black the whole capsule set sits on — rather
    than onto the plate colour, so the corners stay visible and the icon reads
    as part of the same family as the store art.

    4:4:4 sampling, because chroma subsampling on a 184 px icon smears the
    plate edge and the ribbon's lettering, and both of those are what the
    asset exists to show. ``-strip`` drops the profile and any timestamp, and
    the Huffman tables are optimised rather than left at libjpeg's defaults so
    the file does not depend on which default a build happens to carry.

    Even so this is the one output whose bytes are not promised across
    machines — see the module docstring. Judge a regenerated .jpg by looking
    at it, not by ``git diff``.
    """
    subprocess.run(
        [_magick(), "PNG:" + str(png), "-background", RIBBON_BG,
         "-alpha", "remove", "-alpha", "off", "-strip",
         "-sampling-factor", "1x1", "-quality", "95",
         "-define", "jpeg:optimize-coding=true", "JPEG:" + str(dest)],
        check=True,
    )


def build(edition: str, bundle_dir: Path, steam_dir: Path) -> list[Path]:
    """Write one edition's bundle icon set and its Steamworks icons."""
    bundle_dir.mkdir(parents=True, exist_ok=True)
    steam_dir.mkdir(parents=True, exist_ok=True)
    needed = sorted({*ICO_SIZES, *ICNS_SIZES, *(s for s, _ in BUNDLE_PNGS),
                     APP_ICON_PX, SHORTCUT_ICON_PX})
    written = []
    with tempfile.TemporaryDirectory() as tmp:
        frames = {
            s: render_png(edition, s, Path(tmp) / f"{s}.png") for s in needed
        }
        for size, name in BUNDLE_PNGS:
            dest = bundle_dir / name
            dest.write_bytes(frames[size].read_bytes())
            written.append(dest)

        ico = bundle_dir / "icon.ico"
        write_ico(frames, ico, ICO_SIZES)
        written.append(ico)

        icns = bundle_dir / "icon.icns"
        write_icns(frames, icns)
        written.append(icns)

        # Steamworks App Icon: the 184 px JPG the Steam client draws beside
        # the app name in the library list, in chat favourites and in
        # notifications.  This is the asset in issue #499's screenshot — the
        # one that made the demo and the full game indistinguishable there.
        app_icon = steam_dir / f"{edition}_app_icon.jpg"
        write_app_icon(frames[APP_ICON_PX], app_icon)
        written.append(app_icon)

        # Steamworks Shortcut Icon: 256 px, for the desktop shortcut Steam
        # creates.  Valve accepts a PNG here and generates the .ico itself, so
        # this is simply the same 256 px frame the app installs — no hand-built
        # container between the mark and the shortcut.
        shortcut = steam_dir / f"{edition}_shortcut_icon.png"
        shortcut.write_bytes(frames[SHORTCUT_ICON_PX].read_bytes())
        written.append(shortcut)

    # The large-frame artwork as vector, next to the uploads: for reading
    # the mark and re-rendering it at sizes this script does not emit.  It is
    # the >= RIBBON_MIN_PX drawing — the demo render always carries the ribbon,
    # so re-render from here only at 128 px and up; below that the word is the
    # mush RIBBON_MIN_PX exists to avoid, and the frame to use is the one
    # render_png emits (or icon_svg(edition, ribbon=False)).  It is generated
    # output, overwritten on every run — the mark's source of truth is the
    # geometry above, so edits belong there and not in the .svg.
    svg = steam_dir / f"{edition}_icon.svg"
    svg.write_text(icon_svg(edition, ribbon=edition == "demo"))
    written.append(svg)
    return written


# Where each edition lands with no --out.  Only the demo writes into the repo:
# the base set in apps/desktop/src-tauri/icons/ is the original `tauri icon`
# output, and this script must never overwrite it by accident.
DEMO_BUNDLE_DIR = REPO_ROOT / "apps" / "desktop" / "src-tauri" / "icons-demo"
STEAM_ICON_DIR = REPO_ROOT / "publishing" / "assets" / "icons"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--edition", choices=("base", "demo", "all"), default="demo")
    ap.add_argument(
        "--out",
        type=Path,
        help="write everything under this directory instead of the committed "
             "locations; always use it when rendering the base edition for "
             "comparison",
    )
    args = ap.parse_args()

    editions = ("base", "demo") if args.edition == "all" else (args.edition,)
    for edition in editions:
        if args.out is not None:
            bundle_dir = args.out / edition if len(editions) > 1 else args.out
            steam_dir = bundle_dir
        elif edition == "demo":
            bundle_dir, steam_dir = DEMO_BUNDLE_DIR, STEAM_ICON_DIR
        else:
            scratch = Path(tempfile.gettempdir()) / "convsim-icons-base"
            bundle_dir, steam_dir = scratch, scratch
        for path in build(edition, bundle_dir, steam_dir):
            print(f"{edition}: {path}")


if __name__ == "__main__":
    main()
