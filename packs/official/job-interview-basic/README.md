<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Pack: Job Interview Basics

**License:** CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/
**Pack ID:** `official.job_interview_basic`
**Content rating:** PG
**Status:** Active — four playable scenarios.

Practice four distinct job interview scenarios, each with a different NPC style,
pressure dynamic, and scoring rubric. The pack covers structured behavioral
questions, executive-level pressure, practical blue-collar supervisor interviews,
and making the case when you are underqualified for a role.

## Scenarios

### 1. The Behavioral Interview (`behavioral_interview`)

**File:** `scenarios/behavioral_interview.yaml`

You are interviewing for a Software Engineer role at Meridian Systems, a
mid-sized B2B tech company. Dana Reyes, the Engineering Manager, will ask
behavioral questions about your past experience. Specific, concrete answers
using the STAR method earn a stronger impression; vague platitudes lower it.

**Player role:** Job Candidate (mid-level Software Engineer)
**NPC:** Dana Reyes — professional, warm, and quietly demanding
**Scene:** Meridian Systems conference room
**Rubric:** Clarity / Specificity / Rapport / Self-Awareness
**Duration:** Up to 20 turns (≈ 15 minutes)
**Difficulty options:** easy / normal / hard
**Model recommendation:** Any supported model; works well in text-only mode
**Voice support:** Placeholder (no voice engine configured)
**Content rating:** PG

**State variables:**

| Variable | Visible | Default | Description |
|---|---|---|---|
| `impression` | Yes | 50 | Dana's overall impression of the candidate |
| `rapport` | Yes | 40 | Social warmth and connection built during the interview |
| `rambling_count` | No | 0 | Tracks unfocused, overlong answers |
| `specificity_score` | No | 50 | Tracks quality and concreteness of examples given |

**Events:**

- **rambling_redirect** — fires when `rambling_count > 2`; Dana asks for a concrete, specific example
- **high_specificity_reward** — fires once when `specificity_score > 75`; Dana shows deeper follow-up engagement
- **low_impression_warning** — fires once when `impression < 25`; Dana begins wrapping up

**Endings:**

- **Success** — `impression > 70`: Dana advances the candidate to the next round
- **Failure** — `impression < 15`: Dana politely ends the interview early
- **Timeout** — 20 turns elapsed; outcome determined by final state

---

### 2. The Executive Gauntlet (`hostile_executive_interview`)

**File:** `scenarios/hostile_executive_interview.yaml`

You are interviewing for a Lead Software Architect role at Vantage Fintech
Solutions. Victor Hargrove, the VP of Engineering, is skeptical of your
credentials and challenges almost every answer. Stay composed under sustained
pressure, back your claims with concrete evidence, and hold your ground
respectfully when you are right.

**Player role:** Job Candidate (Lead Software Architect)
**NPC:** Victor Hargrove — exacting, skeptical VP of Engineering
**Scene:** Vantage Fintech executive corner office
**Rubric:** Composure / Credibility / Directness / Resilience
**Duration:** Up to 18 turns (≈ 12 minutes)
**Difficulty options:** easy / normal / hard (hard is significantly more hostile)
**Model recommendation:** Any supported model; works well in text-only mode
**Voice support:** Placeholder (no voice engine configured)
**Content rating:** PG

**State variables:**

| Variable | Visible | Default | Description |
|---|---|---|---|
| `composure` | Yes | 65 | Player's maintained professionalism under pressure |
| `credibility` | Yes | 35 | Victor's assessment of technical/professional credibility |
| `pressure_level` | No | 3 | Escalating hostility; triggers escalate_pressure event |
| `capitulation_count` | No | 0 | Tracks backing down without good reason |

**Events:**

- **credibility_challenge** — fires repeatedly when `credibility < 50`; Victor demands concrete evidence for any claim
- **escalate_pressure** — fires once when `pressure_level > 6`; Victor turns up the heat significantly
- **capitulation_penalty** — fires once when `capitulation_count > 2`; Victor calls out the pattern directly
- **grudging_respect** — fires once when `credibility > 55`; Victor acknowledges the answer and asks a harder follow-up before the candidate has fully cleared the bar

**Endings:**

- **Success** — `credibility > 65`: Victor decides to advance the candidate
- **Failure** — `composure < 20`: Victor ends the interview; player could not handle the pressure
- **Timeout** — 18 turns elapsed; outcome determined by final state

---

### 3. The Foreman's Interview (`blue_collar_supervisor_interview`)

**File:** `scenarios/blue_collar_supervisor_interview.yaml`

You are applying for a Shift Team Lead position at Crestview Distribution Co.,
a regional logistics and fulfillment company. Ray Morales, the Operations
Supervisor, runs a direct, no-nonsense interview focused on practical skills,
reliability, and whether you can earn the trust of a working crew. Corporate
jargon will not help here — plain, specific, honest answers will.

**Player role:** Job Candidate (Shift Team Lead)
**NPC:** Ray Morales — practical, direct warehouse operations supervisor
**Scene:** Crestview Distribution break room
**Rubric:** Practicality / Reliability / Crew Awareness / Motivation Fit
**Duration:** Up to 16 turns (≈ 12 minutes)
**Difficulty options:** easy / normal / hard (hard adds suspicion about candidate's motives)
**Model recommendation:** Any supported model; works well in text-only mode
**Voice support:** Placeholder (no voice engine configured)
**Content rating:** PG

**State variables:**

| Variable | Visible | Default | Description |
|---|---|---|---|
| `trust` | Yes | 40 | Ray's trust in the candidate |
| `work_ethic_score` | Yes | 50 | Ray's assessment of work ethic |
| `overqualified_concern` | No | 0 | Worry that candidate is slumming it; triggers overqualified_flag |
| `reliability_signals` | No | 50 | Evidence of reliability and commitment |

**Events:**

- **overqualified_flag** — fires once when `overqualified_concern > 3`; Ray directly asks why the candidate wants this job
- **reliability_probe** — fires repeatedly when `reliability_signals < 40`; Ray probes job history and commitment
- **crew_fit_test** — fires once when `trust > 60`; Ray presents a real crew conflict scenario

**Endings:**

- **Success** — `trust > 70`: Ray decides to offer the job
- **Failure** — `overqualified_concern > 4`: Ray politely says they will "keep your resume on file"
- **Timeout** — 16 turns elapsed; outcome determined by final state

---

### 4. Making the Case (`stretch_role_interview`)

**File:** `scenarios/stretch_role_interview.yaml`

You are applying for a Senior Product Manager role at Nexus Analytics with only
two years of relevant experience, where the role typically requires five or more.
Elena Vasquez, the Head of Product, is genuinely open to a stretch hire — but
only if you acknowledge the gap honestly, back your readiness with specific
transferable examples, and demonstrate you have done genuine research on the role.

**Player role:** Job Candidate (underqualified for Senior PM)
**NPC:** Elena Vasquez — thoughtful, growth-minded Head of Product
**Scene:** Nexus Analytics open office product team area
**Rubric:** Self-Awareness / Transferable Evidence / Preparation / Learning Velocity
**Duration:** Up to 20 turns (≈ 15 minutes)
**Difficulty options:** easy / normal / hard (hard requires more evidence to reach conviction threshold)
**Model recommendation:** Any supported model; works well in text-only mode
**Voice support:** Placeholder (no voice engine configured)
**Content rating:** PG

**State variables:**

| Variable | Visible | Default | Description |
|---|---|---|---|
| `conviction` | Yes | 35 | Elena's belief that candidate can succeed in the role |
| `preparation_score` | Yes | 45 | Demonstrated knowledge of the role and company |
| `stretch_potential` | No | 40 | Evidence of ability to grow quickly |
| `gap_acknowledged` | No | 0 | Whether player has honestly addressed the experience gap (0 or 1) |

**Events:**

- **gap_probing** — fires once when `gap_acknowledged < 1`; Elena raises the experience gap directly
- **evidence_boost** — fires once when `stretch_potential > 70`; Elena engages with a hard real challenge
- **hesitation_signal** — fires once when `conviction < 30`; Elena flags her concern and asks for the strongest evidence
- **preparation_challenge** — fires once when `preparation_score < 35`; Elena tests whether the candidate has done real research

**Endings:**

- **Success** — `conviction > 65`: Elena wants to advance the candidate
- **Failure** — `conviction < 15`: Elena respectfully declines
- **Timeout** — 20 turns elapsed; outcome determined by final state

---

## Why this pack

Clear utility, easy to score, safe content, strong replay value, and immediately
useful to job seekers and anyone practicing professional communication. Each
scenario puts the player in a meaningfully different interpersonal situation,
requiring a different skill set to succeed.

## NPC safety boundaries

All NPCs in this pack will never:

- Ask illegal interview questions (age, marital status, religion, national origin, disability, family plans, sexual orientation)
- Flirt, make romantic comments, or introduce any sexual or intimate content
- Impersonate a real person or named public figure
- Discuss salary or make promises about hiring outcomes

Governed by: `safety/interview_safety.yaml`

## Pack structure

```
job-interview-basic/
├── manifest.yaml
├── README.md
├── scenarios/
│   ├── behavioral_interview.yaml
│   ├── hostile_executive_interview.yaml
│   ├── blue_collar_supervisor_interview.yaml
│   └── stretch_role_interview.yaml
├── npcs/
│   ├── hiring_manager.yaml              Dana Reyes — behavioral interviewer
│   ├── executive_interviewer.yaml       Victor Hargrove — hostile VP
│   ├── trade_supervisor.yaml            Ray Morales — warehouse supervisor
│   └── product_head.yaml               Elena Vasquez — Head of Product
├── rubrics/
│   ├── interview_rubric.yaml            Clarity / Specificity / Rapport / Self-Awareness
│   ├── executive_interview_rubric.yaml  Composure / Credibility / Directness / Resilience
│   ├── blue_collar_rubric.yaml          Practicality / Reliability / Crew Awareness / Motivation Fit
│   └── stretch_role_rubric.yaml         Self-Awareness / Transferable Evidence / Preparation / Learning Velocity
├── scenes/
│   ├── meridian_conference_room.yaml
│   ├── vantage_executive_suite.yaml
│   ├── crestview_break_room.yaml
│   └── nexus_open_office.yaml
├── safety/
│   └── interview_safety.yaml
├── assets/
│   └── PLACEHOLDERS.md
└── tests/
    ├── smoke_behavioral_interview.yaml
    ├── smoke_hostile_executive_interview.yaml
    ├── smoke_blue_collar_supervisor_interview.yaml
    ├── smoke_stretch_role_interview.yaml
    └── golden_behavioral_interview.yaml
```

## License

All scenario content in this pack is released under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
You may share and adapt this content for any purpose with attribution.
