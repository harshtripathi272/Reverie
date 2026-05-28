"""Reverie demo — designed for video recording.

Packs every visual feature of Reverie into one ~50-event run:

  - 1 main goal + 1 sub-goal             → violet orbs
  - 3 subagents (planner/researcher/writer) → teal cluster centres
  - ~10 tool calls (LLM + search + fetch + summarise) → cyan orbs
  - 4 memory retrievals → emerald orbs
  - 2 retries (one resolves, one fails)  → amber orbs
  - 2 validation checks                  → mid orbs
  - 1 deliberate failure cascade         → red orbs (impossible to miss)
  - 3 reasoning summaries                → purple orbs
  - 2 reflections                        → purple
  - critical-path running through ~12 events → bright thicker connections

Total: ~50 orbs across 3 clusters with varied colors and one cascading
failure. Perfect for a 60-second screen-record where you fly the camera
around, click orbs to show the detail panel, and demonstrate the
annotation flow.

Setup
-----

    $env:NVIDIA_API_KEY = "your-key"
    .venv\Scripts\python.exe examples/real/demo_recording.py

Or without an API key (synthetic LLM calls — fully reproducible):

    .venv\Scripts\python.exe examples/real/demo_recording.py --synthetic

The synthetic version is faster and more reliable for recording — it
adds realistic timing but doesn't hit the network for the LLM calls.
"""

from __future__ import annotations

import os
import random
import sys
import time
from pathlib import Path

# Make ``reverie_emit`` importable when running from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reverie_emit import ReverieClient  # noqa: E402

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL = "bytedance/seed-oss-36b-instruct"


# ---------------------------------------------------------------------------
# A predictable LLM stand-in for synthetic mode
# ---------------------------------------------------------------------------


def _fake_llm_call(prompt: str, *, latency_range: tuple[float, float] = (0.3, 1.2)) -> tuple[str, int]:
    """Pretend to call an LLM. Sleeps a realistic amount, returns text + tokens."""

    delay = random.uniform(*latency_range)
    time.sleep(delay)
    text = f"[synthetic answer to: {prompt[:60]}]"
    tokens = random.randint(120, 800)
    return text, tokens


def _real_llm_call(prompt: str, client) -> tuple[str, int]:
    """Hit NVIDIA NIM for a real completion."""

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=400,
    )
    text = completion.choices[0].message.content or ""
    tokens = (
        getattr(completion.usage, "total_tokens", 0)
        if completion.usage
        else len(text.split())
    )
    return text.strip(), int(tokens)


# ---------------------------------------------------------------------------
# The orchestrated demo run
# ---------------------------------------------------------------------------


def run(*, synthetic: bool = False) -> str:
    if synthetic:
        client = None
    else:
        api_key = os.environ.get("NVIDIA_API_KEY")
        if not api_key:
            print(
                "error: NVIDIA_API_KEY not set. Pass --synthetic for the no-API version.",
                file=sys.stderr,
            )
            sys.exit(1)
        from openai import OpenAI

        client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)

    def llm(prompt: str) -> tuple[str, int]:
        if synthetic:
            return _fake_llm_call(prompt)
        return _real_llm_call(prompt, client)

    rev = ReverieClient(agent_id="reverie-demo", runtime="demo")
    rev.start_run(goal="Produce a research briefing on agent observability")

    # ============================================================ TOP GOAL
    main_goal = rev.goal(
        "Produce a comprehensive research briefing on AI agent observability tools",
        priority="high",
    )
    rev.reasoning(
        summary=(
            "I'll decompose this into planning, research, and writing phases. "
            "Each phase will be a sub-agent."
        ),
        model_id=MODEL if not synthetic else "synthetic",
        parent_id=main_goal,
    )

    # ============================================================ PLANNER SUBAGENT
    planner = rev.subagent_spawned(
        agent_type="planner",
        task="Decompose the briefing into 4 research questions",
        parent_id=main_goal,
    )
    plan_goal = rev.goal(
        "Produce 4 specific research questions",
        parent_id=planner,
    )

    # planner LLM call
    plan_call = rev.tool_called(
        f"{MODEL}.plan",
        input={"task": "decompose briefing", "depth": 4},
        parent_id=plan_goal,
    )
    started = time.time()
    text, tokens = llm("List 4 research questions on agent observability")
    rev.tool_returned(
        f"{MODEL}.plan",
        output={"plan": text[:200]},
        latency_ms=(time.time() - started) * 1000,
        token_cost=tokens,
        parent_id=plan_call,
    )

    # validation: did we get exactly 4 questions back?
    val_call = rev.tool_called(
        "validate_plan_structure",
        input={"expected_questions": 4},
        parent_id=plan_goal,
    )
    rev.tool_returned(
        "validate_plan_structure",
        output={"questions_found": 4, "valid": True},
        success=True,
        parent_id=val_call,
    )

    rev.goal_completed(parent_id=plan_goal, outcome="4 questions identified")

    # ============================================================ RESEARCHER SUBAGENT
    researcher = rev.subagent_spawned(
        agent_type="researcher",
        task="Answer each research question with sources",
        parent_id=main_goal,
    )

    questions = [
        "What is agent observability?",
        "Compare LangSmith, Langfuse, and Reverie",
        "What are the failure modes in agent runs?",
        "How does cognitive event modeling work?",
    ]

    for i, q in enumerate(questions):
        # Each question gets its own goal node
        q_goal = rev.goal(intent=q[:80], parent_id=researcher)

        # 1. Memory retrieval
        rev.memory_retrieved(
            query=q,
            results=[
                {"id": f"doc-{i}-1", "title": f"Document about {q[:30]}", "score": 0.87 - i * 0.05},
                {"id": f"doc-{i}-2", "title": "Adjacent topic", "score": 0.62},
            ],
            parent_id=q_goal,
        )

        # 2. Web search
        search_call = rev.tool_called(
            "search_web",
            input={"query": q, "limit": 3},
            parent_id=q_goal,
        )
        time.sleep(0.2)
        rev.tool_returned(
            "search_web",
            output={
                "results": [
                    {"url": f"https://example.com/post-{i}", "title": "First hit"},
                    {"url": f"https://example.com/post-{i}-b", "title": "Second hit"},
                ],
                "count": 2,
            },
            latency_ms=240,
            parent_id=search_call,
        )

        # 3. Fetch first URL — question 3 gets a deliberate 404 to show failure flow
        is_failure_question = i == 2
        fetch_call = rev.tool_called(
            "fetch_url",
            input={"url": f"https://example.com/post-{i}"},
            parent_id=q_goal,
        )
        time.sleep(0.15)
        if is_failure_question:
            # FAILURE CASCADE — fetch fails, retry fails, the LLM call below
            # propagates the failure upward.
            rev.tool_returned(
                "fetch_url",
                output={"status": "failed", "error": "HTTP 404"},
                latency_ms=180,
                success=False,
                error_message="HTTP 404",
                parent_id=fetch_call,
            )
            # Retry attempt
            retry_id = rev.retry(
                reason="404 on fetch_url, trying alternate mirror",
                attempt=2,
                max_attempts=3,
                parent_id=fetch_call,
            )
            retry_fetch = rev.tool_called(
                "fetch_url",
                input={"url": f"https://example.com/post-{i}-mirror"},
                parent_id=retry_id,
            )
            time.sleep(0.2)
            rev.tool_returned(
                "fetch_url",
                output={"status": "failed", "error": "HTTP 503 Service Unavailable"},
                latency_ms=210,
                success=False,
                error_message="HTTP 503",
                parent_id=retry_fetch,
            )
            # Validation says we cannot continue
            rev.error(
                message="Both primary and mirror URLs unreachable. Skipping question.",
                parent_id=q_goal,
            )
            rev.goal_failed(
                parent_id=q_goal,
                reason="No fetchable sources for this question",
            )
            continue

        # Happy path: fetch succeeded
        rev.tool_returned(
            "fetch_url",
            output={"status": "ok", "length": 12_400},
            latency_ms=320,
            parent_id=fetch_call,
        )

        # 4. Summarise via LLM
        sum_call = rev.tool_called(
            f"{MODEL}.summarise",
            input={"url": f"https://example.com/post-{i}"},
            parent_id=q_goal,
        )
        started = time.time()
        text, tokens = llm(f"Summarise the article on {q}")
        rev.tool_returned(
            f"{MODEL}.summarise",
            output={"summary": text[:200]},
            latency_ms=(time.time() - started) * 1000,
            token_cost=tokens,
            parent_id=sum_call,
        )

        rev.goal_completed(parent_id=q_goal, outcome=f"Answered: {q[:50]}")

    rev.reflection(
        insight=(
            "Researched 3 of 4 questions successfully. "
            "Question 3 was abandoned due to upstream service failures."
        ),
        parent_id=researcher,
    )

    # ============================================================ WRITER SUBAGENT
    writer = rev.subagent_spawned(
        agent_type="writer",
        task="Synthesize the briefing from research notes",
        parent_id=main_goal,
    )
    write_goal = rev.goal(
        "Compose final briefing document",
        parent_id=writer,
    )

    # Memory: pull all the summaries we generated
    rev.memory_retrieved(
        query="all research summaries from this run",
        results=[
            {"id": "summary-0", "title": "What is observability"},
            {"id": "summary-1", "title": "Tool comparison"},
            {"id": "summary-3", "title": "Cognitive event modeling"},
        ],
        parent_id=write_goal,
    )

    # The final compose call (the most expensive call in the run)
    compose_call = rev.tool_called(
        f"{MODEL}.compose",
        input={"section_count": 4, "tone": "executive briefing"},
        parent_id=write_goal,
    )
    started = time.time()
    text, tokens = llm("Synthesize a one-page executive briefing on agent observability")
    rev.tool_returned(
        f"{MODEL}.compose",
        output={"briefing_length": 2400, "section_count": 4},
        latency_ms=(time.time() - started) * 1000,
        token_cost=int(tokens * 1.5),  # the compose call is more expensive
        parent_id=compose_call,
    )

    # Final validation: did we produce something usable?
    val_call = rev.tool_called(
        "validate_briefing_quality",
        input={"min_length": 1000},
        parent_id=write_goal,
    )
    rev.tool_returned(
        "validate_briefing_quality",
        output={"length": 2400, "passed": True, "checks": ["length", "sections", "citations"]},
        success=True,
        parent_id=val_call,
    )

    rev.reflection(
        insight=(
            "Briefing complete. 3 of 4 sections fully grounded; "
            "section on failure modes flagged as incomplete."
        ),
        parent_id=writer,
    )
    rev.goal_completed(parent_id=write_goal, outcome="Briefing ready")

    # ============================================================ DONE
    rev.goal_completed(
        parent_id=main_goal,
        outcome="Research briefing produced (3 of 4 questions covered)",
    )
    rev.complete_run()
    rev.close()

    print()
    print(f"[reverie] run id: {rev.run_id}")
    print(f"[reverie] view at: http://localhost:3000/run?id={rev.run_id}")
    print(f"[reverie] events emitted: ~50")
    print()
    print("Things to demo in your video:")
    print("  1. Orbit the camera around all 3 clusters (planner / researcher / writer)")
    print("  2. Click the red orb in the researcher cluster -- show fault tree")
    print("  3. Shift-click 4 nodes in the failed question -- bulk-tag as 'avoid'")
    print("  4. Run it again with REVERIE_USE_GUIDANCE=1 -- show the prompt prefix")
    return rev.run_id


if __name__ == "__main__":
    synthetic = "--synthetic" in sys.argv
    run(synthetic=synthetic)
