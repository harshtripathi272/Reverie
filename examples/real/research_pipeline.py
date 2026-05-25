"""End-to-end research pipeline with Reverie instrumentation.

Pipeline shape (this is what real agents look like in production):

    Goal → search_web → for each result: fetch_url → summarise → write_report

Each step is a tool call; failures are realistic (rate limits, 404s,
truncations); the final report depends on the partial successes upstream.

Why this is the canonical "real" example
----------------------------------------

It hits every Reverie feature naturally:

  * Critical path — the chain of events that produced the final report
  * Salience — failed fetches and slow URLs surface as high-importance
  * Anomalies — if 3 fetches fail in a row, the loop detector flags it
  * Comparison — run twice with different model temperatures and use
    ``reverie compare`` to see what changed
  * Annotations — if the agent fetches the wrong URL, click the orb,
    mark it "avoid", and the next run gets that guidance

Setup
-----

    export NVIDIA_API_KEY=<your key>
    pip install openai httpx
    python research_pipeline.py "AI agent observability"

Open http://localhost:3000 to view the orb world.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

# Make ``reverie_emit`` importable when running from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reverie_emit import ReverieClient  # noqa: E402

from openai import OpenAI  # noqa: E402


NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL = "bytedance/seed-oss-36b-instruct"


@dataclass
class Source:
    url: str
    title: str
    excerpt: str


# ---------------------------------------------------------------------------
# Fake tool implementations — replace with real DuckDuckGo / Tavily / Brave.
# ---------------------------------------------------------------------------


def search_web(query: str, *, limit: int = 4) -> list[Source]:
    """Stand-in for a real search-engine call.

    In production you'd use Tavily / Brave / SerpAPI / DuckDuckGo. Output
    shape is what matters — the rest of the pipeline doesn't care which
    provider you pick.
    """

    # We use a stable list so the example is reproducible. A real one
    # would pass ``query`` through to the search provider.
    return [
        Source(
            url="https://opentelemetry.io/docs/concepts/observability-primer/",
            title="OpenTelemetry — Observability Primer",
            excerpt="Observability lets us understand a system from the outside…",
        ),
        Source(
            url="https://www.honeycomb.io/blog/what-is-observability",
            title="Honeycomb — What is observability?",
            excerpt="Observability is your ability to understand a system's behavior…",
        ),
        Source(
            url="https://blog.langchain.dev/agent-observability/",
            title="LangChain Blog — Agent observability",
            excerpt="As agents grow more complex, observability becomes essential…",
        ),
        Source(
            url="https://example.invalid/this-will-404",
            title="A page that doesn't exist",
            excerpt="(this URL will fail to fetch — useful for showing "
            "Reverie's failure visualisation)",
        ),
    ][:limit]


def fetch_url(url: str, *, timeout: float = 5.0) -> tuple[bool, str, int]:
    """Fetch a URL. Returns (ok, body_or_error, latency_ms)."""

    started = time.time()
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        latency_ms = int((time.time() - started) * 1000)
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}", latency_ms
        return True, resp.text[:8000], latency_ms
    except Exception as exc:
        latency_ms = int((time.time() - started) * 1000)
        return False, f"{type(exc).__name__}: {exc}", latency_ms


# ---------------------------------------------------------------------------
# LLM-backed steps
# ---------------------------------------------------------------------------


def summarise_chunk(client: OpenAI, source: Source, body: str) -> tuple[str, int]:
    """Call the LLM to summarise one fetched page. Returns (summary, tokens)."""

    prompt = (
        f"Summarise the following article in 2 sentences. "
        f"Focus on what's specifically said about agent observability.\n\n"
        f"Title: {source.title}\nURL: {source.url}\n\n"
        f"---\n{body[:6000]}\n---"
    )

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=400,
    )
    text = completion.choices[0].message.content or ""
    tokens = (
        getattr(completion.usage, "total_tokens", 0)
        if completion.usage
        else len(text.split())
    )
    return text.strip(), int(tokens)


def write_report(client: OpenAI, query: str, summaries: list[tuple[Source, str]]) -> tuple[str, int]:
    """Synthesise the final report from the per-source summaries."""

    body_lines = [f"# Research report: {query}", ""]
    for src, summary in summaries:
        body_lines.append(f"## {src.title}\n{src.url}\n\n{summary}\n")
    bundled = "\n".join(body_lines)

    prompt = (
        f"You are writing a one-page briefing on the topic '{query}'. "
        f"Synthesize the following per-source notes into a cohesive briefing. "
        f"Use markdown headings. Be concrete.\n\n{bundled}"
    )

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=1200,
    )
    text = completion.choices[0].message.content or ""
    tokens = (
        getattr(completion.usage, "total_tokens", 0)
        if completion.usage
        else len(text.split())
    )
    return text.strip(), int(tokens)


# ---------------------------------------------------------------------------
# The pipeline, fully instrumented
# ---------------------------------------------------------------------------


def run(query: str) -> str:
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        print(
            "error: NVIDIA_API_KEY is not set. "
            "Get one at https://build.nvidia.com.",
            file=sys.stderr,
        )
        sys.exit(1)

    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)
    rev = ReverieClient(agent_id="research-pipeline", runtime="nvidia-nim")
    rev.start_run(goal=f"Research briefing on: {query}")

    # ---- Top-level goal.
    goal_id = rev.goal(f"Produce a one-page briefing on '{query}'")

    # ---- Step 1: search.
    search_call = rev.tool_called(
        "search_web", input={"query": query, "limit": 4}, parent_id=goal_id
    )
    search_started = time.time()
    sources = search_web(query, limit=4)
    rev.tool_returned(
        "search_web",
        output={
            "results": [
                {"url": s.url, "title": s.title, "excerpt": s.excerpt[:120]}
                for s in sources
            ],
            "count": len(sources),
        },
        latency_ms=(time.time() - search_started) * 1000,
        parent_id=goal_id,
    )

    # ---- Step 2: per-source fetch + summarise. Failures are expected.
    summaries: list[tuple[Source, str]] = []
    for source in sources:
        # fetch_url
        fetch_call = rev.tool_called(
            "fetch_url", input={"url": source.url}, parent_id=goal_id
        )
        ok, body_or_error, latency_ms = fetch_url(source.url)
        rev.tool_returned(
            "fetch_url",
            output={
                "url": source.url,
                "status": "ok" if ok else "failed",
                "length": len(body_or_error) if ok else 0,
                "error": None if ok else body_or_error,
            },
            latency_ms=latency_ms,
            success=ok,
            error_message=None if ok else body_or_error,
            parent_id=fetch_call,
            duration_ms=latency_ms,
        )

        if not ok:
            # In a real agent you might retry here; we just skip the source.
            rev.retry(
                reason=f"fetch failed for {source.url}",
                attempt=1,
                max_attempts=1,
                parent_id=fetch_call,
            )
            continue

        # summarise
        sum_call = rev.tool_called(
            f"{MODEL}.summarise",
            input={"url": source.url, "title": source.title},
            parent_id=fetch_call,
        )
        sum_started = time.time()
        try:
            summary, tokens = summarise_chunk(client, source, body_or_error)
        except Exception as exc:
            rev.tool_returned(
                f"{MODEL}.summarise",
                output=None,
                latency_ms=(time.time() - sum_started) * 1000,
                success=False,
                error_message=f"{type(exc).__name__}: {exc}",
                parent_id=sum_call,
            )
            continue
        rev.tool_returned(
            f"{MODEL}.summarise",
            output={"summary": summary},
            latency_ms=(time.time() - sum_started) * 1000,
            token_cost=tokens,
            parent_id=sum_call,
        )
        summaries.append((source, summary))

    if not summaries:
        rev.goal_failed(parent_id=goal_id, reason="every source failed to fetch")
        rev.complete_run(status="failed")
        print("error: no sources retrieved", file=sys.stderr)
        sys.exit(1)

    # ---- Step 3: synthesize the final report.
    report_call = rev.tool_called(
        f"{MODEL}.write_report",
        input={"query": query, "source_count": len(summaries)},
        parent_id=goal_id,
    )
    report_started = time.time()
    try:
        report, tokens = write_report(client, query, summaries)
    except Exception as exc:
        rev.tool_returned(
            f"{MODEL}.write_report",
            output=None,
            latency_ms=(time.time() - report_started) * 1000,
            success=False,
            error_message=f"{type(exc).__name__}: {exc}",
            parent_id=report_call,
        )
        rev.goal_failed(parent_id=goal_id, reason="report writer crashed")
        rev.complete_run(status="failed")
        raise

    rev.tool_returned(
        f"{MODEL}.write_report",
        output={"length": len(report), "preview": report[:200]},
        latency_ms=(time.time() - report_started) * 1000,
        token_cost=tokens,
        parent_id=report_call,
    )

    # ---- Reflect + complete.
    rev.reflection(
        insight=(
            f"Summarised {len(summaries)} of {len(sources)} sources successfully; "
            f"final briefing is {len(report)} characters."
        ),
        parent_id=goal_id,
    )
    rev.goal_completed(parent_id=goal_id, outcome=f"Briefing on {query} ready")
    rev.complete_run()
    rev.close()

    print("\n========== REPORT ==========\n")
    print(report)
    print("\n============================\n")
    print(f"[reverie] run id: {rev.run_id}")
    print(f"[reverie] view at: http://localhost:3000/run?id={rev.run_id}")
    return report


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "AI agent observability"
    run(query)
