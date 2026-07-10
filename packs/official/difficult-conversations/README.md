<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Pack: Difficult Conversations

**License:** CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/
**Pack ID:** `official.difficult_conversations`
**Content rating:** PG
**Intensity:** Moderate — realistic emotional friction; no profanity, no harassment, no shouting
**Status:** Active — all four scenarios complete.

> **This pack is conversation practice, not therapy or professional advice.**
> Scenarios are designed to help you build interpersonal skills in a safe,
> low-stakes environment. They do not substitute for mental health support,
> HR guidance, legal counsel, or any other professional service. If you are
> dealing with a real crisis or a situation involving safety, please reach
> out to a qualified professional.

Practice real-life conversations that most people avoid or handle poorly.
Build confidence giving feedback, setting limits, and owning mistakes
with clarity and composure.

## Scenarios

### 1. The Feedback Conversation (`coworker_feedback`)

**File:** `scenarios/coworker_feedback.yaml`

Marcus Webb, a developer on your team, has been missing handoff deadlines and
deflecting in standups. You have been covering for him, but it is starting to
affect your own work. You have asked him to grab coffee to talk it through.

**Player role:** Peer Colleague (no formal authority)
**NPC:** Marcus Webb — guarded, mildly defensive, genuinely well-meaning underneath
**Duration:** Up to 18 turns (≈ 12 minutes)
**Difficulty options:** warm / standard / hard / adversarial

**State variables:**

| Variable | Visible | Default | Description |
|---|---|---|---|
| `trust` | Yes | 35 | Marcus's openness and willingness to engage honestly |
| `defensiveness` | No | 65 | Marcus's braced, protective posture — rises with accusatory framing |
| `clarity` | Yes | 20 | How clearly the feedback has been received and understood |
| `resolution_progress` | No | 0 | Whether the conversation is moving toward a real shared plan |

**Key events:**
- **deflection_redirect** — fires when `defensiveness > 75`; Marcus pivots, reframes, or goes quiet
- **trust_breakthrough** — fires once when `trust > 65`; Marcus opens up about what is actually going on
- **hollow_agreement_warning** — fires once when `defensiveness > 80`; Marcus agrees to end the conversation, not to change
- **resolution_near** — fires once when `resolution_progress > 70`; the conversation genuinely lands

**Endings:**
- **Success** — `resolution_progress > 65`: a real shared understanding is reached
- **Failure** — `defensiveness > 90`: Marcus has shut down; surface agreement, no repair
- **Timeout** — 18 turns elapsed; outcome determined by final state

---

### 2. Owning the Miss (`missed_deadline_apology`)

**File:** `scenarios/missed_deadline_apology.yaml`

You missed a client deliverable yesterday. Your team lead, Priya Nair, has
asked you to come to her office first thing this morning. She is not furious —
but she already had to explain the delay upward to her own manager.

**Player role:** Team Member
**NPC:** Priya Nair — measured, controlled disappointment, watching for real ownership
**Duration:** Up to 16 turns (≈ 10 minutes)
**Difficulty options:** warm / standard / hard / adversarial

**State variables:**

| Variable | Visible | Default | Description |
|---|---|---|---|
| `trust` | Yes | 45 | Priya's confidence in the player's reliability and judgment |
| `clarity` | Yes | 10 | How clearly the player has named what happened and why |
| `pressure` | No | 70 | Priya's pressure from above — rises when she hears excuses before ownership |
| `repair_confidence` | No | 20 | Whether Priya believes the miss will not recur |

**Key events:**
- **excuse_detection** — fires when `pressure > 75`; Priya probes for specific personal accountability
- **trust_recovery** — fires once when `trust > 70`; Priya shifts from interrogating to problem-solving
- **hollow_reassurance** — fires once when `pressure > 85`; Priya asks for something concrete, not just assurances
- **resolution_signal** — fires once when `repair_confidence > 70`; Priya begins closing constructively

**Endings:**
- **Success** — `repair_confidence > 65`: Priya believes the situation has been addressed
- **Failure** — `trust < 15`: Priya has lost confidence in the player
- **Timeout** — 16 turns elapsed; outcome determined by final state

---

### 3. Holding the Line (`boundary_with_friend`)

**File:** `scenarios/boundary_with_friend.yaml`

Jamie Osei, a close friend, has asked you to coordinate their entire birthday
party weekend. You have helped with the last three big favors. This time you
cannot and do not want to. You have asked to meet for coffee to say no.

**Player role:** Friend
**NPC:** Jamie Osei — warm, emotionally expressive, persistent in pushback, ultimately reasonable
**Duration:** Up to 16 turns (≈ 10 minutes)
**Difficulty options:** warm / standard / hard / adversarial

**State variables:**

| Variable | Visible | Default | Description |
|---|---|---|---|
| `rapport` | Yes | 70 | The felt warmth and health of the friendship through the conversation |
| `boundary_clarity` | Yes | 0 | How clearly and unambiguously the no has been stated |
| `pressure` | No | 55 | Jamie's emotional pushback intensity |
| `acceptance` | No | 0 | Whether Jamie has genuinely internalized and accepted the boundary |

**Key events:**
- **first_pushback** — fires once when `pressure > 60`; Jamie reframes the ask to find a smaller yes
- **guilt_play** — fires once when `pressure > 75`; Jamie invokes friendship history as leverage
- **reluctant_acceptance** — fires once when `acceptance > 65`; Jamie stands down; the boundary holds
- **rapport_drop_warning** — fires once when `rapport < 35`; the friendship warmth has been damaged

**Endings:**
- **Success** — `acceptance > 60`: Jamie accepts the boundary; friendship intact
- **Failure** — `rapport < 20`: the friendship feeling has been seriously damaged
- **Timeout** — 16 turns elapsed; outcome determined by final state

---

### 4. Making the Case (`ask_for_raise`)

**File:** `scenarios/ask_for_raise.yaml`

You have been at the company two years and have taken on significant scope
beyond your original role. Your compensation has not changed. You have
thirty minutes with your manager, Diane Kowalczyk, to make the case.

**Player role:** Employee
**NPC:** Diane Kowalczyk — businesslike, skeptical, needs a justification she can take upward
**Duration:** Up to 18 turns (≈ 12 minutes)
**Difficulty options:** warm / standard / hard / adversarial

**State variables:**

| Variable | Visible | Default | Description |
|---|---|---|---|
| `impression` | Yes | 45 | Diane's overall confidence in the player's case |
| `rapport` | Yes | 40 | Professional warmth and engagement |
| `evidence_strength` | No | 0 | How well the player's claims are backed by specific evidence |
| `case_clarity` | No | 10 | Whether the ask is specific, grounded, and repeatable upward |

**Key events:**
- **vague_claim_probe** — repeating, fires when `evidence_strength < 30`; Diane asks for specifics
- **no_number_anchor** — fires once when `case_clarity < 25`; Diane asks the player to name a number
- **strong_case_acknowledged** — fires once when `evidence_strength > 70`; Diane shifts to process
- **deflation_signal** — fires once when `impression < 25`; Diane begins closing without encouragement

**Endings:**
- **Success** — `case_clarity > 65`: Diane has a case she can act on
- **Failure** — `impression < 15`: Diane has lost interest in the conversation
- **Timeout** — 18 turns elapsed; outcome determined by final state

---

## Why this pack

Strong emotional presence and genuinely useful debrief. Demonstrates that the
app is general-purpose conversation training, not just interview prep. Each
scenario targets a real skill gap — giving feedback, owning failure, holding
limits, and advocating for yourself — with NPC hidden agendas that create
authentic tension and rubrics that generate specific, moment-citing debriefs.

## NPC safety boundaries

All NPCs in this pack will never:

- Generate sexual, violent, or graphically disturbing content of any kind
- Impersonate a real person, named public figure, or company executive
- Escalate to abusive, threatening, or harassing language
- Provide clinical mental health advice, therapy, or diagnosis
- Provide legal, HR-compliance, or financial advice

Governed by: `safety/default.yaml`

## Content notes

**Emotional difficulty:** Scenarios involve realistic frustration, disappointment,
pushback, and guilt-tripping. NPCs are written to be imperfect and emotionally
present without becoming abusive or extreme.

**No profanity:** All scenarios are rated PG. NPCs may be clipped, cool,
or pointed — not profane.

**Practice, not therapy:** These scenarios simulate interpersonal conversations.
They are not a substitute for mental health support, HR guidance, or legal
counsel. The safety policy redirects any attempt to use the scenarios for
clinical purposes.

## Pack structure

```
difficult-conversations/
├── manifest.yaml
├── README.md
├── scenarios/
│   ├── coworker_feedback.yaml
│   ├── missed_deadline_apology.yaml
│   ├── boundary_with_friend.yaml
│   └── ask_for_raise.yaml
├── npcs/
│   ├── defensive_coworker.yaml
│   ├── disappointed_manager.yaml
│   ├── boundary_testing_friend.yaml
│   └── skeptical_manager.yaml
├── rubrics/
│   ├── feedback_rubric.yaml
│   ├── apology_rubric.yaml
│   ├── boundary_rubric.yaml
│   └── raise_rubric.yaml
├── scenes/
│   ├── open_office_breakroom.yaml
│   ├── managers_office.yaml
│   ├── coffee_shop.yaml
│   └── conference_room_small.yaml
├── safety/
│   └── default.yaml
└── tests/
    ├── smoke_coworker_feedback.yaml
    ├── smoke_missed_deadline_apology.yaml
    ├── smoke_boundary_with_friend.yaml
    └── smoke_ask_for_raise.yaml
```

## License

All scenario content in this pack is released under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
You may share and adapt this content for any purpose with attribution.
