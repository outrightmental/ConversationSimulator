<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Stream fixtures

Raw engine streams the runtime adapters are tested against (issue #519).

A file whose name starts with the engine tag (for example
`llama_server_b9415_turn.sse`) is a verbatim capture from that build. A file
whose name starts with `synthetic_` was written by hand from the engine's
documented wire format because the build could not be run where the fixture
was made, and says so in its first comment line. Replace a synthetic fixture
with a capture when one exists; keep the file name's tag honest.

| File | Engine | What it shows |
|---|---|---|
| `synthetic_llama_server_b9415_turn.sse` | llama-server b9415 (OpenAI-compatible SSE) | A full turn with `prompt_progress` chunks, per-token `timings`, a `usage` chunk with empty `choices`, and `finish_reason: stop` |
| `synthetic_llama_server_b9415_length.sse` | llama-server b9415 | A turn cut off at the token cap: `finish_reason: length` |
| `synthetic_llama_server_no_timings.sse` | an OpenAI-compatible server that reports nothing | Tokens and a finish, no `usage`, no `timings`, no `prompt_progress` |
| `synthetic_ollama_0_34_turn.ndjson` | Ollama ≥ 0.34 (`prompt_eval_cached_count` present) | A full turn with every duration field |
| `synthetic_ollama_0_33_turn.ndjson` | Ollama < 0.34 (no cached count) | The same turn without `prompt_eval_cached_count` |

Capturing a llama-server fixture: start the pinned build with the starter model
and run one turn with `curl -N` against `/v1/chat/completions` using the same
body `LlamaCppRuntime._build_payload` sends (`stream`, `stream_options.include_usage`,
`return_progress`, `timings_per_token`), then save the response verbatim.
