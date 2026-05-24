---
name: Feature request
about: Propose a new feature or improvement
title: "[feat] "
labels: enhancement
---

## What you want to be able to do

Describe the workflow or capability you wish Reverie supported. Be concrete:
"I want to compare three runs at once" beats "make compare better".

## Why

What problem does this solve for you? What are you doing today instead?

## How it might look

Optional sketches / mockups / API ideas. Even a one-line CLI invocation
or a JSON shape is helpful.

```bash
# What you'd type
reverie compare run-a run-b run-c --pivot run-a
```

## Schema implications

Reverie's `CognitiveEvent` schema is **frozen at v1.0**. Any new event
types or fields are additive only. If your idea needs a schema change,
sketch it here so we can plan the rollout.

## Alternatives considered

Workarounds you've tried, related tools you've used, etc.
