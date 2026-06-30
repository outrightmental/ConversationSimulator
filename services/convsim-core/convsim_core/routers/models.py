# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
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
from convsim_core.services.model_manager_service import (
    create_install_record,
    get_active_config,
    get_installed_models,
    save_benchmark_result,
    set_active_config,
)
from convsim_core.services.model_registry_service import list_registry_models

router = APIRouter()

_BENCHMARK_PROMPT = "Say hello in exactly three words."
_BENCHMARK_SYSTEM = "You are a helpful assistant. Be brief and literal."
_OLLAMA_DETECT_TIMEOUT = 3.0


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
    installed_at: str


class DetectedOllamaModel(BaseModel):
    id: str
    name: str
    size_category: Optional[str] = None


class ActiveModelConfig(BaseModel):
    runtime_id: Optional[str] = None
    model_id: Optional[str] = None


class ModelsResponse(BaseModel):
    registry: list[ModelRegistryEntry]
    installed: list[InstalledModelInfo]
    ollama_models: list[DetectedOllamaModel]
    active: ActiveModelConfig
    runtime_health: RuntimeHealth
    total: int


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
        "SELECT id, name, license_spdx, sha256, source_type FROM model_registry WHERE id = ?",
        (registry_id,),
    ).fetchone()
    return dict(row) if row is not None else None


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

    return ModelsResponse(
        registry=registry_entries,
        installed=installed,
        ollama_models=ollama_models,
        active=ActiveModelConfig(**active_cfg),
        runtime_health=runtime_health,
        total=len(registry_entries),
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

    try:
        test_runtime = build_runtime(body.runtime_id)
        health = await test_runtime.health()
    except Exception as exc:
        raise ConvsimError(
            code="RUNTIME_UNAVAILABLE",
            message=f"Cannot reach runtime '{body.runtime_id}': {exc}",
            status_code=503,
        ) from exc

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
    """Queue an explicit model download.

    Rejects registry entries that lack license or verified checksum metadata,
    ensuring the API never downloads unverified weights.
    """
    conn = request.app.state.db.connection()

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
    if not sha256 or sha256 == "PENDING":
        raise ConvsimError(
            code="MISSING_CHECKSUM",
            message=(
                f"Registry entry '{body.registry_id}' has no verified SHA-256 checksum. "
                "Cannot install until a confirmed checksum is available."
            ),
            status_code=400,
        )

    filename = f"{body.registry_id}.gguf"
    install_id = create_install_record(
        conn, registry_id=body.registry_id, filename=filename, file_path=""
    )

    return InstallModelResponse(
        install_id=install_id,
        registry_id=body.registry_id,
        status="pending",
        message=f"Install queued for '{model['name']}'. Download will proceed in the background.",
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

    warnings: list[str] = []
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

    output_tokens = final.output_tokens
    if output_tokens == 0:
        warnings.append("Output token count reported as 0; estimating from word count.")
        output_tokens = max(1, len(final.text.split()))

    if elapsed_sec < 0.001:
        warnings.append(
            "Benchmark completed in under 1 ms; tokens/sec estimate may not reflect real-world performance."
        )

    tokens_per_sec = round(output_tokens / elapsed_sec, 2) if elapsed_sec > 0 else 0.0

    context_length: int | None = None
    try:
        models = await runtime.list_models()
        matched = next((m for m in models if m.id == final.model_id), None)
        if matched:
            context_length = matched.context_length
    except Exception:
        pass

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
