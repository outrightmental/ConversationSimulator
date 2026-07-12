// SteamPipe app build configuration template.
//
// This is a template file — do not pass it to steamcmd directly.
// The deploy workflow (.github/workflows/steam-deploy.yml) substitutes
// the ${VAR} placeholders using envsubst before invoking steamcmd.
//
// Variables substituted at deploy time:
//   STEAM_APP_ID             — from GitHub repository variable vars.STEAM_APP_ID
//   STEAM_DEPOT_WINDOWS_ID   — from vars.STEAM_DEPOT_WINDOWS_ID
//   STEAM_DEPOT_MACOS_ID     — from vars.STEAM_DEPOT_MACOS_ID
//   STEAM_DEPOT_LINUX_ID     — from vars.STEAM_DEPOT_LINUX_ID
//   STEAM_BUILD_DESCRIPTION  — set by the deploy workflow (tag + date)
//   STEAM_SET_LIVE_BRANCH    — from workflow input; empty = stage only, do not set live
//   GITHUB_WORKSPACE         — set automatically by GitHub Actions
//
// See publishing/STEAM_APP_REGISTRATION.md for depot layout and content rules.
"AppBuild"
{
    "AppID"         "${STEAM_APP_ID}"
    "Desc"          "${STEAM_BUILD_DESCRIPTION}"

    // Preview mode: set to "1" to do a dry run without uploading to Steam.
    // The deploy workflow always sets this to "0" for a real upload.
    "Preview"       "0"

    // Local: path to a local content server; leave empty for normal uploads.
    "Local"         ""

    // SetLive: branch to set live after upload. Empty string = stage only.
    // Use "beta" for Stage 3 private beta; "default" for Stage 4 public release.
    "SetLive"       "${STEAM_SET_LIVE_BRANCH}"

    // ContentRoot is the base directory for relative paths in depot VDFs.
    // Set to the workspace root so depot VDFs can use absolute paths.
    "ContentRoot"   "${GITHUB_WORKSPACE}/"

    // BuildOutput: where steamcmd writes build logs and manifests.
    "BuildOutput"   "${GITHUB_WORKSPACE}/steam-build/output/"

    "Depots"
    {
        // One depot per platform for the BASE ($9.99) app. Depot IDs are assigned
        // by Valve at registration and stored as GitHub repository variables — see
        // publishing/STEAM_APP_REGISTRATION.md.
        //
        // NOTE: premium scenario-pack DLC is NOT built here. Each DLC has its own
        // App ID and content depot, built and uploaded from the PRIVATE repo
        // (ConversationSimulator-DLC) using steam/depot_dlc_scenariopacks.vdf.tpl.
        // Paid content must never be staged into these base depots — see
        // docs/DLC_MODEL.md and publishing/STEAM_DEPOT_CONTENTS.md.
        "${STEAM_DEPOT_WINDOWS_ID}"  "depot_windows.vdf"
        "${STEAM_DEPOT_MACOS_ID}"    "depot_macos.vdf"
        "${STEAM_DEPOT_LINUX_ID}"    "depot_linux.vdf"
    }
}
