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

All registry-managed models have a verified 64-character lowercase SHA-256
hex digest and a Hugging Face URL pinned to a specific commit SHA.  The app
refuses to start a download if either field is missing or equals `PENDING`.

## Model tiers

| Tier         | Model                              | Size    | Min VRAM |
| ------------ | ---------------------------------- | ------- | -------- |
| Starter      | Qwen3 4B Instruct Q4\_K\_M         | 2.5 GB  | 4 GB     |
| Standard     | Qwen3 8B Instruct Q4\_K\_M         | 5.0 GB  | 6 GB     |
| High-quality | Qwen3 14B Instruct Q4\_K\_M        | 9.0 GB  | 10 GB    |
| High-quality | Mistral Small 3.1 24B Q4\_K\_M     | 14.3 GB | 16 GB    |
| User-supplied | Any GGUF                          | varies  | varies   |

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
   commit SHA), verified SHA-256, and accurate `size_gb`.
2. Do **not** use `PENDING` — the per-PR CI (`test_actual_registry_no_pending_values`)
   will reject the PR until real values are present.
3. Run `python scripts/validate-registry.py --url-check` locally to confirm
   the URL is reachable before opening a PR.

## Policy

No model weights are redistributed in this repository.  Models are downloaded
on demand, after the user reads and accepts the license disclosed in the
model manager.
