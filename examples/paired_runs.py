"""Twin agents for the Phase 3+4 gate test.

Two synthetic runs with the **same goal** but different paths:

  run A: cleanly searches, reads, writes a summary -> SUCCESS.
  run B: searches, reads, then a brittle citation tool fails -> FAILURE.

Run via:

    reverie run python examples/paired_runs.py
"""

from __future__ import annotations

import sys

from agents.tracing import agent_span, function_span, trace


def _run_a() -> str:
    with trace("paired-mission", group_id="paired-session-a") as t:
        with agent_span(name="planner"):
            with function_span(name="search_web", input='{"q":"observability"}') as fn:
                fn.span_data.output = "found 3 articles"
            with function_span(name="read_article", input='{"id":"art-1"}') as fn:
                fn.span_data.output = "summary..."
            with function_span(name="write_summary", input='{"title":"Observability 2026"}') as fn:
                fn.span_data.output = "summary written"
    return t.trace_id


def _run_b() -> str:
    with trace("paired-mission", group_id="paired-session-b") as t:
        with agent_span(name="planner"):
            with function_span(name="search_web", input='{"q":"observability"}') as fn:
                fn.span_data.output = "found 3 articles"
            with function_span(name="read_article", input='{"id":"art-1"}') as fn:
                fn.span_data.output = "summary..."
            with function_span(name="cite_source", input='{"id":"art-1"}') as fn:
                fn.set_error({"message": "citation database is offline", "data": None})
    return t.trace_id


def main() -> int:
    a = _run_a()
    b = _run_b()
    print(f"\n--- Paired runs done ---")
    print(f"trace_id A (success): {a}")
    print(f"trace_id B (failure): {b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
