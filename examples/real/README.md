# Real-world Reverie examples

These aren't toy demos. Each one is a realistic agent shape you'd actually
ship. They use real provider APIs (NVIDIA NIM, OpenAI, Anthropic, Gemini),
real tools (web search, file ops, RAG), and produce events that look like
production traces.

## Prerequisites

```bash
# 1. The Reverie backend running somewhere:
reverie start --no-browser

# 2. The emitter installed in your project's environment:
pip install httpx
# (once reverie-schema lands on PyPI:)
# pip install reverie-obs
```

For now, copy `examples/reverie_emit.py` into your project and import
`ReverieClient` from it. Once `reverie-obs` is fully published, you'll
just `pip install reverie-obs` and `from reverie_obs import ReverieClient`.

## Examples in this folder

| File | What it shows |
|---|---|
| [`nvidia_streaming_agent.py`](./nvidia_streaming_agent.py) | NVIDIA NIM (`bytedance/seed-oss-36b-instruct`) with streaming + reasoning capture. Demonstrates `reasoning.generated` + `tool.called/returned`. |
| [`research_pipeline.py`](./research_pipeline.py) | Real research agent: web search → fetch URLs → summarise → write report. Shows critical-path computation when subagents fail. |
| [`code_review_agent.py`](./code_review_agent.py) | Static analyser + LLM reviewer. Demonstrates `validation.passed/failed` + retry logic that the salience scorer flags. |
| [`rag_qa_agent.py`](./rag_qa_agent.py) | Vector-store retrieval + answer generation. Demonstrates `memory.retrieved` and how poison-memory anomalies surface. |
| [`multi_agent_planner.py`](./multi_agent_planner.py) | Planner spawns researcher + writer. Demonstrates `subagent.spawned/completed` and how the 3D view clusters per-subagent. |

## How they're structured

Every example follows the same pattern:

```python
from reverie_emit import ReverieClient

rev = ReverieClient(agent_id="my-agent-name", runtime="...")
rev.start_run(goal="What this run is trying to do")

try:
    goal_id = rev.goal("Top-level objective")

    # Each LLM call:
    tool_id = rev.tool_called("provider.model", input={...}, parent_id=goal_id)
    response = your_llm.call(...)
    rev.tool_returned("provider.model", output=..., token_cost=..., parent_id=goal_id)

    # Optional: capture model reasoning when available
    rev.reasoning(summary="...", model_id="...", parent_id=goal_id)

    rev.goal_completed(parent_id=goal_id, outcome="...")
except Exception as e:
    rev.error(str(e), parent_id=goal_id)
    rev.complete_run(status="failed")
    raise

rev.complete_run()
```

The instrumentation is ~10% of your code. Everything else is your normal
agent logic.
