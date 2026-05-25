"""NVIDIA NIM agent with Reverie instrumentation.

Demonstrates:

  - Streaming completions from NVIDIA's hosted ``bytedance/seed-oss-36b-instruct``
  - Capturing the model's reasoning trace (the ``reasoning_content`` field)
  - Reporting timing, token cost, and final output to Reverie

Why this is useful
------------------

NVIDIA NIM (and OpenAI-compatible endpoints in general) don't ship with
any agent observability. You stream tokens and that's it. Wrap the call
site with Reverie and you get:

  - The exact prompt and final output saved to the run
  - The model's reasoning text captured separately from its answer
  - A 3D orb you can click to see the entire payload
  - Failure replay if the call timed out, hit a content filter, etc.

Setup
-----

    export NVIDIA_API_KEY=<your key from build.nvidia.com>
    pip install openai httpx
    # Copy ../reverie_emit.py into the same folder as this file
    python nvidia_streaming_agent.py

Then open http://localhost:3000 to see the run.
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


def run(prompt: str, *, agent_id: str = "nvidia-seed-bot") -> str:
    """Stream a completion from NVIDIA NIM and emit Reverie events.

    Returns the final assembled answer text.
    """

    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        print(
            "error: NVIDIA_API_KEY env var is not set.\n"
            "       get one from https://build.nvidia.com",
            file=sys.stderr,
        )
        sys.exit(1)

    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)

    rev = ReverieClient(agent_id=agent_id, runtime="nvidia-nim")
    rev.start_run(goal=f"Answer: {prompt[:80]}")

    goal_id = rev.goal(intent=prompt[:120])

    # Single tool call: the LLM completion itself. Streaming, so we record
    # the start when we kick it off, then the end when the stream closes.
    tool_id = rev.tool_called(
        f"{MODEL}.complete",
        input={
            "model": MODEL,
            "prompt": prompt,
            "temperature": 1.1,
            "top_p": 0.95,
            "max_tokens": 4096,
            "stream": True,
        },
        parent_id=goal_id,
    )

    started_at = time.time()
    reasoning_chunks: list[str] = []
    answer_chunks: list[str] = []
    failed = False
    error_message: str | None = None

    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1.1,
            top_p=0.95,
            max_tokens=4096,
            frequency_penalty=0,
            presence_penalty=0,
            stream=True,
            extra_body={"thinking_budget": -1},
        )

        for chunk in completion:
            delta = chunk.choices[0].delta
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                reasoning_chunks.append(reasoning)
                # Mirror to stdout so the user can see the model thinking.
                print(reasoning, end="", flush=True)
            if delta.content is not None:
                answer_chunks.append(delta.content)
                print(delta.content, end="", flush=True)
        print()  # newline after the stream
    except Exception as exc:
        failed = True
        error_message = f"{type(exc).__name__}: {exc}"

    latency_ms = (time.time() - started_at) * 1000.0
    answer = "".join(answer_chunks)
    reasoning_text = "".join(reasoning_chunks).strip()

    rev.tool_returned(
        f"{MODEL}.complete",
        output={"text": answer, "length": len(answer)},
        latency_ms=latency_ms,
        # NVIDIA NIM doesn't return usage in stream mode; set None and let
        # the salience scorer ignore the token-cost dimension here.
        token_cost=None,
        success=not failed,
        error_message=error_message,
        parent_id=goal_id,
        duration_ms=latency_ms,
    )

    # Capture the model's chain-of-thought as a separate reasoning event so
    # it shows up as its own purple orb in the 3D view.
    if reasoning_text:
        rev.reasoning(
            summary=_truncate(reasoning_text, 300),
            model_id=MODEL,
            parent_id=goal_id,
        )

    if failed:
        rev.goal_failed(parent_id=goal_id, reason=error_message or "unknown")
        rev.complete_run(status="failed")
        raise SystemExit(1)

    rev.goal_completed(
        parent_id=goal_id,
        outcome=_truncate(answer, 80),
    )
    rev.complete_run()
    rev.close()

    print(f"\n[reverie] run id: {rev.run_id}")
    print(f"[reverie] view at: http://localhost:3000/run?id={rev.run_id}")
    return answer


def _truncate(text: str, n: int) -> str:
    text = text.strip().replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


if __name__ == "__main__":
    prompt = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Explain in 3 bullet points why graph-based observability matters for AI agents."
    )
    run(prompt)
