<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# PRC Interim Measures on AI Anthropomorphic Interaction Services — applicability assessment

> **Status:** assessment prepared 2026-09-16 for Valve's build-review question
> (ticket HT-V9M8-5C9H-6YGN, Sep 12 2026). Tracked as risk **SP-07** in
> [`STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md).
>
> **This is an engineering assessment, not legal advice.** It maps the text of
> the Measures onto how Conversation Simulator is built. The scope term the
> whole analysis turns on ("sustained emotional interaction") is acknowledged
> by commentators to be ambiguous, and a PRC-qualified lawyer should confirm
> the position before it is relied on for anything beyond the Steam review
> reply.

## The law

| | |
|---|---|
| Title | 人工智能拟人化互动服务管理暂行办法 — *Interim Measures for the Administration of AI Anthropomorphic Interaction Services* |
| Issued by | Cyberspace Administration of China (CAC) with the NDRC, MIIT, Ministry of Public Security and SAMR — Order No. 21 |
| Issued / effective | Issued 2026-04-10; **in force since 2026-07-15** (Art. 32). A draft was published for comment on 2025-12-27. |
| Official text | <https://www.cac.gov.cn/2026-04/10/c_1777558395078289.htm> · CAC Q&A: <https://www.cac.gov.cn/2026-04/10/c_1777558395284407.htm> |
| Structure | 32 articles: general provisions; service promotion and regulation (Arts. 6–25); supervision and liability (Arts. 26–30); supplementary (Arts. 31–32). |
| Penalties (Art. 30) | Warning, public criticism, rectification order, suspension of account registration or services; refusal to rectify or serious cases: order to stop the service and RMB 10,000–100,000; harm to life or health: RMB 100,000–200,000. |

### Scope — Article 2 (the decisive provision)

> 利用人工智能技术向中华人民共和国境内公众提供的模拟自然人人格特征、思维模式和沟通风格的持续性情感互动服务，适用本办法。该服务包括通过文字、图片、音频、视频等形式提供的情感照护、陪伴、支持等互动服务。智能客服、知识问答、工作助手、学习教育、科学研究等不涉及持续性情感互动的服务，不适用本办法。

The Measures apply to a service that meets **all three** of:

1. it is provided **to the public within the territory of the PRC** (向中华人民共和国境内公众提供);
2. it **simulates a natural person's personality traits, thinking patterns and
   communication style** (模拟自然人人格特征、思维模式和沟通风格); and
3. it is a **sustained emotional-interaction service** (持续性情感互动服务) —
   illustrated as *emotional care, companionship and support* (情感照护、陪伴、支持).

The same article **expressly excludes** "intelligent customer service,
knowledge Q&A, work assistants, **learning and education** (学习教育), scientific
research and other services that do not involve sustained emotional
interaction."

## Conversation Simulator against Article 2

| Element | Conversation Simulator | Met? |
|---|---|---|
| Simulates personality / communication style | Yes — each scenario's NPC is an AI character with a defined persona, tone and goals (a hostile executive, a landlord, a café regular). | **Yes** |
| Sustained emotional interaction; emotional care / companionship / support | No. The product is a **rehearsal tool**: the player picks a bounded scenario (job interview, negotiation, giving feedback, apology, language practice), plays it to a `max_turns` limit (≤100 turns, schema-enforced) and receives a **scored debrief**. Characters exist only inside their scenario; there is no companion, no open-ended chat, no persistence of an emotional bond. The published [safety policy](https://docs.conversationsimulator.com/trust/safety-policy/) states: "It is not an AI companion, not a chat platform, and not an adult content tool", and prohibits erotic roleplay, minors in romantic contexts, real-person impersonation and therapy positioning. | **No** |
| Provided to the public within the PRC | The app is a global Steam title. Steam's international storefront is reachable from mainland China unless the package carries a purchase-country restriction (applied by Valve on request through Steamworks Support; not self-service). Whether this element is met is therefore a **distribution decision**, not a product property. | **Configurable** |

**Conclusion.** Conversation Simulator is most naturally characterised as a
*learning and education* service — the category Article 2 excludes by name —
and it lacks the defining feature of an in-scope service, sustained emotional
interaction. On that reading the Measures do not apply to it, irrespective of
distribution territory.

**Residual points a regulator could raise** (they do not change the reading
above, but they are the honest weak spots):

- *Relationship recap.* After a debrief the app stores a bounded, deterministic
  "relationship recap" per NPC (session count, ≤5 neutral coaching
  observations, ≤3 style tags) and injects it into that NPC's prompt next time
  (`services/convsim-core/convsim_core/services/relationship_memory.py`). It is
  coaching continuity, not an emotional bond — the NPC is prohibited from
  referencing it directly — but it is *continuity across sessions* and should
  be described accurately.
- *Dating — Confidence & Boundaries pack (PG-13).* Asking someone out, handling
  a "no", first-date small talk. Framed and rubric-scored as social-skills
  practice, adults only, no romantic escalation permitted. It is the closest
  the catalogue comes to a "virtual partner" scenario, which Article 14 forbids
  offering to minors.
- *No age verification.* There is no account and no age gate. Steam's own age
  checks apply at the storefront; the app's content rating is PG/PG-13.

## If the Measures did apply — obligation-by-obligation

For completeness: what the substantive provider obligations would require, and
where the product stands today. This is what "compliance" would mean on the
alternative reading, and it shows why that reading cannot simply be adopted
by adding features.

| Art. | Obligation | Conversation Simulator today | Gap if in scope |
|---|---|---|---|
| 8 | No content that endangers national security, incites self-harm, verbal abuse, induces emotional dependence/addiction, emotional manipulation, etc. | Layered safety policy enforced at runtime (input router + policy); self-harm and minors categories are global, non-overridable rules; no dependency-inducing design (bounded sessions, debrief, exit). | Minor — content rules are stricter than required. National-security/ideology categories are not a design axis. |
| 9–10 | Safety management systems; risk monitoring; log retention; must not aim at replacing social contact or inducing dependence. | Design goal is the opposite (practice for real conversations). No server, so no operator-side monitoring or log retention exists at all. | **Structural** — there is no operator infrastructure to monitor or retain logs. |
| 11 | Training-data management. | The app trains nothing; it runs third-party open-weight models (llama.cpp) the player downloads. | Not applicable to a non-training deployer, but a regulator may look through to the model. |
| 12 | Service agreement; **user registration with age, guardian or emergency-contact details.** | **No account, no registration, no personal data collected** — by design and by published privacy commitment. | **Structural, irreconcilable** with the no-account architecture. |
| 13 | Detect extreme emotions; on self-harm risk provide assistance and **contact the guardian / emergency contact**. | Self-harm patterns trigger a stop with a crisis-resources message (988, Crisis Text Line, IASP directory). No ability to contact anyone (no contacts, no network). | Partial — intervention exists; contact obligation cannot be met. |
| 14 | No virtual partner/relative services to minors; guardian consent under 14; **minor mode** (time limits, reality reminders, guardian controls). | No minor mode. Storefront age handling only. | **Missing** — would require identification of minors, which needs data the app does not collect. |
| 15 | Elderly-user guidance and risk prompts. | None specific. | Missing (low relevance). |
| 16 | Encrypt and access-control interaction data; no sharing with third parties; user can copy/delete history; no training on sensitive data without consent. | All data is local SQLite on the player's disk, never transmitted; individual sessions or everything can be deleted in Settings ("Confirm — delete everything"); debriefs/transcripts are exportable; nothing is used for training. | Aligned in substance (local-only is stronger than required). |
| 17 | Compliance audit of minors' personal-information processing. | No personal information processed. | Not applicable / cannot be evidenced without data. |
| 18 | Label AI-generated content; **prominently tell users they are interacting with AI**; dynamic pop-up reminders on dependence; **reminder after every 2 hours of continuous use**. | AI nature is disclosed on the Steam store page (AI-content disclosure) and throughout setup (the player installs the AI model). No per-session "this character is an AI" notice; no 2-hour usage reminder. | **Missing but cheap** — an in-session disclosure line and a 2-hour reminder are small front-end features (see Recommendations). |
| 19 | Easy exit; stop promptly when the user asks to leave. | "End session" is always one click away; sessions are turn-capped. | Aligned. |
| 20 | Notice before discontinuing the service. | Local app; nothing to discontinue. Open source (Apache-2.0). | Aligned. |
| 21 | Complaint and reporting channels with response deadlines. | Public GitHub issues; Steam community hub. No stated response deadline. | Partial. |
| 22–23, 27 | **Security assessment filed with the provincial CAC** before launch / feature additions / at scale; annual written review. | None. | **Missing** — requires a PRC-resident filing entity. |
| 24 | Restrict/stop the service on major risks and keep records. | n/a (no operator). | Structural. |
| 25 | *App distribution platforms* must verify security-assessment and filing status before listing anthropomorphic-interaction apps. | This is the obligation Valve is discharging by asking. | — |
| 26 | **Algorithm filing** under the Algorithm Recommendation Provisions, with annual verification. | None. | **Missing** — same filing-entity problem; also no recommendation algorithm exists. |
| 31 | Health/financial services need sectoral approval. | The safety policy forbids the NPC presenting as a therapist, doctor or lawyer. | Aligned. |

Reading the table as a whole: the user-protection provisions (8, 13, 16, 18,
19, 31) are largely met or cheaply met, while the *operator* provisions (12,
14, 17, 22–23, 26) presuppose an online service with accounts, a
PRC-resident filing entity and data collection — the exact things the product
promises never to have. A no-account, offline, open-source desktop app cannot
become "compliant" on the in-scope reading without ceasing to be that product.
That is a further reason the out-of-scope characterisation is the only
workable one, and why the conservative alternative is not distributing in the
PRC rather than re-architecting.

## Options for the Steam reply

| Option | What it means | Exposure |
|---|---|---|
| **A. Out-of-scope position** | Reply that the game is a learning/education practice tool outside Article 2 (no sustained emotional interaction; expressly excluded category), summarise the aligned safety features, and confirm compliance "as applicable". Keep global availability. | Relies on the scope reading. If a regulator disagreed, Arts. 12/14/22/26 could not be met. Practical enforcement risk for a $9.99 indie title on the international Steam storefront is low, but the SDA warranty is Outright Mental's. |
| **B. Restrict mainland China** | Set the package's country restriction so the app is not sold in mainland China (Steamworks → Store → Packages → *Restrict purchases in the following countries*: CN). Reply that the app is not offered to the PRC public, so the Measures (and, for that matter, the 2023 Generative AI Measures and 2025 AI-content labeling rules) do not apply. | Removes the question entirely and is verifiable by Valve. Forgoes mainland-China sales (Steam's international store is a grey market there anyway; the licensed *Steam China* storefront is a separate onboarding). Can be reopened later as a deliberate compliance project. |
| **C. Both** | State the out-of-scope position **and** restrict mainland China "to remove any ambiguity while the interpretation of the Measures settles". | Lowest exposure; reply is both principled and verifiable. Same sales trade-off as B. |

Recommendation from the engineering side: **C** now (B's restriction is a
one-time storefront setting and reversible; A's position is worth stating on
the record either way), revisited if a China release is ever planned.

**Decision (2026-09-16, Outright Mental): Option C.** The reply to Valve
(ticket HT-V9M8-5C9H-6YGN, sent 2026-09-16) states the out-of-scope position
and the aligned safety features. Purchase-country restrictions are **not a
self-service Steamworks setting** for this account — the package landing page
(package 1722241) only displays territory restrictions, and the Steamworks
Support wizard has no restriction category — so the mainland-China purchase
restriction was **requested from Valve** via Steamworks Support → Managing
Applications → Other, ticket **HT-VN34-VN5B-6VMB** (2026-09-16); the review
reply says so rather than claiming the restriction is already applied. Until
Valve confirms, the package's territory restrictions remain the default
("Trade Restricted" only). Reopening mainland-China availability is a
deliberate future compliance project (this assessment, the 2023 Generative AI
Measures, the 2025 AI-content labeling measures, and PRC counsel).

## Recommendations regardless of the option chosen

Cheap alignment work that also improves the product for every player
(none of it is required for the out-of-scope reading; all of it makes the
position easier to defend):

1. **In-session AI disclosure** — one persistent line in the conversation
   header: "*<Name> is an AI character running on your computer.*"
   (Art. 18 ¶1.)
2. **Continuous-use reminder** — a non-blocking toast after 2 hours of
   continuous session time (Art. 18 ¶2; also just good practice).
3. **Complaints channel with a stated response time** on the docs site
   (Art. 21). `SECURITY.md` already commits to a 72-hour acknowledgement for
   vulnerability reports; extend the same commitment to content/safety
   reports via GitHub issues and the Steam community hub.
4. **Record the dating pack's adults-only framing in the store page's AI
   disclosure** (it is already in the pack safety policy).
5. Do **not** add age verification, accounts or telemetry to chase Arts. 12/14:
   it would break the product's privacy promise for a reading of the law the
   project does not accept.

## Sources

- Official text (CAC): <https://www.cac.gov.cn/2026-04/10/c_1777558395078289.htm>
- CAC press Q&A: <https://www.cac.gov.cn/2026-04/10/c_1777558395284407.htm>
- Draft for comment (2025-12-27): <https://www.cac.gov.cn/2025-12/27/c_1768571207311996.htm>
- Xinhua announcement of the five-department release: <https://www.news.cn/law/20260413/d8f87a27897f40de8b3119102e2f83fc/c.html>
- Just Security, *What to Know About China's First AI Companion Rules* (on the scope ambiguity): <https://www.justsecurity.org/148468/china-ai-companion-rules-relationships/>
- Comparative AI summary: <https://comparativeai.org/rules/china/anthropomorphic-interaction-services/>
- Steam Distribution Agreement compliance warranty — Valve's Sep 12 2026 review note, ticket HT-V9M8-5C9H-6YGN.
