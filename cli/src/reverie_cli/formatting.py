"""Shared output helpers — Rich-based, but degrades cleanly when the terminal
isn't a TTY (so piping ``reverie ...`` into other tools works).

Tests use ``Console(width=200, force_terminal=False)`` to capture wide,
ANSI-free output that's easy to assert against.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from rich.console import Console
from rich.table import Table


def make_console() -> Console:
    """Default console. Detects TTY automatically."""

    return Console()


def format_timestamp_ms(value: int | None) -> str:
    if value is None:
        return "-"
    try:
        dt = datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
    except (OSError, ValueError, OverflowError):
        return str(value)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_duration_ms(value: float | int | None) -> str:
    if value is None:
        return "-"
    if value < 1000:
        return f"{value:.1f}ms"
    return f"{value / 1000:.2f}s"


def runs_table(runs: list[dict[str, Any]]) -> Table:
    table = Table(show_lines=False, header_style="bold")
    table.add_column("Run ID", overflow="fold", min_width=12)
    table.add_column("Status")
    table.add_column("Goal", overflow="fold")
    table.add_column("Events", justify="right")
    table.add_column("Tools", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Started")

    for r in runs:
        table.add_row(
            r["id"][:8] + "…",
            _status_styled(r["status"]),
            (r.get("goal") or "-")[:60],
            str(r["totalEvents"]),
            str(r["totalToolCalls"]),
            str(r["totalTokens"]),
            format_timestamp_ms(r["startedAt"]),
        )
    return table


def events_table(events: list[dict[str, Any]]) -> Table:
    table = Table(show_lines=False, header_style="bold")
    table.add_column("#", justify="right", style="dim", min_width=3)
    table.add_column("Time")
    table.add_column("Type")
    table.add_column("Depth", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Detail", overflow="fold")

    for i, e in enumerate(events, start=1):
        table.add_row(
            str(i),
            format_timestamp_ms(e["timestamp"]),
            _type_styled(e["type"]),
            str(e["depth"]),
            format_duration_ms(e.get("durationMs")),
            _summarise_payload(e["payload"]),
        )
    return table


def _status_styled(status: str) -> str:
    color = {
        "running": "yellow",
        "completed": "green",
        "failed": "red",
        "aborted": "magenta",
    }.get(status, "white")
    return f"[{color}]{status}[/{color}]"


def _type_styled(type_: str) -> str:
    if type_.startswith("goal."):
        return f"[bold magenta]{type_}[/bold magenta]"
    if type_.startswith("tool."):
        return f"[cyan]{type_}[/cyan]"
    if type_.startswith("retry."):
        return f"[yellow]{type_}[/yellow]"
    if type_ == "validation.failed" or type_.endswith(".failed"):
        return f"[red]{type_}[/red]"
    if type_.startswith("subagent."):
        return f"[blue]{type_}[/blue]"
    if type_ == "reasoning.extracted":
        return f"[dim]{type_}[/dim]"
    return type_


def _summarise_payload(payload: dict[str, Any]) -> str:
    """One-line readable description of an event's payload."""

    kind = payload.get("_type", "")
    if kind == "goal":
        return _safe(payload.get("intent"))
    if kind == "tool":
        name = payload.get("toolName", "?")
        if payload.get("success") is False:
            return f"{name} → ERROR: {_safe(payload.get('errorMessage'))}"
        latency = payload.get("latencyMs")
        if latency:
            return f"{name} ({format_duration_ms(latency)})"
        return name
    if kind == "memory":
        return f"query: {_safe(payload.get('query'))}"
    if kind == "retry":
        return f"attempt {payload.get('attempt')}/{payload.get('maxAttempts')}: {_safe(payload.get('reason'))}"
    if kind == "subagent":
        return f"→ {_safe(payload.get('agentType'))}: {_safe(payload.get('task'))}"
    if kind == "validation":
        return f"{payload.get('checkName', '?')}: {'pass' if payload.get('passed') else 'fail'}"
    if kind == "reasoning":
        return _safe(payload.get("summary"))
    if kind == "reflection":
        return _safe(payload.get("insight"))
    return ""


def _safe(value: Any, *, max_len: int = 80) -> str:
    if value is None:
        return ""
    s = value if isinstance(value, str) else repr(value)
    return s if len(s) <= max_len else s[: max_len - 1] + "…"
