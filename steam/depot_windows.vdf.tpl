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

    // Register the Steam InstallScript that bootstraps the WebView2 Evergreen
    // Runtime on first launch (see steam/installscript.vdf and issue #408).
    // Shipping installscript.vdf as depot content is NOT enough: the Steam
    // client only executes it when the depot build config marks the file with
    // the "InstallScript" key. Path is relative to ContentRoot — the file lands
    // at the depot root next to ConversationSimulator.exe. Without this line the
    // WebView2 runtime is never installed and the app fails to launch on a clean
    // Windows 10 machine (portable depot cannot run the NSIS bootstrapper).
    "InstallScript" "installscript.vdf"

    // Exclude debug symbols — not useful to players.
    "FileExclusion" "*.pdb"

    // Exclude model weight files. Model weights must never appear in any
    // Steam depot — see risk MD-04 in
    // publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md and the full list of
    // excluded patterns in publishing/STEAM_DEPOT_CONTENTS.md.
    "FileExclusion" "*.gguf"
    "FileExclusion" "*.bin"
    "FileExclusion" "*.safetensors"
    "FileExclusion" "*.pt"
    "FileExclusion" "*.pth"
    "FileExclusion" "*.ckpt"
}
