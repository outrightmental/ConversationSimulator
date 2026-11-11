<!-- SPDX-License-Identifier: Apache-2.0 -->
# model-registry/

Curated registry of local LLM models that Conversation Simulator supports.

Models are **not bundled** in this repository. The registry provides metadata
so the in-app model manager can display download options, license disclosures,
hardware requirements, and checksum verification before the user downloads.

## registry.yaml

The primary registry file. Each entry includes:

- Model ID, name, family, and role
- SPDX license identifier (shown to user before download)
- Minimum and recommended VRAM targets
- Download provider, URL pinned to a specific repo revision, and SHA-256 checksum
- Runtime configuration defaults (context length, temperature, top-p)

The `runtime.llama_cpp` defaults are all used. `context_length` sizes the
engine's context when the app launches it. `temperature_default` and
`top_p_default` are the sampling a conversation on that model is sent with:
each NPC turn, its repair and retry calls, and the debrief. The model is the
file the app starts the engine on, matched to its entry the same way as for
`context_length`, whether or not a selection is saved. A model whose entry
leaves one out, a GGUF you registered yourself, and a llama-server you
started on a data directory with no install record of its file are sent at
temperature 0.8 and the llama.cpp adapter's top-p (0.95 unless
`CONVSIM_LLAMA_CPP_TOP_P` sets it); `docs/runtime-adapters.md` has the
details. The model benchmark keeps its fixed temperature of 0.

All registry-managed models have a verified 64-character lowercase SHA-256
hex digest and a Hugging Face URL pinned to a specific commit SHA.  The app
refuses to start a download if either field is missing or equals `PENDING`.

## Model tiers

| Tier         | Model                              | Size    | Min VRAM |
| ------------ | ---------------------------------- | ------- | -------- |
| Starter      | Qwen3 4B Instruct 2507 Q4\_K\_M    | 2.5 GB  | 4 GB     |
| Standard     | Qwen3 8B Instruct Q4\_K\_M         | 5.0 GB  | 6 GB     |
| High-quality | Qwen3 14B Instruct Q4\_K\_M        | 9.0 GB  | 10 GB    |
| High-quality | Mistral Small 3.1 24B Q4\_K\_M     | 14.3 GB | 16 GB    |
| User-supplied | Any GGUF                          | varies  | varies   |

### Demo edition

The free Steam Next Fest demo installs exactly one model: the `role: starter`
entry above, unless `CONVSIM_DEMO_MODEL_ID` names another registry id. That is
the hook for evaluating a smaller/faster tier for the demo without a code
change — see [`docs/steam-next-fest-demo.md`](../docs/steam-next-fest-demo.md)
for the quality gate a candidate must clear.

## Mirror and fallback policy

### Primary source

All registry-managed models are downloaded directly from **Hugging Face Hub**
(`huggingface.co`).  URLs are pinned to a specific commit SHA so the same
file is always served, even if the upstream repo is later updated or deleted.

Example pinned URL format:

```
https://huggingface.co/{org}/{repo}/resolve/{commit_sha}/{filename}
```

### When Hugging Face is unavailable

The app does not automatically fall back to a mirror.  If HuggingFace is
unreachable or rate-limits your connection:

1. **Wait and retry.** Transient rate limits (HTTP 429) usually clear within
   a few minutes.
2. **Use a community mirror.** If you have the same file from a trusted
   source (e.g. a local NAS, a university mirror, or an employer's model
   cache), place the GGUF file in `~/.convsim/models/llm/` and register it
   via **Settings → Models → Use custom GGUF**.  The app will skip the
   download and load from that path.
3. **Verify the checksum manually.** If you obtained the file from a mirror,
   always verify the SHA-256 checksum against the value in `registry.yaml`
   before loading the model.  The app performs this check automatically for
   registry-managed downloads, but not for user-supplied files.

### When a model repo moves or is deleted

URLs are pinned to a commit SHA, not just `main`.  If the upstream repo is
deleted, the URL will return 404.  In that case:

- The nightly CI job (`registry-nightly.yml`) will detect the broken URL and
  alert maintainers via a failed workflow.
- Maintainers should update `registry.yaml` to point to a replacement source,
  recompute the SHA-256, and submit a PR.  The no-PENDING CI check ensures the
  updated entry is complete before merging.

### Adding a new model

1. Add the entry to `registry.yaml` with the real download URL (pinned to a
   commit SHA), verified SHA-256, and accurate `size_gb`. For a Hugging Face
   GGUF, `python scripts/pin-model.py <org/repo> <file.gguf> --id … --role …
   --min-vram … --recommended-vram …` prints a policy-compliant entry: the
   Hub's Git-LFS object id is the file's SHA-256 and the repo's current commit
   pins the URL, so nothing has to be downloaded to hash it.
2. Do **not** use `PENDING` — the per-PR CI (`test_actual_registry_no_pending_values`)
   will reject the PR until real values are present.
3. Run `python scripts/validate-registry.py --url-check` locally to confirm
   the URL is reachable before opening a PR.

## Policy

No model weights are redistributed in this repository.  Models are downloaded
on demand, after the user reads and accepts the license disclosed in the
model manager.
