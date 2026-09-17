<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Vendored: tauri-plugin-steam-overlay-surface

| | |
|---|---|
| Upstream | <https://github.com/PSG-Team/tauri-steam-overlay-surface> |
| Path | `crates/tauri-plugin-steam-overlay-surface` |
| Version | 0.1.3 (crates.io `tauri-plugin-steam-overlay-surface = "0.1.3"`) |
| Commit | `52071556b15639d3719456691e9e16585307bc01` (2026-08-11) |
| License | MIT — `LICENSE` in this directory; attribution in the repo `NOTICE` |
| Author | PSG Studios (The Private Sector Group, LLC) — built for *Spirefall* |

## What it does

Gives Steam's injected `gameoverlayrenderer64.dll` a swapchain to hook: a
transparent, click-through, borderless child window that exactly covers the
main window and presents empty frames at vsync through wgpu. Steam composites
the overlay, notifications, and toasts into those frames; every pixel Steam
does not touch stays transparent so the WebView2 UI shows through. Also
provides hooked-screenshot capture (`PrintWindow`) so F12 saves a live frame.
See the upstream README for the full technique write-up and the list of
hard-won invariants. Windows-only; every call is a no-op elsewhere.

## Why vendored rather than a crates.io dependency

1. **`panic = "abort"`.** `apps/desktop/src-tauri/Cargo.toml` ships the
   release profile with `panic = "abort"`. wgpu's default uncaptured-error
   handler *panics*, so on a driver quirk the upstream crate would take the
   whole game down instead of just retiring a cosmetic surface. Upstream was
   validated with the default unwinding profile, where the same panic only
   kills the surface thread.
2. **Reviewability.** The crate is young (a handful of commits). Vendoring pins
   the exact code that was reviewed for this integration; bump deliberately.

## Local edits (keep this list current)

Everything not listed here is byte-identical to upstream.

- `src/surface.rs`
  - `LAST_ERROR` + `record_error()`: remember why the surface gave up.
  - `device.on_uncaptured_error(...)`: log wgpu errors instead of panicking
    (see above). The existing consecutive-frame-failure guard still retires a
    surface that cannot present.
- `src/lib.rs`
  - `pub fn surface_error() -> Option<String>`: expose `LAST_ERROR` for the
    app's `steam_overlay_status` command / QA readout.
- `src/snapshot.rs`
  - `SNAPSHOT.lock().unwrap()` → `unwrap_or_else(|e| e.into_inner())`
    (poison-tolerant; a poisoned lock must not abort the app).
- `Cargo.toml`
  - `publish = false`; dropped the upstream `readme`/docs.rs metadata.

## Updating

```sh
git clone https://github.com/PSG-Team/tauri-steam-overlay-surface /tmp/tsos
cp /tmp/tsos/crates/tauri-plugin-steam-overlay-surface/src/*.rs src/
# re-apply the edits above, update the commit/version in this file,
# then verify on a real Steam-launched Windows build (docs/STEAM_INTEGRATION.md).
```
