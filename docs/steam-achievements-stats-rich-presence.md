<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam Achievements, Stats, and Rich Presence

> **Roadmap item 48.** This document is the Steamworks configuration companion
> to the implementation in `apps/desktop/src-tauri/src/steam.rs` and the
> `useSteamAchievements` / `useSteamRichPresence` React hooks.
>
> Privacy guarantee: **no conversation content, transcript text, or session
> details are ever sent to Steam.** Only aggregate integer counts and generic
> activity tokens are transmitted — and only when the Steamworks SDK is active
> and the player is running inside Steam.

---

## Achievements

Configure these in the **Steamworks App Admin → Achievements** tab.

| Display name | API name | Unlock condition |
|---|---|---|
| First Scenario | `ACH_FIRST_SCENARIO` | Player completes their first conversation scenario (session ends normally or is manually ended). |
| First Debrief | `ACH_FIRST_DEBRIEF` | Player views their first generated debrief screen. |
| Practice Streak | `ACH_PRACTICE_STREAK` | Player completes scenarios on three or more consecutive calendar days. |
| Pack Explorer | `ACH_PACK_EXPLORER` | Player plays a scenario from at least three different packs. |
| Creator First Validate | `ACH_CREATOR_FIRST_VALIDATE` | Player successfully validates their first custom scenario pack in the creator workbench. |

### Steamworks settings for each achievement

- **Hidden:** set to `true` for `ACH_PRACTICE_STREAK` and `ACH_PACK_EXPLORER`
  (reveal on unlock so players discover them organically).
- **Global unlock percentage:** visible; Valve computes this automatically.
- **Icon:** 64×64 px and 32×32 px locked/unlocked pairs required. See
  `publishing/STEAM_ASSETS_SPEC.md` for the art spec.

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
| Packs Validated | `STAT_PACKS_VALIDATED` | Creator workbench reports a successful `validate-pack` run. |
| Text Mode Sessions | `STAT_TEXT_MODE_SESSIONS` | Session starts in text input mode. |
| Voice Mode Sessions | `STAT_VOICE_MODE_SESSIONS` | Session starts in voice input mode. |

### Privacy constraint

Stats store **only counts** — no content. A stat value of `7` means "7
scenarios completed"; it reveals nothing about which scenarios, what was said,
or who the NPCs were. This matches the project's local-first, no-telemetry
commitment and the requirement stated in `docs/steam-mvp-scope.md`.

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

The Tauri commands (`steam_unlock_achievement`, `steam_increment_stat`,
`steam_set_rich_presence`) can be invoked freely on any build; callers do not
need to check `SteamStatus.is_steam_enabled` first.

---

## Steamworks configuration checklist

Use this checklist before the Stage 4 gate (public Steam release):

- [ ] All five achievements created in App Admin with correct API names.
- [ ] Locked and unlocked icons uploaded for all five achievements.
- [ ] Hidden flag set for `ACH_PRACTICE_STREAK` and `ACH_PACK_EXPLORER`.
- [ ] All five stats created in App Admin as INT type.
- [ ] Rich presence localization file uploaded for English.
- [ ] Rich presence localization files uploaded for any additional launch
      languages.
- [ ] End-to-end test: run with `SteamAppId=480 cargo tauri dev --features steam`,
      trigger each unlock event, confirm the Steam overlay shows the achievement
      notification and the stats increment.
- [ ] Confirm no session content appears in any Steam-facing string.
