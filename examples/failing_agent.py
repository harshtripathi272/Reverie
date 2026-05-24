"""Reference agent that intentionally fails partway through.

Used by Phase 1's gate test: a developer must be able to ``reverie replay
<id> --jump-failure`` and identify the failure event without any visual UI.

Run it via:

    reverie run python examples/failing_agent.py
"""

from __future__ import annotations

import sys

from agents.tracing import agent_span, function_span, trace


def main() -> int:
    with trace("failing-research-workflow", group_id="failing-session") as t:
        with agent_span(name="planner"):
            # Successful first step.
            with function_span(
                name="search_web", input='{"query":"observability tools"}'
            ) as fn:
                fn.span_data.output = "found 3 articles"

            # Successful second step.
            with function_span(
                name="read_article", input='{"id":"art-1"}'
            ) as fn:
                fn.span_data.output = "summary..."

            # The failure: a tool that raises.
            with function_span(name="cite_source", input='{"id":"art-1"}') as fn:
                fn.set_error(
                    {
                        "message": "citation database is offline",
                        "data": {"retryable": False},
                    }
                )

            # Recovery attempt that also fails — gives /failures something to
            # find. The first failure will be cite_source above.
            with function_span(name="cite_source_retry", input='{"id":"art-1"}') as fn:
                fn.set_error(
                    {
                        "message": "still offline",
                        "data": {"retryable": False},
                    }
                )

    print(f"\n--- Failing run complete ---")
    print(f"trace_id: {t.trace_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
