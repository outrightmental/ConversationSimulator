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
    the Steam client icon is 32 px and the word is unreadable there;
  * the Steamworks client icon is the same image the app itself installs.

Nothing here needs a build, a network, or ImageMagick: the PNGs, the ICO and
the ICNS are parsed directly. Owner: platform team.
"""
from __future__ import annotations

import json
import struct
import zlib
from collections import Counter
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_TAURI = _REPO_ROOT / "apps" / "desktop" / "src-tauri"
_BASE_CONF = _SRC_TAURI / "tauri.conf.json"
_DEMO_CONF = _SRC_TAURI / "tauri.demo.conf.json"
_CLIENT_ICON = _REPO_ROOT / "publishing" / "assets" / "icons" / "demo_client_icon.ico"

# Plate colours from publishing/assets/source/gen_icons.py.
_BASE_PLATE = (0x14, 0x7A, 0x84)
_DEMO_PLATE = (0x6D, 0x28, 0xD9)
_RIBBON_BG = (0x0D, 0x0D, 0x15)

# Below this the two icons would start to look alike in a library list.  The
# teal/purple pair measures ~148, so there is room to retune either plate; the
# point of the floor is to fail a future "subtle" recolour, not to be a tight fit.
_MIN_PLATE_DISTANCE = 100.0


# ---------------------------------------------------------------------------
# Minimal PNG reader — enough for the 8-bit RGBA icons this repo generates.
# ---------------------------------------------------------------------------
def _read_png(path: Path) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    """Return (width, height, RGBA pixels) for an 8-bit truecolour-alpha PNG."""
    raw = path.read_bytes()
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


def _plate_colour(path: Path) -> tuple[int, int, int]:
    """The icon's dominant opaque colour — in practice the rounded-square plate."""
    _, _, pixels = _read_png(path)
    opaque = Counter((r, g, b) for r, g, b, a in pixels if a == 255)
    assert opaque, f"{path} has no fully opaque pixels"
    return opaque.most_common(1)[0][0]


def _distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _count_near(path: Path, colour: tuple[int, int, int], tolerance: int = 24) -> int:
    _, _, pixels = _read_png(path)
    return sum(
        1 for r, g, b, a in pixels
        if a > 200 and _distance((r, g, b), colour) <= tolerance
    )


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
        """The demo is the same product: the plate shape must not move.

        Compared as coverage rather than raw alpha, so that the two renderers
        disagreeing by a fraction of a pixel along the rounded edge does not
        read as a different shape.
        """
        _, _, base = _read_png(_SRC_TAURI / "icons" / name)
        _, _, demo = _read_png(_SRC_TAURI / "icons-demo" / name)
        assert len(base) == len(demo)
        differing = sum(
            1 for (_, _, _, a), (_, _, _, b) in zip(base, demo) if (a > 128) != (b > 128)
        )
        assert differing <= len(base) * 0.01, (
            f"{name}: {differing}/{len(base)} covered pixels differ — the demo "
            "mark should share the base silhouette"
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
        """At 32 px the word is ~6 px tall; it reads as dirt, not as a word."""
        path = _SRC_TAURI / "icons-demo" / "32x32.png"
        assert _count_near(path, _RIBBON_BG) == 0

    def test_base_icon_never_carries_a_ribbon(self):
        for name in ("32x32.png", "128x128.png", "128x128@2x.png"):
            assert _count_near(_SRC_TAURI / "icons" / name, _RIBBON_BG) == 0, name


# ---------------------------------------------------------------------------
# D-10d  Container formats, and the Steamworks client icon
# ---------------------------------------------------------------------------
class TestIconContainers:
    def test_ico_carries_the_sizes_windows_asks_for(self):
        frames = _read_ico(_SRC_TAURI / "icons-demo" / "icon.ico")
        sizes = {w for w, _, _ in frames}
        assert {16, 32, 48, 256} <= sizes, f"icon.ico is missing sizes: {sizes}"

    def test_icns_is_well_formed(self):
        raw = (_SRC_TAURI / "icons-demo" / "icon.icns").read_bytes()
        assert raw[:4] == b"icns"
        assert struct.unpack(">I", raw[4:8])[0] == len(raw), "ICNS length field is wrong"
        pos, types = 8, []
        while pos < len(raw):
            kind = raw[pos:pos + 4]
            (length,) = struct.unpack(">I", raw[pos + 4:pos + 8])
            assert 8 < length <= len(raw) - pos, f"bad chunk length for {kind!r}"
            types.append(kind)
            pos += length
        # ic07/ic08 are the 128 and 256 px representations macOS actually draws
        # in the Dock and in Finder's icon view.
        assert {b"ic07", b"ic08"} <= set(types), types

    def test_steamworks_client_icon_is_a_32px_ico(self):
        frames = _read_ico(_CLIENT_ICON)
        assert [(w, h) for w, h, _ in frames] == [(32, 32)], (
            "Steamworks wants the client icon as a single 32x32 frame"
        )

    def test_client_icon_matches_the_installed_app_icon(self):
        """One mark: what Steam lists and what the app installs are the same image."""
        (_, _, payload), = _read_ico(_CLIENT_ICON)
        assert payload == (_SRC_TAURI / "icons-demo" / "32x32.png").read_bytes()
