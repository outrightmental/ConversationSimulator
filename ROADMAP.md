<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Roadmap

For the authoritative milestone breakdown, see
[GitHub Milestones](https://github.com/outrightmental/ConversationSimulator/milestones)
and the [full specification](docs/SPEC.md).

## Milestone overview

| Milestone | Goal                            | Status   |
| --------- | ------------------------------- | -------- |
| 0         | Monorepo skeleton and dev setup | Complete |
| 1         | Text-only local simulator       | TODO     |
| 2         | Scenario pack system            | TODO     |
| 3         | Local voice input (Whisper)     | TODO     |
| 4         | Local voice output (TTS)        | TODO     |
| 5         | Polished playable alpha         | TODO     |

## Milestone 0 — Monorepo skeleton (current)

- [x] Directory structure, licensing, tooling
- [x] Developer scripts (`setup.sh`, `dev.sh`)
- [x] Model registry placeholder
- [x] Community files (this file)

## Milestone 1 — Text-only local simulator

The first working build: a browser UI, Python backend, and local LLM working
together to run a single conversation scenario from start to debrief.

No voice, no desktop packaging. Text only.

See [docs/SPEC.md](docs/SPEC.md) for the full technical requirements.
