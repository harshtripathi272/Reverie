# reverie-adapter-openai

Zero-config Reverie instrumentation for the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/).

## Use

```python
import reverie_openai
reverie_openai.auto()

# ... your normal Agents SDK code below ...
from agents import Agent, Runner
agent = Agent(name="my-agent", instructions="...")
result = await Runner.run(agent, "Do the thing.")
```

That's it. Every span produced by the SDK is translated into a Reverie
`CognitiveEvent` and posted to the backend (default `http://127.0.0.1:8000`).

## What you get

| SDK span type | CognitiveEvent on start | CognitiveEvent on end |
|---|---|---|
| `agent`     | `goal.created`     | `goal.completed` / `goal.failed`     |
| `function`  | `tool.called`      | `tool.returned`  / `tool.failed`     |
| `handoff`   | `subagent.spawned` | `subagent.completed`                 |
| `generation`| —                  | `reasoning.extracted`                |
| `response`  | —                  | `reasoning.extracted`                |
| `guardrail` | —                  | `validation.passed` / `validation.failed` |
| Other types | (wrapped in `GenericPayload` for forward-compat) |

The full event tree (`parentId` + `depth`) is preserved.

## Resilience

- Events are posted in **batches of up to 50** every ~100ms.
- The emitter runs in a **daemon thread** with its own asyncio loop —
  the agent is never blocked.
- If the backend is unreachable, events are **dropped silently**. The agent
  always runs to completion.
- A bounded queue (10k events default) protects against memory blow-up.

## Configuration

All optional, set as env vars before `reverie_openai.auto()`:

| Var | Default | Description |
|---|---|---|
| `REVERIE_BACKEND_URL` | `http://127.0.0.1:8000` | Backend base URL |
| `REVERIE_AGENT_ID`    | `openai-agent`          | Default agent id label |
| `REVERIE_QUEUE_SIZE`  | `10000`                 | Max queued events |
| `REVERIE_BATCH_SIZE`  | `50`                    | Max events per POST |
| `REVERIE_FLUSH_MS`    | `100`                   | Max wait between flushes |
| `REVERIE_DISABLED`    | (unset)                 | If set to `1`, the adapter does nothing |

## Install

```
uv pip install -e ".[dev]"
pytest
```
