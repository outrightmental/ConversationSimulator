// SteamPipe depot build configuration — Windows x86-64.
//
// Template file. Substituted by the deploy workflow before steamcmd is invoked.
// Variables: STEAM_DEPOT_WINDOWS_ID, GITHUB_WORKSPACE.
//
// Content: the Tauri application directory for Windows x86-64.
// Do NOT include the NSIS installer (.exe setup) here — Steam's own depot
// mechanism handles installation. Upload the raw application binary and
// its resources from the Tauri build output.
//
// The deploy workflow places Windows content at:
//   ${GITHUB_WORKSPACE}/steam-content/windows/
"DepotBuild"
{
    "DepotID"       "${STEAM_DEPOT_WINDOWS_ID}"

    "ContentRoot"   "${GITHUB_WORKSPACE}/steam-content/windows/"

    "FileMapping"
    {
        "LocalPath"     "*"
        "DepotPath"     "."
        "Recursive"     "1"
    }

    // Exclude debug symbols — not useful to players.
    "FileExclusion" "*.pdb"

    // Exclude model weight files. Model weights must never appear in any
    // Steam depot — see risk MD-04 in
    // publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md.
    "FileExclusion" "*.gguf"
    "FileExclusion" "*.bin"
    "FileExclusion" "*.safetensors"
}
