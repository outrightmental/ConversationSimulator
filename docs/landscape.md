<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Landscape: where Conversation Simulator sits

This document orients contributors and future maintainers: the sixty-year lineage this
project belongs to, the field it competes in today, and the commercial precedents its
business model is built on. Pair it with [governance.md](governance.md) (how the project
is run) and [ROADMAP.md](../ROADMAP.md) (what is being built).

> **Keep this honest:** revisit at each release train. If a competitor ships something
> that changes the analysis, or a precedent stops being true, update it here.

---

## Sixty years of practicing conversation with machines

People have been rehearsing real feelings on artificial interlocutors since before the
term "chatbot" existed. Conversation Simulator is a deliberate fusion of three older
traditions:

- **1966 — ELIZA** (Joseph Weizenbaum, MIT). A few hundred lines of pattern matching
  playing a Rogerian therapist — and people confided in it anyway. The "ELIZA effect" is
  the founding observation of this entire category: humans readily practice real emotional
  material with a machine, *especially* when no other human is watching.
- **1990 — The Secret of Monkey Island.** Insult sword-fighting made verbal sparring a
  *game mechanic* — exchanges you could win, lose, and get better at. Ritualized verbal
  duels are far older (flyting goes back to Norse and Scots tradition), but this was the
  proof that scored dialogue is genuinely fun. (See the flyting proposal in
  [#454](https://github.com/outrightmental/ConversationSimulator/issues/454).)
- **2005 — Façade** (Michael Mateas & Andrew Stern). The first natural-language
  interactive drama: free-text input steering a live social situation with reactive
  characters and social state. It proved the experience could be compelling — and that
  authoring it by hand was brutally hard. LLMs dissolve exactly the authoring wall Façade
  hit.
- **2010s — the coaching industry moves on-screen.** VR soft-skills trainers and
  chatbot-based coaching brought "practice the hard conversation before you have it" to
  enterprise L&D — cloud-hosted, per-seat, subscription-priced.
- **2022–2026 — the LLM era, split in two.** Cloud AI coaches multiplied (interview
  prep, sales roleplay, speaking coaches). In parallel, the local-model movement —
  llama.cpp, Ollama, LM Studio, Jan, SillyTavern — proved that consumer hardware runs
  capable models with total privacy, and that a large audience will do real setup work to
  get it.

Conversation Simulator's bet is that these strands belong together: **the game structure**
(scenario state, events, scoring, debrief), **the coaching value** (rubrics, progression,
replay), and **the local-first guarantee** (no account, no cloud, no telemetry) — all in
the open, where the community can extend it.

---

## The field today

| Category | Representatives | Delivery | Typical model |
| -------- | --------------- | -------- | ------------- |
| AI communication coaches | Yoodli, Vocal Image, Poised | Cloud SaaS | Subscription; recordings and transcripts processed server-side |
| Enterprise roleplay & VR training | VirtualSpeech, Retorio, Coachello, Bodyswaps | Cloud / VR, B2B | Per-seat licenses; sold to L&D departments, not individuals |
| Interview prep | Google Interview Warmup, Big Interview, assorted "AI interview coach" apps | Cloud | Free-with-account or subscription; single-domain |
| Sales roleplay | Second Nature, Hyperbound | Cloud, B2B | Per-seat; single-domain |
| Language speaking practice | ELSA, BoldVoice, TalkPal, Duolingo roleplay | Cloud, mobile | Subscription; single-domain |
| General chatbots pressed into service | ChatGPT Voice, Pi | Cloud | Freemium; no scenario structure, state, scoring, or packs |
| Local-LLM roleplay frontends | SillyTavern and kin | **Local** | Free/open; entertainment RP — no rubrics, debrief, or curriculum; setup-heavy |

Three observations fall out of that table:

1. **Every direct competitor is cloud-based.** The things people most need to rehearse —
   firing someone, the salary ask, the breakup, the visa interview, the diagnosis
   conversation — are exactly the things they least want on someone else's server.
   Privacy is not a feature checkbox in this category; it is a purchase driver.
2. **The cloud products cannot follow us here.** Local-first is not a feature a SaaS
   coach can patch in; it is the negation of their business model (subscriptions,
   usage-metered inference, data-network effects). The moat is structural.
3. **The local products are not games, and the games are not local.** SillyTavern proves
   local roleplay demand but offers no practice structure; the coaches offer structure but
   no privacy and no play. **No shipping product combines all three: a structured practice
   game, 100% local inference, and open source.** That intersection is this project.

---

## Business-model precedents

"Free and open source on GitHub, fairly priced on Steam, first-party DLC on top" is not an
experiment — it is a pattern with a track record:

- **Dwarf Fortress** — freeware for twenty years (sustained by roughly $15k/month in
  donations), then a paid, packaged Steam edition in December 2022: ~600,000 copies and
  ~$7M in its first two months, past a million copies since. The free version never went
  away — it *built* the audience the paid edition converted. The lesson: packaging,
  onboarding, and platform polish are what people pay for, and the free build does not
  cannibalize the paid one; it is the funnel.
- **Shattered Pixel Dungeon** — GPL-3, source and free builds on GitHub and itch.io, ~$10
  on Steam and mobile stores; that convenience price sustains a full-time maintainer. The
  lesson: even when compiling is trivial, "installed, updated, and supporting the author"
  is a product.
- **Mindustry** — GPL-3, free from source and itch.io, $9.99 on Steam with Workshop
  integration. The lesson: platform integration (Workshop, cloud saves, achievements) is
  legitimate paid value on top of an open core.
- **Aseprite** — source-available; compile it yourself for free or pay ~$20. The lesson:
  a fair price on an open codebase functions as a tip jar with a barcode — buyers are
  funding the roadmap and they know it.

What Conversation Simulator borrows, per
[README → How it's distributed](../README.md#how-its-distributed) and
[DLC_MODEL.md](DLC_MODEL.md): the engine and four official packs are free forever
(Apache-2.0 / CC BY 4.0); the $9.99 Steam edition sells *packaging* — signed, notarized,
auto-updating, Steam Deck–verified — never gated features; premium scenario packs are
additive first-party DLC from a private repo; **nothing that ships free is ever relocked.**

What it refuses: open-core feature hostage-taking, telemetry-funded free tiers, and any
cloud dependency for core play.

---

## What this means for stewardship

1. **The free build is the top of the funnel.** Every minute of friction between
   `git clone` and a first conversation is a revenue problem, not just a DX problem —
   which is why the v0.3 onboarding overhaul
   ([#388](https://github.com/outrightmental/ConversationSimulator/issues/388)) was
   treated as release-gating work.
2. **The Steam page is the cash register.** Deck verification, achievements, store
   assets, and review-response hygiene are product work, not chores
   ([STEAM_ROADMAP.md](STEAM_ROADMAP.md)).
3. **Packs are the content engine.** Creator tooling compounds: community packs grow the
   audience that buys first-party DLC, and the eventual marketplace
   ([marketplace-architecture.md](marketplace-architecture.md),
   [#465](https://github.com/outrightmental/ConversationSimulator/issues/465),
   [#466](https://github.com/outrightmental/ConversationSimulator/issues/466)) turns
   creators into stakeholders.
4. **Trust is the brand.** The local-first promise must remain *auditable* — offline
   smoke tests in CI, no-egress guarantees, reproducible builds where possible. One
   violated promise erases the structural moat.
5. **The public record is the marketing.** The
   [delivery board](https://github.com/orgs/outrightmental/projects/12) shows every issue
   ever shipped, phase by phase — seven weeks from empty repository to signed,
   Steam-ready build. For skeptical buyers and prospective contributors alike, visible
   momentum is the strongest argument this project has. Keep it public, keep it honest
   ([governance.md](governance.md)).

---

## Sources

- [Dwarf Fortress has topped 1 million sales on Steam — Game Developer](https://www.gamedeveloper.com/business/dwarf-fortress-has-topped-1-million-sales-on-steam)
- [Dwarf Fortress sales figures since Steam release — PC Gamer](https://www.pcgamer.com/dwarf-fortress-releases-sales-figures-since-steam-release-showing-46000-increase-in-earnings/)
- [Shattered Pixel Dungeon — GitHub](https://github.com/00-Evan/shattered-pixel-dungeon) · [Steam](https://store.steampowered.com/app/1769170/Shattered_Pixel_Dungeon/)
- [Best apps to practice difficult conversations with AI (2026) — Vocal Image](https://www.vocalimage.app/en/articles/37-practice-difficult-conversations-ai-apps/)
- [AI roleplays for interview preparation — Yoodli](https://yoodli.ai/use-cases/interview-preparation)
- [Running local LLMs in 2026: Ollama, LM Studio, and Jan compared — DEV](https://dev.to/synsun/running-local-llms-in-2026-ollama-lm-studio-and-jan-compared-5dii)
- [Façade (video game) — Wikipedia](https://en.wikipedia.org/wiki/Fa%C3%A7ade_(video_game))
- [ELIZA, Part 1 — The Digital Antiquarian](https://www.filfre.net/2011/06/eliza-part-1/)
