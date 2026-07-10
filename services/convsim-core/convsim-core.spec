# SPDX-License-Identifier: Apache-2.0
# PyInstaller spec for convsim-core — produces a self-contained single-file
# executable that does not require a developer venv or Python installation.
#
# Usage (run from services/convsim-core/ with the project venv active):
#   pip install pyinstaller
#   pyinstaller convsim-core.spec
#
# Or use the build wrapper:
#   ./scripts/build-core.sh           (Linux / macOS)
#   .\scripts\build-core.ps1          (Windows PowerShell)
#
# Output:
#   dist/convsim-core     (Linux / macOS)
#   dist/convsim-core.exe (Windows)
#
# The build script copies the output to
#   apps/desktop/src-tauri/resources/bin/
# so the Tauri shell can locate it via find_core_executable().
#
# Official packs are embedded as data files; they land under sys._MEIPASS/packs/
# at runtime. config.py detects sys._MEIPASS and uses that path automatically.
# Large model weights (.gguf / .safetensors / .bin) are never bundled; the
# in-app model registry handles downloading them on first use.

from pathlib import Path  # noqa: F401 — used below; PyInstaller evaluates this file

block_cipher = None

# Repository root is two levels above services/convsim-core/
_SPEC_DIR = Path(SPECPATH)         # services/convsim-core/   # noqa: F821
_REPO_ROOT = _SPEC_DIR.parents[1]  # repo root

a = Analysis(
    ['convsim_core/main.py'],
    pathex=[str(_SPEC_DIR)],
    binaries=[],
    datas=[
        # JSON schemas bundled for offline pack validation (no network needed).
        ('convsim_core/schemas', 'convsim_core/schemas'),
        # Read-only official scenario packs shipped with the app.
        # These land at sys._MEIPASS/packs/official/ and are found by config.py
        # when it detects the frozen (PyInstaller) environment.
        (str(_REPO_ROOT / 'packs' / 'official'), 'packs/official'),
    ],
    hiddenimports=[
        # uvicorn resolves protocol and loop implementations at runtime.
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # pydantic v2 internals loaded via __getattr__ at import time.
        'pydantic.deprecated.decorators',
        # onnxruntime is an optional extra (CONVSIM_VAD_WORKER_ID=silero_vad);
        # it is not installed by default and should only be imported when the
        # caller explicitly requests Silero VAD.  List it so PyInstaller does
        # not raise ImportError if it happens to be present in the venv.
        'onnxruntime',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Development / test-only packages — must not ship in the release binary.
        'pytest',
        'pytest_asyncio',
        '_pytest',
        'pip',
        'setuptools',
        'distutils',
        'pkg_resources',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

# Single-file mode: all dependencies are packed into the executable and
# extracted to a temporary directory on first launch.  The startup overhead
# (~1–2 s) is acceptable for a long-running background service.
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='convsim-core',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    codesign_identity=None,
    entitlements_file=None,
)
