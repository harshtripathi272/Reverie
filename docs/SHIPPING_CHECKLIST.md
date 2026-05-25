# Reverie shipping checklist

A living document of what's done, what's in progress, and what's left
before this is a real, public-ready tool. Update it as items move.

---

## Status snapshot — May 2026

| Area | State |
|---|---|
| Schema (22 event types, frozen v1.0) | done |
| FastAPI backend + SQLite log | done |
| OpenAI Agents SDK adapter | done |
| Universal `ReverieClient` (any framework) | done |
| Snapshot engine | done |
| Graph intelligence + anomaly detection | done |
| Salience scorer | done |
| Comparative debugger | done |
| 3D explorer (R3F) | done |
| Multi-select + bulk-tag in 3D | done |
| Annotations (avoid/focus/done/note) + guidance loop | done |
| `reverie start` one-command launch | done |
| `reverie init` global config | done |
| Bundled web app (single-port serve) | done |
| Standalone binary (PyInstaller) | done |
| 4 of 5 packages live on PyPI | done |
| `reverie-schema` on PyPI | rate-limited, retry tomorrow |
| Real-shape examples (NVIDIA, RAG, multi-agent) | done — see `examples/real/` |

---

## P0 — required before public announcement

- [ ] **`reverie-schema` on PyPI.** Without this, `pip install reverie-obs`
      fails. Re-run release workflow tomorrow once the rate limit clears.
- [ ] **Smoke-test `pipx install reverie-obs` end-to-end on a clean
      machine.** Once schema lands, do this on a fresh VM to make sure the
      install path actually works for users who don't have your repo.
- [ ] **Smoke-test the standalone binaries on Linux + macOS.** Windows
      one is verified locally; the Linux/macOS ones come out of CI but
      haven't been run on the target OS yet.
- [ ] **Privacy redaction for payloads.** Add a `redactor` callable on
      `ReverieClient` so users can scrub secrets before events leave their
      process. ~1 day.

## P1 — high value, do soon

- [ ] **Auth on the backend.** Currently the API is unauthenticated —
      fine for localhost, dangerous for shared deployments. Add a bearer
      token check that's a no-op when unset. ~1 day.
- [ ] **WebSocket live-update in the 3D explorer.** Today the page only
      fetches once. Wire up `/stream` so new orbs appear as the agent
      runs. ~1 day.
- [ ] **More framework adapters.** LangGraph, CrewAI, MCP. The
      `ReverieClient` covers most use cases but a native adapter feels
      better for major frameworks. ~2 days each.
- [ ] **Postgres backend option.** Same schema, swap the storage layer.
      Required for any team usage past a single dev's machine. ~3 days.
- [ ] **Run-deletion + retention policies.** Users will accumulate
      thousands of runs. Need a TTL + a "pin this one forever" feature.
      ~1 day.
- [ ] **Replay scrubber in the 3D view.** Drag a timeline at the bottom
      to roll the run forward/backward. The snapshot engine already
      supports it; just needs the UI. ~2 days.

## P2 — nice to have

- [ ] **Auto-redaction heuristic.** Recognise API-key-shaped strings,
      credit-card numbers, etc., and redact them before storage. ~1 day.
- [ ] **Run sharing via signed URLs.** Send a teammate a link to a
      specific run without giving them admin access to the backend.
      ~2 days.
- [ ] **Code-signed Windows binary.** Eliminates SmartScreen warning.
      $200/year for a cert + signing step in the release workflow.
- [ ] **Hosted demo environment** at `try.reverie-obs.dev` so people can
      poke around without running anything locally.
- [ ] **Native Anthropic adapter.** Auto-instrument the official Claude
      Python SDK the way we do for OpenAI Agents SDK.
- [ ] **Native Gemini adapter.** Same idea for `google-generativeai`.

---

## Things to test before going public

The 3D explorer + backend work end-to-end locally; what we *haven't*
hammered:

- [ ] Run with **10,000+ events** — does the 3D scene stay above 30 fps?
      (Currently tested up to ~500.)
- [ ] Run with **50+ subagents** — does clustering still produce a
      readable graph?
- [ ] **Concurrent agents** — multiple Python processes emitting events
      to the same backend. Should work (HTTP is fine with concurrency)
      but never stress-tested.
- [ ] **Long-running runs** (1+ hour). The backend is fine; verify the
      browser doesn't accumulate memory.
- [ ] **Real third-party adapters.** We've tested with our own examples;
      need a community dev to integrate with their actual production
      agent and report back.

---

## Documentation gaps

- [ ] **A 90-second video walkthrough.** Click → see → debug. Posted on
      the README.
- [ ] **A "Hello World" 5-minute tutorial** that doesn't require an API
      key. Use the synthetic example agents.
- [ ] **Architecture overview** — the 8-layer SRS exists, but
      a short diagram-heavy version for skimmers would help.
- [ ] **FAQ** — currently in the README, should be its own page once
      we hit ~10 questions.
- [ ] **Comparison page** vs. LangSmith / Langfuse / W&B Weave. People
      will ask. Better to answer pre-emptively.

---

## Prompts you can use to test the real examples

Drop these into `examples/real/<name>.py "..."` to drive realistic runs:

### `nvidia_streaming_agent.py`

```
"Walk me through how distributed-tracing systems track a request across
microservice boundaries, and what an equivalent for AI agents would
need to look like."
```

### `research_pipeline.py`

```
"agent observability tools comparison 2026"
"latest production patterns for RAG systems"
"how do agent frameworks handle long-running tasks"
```

### `code_review_agent.py`

```
python examples/real/code_review_agent.py path/to/your/real/file.py
```

### `rag_qa_agent.py`

```
"What is observability for AI agents and why does it matter?"      # on-topic
"How do I season a cast iron skillet?"                              # off-topic — triggers poison-memory anomaly
"Explain the difference between traces and spans"                   # mid-relevance
```

### `multi_agent_planner.py`

```
"Should mid-stage startups invest in agent observability?"
"What's the strongest case against multi-agent systems in production?"
```

---

## How to keep this list fresh

When you finish a thing, move it to the "done" snapshot at the top.
When you discover a new gap, add it to P1 or P2. Treat this file as
the single source of truth for "what's left."
