"""End-to-end smoke test: real OpenAI Agents SDK trace + spans → real Reverie
backend (no mock).

Run after starting ``python -m reverie_api`` in another terminal:

    .venv\\Scripts\\python.exe scripts\\smoke_adapter.py
"""

from __future__ import annotations

import sys
import time

import httpx
from agents.tracing import agent_span, function_span, trace

import reverie_openai

BACKEND = "http://127.0.0.1:8000"


def main() -> None:
    print("[smoke] installing adapter")
    reverie_openai.auto()

    print("[smoke] running synthetic trace")
    with trace("smoke-test", group_id="smoke-session") as t:
        with agent_span(name="planner") as _planner:
            for q in ("AI agent observability", "OpenTelemetry tracing"):
                with function_span(name="search_web", input=f'{{"query":"{q}"}}') as fn:
                    fn.span_data.output = f"results for {q}"

    trace_id = t.trace_id
    print(f"[smoke] trace_id={trace_id}")

    # Flush + wait for the background poster.
    reverie_openai.shutdown(timeout=5.0)
    time.sleep(0.3)

    # Look up the run and its events.
    from reverie_openai.idmap import to_uuid

    run_id = to_uuid(trace_id)
    print(f"[smoke] run_id (Reverie UUID)={run_id}")

    r = httpx.get(f"{BACKEND}/api/v1/runs/{run_id}", timeout=2.0)
    if r.status_code != 200:
        print(f"[smoke] FAIL: GET /runs/{run_id} -> {r.status_code} {r.text}")
        sys.exit(1)
    run = r.json()
    print(f"[smoke] run status={run['status']} totalEvents={run['totalEvents']}")

    r = httpx.get(f"{BACKEND}/api/v1/runs/{run_id}/events", timeout=2.0)
    if r.status_code != 200:
        print(f"[smoke] FAIL: GET events -> {r.status_code} {r.text}")
        sys.exit(1)
    events = r.json()
    types = [e["type"] for e in events]
    print(f"[smoke] received {len(events)} events:")
    for e in events:
        print(f"  - {e['type']:25s} depth={e['depth']} ts={e['timestamp']}")
    assert types.count("goal.created") == 1
    assert types.count("goal.completed") == 1
    assert types.count("tool.called") == 2
    assert types.count("tool.returned") == 2
    print("[smoke] OK")


if __name__ == "__main__":
    main()
