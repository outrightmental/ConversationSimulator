# SPDX-License-Identifier: Apache-2.0
"""The pinned llama.cpp release: one tag and one SHA-256 per archive (issue #530).

The pin lives in ``runtimes/llama_cpp/pin.json``, the single file the two
download scripts, CI and this module read. A frozen (PyInstaller) build embeds
it at ``sys._MEIPASS/runtimes/llama_cpp/pin.json`` (see ``convsim-core.spec``);
a source checkout reads it from the repository.

Upstream publishes no checksum file for its releases, so these digests are the
only thing that verifies an engine download. They were copied from the
``digest`` GitHub's release API reports for each asset
(``gh api repos/ggml-org/llama.cpp/releases/tags/<tag>``). An archive with no
digest here is refused: there is no unverified install.

Asset names, as upstream publishes them for the pinned tag:

==============  ==========================================  =========================================
platform        default build                               Vulkan build
==============  ==========================================  =========================================
win-x64         ``llama-<tag>-bin-win-cpu-x64.zip``         ``llama-<tag>-bin-win-vulkan-x64.zip``
win-arm64       ``llama-<tag>-bin-win-cpu-arm64.zip``       none
linux-x64       ``llama-<tag>-bin-ubuntu-x64.tar.gz``       ``llama-<tag>-bin-ubuntu-vulkan-x64.tar.gz``
linux-arm64     ``llama-<tag>-bin-ubuntu-arm64.tar.gz``     ``llama-<tag>-bin-ubuntu-vulkan-arm64.tar.gz``
macos-arm64     ``llama-<tag>-bin-macos-arm64.tar.gz``      none (the default build uses Metal)
macos-x64       ``llama-<tag>-bin-macos-x64.tar.gz``        none
==============  ==========================================  =========================================
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping

#: Where the pin lives, relative to the repository root and to ``sys._MEIPASS``.
PIN_RELATIVE_PATH = Path("runtimes") / "llama_cpp" / "pin.json"

#: The build variants a platform may have. ``cpu`` is the default build: on
#: macOS that archive is the Metal build, which is the only one upstream ships.
VARIANTS: tuple[str, ...] = ("cpu", "vulkan")

# app platform id -> (upstream platform segment for the default build,
#                     upstream segment for the Vulkan build or None)
_UPSTREAM_SEGMENTS: Mapping[str, tuple[str, str | None]] = {
    "win-x64": ("win-cpu-x64", "win-vulkan-x64"),
    "win-arm64": ("win-cpu-arm64", None),
    "linux-x64": ("ubuntu-x64", "ubuntu-vulkan-x64"),
    "linux-arm64": ("ubuntu-arm64", "ubuntu-vulkan-arm64"),
    "macos-arm64": ("macos-arm64", None),
    "macos-x64": ("macos-x64", None),
}


class PinError(RuntimeError):
    """The pin is missing, unreadable, or has no digest for an archive."""


@dataclass(frozen=True)
class LlamaCppPin:
    """The pinned tag and the SHA-256 of each of its archives."""

    tag: str
    sha256: Mapping[str, str]

    def digest_for(self, asset_name: str) -> str:
        """The pinned lowercase hex SHA-256 of *asset_name*.

        Raises :class:`PinError` when the pin has none: a download with no
        expected digest is never installed.
        """
        digest = self.sha256.get(asset_name)
        if not digest:
            raise PinError(
                f"No pinned SHA-256 for {asset_name}. Every engine download is verified "
                f"against runtimes/llama_cpp/pin.json; add the asset's digest there "
                f"(gh api repos/ggml-org/llama.cpp/releases/tags/{self.tag})."
            )
        return digest


def pin_path() -> Path:
    """The pin file this process reads.

    A frozen build reads its embedded copy; a source checkout reads the
    repository's. ``parents[4]`` of this file is the repository root
    (``services/convsim-core/convsim_core/runtime/llama_cpp_pin.py``).
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / PIN_RELATIVE_PATH
    return Path(__file__).resolve().parents[4] / PIN_RELATIVE_PATH


def parse_pin(text: str) -> LlamaCppPin:
    """Parse the pin file's JSON. Raises :class:`PinError` when malformed."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PinError(f"The llama.cpp pin is not valid JSON: {exc}") from exc
    tag = data.get("tag") if isinstance(data, dict) else None
    digests = data.get("sha256") if isinstance(data, dict) else None
    if not isinstance(tag, str) or not tag:
        raise PinError("The llama.cpp pin has no tag.")
    if not isinstance(digests, dict):
        raise PinError("The llama.cpp pin has no sha256 table.")
    clean: dict[str, str] = {}
    for name, digest in digests.items():
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise PinError(f"The pinned SHA-256 for {name} is not 64 lowercase hex digits.")
        clean[str(name)] = digest
    return LlamaCppPin(tag=tag, sha256=clean)


@lru_cache(maxsize=1)
def load_pin() -> LlamaCppPin:
    """The pin this build ships with. Raises :class:`PinError` when unreadable."""
    path = pin_path()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PinError(f"Cannot read the llama.cpp pin at {path}: {exc}") from exc
    return parse_pin(text)


def pinned_tag() -> str | None:
    """The pinned tag, or None when the pin cannot be read. Never raises."""
    try:
        return load_pin().tag
    except PinError:
        return None


def has_variant(platform_string: str, variant: str) -> bool:
    """True when upstream publishes *variant* for *platform_string*."""
    segments = _UPSTREAM_SEGMENTS.get(platform_string)
    if segments is None:
        return False
    if variant == "cpu":
        return True
    if variant == "vulkan":
        return segments[1] is not None
    return False


def asset_name(tag: str, platform_string: str, variant: str = "cpu") -> str:
    """The upstream archive name for *tag*, *platform_string* and *variant*.

    Raises ValueError for a platform or variant upstream does not publish.
    """
    segments = _UPSTREAM_SEGMENTS.get(platform_string)
    if segments is None:
        raise ValueError(f"Unknown engine platform: {platform_string}")
    if variant not in VARIANTS:
        raise ValueError(f"Unknown engine variant: {variant} (expected one of {', '.join(VARIANTS)})")
    segment = segments[0] if variant == "cpu" else segments[1]
    if segment is None:
        raise ValueError(f"llama.cpp publishes no {variant} build for {platform_string}.")
    extension = "zip" if platform_string.startswith("win-") else "tar.gz"
    return f"llama-{tag}-bin-{segment}.{extension}"


def is_zip(asset: str) -> bool:
    """True for a Windows ``.zip`` archive, False for a ``.tar.gz``."""
    return asset.endswith(".zip")
