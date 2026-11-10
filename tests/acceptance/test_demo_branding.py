# SPDX-License-Identifier: Apache-2.0
"""Acceptance tests — demo-edition branding (issue #499, demo gate D-10).

The Steam Demo app (5343430) shipped the base app's icon because
``tauri.demo.conf.json`` overlaid the product name but not ``bundle.icon``, so
the demo and the full game were indistinguishable in the Steam client. These
tests pin the fix from both ends:

  * the demo overlay overrides every icon the base config declares, and each
    override resolves to a real file;
  * the demo icons are the same mark on a visibly different plate — a colour
    distance the eye cannot miss at 32 px, with the silhouette left alone so
    the demo still reads as the same product;
  * the "DEMO" ribbon is on the large frames and off the small ones, because
    the word is unreadable at the 16-32 px the taskbar and the library row
    actually draw — and where it is drawn, the band really does spell the word;
  * the hand-written ICO and ICNS containers carry every representation the
    base app's do, each one holds the size its directory entry or chunk type
    promises, and the ones that are not PNG decode back to the frame they were
    built from;
  * the two Steamworks icons exist at the sizes Valve's spec names — App Icon
    184 x 184 JPG, Shortcut Icon 256 x 256 PNG (512 is the only other size
    Valve takes there) — and the shortcut icon is the same image the app
    itself installs.

The App Icon is the one the issue's screenshot is about: Valve's spec says it
is what the Steam client draws "in the library list view, 'favorites' in chat,
and notifications", which is exactly the sidebar row where the demo and the
full game read as the same product.

Issue #551 is the same gap one level up: the demo app had no capsule or
library art at all, so its library entry and store presence rendered blank.
D-10g pins the demo capsule set ``gen_capsules.py --edition demo`` writes to
``publishing/assets/capsules/demo/``: every asset at Valve's exact size, on
the demo icon's purple plate rather than the full game's near-black stage,
with the icon's "DEMO" ribbon in the lower-right corner of every asset allowed
to carry the name — clear of the composition — and none on the library hero.

Nothing here needs a build or a network, and only the JPEG's pixels need
ImageMagick — the PNGs, the ICO and the ICNS are parsed directly, and the
JPEG's dimensions come straight out of its SOF marker. The CI acceptance job
installs ImageMagick for those three pixel checks; without it they skip on a
developer machine and fail under CI, so a runner image that stops shipping it
cannot quietly drop the App Icon from the gate. Owner: platform team.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import shutil
import struct
import subprocess
import zlib
from collections import Counter
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_TAURI = _REPO_ROOT / "apps" / "desktop" / "src-tauri"
_BASE_CONF = _SRC_TAURI / "tauri.conf.json"
_DEMO_CONF = _SRC_TAURI / "tauri.demo.conf.json"
_ICON_DIR = _REPO_ROOT / "publishing" / "assets" / "icons"
_APP_ICON = _ICON_DIR / "demo_app_icon.jpg"
_SHORTCUT_ICON = _ICON_DIR / "demo_shortcut_icon.png"
_DEMO_SVG = _ICON_DIR / "demo_icon.svg"
_ASSET_SOURCE = _REPO_ROOT / "publishing" / "assets" / "source"
_GEN_ICONS = _ASSET_SOURCE / "gen_icons.py"
_GEN_CAPSULES = _ASSET_SOURCE / "gen_capsules.py"
_CAPSULE_DIR = _REPO_ROOT / "publishing" / "assets" / "capsules"
_DEMO_CAPSULE_DIR = _CAPSULE_DIR / "demo"

# Plate colours from publishing/assets/source/gen_icons.py.
_BASE_PLATE = (0x14, 0x7A, 0x84)
_DEMO_PLATE = (0x6D, 0x28, 0xD9)
_RIBBON_BG = (0x0D, 0x0D, 0x15)
_RIBBON_FG = (0xF4, 0xF4, 0xF5)
_WHITE = (0xFF, 0xFF, 0xFF)

# The ribbon band, as gen_icons.py places it: distance along the lower-right
# diagonal, u(x, y) = (x + y) / sqrt(2), in the 256-unit viewBox the mark is
# drawn in.  Restated here rather than imported so that moving the band in the
# generator without meaning to is a failure, not a silently relocated ribbon.
_VIEW = 256.0
_RIBBON_U_INNER, _RIBBON_U_OUTER = 266.0, 308.0

# Steamworks, Store Presence -> Graphical Assets -> Community and Client Icons
# (https://partner.steamgames.com/doc/store/assets/community).  Both fields are
# required, and neither is the 32 px ".ico" a reader might expect: the sizes are
# restated here so a drift in gen_icons.py fails rather than ships an asset
# Valve's uploader rejects.
_APP_ICON_PX = 184       # App Icon: 184x184 JPG — the library-list row
# Shortcut Icon: Valve takes 256x256 or 512x512, .ico or .png.  This pins the
# 256 the generator emits, which is the frame the bundle already ships; a move
# to 512 is a deliberate change to both sides, not a drift.
_SHORTCUT_ICON_PX = 256

# Below this the two icons would start to look alike in a library list.  The
# teal/purple pair measures ~148, so there is room to retune either plate; the
# point of the floor is to fail a future "subtle" recolour, not to be a tight fit.
_MIN_PLATE_DISTANCE = 100.0

# Steamworks capsule and library sizes
# (https://partner.steamgames.com/doc/store/assets), restated so a drift in
# gen_capsules.py fails here rather than in Valve's uploader.  The demo set is
# all of these; the full game's adds page_background.
_CAPSULE_SIZES = {
    "header_capsule": (920, 430),
    "small_capsule": (462, 174),
    "main_capsule": (1232, 706),
    "vertical_capsule": (748, 896),
    "library_capsule": (600, 900),
    "library_header": (920, 430),
    "library_hero": (3840, 1240),
    "library_logo": (1280, 720),     # transparent PNG
}
_BASE_ONLY_CAPSULES = {"page_background": (1438, 810)}
# The assets that carry the game name, and so may carry "DEMO".  The hero must
# stay textless (Steam lays the logo over it) and the logo has no corner.
_RIBBONED_CAPSULES = ("header_capsule", "small_capsule", "main_capsule",
                      "vertical_capsule", "library_capsule", "library_header")
_OPAQUE_CAPSULES = tuple(n for n in _CAPSULE_SIZES if n != "library_logo")

# The full game's capsule stage, lower and upper band (gen_capsules.py).
_BASE_STAGE = ((0x0D, 0x0D, 0x15), (0x12, 0x12, 0x1C))
# The demo stage: the icon plate above, a step darker below.
_DEMO_LOWER_BAND = (0x5B, 0x21, 0xB6)

# Ribbon placement on a capsule, restated from gen_capsules.py: the icon's
# 256-unit frame, plate corner (245.5, 245.5) pinned to the capsule's
# lower-right corner and scaled as a demo icon 0.6 x the capsule's
# geometric-mean side.  The band edges themselves are _RIBBON_U_* above.
_PLATE_CORNER = 245.5
_CAPSULE_RIBBON_ICON_SIDE = 0.6
# Fraction of the band's width that must stay clear inside its inner edge.
_CAPSULE_RIBBON_CLEARANCE = 0.4


# ---------------------------------------------------------------------------
# Minimal PNG reader — enough for the 8-bit RGBA icons this repo generates.
# ---------------------------------------------------------------------------
def _read_png(path: Path) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    """Return (width, height, RGBA pixels) for an 8-bit truecolour-alpha PNG."""
    return _decode_png(path.read_bytes(), path)


def _decode_png(raw: bytes, path: object) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    """As ``_read_png``, for PNG bytes already in hand (an ICO frame)."""
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    pos, idat, header = 8, b"", None
    while pos < len(raw):
        (length,) = struct.unpack(">I", raw[pos:pos + 4])
        kind = raw[pos + 4:pos + 8]
        payload = raw[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            idat += payload
        pos += length + 12

    assert header is not None, f"{path} has no IHDR"
    width, height, depth, colour, _, _, interlace = header
    assert (depth, colour, interlace) == (8, 6, 0), (
        f"{path} is not an 8-bit non-interlaced RGBA PNG: {header}"
    )

    data = zlib.decompress(idat)
    stride = width * 4
    out: list[tuple[int, int, int, int]] = []
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        filter_type = data[pos]
        line = bytearray(data[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        for i in range(stride):
            left = line[i - 4] if i >= 4 else 0
            up = prev[i]
            up_left = prev[i - 4] if i >= 4 else 0
            if filter_type == 1:
                line[i] = (line[i] + left) & 0xFF
            elif filter_type == 2:
                line[i] = (line[i] + up) & 0xFF
            elif filter_type == 3:
                line[i] = (line[i] + (left + up) // 2) & 0xFF
            elif filter_type == 4:
                p = left + up - up_left
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - up_left)
                best = left if (pa <= pb and pa <= pc) else (up if pb <= pc else up_left)
                line[i] = (line[i] + best) & 0xFF
            elif filter_type != 0:
                raise AssertionError(f"{path}: unsupported PNG filter {filter_type}")
        out.extend(
            (line[i], line[i + 1], line[i + 2], line[i + 3])
            for i in range(0, stride, 4)
        )
        prev = line
    return width, height, out


def _png_dimensions(raw: bytes) -> tuple[int, int]:
    """(width, height) straight out of the IHDR, without decoding the pixels.

    Used to check the containers' own bookkeeping — an ICO directory entry or
    an ICNS chunk type against the frame it actually holds — where inflating a
    1024 px frame in pure Python would cost seconds for no extra assurance.
    """
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG payload"
    assert raw[12:16] == b"IHDR", "first chunk is not IHDR"
    return struct.unpack(">II", raw[16:24])


class _Raster:
    """Pixel access to an 8-bit non-interlaced PNG: RGB, RGBA or palette.

    For the capsules, which run to 3840 x 1240 — far past what ``_read_png``'s
    tuple-per-pixel decode can do in a test's time.  Rows are kept as bytes
    and only sampled pixels are looked at.  A row stored with filter type 0
    costs nothing to read, and gen_capsules.py writes every row that way; any
    other filter is still decoded correctly, just at pure-Python speed.
    """

    def __init__(self, path: Path):
        raw = path.read_bytes()
        assert raw[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
        pos, idat, header, palette, trns = 8, b"", None, b"", b""
        while pos < len(raw):
            (length,) = struct.unpack(">I", raw[pos:pos + 4])
            kind = raw[pos + 4:pos + 8]
            payload = raw[pos + 8:pos + 8 + length]
            if kind == b"IHDR":
                header = struct.unpack(">IIBBBBB", payload)
            elif kind == b"PLTE":
                palette = payload
            elif kind == b"tRNS":
                trns = payload
            elif kind == b"IDAT":
                idat += payload
            pos += length + 12
        assert header is not None, f"{path} has no IHDR"
        self.width, self.height, depth, self.colour, _, _, interlace = header
        assert depth == 8 and interlace == 0 and self.colour in (2, 3, 6), (
            f"{path}: unsupported PNG layout {header}"
        )
        self.alpha = self.colour == 6
        self.palette = [tuple(palette[i:i + 3]) for i in range(0, len(palette), 3)]
        self.trns = trns
        bpp = {2: 3, 3: 1, 6: 4}[self.colour]
        self.bpp = bpp
        stride = self.width * bpp
        data = zlib.decompress(idat)
        rows: list[bytes] = []
        prev = bytes(stride)
        pos = 0
        for _ in range(self.height):
            filter_type = data[pos]
            line = data[pos + 1:pos + 1 + stride]
            pos += 1 + stride
            if filter_type != 0:
                line = self._unfilter(filter_type, bytearray(line), prev, bpp, path)
            rows.append(line)
            prev = line
        self.rows = rows

    @staticmethod
    def _unfilter(kind: int, line: bytearray, prev: bytes, bpp: int, path: Path) -> bytes:
        for i in range(len(line)):
            left = line[i - bpp] if i >= bpp else 0
            up = prev[i]
            up_left = prev[i - bpp] if i >= bpp else 0
            if kind == 1:
                line[i] = (line[i] + left) & 0xFF
            elif kind == 2:
                line[i] = (line[i] + up) & 0xFF
            elif kind == 3:
                line[i] = (line[i] + (left + up) // 2) & 0xFF
            elif kind == 4:
                p = left + up - up_left
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - up_left)
                best = left if (pa <= pb and pa <= pc) else (up if pb <= pc else up_left)
                line[i] = (line[i] + best) & 0xFF
            else:
                raise AssertionError(f"{path}: unsupported PNG filter {kind}")
        return bytes(line)

    def rgba(self, x: int, y: int) -> tuple[int, int, int, int]:
        row = self.rows[y]
        if self.colour == 3:
            index = row[x]
            alpha = self.trns[index] if index < len(self.trns) else 255
            return (*self.palette[index], alpha)
        i = x * self.bpp
        if self.colour == 2:
            return row[i], row[i + 1], row[i + 2], 255
        return row[i], row[i + 1], row[i + 2], row[i + 3]

    def sample(self, step: int):
        """Every ``step``-th pixel in both directions, as (x, y, rgba)."""
        for y in range(0, self.height, step):
            for x in range(0, self.width, step):
                yield x, y, self.rgba(x, y)

    def diagonal_strip(self, lo: float, hi: float):
        """The pixels whose centres satisfy lo <= x + y <= hi, as (x, y, rgba).

        The ribbon band, its clearance and the corner tip beyond it are all
        such strips across the lower-right corner, so only they are read.
        """
        w, h = self.width, self.height
        for y in range(max(0, int(lo) - w - 1), h):
            x0 = max(0, math.floor(lo - y - 1))
            x1 = min(w - 1, math.ceil(hi - y - 1))
            for x in range(x0, x1 + 1):
                if lo <= x + y + 1 <= hi:
                    yield x, y, self.rgba(x, y)


def _find_magick() -> str | None:
    """ImageMagick's command-line entry point, or None when it is not installed.

    ``magick`` is ImageMagick 7's binary and nothing else installs one under
    that name, so it is taken at its word. ``convert`` is ImageMagick 6's, but
    Windows ships a ``convert.exe`` of its own in System32 (the NTFS volume
    converter), so that name is believed only when ``convert -version`` says
    ImageMagick. Otherwise the tests that need it skip as documented instead
    of erroring on the wrong program.
    """
    magick = shutil.which("magick")
    if magick is not None:
        return magick
    convert = shutil.which("convert")
    if convert is None:
        return None
    try:
        probe = subprocess.run([convert, "-version"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return convert if b"ImageMagick" in probe.stdout else None


_MAGICK = _find_magick()


def _running_in_ci() -> bool:
    """GitHub Actions sets ``CI=true``; other runners set it to something truthy too."""
    return os.environ.get("CI", "").strip().lower() not in ("", "0", "false")


def _require_magick() -> str:
    """The ImageMagick binary, or the test's verdict on not having one.

    On a developer machine without ImageMagick the App Icon's pixel checks
    skip: the JPEG is the one asset here with no pure-Python reader, and a
    baseline-JPEG decoder for one 184 px icon would be a worse trade. Under CI
    they fail instead. The acceptance job installs the ``imagemagick`` package
    for exactly these tests, so ImageMagick missing there means the install
    step was dropped or the runner image changed underneath it, and a skip
    would let a wrong App Icon through the gate while the job stayed green.
    """
    if _MAGICK is not None:
        return _MAGICK
    message = (
        "reading the App Icon's pixels needs ImageMagick; its JPEG payload is "
        "the one asset in this suite with no pure-Python reader"
    )
    if _running_in_ci():
        pytest.fail(
            f"{message}. CI is set and ImageMagick is not on PATH: the acceptance "
            "job must install the imagemagick package (apt) before running this "
            "suite, or the App Icon ships unchecked",
            pytrace=False,
        )
    pytest.skip(message)


def _magick_rgb(path: Path, size: int) -> list[tuple[int, int, int]]:
    """``size * size`` RGB pixels, read through ImageMagick.

    Only the App Icon needs this: everything else here is PNG, ICO or ICNS and
    is parsed in-process. Without ImageMagick the calling test skips locally
    and fails under CI; see ``_require_magick``.
    """
    magick = _require_magick()
    raw = subprocess.run(
        [magick, str(path), "-depth", "8", "RGB:-"],
        check=True, capture_output=True,
    ).stdout
    assert len(raw) == size * size * 3, (
        f"{path}: expected {size}x{size} RGB, got {len(raw)} bytes"
    )
    return [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]


def _plate_colour(path: Path) -> tuple[int, int, int]:
    """The icon's dominant opaque colour — in practice the rounded-square plate."""
    _, _, pixels = _read_png(path)
    opaque = Counter((r, g, b) for r, g, b, a in pixels if a == 255)
    assert opaque, f"{path} has no fully opaque pixels"
    return opaque.most_common(1)[0][0]


def _distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _mark_mask(path: Path) -> set[tuple[int, int]]:
    """``{(x, y)}`` of the opaque near-white pixels outside the ribbon band.

    White is the mark: the speech bubble and its tail, with the three
    plate-coloured dots as holes in it. The ribbon's lettering is white as
    well, so the band is cut out of every frame alike, whichever edition it
    is; the base has no ribbon, and its absence must not read as a missing
    mark.
    """
    width, _, pixels = _read_png(path)
    inner = _RIBBON_U_INNER * 2 ** 0.5 * (width / _VIEW)
    mask: set[tuple[int, int]] = set()
    for index, (r, g, b, a) in enumerate(pixels):
        y, x = divmod(index, width)
        if (x + 0.5) + (y + 0.5) >= inner:
            continue
        if a > 128 and _distance((r, g, b), _WHITE) <= 60:
            mask.add((x, y))
    return mask


def _unmatched(mask: set[tuple[int, int]], other: set[tuple[int, int]]) -> int:
    """How many pixels of ``mask`` have no pixel of ``other`` within one step.

    The one-pixel neighbourhood is what lets two anti-aliasers disagree about
    an edge without the masks disagreeing about the mark. A mark that is
    missing, moved or resized by more than a pixel still shows up in full.
    """
    return sum(
        1 for x, y in mask
        if not any(
            (x + dx, y + dy) in other
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)
        )
    )


def _count_near(path: Path, colour: tuple[int, int, int], tolerance: int = 24) -> int:
    _, _, pixels = _read_png(path)
    return sum(
        1 for r, g, b, a in pixels
        if a > 200 and _distance((r, g, b), colour) <= tolerance
    )


def _ribbon_band(path: Path) -> tuple[int, int, int]:
    """(covered, band colour, lettering) pixel counts inside the ribbon band.

    The band is the strip of the plate between ``_RIBBON_U_INNER`` and
    ``_RIBBON_U_OUTER`` along the lower-right diagonal, scaled from the
    256-unit viewBox to the frame.  Looking only inside it is what separates
    the ribbon's own white lettering from the speech bubble's white body.
    """
    width, _, pixels = _read_png(path)
    scale = width / _VIEW
    inner, outer = _RIBBON_U_INNER * 2 ** 0.5 * scale, _RIBBON_U_OUTER * 2 ** 0.5 * scale
    covered = band = word = 0
    for index, (r, g, b, a) in enumerate(pixels):
        y, x = divmod(index, width)
        if not inner <= (x + 0.5) + (y + 0.5) <= outer or a <= 200:
            continue
        covered += 1
        if _distance((r, g, b), _RIBBON_BG) <= 24:
            band += 1
        elif _distance((r, g, b), _RIBBON_FG) <= 24:
            word += 1
    return covered, band, word


def _ribbon_letterforms(path: Path) -> list[int]:
    """Lettering pixel counts, one entry per letterform, reading along the band.

    The ribbon runs down the lower-right diagonal, so the word is laid out
    along ``x - y`` — bucket the band's light pixels by that and the gaps
    ``WORD_TRACKING`` leaves between glyphs show up as empty buckets.  Summing
    a glyph into a single bucket range rather than walking connected pixels is
    what makes this survive a re-render: a counter (the hole in D and O) and a
    hairline stroke the anti-aliasing happens to break in two still read as one
    letterform, while a missing or overlapping glyph does not.
    """
    width, _, pixels = _read_png(path)
    scale = width / _VIEW
    inner, outer = _RIBBON_U_INNER * 2 ** 0.5 * scale, _RIBBON_U_OUTER * 2 ** 0.5 * scale
    columns: dict[int, int] = {}
    for index, (r, g, b, a) in enumerate(pixels):
        y, x = divmod(index, width)
        if not inner <= (x + 0.5) + (y + 0.5) <= outer or a <= 200:
            continue
        if _distance((r, g, b), _RIBBON_FG) <= 24:
            columns[x - y] = columns.get(x - y, 0) + 1
    return _letterform_runs(columns)


def _letterform_runs(columns: dict[int, int]) -> list[int]:
    """Lettering pixel counts per run of consecutive ``x - y`` buckets."""
    if not columns:
        return []
    runs, current = [], [min(columns)]
    for key in sorted(columns)[1:]:
        if key == current[-1] + 1:
            current.append(key)
        else:
            runs.append(current)
            current = [key]
    runs.append(current)
    return [sum(columns[k] for k in run) for run in runs]


# ---------------------------------------------------------------------------
# Minimal ICO reader.
# ---------------------------------------------------------------------------
def _read_ico(path: Path) -> list[tuple[int, int, bytes]]:
    """Return [(width, height, payload)] for each frame in an ICO."""
    raw = path.read_bytes()
    reserved, kind, count = struct.unpack("<HHH", raw[:6])
    assert (reserved, kind) == (0, 1), f"{path} is not an ICO"
    assert count > 0, f"{path} declares no frames"
    frames = []
    for i in range(count):
        entry = raw[6 + i * 16:6 + (i + 1) * 16]
        width, height = entry[0] or 256, entry[1] or 256
        size, offset = struct.unpack("<II", entry[8:16])
        assert offset + size <= len(raw), f"{path} frame {i} runs past end of file"
        frames.append((width, height, raw[offset:offset + size]))
    return frames


# ---------------------------------------------------------------------------
# Minimal JPEG header reader — the App Icon is the one asset that is not PNG.
# ---------------------------------------------------------------------------
def _jpeg_frame(path: Path) -> tuple[int, int, int]:
    """(width, height, component count) from the JPEG's start-of-frame marker.

    Decoding the pixels would mean a Huffman and IDCT implementation for one
    184 px icon; the SOF marker carries everything the spec can be checked
    against, and the pixel check below borrows ImageMagick when it is on PATH.
    """
    raw = path.read_bytes()
    assert raw[:2] == b"\xff\xd8", f"{path} is not a JPEG"
    pos = 2
    while pos < len(raw):
        assert raw[pos] == 0xFF, f"{path}: lost marker alignment at {pos}"
        marker = raw[pos + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        (length,) = struct.unpack(">H", raw[pos + 2:pos + 4])
        # SOF0/1/2 — baseline and progressive. DHT/DAC/SOF4 etc. are not frames.
        if marker in (0xC0, 0xC1, 0xC2):
            _, height, width, components = struct.unpack(
                ">BHHB", raw[pos + 4:pos + 10]
            )
            return width, height, components
        pos += 2 + length
    raise AssertionError(f"{path} has no start-of-frame marker")


# ---------------------------------------------------------------------------
# Minimal ICNS reader.
# ---------------------------------------------------------------------------
# Chunks that hold no plain image: the table of contents, the version and
# metadata blobs Apple's own tooling appends (the base icon.icns carries an
# `info`), and the nested-ICNS variant chunks.  Only image types are required
# of the demo set.
_ICNS_METADATA = {b"TOC ", b"icnV", b"info", b"name", b"sbtp", b"slct"}

# The pixel size each PNG-payload chunk type promises, per the ICNS format.
# ``write_icns`` in gen_icons.py picks the frame for each type off its own copy
# of this table; stating it independently here is what makes a transposed pair
# (ic07 handed the 256 px frame, say) a test failure rather than a shipped icon
# that macOS quietly rescales.
_ICNS_PNG_SIZES = {
    b"ic11": 32, b"ic12": 64, b"ic07": 128, b"ic13": 256,
    b"ic08": 256, b"ic14": 512, b"ic09": 512, b"ic10": 1024,
}


def _read_icns(path: Path) -> dict[bytes, bytes]:
    """Return {chunk type: payload} for an ICNS file."""
    raw = path.read_bytes()
    assert raw[:4] == b"icns", f"{path} is not an ICNS"
    assert struct.unpack(">I", raw[4:8])[0] == len(raw), f"{path}: wrong length field"
    chunks: dict[bytes, bytes] = {}
    pos = 8
    while pos < len(raw):
        kind = raw[pos:pos + 4]
        (length,) = struct.unpack(">I", raw[pos + 4:pos + 8])
        assert 8 < length <= len(raw) - pos, f"{path}: bad chunk length for {kind!r}"
        chunks[kind] = raw[pos + 8:pos + length]
        pos += length
    return chunks


def _unpack_icns_rle(data: bytes, expected: int) -> tuple[bytes, int]:
    """Decode one ARGB channel; returns (samples, bytes consumed).

    A control byte below 128 introduces ``n + 1`` literals, one at or above
    128 repeats the next byte ``n - 125`` times.
    """
    out = bytearray()
    pos = 0
    while len(out) < expected:
        assert pos < len(data), "ARGB channel ends before its pixel count"
        control = data[pos]
        pos += 1
        if control < 128:
            out += data[pos:pos + control + 1]
            pos += control + 1
        else:
            out += bytes([data[pos]]) * (control - 125)
            pos += 1
    assert len(out) == expected, f"ARGB channel overruns: {len(out)} != {expected}"
    return bytes(out), pos


def _icns_argb_last_op(payload: bytes, size: int) -> int:
    """The control byte of the final RLE op in an ``ic04``/``ic05`` payload.

    Below 128 it is a literal run, at or above it a repeat — and a repeat's
    value byte is the one byte a short reader drops. See the test below.
    """
    assert payload[:4] == b"ARGB", f"expected an ARGB payload, got {payload[:4]!r}"
    body, pos = payload[4:], 0
    for _ in range(3):                      # skip A, R and G
        _, used = _unpack_icns_rle(body[pos:], size * size)
        pos += used
    blue, control = body[pos:], None
    pos = 0
    while pos < len(blue):
        control = blue[pos]
        pos += 2 if control >= 128 else 2 + control
    assert control is not None, "the blue channel is empty"
    return control


def _decode_icns_argb(payload: bytes, size: int) -> list[tuple[int, int, int, int]]:
    """Decode an ``ic04``/``ic05`` payload to RGBA pixels."""
    assert payload[:4] == b"ARGB", f"expected an ARGB payload, got {payload[:4]!r}"
    body, pos, channels = payload[4:], 0, []
    for _ in range(4):
        channel, used = _unpack_icns_rle(body[pos:], size * size)
        channels.append(channel)
        pos += used
    assert pos == len(body), f"ARGB payload has {len(body) - pos} trailing bytes"
    alpha, red, green, blue = channels
    return [(red[i], green[i], blue[i], alpha[i]) for i in range(size * size)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def base_icons() -> list[str]:
    return json.loads(_BASE_CONF.read_text())["bundle"]["icon"]


@pytest.fixture(scope="module")
def demo_icons() -> list[str]:
    return json.loads(_DEMO_CONF.read_text())["bundle"]["icon"]


# ---------------------------------------------------------------------------
# D-10a  The demo overlay actually overrides the icons
# ---------------------------------------------------------------------------
class TestDemoOverlayOverridesIcons:
    def test_demo_overlay_declares_bundle_icon(self, demo_icons):
        assert demo_icons, "tauri.demo.conf.json must override bundle.icon"

    def test_demo_covers_every_base_icon_file(self, base_icons, demo_icons):
        """Tauri replaces the array wholesale, so a short list drops a platform."""
        assert [Path(p).name for p in demo_icons] == [Path(p).name for p in base_icons]

    def test_demo_icons_live_outside_the_base_icon_directory(self, base_icons, demo_icons):
        base_dirs = {Path(p).parent for p in base_icons}
        demo_dirs = {Path(p).parent for p in demo_icons}
        assert demo_dirs.isdisjoint(base_dirs)

    def test_every_declared_icon_exists(self, demo_icons):
        missing = [p for p in demo_icons if not (_SRC_TAURI / p).is_file()]
        assert not missing, f"declared but absent: {missing}"

    def test_no_demo_icon_is_a_copy_of_the_base_icon(self, base_icons, demo_icons):
        """The regression itself: identical bytes meant identical icons in Steam."""
        base_by_name = {Path(p).name: _SRC_TAURI / p for p in base_icons}
        for rel in demo_icons:
            demo = _SRC_TAURI / rel
            base = base_by_name[demo.name]
            assert demo.read_bytes() != base.read_bytes(), (
                f"{demo.name} is byte-identical to the base app's"
            )


# ---------------------------------------------------------------------------
# D-10b  Same mark, visibly different plate
# ---------------------------------------------------------------------------
class TestDemoIconIsVisuallyDistinct:
    @pytest.mark.parametrize("name", ["32x32.png", "128x128.png", "128x128@2x.png"])
    def test_plate_colours_are_far_apart(self, name):
        base = _plate_colour(_SRC_TAURI / "icons" / name)
        demo = _plate_colour(_SRC_TAURI / "icons-demo" / name)
        assert _distance(base, demo) >= _MIN_PLATE_DISTANCE, (
            f"{name}: demo plate {demo} is too close to the base plate {base}"
        )

    def test_plates_are_the_documented_colours(self):
        assert _distance(_plate_colour(_SRC_TAURI / "icons" / "32x32.png"), _BASE_PLATE) < 12
        assert _distance(_plate_colour(_SRC_TAURI / "icons-demo" / "32x32.png"), _DEMO_PLATE) < 12

    @pytest.mark.parametrize("name", ["32x32.png", "128x128.png", "128x128@2x.png"])
    def test_silhouette_is_unchanged(self, name):
        """The demo is the same product: neither the plate's outline nor the
        mark on it may move.

        Two comparisons, because the plate is opaque under the bubble, so
        alpha alone cannot tell a frame with the bubble painted out from the
        real one. Coverage is compared rather than raw alpha, so that the two
        renderers disagreeing by a fraction of a pixel along the rounded edge
        does not read as a different shape; the white mark is compared as a
        mask with a one-pixel neighbourhood for the same reason, with the
        ribbon band cut out of both editions because its lettering is white
        too and the base has no ribbon.
        """
        base_path = _SRC_TAURI / "icons" / name
        demo_path = _SRC_TAURI / "icons-demo" / name
        _, _, base = _read_png(base_path)
        _, _, demo = _read_png(demo_path)
        assert len(base) == len(demo)
        differing = sum(
            1 for (_, _, _, a), (_, _, _, b) in zip(base, demo) if (a > 128) != (b > 128)
        )
        assert differing <= len(base) * 0.01, (
            f"{name}: {differing}/{len(base)} covered pixels differ — the demo "
            "mark should share the base silhouette"
        )

        base_mark = _mark_mask(base_path)
        demo_mark = _mark_mask(demo_path)
        assert base_mark, f"{name}: no white mark found on the base icon"
        stray = _unmatched(demo_mark, base_mark) + _unmatched(base_mark, demo_mark)
        # Zero on the committed set at every size: the edge pixels the two
        # renderers classify differently all have a matching neighbour. A
        # painted-out bubble puts the whole base mark here; dropped dots put
        # their interiors here at 128 px and up.
        assert stray <= len(base_mark) * 0.01, (
            f"{name}: {stray} pixels of the white mark are in one edition and "
            f"not within a pixel of it in the other (base mark {len(base_mark)}, "
            f"demo mark {len(demo_mark)}): the demo should carry the base mark"
        )

    def test_png_dimensions(self):
        for name, expected in (("32x32.png", 32), ("128x128.png", 128), ("128x128@2x.png", 256)):
            width, height, _ = _read_png(_SRC_TAURI / "icons-demo" / name)
            assert (width, height) == (expected, expected), name


# ---------------------------------------------------------------------------
# D-10c  The "DEMO" ribbon appears only where it is legible
# ---------------------------------------------------------------------------
class TestDemoRibbon:
    def test_large_frames_carry_the_ribbon(self):
        for name in ("128x128.png", "128x128@2x.png"):
            path = _SRC_TAURI / "icons-demo" / name
            width, _, _ = _read_png(path)
            ribbon_px = _count_near(path, _RIBBON_BG)
            assert ribbon_px > width * 4, f"{name}: no DEMO ribbon found"

    def test_small_frame_has_no_ribbon(self):
        """At 32 px the word is ~3 px tall; it reads as dirt, not as a word."""
        path = _SRC_TAURI / "icons-demo" / "32x32.png"
        assert _count_near(path, _RIBBON_BG) == 0

    @pytest.mark.parametrize("name", ["128x128.png", "128x128@2x.png"])
    def test_the_ribbon_actually_spells_demo(self, name):
        """The band is dark and the word is light, both inside the band.

        Without this the ribbon tests pass on an empty black stripe: the
        letterforms in ``gen_icons.py`` are hand-built polygons laid out in an
        upright frame and then rotated onto the diagonal, so a tracking or
        glyph-height slip can push "DEMO" off the band — or collapse it —
        while the band itself is still drawn exactly where it belongs.
        """
        covered, band, word = _ribbon_band(_SRC_TAURI / "icons-demo" / name)
        assert covered, f"{name}: the ribbon band falls outside the plate"
        assert band > covered * 0.5, (
            f"{name}: only {band}/{covered} band pixels are the ribbon colour"
        )
        # "DEMO" measures ~17-22% of the band; the window is wide enough to
        # survive a re-render and narrow enough to catch a missing or
        # overflowing word.
        assert 0.05 <= word / covered <= 0.45, (
            f"{name}: lettering is {word}/{covered} of the ribbon band — "
            '"DEMO" is missing, mispositioned or the wrong size'
        )

    @pytest.mark.parametrize("name", ["128x128.png", "128x128@2x.png"])
    def test_the_ribbon_carries_four_separated_letterforms(self, name):
        """Four glyphs, not four glyphs' worth of ink.

        The area check above is blind to *which* letters are there: drop the E
        from ``_GLYPHS``' layout and the remaining three still land inside its
        window.  Counting the gaps ``WORD_TRACKING`` leaves along the band is
        what pins the word to "DEMO" — a dropped glyph gives three runs, and a
        tracking or glyph-width slip that lets two letters touch gives fewer
        than four as well.
        """
        runs = _ribbon_letterforms(_SRC_TAURI / "icons-demo" / name)
        assert len(runs) == 4, (
            f'{name}: the ribbon has {len(runs)} letterform(s), not the four of '
            f'"DEMO" — pixel counts {runs}'
        )
        # D, E, M and O differ in width, but not by anything like 4x; a run
        # that small is a fragment, not a letter.
        assert min(runs) * 4 >= max(runs), f"{name}: lopsided letterforms {runs}"

    def test_base_icon_never_carries_a_ribbon(self):
        for name in ("32x32.png", "128x128.png", "128x128@2x.png"):
            assert _count_near(_SRC_TAURI / "icons" / name, _RIBBON_BG) == 0, name


# ---------------------------------------------------------------------------
# D-10d  Container formats
# ---------------------------------------------------------------------------
class TestIconContainers:
    def test_ico_carries_the_sizes_windows_asks_for(self):
        frames = _read_ico(_SRC_TAURI / "icons-demo" / "icon.ico")
        sizes = {w for w, _, _ in frames}
        assert {16, 32, 48, 256} <= sizes, f"icon.ico is missing sizes: {sizes}"

    def test_ico_entries_match_the_frames_they_point_at(self):
        """A directory entry that disagrees with its own payload is a dead frame.

        The entry is all Windows reads when it picks a size, so a 48 px slot
        holding the 64 px frame is drawn rescaled — or skipped. ``write_ico``
        derives both numbers from the same list, which is exactly the kind of
        pairing that stays right until someone reorders one side of it.
        """
        for width, height, payload in _read_ico(_SRC_TAURI / "icons-demo" / "icon.ico"):
            assert _png_dimensions(payload) == (width, height), (
                f"icon.ico declares a {width}x{height} frame but holds "
                f"{_png_dimensions(payload)}"
            )

    def test_icns_png_chunks_hold_the_size_their_type_promises(self):
        """Same bookkeeping on the macOS side: the type *is* the size."""
        chunks = _read_icns(_SRC_TAURI / "icons-demo" / "icon.icns")
        for kind, payload in chunks.items():
            if kind not in _ICNS_PNG_SIZES:
                continue
            size = _ICNS_PNG_SIZES[kind]
            assert _png_dimensions(payload) == (size, size), (
                f"{kind.decode()} should be {size}x{size}, holds "
                f"{_png_dimensions(payload)}"
            )

    def test_ico_32px_frame_is_the_bundle_png(self):
        """Closes the ring between the three 32 px artefacts.

        ``ic05`` is pinned to this frame below, and the three 32 px artefacts
        — the bundle PNG, the ICO slot and the ICNS rep — are what the taskbar
        and the Finder list draw. Without this link they could drift apart one
        re-render at a time.
        """
        ico = {w: payload for w, _, payload in _read_ico(_SRC_TAURI / "icons-demo" / "icon.ico")}
        _, _, from_ico = _decode_png(ico[32], "icon.ico 32px frame")
        _, _, from_png = _read_png(_SRC_TAURI / "icons-demo" / "32x32.png")
        assert from_ico == from_png, "icon.ico's 32 px frame is not 32x32.png"

    def test_icns_is_well_formed(self):
        chunks = _read_icns(_SRC_TAURI / "icons-demo" / "icon.icns")
        # ic07/ic08 are the 128 and 256 px representations macOS actually draws
        # in the Dock and in Finder's icon view.
        assert {b"ic07", b"ic08"} <= set(chunks), list(chunks)

    def test_icns_covers_every_representation_the_base_icon_has(self):
        """Including the 1x 16 pt and 32 pt reps (``ic04``/``ic05``).

        Without them macOS has to scale the nearest representation down for
        Finder's list view and a 1x Dock — which costs exactly the small-size
        sharpness this icon exists to provide.
        """
        base = _read_icns(_SRC_TAURI / "icons" / "icon.icns")
        demo = _read_icns(_SRC_TAURI / "icons-demo" / "icon.icns")
        wanted = set(base) - _ICNS_METADATA
        missing = sorted(k.decode("latin-1") for k in wanted - set(demo))
        assert not missing, f"demo icon.icns is missing representations: {missing}"

    @pytest.mark.parametrize("kind,size", [(b"ic04", 16), (b"ic05", 32)])
    def test_icns_argb_reps_match_the_ico_frame_of_the_same_size(self, kind, size):
        """The hand-rolled ARGB encoding decodes back to the frame it came from.

        ``ic04``/``ic05`` are run-length-encoded raw pixels rather than PNG, so
        a channel-order or RLE slip would ship a corrupt icon that still opens.
        """
        chunks = _read_icns(_SRC_TAURI / "icons-demo" / "icon.icns")
        decoded = _decode_icns_argb(chunks[kind], size)
        ico = _read_ico(_SRC_TAURI / "icons-demo" / "icon.ico")
        frames = {w: payload for w, _, payload in ico}
        width, height, expected = _decode_png(frames[size], f"icon.ico {size}px frame")
        assert (width, height) == (size, size)
        assert decoded == expected, f"{kind.decode()} does not match the {size} px frame"

    @pytest.mark.parametrize("kind,size", [(b"ic04", 16), (b"ic05", 32)])
    def test_icns_argb_payload_ends_on_a_literal(self, kind, size):
        """The last RLE op must not be a repeat, whose value byte ends the payload.

        ``iconutil``'s ARGB reader stops one byte short of the payload — on
        Apple's own files as well. Apple always ends a channel on a literal,
        so it loses one sample there and nobody notices. Ending on a repeat
        instead loses the whole run: before ``tail_literal``, the blue channel
        closed with a 42- and an 83-sample run and ``iconutil -c iconset``
        gave back a band of (109, 40, 0) across the bottom two rows of both
        reps, on fully opaque pixels. ``NSImage`` reads either form correctly,
        but this file is also uploaded to Steamworks' Mac Icon field and
        decoded by something we do not control.
        """
        chunks = _read_icns(_SRC_TAURI / "icons-demo" / "icon.icns")
        control = _icns_argb_last_op(chunks[kind], size)
        assert control < 128, (
            f"{kind.decode()} ends on a repeat of {control - 125} samples; a "
            "reader that stops one byte early loses all of them"
        )


# ---------------------------------------------------------------------------
# D-10e  The two Steamworks icons
# ---------------------------------------------------------------------------
class TestSteamworksIcons:
    """Valve's "Community and Client Icons" fields, and only those.

    There is no "client icon" asset: the fields are App Icon (184 x 184 JPG)
    and Shortcut Icon (256 x 256 or 512 x 512, .ico or .png), plus Mac Icon,
    which takes the bundle's own ``icon.icns`` unchanged. Getting the field
    wrong is not a cosmetic slip — an asset at a size Valve does not accept is
    one the uploader rejects, which is how the demo's library row stays
    identical to the full game's.
    """

    def test_app_icon_is_a_184px_jpeg(self):
        """The asset in issue #499's screenshot: Steam's library-list row."""
        width, height, components = _jpeg_frame(_APP_ICON)
        assert (width, height) == (_APP_ICON_PX, _APP_ICON_PX), (
            f"Steamworks requires {_APP_ICON_PX}x{_APP_ICON_PX}, got {width}x{height}"
        )
        assert components == 3, (
            f"the App Icon should be 3-component YCbCr, not {components}"
        )

    def test_app_icon_is_flattened_onto_the_capsule_base(self):
        """JPEG has no alpha, so the plate's rounded corners must be composited.

        Valve replaces alpha with solid black when it derives an App Icon from
        the Shortcut Icon; this one is flattened onto the capsule set's
        near-black deliberately, so the corners read as the store art's
        background rather than as a black notch.
        """
        pixels = _magick_rgb(_APP_ICON, _APP_ICON_PX)
        corner = pixels[2 * _APP_ICON_PX + 2]
        assert _distance(corner, _RIBBON_BG) <= 24, (
            f"the App Icon's corner is {corner}, not the capsule base colour"
        )

    def test_app_icon_plate_is_the_demo_purple(self):
        """Hue is what separates the two library rows at the size this is drawn."""
        pixels = _magick_rgb(_APP_ICON, _APP_ICON_PX)
        plate = Counter(pixels).most_common(1)[0][0]
        assert _distance(plate, _DEMO_PLATE) <= 24, (
            f"the App Icon's dominant colour is {plate}, not the demo purple"
        )
        assert _distance(plate, _BASE_PLATE) >= _MIN_PLATE_DISTANCE

    def test_app_icon_carries_the_demo_ribbon(self):
        """184 clears ``RIBBON_MIN_PX``, so the word is on the asset that matters.

        Not a given — it is why the App Icon is rendered at 184 rather than
        downscaled from an existing frame. If the floor ever rises above 184
        the library row loses the word and falls back to hue alone, which
        should be a decision, not a side effect.

        Counted the same way as the bundle frames: dark band, light lettering,
        both inside the diagonal strip, with the tolerance opened up because
        JPEG ringing smears every edge in here.
        """
        gen = _load_generator()
        assert _APP_ICON_PX >= gen.RIBBON_MIN_PX

        pixels = _magick_rgb(_APP_ICON, _APP_ICON_PX)
        scale = _APP_ICON_PX / _VIEW
        inner = _RIBBON_U_INNER * 2 ** 0.5 * scale
        outer = _RIBBON_U_OUTER * 2 ** 0.5 * scale
        band = word = covered = 0
        for index, rgb in enumerate(pixels):
            y, x = divmod(index, _APP_ICON_PX)
            if not inner <= (x + 0.5) + (y + 0.5) <= outer:
                continue
            covered += 1
            if _distance(rgb, _RIBBON_BG) <= 48:
                band += 1
            elif _distance(rgb, _RIBBON_FG) <= 48:
                word += 1
        assert covered, "the ribbon band falls outside the App Icon"
        assert band > covered * 0.5, (
            f"only {band}/{covered} band pixels are the ribbon colour"
        )
        assert 0.05 <= word / covered <= 0.45, (
            f'lettering is {word}/{covered} of the band — "DEMO" is missing, '
            "mispositioned or the wrong size on the App Icon"
        )

    def test_shortcut_icon_is_a_256px_png(self):
        width, height, _ = _read_png(_SHORTCUT_ICON)
        assert (width, height) == (_SHORTCUT_ICON_PX, _SHORTCUT_ICON_PX), (
            f"the Shortcut Icon should be {_SHORTCUT_ICON_PX}x"
            f"{_SHORTCUT_ICON_PX} — the frame the bundle ships; Valve's other "
            "accepted size, 512, would break the byte-identity below"
        )

    def test_shortcut_icon_is_the_frame_the_app_installs(self):
        """One mark: the desktop shortcut Steam creates and the bundled app agree.

        Byte equality rather than pixel equality, because they are meant to be
        the same file — Valve generates the .ico from this PNG, so there is no
        container in between to justify a re-encode.
        """
        assert _SHORTCUT_ICON.read_bytes() == (
            _SRC_TAURI / "icons-demo" / "128x128@2x.png"
        ).read_bytes()

    def test_no_stale_client_icon_remains(self):
        """The 32 px ".ico" this suite used to pin is not a Steamworks field.

        It was the wrong asset at the wrong size: Valve has no slot for it, and
        the row in the issue's screenshot is the App Icon. Leaving the file in
        the tree would invite someone to upload it.
        """
        assert not (_ICON_DIR / "demo_client_icon.ico").exists()


# ---------------------------------------------------------------------------
# D-10f  The committed output still matches the generator
# ---------------------------------------------------------------------------
def _load_generator():
    """Import ``gen_icons.py`` by path — it is a script, not a package module.

    Only the geometry is touched. ``_magick()`` is looked up lazily inside the
    render functions, so importing costs nothing and needs no ImageMagick.
    """
    spec = importlib.util.spec_from_file_location("convsim_gen_icons", _GEN_ICONS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestGeneratedArtworkIsCurrent:
    """The one artefact here that is checked against its generator rather than
    against a property of itself.

    Everything above pins what the rasterised set *looks like*; none of it can
    tell a tree where the mark was edited in ``gen_icons.py`` and the script
    never re-run — rasterising to find out would need ImageMagick, which this
    suite borrows for the App Icon's pixels and nothing else. The committed
    ``demo_icon.svg`` is drawn from the same geometry constants as the PNG, ICO
    and ICNS frames, and unlike them it is plain text, so comparing it to
    ``icon_svg()`` catches a half-applied regeneration for free — and keeps the
    vector the docs hand to anyone re-rendering the mark from drifting out of
    hand-edits.
    """

    def test_committed_svg_is_what_the_generator_draws(self):
        """Compared stripped: the drawing must match, the trailing byte need not.

        The generator writes the file with a final newline, as the repo's
        .editorconfig asks. Pinning that exactly would make the one artefact
        here anyone is invited to *open* fail the suite the moment an editor
        normalised its last line — and re-running the generator would take the
        newline straight back out again.
        """
        gen = _load_generator()
        assert _DEMO_SVG.read_text().strip() == gen.icon_svg("demo", ribbon=True), (
            "publishing/assets/icons/demo_icon.svg is out of date — it is "
            "generated output: re-run publishing/assets/source/gen_icons.py "
            "(which also rewrites the bundle icon set and the Steam uploads; "
            "expect every raster's bytes to change with it, and name your "
            "ImageMagick build in the commit message, see the script's docstring)"
        )

    def test_the_vector_carries_the_ribbon(self):
        """It is billed as the >= 128 px drawing, so it must be the ribboned one."""
        gen = _load_generator()
        assert _DEMO_SVG.read_text().strip() != gen.icon_svg("demo", ribbon=False)


# ---------------------------------------------------------------------------
# D-10g  The demo capsule and library art (issue #551)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def demo_capsule():
    """``demo_capsule(name)`` -> a decoded ``_Raster``, each file read once."""
    cache: dict[str, _Raster] = {}

    def load(name: str) -> _Raster:
        if name not in cache:
            cache[name] = _Raster(_DEMO_CAPSULE_DIR / f"{name}.png")
        return cache[name]

    return load


def _capsule_ribbon_band(width: int, height: int) -> tuple[float, float]:
    """The demo ribbon's (inner, outer) edges on a capsule, as values of x + y."""
    k = _CAPSULE_RIBBON_ICON_SIDE * math.sqrt(width * height) / _VIEW
    root2 = math.sqrt(2.0)
    return (width + height - (2 * _PLATE_CORNER - _RIBBON_U_INNER * root2) * k,
            width + height - (2 * _PLATE_CORNER - _RIBBON_U_OUTER * root2) * k)


def _dominant_colour(raster: _Raster, step: int = 4) -> tuple[int, int, int]:
    counts = Counter(rgba[:3] for _, _, rgba in raster.sample(step) if rgba[3] == 255)
    assert counts, "no opaque pixels"
    return counts.most_common(1)[0][0]


class TestDemoCapsules:
    """The demo app's own store and library art, so its entries stop rendering blank.

    The set is the full game's, on the demo icon's purple plate and with the
    icon's "DEMO" ribbon in the lower-right corner of every asset that may
    carry the game name. The checks mirror the icon ones above: the plate
    separates the two library entries at a glance, and where the ribbon is
    drawn it really spells the word — and nothing of the composition runs
    under it.
    """

    def test_the_demo_set_is_exactly_the_upload_set(self):
        """Eight assets, and nothing that invites a wrong upload.

        No page background — it is optional, Valve wants it ambient and
        textless, and the full game's near-black one is the file to use if the
        demo ever needs one — and no community icon: the App Icon and the
        Shortcut Icon are gen_icons.py's, in publishing/assets/icons/.
        """
        found = sorted(p.name for p in _DEMO_CAPSULE_DIR.iterdir())
        assert found == sorted(f"{n}.png" for n in _CAPSULE_SIZES), (
            f"publishing/assets/capsules/demo/ holds {found}; re-run "
            "gen_capsules.py --edition demo"
        )

    @pytest.mark.parametrize("name", sorted(_CAPSULE_SIZES))
    def test_demo_asset_is_valves_exact_size(self, name):
        path = _DEMO_CAPSULE_DIR / f"{name}.png"
        assert path.is_file(), f"{path.name} is missing: run gen_capsules.py --edition demo"
        assert _png_dimensions(path.read_bytes()) == _CAPSULE_SIZES[name], (
            f"{name}: Steamworks requires {_CAPSULE_SIZES[name]}"
        )

    @pytest.mark.parametrize("name", sorted({**_CAPSULE_SIZES, **_BASE_ONLY_CAPSULES}))
    def test_full_game_asset_is_valves_exact_size(self, name):
        sizes = {**_CAPSULE_SIZES, **_BASE_ONLY_CAPSULES}
        path = _CAPSULE_DIR / f"{name}.png"
        assert path.is_file(), f"{path.name} is missing: run gen_capsules.py"
        assert _png_dimensions(path.read_bytes()) == sizes[name]

    def test_no_demo_asset_is_a_copy_of_the_full_games(self):
        """The regression itself: the demo app's entries showing the base art,
        or nothing, instead of their own."""
        for name in _CAPSULE_SIZES:
            demo = (_DEMO_CAPSULE_DIR / f"{name}.png").read_bytes()
            assert demo != (_CAPSULE_DIR / f"{name}.png").read_bytes(), name

    @pytest.mark.parametrize("name", _OPAQUE_CAPSULES)
    def test_plate_is_the_demo_purple(self, name, demo_capsule):
        """Hue separates the two library entries, as it does the two icons."""
        raster = demo_capsule(name)
        opaque = all(rgba[3] == 255 for _, _, rgba in raster.sample(16))
        assert opaque, f"{name}: a store capsule should be fully opaque"
        plate = _dominant_colour(raster)
        assert _distance(plate, _DEMO_PLATE) <= 12, (
            f"{name}: dominant colour {plate} is not the demo plate {_DEMO_PLATE}"
        )
        assert _distance(plate, _BASE_PLATE) >= _MIN_PLATE_DISTANCE
        for stage in _BASE_STAGE:
            assert _distance(plate, stage) >= _MIN_PLATE_DISTANCE, (
                f"{name}: plate {plate} is too close to the full game's stage {stage}"
            )

    @pytest.mark.parametrize("name", _RIBBONED_CAPSULES)
    def test_ribbon_spells_demo_in_the_lower_right(self, name, demo_capsule):
        """A dark band with four light letterforms, where the generator puts it.

        Counted as on the icons: band colour and lettering inside the diagonal
        strip, then the lettering bucketed along the band so the gaps between
        D, E, M and O show up as four separate runs.
        """
        raster = demo_capsule(name)
        inner, outer = _capsule_ribbon_band(raster.width, raster.height)
        covered = band = word = 0
        columns: dict[int, int] = {}
        for x, y, (r, g, b, _) in raster.diagonal_strip(inner, outer):
            covered += 1
            if _distance((r, g, b), _RIBBON_BG) <= 24:
                band += 1
            elif _distance((r, g, b), _RIBBON_FG) <= 24:
                word += 1
                columns[x - y] = columns.get(x - y, 0) + 1
        assert covered, f"{name}: the ribbon band falls outside the capsule"
        assert band > covered * 0.5, (
            f"{name}: only {band}/{covered} band pixels are the ribbon colour"
        )
        assert 0.05 <= word / covered <= 0.45, (
            f'{name}: lettering is {word}/{covered} of the band — "DEMO" is '
            "missing, mispositioned or the wrong size"
        )
        runs = _letterform_runs(columns)
        assert len(runs) == 4, f"{name}: {len(runs)} letterform(s), not four: {runs}"
        assert min(runs) * 4 >= max(runs), f"{name}: lopsided letterforms {runs}"

    @pytest.mark.parametrize("name", _RIBBONED_CAPSULES)
    def test_nothing_crowds_the_ribbon(self, name, demo_capsule):
        """Only the plate in the clearance inside the band and in the tip beyond it.

        A mark or a line of the logotype under the ribbon is half hidden — the
        one failure in this set the eye skips over on a full-size capsule. The
        two pixels next to each band edge are left out for the anti-aliasing.
        """
        raster = demo_capsule(name)
        inner, outer = _capsule_ribbon_band(raster.width, raster.height)
        stage = (_DEMO_PLATE, _DEMO_LOWER_BAND)

        def strays(lo: float, hi: float) -> list[tuple[int, int]]:
            return [
                (x, y) for x, y, rgba in raster.diagonal_strip(lo, hi)
                if min(_distance(rgba[:3], c) for c in stage) > 16
            ]

        clearance = strays(inner - _CAPSULE_RIBBON_CLEARANCE * (outer - inner), inner - 2)
        assert not clearance, (
            f"{name}: {len(clearance)} pixels of artwork within the ribbon's "
            f"clearance, e.g. {clearance[:5]}"
        )
        tip = strays(outer + 2, raster.width + raster.height)
        assert not tip, f"{name}: the corner beyond the ribbon is not plain plate: {tip[:5]}"

    def test_hero_carries_no_ribbon(self, demo_capsule):
        """Valve's library hero takes no text or logo: plate and mark only."""
        raster = demo_capsule("library_hero")
        inner, outer = _capsule_ribbon_band(raster.width, raster.height)
        corner = [rgba for _, _, rgba in raster.diagonal_strip(
            inner - (outer - inner), raster.width + raster.height)]
        assert corner
        stage = (_DEMO_PLATE, _DEMO_LOWER_BAND)   # the strip crosses both bands
        assert all(min(_distance(rgba[:3], c) for c in stage) <= 16 for rgba in corner), (
            "the hero's lower-right corner is not plain plate"
        )
        dark = sum(1 for _, _, rgba in raster.sample(4) if _distance(rgba[:3], _RIBBON_BG) <= 48)
        assert dark == 0, f"{dark} sampled hero pixels are the ribbon's near-black"

    def test_logo_is_transparent_and_carries_the_demo_mark(self, demo_capsule):
        """The logo is laid over the purple hero, so its player bubble is white.

        The full game's logo has a #6D28D9 bubble, which on the demo hero would
        vanish into the plate and leave three floating dots: of the logo's
        opaque pixels, only those dots may be the plate colour.
        """
        raster = demo_capsule("library_logo")
        assert raster.alpha, "the library logo must be a transparent PNG"
        w, h = raster.width, raster.height
        for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
            assert raster.rgba(x, y)[3] == 0, f"logo corner ({x}, {y}) is not transparent"
        opaque = [rgba[:3] for _, _, rgba in raster.sample(2) if rgba[3] == 255]
        assert opaque, "the library logo is empty"
        purple = sum(1 for rgb in opaque if _distance(rgb, _DEMO_PLATE) <= 24)
        assert purple <= len(opaque) * 0.02, (
            f"{purple}/{len(opaque)} of the logo is the demo plate colour — it "
            "would disappear against the demo hero"
        )
        assert not any(_distance(rgb, _RIBBON_BG) <= 24 for rgb in opaque), (
            "the library logo carries the ribbon's band colour"
        )
