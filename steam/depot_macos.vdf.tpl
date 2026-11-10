// SteamPipe depot build configuration — macOS (Apple Silicon only).
//
// Template file. Substituted by the deploy workflow before steamcmd is invoked.
// Variables: STEAM_DEPOT_MACOS_ID, GITHUB_WORKSPACE.
//
// Content: the Tauri .app bundle for macOS, built for Apple Silicon (arm64)
// only. release.yml has one macOS leg, macOS-aarch64 on macos-latest; there is
// no x86-64 or universal build, so an Intel Mac cannot run what this depot
// carries (issue #563). Adding Intel means a second macOS build leg, its own
// frozen convsim-core sidecar and notarisation, and a universal merge before
// staging; until then the store page, the QA matrix and this comment say
// Apple Silicon only, and tests/acceptance/test_macos_architecture.py fails if
// any of them claims otherwise.
//
// The build must be notarised with an Apple Developer ID certificate before
// this depot is submitted for Stage 3 (private beta) or Stage 4 (public
// release) — see gate G3-01 in docs/steam-mvp-scope.md.
//
// The deploy workflow places macOS content at:
//   ${GITHUB_WORKSPACE}/steam-content/macos/
"DepotBuild"
{
    "DepotID"       "${STEAM_DEPOT_MACOS_ID}"

    "ContentRoot"   "${GITHUB_WORKSPACE}/steam-content/macos/"

    "FileMapping"
    {
        "LocalPath"     "*"
        "DepotPath"     "."
        "Recursive"     "1"
    }

    // Exclude debug symbol bundles. A .dSYM is a directory bundle, so the
    // pattern must match the files inside it — SteamPipe FileExclusion is
    // matched per file path, not against directory entries.
    "FileExclusion" "*.dSYM/*"

    // Exclude model weight files — see risk MD-04 in
    // publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md and the full list of
    // excluded patterns in publishing/STEAM_DEPOT_CONTENTS.md.
    "FileExclusion" "*.gguf"
    "FileExclusion" "*.bin"
    "FileExclusion" "*.safetensors"
    "FileExclusion" "*.pt"
    "FileExclusion" "*.pth"
    "FileExclusion" "*.ckpt"
}
