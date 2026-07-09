// SteamPipe depot build configuration — Linux x86-64 / SteamOS.
//
// Template file. Substituted by the deploy workflow before steamcmd is invoked.
// Variables: STEAM_DEPOT_LINUX_ID, GITHUB_WORKSPACE.
//
// Content: the Tauri application binary and resources for Linux x86-64.
// This depot covers both standard Linux (glibc, tested on Ubuntu 22.04 and
// Fedora 40) and Steam Deck (SteamOS 3.x, x86-64).
//
// Steam Deck Verified tier requires passing the verification checklist in
// docs/STEAM_ROADMAP.md before the public release gate (Stage 4) opens.
//
// The deploy workflow places Linux content at:
//   ${GITHUB_WORKSPACE}/steam-content/linux/
"DepotBuild"
{
    "DepotID"       "${STEAM_DEPOT_LINUX_ID}"

    "ContentRoot"   "${GITHUB_WORKSPACE}/steam-content/linux/"

    "FileMapping"
    {
        "LocalPath"     "*"
        "DepotPath"     "."
        "Recursive"     "1"
    }

    // Exclude model weight files — see risk MD-04 in
    // publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md.
    "FileExclusion" "*.gguf"
    "FileExclusion" "*.bin"
    "FileExclusion" "*.safetensors"
}
