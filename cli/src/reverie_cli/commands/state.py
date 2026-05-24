"""``reverie state <run-id>`` — print the cognitive state of a run.

Phase 1 preview. Useful for "what was the agent thinking at moment N" without
having to scrub through the whole event timeline.
"""

from __future__ import annotations

import json

import click
import httpx

from reverie_cli.client import ReverieClient
from reverie_cli.formatting import (
    format_duration_ms,
    format_timestamp_ms,
    make_console,
)


@click.command(
    "state",
    short_help="Show the cognitive state of a run at a given event index.",
)
@click.argument("run_id")
@click.option(
    "--backend",
    "backend_url",
    envvar="REVERIE_BACKEND_URL",
    default="http://127.0.0.1:8000",
    show_default=True,
)
@click.option(
    "--at",
    type=click.IntRange(0, 1_000_000),
    default=None,
    help="Event index. Defaults to the run's terminal state.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def state_command(
    run_id: str,
    backend_url: str,
    at: int | None,
    as_json: bool,
) -> None:
    """Show the run's cognitive state at index AT (or terminal if omitted)."""

    console = make_console()
    params = {"at": at} if at is not None else {}

    try:
        with ReverieClient(backend_url) as client:
            resp = client._client.get(  # noqa: SLF001 — small intentional internal call
                f"/api/v1/runs/{run_id}/snapshot", params=params
            )
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            err = exc.response.json()
            err_kind = err.get("error", "not_found")
            console.print(f"[red]error:[/red] {err_kind}: {err.get('detail', '')}")
            raise SystemExit(1)
        console.print(f"[red]error:[/red] {exc.response.status_code} {exc.response.text}")
        raise SystemExit(1)
    except httpx.HTTPError as exc:
        console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    if as_json:
        click.echo(json.dumps(body, indent=2))
        return

    _render_state(console, body)


def _render_state(console, state: dict) -> None:
    """Pretty-print a RunState body."""

    console.print(
        f"[bold]State[/bold] of run [dim]{state['runId']}[/dim] "
        f"at event [bold]{state['eventCount']}[/bold]"
    )
    if state.get("lastTimestamp"):
        console.print(f"  last event:  {format_timestamp_ms(state['lastTimestamp'])}")
    console.print(
        f"  metrics:     events={state['eventCount']} "
        f"tools={state['totalToolCalls']} "
        f"retries={state['totalRetries']} "
        f"subagents={state['totalSubagents']} "
        f"tokens={state['totalTokens']} "
        f"failures={state['totalFailures']}"
    )

    fail = state.get("firstFailure")
    if fail:
        console.print(
            f"  [red]first failure:[/red] "
            f"{fail['type']} at {format_timestamp_ms(fail['occurredAt'])}: "
            f"{fail['message']}"
        )

    active_goals = state.get("activeGoals") or []
    if active_goals:
        console.print(f"\n[bold]Active goals[/bold] ({len(active_goals)})")
        for g in active_goals:
            indent = "  " * (1 + min(int(g["depth"]), 6))
            console.print(
                f"{indent}• [magenta]{g['intent']}[/magenta] "
                f"[dim](priority={g['priority']}, started "
                f"{format_timestamp_ms(g['startedAt'])})[/dim]"
            )
    else:
        console.print("\n[dim]No active goals.[/dim]")

    active_tools = state.get("activeTools") or []
    if active_tools:
        console.print(f"\n[bold]Active tools[/bold] ({len(active_tools)})")
        for t in active_tools:
            indent = "  " * (1 + min(int(t["depth"]), 6))
            console.print(
                f"{indent}• [cyan]{t['toolName']}[/cyan] "
                f"[dim]args={t['argsSummary']}[/dim]"
            )

    recent = state.get("recentToolResults") or []
    if recent:
        console.print(f"\n[bold]Recent tool results[/bold] (most recent first)")
        for r in recent[:8]:  # cap at 8 in display
            status = "[green]ok[/green]" if r["success"] else "[red]FAIL[/red]"
            console.print(
                f"  {status:>4} [cyan]{r['toolName']}[/cyan] "
                f"({format_duration_ms(r['latencyMs'])}) "
                f"[dim]@ {format_timestamp_ms(r['finishedAt'])}[/dim]"
                + (f" — {r['errorMessage']}" if r.get("errorMessage") else "")
            )

    if state.get("lastReasoningSummary"):
        console.print(
            f"\n[bold]Last reasoning[/bold] "
            f"[dim]({state.get('lastReasoningModel') or '?'})[/dim]"
        )
        console.print(f"  {state['lastReasoningSummary']}")

    if state.get("contextTokenLimit"):
        used = state["contextTokensUsed"]
        limit = state["contextTokenLimit"]
        pct = state["contextPercentUsed"]
        console.print(
            f"\n[bold]Context window[/bold]: "
            f"{used:,}/{limit:,} tokens "
            f"({pct:.1f}% used)"
        )
