<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Runtime adapters

This document explains how the `ChatRuntime` abstraction works, describes each
built-in adapter, and walks through adding a new runtime.

For the system overview see [architecture.md](architecture.md).

---

## The `ChatRuntime` interface

All LLM integrations implement `ChatRuntime`, defined in
`services/convsim-core/convsim_core/runtime/base.py`.

```python
class ChatRuntime(ABC):
    @property
    @abstractmethod
    def id(self) -> str: ...            # stable machine id, e.g. "llama_cpp"

    @property
    @abstractmethod
    def display_name(self) -> str: ...  # human label shown in UI

    @property
    @abstractmethod
    def capabilities(self) -> RuntimeCapabilities: ...

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]: ...

    @abstractmethod
    def chat_stream(self, request: ChatRequest) \
        -> AsyncIterator[ChatToken | ChatFinal]: ...

    @abstractmethod
    async def health(self) -> RuntimeHealth: ...
```

### Types

**`RuntimeCapabilities`** — feature flags the engine uses to decide how to
call the runtime:

```python
class RuntimeCapabilities(BaseModel):
    streaming: bool   # yields ChatToken chunks before ChatFinal
    json_schema: bool # can enforce a JSON Schema on the response
    grammar: bool     # supports GBNF/BNF grammar constraints (future)
    tool_calling: bool
    embeddings: bool
```

**`ChatRequest`** — what the engine sends:

```python
class ChatRequest(BaseModel):
    messages: list[ChatMessage]       # role: "system" | "user" | "assistant"
    model_id: str | None              # None → runtime picks the loaded model
    max_tokens: int = 512
    temperature: float = 0.8
    json_schema: dict | None          # if set and json_schema=True, enforce it
```

**Streaming contract.** `chat_stream` must yield zero or more `ChatToken`
objects followed by exactly one `ChatFinal`. `ChatFinal.text` is the
authoritative complete response; callers may build a preview from tokens
but must not append to `ChatFinal.text`.

```python
class ChatToken(BaseModel):
    type: Literal["token"] = "token"
    text: str

class ChatFinal(BaseModel):
    type: Literal["final"] = "final"
    text: str
    model_id: str
    input_tokens: int
    output_tokens: int
    structured: dict | None    # parsed JSON when json_schema was set
```

**`RuntimeHealth`** — returned by `health()`:

```python
class RuntimeHealth(BaseModel):
    runtime_id: str
    runtime_name: str
    status: RuntimeStatus    # UNAVAILABLE | STARTING | READY | DEGRADED | ERROR
    model_id: str | None
    latency_ms: float | None
    message: str | None
    checked_at: str          # ISO 8601
```

---

## Runtime registry

Adapters self-register using the `@register(runtime_id)` decorator from
`convsim_core/runtime/registry.py`. The application instantiates the
selected runtime at startup via `build_runtime(runtime_id)`.

```python
from convsim_core.runtime.registry import register

@register("my_runtime")
class MyRuntime(ChatRuntime):
    ...
```

The active runtime id is chosen by the `CONVSIM_RUNTIME_ID` environment
variable (default: `"fake"`, so the app runs with no model installed).
Set `CONVSIM_RUNTIME_ID=llama_cpp` (or `ollama`) to use a real local model.
Valid values are the ids of all registered runtimes.

---

## Built-in adapters

### llama.cpp (primary)

**Module:** `convsim_core/runtime/llama_cpp.py`  
**Runtime id:** `llama_cpp`  
**Display name:** `llama.cpp (local)`

Connects to a running `llama-server` instance using its OpenAI-compatible
HTTP API. `llama-server` is the inference binary from the llama.cpp project.

**Capabilities:**

| Capability   | Supported |
|--------------|-----------|
| streaming    | Yes       |
| json_schema  | Yes (via `response_format.json_schema`) |
| grammar      | No        |
| tool_calling | No        |
| embeddings   | No        |

**Configuration** (environment variables, all prefixed `CONVSIM_LLAMA_CPP_`):

| Variable                          | Default                     | Description                        |
|-----------------------------------|-----------------------------|------------------------------------|
| `CONVSIM_LLAMA_CPP_BASE_URL`      | `http://127.0.0.1:7356`     | llama-server base URL              |
| `CONVSIM_LLAMA_CPP_MODEL_ID`      | `None` (server default)     | Model id to pass in requests       |
| `CONVSIM_LLAMA_CPP_CONTEXT_LENGTH`| `None`                      | Context length hint for `list_models` |
| `CONVSIM_LLAMA_CPP_TEMPERATURE`   | `0.8`                       | Default temperature                |
| `CONVSIM_LLAMA_CPP_TOP_P`         | `0.95`                      | top-p sampling                     |
| `CONVSIM_LLAMA_CPP_REPEAT_PENALTY`| `1.1`                       | Repetition penalty                 |
| `CONVSIM_LLAMA_CPP_THREADS`       | `None`                      | CPU thread count                   |
| `CONVSIM_LLAMA_CPP_GPU_LAYERS`    | `None`                      | Layers to offload to GPU           |
| `CONVSIM_LLAMA_CPP_TIMEOUT`       | `30.0`                      | HTTP request timeout (seconds)     |
| `CONVSIM_LLAMA_CPP_JSON_SCHEMA_ENABLED` | `True`              | Enable structured output           |

**Health check.** Calls `GET /health` on the llama-server. HTTP 200 → READY;
HTTP 503 → STARTING (model still loading); connection error → UNAVAILABLE.

**Starting llama-server manually:**

```sh
llama-server --port 7356 --model /path/to/model.gguf
```

**JSON schema enforcement.** When `json_schema` is set on the request,
the adapter wraps it in the `response_format.json_schema` OpenAI field.
`strict` is set to `False` to avoid rejecting slightly out-of-spec responses.
The adapter attempts `json.loads(full_text)` and sets `ChatFinal.structured`
on success; parse failure leaves `structured=None` (the pipeline uses its
own fallback logic).

---

### Ollama

**Module:** `convsim_core/runtime/ollama_adapter.py`  
**Runtime id:** `ollama`  
**Display name:** `Ollama (local)`

Connects to a local Ollama server using its native REST API (`/api/chat`
and `/api/tags`). Does **not** depend on the `ollama` PyPI package, keeping
`convsim_core` importable without Ollama installed.

**Capabilities:**

| Capability   | Supported |
|--------------|-----------|
| streaming    | Yes       |
| json_schema  | Yes (via `format` field) |
| grammar      | No        |
| tool_calling | No        |
| embeddings   | No        |

**Configuration:**

| Variable                    | Default                        | Description            |
|-----------------------------|--------------------------------|------------------------|
| `CONVSIM_OLLAMA_BASE_URL`   | `http://127.0.0.1:11434`       | Ollama server base URL |

The Ollama port (11434) is Ollama's default and is separate from the
Conversation Simulator port range.

**Model selection.** If `ChatRequest.model_id` is `None`, the adapter
calls `list_models()` and picks the first available model. If Ollama is
reachable but has no models, it raises `RuntimeError` with instructions
to run `ollama pull <model>`. If Ollama is unreachable, it raises with
instructions to run `ollama serve`.

**Health check.** Calls `GET /` on the Ollama server. READY if reachable
and at least one model is installed; DEGRADED if reachable but no models;
UNAVAILABLE on connection failure.

**Starting Ollama:**

```sh
ollama serve         # start the server
ollama pull llama3.2 # pull a compatible model
```

---

### Fake (deterministic)

**Module:** `convsim_core/runtime/fake.py`  
**Runtime id:** `fake`  
**Display name:** `Fake (deterministic)`

A test double that never calls a real model. Used in automated tests and
for running the UI without any LLM installed.

**Behavior:**

- Always returns the same fixed response so test assertions are stable.
- When `json_schema` is absent: returns a plain text sentence.
- When `json_schema` is present and contains `replay_suggestions` in
  its `properties`: returns a canned debrief narrative JSON.
- Otherwise: returns a canned NPC turn JSON with `npc_utterance`,
  `npc_emotion`, `state_delta`, `event_flags`, `rubric_observations`,
  `safety`, and `session_control`.
- Streams tokens word-by-word with `asyncio.sleep(0)` between each
  (yields control, no actual delay).
- Health always returns READY with `latency_ms=0.0`.

**Models exposed:** `fake-small` (4 096 context) and `fake-large` (32 768 context).

Enable it by setting `CONVSIM_RUNTIME_ID=fake`.

---

## Adding a new runtime adapter

Follow these steps to add a runtime that is not yet supported.

### 1. Create the module

Add a new file under `services/convsim-core/convsim_core/runtime/`.
Name it after the runtime id, e.g. `my_provider.py`.

```python
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator

from convsim_core.runtime.base import ChatRuntime
from convsim_core.runtime.registry import register
from convsim_core.runtime.types import (
    ChatFinal, ChatRequest, ChatToken,
    ModelInfo, RuntimeCapabilities, RuntimeHealth, RuntimeStatus,
)


@register("my_provider")
class MyProviderRuntime(ChatRuntime):
    """One-line description of this runtime."""

    @property
    def id(self) -> str:
        return "my_provider"

    @property
    def display_name(self) -> str:
        return "My Provider (local)"

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            streaming=True,
            json_schema=True,   # set to False if the backend cannot enforce schemas
        )

    async def list_models(self) -> list[ModelInfo]:
        # Return the models available through this runtime.
        # Return [] on connection error so callers can detect gracefully.
        return []

    def chat_stream(self, request: ChatRequest) -> AsyncGenerator[ChatToken | ChatFinal, None]:
        return self._stream(request)

    async def _stream(
        self, request: ChatRequest
    ) -> AsyncGenerator[ChatToken | ChatFinal, None]:
        # Yield ChatToken chunks while the response streams.
        # Yield exactly one ChatFinal at the end.
        yield ChatToken(text="Hello ")
        yield ChatToken(text="world.")
        yield ChatFinal(
            text="Hello world.",
            model_id=request.model_id or "my-model",
            input_tokens=10,
            output_tokens=2,
            structured=None,
        )

    async def health(self) -> RuntimeHealth:
        checked_at = datetime.now(timezone.utc).isoformat()
        # Probe the backend and return the appropriate status.
        return RuntimeHealth(
            runtime_id=self.id,
            runtime_name=self.display_name,
            status=RuntimeStatus.READY,
            checked_at=checked_at,
        )
```

### 2. Import the module at startup

The `@register` decorator only fires when the module is imported.
Add an import to `convsim_core/runtime/__init__.py`:

```python
from convsim_core.runtime import my_provider  # noqa: F401
```

Or import it in `app.py` before `build_runtime` is called — whichever
pattern the other adapters follow in that file.

### 3. Wire configuration

If the runtime needs configuration (base URL, API key, etc.), use a
Pydantic `BaseSettings` subclass with an appropriate env-var prefix,
following the same pattern as `LlamaCppConfig` in `llama_cpp.py`.

### 4. Add tests

Add a test file at
`services/convsim-core/tests/test_<runtime_id>_runtime.py`.

At minimum, test:

- `list_models()` returns `ModelInfo` objects.
- `chat_stream()` yields at least one `ChatToken` and exactly one `ChatFinal`.
- `health()` returns `RuntimeStatus.READY` when the backend is reachable.
- `health()` returns `RuntimeStatus.UNAVAILABLE` when the backend is down
  (mock the HTTP client with `respx` or `pytest-httpx`).

See `tests/test_llama_cpp_runtime.py` and `tests/test_ollama_runtime.py`
for examples.

### 5. Select at runtime

Set the environment variable before starting convsim-core:

```sh
CONVSIM_RUNTIME_ID=my_provider uvicorn convsim_core.app:app --port 7355
```

Or add it to the `.env` file in the service root.

---

## Runtime selection and fallback logic

The active runtime is chosen once at application startup:

```
CONVSIM_RUNTIME_ID (env) → build_runtime(id) → ChatRuntime instance
```

There is no automatic fallback to another runtime if the selected one is
unhealthy. Health status is reported to the UI via `GET /api/health` so the
user can take corrective action (e.g. start `llama-server`).

The `GET /api/models` endpoint proxies `runtime.list_models()` and
`GET /api/health` proxies `runtime.health()`. Both are polled periodically
by the UI home screen.

---

## Structured output and JSON schema enforcement

The turn pipeline always passes `NPC_TURN_OUTPUT_SCHEMA` (from
`convsim_prompt`) as `ChatRequest.json_schema`. This schema defines the
expected NPC response format including `npc_utterance`, `npc_emotion`,
`state_delta`, `event_flags`, `rubric_observations`, `safety`, and
`session_control`.

When `RuntimeCapabilities.json_schema` is `True`, the adapter encodes the
schema in a backend-specific way:

- **llama.cpp:** `response_format.json_schema` field in the
  `/v1/chat/completions` request body.
- **Ollama:** `format` field in the `/api/chat` request body.
- **Fake:** returns a hard-coded valid JSON string regardless of schema.

When `json_schema` is `False` (a future plain-text runtime, for example),
the pipeline relies entirely on `convsim_prompt.parse_turn_output` to
extract structured fields from free text, with the safe fallback utterance
as the error case.

---

## Future adapters

These are noted as non-MVP candidates:

| Runtime id (proposed)    | Backend                              |
|--------------------------|--------------------------------------|
| `openai_compatible`      | Any OpenAI-API-compatible server     |
| `mlx`                    | Apple MLX inference (Apple Silicon)  |
| `tgi`                    | HuggingFace Text Generation Inference|
| `vllm`                   | vLLM (for multi-GPU dev machines)    |

Because all engine code is decoupled from adapter code via the
`ChatRuntime` interface, adding any of these requires only steps 1–5
above without changing the scenario engine, turn pipeline, or
debrief engine.
