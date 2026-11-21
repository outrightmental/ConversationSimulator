<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Social media kit

The images every Conversation Simulator profile should carry. All of them are
the one official icon, `docs/assets/brand/ConversationSimulatorIcon.svg`, and
all of them are generated: edit the source, then re-run
`python3 publishing/assets/source/gen_icons.py`. Never upload any other
Conversation Simulator picture.

| File | Size | Use it for |
|------|------|------------|
| [`avatar.png`](avatar.png) | 1024 × 1024 | Every profile picture and community icon |
| [`banner.png`](banner.png) | 1500 × 500 | Every profile header that is 3:1 |
| [`../../../website/static/images/og-card.png`](../../../website/static/images/og-card.png) | 1200 × 630 | Link previews and the GitHub social preview |

The avatar is the icon square and full bleed. Platforms that crop avatars to a
circle keep all of both bubbles: they sit inside the circle with room to spare.
The banner has no text, because every platform prints the account's name with
it, and the mark is centred because each platform crops a header differently
on phones and lays the avatar over a different corner.

## Where each one goes

Wherever the project has a profile, these replace whatever picture is there now.

| Platform | Profile picture | Header / banner |
|----------|-----------------|-----------------|
| Bluesky | Edit profile → avatar: `avatar.png` | Edit profile → banner: `banner.png` |
| X | Edit profile → photo: `avatar.png` | Edit profile → header: `banner.png` |
| Mastodon | Preferences → Public profile → Avatar: `avatar.png` | Header: `banner.png` |
| Threads, Instagram, TikTok, LinkedIn | Profile photo: `avatar.png` | — |
| Discord | Server Settings → Overview → server icon: `avatar.png` | — |
| Reddit | Mod tools → Community appearance → Avatar: `avatar.png` | — |
| YouTube | Customisation → Branding → Picture: `avatar.png` | — |
| GitHub | Organisation settings → Profile picture: `avatar.png` | Repository settings → Social preview: `og-card.png` |
| Steam | The App Icon, Shortcut Icon and Mac Icon in `publishing/assets/icons/` and `apps/desktop/src-tauri/icons*/`; see `publishing/STEAM_ASSETS_SPEC.md` | The capsules in `publishing/assets/capsules/` |
| Microsoft Store | The package logos in `publishing/microsoft-store/Assets*/` | — |

The demo has no social profiles of its own. Where a demo needs an image (the
Steam demo app, the Microsoft Store demo listing), it is the demo icon, with
the amber DEMO badge, from the same generator.
