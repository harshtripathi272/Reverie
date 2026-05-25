"""Universal Reverie event emitter — works with any agent framework.

Usage
-----

    pip install reverie-obs

    from reverie_obs import ReverieClient

    rev = ReverieClient(agent_id="my-gemini-bot")
    rev.start_run(goal="Summarise the quarterly report")

    goal_id = rev.goal("Summarise Q4 report")
    rev.tool_called("gemini.generate", input={"prompt": "..."}, parent_id=goal_id)
    rev.tool_returned("gemini.generate", output="...", token_cost=1234, parent_id=goal_id)

    rev.complete_run()

Then open http://localhost:8000 (or wherever ``reverie start`` is running)
and your run appears in the 3D explorer.

Design rules
------------

- All public methods are non-blocking and never raise. If the Reverie
  backend is down, events are silently dropped — your agent keeps running.
- Every method returns the event ID it created (or ``None`` on failure)
  so you can use them as ``parent_id`` for child events.
- Only dependency is ``httpx`` (already pulled in by reverie-obs).
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

import httpx


def _now_ms() -> int:
    return int(time.time() * 1000)


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
            (``"gemini"``, ``"openai"``, ``"langgraph"``, ``"custom"``).
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
        self._depth_map: dict[str | None, int] = {None: 0}

    # ------------------------------------------------------------------ run

    def start_run(self, goal: str | None = None) -> str:
        """Tell Reverie a run is starting. Idempotent."""

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
        """Mark the run as finished (completed | failed | aborted)."""

        body = {"status": status, "completedAt": _now_ms()}
        try:
            self._client.patch(
                f"{self.backend_url}/api/v1/runs/{self.run_id}", json=body
            )
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

        return self._emit(
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
        """Emit ``goal.completed``."""

        return self._emit(
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
        """Emit ``goal.failed``."""

        return self._emit(
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
        """Emit ``tool.called``. Returns event id (use as parent for tool_returned)."""

        return self._emit(
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
        """Emit ``tool.returned``."""

        return self._emit(
            "tool.returned",
            parent_id=parent_id,
            duration_ms=duration_ms or latency_ms,
            payload={
                "_type": "tool",
                "toolName": tool_name,
                "args": {},
                "result": output if isinstance(output, (dict, list)) else {"text": str(output) if output else None},
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
        """Emit ``memory.retrieved``."""

        return self._emit(
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
        """Emit ``reasoning.generated`` — the model's chain-of-thought."""

        return self._emit(
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
        """Emit ``retry.triggered``."""

        return self._emit(
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
        """Emit ``reflection.generated``."""

        return self._emit(
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
        """Emit ``subagent.spawned``."""

        return self._emit(
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

        return self._emit(
            "error.occurred",
            parent_id=parent_id,
            payload={
                "_type": "generic",
                "data": {"error": message},
            },
        )

    # ------------------------------------------------------------- internal

    def _emit(
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
        depth = self._depth_map.get(parent_id, 0)
        if parent_id is not None:
            depth = self._depth_map.get(parent_id, 0) + 1
        self._depth_map[event_id] = depth

        event = {
            "id": event_id,
            "type": event_type,
            "runId": self.run_id,
            "sessionId": self.session_id,
            "agentId": self.agent_id,
            "parentId": parent_id,
            "depth": depth,
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
        """Close the HTTP client. Optional — the client is lightweight."""

        try:
            self._client.close()
        except Exception:
            pass

    def __enter__(self) -> "ReverieClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
