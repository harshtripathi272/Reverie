"""Reference agent producing ~500 events for the Phase 2 gate test.

A "complex" trace: 1 root mission goal, several subagent delegations,
many tool calls (some repeated for loop detection), and a few failures.
Used by the Phase 2 gate to verify ``reverie graph --level N`` produces
SRS-conforming cardinalities.

Run via:

    reverie run python examples/complex_agent.py
"""

from __future__ import annotations

import sys

from agents.tracing import agent_span, function_span, trace


def _do_subagent(name: str, *, n_tools: int) -> None:
    with agent_span(name=name):
        for i in range(n_tools):
            with function_span(name="search_web", input=f'{{"q":"q{i}"}}') as fn:
                fn.span_data.output = f"results-{i}"


def main() -> int:
    with trace("complex-mission", group_id="complex-session") as t:
        with agent_span(name="planner"):
            # Burst of repeated identical tool calls to trigger LOOP detector.
            for _ in range(6):
                with function_span(
                    name="ping_status", input='{"check":"db"}'
                ) as fn:
                    fn.span_data.output = "ok"

            # A handful of specialized subagents.
            _do_subagent("researcher", n_tools=12)
            _do_subagent("validator", n_tools=8)
            _do_subagent("writer", n_tools=6)

            # A few hot spots — large token counts, but the SDK doesn't track
            # tokens for synthetic spans, so the hotspot detector won't flag
            # these. That's fine — the LOOP and EXPLOSION detectors will.

            # A subagent that fails near the end.
            with agent_span(name="reviewer"):
                with function_span(name="approve", input='{"id":1}') as fn:
                    fn.set_error(
                        {"message": "policy violation", "data": None}
                    )

    print(f"\n--- Complex run done ---")
    print(f"trace_id: {t.trace_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
