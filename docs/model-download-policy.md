<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Model Download Policy

> **Purpose:** Define the rules that govern how LLM model weights are
> downloaded, verified, and surfaced to players. No model weights are bundled
> in Steam depots or in the repository. All weights are downloaded explicitly
> after first launch at the player's request.
>
> **Scope:** Conversation Simulator Steam edition and builds from source. The
> policy applies to registry-managed models and to user-supplied GGUF files.
> Section 8 covers the inference engine binary, which is the only other file
> the app downloads, and the update manifest that builds from source fetch.
>
> **Compliance cross-references:** MD-01 (silent download), MD-02 (checksum),
> MD-03 (licence disclosure), MD-04 (bundled weights) in
> [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](../publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md).

---

## 1. Download rules

### No silent downloads

No model download may be triggered by:

- App startup or splash screen
- Background update checking
- Any installer script or post-install hook
- Pack loading or session start

Every download begins with an explicit player action on a screen that states
the model's size and licence (see [Section 4](#4-licence-disclosure)):

- **Set me up** on the Welcome screen. The card reads "Downloads the AI model
  (2.5 GB, Apache-2.0). Works offline afterwards." with the size and licence
  taken from the registry.
- **Confirm & install** on the **Confirm model install** screen, reached from
  the **Install recommended model** card in the first-run chooser or in the
  model manager.

Until the player presses one of these, zero bytes are transferred. The one
exception is a download the player already confirmed and that the app was
closed in the middle of; it is continued at the next launch (see
[Section 6](#6-retry-and-resume-behaviour)).

Cancelling a download leaves no model file on disk: the in-progress `.part`
file is deleted on cancel.

### Only registry-managed and user-supplied models

Two sources of model files are accepted:

| Source | Who controls the URL | Checksum verified? |
|--------|---------------------|--------------------|
| Registry-managed | `model-registry/registry.yaml` | YES — mandatory |
| User-supplied GGUF | Player selects a local file path | NO — cannot verify unknown provenance; player is informed |

The app never fetches model weights from any URL other than the one in the
registry entry, and a user-supplied GGUF file involves no network fetch at
all. There is no auto-update or silent version upgrade for installed model
weights.

The chooser's second card, **Use existing Ollama model**, connects to a model
that the player's own Ollama installation already holds. The app downloads
nothing for it (the step tells the player to pull a model with Ollama first),
so it is outside this policy. The demo edition does not show the card.

### Destination directory

Downloaded model files are written to `models/llm/` under the app's data
folder. The desktop shell builds that folder from the operating system's
local data directory and the app identifier `com.outrightmental.convsim`,
and passes it to convsim-core as `CONVSIM_DATA_ROOT` whenever it launches
the service, which every packaged build does. The demo edition's shell uses
the same identifier for this folder even though its bundle identifier
differs, so the demo and the full app share one models folder:

| Platform | Models folder |
|----------|---------------|
| Linux / Steam Deck | `$XDG_DATA_HOME/com.outrightmental.convsim/models/llm/`, or `~/.local/share/com.outrightmental.convsim/models/llm/` when `XDG_DATA_HOME` is unset |
| macOS | `~/Library/Application Support/com.outrightmental.convsim/models/llm/` |
| Windows | `%LOCALAPPDATA%\com.outrightmental.convsim\models\llm\` |

Settings shows the real path in the **Local folders** list as the **Models**
row (`GET /api/privacy/folders`). The app has no setting for moving the
folder; developers can point `CONVSIM_DATA_ROOT` or `CONVSIM_MODELS_DIR`
elsewhere. When convsim-core is started without `CONVSIM_DATA_ROOT`, for
example a developer running the Python service on its own,
`convsim_core.paths.platform_data_root` falls back to its own defaults:
`$XDG_DATA_HOME/convsim` (or `~/.local/share/convsim`) on Linux and
`%LOCALAPPDATA%\outrightmental\convsim` on Windows, which are different
folders from the ones the desktop app uses; the macOS fallback is the same
folder as above.

The **Saves to** row of the confirmation screen (**Storage path** in the
model manager) shows the filename under a `~/.convsim/models/llm/` prefix.
That prefix is wrong on every build, including developer runs from source:
`~/.convsim` is the legacy data location, and model files are written under
the folders above. Only the filename on that row is accurate.

Files are named after the model ID:

```
<models folder>/
  qwen3-4b-instruct-q4_k_m.gguf
  qwen3-8b-instruct-q4_k_m.gguf
  ...
  qwen3-4b-instruct-q4_k_m.gguf.part   # only while a download is in progress
```

### Voice models

The app does not download speech models. The Whisper speech-to-text and
Silero voice-detection model files are fetched by the developer scripts
`runtimes/whisper_cpp/download-runtime.sh` and
`runtimes/silero_vad/download-model.sh` into `~/.convsim/models/stt/` and
`~/.convsim/models/vad/`, or placed there by the player; the Kokoro
text-to-speech worker talks to a server the player runs. See the READMEs in
`runtimes/`.

---

## 2. Mirror and CDN policy

### Primary source: HuggingFace Hub

All registry-managed models list `provider: huggingface` in `model-registry/registry.yaml`.
The download URL points directly to HuggingFace Hub (e.g.
`https://huggingface.co/<org>/<repo>/resolve/<ref>/<filename>.gguf`).

All registry-managed URLs are pinned to a specific repo revision (commit SHA)
and paired with a verified checksum. The schema keeps a `PENDING` sentinel for
a pre-release entry, but no shipped entry carries one: the per-PR test
`test_actual_registry_no_pending_values` and the nightly
`scripts/validate-registry.py` run both reject it. Should one ever appear, the
confirmation screen flags the checksum as not yet confirmed and the setup
pipeline refuses to download it (see Section 4).

### No automatic mirror fallback

The model manager does **not** configure automatic fallback mirrors. A mirror
URL would require a separate trusted checksum and a separate licence disclosure
review. Automatic failover to an unvetted mirror could serve unexpected content.

If the HuggingFace URL is unreachable, the install stops with an error and
the player can try again; Section 6 describes what is shown. Manual mirror
support (the player pastes an alternative URL) is a candidate for a future
milestone if demand warrants it.

### User-supplied GGUF files

Players may load any GGUF file from their local filesystem. On the Welcome
screen, open **Advanced: use Ollama or a local GGUF file** and press **Use a
GGUF file**; in the model manager, use the **Use a local GGUF file** card. The
**Use a GGUF file** step takes a file path and activates it with **Use this
file**. The app performs no network fetch for user-supplied files. The player
is responsible for downloading the file themselves and verifying its
provenance. The demo edition does not offer this path.

---

## 3. Checksum policy

### SHA-256 is mandatory for all registry-managed models

Every registry-managed model entry in `model-registry/registry.yaml` must
include a valid 64-character lowercase hex SHA-256 checksum in the
`download.sha256` field. The schema (`schemas/model-registry.schema.json`)
also accepts the literal `PENDING` for a pre-release entry, but a registry
entry with `PENDING` cannot be merged: `test_actual_registry_no_pending_values`
fails the Backend tests job, and the setup pipeline refuses to download such
an entry (see Section 4).

### Post-download verification

After a download completes, the model manager:

1. Computes SHA-256 of the downloaded `.part` file in a streaming pass (64 KB
   blocks, so the file is never held in memory).
2. Compares the computed digest against `download.sha256` from the registry.
3. On **match**: renames the `.part` file to `<model-id>.gguf` in the models
   folder and marks the install `ready`, storing the verified checksum.
4. On **mismatch**: deletes the `.part` file and marks the install
   `checksum_mismatch` with the message "SHA-256 checksum mismatch. The
   downloaded file has been deleted." Nothing partial is kept, so a retry
   starts from zero. The setup pipeline downloads the file a second time on
   its own before giving up. If that copy also fails the check, the
   **Verifying (SHA-256)** stage fails with the same message and the player
   is offered **Try again** (Section 6 says where the error appears). The
   message does not say that two attempts were made.

The checksum check cannot be skipped or suppressed, even via developer flags.

### Updating checksums

When a model provider publishes a new quantisation revision under the same
model ID, the registry entry must be updated with the new URL and SHA-256
before the new file is downloadable. Old installed files at the previous
checksum remain valid until the player explicitly removes them.

### User-supplied GGUF files

The model manager does **not** verify checksums for user-supplied GGUF files,
and it does not copy the file: only its path is stored. The **Use a GGUF
file** step says so before the path field:

> "You are responsible for this model's license and hardware fit. This app
> does not claim the model you provide is official, licensed for
> redistribution, or suitable for your hardware. Review the model's license
> before use. The file will not be copied — only its path is stored."

---

## 4. Licence disclosure

Before **Confirm & install** can be pressed, the **Confirm model install**
screen shows all of the following at once. The screen itself says "No
download begins until you click Confirm & install."

| Row on screen | Source | Example |
|---------------|--------|---------|
| **Model** | `name` field in registry | `Qwen3 4B Instruct Q4_K_M` |
| **Size** | `size_gb` in registry | `2.5 GB` |
| **License** | `license` + `license_url` in registry | `Apache-2.0`, linked to `https://www.apache.org/licenses/LICENSE-2.0` |
| **Min VRAM** / **Recommended VRAM** | `hardware` in registry | `4 GB` / `6 GB` |
| **Integrity checksum** (**SHA-256 checksum** in the model manager) | `download.sha256` in registry | 64 hex chars |
| **Saves to** (**Storage path** in the model manager) | filename `<model-id>.gguf` | `qwen3-4b-instruct-q4_k_m.gguf` (see Section 1 for the folder) |
| **Source** (model manager only) | `source_type` | `Official registry` |

The licence row is a link that opens the full licence text at `license_url`
in the player's browser. This is a hard requirement for compliance rule MD-03.
The download URL itself is not shown on the screen; it is the `download.url`
of the entry in `registry.yaml`.

The **Set me up** card on the Welcome screen states the same size and licence
("Downloads the AI model (2.5 GB, Apache-2.0). Works offline afterwards.") and
starts the install directly, without the confirmation screen. In the demo
edition the card reads "Downloads the demo's AI model (...)".

An entry with `sha256: PENDING` cannot be installed. The confirmation screen
adds a warning beginning "Checksum not yet confirmed" to the checksum row,
and if the player goes ahead, the setup pipeline behind **Set me up** and
**Confirm & install** (`POST /api/setup/install`) fails its model stage with
"No verified SHA-256 checksum for this model — cannot install safely." before
any byte is fetched. The older `POST /api/models/install` endpoint, which no
screen calls, refuses the same entry with `MISSING_CHECKSUM`. No shipped entry
carries `PENDING`.

A user-supplied GGUF file does not pass through this screen. The **Use a GGUF
file** step shows the responsibility notice quoted in Section 3 instead; the
app makes no claim about the file's licence, source or integrity.

---

## 5. Model registry schema enforcement

The model registry schema at `schemas/model-registry.schema.json` enforces:

- `sha256` must be a 64-character hex string or the literal string `PENDING`.
- `license` is required for all registry-managed models.
- `license_url` is required for all registry-managed models.
- `size_gb` is required for all registry-managed models.
- User-supplied entries must use `license: unknown-user-supplied`, and their
  `download` block may hold only `provider: user-filesystem` and an optional
  `path_hint`; `url` and `sha256` are not allowed.

Validation runs in three places:

- The **Backend tests** job in `.github/workflows/ci.yml` runs
  `services/convsim-core/tests/test_model_registry.py` on every pull request
  and every push to `main`. It validates `registry.yaml` against the schema,
  rejects any `PENDING` value, and fails if a model weight file (`.gguf`,
  `.bin`, `.safetensors`, `.pt` or `.ckpt`) is found anywhere under
  `model-registry/`. It does not scan the rest of the repository.
- The nightly `.github/workflows/registry-nightly.yml` runs
  `scripts/validate-registry.py --url-check`, which also confirms every
  download URL still answers.
- convsim-core validates the file against the same schema when it loads it
  (`model_registry_service.load_and_persist_registry`).

A pull request that adds or modifies a registry entry without meeting the
schema requirements fails CI.

---

## 6. Retry and resume behaviour

Errors from the setup pipeline appear in two places. In the first-run wizard
the **Setting up your AI** step shows the error with a **Try again** button;
the full app also offers **Choose a different option**, which the demo hides.
In the model manager the error is shown on the **Confirm model install**
screen under the heading **Request failed**, and the player can press
**Confirm & install** again.

### In-progress download location

Active downloads are written to `<models folder>/<model-id>.gguf.part`,
beside where the finished file will be. The `.part` suffix indicates an
in-progress transfer.

### Disk space check

Before the download starts, the setup pipeline checks that about 2.2 times
the model's size is free in the models folder (room for the `.part` file and
the finished file). If not, the install stops with **Not enough disk space**
and a **Try again** button; nothing is downloaded.

### Cancellation

If the player presses **Cancel and go home** while the install is running:

- The `.part` file is deleted immediately.
- The install record is marked `cancelled`.
- The model stays uninstalled; the model manager offers the install again.

**Cancel** on the confirmation screen returns to the chooser without starting
a download.

### Network failure

If a download fails because of a network error (connection reset, timeout,
DNS failure):

1. The `.part` file is deleted and the install record is marked `failed`
   with the error text reported by the HTTP library, stored as is; for a
   timeout that text is empty. The setup job's model stage carries the same
   text, or "Download failed." when the record's text is empty, and the
   stage text is what the player sees. There is no automatic retry.
2. The wizard shows the stage text with **Try again**. It also has a friendlier
   **Network connection lost** panel with a **Retry** button, but that panel
   appears only when the error text contains a phrase such as
   "offline", "timed out" or "connection refused". The texts the download
   library produces today (for example "All connection attempts failed", or
   "Download failed." for a timeout) do not match, so a player who loses the
   connection usually sees the raw text.
3. **Try again** and **Retry** return to the **Confirm model install** screen
   (or restart the install directly when the wizard reopened on a resumed
   job). The next download starts from the beginning.

### App exit during download

If the app exits (graceful shutdown or crash) while a download is in progress:

- The `.part` file is left on disk, because the download task died with the
  process.
- On the next launch, convsim-core re-drives the newest unfinished install
  job on its own (`resume_orphaned_jobs`). Whether a screen shows it depends
  on whether first-run setup was ever finished. While no onboarding outcome
  is recorded (`GET /api/setup/status` answers `never-run`), the app sends
  the player to the wizard, which reopens on the **Setting up your AI**
  progress step; there is no separate prompt to resume or start over. Once
  an outcome is recorded (the wizard was finished, or **Cancel and go home**
  was pressed at some earlier point), the job still resumes in the
  background but no screen reopens for it. The model manager shows the
  running job again only when the player presses **Confirm & install** for
  the same model: `POST /api/setup/install` then reattaches to the active
  job instead of starting a new one.
- The download sends `Range: bytes=<size of .part>-`. If the server answers
  `206 Partial Content`, the transfer appends from where it stopped. If it
  answers `200`, the `.part` file is truncated and the download restarts from
  the beginning.
- The SHA-256 check in Section 3 still gates registration, so a corrupt
  resume can never be promoted to `ready`.

### Post-verification cleanup

After a successful SHA-256 verification, the `.part` file is renamed to
`<model-id>.gguf` in the models folder. If the verification fails on both
attempts (Section 3), the `.part` file is deleted and the player is offered
**Try again**; the next download starts from zero.

---

## 7. Model registry reference

The authoritative source of model metadata is `model-registry/registry.yaml`.
See `model-registry/README.md` for the policy on adding new entries and the
schema reference.

Current registry entries:

| Model ID | Tier | Size | Licence |
|----------|------|------|---------|
| `qwen3-4b-instruct-q4_k_m` | Starter | 2.5 GB | Apache-2.0 |
| `qwen3-8b-instruct-q4_k_m` | Standard | 5.0 GB | Apache-2.0 |
| `qwen3-14b-instruct-q4_k_m` | High-quality | 9.0 GB | Apache-2.0 |
| `mistral-small-3.1-24b-instruct-q4_k_m` | High-quality | 14.3 GB | Apache-2.0 |
| `user-supplied-gguf` | User-supplied | Unknown | Unknown |

All registry-managed download URLs are pinned to a commit SHA and paired with a
verified SHA-256 checksum; no entry ships a `PENDING` value.

The Steam Next Fest demo installs exactly one model: the `role: starter` entry
(Qwen3 4B Instruct Q4_K_M), unless `CONVSIM_DEMO_MODEL_ID` names another
registry id. See [`docs/steam-next-fest-demo.md`](steam-next-fest-demo.md)
for the decision.

---

## 8. Engine binary download policy

The inference engine (`llama-server`) is downloaded under the same rules as
model weights: nothing is downloaded at startup, and the player starts it.

### Trigger

The engine is installed by the first stage of the setup pipeline, **Getting
the AI engine**, which runs when the player presses **Set me up** or **Confirm
& install**. The stage is skipped when a `llama-server` binary is already
present. The system health check in Settings (`GET /api/preflight`) offers an
**Install engine** action when the binary is missing; it opens the model
manager, where the same install path applies. `POST /api/sidecar/download-runtime`
exists for API callers; the app's screens do not call it directly.

### Source and version

Binaries come from the official llama.cpp GitHub releases
(`https://github.com/ggml-org/llama.cpp/releases`). An in-app install fetches
the latest release at the time of the install. The app does not show the tag,
and no endpoint reports which tag an in-app install fetched: the pipeline
keeps only byte counts from the engine download, and
`GET /api/sidecar/download-runtime` reports a tag only for a download started
through `POST /api/sidecar/download-runtime`, which the app's screens do not
use. Steam depot builds bundle the tag pinned in
`runtimes/llama_cpp/download-runtime.sh` and `download-runtime.ps1` (`b9415`
at this release).

### Integrity

The archive is checked in memory against the `sha256sum.txt` published with
the release before anything is written. A mismatch moves the download to
`checksum_mismatch` and nothing is installed. If the release carries no
`sha256sum.txt` entry for the asset, the download is installed unverified.

### Destination

The binary is placed at `~/.convsim/bin/llama-server` (`llama-server.exe` with
its DLLs on Windows). convsim-core looks for the engine in this order:
`CONVSIM_LLAMA_CPP_EXECUTABLE`, then `CONVSIM_BUNDLED_RUNTIME_DIR`, then
`~/.convsim/bin`, then `PATH`.

### Variants

| Variant | When to use |
|---------|-------------|
| `cpu` (default) | Works on every machine. The setup pipeline always installs this one. |
| `vulkan` | GPU acceleration on Windows. `GET /api/sidecar/gpu-variant` recommends it when `nvidia-smi` or `vulkaninfo` finds a GPU; it is an opt-in request on `POST /api/sidecar/download-runtime`. |

GPU variants are **never required** for first-run. Vulkan is recommended for
NVIDIA GPUs too because the NVIDIA driver ships the Vulkan runtime and Vulkan
is a single, self-contained release asset. llama.cpp publishes CUDA builds per
toolkit version plus a separate `cudart-*` archive, which the single-asset
downloader cannot provision, so CUDA is not offered.

### Offline behaviour

Without a connection the **Getting the AI engine** stage fails with a message
that names the connection problem, and **Try again** behaves as described in
Section 6.

### Steam builds

Every release build bundles `llama-server` under `resources/runtimes/` in the
app bundle. The desktop shell exposes that directory to convsim-core as
`CONVSIM_BUNDLED_RUNTIME_DIR`, so the engine stage is skipped and no download
is needed at first launch. Builds from source download the engine on first
run. See [`docs/sidecar-bundling.md`](sidecar-bundling.md).

### Update check (builds from source)

A build from source asks GitHub once per visit to the Home screen whether a
newer beta exists, by fetching
`https://github.com/outrightmental/ConversationSimulator/releases/download/beta-channel/latest.json`.
The request downloads no files: when a newer version is listed, the Home
screen shows a banner whose **Install** button opens the release page in the
player's browser. Failures are silent, so an offline machine sees nothing.
Steam builds remove the updater from the Tauri configuration and never make
this request; Steam delivers updates itself.

---

## Links

- [`model-registry/registry.yaml`](../model-registry/registry.yaml) — model metadata
- [`model-registry/README.md`](../model-registry/README.md) — registry policy
- [`schemas/model-registry.schema.json`](../schemas/model-registry.schema.json) — JSON Schema
- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](../publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — risk register (MD-01–MD-04)
- [`publishing/STEAM_DEPOT_CONTENTS.md`](../publishing/STEAM_DEPOT_CONTENTS.md) — what ships in the depot
- [`docs/local-models.md`](local-models.md) — player-facing model installation guide
- [`docs/STEAM_ROADMAP.md`](STEAM_ROADMAP.md) — model download transparency specification
- [`docs/sidecar-bundling.md`](sidecar-bundling.md) — sidecar bundling and executable resolution
