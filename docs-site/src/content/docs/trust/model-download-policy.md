---
title: "Model download policy"
description: "Rules governing how LLM model weights are downloaded, verified with SHA-256 checksums, and disclosed to players — no silent downloads, no bundled weights."
sidebar:
  order: 4
verified_against: v0.2.3
---

> **Purpose:** Define the rules that govern how LLM model weights are
> downloaded, verified, and surfaced to players. No model weights are bundled
> in Steam depots or the open-source installer — all weights are downloaded
> explicitly after first launch at the player's request.
>
> **Scope:** Conversation Simulator Steam edition and open-source desktop build.
> The policy applies to registry-managed models and to user-supplied GGUF files.
>
> **Compliance cross-references:** MD-01 (silent download), MD-02 (checksum),
> MD-03 (licence disclosure), MD-04 (bundled weights) in
> [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](https://github.com/outrightmental/ConversationSimulator/blob/main/publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md).

---

## 1. Download rules

### No silent downloads

No model download may be triggered by:

- App startup or splash screen
- Background update checking
- Any installer script or post-install hook
- Pack loading or session start

Every download must begin with **explicit player confirmation** of all six
mandatory disclosure fields (see [Section 4](#4-licence-disclosure)). Until the
player presses **Download**, zero bytes are transferred.

Cancelling a download at any point leaves no permanent files on disk (partial
files are written to a temporary location and cleaned up on cancel — see
[Section 6](#6-retry-and-resume-behaviour)).

### Only registry-managed and user-supplied models

The model manager accepts two model sources:

| Source | Who controls the URL | Checksum verified? |
|--------|---------------------|--------------------|
| Registry-managed | `model-registry/registry.yaml` | YES — mandatory |
| User-supplied GGUF | Player selects a local file path | NO — cannot verify unknown provenance; player is informed |

The app never fetches models from URLs not present in the registry or directly
provided by the player. There is no auto-update or silent version upgrade for
installed model weights.

### Destination directory

All downloaded model files are written to `~/.convsim/models/` on the player's
machine. This path is shown in the download confirmation panel. The player may
not redirect this path in v1; future milestones may expose a configurable
models directory.

Subdirectories within `~/.convsim/models/` are created by model ID:

```
~/.convsim/models/
  qwen3-4b-instruct-q4_k_m.gguf
  qwen3-8b-instruct-q4_k_m.gguf
  ...
  .tmp/                           # in-progress downloads only; cleared on success or cancel
```

---

## 2. Mirror and CDN policy

### Primary source: HuggingFace Hub

All registry-managed models list `provider: huggingface` in `model-registry/registry.yaml`.
The download URL points directly to HuggingFace Hub (e.g.
`https://huggingface.co/<org>/<repo>/resolve/<ref>/<filename>.gguf`).

All registry-managed URLs are pinned to a specific repo revision (commit SHA)
and paired with a verified checksum. The `PENDING` sentinel remains reserved in
the schema for any future pre-release entry; while an entry carries
`url: PENDING` the model manager shows a **Not yet available** state and its
download is blocked.

### No automatic mirror fallback

The model manager does **not** configure automatic fallback mirrors. A mirror
URL would require a separate trusted checksum and a separate licence disclosure
review. Automatic failover to an unvetted mirror could serve unexpected content.

If the primary HuggingFace URL is unavailable, the player receives an error
with the reason and a suggestion to try again later. Manual mirror support (the
player pastes an alternative URL) is a candidate for a future milestone if
demand warrants it.

### User-supplied GGUF files

Players may load any GGUF file from their local filesystem during first-run
setup by expanding **Advanced** on the welcome screen and choosing **Use a
GGUF file**. The app performs no
network fetch for user-supplied files. The player is responsible for
downloading the file themselves and verifying its provenance.

---

## 3. Checksum policy

### SHA-256 is mandatory for all registry-managed models

Every registry-managed model entry in `model-registry/registry.yaml` must
include a valid 64-character lowercase hex SHA-256 checksum in the
`download.sha256` field. The value `PENDING` is allowed only until Milestone 1
(see `schemas/model-registry.schema.json`). After Milestone 1 no new registry
entry may be merged without a verified checksum.

### Post-download verification

After a download completes, the model manager:

1. Computes SHA-256 of the downloaded file in a streaming pass (to avoid
   holding the full file in memory).
2. Compares the computed digest against `download.sha256` from the registry.
3. On **match**: moves the file from `.tmp/` to `~/.convsim/models/<model-id>.gguf`
   and marks the model as installed.
4. On **mismatch**: deletes the downloaded file from `.tmp/`, clears any
   in-progress resume token, and surfaces an error to the player with the
   expected and actual checksums. The player may retry; the manager will
   re-download from scratch (no partial resume is used after a checksum failure).

The checksum check cannot be skipped or suppressed, even via developer flags.

### Updating checksums

When a model provider publishes a new quantisation revision under the same
model ID, the registry entry must be updated with the new URL and SHA-256
before the new file is downloadable. Old installed files at the previous
checksum remain valid until the player explicitly removes them.

### User-supplied GGUF files

The model manager does **not** verify checksums for user-supplied GGUF files.
The download confirmation panel explicitly states this:

> "This is a user-supplied file. Its source and integrity cannot be verified by
> Conversation Simulator. Ensure you obtained it from a trusted source."

---

## 4. Licence disclosure

Before the **Download** button becomes active, the model manager must display
all six mandatory disclosure fields simultaneously on a single confirmation
screen. No partial disclosure is acceptable.

| # | Field | Source | Example |
|---|-------|--------|---------|
| 1 | **Model name** | `name` field in registry | `Qwen3 4B Instruct Q4_K_M` |
| 2 | **Source URL** | `download.url` in registry | `https://huggingface.co/…` |
| 3 | **Licence** | `license` + `license_url` in registry | `Apache 2.0` with link to `https://www.apache.org/licenses/LICENSE-2.0` |
| 4 | **Download size** | `size_gb` in registry | `2.5 GB` |
| 5 | **SHA-256 checksum** | `download.sha256` in registry | `abc123…` (64 hex chars) or `PENDING — not yet available` |
| 6 | **Destination path** | Resolved at runtime | `~/.convsim/models/qwen3-4b-instruct-q4_k_m.gguf` |

The licence field must include a clickable link that opens the full licence text
at `license_url` in the player's default browser. This is a hard requirement
for compliance rule MD-03.

Models with `sha256: PENDING` may **not** be downloaded. The **Download**
button is disabled and a message explains that the model is not yet available
in this release.

For user-supplied GGUF files, fields 1–5 are either unknown or player-supplied.
The confirmation screen must clearly label these as unverified.

---

## 5. Model registry schema enforcement

The model registry schema at [`schemas/model-registry.schema.json`](https://github.com/outrightmental/ConversationSimulator/blob/main/schemas/model-registry.schema.json) enforces:

- `sha256` must be a 64-character hex string or the literal string `PENDING`.
- `license` is required for all registry-managed models.
- `license_url` is required for all registry-managed models.
- `size_gb` is required for all registry-managed models.
- User-supplied entries must use `license: unknown-user-supplied` and may have
  `sha256` absent entirely.

Schema validation runs in CI on every push
([`.github/workflows/ci.yml`](https://github.com/outrightmental/ConversationSimulator/blob/main/.github/workflows/ci.yml) — `schemas` job). A pull request that adds or
modifies a registry entry without meeting the schema requirements fails CI.

---

## 6. Retry and resume behaviour

### In-progress download location

Active downloads are written to `~/.convsim/models/.tmp/<model-id>.gguf.part`.
The `.part` suffix indicates an in-progress transfer.

### Cancellation

If the player cancels a download:

- The `.part` file is deleted immediately.
- No resume token is stored.
- The model manager returns to the **Not installed** state for that model.

### Network failure and automatic retry

If a download fails due to a network error (connection reset, timeout, DNS
failure):

1. The model manager retries up to **three times** with exponential back-off
   (5 s, 30 s, 120 s).
2. If all retries fail, the `.part` file is preserved for a manual resume
   on the next attempt.
3. The player is shown the error and given a **Try again** button.

### Manual resume

When the player initiates a download for a model that has a `.part` file:

1. The model manager inspects the file size of the `.part` file.
2. It issues an `HTTP Range: bytes=<size>-` request to the download URL.
3. If the server supports range requests (HTTP 206 Partial Content), the
   download resumes from where it left off.
4. If the server does not support range requests (HTTP 200 Full Content),
   the `.part` file is truncated and the download restarts from the beginning.

### App exit during download

If the app exits (graceful shutdown or crash) while a download is in progress:

- The `.part` file is left on disk.
- On next launch, the model manager detects the stale `.part` file and
  offers a **Resume** or **Start over** option.
- A stale `.part` file is never silently resumed without player action.

### Post-verification cleanup

After a successful SHA-256 verification, the `.part` file is renamed to
`<model-id>.gguf` in `~/.convsim/models/`. The `.tmp/` directory is then
empty. If the verification fails, the complete downloaded file is deleted (not
the original `.part` file — which no longer exists at that point), and the
player is offered a **Try again** option that starts a fresh download.

---

## 7. Model registry reference

The authoritative source of model metadata is [`model-registry/registry.yaml`](https://github.com/outrightmental/ConversationSimulator/blob/main/model-registry/registry.yaml).
See [`model-registry/README.md`](https://github.com/outrightmental/ConversationSimulator/blob/main/model-registry/README.md) for the policy on adding new entries and the
schema reference.

Current registry-managed models (v1):

| Model ID | Tier | Size | Licence |
|----------|------|------|---------|
| `qwen3-4b-instruct-q4_k_m` | Starter | 2.5 GB | Apache 2.0 |
| `qwen3-8b-instruct-q4_k_m` | Standard | 5.0 GB | Apache 2.0 |
| `qwen3-14b-instruct-q4_k_m` | High-quality | 9.0 GB | Apache 2.0 |
| `mistral-small-3.1-24b-instruct-q4_k_m` | High-quality | 14.3 GB | Apache 2.0 |
| `user-supplied-gguf` | User-supplied | Unknown | Unknown |

All registry-managed download URLs are pinned to a commit SHA and paired with a
verified SHA-256 checksum; no entry ships a `PENDING` value.

---

## Links

- [`model-registry/registry.yaml`](https://github.com/outrightmental/ConversationSimulator/blob/main/model-registry/registry.yaml) — model metadata
- [`model-registry/README.md`](https://github.com/outrightmental/ConversationSimulator/blob/main/model-registry/README.md) — registry policy
- [`schemas/model-registry.schema.json`](https://github.com/outrightmental/ConversationSimulator/blob/main/schemas/model-registry.schema.json) — JSON Schema
- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](https://github.com/outrightmental/ConversationSimulator/blob/main/publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — risk register (MD-01–MD-04)
- [`publishing/STEAM_DEPOT_CONTENTS.md`](https://github.com/outrightmental/ConversationSimulator/blob/main/publishing/STEAM_DEPOT_CONTENTS.md) — what ships in the depot
- [Choosing how to run the AI](/play/ai-engine/) — player-facing model installation guide
- [Steam roadmap](/dev/steam-roadmap/) — model download transparency specification
