// SteamPipe depot build configuration — macOS (Apple Silicon + Intel).
//
// Template file. Substituted by the deploy workflow before steamcmd is invoked.
// Variables: STEAM_DEPOT_MACOS_ID, GITHUB_WORKSPACE.
//
// Content: the Tauri .app bundle for macOS, targeting Apple Silicon (arm64)
// and Intel (x86-64). A universal binary is preferred; separate slices are
// acceptable if a universal build is not yet available.
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
