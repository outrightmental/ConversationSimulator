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

**Streaming contract.** `chat_stream` must yield zero or more `ChatProgress`
and `ChatToken` objects, in the order the engine produced them, followed by
exactly one `ChatFinal`. `ChatFinal.text` is the authoritative complete
response; callers may build a preview from tokens but must not append to
`ChatFinal.text`. Progress chunks are optional: an adapter emits one only when
the engine sent a real signal, and callers that only want text ignore them.

```python
class ChatToken(BaseModel):
    type: Literal["token"] = "token"
    text: str

class ChatProgress(BaseModel):
    type: Literal["progress"] = "progress"
    stage: Literal["waiting", "reading", "writing"]
    processed: int | None      # prompt tokens read so far
    total: int | None          # prompt tokens in all
    cached: int | None         # of which reused from the engine's cache

class ChatTimings(BaseModel):          # what the engine itself reported
    prompt_tokens: int | None          # evaluated + cached
    cached_tokens: int | None
    evaluated_tokens: int | None
    output_tokens: int | None
    prompt_ms: float | None            # engine wall time reading
    generation_ms: float | None        # engine wall time writing
    load_ms: float | None              # model load attributed to the request (Ollama)
    reading_tps: float | None
    writing_tps: float | None

class ChatFinal(BaseModel):
    type: Literal["final"] = "final"
    text: str
    model_id: str
    input_tokens: int
    output_tokens: int
    structured: dict | None    # parsed JSON when json_schema was set
    timings: ChatTimings | None             # None when the engine said nothing
    finish_reason: Literal["stop", "length", "cancelled"] | None
```

**What a turn cost.** The turn pipeline times each stage of a turn with a
monotonic clock — `waiting`, `reading`, `writing`, `finishing`, `checking`,
`voice`, defined once in `convsim_core/services/turn_timing.py` — and
combines it with the engine's `ChatTimings` into one `TurnTiming` record per
NPC turn (mirrored as `TurnTiming` in `packages/shared`). The record is
persisted as a `turn_timing` event, returned on the turn's `npc_turn` event
and by the debug and transcript endpoints, and summarised by
`GET /api/performance/rolling`. A field an engine cannot supply is `null`;
nothing is estimated silently. Adapters must therefore never invent a count or
a duration — report what the engine said, or `None`.

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
| `CONVSIM_LLAMA_CPP_TEMPERATURE`   | `0.8`                       | Not used: every request carries its own temperature (see **Sampling** below) |
| `CONVSIM_LLAMA_CPP_TOP_P`         | `0.95`                      | top-p sampling, for a model whose registry entry declares no `top_p_default` |
| `CONVSIM_LLAMA_CPP_REPEAT_PENALTY`| `1.1`                       | Repetition penalty                 |
| `CONVSIM_LLAMA_CPP_THREADS`       | `None`                      | CPU thread count                   |
| `CONVSIM_LLAMA_CPP_GPU_LAYERS`    | `None`                      | Layers to offload to GPU           |
| `CONVSIM_LLAMA_CPP_TIMEOUT`       | `30.0`                      | Timeout for model listing (seconds) |
| `CONVSIM_LLAMA_CPP_CHAT_TIMEOUT`  | `180.0`                     | How long generation may go quiet (seconds); covers CPU-only prompt eval |
| `CONVSIM_LLAMA_CPP_JSON_SCHEMA_ENABLED` | `True`              | Enable structured output           |

**Sampling.** A conversation's requests (each NPC turn, its repair and
retry calls, and the debrief) carry the temperature and top-p that the
model's registry entry declares as `runtime.llama_cpp.temperature_default`
and `top_p_default` (issue #580). The model is found the way the app finds
the one to start the engine on: the saved selection when it is a model file
on disk, otherwise the newest ready install, mapped to its registry entry by
the same install-record lookup that sets the engine's context size. It does
not matter whether the model was selected in setup or Settings or the core
was started with `CONVSIM_RUNTIME_ID=llama_cpp` and nothing saved. A file
selected while the engine is running is the one whose values are sent from
then on, although the engine keeps the earlier file until the app is
reopened. The demo edition starts its engine only on the demo model's own
install, so its requests carry that model's values whatever the full app,
which shares its data directory, has selected.

Where there is no registry value to use, a request is sent at temperature
0.8, the request default, and the top-p above. That covers a GGUF the player
registered and a value the entry does not declare. It also covers a
llama-server the app did not start, on a data directory with no install
record of its file, such as the one `scripts/nightly-model-smoke.py` runs:
the app does not ask a running server which file it loaded, and without an
install record it could not map the file to an entry. A server you start
yourself while the app does hold a ready install is sent the values of the
file the app would have started, whichever file the server loaded. The model
benchmark keeps its fixed temperature of 0.

**Health check.** Calls `GET /health` on the llama-server. HTTP 200 → READY;
HTTP 503 → STARTING (model still loading); connection error → UNAVAILABLE.

**Starting llama-server manually:**

```sh
llama-server --port 7356 --model /path/to/model.gguf
```

**Managed engine launch settings.** When the app launches `llama-server`
itself — `LlamaCppSidecar.start()` in `convsim_core/runtime/sidecar.py`,
reached from the autostart in `runtime/active.py`, the install pipeline's
warmup stage, and `POST /api/sidecar/start` — it does not accept the engine's
defaults. Those defaults suit a shared inference server, not one player having
one conversation on an 8 GB machine. The log in issue #489 showed what they
cost: four slots, the model's full trained context (40,960 tokens where the
registry says 8,192), 6,759 MiB of projected memory for a 2.5 GB model, an
8 GiB prompt cache in host memory, and a single progress update for a
22-second prompt because the default batch is 2,048 tokens.

One helper, `convsim_core/runtime/launch.py`, builds the launch configuration
— `LaunchConfig`, `resolve_launch_config(model_path, conn)` and
`launch_env(config)` — and all three start sites use it, so they cannot drift
apart (issue #523). Issue #529 turns it into a player-configurable launch
profile.

| Setting | Value | Passed as | Why |
|---------|-------|-----------|-----|
| Context size | the loaded model's `context_length` from the model registry; a player-supplied GGUF uses the context stated when it was registered, or 8192 | `--ctx-size` on the command line | The KV cache is sized from it. The model file's trained length is far more than one conversation needs, and loading it is what blew the memory budget in #489. |
| Slots | 1 | `LLAMA_ARG_N_PARALLEL=1` | One player has one conversation. Every extra slot divides the context between slots and multiplies KV-cache memory. No `id_slot` is sent in any request. |
| Batch size | 256 tokens | `LLAMA_ARG_BATCH=256` | Prompt processing reports progress and checks for cancellation once per batch. At the CPU rate seen in #489 (87 tokens/s) that is about every 3 s, instead of once for the whole prompt. |
| Host prompt cache | 1024 MiB | `LLAMA_ARG_CACHE_RAM=1024` | Bounds the prompt cache the server keeps in host memory; the default on the #489 machine was 8 GiB. |
| Reasoning | off | `LLAMA_ARG_REASONING=off` | NPC turns need in-character JSON, not visible chain-of-thought, which blows the turn token budget and multiplies latency. |

Why two mechanisms: `--ctx-size` goes on the command line because every
`llama-server` build has the flag, and an engine too old to read `LLAMA_ARG_*`
would otherwise load the model's full trained context — the memory problem
itself. The rest travel as `LLAMA_ARG_*` environment variables, which
`llama-server` reads as if the flag had been given (its `common/arg.cpp` binds
`--parallel` to `LLAMA_ARG_N_PARALLEL`, `--batch-size` to `LLAMA_ARG_BATCH`,
`--cache-ram` to `LLAMA_ARG_CACHE_RAM`). An engine build that lacks one of
them starts anyway: an unknown flag is fatal, an unknown variable is ignored.

Every variable is applied with `setdefault`, so a value already in the app's
environment is an operator override that wins — start the app with
`LLAMA_ARG_N_PARALLEL=2` and the engine runs two slots. `LLAMA_ARG_CTX_SIZE`
is honoured the same way: when it is set and nothing states a context size
for this start, `--ctx-size` is left off the command line so the flag cannot
silently beat the variable. An explicit `context_length` in the
`POST /api/sidecar/start` body is such a statement: it goes on the command
line as `--ctx-size` and wins over both the registry value and the variable.

None of this changes sampling: the adapter sends the same request body as
before. It applies only to an engine the app launches; a `llama-server` the
player runs by hand is configured by the player. Each launch writes the command
line and the effective `LLAMA_ARG_*` variables under the
`--- llama-server start` marker in `runtime.log`, so a log excerpt shows how
the engine was launched.

*What to measure.* These settings exist for memory and responsiveness, so a
change to them is recorded as a before/after on one machine with the same
model:

- resident memory of the `llama-server` process once `/health` returns 200
  (Task Manager, or `ps -o rss -p <pid>`);
- the projected memory the engine logs while loading (the KV-cache and
  compute-buffer size lines after the `--- llama-server start` marker in
  `runtime.log`);
- `GET /props` on the engine: `total_slots` and
  `default_generation_settings.n_ctx` should read 1 and the registry's
  context length;
- for one long prompt, how many progress updates the UI shows and how long a
  cancel takes to act (one batch — about 3 s on the #489 machine).

**JSON schema enforcement.** When `json_schema` is set on the request,
the adapter wraps it in the `response_format.json_schema` OpenAI field.
`strict` is set to `False` to avoid rejecting slightly out-of-spec responses.
The adapter attempts `json.loads(full_text)` and sets `ChatFinal.structured`
on success; parse failure leaves `structured=None` (the pipeline uses its
own fallback logic).

**Timings and progress.** Every request also carries
`stream_options: {"include_usage": true}`, `return_progress: true` and
`timings_per_token: true`. llama-server then streams `prompt_progress`
chunks while it reads the prompt (surfaced as `ChatProgress`, stage
`reading`), attaches its `timings` block (tokens read, tokens reused from
cache, both speeds) and ends with a `usage` chunk whose `choices` is empty —
the adapter reads `usage` and `timings` before skipping chunks without
choices. None of these fields change what the model generates. A server that
rejects the request because of those fields (HTTP 422, or a 400 whose error
names one of them) gets the same request once more without them; the turn
completes and the timing fields stay `null` for the life of that adapter
instance. Any other 400, such as a prompt over the context size or a chat
template that cannot format the messages, is reported as the request error it
is, and the fields stay on. Raw streams the
adapter is tested against live under `services/convsim-core/tests/fixtures/`;
a file named `synthetic_*` was written from the documented wire format rather
than captured, and its README says how to replace it with a capture.

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

**Timings.** The final `done` chunk is the only place Ollama reports what a
request cost. The adapter keeps `prompt_eval_count`, `prompt_eval_cached_count`
(present from Ollama v0.34.0), `prompt_eval_duration`, `eval_count`,
`eval_duration` and `load_duration` — durations are nanoseconds and are
converted to milliseconds — and `done_reason` becomes `finish_reason`. Without
the cached count, the cached and evaluated token counts and the reading speed
stay `None`: a prompt mostly served from cache would otherwise read as
impossibly fast. Ollama sends no progress while reading, so the adapter emits
no `ChatProgress`.

**Model selection.** If `ChatRequest.model_id` is `None`, the adapter
calls `list_models()` and picks the first available model. If Ollama is
reachable but has no models, it raises `RuntimeError` with instructions
to run `ollama pull <model>`. If Ollama is unreachable, it raises
`ConnectionError` with instructions to run `ollama serve` — the same type the
llama.cpp adapter uses, so the turn endpoint reports it as a 503
`RUNTIME_UNAVAILABLE` rather than a generic 500.

**Timeouts.** Control-plane calls (tag listing, reachability probe) get 60 s.
`/api/chat` gets 180 s applied per read, so it bounds how long the server may go
quiet rather than how long the whole reply may take — generation on CPU-only
hardware is legitimately slow, and the first quiet stretch is prompt eval. The
connect phase keeps a separate 5 s budget, so an endpoint that is not accepting
connections is reported in seconds instead of after the generation budget. A
stall past the read budget raises `TimeoutError`, which the turn endpoint reports
as a retryable 504 `TURN_TIMEOUT`.

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
- Reports deterministic timings: two `reading` progress chunks before the
  first token, and a `ChatTimings` block of one millisecond per prompt token
  read and two per token written (1 000 and 500 tokens/s), nothing cached,
  `finish_reason: "stop"`. The scripted tutorial runtime does the same, so
  tests of the turn-timing record have fixed figures to assert against.
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
