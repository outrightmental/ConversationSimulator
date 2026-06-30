<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Pack: Job Interview Basics

**License:** CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/
**Pack ID:** `official.job_interview_basic`
**Content rating:** PG
**Status:** Active — behavioral interview scenario complete; additional scenarios planned.

Practice realistic job interviews with configurable difficulty. Sharpen your
ability to give specific, structured answers using the STAR method (Situation,
Task, Action, Result), build rapport with a professional interviewer, and
reflect honestly on past experience.

## Scenarios

### 1. The Behavioral Interview (`behavioral_interview`)

**File:** `scenarios/behavioral_interview.yaml`

You are interviewing for a Software Engineer role at Meridian Systems, a
mid-sized B2B tech company. Dana Reyes, the Engineering Manager, will ask
behavioral questions about your past experience. Specific, concrete answers
earn a stronger impression; vague platitudes lower it.

**Player role:** Job Candidate
**NPC:** Dana Reyes — professional, warm, and quietly demanding
**Duration:** Up to 20 turns (≈ 15 minutes)
**Difficulty options:** easy / normal / hard

**State variables:**

| Variable | Visible to player | Default | Description |
|---|---|---|---|
| `impression` | Yes | 50 | Dana's overall impression of the candidate |
| `rapport` | Yes | 40 | Social warmth and connection built during the interview |
| `rambling_count` | No | 0 | Tracks unfocused, overlong answers |
| `specificity_score` | No | 50 | Tracks quality and concreteness of examples given |

**Events:**

- **rambling_redirect** — fires when `rambling_count > 2`; Dana asks the candidate to give a concrete, specific example
- **high_specificity_reward** — fires once when `specificity_score > 75`; Dana shows deeper engagement and follow-up curiosity
- **low_impression_warning** — fires once when `impression < 25`; Dana begins wrapping up the interview

**Endings:**

- **Success** — `impression > 70`: Dana advances the candidate to the next round
- **Failure** — `impression < 15`: Dana politely ends the interview early
- **Timeout** — 20 turns elapsed; the outcome is determined by final state

### Planned Scenarios (Milestone 2+)

2. **Hostile Executive Interview** — stay composed under pressure and skepticism
3. **Blue-Collar Supervisor Interview** — practical, task-focused conversation
4. **Stretch Role Interview** — make the case when you are underqualified

## Why this pack

Clear utility, easy to score, safe content, strong replay value, and immediately
useful to job seekers and anyone practicing professional communication.

## NPC safety boundaries

Dana Reyes will never:

- Ask illegal interview questions (age, marital status, religion, national origin, disability, family plans)
- Flirt or make any romantic or sexual comments
- Impersonate a real person or named public figure
- Discuss salary or make promises about hiring outcomes

Governed by: `safety/interview_safety.yaml`

## Pack structure

```
job-interview-basic/
├── manifest.yaml                          Pack metadata and entry point list
├── README.md                              This file
├── scenarios/
│   └── behavioral_interview.yaml         The behavioral interview scenario
├── npcs/
│   └── hiring_manager.yaml               Dana Reyes NPC definition
├── rubrics/
│   └── interview_rubric.yaml             Clarity / Specificity / Rapport / Self-Awareness
├── scenes/
│   └── meridian_conference_room.yaml     Visual context descriptor
├── safety/
│   └── interview_safety.yaml             Content policy (PG, no illegal questions)
├── assets/
│   └── PLACEHOLDERS.md                   Documents portrait and background placeholders
└── tests/
    └── smoke_behavioral_interview.yaml   Smoke test fixture for the future test runner
```

## License

All scenario content in this pack is released under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
You may share and adapt this content for any purpose with attribution.
