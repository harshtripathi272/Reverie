"""Multi-agent pipeline: planner → researcher + writer.

This is the canonical "production" agent shape: a top-level orchestrator
that delegates to specialised sub-agents. In Reverie's 3D view, each
sub-agent's events form their own visual cluster around the spawn point,
so you can see at a glance which sub-agent did what.

Pipeline shape
--------------

    planner_agent.create_plan(query)
        │
        ├── researcher_agent.research(plan.research_question)
        │       └── 3 parallel search → fetch → summarise calls
        │
        └── writer_agent.write(query, research_results)

Why this is interesting for Reverie
-----------------------------------

- Each sub-agent emits events with the SAME run_id but logically nests
  under its spawning ``subagent.spawned`` event. The graph engine
  recognises this and creates a "subagent" cluster automatically.
- If the writer fails because the researcher returned bad data, the
  fault tree walks all the way back to the bad research call.
- ``reverie compare`` between two runs of this pipeline (different
  models, different temperatures) shows which sub-agent's output
  diverged.

Setup
-----

    export NVIDIA_API_KEY=<your key>
    python multi_agent_planner.py "Should we adopt agent observability?"
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Make ``reverie_emit`` importable when running from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reverie_emit import ReverieClient  # noqa: E402

from openai import OpenAI  # noqa: E402

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL = "bytedance/seed-oss-36b-instruct"


def _llm_call(
    client: OpenAI,
    rev: ReverieClient,
    *,
    parent_id: str,
    tool_name: str,
    prompt: str,
    temperature: float = 0.4,
    max_tokens: int = 800,
) -> str:
    """One instrumented LLM call. Returns the response text."""

    call_id = rev.tool_called(
        tool_name,
        input={"prompt": prompt[:200], "temperature": temperature},
        parent_id=parent_id,
    )
    started = time.time()
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = completion.choices[0].message.content or ""
        tokens = (
            getattr(completion.usage, "total_tokens", 0)
            if completion.usage
            else len(text.split())
        )
    except Exception as exc:
        rev.tool_returned(
            tool_name,
            output=None,
            latency_ms=(time.time() - started) * 1000,
            success=False,
            error_message=f"{type(exc).__name__}: {exc}",
            parent_id=call_id,
        )
        raise

    rev.tool_returned(
        tool_name,
        output={"text": text[:300] + ("…" if len(text) > 300 else "")},
        latency_ms=(time.time() - started) * 1000,
        token_cost=tokens,
        parent_id=call_id,
    )
    return text.strip()


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


def planner_agent(client: OpenAI, rev: ReverieClient, query: str, parent_id: str) -> dict:
    """Decides what research questions to ask + plan of attack."""

    sub_id = rev.subagent_spawned(
        agent_type="planner",
        task="Decompose the query into research sub-questions",
        parent_id=parent_id,
    )
    plan_text = _llm_call(
        client,
        rev,
        parent_id=sub_id or parent_id,
        tool_name=f"{MODEL}.plan",
        prompt=(
            f"Given the query: '{query}'\n\n"
            f"List exactly 3 specific research sub-questions that would help "
            f"answer it. Output as a numbered list, no other text."
        ),
        temperature=0.4,
    )
    rev.reasoning(
        summary=plan_text[:200],
        model_id=MODEL,
        parent_id=sub_id or parent_id,
    )
    questions = [
        line.split(".", 1)[1].strip()
        for line in plan_text.splitlines()
        if line.strip() and line.strip()[0].isdigit() and "." in line
    ][:3]
    return {"sub_id": sub_id, "questions": questions or [query]}


def researcher_agent(
    client: OpenAI,
    rev: ReverieClient,
    questions: list[str],
    parent_id: str,
) -> list[str]:
    """Answers each research sub-question with a focused LLM call."""

    sub_id = rev.subagent_spawned(
        agent_type="researcher",
        task=f"Answer {len(questions)} research questions",
        parent_id=parent_id,
    )
    answers: list[str] = []
    for q in questions:
        try:
            ans = _llm_call(
                client,
                rev,
                parent_id=sub_id or parent_id,
                tool_name=f"{MODEL}.research_answer",
                prompt=(
                    f"Answer the following research question concisely (3-5 sentences). "
                    f"Be concrete and factual.\n\nQuestion: {q}"
                ),
                temperature=0.3,
                max_tokens=400,
            )
            answers.append(f"Q: {q}\nA: {ans}")
        except Exception as exc:
            rev.error(message=f"researcher failed on '{q}': {exc}", parent_id=sub_id)
            answers.append(f"Q: {q}\nA: (no answer — call failed)")
    return answers


def writer_agent(
    client: OpenAI,
    rev: ReverieClient,
    query: str,
    research: list[str],
    parent_id: str,
) -> str:
    """Composes the final answer using the researcher's outputs."""

    sub_id = rev.subagent_spawned(
        agent_type="writer",
        task="Synthesise final answer from research",
        parent_id=parent_id,
    )
    prompt = (
        f"You are writing a one-paragraph executive answer to: '{query}'\n\n"
        f"Use the following research notes as your source of truth:\n\n"
        + "\n\n---\n\n".join(research)
        + "\n\nWrite the final answer below. Be concrete. No hedging."
    )
    text = _llm_call(
        client,
        rev,
        parent_id=sub_id or parent_id,
        tool_name=f"{MODEL}.compose",
        prompt=prompt,
        temperature=0.5,
        max_tokens=600,
    )
    rev.reflection(
        insight=f"Final answer is {len(text)} chars, drawn from {len(research)} research notes",
        parent_id=sub_id or parent_id,
    )
    return text


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


def run(query: str) -> str:
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        print("error: NVIDIA_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)
    rev = ReverieClient(agent_id="multi-agent-planner", runtime="nvidia-nim")
    rev.start_run(goal=f"Multi-agent answer for: {query}")

    goal_id = rev.goal(intent=query)

    try:
        plan = planner_agent(client, rev, query, parent_id=goal_id)
        research = researcher_agent(
            client, rev, plan["questions"], parent_id=goal_id
        )
        answer = writer_agent(client, rev, query, research, parent_id=goal_id)
    except Exception as exc:
        rev.goal_failed(parent_id=goal_id, reason=str(exc))
        rev.complete_run(status="failed")
        raise

    rev.goal_completed(parent_id=goal_id, outcome=f"Answered: {answer[:60]}…")
    rev.complete_run()
    rev.close()

    print("\n========== ANSWER ==========\n")
    print(answer)
    print("\n============================\n")
    print(f"[reverie] run id: {rev.run_id}")
    print(f"[reverie] view at: http://localhost:3000/run?id={rev.run_id}")
    return answer


if __name__ == "__main__":
    query = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Should mid-stage startups invest in agent observability?"
    )
    run(query)
