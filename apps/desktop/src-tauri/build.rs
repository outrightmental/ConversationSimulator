// SPDX-License-Identifier: Apache-2.0

/// The model registry, relative to this crate: `apps/desktop/src-tauri` → repo root.
const MODEL_REGISTRY_REL: &str = "../../../model-registry/registry.yaml";

/// Refuse a `CONVSIM_DEMO_MODEL_ID` that names nothing the demo could install.
///
/// The shape check above only proves the value *could* be a registry id.
/// `qwen3-1.7b-instruct-q8-0` (hyphen for the underscore) is perfectly shaped
/// and is in no registry, and at run time that costs nothing visible:
/// `edition.resolve_demo_model_id` logs an error and falls back to
/// `role: starter`. The build succeeds, the demo ships, and the store copy
/// quotes a download size for a model nobody gets — the exact silent swap the
/// release.yml gate exists to prevent.
///
/// release.yml runs these same two checks on its `demo_model_id` input, and
/// keeps doing so: there it fails in Validate, before three platform builds
/// spin up. But only a CI dispatch goes through release.yml, and
/// `apps/desktop/README.md` documents setting this variable on a local
/// `tauri build` — the one place that covers *every* demo build is here.
///
/// Scanned line by line rather than parsed: build.rs has no YAML dependency,
/// and every entry is a `  - id: <id>` line followed by its `    role:` —
/// exactly how the workflow matches it. A registry we cannot read (a build
/// from outside a full checkout) warns rather than failing the build; the
/// shape check still applies.
fn check_demo_model_is_installable(id: &str) {
    println!("cargo:rerun-if-changed={MODEL_REGISTRY_REL}");
    let registry = match std::fs::read_to_string(MODEL_REGISTRY_REL) {
        Ok(text) => text,
        Err(err) => {
            println!(
                "cargo:warning=CONVSIM_DEMO_MODEL_ID={id} could not be checked against \
                 {MODEL_REGISTRY_REL} ({err}). If it is not a real registry entry the demo \
                 will silently install the starter model instead."
            );
            return;
        }
    };

    let mut ids: Vec<&str> = Vec::new();
    let mut pinned_role: Option<&str> = None;
    let mut in_pinned_entry = false;
    for line in registry.lines() {
        if let Some(entry) = line.strip_prefix("  - id: ") {
            let entry = entry.trim();
            ids.push(entry);
            // Every entry ends where the next one begins, so this both enters
            // the pinned entry and leaves it.
            in_pinned_entry = entry == id;
        } else if in_pinned_entry {
            if let Some(role) = line.strip_prefix("    role: ") {
                pinned_role = Some(role.trim());
                in_pinned_entry = false;
            }
        }
    }

    if !ids.contains(&id) {
        panic!(
            "CONVSIM_DEMO_MODEL_ID={id:?} is not in model-registry/registry.yaml, so the \
             demo would fall back to the starter model at run time. Known ids: {}.",
            ids.join(", ")
        );
    }

    // `user-supplied-gguf` is a registry entry but stands for a file the player
    // brings, so it carries no download URL and no checksum. Pinning the demo
    // to it passes the membership check and then fails every install with "No
    // download URL configured for this model" — a first-run dead end, because
    // the demo offers no other model.
    if pinned_role == Some("user-supplied") {
        panic!(
            "CONVSIM_DEMO_MODEL_ID={id:?} is the user-supplied placeholder \
             (role: user-supplied), which has no download URL or checksum: every demo \
             install would fail with no other model to fall back to. Pick a downloadable \
             tier — see model-registry/README.md."
        );
    }
}

fn main() {
    // Rerun when the DLC App ID registry changes so the build picks up updated
    // pack-id ↔ DLC App ID mappings without requiring a manual `cargo clean`.
    println!("cargo:rerun-if-env-changed=VITE_STEAM_DLC_APP_IDS");

    // Validate the format at build time so a malformed mapping fails loudly
    // rather than silently producing a binary that treats all DLC as not-owned.
    if let Ok(raw) = std::env::var("VITE_STEAM_DLC_APP_IDS") {
        if !raw.is_empty() {
            for entry in raw.split(',') {
                let entry = entry.trim();
                if entry.is_empty() {
                    continue;
                }
                let colon = entry.find(':').unwrap_or(0);
                let pack_id = entry[..colon].trim();
                let app_id_str = entry[colon + 1..].trim();
                if colon == 0 || pack_id.is_empty() || app_id_str.parse::<u32>().is_err() {
                    panic!(
                        "VITE_STEAM_DLC_APP_IDS contains a malformed entry: {:?}\n\
                         Expected format: pack_id:dlc_app_id  \
                         (e.g. official.pack:2123456)\n\
                         Full value: {}",
                        entry, raw
                    );
                }
            }
        }
    }

    // Product edition (issue #495). `lib.rs` bakes CONVSIM_EDITION into the
    // binary with option_env! and hands it to convsim-core at launch. Rerun
    // when it changes so switching between a demo and a full build never
    // reuses a stale object, and reject anything but the two known values so
    // a typo cannot silently produce a full build labelled as a demo.
    println!("cargo:rerun-if-env-changed=CONVSIM_EDITION");
    if let Ok(raw) = std::env::var("CONVSIM_EDITION") {
        // Exact match, no trimming: lib.rs compares option_env!("CONVSIM_EDITION")
        // against "demo" byte for byte, so a padded "demo " (a stray newline in
        // a shell export) must be rejected here rather than quietly compiled
        // as the full app.
        if !raw.is_empty() && raw != "full" && raw != "demo" {
            panic!(
                "CONVSIM_EDITION must be exactly \"full\" or \"demo\" (got {:?}). \
                 See docs/steam-next-fest-demo.md.",
                raw
            );
        }
    }

    // Which model the demo installs (issue #495). The demo edition exposes
    // exactly one registry model; by default that is the registry's
    // `role: starter` entry, and CONVSIM_DEMO_MODEL_ID names another registry
    // id instead — the hook for shipping the demo on the smaller `lightweight`
    // tier once it clears the demo quality gate. A packaged app is launched by
    // Steam with no environment of ours, so the value has to be baked in here
    // for `lib.rs` to hand it to convsim-core.
    println!("cargo:rerun-if-env-changed=CONVSIM_DEMO_MODEL_ID");
    if let Ok(raw) = std::env::var("CONVSIM_DEMO_MODEL_ID") {
        let id = raw.trim();
        if !id.is_empty() {
            // Only the demo reads it. Setting it on a full build would silently
            // do nothing, which is exactly the kind of quiet no-op that ships a
            // demo on the wrong model.
            let edition = std::env::var("CONVSIM_EDITION").unwrap_or_default();
            if edition != "demo" {
                panic!(
                    "CONVSIM_DEMO_MODEL_ID={id:?} is set but CONVSIM_EDITION is not \"demo\" \
                     (got {edition:?}). Only a demo build installs a pinned model. \
                     See docs/steam-next-fest-demo.md."
                );
            }
            // Same shape the registry schema requires of an `id`. A value that
            // cannot be a registry id can only ever log an error at runtime and
            // fall back to the starter — catch the typo at build time instead.
            let is_id_char =
                |c: char| c.is_ascii_lowercase() || c.is_ascii_digit() || matches!(c, '.' | '_' | '-');
            let starts_alnum = id.starts_with(|c: char| c.is_ascii_lowercase() || c.is_ascii_digit());
            if !(starts_alnum && id.chars().all(is_id_char)) {
                panic!(
                    "CONVSIM_DEMO_MODEL_ID={id:?} is not a model-registry id \
                     (lowercase letters, digits, '.', '_' and '-'; must start with a letter \
                     or digit). See model-registry/registry.yaml."
                );
            }
            check_demo_model_is_installable(id);
            println!("cargo:rustc-env=CONVSIM_DEMO_MODEL_ID={id}");
        }
    }

    // Shared data-root key (issue #495). Every edition keys its per-user data
    // directory to the FULL app's bundle identifier so the demo and the full
    // app share models, sessions and the logbook. Read it from tauri.conf.json
    // here — the base config; the demo's overlay is applied by the Tauri CLI
    // at build time, never to this file — so the value lib.rs uses can never
    // drift from the identifier the full app actually installs under.
    println!("cargo:rerun-if-changed=tauri.conf.json");
    let conf = std::fs::read_to_string("tauri.conf.json")
        .expect("tauri.conf.json must be readable next to build.rs");
    let conf: serde_json::Value =
        serde_json::from_str(&conf).expect("tauri.conf.json must be valid JSON");
    let identifier = conf
        .get("identifier")
        .and_then(|v| v.as_str())
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .expect("tauri.conf.json must set a non-empty `identifier`");
    println!("cargo:rustc-env=CONVSIM_DATA_ROOT_IDENTIFIER={identifier}");

    tauri_build::build()
}
