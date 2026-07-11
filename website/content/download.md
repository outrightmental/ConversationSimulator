---
title: Download
subtitle: Free, open source, and yours to keep. Runs entirely on your computer.
description: Download Conversation Simulator for Windows, macOS, or Linux — free and open source, running 100% locally.
---

<div class="dl-grid">
  <a class="dl-card" href="https://github.com/outrightmental/ConversationSimulator/releases/latest">
    <strong>Windows</strong>
    <span>Windows 10/11 · 64-bit installer</span>
  </a>
  <a class="dl-card" href="https://github.com/outrightmental/ConversationSimulator/releases/latest">
    <strong>macOS</strong>
    <span>Apple Silicon &amp; Intel · signed and notarized</span>
  </a>
  <a class="dl-card" href="https://github.com/outrightmental/ConversationSimulator/releases/latest">
    <strong>Linux</strong>
    <span>AppImage &amp; SteamOS-compatible builds</span>
  </a>
</div>

All downloads are served from
[GitHub Releases](https://github.com/outrightmental/ConversationSimulator/releases),
with checksums published alongside every build. A free Steam release is in
preparation and will carry the same local-first guarantee.

## What to expect on first launch

No model ships in the box — you choose what runs on your machine. On first
launch the app walks you through downloading a starter model
(**Qwen3 4B Instruct**, ~2.5 GB, Apache-2.0), with the license and size shown
before anything is fetched. One model download is the only time the app needs
the internet. After that, everything works offline.

**Recommended hardware:** any 64-bit machine with 8 GB RAM runs the starter
model; 6 GB+ of VRAM unlocks the larger, sharper models. Full details in the
[install guide](https://docs.conversationsimulator.com/start/install/) and
[local models guide](https://docs.conversationsimulator.com/play/local-models/).

## Run from source

The whole platform is open source, and the dev setup is two scripts:

```
git clone https://github.com/outrightmental/ConversationSimulator
cd ConversationSimulator
./scripts/setup.sh     # Windows: scripts\setup.ps1
./scripts/dev.sh       # Windows: scripts\dev.ps1
```

Then open `http://127.0.0.1:7354` in your browser. The
[quickstart](https://docs.conversationsimulator.com/start/quickstart/) takes
it from there.

## Having trouble?

The [troubleshooting guide](https://docs.conversationsimulator.com/start/troubleshooting/)
covers the common failure modes, and
[GitHub issues](https://github.com/outrightmental/ConversationSimulator/issues)
are open to everyone. Beta builds include a one-click, fully-redacted
diagnostic report — nothing is ever uploaded automatically.
