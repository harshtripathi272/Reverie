# Integrating Reverie into your project

This is the contract. If you follow it, every Reverie feature works for you.

---

## When to use Reverie

Reverie is **observability + steering for autonomous AI agents**. Use it when:

- Your agent makes more than one LLM call per user request.
- It uses tools (function calls, code execution, search, retrieval).
- You'd find it useful to **replay** a failed run or **compare** two runs.
- You want users (or yourself) to be able to give feedback on agent
  decisions visually instead of by editing prompts.

Don't use it when:

- You're making single, deterministic LLM calls. Just log the request +
  response — no agent, no graph.
- You don't control the call site of your LLM calls. Reverie integrates
  by wrapping calls; if a third-party SDK hides them, you can't.

---

## The contract

To get value out of Reverie, your events have to follow three rules:

### 1. One run = one `runId`

A "run" is one user-visible task. Generate one UUID at the start, attach
it to every event you emit during that task. Don't reuse run IDs across
tasks.

```python
rev = ReverieClient(agent_id="my-bot")
rev.start_run(goal="Answer the user's question")  # generates a run_id
# ... all subsequent events automatically use rev.run_id
rev.complete_run()
```

### 2. Causal parent IDs must be honest

When event B happens **because of** event A, set `B.parentId = A.id`.

```python
goal_id = rev.goal("Find papers on AI safety")
# This tool call is in service of the goal:
tool_id = rev.tool_called("search_web", input={...}, parent_id=goal_id)
# This tool returned in response to that call:
rev.tool_returned("search_web", output=..., parent_id=tool_id)
```

The graph engine builds the cognitive DAG from these parent links. If
you fake them or skip them, the visualization, critical-path
computation, and fault-tree analysis all degrade.

### 3. Event types must be from the frozen v1.0 vocabulary

These 22 strings are the only valid event types:

```
goal.created, goal.updated, goal.completed, goal.failed
tool.called, tool.returned
memory.retrieved, memory.stored
retry.triggered
validation.passed, validation.failed
reflection.generated
reasoning.generated
subagent.spawned, subagent.completed
planning.started, planning.completed
context.overflow, context.compressed
decision.made
error.occurred
guardrail.triggered
```

The schema rejects anything else with HTTP 422. This vocabulary is the
common ground that makes runs comparable across frameworks.

If your agent does something none of these capture cleanly, **map it to
the closest match**. If you really need a new type, open an issue — we'll
add it as an additive change in a future schema version.

---

## How to map your framework's events

| Your framework's concept | Reverie event type |
|---|---|
| LLM call (any framework) | `tool.called` + `tool.returned` |
| Function/tool call | `tool.called` + `tool.returned` |
| Vector store query | `memory.retrieved` |
| Cache hit / write | `memory.stored` |
| LangChain `AgentAction` | `tool.called` |
| LangChain `AgentFinish` | `goal.completed` |
| LangGraph node enter/exit | `tool.called` + `tool.returned` |
| CrewAI task start/finish | `subagent.spawned` + `subagent.completed` |
| OpenAI assistant run step | `tool.called` (for actions) / `reasoning.generated` (for messages) |
| Anthropic tool_use block | `tool.called` |
| Gemini function call | `tool.called` |
| HTTP retry / backoff | `retry.triggered` |
| JSON-schema validation failure | `validation.failed` |
| Pydantic parse error | `validation.failed` |
| User confirmation prompt | `decision.made` |
| Content filter block | `guardrail.triggered` |
| Token-count summarisation | `context.compressed` |
| LLM hit context limit | `context.overflow` |
| Chain-of-thought capture | `reasoning.generated` |
| Self-critique step | `reflection.generated` |

---

## Performance and reliability rules

- **Never block on Reverie.** The emitter uses HTTP with a 2-second
  timeout. If the backend is down, events are dropped silently — your
  agent runs unchanged.
- **Don't over-instrument.** A 500-event run is great. A 50,000-event
  run will work but the 3D explorer slows down. Aggregate trivial
  events (e.g. one `memory.retrieved` per query, not one per chunk).
- **Match real timestamps.** Use UTC milliseconds since epoch for the
  `timestamp` field. The `ReverieClient` does this automatically.
- **Real token counts when you have them.** The salience scorer ranks
  events by resource consumption. Without `token_cost`, expensive calls
  don't surface as expensive.

---

## Agent-id strategy

`agent_id` is what `reverie guidance` and `reverie compare` use to group
runs. Pick it carefully.

**Good:**
- One `agent_id` per logical agent (`"customer-support-bot"`,
  `"research-pipeline-v2"`).
- Stable across runs of the same agent — that's how guidance accumulates.

**Bad:**
- Different `agent_id` per run (you lose all cross-run signal).
- Same `agent_id` across totally different agents (guidance bleeds
  between them).

If you have one logical agent serving multiple task types (research,
coding, support), pass a `tag` parameter to `rev.goal()` so guidance
can be scoped per topic.

---

## Privacy / data handling

The `payload` field is stored verbatim. If your prompts contain PII or
secrets, **redact before emitting**. Reverie does not do this for you.

```python
# Good — strip the API key from logged payloads:
rev.tool_called(
    "stripe.charge",
    input={"amount": 1000, "customer": customer_id},
    # NOT: input={"api_key": secret_key, ...}
    parent_id=goal_id,
)
```

A redaction helper is on the roadmap.

---

## Production deployment

For local development, the backend runs on `localhost:8000`. For
production:

1. Run `reverie-api` somewhere (Docker, Kubernetes, bare metal).
2. Set `REVERIE_BACKEND_URL=https://reverie.your-company.com` in your
   agent's environment.
3. Optionally configure auth headers via the `extra_headers` parameter
   (the OpenAI Agents SDK adapter has this; the simple `ReverieClient`
   doesn't yet — it's on the roadmap).

The backend is a single FastAPI process with a SQLite append-only log.
For low-volume internal use, this is fine on a small VM. For high
volume, you'd swap SQLite for Postgres — the schema layer is already
abstracted, the swap is a Phase 7 task on the roadmap.

---

## What to instrument vs. skip

**Always instrument:**
- Every LLM call (model + provider + token cost)
- Every tool call (name + args + result)
- Every retry
- Every memory retrieval / store
- Top-level goals + outcomes

**Skip:**
- Internal helper functions inside your code (those are normal logs)
- Per-token streaming events (one `tool.called` + one `tool.returned` is enough)
- Health checks and other infrastructure noise

If in doubt: instrument. The salience scorer hides low-importance events
in the 3D view by default, so over-instrumenting doesn't hurt the UX.
