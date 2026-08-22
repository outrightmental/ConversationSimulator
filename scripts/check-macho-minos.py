#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail when a Mach-O binary targets a macOS newer than the supported floor.

Why this exists: the Steam macOS depot once shipped an upstream llama.cpp
build whose Metal backend (libggml-metal.0.dylib) was compiled for macOS 26.
On every supported macOS below that, dyld killed llama-server the instant it
launched ("Symbol not found: _OBJC_CLASS_$_MTLResidencySetDescriptor …
built for macOS 26.0 which is newer than running OS"), which the setup wizard
misreported as insufficient RAM (issue #469). The breakage is statically
visible in the Mach-O load commands, so it belongs in CI — not in a player's
first-run experience.

This script parses each file's LC_BUILD_VERSION (platform macOS) or legacy
LC_VERSION_MIN_MACOSX load command — including universal/fat binaries — and
reports the minimum-OS version the binary declares. With --max it exits
non-zero when any inspected file exceeds the given floor.

No dependencies beyond the standard library; runs anywhere (the bytes are
parsed directly, so a Linux CI runner can inspect macOS artifacts).

Usage:
  check-macho-minos.py [--max X.Y] PATH...   # files or directories
  check-macho-minos.py --self-test           # verify the parser on
                                             # synthesized fixtures

Exit codes: 0 = ok, 1 = a binary exceeds --max (or self-test failed),
2 = usage / read error.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys

MH_MAGIC = 0xFEEDFACE
MH_CIGAM = 0xCEFAEDFE
MH_MAGIC_64 = 0xFEEDFACF
MH_CIGAM_64 = 0xCFFAEDFE
FAT_MAGIC = 0xCAFEBABE
FAT_CIGAM = 0xBEBAFECA
FAT_MAGIC_64 = 0xCAFEBABF
FAT_CIGAM_64 = 0xBFBAFECA

LC_VERSION_MIN_MACOSX = 0x24
LC_BUILD_VERSION = 0x32
PLATFORM_MACOS = 1


def _decode_version(value: int) -> str:
    """Decode the xxxx.yy.zz packed version used by Mach-O load commands."""
    return f"{value >> 16}.{(value >> 8) & 0xFF}.{value & 0xFF}"


def _version_tuple(text: str) -> tuple[int, int, int]:
    """Parse X[.Y[.Z]] into a comparable 3-tuple.

    Padding matters: naive tuples make "14.0.0" > "14.0" (longer tuple wins
    on equal prefix), which would fail binaries that exactly match the floor.
    """
    parts = [int(part) for part in text.split(".")]
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])


def _parse_thin(data: bytes) -> str | None:
    """Return the declared macOS minimum of one thin Mach-O image, or None."""
    if len(data) < 32:
        return None
    (magic,) = struct.unpack_from("<I", data, 0)
    if magic in (MH_MAGIC_64, MH_MAGIC):
        endian = "<"
    elif magic in (MH_CIGAM_64, MH_CIGAM):
        endian = ">"
    else:
        return None
    is64 = magic in (MH_MAGIC_64, MH_CIGAM_64)
    header_fmt = endian + ("7I" if not is64 else "8I")
    header_size = struct.calcsize(header_fmt)
    if len(data) < header_size:
        return None
    header = struct.unpack_from(header_fmt, data, 0)
    ncmds = header[4]
    offset = header_size
    for _ in range(ncmds):
        if offset + 8 > len(data):
            return None
        cmd, cmdsize = struct.unpack_from(endian + "II", data, offset)
        if cmdsize < 8 or offset + cmdsize > len(data):
            return None
        if cmd == LC_BUILD_VERSION and cmdsize >= 24:
            platform, minos = struct.unpack_from(endian + "II", data, offset + 8)
            if platform == PLATFORM_MACOS:
                return _decode_version(minos)
        elif cmd == LC_VERSION_MIN_MACOSX and cmdsize >= 16:
            (version,) = struct.unpack_from(endian + "I", data, offset + 8)
            return _decode_version(version)
        offset += cmdsize
    return None


def macho_minos(data: bytes) -> str | None:
    """Return the highest declared macOS minimum across all slices, or None
    when the bytes are not a Mach-O image (or declare no macOS target)."""
    if len(data) < 8:
        return None
    (magic_be,) = struct.unpack_from(">I", data, 0)
    if magic_be in (FAT_MAGIC, FAT_MAGIC_64):
        is64 = magic_be == FAT_MAGIC_64
        (nfat,) = struct.unpack_from(">I", data, 4)
        arch_fmt = ">2I2Q2I" if is64 else ">5I"
        arch_size = struct.calcsize(arch_fmt)
        results: list[str] = []
        for i in range(nfat):
            base = 8 + i * arch_size
            if base + arch_size > len(data):
                break
            fields = struct.unpack_from(arch_fmt, data, base)
            slice_offset, slice_size = fields[2], fields[3]
            if slice_offset + slice_size > len(data):
                continue
            found = _parse_thin(data[slice_offset : slice_offset + slice_size])
            if found is not None:
                results.append(found)
        if not results:
            return None
        return max(results, key=_version_tuple)
    return _parse_thin(data)


def iter_candidate_files(paths: list[str]):
    for path in paths:
        if os.path.isdir(path):
            for root, _dirs, files in os.walk(path):
                for name in files:
                    full = os.path.join(root, name)
                    if not os.path.islink(full):
                        yield full
        elif not os.path.islink(path):
            yield path


def run_check(paths: list[str], max_minos: str | None) -> int:
    limit = _version_tuple(max_minos) if max_minos else None
    inspected = 0
    violations = 0
    for path in iter_candidate_files(paths):
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            print(f"error: cannot read {path}: {exc}", file=sys.stderr)
            return 2
        minos = macho_minos(data)
        if minos is None:
            continue
        inspected += 1
        if limit is not None and _version_tuple(minos) > limit:
            violations += 1
            print(f"FAIL {path}: targets macOS {minos} (> allowed {max_minos})")
        else:
            print(f"ok   {path}: targets macOS {minos}")
    if inspected == 0:
        print("error: no Mach-O files found under the given paths", file=sys.stderr)
        return 2
    if violations:
        print(
            f"\n{violations} binar{'y' if violations == 1 else 'ies'} exceed the "
            f"macOS {max_minos} floor. Shipping these would crash on supported "
            "systems the moment the engine launches (see issue #469).",
            file=sys.stderr,
        )
        return 1
    return 0


# ── Self-test ────────────────────────────────────────────────────────────────


def _synth_thin(minos: int, *, legacy: bool = False, big_endian: bool = False) -> bytes:
    """Build a minimal 64-bit Mach-O with one version load command."""
    endian = ">" if big_endian else "<"
    if legacy:
        cmd = struct.pack(endian + "4I", LC_VERSION_MIN_MACOSX, 16, minos, minos)
    else:
        cmd = struct.pack(
            endian + "6I", LC_BUILD_VERSION, 24, PLATFORM_MACOS, minos, minos, 0
        )
    # The magic constant is always MH_MAGIC_64; writing every header field in
    # the target byte order is what makes the on-disk image big-endian (a
    # little-endian reader then sees MH_CIGAM_64 and swaps, as dyld would).
    # magic, cputype, cpusubtype, filetype, ncmds, sizeofcmds, flags, reserved
    header = struct.pack(endian + "8I", MH_MAGIC_64, 0, 0, 2, 1, len(cmd), 0, 0)
    return header + cmd


def _synth_fat(slices: list[bytes]) -> bytes:
    header = struct.pack(">2I", FAT_MAGIC, len(slices))
    arch_size = struct.calcsize(">5I")
    offset = len(header) + arch_size * len(slices)
    archs = b""
    body = b""
    for blob in slices:
        archs += struct.pack(">5I", 0, 0, offset, len(blob), 0)
        body += blob
        offset += len(blob)
    return header + archs + body


def self_test() -> int:
    v13 = (13 << 16) | (0 << 8)
    v26 = (26 << 16) | (0 << 8)
    v12_7_4 = (12 << 16) | (7 << 8) | 4
    cases = [
        ("LC_BUILD_VERSION 13.0", macho_minos(_synth_thin(v13)), "13.0.0"),
        ("LC_BUILD_VERSION 26.0", macho_minos(_synth_thin(v26)), "26.0.0"),
        ("legacy LC_VERSION_MIN 12.7.4", macho_minos(_synth_thin(v12_7_4, legacy=True)), "12.7.4"),
        ("big-endian image", macho_minos(_synth_thin(v13, big_endian=True)), "13.0.0"),
        ("fat: max of slices", macho_minos(_synth_fat([_synth_thin(v13), _synth_thin(v26)])), "26.0.0"),
        ("not Mach-O", macho_minos(b"\x7fELF" + b"\x00" * 64), None),
        ("truncated", macho_minos(b"\xcf\xfa\xed\xfe\x00"), None),
    ]
    failed = False
    for name, got, want in cases:
        status = "ok" if got == want else "FAIL"
        if got != want:
            failed = True
        print(f"{status:4} self-test: {name}: got {got!r}, want {want!r}")
    ordering = _version_tuple("26.0.0") > _version_tuple("13.0")
    print(f"{'ok' if ordering else 'FAIL':4} self-test: version ordering 26.0.0 > 13.0")
    failed = failed or not ordering
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", help="Mach-O files or directories to inspect")
    parser.add_argument("--max", dest="max_minos", metavar="X.Y",
                        help="fail when any binary targets a macOS newer than this")
    parser.add_argument("--self-test", action="store_true",
                        help="verify the parser against synthesized fixtures")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.paths:
        parser.print_usage(sys.stderr)
        return 2
    return run_check(args.paths, args.max_minos)


if __name__ == "__main__":
    sys.exit(main())
