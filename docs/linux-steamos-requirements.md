<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Linux and SteamOS system requirements

This document records the runtime library assumptions, GLibC version requirements,
fallback guidance, and the minimum and recommended system requirements for the
Conversation Simulator Linux depot on Steam.

---

## Installer formats

Two Linux artifacts are produced by the CI release build:

| Format | File | Use case |
|--------|------|----------|
| **AppImage** | `ConversationSimulator_<ver>_amd64.AppImage` | Portable — runs on any compatible x86_64 Linux without installation. Recommended for Steam Deck and Flatpak-style installs. |
| **Debian package** | `conversation-simulator_<ver>_amd64.deb` | Ubuntu 22.04+ and Debian 12+. Installs to `/usr/bin/` with system-managed runtime dependencies. |

The Steam depot ships the AppImage as the primary artifact. The `.deb` is
available as a GitHub release asset for users who prefer system packages.

---

## GLibC version requirements

The C standard library (glibc) is the one shared library that is **not
bundled** inside the AppImage — it must be present on the target system at a
version equal to or newer than what was used on the build machine.

| Artifact | Build machine | Minimum glibc on target |
|----------|--------------|------------------------|
| AppImage | Ubuntu 22.04 LTS (CI runner) | **≥ 2.35** |
| `.deb` | Ubuntu 22.04 LTS (CI runner) | **≥ 2.35** |

### Distribution compatibility (AppImage)

| Distribution | Shipped glibc | Compatible |
|-------------|--------------|------------|
| Ubuntu 22.04 LTS | 2.35 | Yes (exact match) |
| Ubuntu 24.04 LTS | 2.39 | Yes |
| Debian 12 (Bookworm) | 2.36 | Yes |
| Fedora 38+ | 2.37 | Yes |
| Arch Linux (rolling) | 2.38+ | Yes |
| **SteamOS 3.x** (Arch-based) | 2.37+ | **Yes** |
| Ubuntu 20.04 LTS | 2.31 | **No** — upgrade required |
| Debian 11 (Bullseye) | 2.31 | **No** — upgrade required |

> **Rationale:** Ubuntu 22.04 LTS is the minimum supported distribution because
> the Tauri 2 WebKitGTK 4.1 binding (`libwebkit2gtk-4.1`) is not packaged in
> Ubuntu 20.04 or Debian 11 repositories. Extending support to older releases
> would require a custom build toolchain (e.g. a Docker image based on Debian
> 11 with backported WebKitGTK) — deferred to a post-launch milestone if
> demand warrants it.

---

## Runtime library requirements

### AppImage

The AppImage bundles most user-space dependencies, including:

- **WebKitGTK 4.1** (`libwebkit2gtk-4.1.so`) — web view engine
- **GTK 3** (`libgtk-3.so`) — window chrome
- **libayatana-appindicator3** — system tray icon support
- **librsvg2** — SVG icon rendering
- **glib2, gio, gobject** — GLib base libraries

The AppImage does **not** bundle:

- glibc / libgcc (must be ≥ 2.35 on host)
- libX11 / libXext / libXrender / libXcursor (X11 display server, or Wayland
  via XWayland) — must be present on host
- FUSE 2 (`libfuse.so.2`) — required to mount the AppImage at runtime

> **FUSE note:** On systems where FUSE 2 is not available (e.g. Ubuntu 22.04
> ships FUSE 3 by default), run the AppImage with `--appimage-extract-and-run`
> to bypass FUSE mounting and extract to a temporary directory instead:
> ```bash
> ./ConversationSimulator.AppImage --appimage-extract-and-run
> ```
> Alternatively, install FUSE 2: `sudo apt-get install libfuse2`

### Debian package (.deb)

The `.deb` declares the following `Depends:` entries (set by the Tauri bundler):

```
libwebkit2gtk-4.1-0, libgtk-3-0, libayatana-appindicator3-1, librsvg2-2
```

Install these on Ubuntu 22.04 before installing the `.deb`:

```bash
sudo apt-get install -y \
  libwebkit2gtk-4.1-0 \
  libgtk-3-0 \
  libayatana-appindicator3-1 \
  librsvg2-2
```

### Microphone (voice input)

Voice input requires `xdg-desktop-portal` and a running PipeWire or PulseAudio
session. On headless or minimal desktop environments, microphone access may
silently fail; text-only input mode works without audio hardware.

```bash
# Install xdg-desktop-portal on Ubuntu
sudo apt-get install -y xdg-desktop-portal xdg-desktop-portal-gtk
```

---

## SteamOS 3.x / Steam Deck

SteamOS 3.x is based on Arch Linux and ships with glibc 2.37+, satisfying the
≥ 2.35 requirement. The AppImage runs without modification.

### Steam Deck hardware profile

| Component | Spec |
|-----------|------|
| CPU | AMD Zen 2, 4-core / 8-thread, 2.4–3.5 GHz |
| RAM | 16 GB LPDDR5 (shared with GPU) |
| GPU | AMD RDNA 2, 8 CUs, 1.0–1.6 GHz |
| VRAM | Shared from RAM pool (1–8 GB configurable) |
| Storage | 64 GB eMMC / 256 GB NVMe / 512 GB NVMe |
| Screen | 1280×800 (LCD model) / 1280×800 OLED |
| Input | Gamepad buttons, dual trackpads, gyro, touchscreen |

### Installation on Steam Deck

Via the Steam library (after depot upload):

1. Install from the Steam library entry — no terminal required.
2. On first launch the Model Manager wizard appears — download the recommended
   starter model (Qwen3 4B Q4_K_M, ≈ 2.6 GB).

Manual AppImage install for testing (Desktop Mode):

```bash
# In Desktop Mode, open Konsole:
chmod +x ConversationSimulator_*.AppImage
./ConversationSimulator_*.AppImage
```

To add as a non-Steam game for Gaming Mode launch:

1. Open Steam in Desktop Mode → **Add a game** → **Add a Non-Steam Game**.
2. Browse to the AppImage and select it.
3. Set Launch Options: *(empty for default)*
4. Switch to Gaming Mode and launch from the library.

### Steam Deck verification checklist

Complete all items on a physical Steam Deck running SteamOS 3.x in Gaming Mode
before the Stage 4 gate (G4-02) can be declared PASS. This checklist extends
the general QA matrix in `docs/QA_STEAM_PLATFORM_MATRIX.md`.

- [ ] App launches in Gaming Mode from the Steam library without extra setup.
- [ ] Home screen, scenario picker, and Model Manager are fully navigable with
      the controller alone (D-pad, A/B/X/Y, left stick, right trackpad).
- [ ] On-screen keyboard appears automatically when any text input field is
      focused.
- [ ] All text is readable at 1280×800 without zooming or horizontal scrolling.
- [ ] No required action is hidden behind a mouse-only hover state.
- [ ] Offline smoke test passes under SteamOS 3.x (no outbound network during
      play).
- [ ] Steam overlay (Shift+Tab) opens and closes without breaking the current
      session.
- [ ] Push-to-talk key (if using voice) does not conflict with the Steam overlay
      binding.
- [ ] Battery draw during a text session is documented (target: < 15 W average).
- [ ] App exits cleanly and returns to the Steam library home screen.

### Performance expectations on Steam Deck (Starter tier)

| Metric | Target |
|--------|--------|
| App cold-start to home screen | ≤ 10 s |
| Model load (Qwen3 4B Q4_K_M, first load) | ≤ 90 s |
| First-token latency during text session | ≤ 30 s |
| Battery draw during text session | < 15 W average |

> The Steam Deck GPU can run the Qwen3 4B Q4_K_M model with partial GPU
> offload. Set the number of GPU layers in the Model Manager settings to
> maximise performance. CPU-only inference is slower but fully functional.

---

## Minimum and recommended system requirements (Steam store page)

These are the values for the Linux section of the Steam store page.

### Minimum

| | |
|--|--|
| **OS** | Ubuntu 22.04 LTS or equivalent (glibc 2.35+, x86-64) |
| **Processor** | 64-bit x86 processor, 4 cores, 2.0 GHz |
| **Memory** | 8 GB RAM |
| **Graphics** | Any GPU or CPU with integrated graphics |
| **Storage** | 2 GB available (app) + 3–6 GB for a starter model |
| **Additional notes** | Text-only play mode; voice input requires PipeWire or PulseAudio. |

### Recommended

| | |
|--|--|
| **OS** | Ubuntu 22.04 LTS / Ubuntu 24.04 LTS / SteamOS 3.x (x86-64) |
| **Processor** | 64-bit x86 processor, 6+ cores, 3.0 GHz |
| **Memory** | 16 GB RAM |
| **Graphics** | GPU with 4 GB VRAM (NVIDIA RTX 2060 / AMD RX 6600 or better) |
| **Storage** | 2 GB available (app) + 6–10 GB for recommended models |
| **Additional notes** | GPU acceleration significantly reduces inference latency. Microphone recommended for voice input mode. |

### Steam Deck

| | |
|--|--|
| **Compatibility** | Steam Deck Verified (target; requires Valve review) |
| **Notes** | All official packs playable in text-only mode. Voice input available in Desktop Mode via microphone dongle. |

---

## Fallback guidance for older distributions

If a player's system does not meet the glibc 2.35 minimum:

1. **Upgrade the distribution.** Ubuntu 22.04 LTS has free upgrade paths from
   20.04 via `do-release-upgrade`.

2. **Run in a container.** A Podman or Docker container based on Ubuntu 22.04
   can host the AppImage with full library access. This is a developer option,
   not a supported player workflow.

3. **Build from source.** Players comfortable with Rust/Node/Python toolchains
   can build directly from the GitHub repository on their own distro. See
   `docs/platform-notes.md` and `scripts/setup.sh`.

Conversation Simulator does not ship a "legacy" build targeting older
distributions in v1. If demand for older glibc compatibility is confirmed
post-launch, a Debian 11 / Ubuntu 20.04 compatible build can be explored as a
Stage 5 follow-on using an older build toolchain (linuxdeploy / appimagetool
with glibc 2.31 base image).

---

## References

- [platform-notes.md](platform-notes.md) — Linux build prerequisites and dev environment
- [QA_STEAM_PLATFORM_MATRIX.md](QA_STEAM_PLATFORM_MATRIX.md) — full manual and automated QA test matrix
- [release-checklist.md](release-checklist.md) — release smoke steps and CI gate list
- [publishing/STEAM_DEPOT_CONTENTS.md](../publishing/STEAM_DEPOT_CONTENTS.md) — depot content policy
- `scripts/build-linux.sh` — local Linux build command
- `scripts/depot-audit.sh` — pre-upload depot content audit
