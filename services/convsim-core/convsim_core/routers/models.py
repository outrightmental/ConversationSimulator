# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel

from convsim_core.errors import ConvsimError
from convsim_core.runtime import build_runtime, list_runtime_ids
from convsim_core.runtime.ollama_adapter import OllamaChatRuntime
from convsim_core.runtime.types import (
    ChatFinal,
    ChatMessage,
    ChatRequest,
    RuntimeHealth,
    RuntimeStatus,
)
from convsim_core.services.model_download_service import execute_download
from convsim_core.services.model_manager_service import (
    create_install_record,
    get_active_config,
    get_install_record,
    get_installed_models,
    get_most_recent_benchmark,
    mark_install_failed,
    register_user_gguf,
    save_benchmark_result,
    set_active_config,
)
from convsim_core.services.model_registry_service import list_registry_models

router = APIRouter()

# Maps install_id → asyncio.Event; setting the event signals cancel to the download task.
_cancel_events: dict[int, asyncio.Event] = {}

# Strong references to in-flight download tasks. asyncio only keeps a weak
# reference to tasks created via create_task, so without this the download task
# can be garbage-collected mid-download and silently cancelled, leaving the
# install record stuck in 'downloading'. Tasks remove themselves when done.
_download_tasks: set[asyncio.Task[None]] = set()


def _spawn_download_task(coro: Any) -> "asyncio.Task[None]":
    """Schedule *coro* as a background task and hold a strong reference to it.

    Extracted so tests can suppress background execution deterministically
    instead of racing the fire-and-forget task against their assertions.
    """
    task = asyncio.create_task(coro)
    _download_tasks.add(task)
    task.add_done_callback(_download_tasks.discard)
    return task

_BENCHMARK_PROMPT = "Say hello in exactly three words."
_BENCHMARK_SYSTEM = "You are a helpful assistant. Be brief and literal."
_OLLAMA_DETECT_TIMEOUT = httpx.Timeout(3.0, connect=0.5)


# ── Request / response schemas ────────────────────────────────────────────────


class ModelRegistryEntry(BaseModel):
    id: str
    name: str
    provider: str
    family: Optional[str] = None
    role: Optional[str] = None
    format: Optional[str] = None
    license_spdx: Optional[str] = None
    license_url: Optional[str] = None
    source_type: Optional[str] = None
    download_url: Optional[str] = None
    sha256: Optional[str] = None
    size_gb: Optional[float] = None
    min_vram_gb: Optional[float] = None
    recommended_vram_gb: Optional[float] = None
    context_length: Optional[int] = None
    registered_at: str


class InstalledModelInfo(BaseModel):
    id: int
    registry_id: Optional[str] = None
    filename: str
    file_path: str
    size_bytes: Optional[int] = None
    install_status: str
    progress_bytes: Optional[int] = None
    error_message: Optional[str] = None
    verified_sha256: Optional[str] = None
    installed_at: str


class DetectedOllamaModel(BaseModel):
    id: str
    name: str
    size_category: Optional[str] = None


class ActiveModelConfig(BaseModel):
    runtime_id: Optional[str] = None
    model_id: Optional[str] = None


class UseModelRequest(BaseModel):
    runtime_id: str
    model_id: Optional[str] = None


class UseModelResponse(BaseModel):
    runtime_id: str
    model_id: Optional[str] = None
    runtime_name: str
    status: str
    message: Optional[str] = None


class InstallModelRequest(BaseModel):
    registry_id: str


class InstallModelResponse(BaseModel):
    install_id: int
    registry_id: str
    status: str
    message: Optional[str] = None


class RegisterGgufRequest(BaseModel):
    path: str
    display_name: Optional[str] = None
    family_guess: Optional[str] = None
    context_length: Optional[int] = None


class RegisterGgufResponse(BaseModel):
    profile_id: int
    file_path: str
    filename: str
    display_name: str
    family_guess: Optional[str] = None
    context_length_default: Optional[int] = None
    warnings: list[str]
    active_runtime_id: str
    active_model_id: str


class BenchmarkRequest(BaseModel):
    model_id: Optional[str] = None


class BenchmarkResponse(BaseModel):
    model_id: str
    runtime_id: str
    tokens_per_sec: float
    context_length: Optional[int] = None
    warnings: list[str]
    output_tokens: int
    benchmarked_at: str


# ModelsResponse embeds the most recent benchmark so the UI can display it
# without a separate round-trip.
class ModelsResponse(BaseModel):
    registry: list[ModelRegistryEntry]
    installed: list[InstalledModelInfo]
    ollama_models: list[DetectedOllamaModel]
    active: ActiveModelConfig
    runtime_health: RuntimeHealth
    total: int
    last_benchmark: Optional[BenchmarkResponse] = None


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _detect_ollama_models() -> list[DetectedOllamaModel]:
    """Try to list models from a local Ollama server. Returns [] if unreachable."""
    base_url = os.environ.get("CONVSIM_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    client = httpx.AsyncClient(base_url=base_url, timeout=_OLLAMA_DETECT_TIMEOUT)
    try:
        rt = OllamaChatRuntime(client=client)
        infos = await rt.list_models()
        return [
            DetectedOllamaModel(id=m.id, name=m.name, size_category=m.size_category)
            for m in infos
        ]
    except Exception:
        return []
    finally:
        await client.aclose()


def _get_registry_row(conn: Any, registry_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, name, license_spdx, sha256, source_type, download_url FROM model_registry WHERE id = ?",
        (registry_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _compute_warnings(
    *,
    original_output_tokens: int,
    elapsed_sec: float,
    tokens_per_sec: float,
    context_length: int | None,
) -> list[str]:
    """Return warning messages for a benchmark result based on threshold rules."""
    warnings: list[str] = []
    if original_output_tokens == 0:
        warnings.append("Output token count reported as 0; estimating from word count.")
    if elapsed_sec < 0.001:
        warnings.append(
            "Benchmark completed in under 1 ms; "
            "tokens/sec estimate may not reflect real-world performance."
        )
    else:
        if tokens_per_sec < 1.0:
            warnings.append(
                f"Very slow generation ({tokens_per_sec:.1f} tok/s). "
                "The model may be running on CPU only. "
                "Enable GPU acceleration or try a smaller model."
            )
        elif tokens_per_sec < 3.0:
            warnings.append(
                f"Slow generation ({tokens_per_sec:.1f} tok/s). "
                "Consider enabling GPU acceleration or using a smaller model."
            )
    if context_length is not None and context_length > 32768:
        warnings.append(
            f"Very large context window ({context_length:,} tokens). "
            "This may require substantial RAM; "
            "consider a lower context length if memory is limited."
        )
    return warnings


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/api/models", response_model=ModelsResponse)
async def list_models(request: Request) -> ModelsResponse:
    """Return registry models, installed models, detected Ollama models, and active runtime."""
    db = request.app.state.db
    runtime = request.app.state.runtime
    conn = db.connection()

    registry_rows: list[dict[str, Any]] = list_registry_models(conn)
    registry_entries = [ModelRegistryEntry(**row) for row in registry_rows]

    installed_rows = get_installed_models(conn)
    installed = [InstalledModelInfo(**row) for row in installed_rows]

    active_cfg = get_active_config(conn)
    ollama_models = await _detect_ollama_models()
    runtime_health = await runtime.health()

    bm_row = get_most_recent_benchmark(conn)
    last_benchmark: BenchmarkResponse | None = None
    if bm_row is not None:
        last_benchmark = BenchmarkResponse(
            model_id=bm_row["model_id"],
            runtime_id=bm_row["runtime_id"],
            tokens_per_sec=bm_row["tokens_per_sec"],
            context_length=bm_row.get("context_length"),
            warnings=bm_row.get("warnings", []),
            output_tokens=bm_row.get("output_tokens") or 0,
            benchmarked_at=bm_row["benchmarked_at"],
        )

    return ModelsResponse(
        registry=registry_entries,
        installed=installed,
        ollama_models=ollama_models,
        active=ActiveModelConfig(**active_cfg),
        runtime_health=runtime_health,
        total=len(registry_entries),
        last_benchmark=last_benchmark,
    )


@router.post("/api/models/use", response_model=UseModelResponse)
async def use_model(request: Request, body: UseModelRequest) -> UseModelResponse:
    """Select a runtime and optional model, validating availability first."""
    db = request.app.state.db

    known = list_runtime_ids()
    if body.runtime_id not in known:
        raise ConvsimError(
            code="UNKNOWN_RUNTIME",
            message=f"Unknown runtime '{body.runtime_id}'. Available: {known}",
            status_code=400,
        )

    test_runtime = None
    try:
        test_runtime = build_runtime(body.runtime_id)
        health = await test_runtime.health()
    except Exception as exc:
        raise ConvsimError(
            code="RUNTIME_UNAVAILABLE",
            message=f"Cannot reach runtime '{body.runtime_id}': {exc}",
            status_code=503,
        ) from exc
    finally:
        # OllamaChatRuntime holds a persistent httpx.AsyncClient; close it to
        # avoid connection-pool leaks when this temporary instance is used only
        # for the availability check.
        _client = getattr(test_runtime, "_client", None)
        if isinstance(_client, httpx.AsyncClient):
            await _client.aclose()

    if health.status in (RuntimeStatus.UNAVAILABLE, RuntimeStatus.ERROR):
        raise ConvsimError(
            code="RUNTIME_UNAVAILABLE",
            message=health.message or f"Runtime '{body.runtime_id}' is not available.",
            status_code=503,
        )

    set_active_config(db.connection(), runtime_id=body.runtime_id, model_id=body.model_id)

    return UseModelResponse(
        runtime_id=body.runtime_id,
        model_id=body.model_id,
        runtime_name=test_runtime.display_name,
        status=health.status.value,
        message=health.message,
    )


@router.post("/api/models/install", response_model=InstallModelResponse)
async def install_model(request: Request, body: InstallModelRequest) -> InstallModelResponse:
    """Start an explicit model download.

    Validates license and checksum metadata before creating the install record,
    then kicks off a background download task.  The install_id returned can be
    polled via GET /api/models/install/{install_id}.
    """
    conn = request.app.state.db.connection()
    models_dir = Path(getattr(request.app.state, "models_dir", ""))

    model = _get_registry_row(conn, body.registry_id)
    if model is None:
        raise ConvsimError(
            code="MODEL_NOT_FOUND",
            message=f"Model '{body.registry_id}' not found in the local registry.",
            status_code=404,
        )

    if model["source_type"] == "user-supplied":
        raise ConvsimError(
            code="INSTALL_NOT_APPLICABLE",
            message=(
                "User-supplied models cannot be installed via this endpoint. "
                "Provide the file path directly via POST /api/models/use."
            ),
            status_code=400,
        )

    if not model.get("license_spdx"):
        raise ConvsimError(
            code="MISSING_LICENSE",
            message=(
                f"Registry entry '{body.registry_id}' has no license metadata. "
                "Cannot install a model without a declared license."
            ),
            status_code=400,
        )

    sha256 = model.get("sha256") or ""
    if not sha256 or sha256.upper() == "PENDING":
        raise ConvsimError(
            code="MISSING_CHECKSUM",
            message=(
                f"Registry entry '{body.registry_id}' has no verified SHA-256 checksum. "
                "Cannot install until a confirmed checksum is available."
            ),
            status_code=400,
        )

    download_url = (model.get("download_url") or "").strip()
    if not download_url:
        raise ConvsimError(
            code="MISSING_DOWNLOAD_URL",
            message=(
                f"Registry entry '{body.registry_id}' has no download URL. "
                "Cannot start a download without a source URL."
            ),
            status_code=400,
        )

    filename = f"{body.registry_id}.gguf"
    install_id = create_install_record(
        conn, registry_id=body.registry_id, filename=filename, file_path=""
    )

    # Register a cancel event before launching the task so DELETE can signal it.
    cancel_event = asyncio.Event()
    _cancel_events[install_id] = cancel_event

    async def _run_download() -> None:
        try:
            await execute_download(
                conn,
                install_id,
                download_url,
                sha256,
                models_dir,
                filename,
                cancel_event=cancel_event,
            )
        finally:
            _cancel_events.pop(install_id, None)

    _spawn_download_task(_run_download())

    return InstallModelResponse(
        install_id=install_id,
        registry_id=body.registry_id,
        status="pending",
        message=f"Downloading '{model['name']}'. Poll GET /api/models/install/{install_id} for progress.",
    )


@router.get("/api/models/install/{install_id}", response_model=InstalledModelInfo)
async def get_install_status(request: Request, install_id: int) -> InstalledModelInfo:
    """Return the current status and progress of an install record."""
    conn = request.app.state.db.connection()
    record = get_install_record(conn, install_id)
    if record is None:
        raise ConvsimError(
            code="INSTALL_NOT_FOUND",
            message=f"Install record {install_id} not found.",
            status_code=404,
        )
    return InstalledModelInfo(**record)


@router.delete("/api/models/install/{install_id}", status_code=204)
async def cancel_install(request: Request, install_id: int) -> None:
    """Cancel an in-progress download, or return 409 if already in a terminal state."""
    conn = request.app.state.db.connection()
    record = get_install_record(conn, install_id)
    if record is None:
        raise ConvsimError(
            code="INSTALL_NOT_FOUND",
            message=f"Install record {install_id} not found.",
            status_code=404,
        )

    _TERMINAL = {"ready", "complete", "failed", "cancelled", "checksum_mismatch"}
    if record["install_status"] in _TERMINAL:
        raise ConvsimError(
            code="INSTALL_NOT_CANCELLABLE",
            message=f"Install {install_id} is already in terminal state '{record['install_status']}'.",
            status_code=409,
        )

    # Signal the background download task if one is running.
    event = _cancel_events.get(install_id)
    if event is not None:
        event.set()
    else:
        # No active download task; mark as cancelled directly.
        mark_install_failed(conn, install_id, "Cancelled by user.", status="cancelled")


@router.post("/api/models/register-gguf", response_model=RegisterGgufResponse)
async def register_gguf(request: Request, body: RegisterGgufRequest) -> RegisterGgufResponse:
    """Register a user-supplied GGUF file as the active model.

    Validates file existence and extension. The file is not copied or modified —
    only the path is stored. The user is responsible for the model's license
    and hardware requirements; the app makes no claims about redistribution.
    """
    path = body.path.strip()

    if not path:
        raise ConvsimError(
            code="GGUF_PATH_EMPTY",
            message="File path must not be empty.",
            status_code=400,
        )

    if not path.lower().endswith(".gguf"):
        raise ConvsimError(
            code="GGUF_INVALID_EXTENSION",
            message="The file must have a .gguf extension.",
            status_code=400,
        )

    if not os.path.isfile(path):
        raise ConvsimError(
            code="GGUF_FILE_NOT_FOUND",
            message=(
                f"GGUF file not found: {path}. "
                "Verify the path is correct and the file is accessible, then try again."
            ),
            status_code=404,
        )

    db = request.app.state.db
    conn = db.connection()

    profile = register_user_gguf(
        conn,
        path=path,
        display_name=body.display_name,
        family_guess=body.family_guess,
        context_length_default=body.context_length,
    )

    set_active_config(conn, runtime_id="llama_cpp", model_id=path)

    return RegisterGgufResponse(
        profile_id=profile["id"],
        file_path=path,
        display_name=profile["display_name"],
        filename=profile["filename"],
        family_guess=body.family_guess,
        context_length_default=body.context_length,
        warnings=[],
        active_runtime_id="llama_cpp",
        active_model_id=path,
    )


@router.post("/api/models/benchmark", response_model=BenchmarkResponse)
async def benchmark_model(request: Request, body: BenchmarkRequest) -> BenchmarkResponse:
    """Run a short local benchmark and persist tokens/sec, context length, and warnings."""
    db = request.app.state.db
    runtime = request.app.state.runtime

    active_cfg = get_active_config(db.connection())
    model_id = body.model_id or active_cfg.get("model_id")

    health = await runtime.health()
    if health.status in (RuntimeStatus.UNAVAILABLE, RuntimeStatus.ERROR):
        raise ConvsimError(
            code="RUNTIME_UNAVAILABLE",
            message=health.message or "Runtime is not available for benchmarking.",
            status_code=503,
        )

    chat_req = ChatRequest(
        messages=[
            ChatMessage(role="system", content=_BENCHMARK_SYSTEM),
            ChatMessage(role="user", content=_BENCHMARK_PROMPT),
        ],
        model_id=model_id,
        max_tokens=50,
        temperature=0.0,
    )

    final: ChatFinal | None = None
    t0 = time.perf_counter()

    try:
        async for chunk in runtime.chat_stream(chat_req):
            if isinstance(chunk, ChatFinal):
                final = chunk
    except Exception as exc:
        raise ConvsimError(
            code="BENCHMARK_FAILED",
            message=f"Benchmark failed during inference: {exc}",
            status_code=503,
        ) from exc

    elapsed_sec = time.perf_counter() - t0

    if final is None:
        raise ConvsimError(
            code="BENCHMARK_FAILED",
            message="Benchmark produced no output from the runtime.",
            status_code=500,
        )

    original_output_tokens = final.output_tokens
    output_tokens = original_output_tokens if original_output_tokens > 0 else max(1, len(final.text.split()))

    tokens_per_sec = round(output_tokens / elapsed_sec, 2) if elapsed_sec > 0 else 0.0

    context_length: int | None = None
    try:
        models = await runtime.list_models()
        matched = next((m for m in models if m.id == final.model_id), None)
        if matched:
            context_length = matched.context_length
    except Exception:
        pass

    warnings = _compute_warnings(
        original_output_tokens=original_output_tokens,
        elapsed_sec=elapsed_sec,
        tokens_per_sec=tokens_per_sec,
        context_length=context_length,
    )

    benchmarked_at = datetime.now(timezone.utc).isoformat()

    save_benchmark_result(
        db.connection(),
        model_id=final.model_id,
        runtime_id=runtime.id,
        tokens_per_sec=tokens_per_sec,
        context_length=context_length,
        warnings=warnings,
        prompt_used=_BENCHMARK_PROMPT,
        output_tokens=output_tokens,
        benchmarked_at=benchmarked_at,
    )

    return BenchmarkResponse(
        model_id=final.model_id,
        runtime_id=runtime.id,
        tokens_per_sec=tokens_per_sec,
        context_length=context_length,
        warnings=warnings,
        output_tokens=output_tokens,
        benchmarked_at=benchmarked_at,
    )
