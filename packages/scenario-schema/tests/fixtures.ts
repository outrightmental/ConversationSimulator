/** Canonical YAML fixtures used across scenario-schema tests. */

export const VALID_MANIFEST_YAML = `\
schema_version: "1.0"
fictional: true
id: job-interview-basic
name: "Job Interview Practice"
version: "1.0.0"
description: "Practice common job interview scenarios with a fictional hiring manager."
author: "Conversation Simulator Contributors"
license: "Apache-2.0"
tags:
  - interview
  - professional
scenarios:
  - scenarios/behavioral-questions.yaml
npcs:
  - npcs/hiring-manager.yaml
rubrics:
  - rubrics/interview-quality.yaml
`;

export const VALID_SCENARIO_YAML = `\
schema_version: "1.0"
id: behavioral-questions
title: "Behavioral Interview"
description: "Practice STAR-method behavioral questions with a fictional hiring manager."
player_role: "You are interviewing for a software engineering position."
goals:
  - "Demonstrate relevant past experience"
  - "Answer with the STAR method"
difficulty: medium
duration_minutes: 20
npc_ref: hiring-manager
rubric_ref: interview-quality
opening_context: "You have arrived for your interview. Jordan greets you."
state_defaults:
  trust: 50
  patience: 80
  pressure: 20
  rapport: 30
  openness: 60
  objective_progress: 0
endings:
  - id: offer
    label: "Offer Extended"
    condition: "objective_progress >= 75"
    npc_reaction: "I was genuinely impressed. We would like to move you forward."
  - id: no-offer
    label: "No Offer"
    condition: "objective_progress < 75"
    npc_reaction: "Thanks for coming in. We will be in touch."
`;

export const VALID_NPC_YAML = `\
schema_version: "1.0"
id: hiring-manager
name: "Jordan Lee"
role: "Senior Engineering Manager"
persona:
  background: "10 years of software engineering, now manages a team of 8."
  speaking_style: "Direct and concise. Uses technical vocabulary naturally."
  personality_traits:
    - analytical
    - fair
    - time-conscious
voice:
  tone: professional
  pace: moderate
  formality: "business-casual"
boundaries:
  - "Does not ask illegal interview questions."
  - "Will not discuss salary before a formal offer."
hidden_agenda: "Values candidates who ask about team culture."
`;

export const VALID_RUBRIC_YAML = `\
schema_version: "1.0"
id: interview-quality
title: "Interview Performance"
dimensions:
  - id: clarity
    label: "Communication Clarity"
    description: "Does the player communicate ideas clearly?"
    weight: 1.0
    max_score: 5
  - id: star-method
    label: "STAR Structure"
    description: "Does the player structure behavioral answers with STAR?"
    weight: 1.5
    max_score: 5
`;
