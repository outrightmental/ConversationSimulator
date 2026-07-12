// SteamPipe depot build configuration — premium scenario-pack DLC.
//
// TEMPLATE / CONTRACT FILE.
// This template lives in the PUBLIC repo to define the canonical shape of a
// premium-DLC content depot. It is NOT built from the public repo: premium pack
// content is authored and uploaded from the PRIVATE repo
// (ConversationSimulator-DLC) — see docs/DLC_MODEL.md.
//
// Each premium expansion pack is its own Steam DLC (its own DLC App ID) with its
// own content depot. The private repo's dlc-steam-deploy.yml substitutes the
// ${VAR} placeholders (per DLC) and invokes steamcmd.
//
// Variables substituted at deploy time (in the PRIVATE repo's workflow):
//   STEAM_DLC_DEPOT_ID   — content depot ID assigned by Valve for this DLC
//   DLC_CONTENT_ROOT     — path to the built pack content for this DLC
//                          (e.g. ${GITHUB_WORKSPACE}/dlc-content/<pack_id>/)
//
// Why a SEPARATE depot (not the base app's depots):
//   Premium pack content must NOT ship inside the base game's depots. If it did,
//   every player would download paid content (merely locked at runtime), and the
//   content could leak. A separate DLC depot downloads only for owners, keeping
//   paid content out of both the base depots and this public repository.
"DepotBuild"
{
    "DepotID"       "${STEAM_DLC_DEPOT_ID}"

    // Root of the built premium-pack content for THIS DLC. Supplied by the
    // private repo's build step — never a path inside this public repo.
    "ContentRoot"   "${DLC_CONTENT_ROOT}"

    "FileMapping"
    {
        "LocalPath"     "*"
        "DepotPath"     "."
        "Recursive"     "1"
    }

    // Packs are declarative YAML + static assets only. Exclude anything that
    // should never be in any depot — mirrors the base depot exclusions.
    "FileExclusion" "*.pdb"
    "FileExclusion" "*.gguf"
    "FileExclusion" "*.bin"
    "FileExclusion" "*.safetensors"
    "FileExclusion" "*.pt"
    "FileExclusion" "*.pth"
    "FileExclusion" "*.ckpt"
}
