// SteamPipe depot build configuration — premium DLC scenario pack.
//
// Template file. Substituted by the DLC deploy workflow before steamcmd is
// invoked. Variables: STEAM_DLC_DEPOT_ID, GITHUB_WORKSPACE, STEAM_DLC_PACK_ID.
//
// Content: the YAML scenario files and assets for one premium DLC pack.
// The pack content is sourced from the private ConversationSimulator-DLC repo.
// Do NOT include engine binaries, model weights, or base-app content here.
//
// The DLC deploy workflow places pack content at:
//   ${GITHUB_WORKSPACE}/steam-content/dlc/${STEAM_DLC_PACK_ID}/
"DepotBuild"
{
    "DepotID"       "${STEAM_DLC_DEPOT_ID}"

    "ContentRoot"   "${GITHUB_WORKSPACE}/steam-content/dlc/${STEAM_DLC_PACK_ID}/"

    "FileMapping"
    {
        "LocalPath"     "*"
        "DepotPath"     "."
        "Recursive"     "1"
    }

    // Model weight files must never appear in any depot.
    // See risk MD-04 in publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md.
    "FileExclusion" "*.gguf"
    "FileExclusion" "*.bin"
    "FileExclusion" "*.safetensors"
    "FileExclusion" "*.pt"
    "FileExclusion" "*.pth"
    "FileExclusion" "*.ckpt"

    // Exclude debug artefacts.
    "FileExclusion" "*.pdb"
    "FileExclusion" "*.dSYM"

    // Exclude source-control metadata.
    "FileExclusion" ".git*"
    "FileExclusion" ".github*"
}
