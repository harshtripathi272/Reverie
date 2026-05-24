"""``reverie runs ...`` — list and inspect runs."""

from __future__ import annotations

import json

import click
import httpx

from reverie_cli.client import ReverieClient
from reverie_cli.formatting import (
    events_table,
    format_duration_ms,
    format_timestamp_ms,
    make_console,
    runs_table,
)


@click.group("runs", short_help="List and inspect runs.")
def runs_group() -> None:
    """Run management commands."""


@runs_group.command("list", short_help="List recent runs.")
@click.option(
    "--backend",
    "backend_url",
    envvar="REVERIE_BACKEND_URL",
    default="http://127.0.0.1:8000",
    show_default=True,
)
@click.option("--limit", default=20, show_default=True, type=click.IntRange(1, 500))
@click.option("--offset", default=0, show_default=True, type=click.IntRange(0))
@click.option("--session", "session_id", default=None, help="Filter by session id.")
@click.option(
    "--status",
    type=click.Choice(["running", "completed", "failed", "aborted"]),
    default=None,
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def list_runs(
    backend_url: str,
    limit: int,
    offset: int,
    session_id: str | None,
    status: str | None,
    as_json: bool,
) -> None:
    """List runs, most recent first."""

    console = make_console()
    try:
        with ReverieClient(backend_url) as client:
            page = client.list_runs(
                limit=limit, offset=offset, session_id=session_id, status=status
            )
    except httpx.HTTPError as exc:
        console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    if as_json:
        click.echo(json.dumps(page, indent=2))
        return

    items = page.get("items", [])
    if not items:
        console.print("[dim]no runs yet[/dim]")
        return

    console.print(
        f"[bold]{len(items)}[/bold] of [bold]{page.get('total', '?')}[/bold] runs "
        f"(offset {page.get('offset', offset)})"
    )
    console.print(runs_table(items))


@runs_group.command("show", short_help="Show one run plus its events.")
@click.argument("run_id")
@click.option(
    "--backend",
    "backend_url",
    envvar="REVERIE_BACKEND_URL",
    default="http://127.0.0.1:8000",
    show_default=True,
)
@click.option("--events/--no-events", default=True, help="Include the event timeline.")
@click.option(
    "--limit",
    default=200,
    show_default=True,
    type=click.IntRange(1, 10_000),
    help="Maximum number of events to fetch.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def show_run(
    run_id: str,
    backend_url: str,
    events: bool,
    limit: int,
    as_json: bool,
) -> None:
    """Show metadata and (optionally) the event timeline for RUN_ID."""

    console = make_console()
    try:
        with ReverieClient(backend_url) as client:
            run = client.get_run(run_id)
            event_list = client.get_events(run_id, limit=limit) if events else []
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            console.print(f"[red]error:[/red] run not found: {run_id}")
            raise SystemExit(1)
        console.print(f"[red]error:[/red] {exc.response.status_code} {exc.response.text}")
        raise SystemExit(1)
    except httpx.HTTPError as exc:
        console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    if as_json:
        click.echo(json.dumps({"run": run, "events": event_list}, indent=2))
        return

    duration_ms: float | None = None
    if run.get("completedAt") is not None:
        duration_ms = float(run["completedAt"] - run["startedAt"])

    console.print(f"[bold]Run[/bold] {run['id']}")
    console.print(f"  session:    {run['sessionId']}")
    console.print(f"  agent:      {run['agentId']}")
    console.print(f"  runtime:    {run['runtime']}")
    console.print(f"  goal:       {run.get('goal') or '—'}")
    console.print(f"  status:     {run['status']}")
    console.print(f"  started:    {format_timestamp_ms(run['startedAt'])}")
    console.print(f"  duration:   {format_duration_ms(duration_ms)}")
    console.print(
        f"  events:     {run['totalEvents']}  "
        f"tools={run['totalToolCalls']}  "
        f"retries={run['totalRetries']}  "
        f"subagents={run['totalSubagents']}  "
        f"tokens={run['totalTokens']}"
    )
    console.print(f"  pinned:     {run['pinned']}")

    if events:
        console.print()
        if not event_list:
            console.print("[dim]no events captured for this run yet[/dim]")
        else:
            console.print(events_table(event_list))
