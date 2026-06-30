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
- Download provider, URL placeholder, and SHA-256 checksum placeholder
- Runtime configuration defaults (context length, temperature, top-p)

## Model tiers

| Tier         | Model family             | Target use                            |
| ------------ | ------------------------ | ------------------------------------- |
| Low-end      | Qwen3 4B / 8B quantized  | First-run demo, lower VRAM systems    |
| Standard     | Qwen3 14B quantized      | Default quality target                |
| High-end     | Mistral Small 3.1 24B Q  | Better NPC quality on strong GPUs     |
| Experimental | User-supplied GGUF       | Power-user customization              |

## Policy

No model weights are redistributed in this repository. Download URLs and
checksums are placeholders until confirmed at the time of Milestone 1
implementation.
