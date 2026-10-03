---
title: "Steam achievements & rich presence"
description: "Steamworks configuration for Conversation Simulator's achievements, stats, and rich presence, with the privacy constraints that keep conversation content off Steam."
sidebar:
  order: 33
---

> **Roadmap item 48.** This document is the Steamworks configuration companion
> to the implementation in [`apps/desktop/src-tauri/src/steam.rs`](https://github.com/outrightmental/ConversationSimulator/blob/main/apps/desktop/src-tauri/src/steam.rs) and the
> `useSteamAchievements` / `useSteamRichPresence` React hooks.
>
> Privacy guarantee: **no conversation content, transcript text, or session
> details are ever sent to Steam.** Only aggregate integer counts and generic
> activity tokens are transmitted — and only when the Steamworks SDK is active
> and the player is running inside Steam.

---

## Achievements

Configure these in the **Steamworks App Admin → Achievements** tab.

The set is designed as a guided tour of the whole product (issue #494): a player
holding all of them has exercised onboarding, both input modes, the whole
microphone pipeline, the debrief and logbook loop, the scenario library, every
privacy control, and the creator workbench. `ACH_CERTIFIED_EXPERT` is the
capstone that confirms it.

`apps/web/src/hooks/useSteamAchievements.ts` (`SteamAchievement`) and
`apps/desktop/src-tauri/src/steam.rs` (`achievements`) carry the same API names;
a test asserts all three lists — including this table — stay in step.

**API names are a shipped contract.** Steam keys a player's unlocked
achievements by API name, so renaming one silently discards their progress. Add
names; never rename or reuse one. The five marked **v1** shipped first (issue
#230) and are frozen.

### Onboarding, models, runtime, and support

| Display name | API name | Unlock condition | Hidden |
|---|---|---|---|
| Ready to Practice | `ACH_SETUP_COMPLETE` | Setup is confirmed complete with a working model — at the end of the first-run wizard, or on any later launch for a player who finished onboarding earlier. | No |
| Bring Your Own Model | `ACH_BYO_MODEL` | Player points the app at their own engine: an Ollama model or a local `.gguf` file, from the wizard or the model manager. | No |
| Know Your Hardware | `ACH_BENCHMARKED` | A model benchmark run completes. | No |
| Under the Hood | `ACH_RUNTIME_TUNED` | Player applies runtime settings (basic or advanced) in Settings. | No |
| All Systems Go | `ACH_SELF_TEST` | Player runs the system self-test / preflight from Settings or Support. | No |
| Bug Hunter | `ACH_DIAGNOSTICS` | Player generates a diagnostics bundle or a beta report bundle from Support. | Yes |

### Conversation: text, voice, and the microphone pipeline

| Display name | API name | Unlock condition | Hidden |
|---|---|---|---|
| First Scenario **(v1)** | `ACH_FIRST_SCENARIO` | Player completes their first conversation scenario (session ends normally or is manually ended). | No |
| Typed Word | `ACH_TEXT_TURN` | Player submits a turn by typing it. | No |
| Out Loud | `ACH_VOICE_TURN` | Player confirms a spoken turn — the microphone captured speech and STT returned a transcript. | No |
| Hands Free | `ACH_HANDS_FREE` | Player confirms a spoken turn while the voice input is in hands-free (VAD) mode rather than push-to-talk. | No |
| Calibrated | `ACH_VAD_CALIBRATED` | Microphone VAD calibration completes successfully. | No |
| Interrupter | `ACH_BARGE_IN` | Player speaks over the NPC while its reply is still being spoken. | Yes |
| Second Draft | `ACH_TRANSCRIPT_EDITED` | Player edits an STT transcript in the review panel before sending it. | Yes |
| Going Deep | `ACH_DEEP_CONVERSATION` | Player takes 12 of their own turns within a single conversation. | No |
| Sound Designer | `ACH_VOICE_TUNED` | Player changes a voice setting: preferred voice, thinking pause, backchannel, or barge-in. | No |

### Debrief, transcripts, logbook, and relationship memory

| Display name | API name | Unlock condition | Hidden |
|---|---|---|---|
| First Debrief **(v1)** | `ACH_FIRST_DEBRIEF` | Player views their first generated debrief screen. | No |
| Turning Point | `ACH_TURNING_POINT` | Player jumps from a debrief turning-point card into the transcript it refers to. | Yes |
| Paper Trail | `ACH_TRANSCRIPT_EXPORT` | Player exports a transcript (JSON or plain text) from the debrief or from Settings. | No |
| Take Two | `ACH_REPLAY_VARIATION` | Player replays the scenario they just finished from the debrief, to run it with a different difficulty, language, or input mode. | No |
| Practice Streak **(v1)** | `ACH_PRACTICE_STREAK` | Player completes scenarios on three or more consecutive calendar days. | Yes |
| Seasoned | `ACH_TEN_SCENARIOS` | Player's logbook records ten or more completed sessions. | No |
| Personal Best | `ACH_PERSONAL_BEST` | Player's logbook records at least one personal best score. | Yes |
| Take It With You | `ACH_LOGBOOK_EXPORT` | Player exports their logbook. | No |
| They Remember You | `ACH_RELATIONSHIP_MEMORY` | An NPC relationship recap exists — an NPC has remembered the player across sessions. | Yes |

### Scenario library and pack management

| Display name | API name | Unlock condition | Hidden |
|---|---|---|---|
| Pack Explorer **(v1)** | `ACH_PACK_EXPLORER` | Player plays a scenario from at least three different packs. | Yes |
| Pack Connoisseur | `ACH_PACK_CONNOISSEUR` | Player plays a scenario from at least five different packs. Reachable on the base game alone — it ships six packs. | Yes |
| Curator | `ACH_LIBRARY_CURATOR` | Player narrows the scenario library with the search box or any facet filter. | No |
| Custom Content | `ACH_PACK_IMPORTED` | Player imports a scenario pack archive, from the library, Settings, or the workbench. | No |
| Factory Reset | `ACH_PACKS_RESTORED` | Player restores the official packs from the library or the workbench. | Yes |

### Privacy controls and personalisation

| Display name | API name | Unlock condition | Hidden |
|---|---|---|---|
| Your Data, Your Rules | `ACH_PRIVACY_TUNED` | Player changes a privacy toggle: save transcripts, save TTS cache, or save raw audio. | No |
| Clean Slate | `ACH_MEMORY_FORGOTTEN` | Player deletes a relationship recap, or clears all of them. | Yes |
| Polyglot | `ACH_POLYGLOT` | Player switches the interface to a different language. | No |
| Peek Behind the Curtain | `ACH_DEV_MODE` | Player turns developer mode on. | Yes |

### Creator workbench

| Display name | API name | Unlock condition | Hidden |
|---|---|---|---|
| Creator First Validate **(v1)** | `ACH_CREATOR_FIRST_VALIDATE` | One of the player's own editable packs validates cleanly in the creator workbench. Official read-only packs do not count. | No |
| Fork It | `ACH_CREATOR_FORK` | Player copies an official pack into their own editable local-dev copy. | No |
| Author | `ACH_CREATOR_SAVE` | Player saves an edit to a pack file in the workbench. | No |
| Dry Run | `ACH_CREATOR_TEST` | Player starts a test conversation against a pack in the workbench. | No |
| Ship It | `ACH_CREATOR_EXPORT` | Player exports one of their packs as a distributable archive. | No |

### Steam platform surfaces

These depend on optional content or optional hardware, so none of them is
required for the capstone (see below).

| Display name | API name | Unlock condition | Hidden |
|---|---|---|---|
| Subscriber | `ACH_WORKSHOP_SUBSCRIBER` | A subscribed Steam Workshop pack is present in the player's library. | No |
| Publisher | `ACH_WORKSHOP_PUBLISHER` | Player publishes one of their packs to the Steam Workshop. | No |
| Collector | `ACH_DLC_LIBRARY` | An installed DLC scenario pack is present in the player's library. | No |
| Couch Practice | `ACH_BIG_PICTURE` | Player drives the interface with a game controller (Steam Deck or Big Picture). | Yes |

### Capstone

| Display name | API name | Unlock condition | Hidden |
|---|---|---|---|
| Certified Expert | `ACH_CERTIFIED_EXPERT` | Every achievement above unlocks, except the four Steam platform surfaces and the two advanced-model ones (`ACH_BYO_MODEL`, `ACH_BENCHMARKED`). | No |

The capstone is unlocked by the front end, not by Steamworks. After every
confirmed unlock, `unlock()` asks Steam — via the `steam_unlocked_achievements`
command — which of the required names plus `ACH_CERTIFIED_EXPERT` the signed-in
account already holds, and fires the capstone when every required name comes
back. `OPTIONAL_ACHIEVEMENTS` in `useSteamAchievements.ts` is the list left out
of the requirement, so that 100% of the base game stays reachable for a player
with no Workshop subscription, no DLC, no controller, and no Ollama or `.gguf`
model of their own. A microphone **is** required — voice practice is the
product, and the store page already lists one as the requirement for voice mode.

**Steam is the only authority here, deliberately.** "Has this player earned
every required achievement?" is a fact about a Steam *account*, so a device-local
record cannot answer it, and an earlier revision that cached confirmed unlocks in
`localStorage` was wrong in both directions. That cache is shared by every Steam
account that plays on one machine and OS login: it handed a second account the
capstone the first account had earned there, and — once it held
`ACH_CERTIFIED_EXPERT` — denied the capstone to any other account on that machine
that genuinely finished the set. It also started empty after a reinstall or an
app-data wipe, stranding a finished player at 42/43 with only one-shot events (a
barge-in, an export, a creator save) left to redo. Do not reintroduce it; asking
Steam costs one IPC hop and a few dozen in-memory lookups per unlock.

The read-back is best-effort in one direction only: Steamworks refuses the read
until the user's stats arrive shortly after launch, and answers nothing at all
outside Steam or with the `steam` feature off. So a name it does not confirm is
treated as *unknown*, never as "not earned" — the capstone simply does not fire
on that pass and is re-evaluated on the next unlock. In a browser or non-Steam
build it therefore never fires, which is the correct no-op.

Including `ACH_CERTIFIED_EXPERT` in the same read-back is also how the re-grant
is skipped once the account already holds it.

Adding an achievement adds it to the capstone requirement by default; a
genuinely optional one must be declared in `OPTIONAL_ACHIEVEMENTS`.

#### Privacy note on the local tally

The only thing kept on disk is `convsim.steam.packsPlayed` — the IDs of the packs
the player has practised with, which drive `ACH_PACK_EXPLORER` and
`ACH_PACK_CONNOISSEUR`. Pack IDs only, on this device only. Nothing in it is sent
anywhere: Steam receives the unlock calls it would have received anyway, plus a
read-back query naming the capstone achievements, which are this repository's own
constants. The pack IDs never leave the device, and neither does a transcript, a
session ID, or any conversation content.

### Retroactive unlocks

Unlocking is idempotent, so call sites re-check their condition on every visit to
the relevant screen. Achievements whose condition is derived from durable state
the app already keeps therefore grant retroactively on the first launch after
this update: `ACH_SETUP_COMPLETE`, `ACH_PRACTICE_STREAK`, `ACH_TEN_SCENARIOS`,
`ACH_PERSONAL_BEST`, `ACH_RELATIONSHIP_MEMORY`, `ACH_WORKSHOP_SUBSCRIBER`,
`ACH_DLC_LIBRARY`, and `ACH_CREATOR_FIRST_VALIDATE` (the workbench re-validates
a pack whenever it is selected). The rest observe an event as it happens and
count from this release forward — including `ACH_PACK_EXPLORER` and
`ACH_PACK_CONNOISSEUR`, whose pack tally starts empty.

### Feature areas with no achievement

Session branching (`POST /sessions/{id}/branch`, `services/branch_service.py`)
is implemented in convsim-core but has no front-end surface at all, so there is
nowhere to put an unlock call. `ACH_REPLAY_VARIATION` covers the player-visible
neighbour — re-running the finished scenario from the debrief with a different
difficulty, language, or input mode — not a true mid-conversation fork. If a
branching UI ships, it earns its own achievement and joins the capstone
requirement by default.

### Steamworks settings for each achievement

- **Hidden:** set per the **Hidden** column in the tables above. Hidden
  achievements are the discovery and completionist ones — they reveal on unlock
  so players find them organically rather than reading them as a to-do list.
- **Global unlock percentage:** visible; Valve computes this automatically.
- **Icon:** 64×64 px and 32×32 px locked/unlocked pairs required. See
  [`publishing/STEAM_ASSETS_SPEC.md`](https://github.com/outrightmental/ConversationSimulator/blob/main/publishing/STEAM_ASSETS_SPEC.md) for the art spec.

### Unlock call site

The front-end calls `useSteamAchievements().unlock(SteamAchievement.<NAME>)` at
the appropriate event boundary. The Tauri command `steam_unlock_achievement`
forwards the call to `steamworks::UserStats::achievement(name).set()` followed
by `store_stats()`. The call is a no-op when Steam is absent.

---

## Stats

Configure these in the **Steamworks App Admin → Stats** tab. All stats are
**INT** type and **monotonically increasing** (never decremented).

| Display name | API name | Increment event |
|---|---|---|
| Scenarios Completed | `STAT_SCENARIOS_COMPLETED` | Session ends (player ends a scenario or it completes naturally). |
| Debriefs Generated | `STAT_DEBRIEFS_GENERATED` | Debrief screen is displayed with generated content. |
| Packs Validated | `STAT_PACKS_VALIDATED` | A player-initiated `validate-pack` run reports a result — a workbench save, or the library's per-pack validate button. The automatic validation on pack selection is not counted, so merely browsing does not inflate it. |
| Text Mode Sessions | `STAT_TEXT_MODE_SESSIONS` | Session starts in text input mode. |
| Voice Mode Sessions | `STAT_VOICE_MODE_SESSIONS` | Session starts in voice input mode. |
| Voice Turns | `STAT_VOICE_TURNS` | Player confirms a spoken turn. |
| Packs Imported | `STAT_PACKS_IMPORTED` | A pack archive import succeeds. |
| Packs Exported | `STAT_PACKS_EXPORTED` | A pack export succeeds. |
| Transcripts Exported | `STAT_TRANSCRIPTS_EXPORTED` | A transcript export (JSON or plain text) succeeds. |

### Privacy constraint

Stats store **only counts** — no content. A stat value of `7` means "7
scenarios completed"; it reveals nothing about which scenarios, what was said,
or who the NPCs were. This matches the project's local-first, no-telemetry
commitment and the requirement stated in
[`docs/steam-mvp-scope.md`](/dev/steam-mvp-scope/).

### Increment call site

The front-end calls
`useSteamAchievements().incrementStat(SteamStat.<NAME>)` at the relevant
event. The Tauri command `steam_increment_stat` reads the current value,
increments by 1, writes it back, and calls `store_stats()`. The call is a
no-op when Steam is absent.

---

## Rich Presence

Configure rich presence localization in the **Steamworks App Admin → Rich
Presence** tab under the app's Steam client localization settings.

The integration uses a single key (`steam_display`) whose value is a
localization token. The tokens and their suggested English display strings are:

| Token | Suggested display string |
|---|---|
| `#InScenario` | `In a practice scenario` |
| `#ReviewingDebrief` | `Reviewing a debrief` |
| `#EditingPack` | `Editing a scenario pack` |
| `#AtMainMenu` | `Browsing scenarios` |

Upload a localization file (`richpresence.vdf`) to the Steamworks portal for
each supported language. Example English file:

```vdf
"lang"
{
    "Language" "english"
    "Tokens"
    {
        "#InScenario"       "In a practice scenario"
        "#ReviewingDebrief" "Reviewing a debrief"
        "#EditingPack"      "Editing a scenario pack"
        "#AtMainMenu"       "Browsing scenarios"
    }
}
```

### Privacy constraint

Tokens reveal **only the category of activity** — never the scenario title,
NPC name, conversation topic, turn count, or any other session detail.

### Set call site

The front-end calls
`useSteamRichPresence().setPresence(SteamActivity.<TOKEN>)` when the player
navigates to a new major screen. The Tauri command `steam_set_rich_presence`
forwards the call to `steamworks::Friends::set_rich_presence(key, value)`.
The call is a no-op when Steam is absent.

Suggested call sites in the React screens:

| Screen | Token to set |
|---|---|
| `screens/Home` / `screens/ScenarioLibrary` | `SteamActivity.AT_MAIN_MENU` |
| `screens/Conversation` | `SteamActivity.IN_SCENARIO` |
| `screens/Debrief` | `SteamActivity.REVIEWING_DEBRIEF` |
| `screens/CreatorWorkbench` | `SteamActivity.EDITING_PACK` |

---

## Graceful fallback outside Steam

All three features (achievements, stats, rich presence) are implemented as
graceful no-ops when:

- The `steam` Cargo feature is disabled (the default; builds without the
  Steamworks SDK).
- The `steam` feature is enabled but `steamworks::Client::init()` fails
  (Steam not running, wrong AppID, or SDK not installed).
- The front-end runs in a browser context (no `window.__TAURI__`).

The `SteamRuntime` struct always exists in managed state; its methods simply
return `false` in all fallback cases without logging errors or throwing.

The Tauri commands (`steam_unlock_achievement`, `steam_unlocked_achievements`,
`steam_increment_stat`, `steam_set_rich_presence`) can be invoked freely on any
build; callers do not need to check `SteamStatus.is_steam_enabled` first.
`steam_unlocked_achievements` answers with an empty list in every fallback case,
which the capstone check reads as "nothing confirmed" rather than "nothing
earned".

---

## Steamworks configuration checklist

Use this checklist before the Stage 4 gate (public Steam release):

- [ ] All 43 achievements created in App Admin with the exact API names from the
      tables above (42 earned in-app, plus the `ACH_CERTIFIED_EXPERT` capstone).
- [ ] Locked and unlocked icons uploaded for all 43 achievements.
- [ ] Hidden flag set for each achievement whose **Hidden** column says `Yes`
      (13 of them).
- [ ] All nine stats created in App Admin as INT type.
- [ ] `ACH_CERTIFIED_EXPERT` reviewed against `OPTIONAL_ACHIEVEMENTS` in
      `apps/web/src/hooks/useSteamAchievements.ts` — nothing that needs Workshop,
      DLC, a controller, or a player-supplied model may be required for it.
- [ ] Rich presence localization file uploaded for English.
- [ ] Rich presence localization files uploaded for any additional launch
      languages.
- [ ] End-to-end test: run with `SteamAppId=480 cargo tauri dev --features steam`,
      trigger each unlock event, confirm the Steam overlay shows the achievement
      notification and the stats increment.
- [ ] Confirm no session content appears in any Steam-facing string.
