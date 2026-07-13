# SPDX-License-Identifier: Apache-2.0
"""Artifact inspection tests (issue #238).

Checks a built desktop artifact for depot layout, executable permissions,
icon presence, version stamping, and forbidden file patterns.  All tests
skip automatically when CONVSIM_ARTIFACT_DIR is not set.

Run via the release-smoke --full runner:
  CONVSIM_ARTIFACT_DIR=<path> ./scripts/release-smoke.sh --full

Or directly:
  CONVSIM_ARTIFACT_DIR=apps/desktop/src-tauri/target/release/bundle/appimage \
    pytest tests/artifact/ -v

These checks complement the shell-based depot-audit.sh, which enforces the
Steamworks compliance rules (MD-04 weight files, devfile exclusions).
Python tests here add: version stamping, icon presence, executable permissions,
and Python-native assertion messages for post-mortem inspection.
"""
from __future__ import annotations

import platform
import plistlib
import re
import stat
from pathlib import Path

import pytest

# Semver pattern — matches 0.1.0, 1.0.0-alpha.1, etc.
_SEMVER = re.compile(r"\d+\.\d+\.\d+")

# Extensions that must never appear in a release artifact.
_WEIGHT_EXTENSIONS = frozenset({".gguf", ".safetensors", ".pt", ".pth", ".ckpt"})

# File names that must never appear in a release artifact.
_FORBIDDEN_NAMES = frozenset({
    ".env", "convsim-core.spec", "pytest.ini", "setup.cfg", "tox.ini",
    ".coverage", "coverage.xml",
})

# Directory names that must never appear in a release artifact.
_FORBIDDEN_DIRS = frozenset({
    "__pycache__", ".venv", "venv", ".git", ".pytest_cache", ".mypy_cache",
    "htmlcov", "tests",
})

# Secret file pattern — matches common credential file names.
_SECRET_PATTERN = re.compile(
    r"\.(key|pem|pfx|p12)$"
    r"|_rsa$|_dsa$|_ecdsa$|_ed25519$"
    r"|^api_keys\.|^credentials\.|^config\.vdf$",
    re.IGNORECASE,
)

# Recognised installer / bundle extensions used to detect the artifact type.
_INSTALLER_EXTENSIONS = (".AppImage", ".deb", ".exe", ".msi", ".tar.gz")

# Application binaries that ship by name in the Windows portable depot layout
# and are NOT installer packages.  Excluded from the semver filename check,
# which is designed for installer filenames like "Conversation Simulator_0.1.0_x64-setup.exe".
_PORTABLE_APP_BINARIES = frozenset({
    "ConversationSimulator.exe",
    "MicrosoftEdgeWebView2Setup.exe",
    "convsim-core.exe",
    "llama-server.exe",
    "whisper-cli.exe",
    "sherpa-onnx-offline-tts.exe",
})


def _is_pyinstaller_internal(path: Path) -> bool:
    """Return True if path is inside a PyInstaller _internal/ directory.

    PyInstaller compiles Python sources to bytecode and stores them under
    _internal/ inside the application bundle.  Filtering these out prevents
    false positives from forbidden-file checks that expect no Python artefacts
    outside source-install paths.
    """
    return "_internal" in path.parts


def _main_app_bundles(artifact_dir: Path) -> list[Path]:
    """Return top-level .app bundles (excluding helper .apps nested in another).

    A macOS product bundle can embed helper .app bundles (e.g. inside
    Contents/Frameworks/); those carry their own versions and must not be
    treated as the shipped application when checking the version stamp.
    """
    bundles = [p for p in artifact_dir.rglob("*.app") if p.is_dir()]
    return [
        b for b in bundles
        if not any(parent.suffix == ".app" for parent in b.parents)
    ]


# ---------------------------------------------------------------------------
# Depot layout
# ---------------------------------------------------------------------------


class TestDepotLayout:
    def test_artifact_directory_is_non_empty(self, all_file_paths: list[Path]) -> None:
        assert all_file_paths, (
            "Artifact directory is empty — the desktop build may have failed"
        )

    def test_expected_installer_or_bundle_present(
        self, all_file_paths: list[Path], artifact_dir: Path
    ) -> None:
        """At least one recognised installer or bundle format must be present."""
        found = {
            ext
            for f in all_file_paths
            for ext in _INSTALLER_EXTENSIONS
            if f.name.endswith(ext)
        }
        # Also accept .app bundles (directories, not files) on macOS.
        app_bundles = list(artifact_dir.rglob("*.app"))
        assert found or app_bundles, (
            f"No recognised installer or bundle found under {artifact_dir}. "
            f"Expected one of: {', '.join(sorted(_INSTALLER_EXTENSIONS))} "
            "or a .app directory on macOS."
        )

    def test_no_empty_root_level_subdirectory(self, artifact_dir: Path) -> None:
        """Every top-level directory in the artifact must contain at least one file."""
        for subdir in artifact_dir.iterdir():
            if not subdir.is_dir():
                continue
            if subdir.name.startswith("."):
                continue
            contents = [p for p in subdir.rglob("*") if p.is_file()]
            assert contents, (
                f"Unexpected empty subdirectory in artifact root: {subdir.name}/"
            )


# ---------------------------------------------------------------------------
# Executable permissions
# ---------------------------------------------------------------------------


class TestExecutablePermissions:
    def test_appimage_is_executable(self, all_file_paths: list[Path]) -> None:
        """Linux AppImages must have the executable bit set."""
        appimages = [f for f in all_file_paths if f.name.endswith(".AppImage")]
        if not appimages:
            pytest.skip("No .AppImage in artifact — skipping AppImage permission check")
        for appimage in appimages:
            mode = appimage.stat().st_mode
            assert mode & stat.S_IXUSR, (
                f".AppImage is not executable (missing +x): {appimage.name}. "
                "Run: chmod +x " + str(appimage)
            )

    def test_macos_app_main_binary_is_executable(
        self, artifact_dir: Path
    ) -> None:
        """macOS .app bundle main binary must have the executable bit set."""
        if platform.system() != "Darwin":
            pytest.skip(
                "macOS .app executable check is only meaningful on macOS "
                "(cross-OS permission bits may not transfer)"
            )
        app_bundles = [p for p in artifact_dir.rglob("*.app") if p.is_dir()]
        if not app_bundles:
            pytest.skip("No .app bundle in artifact — skipping macOS permission check")
        for bundle in app_bundles:
            macos_dir = bundle / "Contents" / "MacOS"
            if not macos_dir.is_dir():
                continue
            binaries = [f for f in macos_dir.iterdir() if f.is_file()]
            assert binaries, (
                f"Contents/MacOS/ is empty in {bundle.name} — bundle may be malformed"
            )
            for binary in binaries:
                mode = binary.stat().st_mode
                assert mode & stat.S_IXUSR, (
                    f"macOS bundle binary is not executable: "
                    f"{bundle.name}/Contents/MacOS/{binary.name}"
                )


# ---------------------------------------------------------------------------
# Icon presence
# ---------------------------------------------------------------------------


class TestIconPresence:
    def test_macos_app_bundle_has_icns_icon(self, artifact_dir: Path) -> None:
        """A macOS .app bundle must contain an .icns icon in Contents/Resources/."""
        app_bundles = [p for p in artifact_dir.rglob("*.app") if p.is_dir()]
        if not app_bundles:
            pytest.skip("No .app bundle in artifact — skipping macOS icon check")
        for bundle in app_bundles:
            resources_dir = bundle / "Contents" / "Resources"
            if not resources_dir.is_dir():
                continue
            icns_files = list(resources_dir.glob("*.icns"))
            assert icns_files, (
                f"No .icns icon found in {bundle.name}/Contents/Resources/. "
                "The Tauri icon configuration may be missing an icns entry."
            )

    def test_linux_appimage_has_companion_icon(
        self, all_file_paths: list[Path]
    ) -> None:
        """A Linux AppImage should have a companion icon file in the same directory."""
        appimages = [f for f in all_file_paths if f.name.endswith(".AppImage")]
        if not appimages:
            pytest.skip("No .AppImage in artifact — skipping Linux icon check")
        for appimage in appimages:
            parent = appimage.parent
            companion_icons = (
                list(parent.glob("*.png"))
                + list(parent.glob("*.svg"))
                + list(parent.glob(".DirIcon"))
            )
            if not companion_icons:
                pytest.skip(
                    f"No companion icon found next to {appimage.name}. "
                    "AppImage icons may be embedded inside the image — "
                    "manual inspection via `--appimage-extract` is recommended."
                )


# ---------------------------------------------------------------------------
# Version stamping
# ---------------------------------------------------------------------------


class TestVersionStamping:
    def test_installer_filename_contains_semver(
        self, all_file_paths: list[Path]
    ) -> None:
        """Installer filenames must contain a semantic version number.

        Windows portable depot layout binaries (ConversationSimulator.exe,
        convsim-core.exe, etc.) are excluded: their version is recorded in
        version.txt at the depot root instead of in the filename.  The check
        is for installer/archive filenames such as
        "Conversation Simulator_0.1.0_x64-setup.exe" or "*.AppImage".
        """
        installers = [
            f
            for f in all_file_paths
            if any(f.name.endswith(ext) for ext in _INSTALLER_EXTENSIONS)
            and f.name not in _PORTABLE_APP_BINARIES
        ]
        if not installers:
            pytest.skip(
                "No installer files found — skipping version stamp filename check"
            )
        versioned = [f for f in installers if _SEMVER.search(f.name)]
        assert versioned, (
            "No installer filename contains a semver string (e.g. 0.1.0). "
            "Found: " + ", ".join(f.name for f in installers) + ". "
            "The version stamp step in the build workflow may not have run."
        )

    def test_version_is_not_zero_placeholder(
        self, all_file_paths: list[Path]
    ) -> None:
        """Version stamp must not be the default placeholder 0.0.0."""
        installers = [
            f
            for f in all_file_paths
            if any(f.name.endswith(ext) for ext in _INSTALLER_EXTENSIONS)
            and f.name not in _PORTABLE_APP_BINARIES
        ]
        if not installers:
            pytest.skip(
                "No installer files found — skipping version value check"
            )
        for f in installers:
            match = _SEMVER.search(f.name)
            if match:
                version = match.group()
                assert version != "0.0.0", (
                    f"Version stamp is 0.0.0 in {f.name}. "
                    "The version stamp step may not have run, or the wrong tag "
                    "was supplied to the build workflow."
                )

    def test_macos_app_info_plist_is_version_stamped(
        self, artifact_dir: Path
    ) -> None:
        """A macOS .app bundle must carry a stamped CFBundleShortVersionString.

        The macOS Steam depot ships the extracted .app bundle, not an installer
        file, so the filename-based checks above skip for it.  The version stamp
        for a .app lives in Contents/Info.plist, so verify it directly there —
        otherwise an unstamped (0.0.0) macOS build would sail through the deploy
        gate uninspected.  Runs on any OS since it only reads the plist file.
        """
        app_bundles = _main_app_bundles(artifact_dir)
        if not app_bundles:
            pytest.skip("No .app bundle in artifact — skipping macOS version check")
        checked = 0
        for bundle in app_bundles:
            plist_path = bundle / "Contents" / "Info.plist"
            if not plist_path.is_file():
                continue
            with plist_path.open("rb") as fh:
                info = plistlib.load(fh)
            version = info.get("CFBundleShortVersionString")
            assert version, (
                f"{bundle.name}/Contents/Info.plist has no "
                "CFBundleShortVersionString — the version stamp step may not "
                "have run."
            )
            assert _SEMVER.search(version), (
                f"CFBundleShortVersionString={version!r} in {bundle.name} is not "
                "a semantic version (e.g. 0.1.0)."
            )
            assert _SEMVER.search(version).group() != "0.0.0", (
                f"CFBundleShortVersionString is 0.0.0 in {bundle.name}. "
                "The version stamp step may not have run, or the wrong tag was "
                "supplied to the build workflow."
            )
            checked += 1
        if checked == 0:
            pytest.skip(
                "No .app bundle contained a Contents/Info.plist — "
                "skipping macOS version stamp check"
            )


# ---------------------------------------------------------------------------
# Forbidden patterns
# ---------------------------------------------------------------------------


class TestForbiddenPatterns:
    def test_no_model_weight_files(
        self, all_file_paths: list[Path], artifact_dir: Path
    ) -> None:
        """No model weight files (.gguf, .safetensors, .pt, etc.) in artifact.

        Mirrors compliance rule MD-04 enforced by depot-audit.sh.
        Model weights must be downloaded explicitly by the player, never bundled.
        """
        weight_files = [
            f for f in all_file_paths if f.suffix in _WEIGHT_EXTENSIONS
        ]
        assert not weight_files, (
            "Model weight files found in artifact (violates compliance rule MD-04): "
            + ", ".join(
                str(f.relative_to(artifact_dir)) for f in weight_files
            )
        )

    def test_no_large_bin_files_that_look_like_weights(
        self, all_file_paths: list[Path], artifact_dir: Path
    ) -> None:
        """Large .bin files that are not ELF/PE executables may be weight files."""
        WEIGHT_SIZE_THRESHOLD = 1_048_576  # 1 MiB — same as depot-audit.sh
        suspicious = []
        for f in all_file_paths:
            if f.suffix != ".bin":
                continue
            try:
                size = f.stat().st_size
            except OSError:
                continue
            if size <= WEIGHT_SIZE_THRESHOLD:
                continue
            try:
                # Read only the header — these files are >1 MiB (and weight
                # files can be many GB), so never load the whole file to check
                # 4 magic bytes.
                with f.open("rb") as fh:
                    magic = fh.read(4)
            except OSError:
                continue
            # ELF: 7f 45 4c 46 — PE: 4d 5a
            if magic[:4] == b"\x7fELF" or magic[:2] == b"MZ":
                continue
            suspicious.append(f)
        assert not suspicious, (
            "Large .bin files that may be weight files found in artifact: "
            + ", ".join(str(f.relative_to(artifact_dir)) for f in suspicious)
        )

    def test_no_dev_only_files(
        self, all_file_paths: list[Path], artifact_dir: Path
    ) -> None:
        """Developer-only files (.env, pytest.ini, convsim-core.spec) must not ship."""
        dev_files = [
            f
            for f in all_file_paths
            if f.name in _FORBIDDEN_NAMES
            and not _is_pyinstaller_internal(f)
        ]
        assert not dev_files, (
            "Developer-only files found in artifact: "
            + ", ".join(str(f.relative_to(artifact_dir)) for f in dev_files)
        )

    def test_no_forbidden_directories(
        self, all_dir_paths: list[Path], artifact_dir: Path
    ) -> None:
        """Forbidden directories (__pycache__, .venv, tests/, etc.) must not ship."""
        forbidden = [
            d
            for d in all_dir_paths
            if d.name in _FORBIDDEN_DIRS
            and not _is_pyinstaller_internal(d)
        ]
        assert not forbidden, (
            "Forbidden directories found in artifact: "
            + ", ".join(str(d.relative_to(artifact_dir)) for d in forbidden)
        )

    def test_no_secret_files(
        self, all_file_paths: list[Path], artifact_dir: Path
    ) -> None:
        """Secret and credential files (.key, .pem, config.vdf, etc.) must not ship.

        PyInstaller's _internal/ bundle legitimately contains public CA
        certificate bundles from dependencies (e.g. certifi's cacert.pem, pulled
        in transitively via httpx).  Those are not secrets, so _internal/ is
        excluded here — mirroring the other forbidden-pattern checks — to avoid
        false-positives that would abort the deploy on every real build.
        """
        secret_files = [
            f
            for f in all_file_paths
            if _SECRET_PATTERN.search(f.name)
            and not _is_pyinstaller_internal(f)
        ]
        assert not secret_files, (
            "Potential secret or credential files found in artifact: "
            + ", ".join(str(f.relative_to(artifact_dir)) for f in secret_files)
        )

    def test_no_python_source_files_outside_bundle(
        self, all_file_paths: list[Path], artifact_dir: Path
    ) -> None:
        """Python .py source files must not appear outside a PyInstaller bundle.

        Inside a .app bundle, _internal/ may legitimately contain .py files
        for package entry points.  Outside of _internal/ there should be none.
        """
        py_files = [
            f
            for f in all_file_paths
            if f.suffix == ".py" and not _is_pyinstaller_internal(f)
        ]
        assert not py_files, (
            "Python source (.py) files found outside the PyInstaller bundle: "
            + ", ".join(str(f.relative_to(artifact_dir)) for f in py_files)
            + ". Use the PyInstaller binary instead of shipping source files."
        )

    def test_no_models_directory(
        self, all_dir_paths: list[Path], artifact_dir: Path
    ) -> None:
        """A models/ directory must never appear in an artifact.

        Model files must live in the player's data directory after explicit
        download, never bundled with the application.
        """
        models_dirs = [d for d in all_dir_paths if d.name == "models"]
        assert not models_dirs, (
            "models/ directory found in artifact — model files must not be bundled: "
            + ", ".join(str(d.relative_to(artifact_dir)) for d in models_dirs)
        )


# ---------------------------------------------------------------------------
# Windows portable depot layout
# ---------------------------------------------------------------------------


class TestWindowsPortableLayout:
    """Windows Steam depot portable layout checks.

    The Windows Steam depot ships the raw application binary tree (not an NSIS
    installer or MSI package) so the Steam client can install the files directly.
    These tests run only when the artifact directory looks like a Windows portable
    depot (ConversationSimulator.exe at the root).

    See publishing/STEAM_DEPOT_CONTENTS.md — Windows depot section.
    """

    def _is_windows_portable_depot(self, artifact_dir: Path) -> bool:
        """Return True if this looks like a Windows portable depot."""
        return (artifact_dir / "ConversationSimulator.exe").is_file()

    def test_main_exe_at_depot_root(
        self, all_file_paths: list[Path], artifact_dir: Path
    ) -> None:
        """ConversationSimulator.exe must be at the depot root.

        Steam launch options point directly to this binary with the depot root
        as the working directory.  Placing it in a subdirectory would break
        both Steam launch and relative resource resolution.
        """
        if not self._is_windows_portable_depot(artifact_dir):
            pytest.skip("Not a Windows portable depot — skipping main exe check")
        root_exe = artifact_dir / "ConversationSimulator.exe"
        assert root_exe.is_file(), (
            "ConversationSimulator.exe not found at depot root. "
            "The Windows Steam depot must ship the application binary directly "
            "at the depot root, not wrapped in an installer. "
            "Check the packaging step in release.yml."
        )

    def test_convsim_core_sidecar_present(
        self, all_file_paths: list[Path], artifact_dir: Path
    ) -> None:
        """convsim-core.exe sidecar must be present under resources/bin/."""
        if not self._is_windows_portable_depot(artifact_dir):
            pytest.skip("Not a Windows portable depot — skipping sidecar check")
        sidecar = artifact_dir / "resources" / "bin" / "convsim-core.exe"
        assert sidecar.is_file(), (
            "convsim-core.exe sidecar not found at resources/bin/convsim-core.exe. "
            "The PyInstaller backend binary must be present in the Windows Steam depot. "
            "Verify the convsim-core build step and the Tauri resources/ bundling."
        )

    def test_installscript_vdf_present_and_parseable(
        self, all_file_paths: list[Path], artifact_dir: Path
    ) -> None:
        """installscript.vdf must be at the depot root and reference the WebView2 bootstrapper.

        Steam runs InstallScript with elevated privileges on first launch, which
        is required to install the WebView2 Evergreen Runtime on systems that do
        not already have it (Windows 10 without the runtime pre-installed).
        """
        if not self._is_windows_portable_depot(artifact_dir):
            pytest.skip("Not a Windows portable depot — skipping installscript.vdf check")
        vdf_path = artifact_dir / "installscript.vdf"
        assert vdf_path.is_file(), (
            "installscript.vdf not found at depot root. "
            "The Windows Steam depot requires a Steam InstallScript to bootstrap "
            "the WebView2 Evergreen Runtime on first launch. "
            "See steam/installscript.vdf and publishing/STEAM_DEPOT_CONTENTS.md."
        )
        content = vdf_path.read_text(encoding="utf-8", errors="replace")
        assert "InstallScript" in content, (
            "installscript.vdf does not contain the 'InstallScript' root key — "
            "the file may be truncated or malformed."
        )
        assert "MicrosoftEdgeWebView2Setup" in content or "WebView2" in content, (
            "installscript.vdf does not reference the WebView2 bootstrapper. "
            "Tauri Windows apps require the WebView2 Evergreen Runtime; "
            "the InstallScript must invoke MicrosoftEdgeWebView2Setup.exe."
        )

    def test_webview2_bootstrapper_present(
        self, all_file_paths: list[Path], artifact_dir: Path
    ) -> None:
        """MicrosoftEdgeWebView2Setup.exe bootstrapper must be at the depot root.

        The Steam InstallScript in installscript.vdf invokes this bootstrapper
        to install the WebView2 Evergreen Runtime on first launch.  The bootstrapper
        must be present at the depot root so Steam can resolve the path.
        """
        if not self._is_windows_portable_depot(artifact_dir):
            pytest.skip(
                "Not a Windows portable depot — skipping WebView2 bootstrapper check"
            )
        bootstrapper = artifact_dir / "MicrosoftEdgeWebView2Setup.exe"
        assert bootstrapper.is_file(), (
            "MicrosoftEdgeWebView2Setup.exe not found at depot root. "
            "The WebView2 Evergreen Bootstrapper must be included in the Windows "
            "Steam depot so the Steam InstallScript can install the WebView2 Runtime "
            "on first launch. See the packaging step in release.yml."
        )

    def test_no_installer_packages_in_depot(
        self, all_file_paths: list[Path], artifact_dir: Path
    ) -> None:
        """NSIS setup installers and MSI packages must never appear in the depot.

        A Steam depot must contain application files, not installer packages.
        Shipping a setup wizard causes Steam's "Play" button to launch the
        installer UI (or fail silently), which fails Valve review and strands
        every beta tester.  See issue #408.
        """
        if not self._is_windows_portable_depot(artifact_dir):
            pytest.skip(
                "Not a Windows portable depot — skipping installer-in-depot check"
            )
        installer_files = [
            f
            for f in all_file_paths
            if f.name.endswith("-setup.exe") or f.suffix == ".msi"
        ]
        assert not installer_files, (
            "NSIS installer or MSI package found in Windows Steam depot "
            "(Steam depots must ship app files, not installer packages — "
            "this will fail Valve review): "
            + ", ".join(str(f.relative_to(artifact_dir)) for f in installer_files)
        )

    def test_windows_depot_has_version_stamp(
        self, all_file_paths: list[Path], artifact_dir: Path
    ) -> None:
        """version.txt must be present at the depot root with a valid semver string.

        The Windows portable depot binary (ConversationSimulator.exe) has no
        version in its filename, unlike installer filenames.  The packaging step
        writes version.txt so artifact inspection can verify the version stamp
        without parsing PE resources or installer metadata.
        """
        if not self._is_windows_portable_depot(artifact_dir):
            pytest.skip(
                "Not a Windows portable depot — skipping version.txt check"
            )
        version_file = artifact_dir / "version.txt"
        assert version_file.is_file(), (
            "version.txt not found at Windows depot root. "
            "The packaging step in release.yml must write version.txt with the "
            "release tag version so artifact inspection can verify the version stamp."
        )
        version = version_file.read_text(encoding="utf-8").strip()
        assert _SEMVER.search(version), (
            f"version.txt contains {version!r}, not a semantic version string "
            "(expected e.g. '0.1.0'). "
            "The version stamp step in the build workflow may not have run."
        )
        assert _SEMVER.search(version).group() != "0.0.0", (
            f"version.txt contains '0.0.0' placeholder in Windows depot. "
            "The version stamp step may not have run, or the wrong tag was "
            "supplied to the build workflow."
        )
