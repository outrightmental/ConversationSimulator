<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Security Policy

## Supported versions

No release versions exist yet. Security fixes apply to the `main` branch only
during pre-release development.

## Reporting a vulnerability

Please **do not** open a public GitHub Issue for security vulnerabilities.

Instead, report security issues privately using
[GitHub's private vulnerability reporting](https://github.com/outrightmental/ConversationSimulator/security/advisories/new)
or by emailing the maintainers directly (address on file in the GitHub
organization contact page).

Include:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested mitigations (optional)

We aim to acknowledge reports within **72 hours** and provide an initial
assessment within **7 days**. Actual fix timelines depend on complexity and
maintainer availability — this is a small team and we cannot guarantee
service-level commitments beyond these targets.

We ask reporters to wait for a fix to be available before publishing technical
details (coordinated disclosure). We do not operate a bug-bounty programme.

## What to report privately

Use private reporting for technical vulnerabilities:

- **Unsafe content bypass** — player input that produces prohibited content
  despite the safety policy being active.
- **Prompt injection escape** — a crafted pack or player input that causes the
  NPC runtime to behave outside the declared safety policy in a way that poses
  real user risk.
- **Local privilege escalation** — a defect that allows a pack, scenario file,
  or crafted input to execute arbitrary code on the user's machine.
- **Data exfiltration** — a defect that causes transcripts or local user data
  to leave the machine unexpectedly.
- **Local network exposure** — a code path that binds a service beyond
  `127.0.0.1` without the user's explicit intent.

Content-only safety concerns (e.g., a pack that contains poor content but does
not bypass a technical control) are **appropriate for public issues**. Use the
[Safety Issue](.github/ISSUE_TEMPLATE/safety_issue.yml) template for those.

## Scope

This project runs entirely on the user's local machine. The network-facing
attack surface is limited to `127.0.0.1` bindings only.

### Local-only data handling

| What | Where it stays |
|------|----------------|
| Conversation transcripts | SQLite at `~/.convsim/db/` — never uploaded |
| Audio input (STT) | Processed locally by whisper.cpp — never sent out |
| LLM inference | Runs via llama.cpp — stays on your machine |
| TTS audio | Generated locally by Kokoro / sherpa-onnx |
| Telemetry | None — the MVP ships no telemetry subsystem |

There is no telemetry, no analytics, and no account system. Nothing in the
codebase sends data to a remote endpoint during a session.

### Localhost binding

All five services (`convsim-ui`, `convsim-core`, `convsim-llm`, `convsim-stt`,
`convsim-tts`) bind exclusively to `127.0.0.1`. No service is reachable from
the local network or the internet. A defect that causes any service to bind on
`0.0.0.0` or any non-loopback address without user opt-in is a reportable
vulnerability.

## Scenario packs vs. plugins

**Packs are not plugins.** This distinction matters for security:

| | Scenario packs | Plugins |
|--|---|---|
| Format | Declarative YAML / JSON only | N/A — no plugin system exists |
| Executable code | Blocked — schema rejects `scripts` field | — |
| Network access during play | Blocked — outbound policy applies | — |
| External asset URLs | Blocked — `allow_external_urls` must be `false` | — |
| Safety policy override | Tightening only; global rules cannot be weakened | — |

A scenario pack is closer to a game level than a code extension. Packs define
NPC personas, scenario goals, and safety policy categories, but they cannot
execute code, make outbound requests, or weaken the global non-overridable
safety rules (`minors_romantic_or_sexual` and `self_harm_crisis`).

The pack validator enforces these constraints at load time. See
[docs/safety-policy.md](docs/safety-policy.md) for the full schema constraints.

There is **no general plugin system**. If a future release adds one, it will be
documented here with an associated threat model before release.

## Dependency review

### Runtime binaries

The project integrates three native binaries:

| Binary | Role | Trust model |
|--------|------|-------------|
| `llama-server` | Local LLM inference | Pinned release; SHA-256 checked at install |
| `whisper.cpp` | Speech-to-text | Same |
| Kokoro / sherpa-onnx | Text-to-speech | Same |

Verify checksums before installing or upgrading any runtime binary. The
`model-registry/registry.yaml` file lists expected checksums for all supported
model files.

When evaluating a PR that changes the pinned version of a runtime binary,
confirm:

1. The new version is from the official upstream project.
2. The commit or release tag is independently verified (not just a branch tip).
3. The checksum in `model-registry/registry.yaml` is updated to match.

### Speech models

Speech model files (`.gguf`, `.onnx`) are downloaded on demand. Each download:

1. Shows the model name, size, and license before starting.
2. Verifies the SHA-256 checksum against `model-registry/registry.yaml` after
   download.
3. Refuses to load a model that fails the checksum.

Do not manually install model files from untrusted sources. A malformed or
adversarially crafted model file could cause the runtime binary to behave
unexpectedly.

### Future plugins

No plugin system exists at this stage. If plugins are introduced:

- Plugins will be isolated from the pack format — a pack will never execute as
  a plugin.
- Plugins will require explicit user installation and will not auto-load.
- Each plugin type will carry its own threat model and will be documented here
  before release.

## Safe disclosure guidance

When reporting a vulnerability:

1. Do **not** open a public GitHub issue or post on public forums.
2. Do **not** include private transcript contents, conversation logs, or
   personal user data in any public report.
3. Use GitHub's private vulnerability reporting or contact maintainers directly.
4. We will acknowledge your report and keep you informed. If you do not receive
   acknowledgment within 72 hours, follow up via a different channel.
5. We ask reporters to hold technical details until a fix is available
   (coordinated disclosure).

## Maintainer checklist: security-sensitive PRs

Changes to the following areas require an explicit security review before merge.
The PR author should tick the relevant items; a maintainer must verify them
independently.

**Safety policy and input routing (`services/convsim-core/`)**

- [ ] Global non-overridable rules (`minors_romantic_or_sexual`,
  `self_harm_crisis`) remain unconditionally enforced.
- [ ] No code path allows a pack to weaken a non-overridable rule.
- [ ] Safety layer is still injected after the NPC persona in the prompt
  construction pipeline.
- [ ] Safety events are logged at WARNING level without writing raw player text.

**Pack loading and validation (`packages/scenario-schema/`, pack validator)**

- [ ] Schema still rejects packs with a `scripts` field.
- [ ] Asset path traversal is blocked (no `../` escape outside the pack
  directory).
- [ ] `allow_external_urls: true` is still rejected by the validator.
- [ ] Symlinks within pack archives are rejected at import time.

**Runtime binary management (`runtimes/`)**

- [ ] New or upgraded binary versions are pinned to a specific release tag or
  commit.
- [ ] Checksums in `model-registry/registry.yaml` are updated.
- [ ] Checksums are verified independently (not copied from the same source
  as the binary).

**Networking**

- [ ] All new service bindings use `127.0.0.1`, not `0.0.0.0` or an interface
  name.
- [ ] No new outbound HTTP calls are made during a session.
- [ ] Any new model download path shows license and size before starting, and
  verifies the checksum after.

**Data handling**

- [ ] No new code writes player text, transcripts, or audio to a path outside
  `~/.convsim/`.
- [ ] No new code sends data to a remote endpoint.
