---
title: Manifesto
subtitle: Why the simulator for conversations exists, and the promises it will not break.
description: Rehearsal is not cheating, your practice is nobody's business, and other convictions behind Conversation Simulator.
---

Some conversations change the course of a life. The interview. The raise. The
apology you owe. The boundary you finally draw. The sentence in another
language you've been too embarrassed to attempt out loud.

Pilots get simulators. Surgeons get practice labs. Musicians get rehearsal
rooms. For the conversations that decide careers and friendships, most people
get one take — live, unrehearsed, with everything on the line.

Conversation Simulator exists to end that. It is the simulator for
conversations. Not a chatbot, not a game, not a course. A practice
environment where you run the conversation before it matters — as many times
as it takes.

These are its convictions.

## Rehearsal is not cheating

Preparing for a hard conversation is not manipulation. It is respect — for
yourself, and for the person across the table. Practice does not make a
conversation less honest; it makes it less clumsy. You still have to mean
what you say. You'll just say it better.

## The stakes belong in the room, not in the rehearsal

The whole point of a simulator is repetitions without consequences. Blow the
interview at one in the morning. Get talked over. Freeze. Then run it again,
and again, until the version of you that walks into the real room has already
been here.

The character across the table pushes back, warms up, loses patience — and
live meters show the dynamic shifting as you speak. When it ends, the debrief
tells you what you said clearly, where you hedged, and which moment turned
the conversation. That feedback loop is the product.

## Your practice is nobody's business

The conversations you most need to rehearse — the raise, the diagnosis
conversation, the apology — are exactly the ones you would never type into
someone else's server.

So there is no server.

The language model, the speech recognition, the voices, the transcripts, the
scores: all of it runs and stays on your computer. No account. No cloud. No
telemetry. No subscription. This is not a privacy policy that could quietly
change one day — it is the architecture. There is no server to trust because
there is no server.

## You shouldn't have to take our word for it

Conversation Simulator is free and open source. Every line of the engine is
public. And verification is built in: one command runs a scripted
conversation and fails loudly if any part of the app so much as attempts an
outbound connection.

```
npx convsim offline-smoke-test packs/official/job-interview-basic
```

Trust that can't be checked is just branding. Check.

## Conversations are written, not engineered

A scenario is a folder of plain YAML files — a situation, a character, a
scoring rubric, safety rules. No code, no build step. If you can describe a
conversation, you can build one: a teacher scripting oral exams, a union rep
drilling negotiations, a friend who knows exactly which conversation you're
dreading.

The official packs are openly licensed. Fork them, remix them, share your own.

## Safety has no difficulty slider

Two rules hold in every scenario, in every pack, from every author, and no
configuration can weaken them: content that sexualizes minors ends the
session, and self-harm crisis language ends the session and surfaces real
resources. Community packs can make safety rules stricter. Never looser.

## Open source and fairly priced

No premium tier. No ads. No locked scenarios. No data resale — there is no
data to sell. The engine is Apache-2.0, the official packs are CC BY 4.0,
and building from source on GitHub is free, always.

On Steam the app costs $9.99 once. That purchase funds development; it does
not unlock anything the source build lacks, and nothing that ships free today
will ever move behind a paywall. Premium expansion packs, written by Outright
Mental and sold as Steam DLC, are the only paid content — and they are always
additions, never relocations.

---

**Practice the conversation before it matters.**

[Download Conversation Simulator](/download/) — or [read the docs](https://docs.conversationsimulator.com)
to see exactly how it works.
