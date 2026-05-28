"""Drop-in Reverie event emitter for ANY Python agent.

Copy this file into your own project (or ``pip install httpx`` and write
your own based on it). Works with Gemini, Claude, OpenAI direct, custom
LLM wrappers — anything where you don't have the OpenAI Agents SDK
auto-adapter.

Quick start
-----------

    from reverie_emit import ReverieClient

    rev = ReverieClient(agent_id="my-gemini-bot")
    rev.start_run(goal="Summarise the quarterly report")

    goal_id = rev.goal("Summarise quarterly Q4 report")
    rev.tool_called("gemini.generate", input={"prompt": "..."}, parent_id=goal_id)
    # ... your agent code ...
    rev.tool_returned("gemini.generate", output="...", token_cost=1234, latency_ms=820, parent_id=goal_id)

    rev.complete_run()

Then open http://localhost:8000 and you'll see your run appear in 3D.

Design rules
------------

- All public methods are non-blocking and never raise. If the Reverie
  backend is down, events are silently dropped.
- Every method returns the event ID it created (or ``None`` on failure)
  so you can use them as ``parent_id`` for child events.
- The class wraps the existing HTTP API — no Reverie-specific deps needed
  beyond ``httpx``.
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx


def _now_ms() -> int:
    return int(time.time() * 1000)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReverieClient:
    """Best-effort emitter for cognitive events.

    Args:
        agent_id: Identifier for your agent. Annotations made in the 3D
            explorer are scoped by this id, so reuse the same value
            across runs of the same logical agent.
        backend_url: Where the Reverie backend lives. Defaults to the
            ``REVERIE_BACKEND_URL`` env var or ``http://127.0.0.1:8000``.
        run_id: Optional pre-set run id. If omitted, ``start_run`` will
            generate a fresh UUID.
        session_id: Groups runs that belong to the same user session.
        runtime: Free-form label for which framework you're using
            (``"gemini"``, ``"openai-direct"``, ``"langgraph"``, etc.).
    """

    def __init__(
        self,
        agent_id: str = "my-agent",
        *,
        backend_url: str | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
        runtime: str = "custom",
    ) -> None:
        self.agent_id = agent_id
        self.runtime = runtime
        self.backend_url = (
            backend_url
            or os.environ.get("REVERIE_BACKEND_URL")
            or "http://127.0.0.1:8000"
        ).rstrip("/")
        self.run_id = run_id or str(uuid.uuid4())
        self.session_id = session_id or str(uuid.uuid4())
        self._client = httpx.Client(timeout=httpx.Timeout(2.0))
        self._started = False

    # ------------------------------------------------------------------ run

    def start_run(self, goal: str | None = None) -> str:
        """Tell Reverie a run is starting. Idempotent — calling twice is OK."""

        if self._started:
            return self.run_id

        body = {
            "runId": self.run_id,
            "sessionId": self.session_id,
            "agentId": self.agent_id,
            "runtime": self.runtime,
            "startedAt": _now_ms(),
            "goal": goal,
        }
        self._safe_post("/api/v1/runs", body)
        self._started = True
        return self.run_id

    def complete_run(self, *, status: str = "completed") -> None:
        """Mark the run as finished (status: completed | failed | aborted)."""

        body = {"status": status, "completedAt": _now_ms()}
        try:
            self._client.patch(f"{self.backend_url}/api/v1/runs/{self.run_id}", json=body)
        except Exception:
            pass

    # --------------------------------------------------------------- events

    def goal(
        self,
        intent: str,
        *,
        parent_id: str | None = None,
        priority: str = "high",
    ) -> str | None:
        """Emit ``goal.created``. Returns the event id."""

        return self._emit_event(
            "goal.created",
            parent_id=parent_id,
            payload={
                "_type": "goal",
                "intent": intent,
                "priority": priority,
                "context": "",
            },
        )

    def goal_completed(
        self,
        *,
        parent_id: str | None = None,
        outcome: str = "",
    ) -> str | None:
        return self._emit_event(
            "goal.completed",
            parent_id=parent_id,
            payload={
                "_type": "goal",
                "intent": outcome or "completed",
                "priority": "high",
                "context": "",
            },
        )

    def goal_failed(
        self,
        *,
        parent_id: str | None = None,
        reason: str = "",
    ) -> str | None:
        """Emit ``goal.failed`` — produces a red orb."""

        return self._emit_event(
            "goal.failed",
            parent_id=parent_id,
            payload={
                "_type": "goal",
                "intent": reason or "failed",
                "priority": "high",
                "context": "",
            },
        )

    def tool_called(
        self,
        tool_name: str,
        *,
        input: dict[str, Any] | None = None,
        parent_id: str | None = None,
    ) -> str | None:
        """Emit ``tool.called``. Returns the event id (use as parent for ``tool_returned``)."""

        return self._emit_event(
            "tool.called",
            parent_id=parent_id,
            payload={
                "_type": "tool",
                "toolName": tool_name,
                "args": input or {},
                "result": None,
                "latencyMs": 0,
                "tokenCost": None,
                "success": True,
                "errorMessage": None,
            },
        )

    def tool_returned(
        self,
        tool_name: str,
        *,
        output: Any = None,
        latency_ms: float = 0,
        token_cost: int | None = None,
        success: bool = True,
        error_message: str | None = None,
        parent_id: str | None = None,
        duration_ms: float | None = None,
    ) -> str | None:
        """Emit ``tool.returned``. Pair with a previous ``tool_called``."""

        return self._emit_event(
            "tool.returned",
            parent_id=parent_id,
            duration_ms=duration_ms,
            payload={
                "_type": "tool",
                "toolName": tool_name,
                "args": {},
                "result": output,
                "latencyMs": latency_ms,
                "tokenCost": token_cost,
                "success": success,
                "errorMessage": error_message,
            },
        )

    def memory_retrieved(
        self,
        query: str,
        *,
        results: list[Any] | None = None,
        parent_id: str | None = None,
    ) -> str | None:
        return self._emit_event(
            "memory.retrieved",
            parent_id=parent_id,
            payload={
                "_type": "memory",
                "query": query,
                "results": results or [],
                "hitCount": len(results or []),
            },
        )

    def reasoning(
        self,
        summary: str,
        *,
        model_id: str = "unknown",
        tokens_used: int | None = None,
        parent_id: str | None = None,
    ) -> str | None:
        return self._emit_event(
            "reasoning.generated",
            parent_id=parent_id,
            payload={
                "_type": "reasoning",
                "rawText": None,
                "summary": summary,
                "modelId": model_id,
                "tokensUsed": tokens_used,
            },
        )

    def retry(
        self,
        reason: str,
        *,
        attempt: int,
        max_attempts: int = 3,
        parent_id: str | None = None,
    ) -> str | None:
        return self._emit_event(
            "retry.triggered",
            parent_id=parent_id,
            payload={
                "_type": "retry",
                "reason": reason,
                "attempt": attempt,
                "maxAttempts": max_attempts,
                "previousError": "",
                "backoffMs": 0,
            },
        )

    def reflection(
        self,
        insight: str,
        *,
        parent_id: str | None = None,
    ) -> str | None:
        return self._emit_event(
            "reflection.generated",
            parent_id=parent_id,
            payload={
                "_type": "reflection",
                "insight": insight,
                "confidence": 0.8,
            },
        )

    def subagent_spawned(
        self,
        agent_type: str,
        task: str,
        *,
        parent_id: str | None = None,
    ) -> str | None:
        """Emit ``subagent.spawned`` — a helper agent gets delegated to."""

        return self._emit_event(
            "subagent.spawned",
            parent_id=parent_id,
            payload={
                "_type": "subagent",
                "agentType": agent_type,
                "task": task,
                "delegatedGoalId": None,
                "childRunId": None,
            },
        )

    def error(
        self,
        message: str,
        *,
        parent_id: str | None = None,
    ) -> str | None:
        """Emit ``error.occurred``."""

        return self._emit_event(
            "error.occurred",
            parent_id=parent_id,
            payload={
                "_type": "generic",
                "data": {"error": message},
            },
        )

    # ------------------------------------------------------------- internal

    def _emit_event(
        self,
        event_type: str,
        *,
        payload: dict[str, Any],
        parent_id: str | None = None,
        duration_ms: float | None = None,
    ) -> str | None:
        """Build, POST, and return the event id. Never raises."""

        if not self._started:
            self.start_run()

        event_id = str(uuid.uuid4())
        event = {
            "id": event_id,
            "type": event_type,
            "runId": self.run_id,
            "sessionId": self.session_id,
            "agentId": self.agent_id,
            "parentId": parent_id,
            "depth": 0 if parent_id is None else 1,
            "timestamp": _now_ms(),
            "durationMs": duration_ms,
            "payload": payload,
            "salience": None,
            "anomaly": False,
            "schemaVersion": "1.0",
        }
        ok = self._safe_post("/api/v1/events", event)
        return event_id if ok else None

    def _safe_post(self, path: str, body: dict[str, Any]) -> bool:
        try:
            resp = self._client.post(f"{self.backend_url}{path}", json=body)
            return 200 <= resp.status_code < 300
        except Exception:
            return False

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Example: Gemini agent
# ---------------------------------------------------------------------------


def _example_gemini_run() -> None:
    """Minimal demonstration — emits a fake Gemini agent's events."""

    rev = ReverieClient(agent_id="gemini-research-bot", runtime="gemini")
    rev.start_run(goal="Find the latest research on AI safety")

    goal_id = rev.goal("Find latest AI safety papers from arXiv")

    # Gemini call 1
    tool_id = rev.tool_called(
        "gemini.generate",
        input={
            "model": "gemini-2.5-pro",
            "prompt": "List the top 5 AI safety papers published this month",
        },
        parent_id=goal_id,
    )
    time.sleep(0.5)  # pretend the call took time
    rev.tool_returned(
        "gemini.generate",
        output={
            "text": "1. Paper A on alignment...\n2. Paper B on interpretability...",
            "model": "gemini-2.5-pro",
        },
        latency_ms=850,
        token_cost=1240,
        parent_id=goal_id,
        duration_ms=850,
    )

    rev.reasoning(
        summary="Found 5 candidate papers; selecting the most cited",
        model_id="gemini-2.5-pro",
        tokens_used=1240,
        parent_id=goal_id,
    )

    # Web fetch
    fetch_id = rev.tool_called(
        "fetch_url",
        input={"url": "https://arxiv.org/abs/2505.12345"},
        parent_id=goal_id,
    )
    time.sleep(0.3)
    rev.tool_returned(
        "fetch_url",
        output={"status": 200, "length": 45_000},
        latency_ms=320,
        parent_id=goal_id,
        duration_ms=320,
    )

    rev.goal_completed(parent_id=goal_id, outcome="Found 3 high-impact papers")
    rev.complete_run()
    rev.close()
    print(f"Run {rev.run_id} complete. Open http://localhost:3000 to view.")


if __name__ == "__main__":
    _example_gemini_run()
