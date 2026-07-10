<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Concept acceptance review

**Owner:** Product team
**Scope:** Every MVP release candidate must pass or document exceptions.
**Goal:** A first-time repo visitor understands the core concept within 60 seconds of landing on the README.

This review is **manual and subjective**. It requires a reviewer who has not seen the project before, or who can credibly simulate that perspective. The reviewer reads only what a GitHub visitor sees in the first scroll.

---

## What to test

The reviewer opens `https://github.com/outrightmental/ConversationSimulator` (or the README rendered locally) and reads for **60 seconds** — no deeper navigation allowed.

After 60 seconds the reviewer answers the following questions **without looking further**.

---

## Rubric

Score each dimension 1 (fail), 2 (partial), or 3 (pass).

| # | Dimension | Pass criteria | Score |
|---|---|---|---|
| 1 | **What it is** | Reviewer can state the product is the simulator for conversations — for interviews, negotiations, language practice, and difficult conversations | 1 / 2 / 3 |
| 2 | **Local-first** | Reviewer can state that inference runs locally (no cloud LLM required) | 1 / 2 / 3 |
| 3 | **Who it is for** | Reviewer can name at least two of the four target audiences (player, creator, developer, researcher) OR two use-cases (interviews, negotiations, language, difficult conversations) | 1 / 2 / 3 |
| 4 | **How to start** | Reviewer can state a concrete first action (e.g. "run setup.sh" or "open the web app") | 1 / 2 / 3 |
| 5 | **Not a chatbot** | Reviewer understands the NPC follows a scenario script with goals and a rubric, not free-form conversation | 1 / 2 / 3 |

**Scoring:**
- 13–15 points: PASS — concept is clear within 60 seconds.
- 10–12 points: PARTIAL — reviewer grasps the core but misses one important dimension; acceptable with documented gap.
- < 10 points: FAIL — README must be revised before MVP tag.

---

## Reviewer notes

```
Reviewer name   :
Date            :
Reading time    : [≤ 60 s / > 60 s]
Source          : GitHub README / local render / other

Q1 – What it is     : [reviewer's words]
Q2 – Local-first    : [yes / no / unsure — reviewer's words]
Q3 – Who it is for  : [reviewer's answer]
Q4 – How to start   : [reviewer's answer]
Q5 – Not a chatbot  : [yes / no / unsure — reviewer's words]

Scores: Q1= Q2= Q3= Q4= Q5=  Total= /15

Result  : PASS / PARTIAL / FAIL

Specific gaps identified:
  -
  -

Suggested README edits (if any):
  -
  -
```

---

## Pass/fail determination

| Result | Action |
|---|---|
| PASS | Record result in release issue; proceed to MVP tag |
| PARTIAL | Record result with gap description; product lead decides whether to block tag or document exception |
| FAIL | README revision required before MVP tag; re-review after revision |

**Release decision:** A PASS or PARTIAL with documented justification is required before the MVP release can be tagged.
