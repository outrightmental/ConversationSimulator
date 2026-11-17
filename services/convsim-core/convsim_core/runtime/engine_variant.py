# SPDX-License-Identifier: Apache-2.0
"""Which llama.cpp build answers: the graphics card or the processor (issue #531).

Windows and Linux builds ship two engines (issue #530): the CPU build, flat in
the runtime directory exactly as before, and the Vulkan build in its own
``vulkan/`` directory, so that starting the CPU build never loads the Vulkan
backend library or touches the graphics driver. macOS ships one build, which
uses Metal.

``engine_variant`` is the player's choice: ``auto`` (the default), ``cpu`` or
``vulkan``. This module turns it into an engine start:

* **Auto** asks the Vulkan build what it can use (``llama-server
  --list-devices``, run from the Vulkan directory) and starts it when a
  discrete card is listed, or a card on :data:`MEASURED_ALLOW_LIST`.
  Integrated graphics alone, or no card, starts the processor build: an
  integrated chip gains on reading the prompt and not reliably on writing the
  reply, and #536 decides that per machine.
* **Layer placement is left to the engine.** No ``--n-gpu-layers`` is passed
  unless the player set one: the engine's own fit is the default, and an
  explicit count turns it off. The fit needs the explicit context size the
  launch configuration already passes (#523).
* **A fail-safe ladder.** Each rung ends on the processor build:

  - *probe*: ``--list-devices`` crashes, exits non-zero or does not answer
    (or lists nothing when the player asked for the card);
  - *load*: the Vulkan build does not load the model;
  - *first generation*: a fixed check request fails;
  - *wrong output*: that check, at temperature 0 with no grammar, does not
    continue "1, 2, …, 8," with 9. A broken driver can load, run and produce
    garbage, and a grammar would turn the garbage into valid JSON, so the check
    is a known answer rather than a well-formed one;
  - *crash*: the Vulkan engine dies during a conversation. The turn in flight
    is retried on the processor (``routers/sessions.py``).

* **Remember, and say so once.** A failure is stored against a fingerprint of
  the graphics adapters, their driver versions and the engine build, so the
  app does not retry on every start; a driver update changes the fingerprint
  and clears it. The player sees one notice, and Settings offers "Try the
  graphics card again".

Nothing here is synced: the setting and the record live in the local
database, which Steam Cloud never uploads (see ``steam_cloud.py``).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

import httpx

from convsim_core.runtime.llama_cpp_pin import pinned_tag
from convsim_core.runtime.procflags import CREATE_NO_WINDOW

logger = logging.getLogger(__name__)

#: The player's choices, in the order Settings offers them.
ENGINE_VARIANT_CHOICES: tuple[str, ...] = ("auto", "cpu", "vulkan")
DEFAULT_ENGINE_VARIANT = "auto"
#: Same ``runtime_setting.`` namespace as the other launch settings.
ENGINE_VARIANT_SETTING_KEY = "runtime_setting.engine_variant"
#: The stored graphics-card failure (one JSON object, or absent).
GPU_FAILURE_KEY = "engine.gpu_failure"

#: The ladder's rungs, as they are stored and reported.
RUNG_PROBE = "probe"
RUNG_LOAD = "load"
RUNG_FIRST_GENERATION = "first_generation"
RUNG_WRONG_OUTPUT = "wrong_output"
RUNG_CRASH = "crash"
RUNGS: tuple[str, ...] = (RUNG_PROBE, RUNG_LOAD, RUNG_FIRST_GENERATION, RUNG_WRONG_OUTPUT, RUNG_CRASH)

#: Seconds ``--list-devices`` may take. It answers in well under a second on a
#: working driver; a driver that hangs here must not hold the engine start.
PROBE_TIMEOUT = 20.0
#: Seconds the check request may take. The first request after a Vulkan
#: engine's first-ever start compiles its shaders, which takes seconds.
CANARY_TIMEOUT = 60.0
#: The check request: greedy decoding must continue the count with 9.
CANARY_PROMPT = "1, 2, 3, 4, 5, 6, 7, 8,"
CANARY_EXPECTED = "9"
CANARY_TOKENS = 4

#: Integrated graphics that measured faster on the Vulkan build than on the
#: processor, by name pattern (case-insensitive regex). Auto treats a listed
#: device like a discrete card. The Steam Deck joins once #532 records a row
#: showing Vulkan ahead on it; until then the list is empty.
MEASURED_ALLOW_LIST: tuple[str, ...] = ()

# ── Executables ───────────────────────────────────────────────────────────────


def default_build_variant() -> str:
    """The variant of the default build: ``metal`` on macOS, else ``cpu``."""
    return "metal" if sys.platform == "darwin" else "cpu"


@dataclass(frozen=True)
class EngineBuild:
    """One llama-server build this install can start."""

    variant: str  # "cpu" | "vulkan" | "metal"
    executable: str
    source: str  # "override" | "bundled" | "user" | "path"


@dataclass(frozen=True)
class EngineBuilds:
    """The builds found on this machine. ``vulkan`` is None when there is none."""

    default: Optional[EngineBuild]
    vulkan: Optional[EngineBuild]

    def available(self) -> list[str]:
        return [b.variant for b in (self.default, self.vulkan) if b is not None]


def find_engine_builds(default_executable: Optional[str] = None) -> EngineBuilds:
    """Resolve the default and Vulkan builds (see ``sidecar.find_executable``).

    ``default_executable`` is a default build the caller already resolved.
    """
    from convsim_core.runtime.sidecar import (
        executable_source,
        find_executable,
        find_vulkan_executable,
    )

    default_exe = default_executable or find_executable()
    default = (
        EngineBuild(default_build_variant(), default_exe, executable_source(default_exe))
        if default_exe
        else None
    )
    vulkan_exe = find_vulkan_executable()
    vulkan = (
        EngineBuild("vulkan", vulkan_exe, executable_source(vulkan_exe, vulkan=True))
        if vulkan_exe
        else None
    )
    return EngineBuilds(default=default, vulkan=vulkan)


# ── Device probe ──────────────────────────────────────────────────────────────

DEVICE_DISCRETE = "discrete"
DEVICE_INTEGRATED = "integrated"
DEVICE_SOFTWARE = "software"
DEVICE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class EngineDevice:
    """One device ``llama-server --list-devices`` reported."""

    backend_id: str  # e.g. "Vulkan0"
    name: str
    total_mib: Optional[int]
    free_mib: Optional[int]
    kind: str


_DEVICE_WITH_MEMORY = re.compile(
    r"^\s*(?P<id>[A-Za-z][\w-]*?\d+)\s*:\s*(?P<name>.+?)\s*"
    r"\((?P<total>\d+)\s*MiB,\s*(?P<free>\d+)\s*MiB free\)\s*$"
)
_DEVICE_NAME_ONLY = re.compile(r"^\s*(?P<id>[A-Za-z][\w-]*?\d+)\s*:\s*(?P<name>.+?)\s*$")

_SOFTWARE_PATTERNS = (
    r"llvmpipe", r"lavapipe", r"swiftshader", r"softpipe", r"microsoft basic render",
)
_INTEGRATED_PATTERNS = (
    # Intel: every integrated chip, including the Arc-branded ones that carry no
    # A/B model number (Meteor Lake "Arc(TM) Graphics", Lunar Lake "Arc 140V").
    r"\buhd\b", r"\biris\b", r"\bhd graphics\b", r"graphics controller",
    r"^intel(\(r\))? graphics\b", r"intel(\(r\))? arc(\(tm\))? graphics\b",
    r"intel(\(r\))? arc(\(tm\))? \d{3}v\b",
    # AMD APUs: "Radeon(TM) Graphics", "Radeon 780M", the Steam Deck's custom
    # chip, and the RADV code names Mesa appends on Linux.
    r"radeon(\(tm\))? graphics", r"\bradeon vega\b", r"\bvega \d+ graphics",
    r"radeon(\(tm\))? \d{3}m\b", r"amd custom gpu",
    r"\(radv (vangogh|renoir|cezanne|rembrandt|phoenix|raphael|mendocino|picasso|raven"
    r"|lucienne|barcelo|krackan|strix|gfx1103|gfx1150|gfx1151)",
    # Phone-class and SoC graphics.
    r"\badreno\b", r"\bmali\b", r"\bpowervr\b", r"\bvivante\b", r"\btegra\b", r"\borin\b",
    r"^apple m\d",
)
_DISCRETE_PATTERNS = (
    r"\bnvidia\b", r"\bgeforce\b", r"\b[rg]tx\b", r"\bquadro\b", r"\btesla\b",
    r"radeon(\(tm\))?\s+(rx|pro|vii|r9|r7)\b", r"\bfirepro\b", r"\binstinct\b",
    r"arc(\(tm\))?\s+(pro\s+)?[ab]\d{3}\b",
)


def _matches(name: str, patterns: Iterable[str]) -> bool:
    return any(re.search(p, name, re.IGNORECASE) for p in patterns)


def classify_device(name: str, total_mib: Optional[int] = None, free_mib: Optional[int] = None) -> str:
    """``discrete``, ``integrated``, ``software`` or ``unknown`` for a device name.

    The probe output carries no device type, so the name decides, with one
    memory hint: a device that reports more free memory than it has is sharing
    system memory, which only integrated graphics do. A name that matches
    nothing is ``unknown``, which Auto treats like integrated graphics: a
    wrong guess in that direction costs speed the player never had, a wrong
    guess the other way could make a working conversation slower.
    """
    if _matches(name, _SOFTWARE_PATTERNS):
        return DEVICE_SOFTWARE
    if _matches(name, _INTEGRATED_PATTERNS):
        return DEVICE_INTEGRATED
    if total_mib is not None and free_mib is not None and free_mib > total_mib:
        return DEVICE_INTEGRATED
    if _matches(name, _DISCRETE_PATTERNS):
        return DEVICE_DISCRETE
    return DEVICE_UNKNOWN


def parse_list_devices(output: str) -> list[EngineDevice]:
    """The devices in ``llama-server --list-devices`` output.

    The engine prints ``Available devices:`` followed by one indented line per
    device, e.g. ``  Vulkan0: NVIDIA GeForce RTX 4080 Laptop GPU (11995 MiB,
    11227 MiB free)``. Anything before the header (backend loading lines in
    verbose mode) is ignored.
    """
    devices: list[EngineDevice] = []
    lines = output.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip().lower().startswith("available devices"))
    except StopIteration:
        return devices
    for line in lines[start + 1:]:
        if not line.strip():
            continue
        match = _DEVICE_WITH_MEMORY.match(line)
        if match:
            total = int(match.group("total"))
            free = int(match.group("free"))
            name = match.group("name")
            devices.append(EngineDevice(match.group("id"), name, total, free, classify_device(name, total, free)))
            continue
        match = _DEVICE_NAME_ONLY.match(line)
        if match and line[:1].isspace():
            name = match.group("name")
            devices.append(EngineDevice(match.group("id"), name, None, None, classify_device(name)))
            continue
        if not line[:1].isspace():
            break  # past the device list
    return devices


@dataclass(frozen=True)
class ProbeResult:
    """What ``--list-devices`` said, or why it said nothing."""

    ok: bool
    devices: tuple[EngineDevice, ...] = ()
    error: Optional[str] = None
    output: str = ""


async def probe_devices(executable: str, *, timeout: float = PROBE_TIMEOUT) -> ProbeResult:
    """Run ``<executable> --list-devices`` from its own directory. Never raises."""
    exe_dir = Path(executable).parent
    cwd = str(exe_dir) if exe_dir.is_absolute() and exe_dir.is_dir() else None
    try:
        proc = await asyncio.create_subprocess_exec(
            executable,
            "--list-devices",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL,
            cwd=cwd,
            creationflags=CREATE_NO_WINDOW,
        )
    except OSError as exc:
        return ProbeResult(ok=False, error=f"could not run --list-devices: {exc}")
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass
        return ProbeResult(ok=False, error=f"--list-devices did not answer within {timeout:.0f} s")
    text = (stdout or b"").decode(errors="replace")
    if proc.returncode != 0:
        return ProbeResult(
            ok=False,
            error=f"--list-devices exited with code {proc.returncode}",
            output=text[-2000:],
        )
    return ProbeResult(ok=True, devices=tuple(parse_list_devices(text)), output=text[-2000:])


# ── Choosing ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class VariantDecision:
    """Which build to start first, and why.

    ``failure_rung`` is set when the decision is itself a ladder failure (the
    probe rung): the caller records it and starts the default build.
    """

    variant: str  # "vulkan" or the default build's variant
    reason: str
    device: Optional[EngineDevice] = None
    failure_rung: Optional[str] = None


def _allow_listed(device: EngineDevice, allow_list: Sequence[str]) -> bool:
    return any(re.search(p, device.name, re.IGNORECASE) for p in allow_list)


def choose_variant(
    setting: str,
    builds: EngineBuilds,
    probe: Optional[ProbeResult],
    *,
    remembered_failure: bool = False,
    allow_list: Sequence[str] = MEASURED_ALLOW_LIST,
) -> VariantDecision:
    """Decide which build to start. Pure: every input is passed in."""
    default_variant = builds.default.variant if builds.default else default_build_variant()
    if builds.vulkan is None:
        return VariantDecision(default_variant, "this install has no graphics-card engine")
    if setting == "cpu":
        return VariantDecision(default_variant, "the player chose the processor")
    if remembered_failure:
        return VariantDecision(
            default_variant,
            "the graphics card failed before with this card, driver and engine",
        )
    if probe is None or not probe.ok:
        detail = probe.error if probe is not None else "no probe was run"
        return VariantDecision(default_variant, f"device probe failed: {detail}", failure_rung=RUNG_PROBE)

    usable = [d for d in probe.devices if d.kind != DEVICE_SOFTWARE]
    preferred = [d for d in usable if d.kind == DEVICE_DISCRETE or _allow_listed(d, allow_list)]
    if preferred:
        return VariantDecision("vulkan", f"{preferred[0].kind} device listed", device=preferred[0])
    if setting == "vulkan":
        if usable:
            return VariantDecision("vulkan", "the player chose the graphics card", device=usable[0])
        return VariantDecision(
            default_variant,
            "the player chose the graphics card, but the engine lists no device",
            failure_rung=RUNG_PROBE,
        )
    if usable:
        return VariantDecision(
            default_variant, f"only {usable[0].kind} graphics listed ({usable[0].name})"
        )
    return VariantDecision(default_variant, "the engine lists no graphics device")


# ── Fingerprint: the card, its driver, the engine ─────────────────────────────


@dataclass(frozen=True)
class GraphicsAdapter:
    """A graphics adapter as the operating system reports it."""

    name: str
    driver_version: str


_WINDOWS_DISPLAY_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"


def _windows_adapters() -> list[GraphicsAdapter]:
    import winreg  # type: ignore[import-not-found]

    adapters: list[GraphicsAdapter] = []
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _WINDOWS_DISPLAY_CLASS) as root:
        index = 0
        while True:
            try:
                sub = winreg.EnumKey(root, index)
            except OSError:
                break
            index += 1
            if not sub.isdigit():
                continue
            try:
                with winreg.OpenKey(root, sub) as key:
                    name = str(winreg.QueryValueEx(key, "DriverDesc")[0])
                    version = str(winreg.QueryValueEx(key, "DriverVersion")[0])
            except OSError:
                continue
            adapters.append(GraphicsAdapter(name, version))
    return adapters


def _linux_adapters() -> list[GraphicsAdapter]:
    """Kernel driver per card, plus the identity of each installed Vulkan driver.

    Mesa's Vulkan drivers carry no version the kernel reports, so each ICD
    library's size and modification time stand in for it: a driver update
    replaces the file.
    """
    adapters: list[GraphicsAdapter] = []
    drm = Path("/sys/class/drm")
    release = os.uname().release if hasattr(os, "uname") else ""
    for card in sorted(drm.glob("card[0-9]*")):
        if "-" in card.name:
            continue  # a connector, not a card
        device = card / "device"
        try:
            vendor = (device / "vendor").read_text().strip()
            product = (device / "device").read_text().strip()
            module = os.path.basename(os.path.realpath(device / "driver"))
        except OSError:
            continue
        version = ""
        try:
            version = Path(f"/sys/module/{module}/version").read_text().strip()
        except OSError:
            pass
        adapters.append(GraphicsAdapter(f"{vendor}:{product} {module}", version or release))
    for icd_dir in (Path("/usr/share/vulkan/icd.d"), Path("/etc/vulkan/icd.d")):
        for icd in sorted(icd_dir.glob("*.json")):
            try:
                library = json.loads(icd.read_text()).get("ICD", {}).get("library_path", "")
                stat = os.stat(library) if library and os.path.isabs(library) else os.stat(icd)
            except (OSError, ValueError, AttributeError):
                continue
            adapters.append(GraphicsAdapter(f"vulkan-icd {icd.name}", f"{stat.st_size}:{int(stat.st_mtime)}"))
    return adapters


def os_graphics_adapters() -> list[GraphicsAdapter]:
    """The graphics adapters and driver versions the OS reports. Never raises."""
    try:
        if sys.platform == "win32":
            return _windows_adapters()
        if sys.platform.startswith("linux"):
            return _linux_adapters()
    except Exception as exc:  # noqa: BLE001 — a fingerprint must never block a start
        logger.info("graphics adapter lookup failed: %s", exc)
    return []


def gpu_fingerprint(
    vulkan_build: Optional[EngineBuild],
    adapters: Optional[Sequence[GraphicsAdapter]] = None,
) -> str:
    """A short hash of the graphics adapters, their drivers and the Vulkan engine.

    Any of them changing gives a different fingerprint, which clears a stored
    failure: a new driver or a new engine deserves another try.
    """
    if adapters is None:
        adapters = os_graphics_adapters()
    engine: dict[str, Any] = {"tag": pinned_tag()}
    if vulkan_build is not None:
        engine["executable"] = vulkan_build.executable
        try:
            engine["size"] = os.path.getsize(vulkan_build.executable)
        except OSError:
            engine["size"] = None
    payload = {
        "engine": engine,
        "adapters": sorted([a.name, a.driver_version] for a in adapters),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return digest[:16]


# ── Stored state ──────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_setting(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM user_settings WHERE key = ?", (key,)).fetchone()
    return None if row is None else row["value"]


def _set_setting(conn: sqlite3.Connection, key: str, value: Optional[str]) -> None:
    if value is None:
        conn.execute("DELETE FROM user_settings WHERE key = ?", (key,))
    else:
        conn.execute(
            """
            INSERT INTO user_settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value),
        )
    conn.commit()


def load_engine_variant_setting(conn: Optional[sqlite3.Connection]) -> str:
    """The player's ``engine_variant``; ``auto`` when unset or unreadable."""
    if conn is None:
        return DEFAULT_ENGINE_VARIANT
    try:
        raw = _get_setting(conn, ENGINE_VARIANT_SETTING_KEY)
    except sqlite3.Error:
        return DEFAULT_ENGINE_VARIANT
    return raw if raw in ENGINE_VARIANT_CHOICES else DEFAULT_ENGINE_VARIANT


@dataclass
class GpuFailure:
    """A graphics-card failure, remembered against :func:`gpu_fingerprint`."""

    fingerprint: str
    rung: str
    detail: str
    device: Optional[str] = None
    at: str = field(default_factory=_now)
    notice_seen: bool = False

    def public(self) -> dict[str, Any]:
        return {"rung": self.rung, "detail": self.detail, "device": self.device, "at": self.at}


def load_gpu_failure(conn: Optional[sqlite3.Connection]) -> Optional[GpuFailure]:
    if conn is None:
        return None
    try:
        raw = _get_setting(conn, GPU_FAILURE_KEY)
    except sqlite3.Error:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return GpuFailure(
            fingerprint=str(data["fingerprint"]),
            rung=str(data["rung"]),
            detail=str(data.get("detail") or ""),
            device=data.get("device"),
            at=str(data.get("at") or _now()),
            notice_seen=bool(data.get("notice_seen", False)),
        )
    except (ValueError, KeyError, TypeError):
        return None


def save_gpu_failure(conn: sqlite3.Connection, failure: GpuFailure) -> None:
    _set_setting(conn, GPU_FAILURE_KEY, json.dumps(asdict(failure)))


def clear_gpu_failure(conn: sqlite3.Connection) -> None:
    _set_setting(conn, GPU_FAILURE_KEY, None)


def mark_gpu_notice_seen(conn: sqlite3.Connection) -> None:
    failure = load_gpu_failure(conn)
    if failure is not None and not failure.notice_seen:
        failure.notice_seen = True
        save_gpu_failure(conn, failure)


# ── What the status endpoint reports ──────────────────────────────────────────


@dataclass
class EngineSelectionState:
    """The last engine start's decision, kept on ``app.state.engine_selection``."""

    decided_variant: Optional[str] = None
    reason: Optional[str] = None
    device: Optional[str] = None
    devices: list[dict[str, Any]] = field(default_factory=list)
    fell_back_from: Optional[str] = None


def selection_state(app: Any) -> EngineSelectionState:
    """The app's selection state; a throwaway one when there is no app."""
    app_state = getattr(app, "state", None)
    if app_state is None:
        return EngineSelectionState()
    state = getattr(app_state, "engine_selection", None)
    if not isinstance(state, EngineSelectionState):
        state = EngineSelectionState()
        try:
            app_state.engine_selection = state
        except AttributeError:  # pragma: no cover — a read-only stand-in
            pass
    return state


# ── The check request ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CanaryResult:
    ok: bool
    rung: Optional[str] = None
    detail: str = ""
    text: str = ""


def canary_passes(text: str) -> bool:
    """True when the engine continued the count: "9" within its first characters."""
    return text.strip()[:6].lstrip(" ,").startswith(CANARY_EXPECTED)


async def run_canary(base_url: str, *, timeout: float = CANARY_TIMEOUT) -> CanaryResult:
    """Ask the engine to continue a count at temperature 0, with no grammar."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=5.0)) as client:
            resp = await client.post(
                f"{base_url}/completion",
                json={
                    "prompt": CANARY_PROMPT,
                    "n_predict": CANARY_TOKENS,
                    "temperature": 0,
                    "cache_prompt": False,
                },
            )
    except (httpx.HTTPError, OSError) as exc:
        return CanaryResult(False, RUNG_FIRST_GENERATION, f"check request failed: {type(exc).__name__}: {exc}")
    if resp.status_code != 200:
        return CanaryResult(
            False, RUNG_FIRST_GENERATION,
            f"check request returned HTTP {resp.status_code}: {resp.text[:200]}",
        )
    try:
        text = str(resp.json().get("content", ""))
    except ValueError:
        return CanaryResult(False, RUNG_FIRST_GENERATION, "check request returned no JSON")
    if not canary_passes(text):
        return CanaryResult(
            False, RUNG_WRONG_OUTPUT,
            f"expected the count to continue with {CANARY_EXPECTED!r}, got {text[:40]!r}", text,
        )
    return CanaryResult(True, text=text)


# ── The ladder ────────────────────────────────────────────────────────────────


async def start_engine(
    app: Any,
    sidecar: Any,
    *,
    model_path: str,
    launch: Any,
    conn: Optional[sqlite3.Connection],
    startup_timeout: float = 120.0,
    gpu_layers: Optional[int] = None,
    threads: Optional[int] = None,
    port: Optional[int] = None,
    builds: Optional[EngineBuilds] = None,
    adapters: Optional[Sequence[GraphicsAdapter]] = None,
    probe: Optional[Callable[[str], Any]] = None,
) -> str:
    """Start the managed engine on the right build, falling back to the processor.

    Returns the variant that is running. Raises what ``sidecar.start`` raises
    when the default build itself cannot start, and RuntimeError when no
    engine is installed. ``port`` defaults to the sidecar's own default.
    ``builds``, ``adapters`` and ``probe`` are for tests.

    The caller holds ``sidecar.start_lock``.
    """
    if builds is None:
        builds = find_engine_builds()
    if builds.default is None and builds.vulkan is None:
        raise RuntimeError(
            "llama-server executable not found. Install llama.cpp or set the "
            "'executable' field in the request."
        )
    state = selection_state(app)
    setting = load_engine_variant_setting(conn)

    async def _start(build: EngineBuild) -> None:
        kwargs: dict[str, Any] = {}
        if port is not None:
            kwargs["port"] = port
        await sidecar.start(
            model_path=model_path,
            executable=build.executable,
            variant=build.variant,
            launch=launch,
            # The launch configuration decides the context (#523).
            context_length=None,
            gpu_layers=gpu_layers,
            threads=threads,
            startup_timeout=startup_timeout,
            **kwargs,
        )

    decision = VariantDecision(builds.default.variant if builds.default else "vulkan", "only build")
    fingerprint: Optional[str] = None
    if builds.vulkan is not None and builds.default is not None and setting != "cpu":
        fingerprint = await asyncio.to_thread(gpu_fingerprint, builds.vulkan, adapters)
        failure = load_gpu_failure(conn)
        if failure is not None and failure.fingerprint != fingerprint and conn is not None:
            logger.info("graphics card, driver or engine changed since its failure; trying the card again")
            clear_gpu_failure(conn)
            failure = None
        result: Optional[ProbeResult] = None
        if failure is None:
            runner = probe or (lambda exe: probe_devices(exe, timeout=min(PROBE_TIMEOUT, startup_timeout)))
            result = await runner(builds.vulkan.executable)
            state.devices = [asdict(d) for d in result.devices]
        decision = choose_variant(setting, builds, result, remembered_failure=failure is not None)
        if decision.failure_rung is not None:
            _record_failure(conn, fingerprint, decision.failure_rung, decision.reason, None)
    elif builds.default is not None:
        decision = choose_variant(setting, builds, None)

    state.decided_variant = decision.variant
    state.reason = decision.reason
    state.device = decision.device.name if decision.device else None
    state.fell_back_from = None
    logger.info("engine variant: %s (%s)", decision.variant, decision.reason)

    if decision.variant == "vulkan" and builds.vulkan is not None:
        rung: Optional[str] = None
        detail = ""
        try:
            await _start(builds.vulkan)
        except (RuntimeError, TimeoutError) as exc:
            if _is_port_conflict(sidecar) or builds.default is None:
                raise
            rung, detail = RUNG_LOAD, str(exc)
        else:
            if builds.default is None:
                return "vulkan"
            canary = await run_canary(f"http://{sidecar.host}:{sidecar.port}")
            if canary.ok:
                return "vulkan"
            rung, detail = canary.rung or RUNG_FIRST_GENERATION, canary.detail
            await _stop_and_release(sidecar)
        logger.warning("graphics-card engine failed (%s): %s; starting the processor engine", rung, detail)
        if fingerprint is None:
            fingerprint = await asyncio.to_thread(gpu_fingerprint, builds.vulkan, adapters)
        _record_failure(conn, fingerprint, rung, detail, state.device)
        state.fell_back_from = "vulkan"
        state.decided_variant = builds.default.variant
        state.reason = f"the graphics card failed ({rung}); using the processor"

    assert builds.default is not None
    await _start(builds.default)
    return builds.default.variant


async def _stop_and_release(sidecar: Any) -> None:
    """Stop the engine and wait for its port, so the next build can bind it."""
    from convsim_core.runtime.sidecar import wait_for_port_release

    await sidecar.stop()
    host, port = getattr(sidecar, "host", None), getattr(sidecar, "port", None)
    if isinstance(host, str) and isinstance(port, int):
        await wait_for_port_release(host, port)


def _is_port_conflict(sidecar: Any) -> bool:
    from convsim_core.runtime.sidecar import SidecarState

    return getattr(sidecar, "state", None) == SidecarState.PORT_CONFLICT


def _record_failure(
    conn: Optional[sqlite3.Connection],
    fingerprint: Optional[str],
    rung: str,
    detail: str,
    device: Optional[str],
) -> None:
    if conn is None or fingerprint is None:
        return
    try:
        save_gpu_failure(conn, GpuFailure(fingerprint=fingerprint, rung=rung, detail=detail[:500], device=device))
    except sqlite3.Error as exc:  # pragma: no cover — bookkeeping must not stop the fallback
        logger.warning("could not record the graphics-card failure: %s", exc)


async def record_crash_and_fall_back(app: Any) -> bool:
    """The Vulkan engine died during a conversation: remember it, start the processor.

    Returns True when the processor engine is now running, so the caller may
    retry the turn in flight. False when the engine that stopped was not the
    Vulkan build, had not crashed, or the processor build could not start.
    """
    from convsim_core.runtime.active import ensure_llama_sidecar_running
    from convsim_core.runtime.sidecar import SidecarState

    sidecar = getattr(app.state, "sidecar", None)
    if sidecar is None or getattr(sidecar, "variant", None) != "vulkan":
        return False
    await sidecar.wait_for_exit(timeout=3.0)
    if sidecar.state != SidecarState.CRASHED:
        return False
    model_path = sidecar.model_path
    port = sidecar.port
    detail = sidecar.get_status().get("error") or "the engine stopped during a conversation"
    conn = app.state.db.connection()
    builds = find_engine_builds()
    fingerprint = await asyncio.to_thread(gpu_fingerprint, builds.vulkan)
    _record_failure(conn, fingerprint, RUNG_CRASH, detail, selection_state(app).device)
    await _stop_and_release(sidecar)
    # The same port: the runtime adapter is still pointed at it.
    started = await ensure_llama_sidecar_running(app, model_path=model_path, port=port)
    return started is not None and getattr(sidecar, "variant", None) != "vulkan"


def engine_status(app: Any, conn: sqlite3.Connection) -> dict[str, Any]:
    """What ``GET /api/runtime/engine`` reports."""
    sidecar = getattr(app.state, "sidecar", None)
    builds = find_engine_builds()
    failure = load_gpu_failure(conn)
    state = selection_state(app)
    running = None
    if sidecar is not None:
        from convsim_core.runtime.sidecar import SidecarState

        if sidecar.state == SidecarState.RUNNING:
            running = getattr(sidecar, "variant", None)
    return {
        "setting": load_engine_variant_setting(conn),
        "running": running,
        "available": builds.available(),
        "device": state.device,
        "reason": state.reason,
        "devices": state.devices,
        "gpu_failure": failure.public() if failure else None,
        "notice_pending": bool(failure and not failure.notice_seen),
    }
