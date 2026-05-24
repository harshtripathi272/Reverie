"""``reverie annotate`` and ``reverie annotations`` — manage user feedback on nodes.

Why this exists
---------------

After a run finishes the user can mark nodes as ``avoid`` / ``focus`` /
``done`` / ``note`` so the next run of the same agent receives that
feedback as a system-prompt prefix. This is the CLI surface for that
workflow; the 3D explorer adds visual affordances for the same operations
in a follow-up.

Two commands ship in this module:

  reverie annotate <run-id> <node-id> <kind> [--note "..."] [--scope ...] [--tag ...]
  reverie annotations <run-id> [--json]

A bulk delete lives under the second command via ``--clear``.
"""

from __future__ import annotations

import json
from typing import Any

import click
import httpx

from reverie_cli.client import ReverieClient
from reverie_cli.formatting import make_console


_VALID_KINDS = ("avoid", "focus", "done", "note")
_VALID_SCOPES = ("agent", "run")


@click.command(
    "annotate",
    short_help="Attach feedback to a node so the next run is steered by it.",
)
@click.argument("run_id")
@click.argument("node_id")
@click.argument("kind", type=click.Choice(_VALID_KINDS))
@click.option(
    "--note",
    "note",
    default=None,
    help="Optional free-text annotation (visible to the agent on next run).",
)
@click.option(
    "--scope",
    "scope",
    type=click.Choice(_VALID_SCOPES),
    default="agent",
    show_default=True,
    help="'agent' carries forward to future runs; 'run' is one-shot.",
)
@click.option(
    "--tag",
    "tag",
    default=None,
    help="Optional topic label so the agent can scope guidance by task.",
)
@click.option(
    "--backend",
    "backend_url",
    envvar="REVERIE_BACKEND_URL",
    default="http://127.0.0.1:8000",
    show_default=True,
)
@click.option("--json", "as_json", is_flag=True)
def annotate_command(
    run_id: str,
    node_id: str,
    kind: str,
    note: str | None,
    scope: str,
    tag: str | None,
    backend_url: str,
    as_json: bool,
) -> None:
    """Attach an annotation to a single node."""

    console = make_console()
    body = {
        "nodeId": node_id,
        "kind": kind,
        "scope": scope,
    }
    if note is not None:
        body["note"] = note
    if tag is not None:
        body["tag"] = tag

    try:
        with ReverieClient(backend_url) as client:
            resp = client._client.post(  # noqa: SLF001
                f"/api/v1/runs/{run_id}/annotations", json=body
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as exc:
        _bail(console, exc)
    except httpx.HTTPError as exc:
        console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    if as_json:
        click.echo(json.dumps(payload, indent=2))
        return

    icon = _kind_icon(kind)
    console.print(
        f"[green]ok[/green] {icon} [bold]{kind}[/bold] "
        f"on [cyan]{node_id[:12]}...[/cyan] "
        f"in run [dim]{run_id[:8]}...[/dim]"
    )
    if note:
        console.print(f"     note: [yellow]{note}[/yellow]")
    if tag:
        console.print(f"     tag:  [magenta]#{tag}[/magenta]")


@click.command(
    "annotations",
    short_help="List or clear annotations on a run.",
)
@click.argument("run_id")
@click.option(
    "--clear",
    "clear",
    is_flag=True,
    help="Delete every annotation on this run.",
)
@click.option(
    "--backend",
    "backend_url",
    envvar="REVERIE_BACKEND_URL",
    default="http://127.0.0.1:8000",
    show_default=True,
)
@click.option("--json", "as_json", is_flag=True)
def annotations_command(
    run_id: str,
    clear: bool,
    backend_url: str,
    as_json: bool,
) -> None:
    """List or clear annotations on a run."""

    console = make_console()

    if clear:
        try:
            with ReverieClient(backend_url) as client:
                resp = client._client.delete(  # noqa: SLF001
                    f"/api/v1/runs/{run_id}/annotations"
                )
                resp.raise_for_status()
                payload = resp.json()
        except httpx.HTTPStatusError as exc:
            _bail(console, exc)
        except httpx.HTTPError as exc:
            console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")
            raise SystemExit(1)

        if as_json:
            click.echo(json.dumps(payload, indent=2))
            return
        console.print(
            f"[green]ok[/green] removed [bold]{payload['deleted']}[/bold] "
            f"annotation(s) from run [dim]{run_id[:8]}...[/dim]"
        )
        return

    try:
        with ReverieClient(backend_url) as client:
            resp = client._client.get(  # noqa: SLF001
                f"/api/v1/runs/{run_id}/annotations"
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as exc:
        _bail(console, exc)
    except httpx.HTTPError as exc:
        console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    items = payload.get("items", [])
    if as_json:
        click.echo(json.dumps(payload, indent=2))
        return

    if not items:
        console.print(
            f"[dim]no annotations on run {run_id[:8]}... yet. "
            f"Add one with[/dim] [bold]reverie annotate[/bold]"
        )
        return

    console.print(
        f"[bold]{len(items)}[/bold] annotation(s) on run "
        f"[dim]{run_id[:8]}...[/dim]"
    )
    for a in items:
        icon = _kind_icon(a["kind"])
        line = (
            f"  {icon} [bold]{a['kind']:<6}[/bold] "
            f"node [cyan]{a['nodeId'][:12]}...[/cyan]"
        )
        if a.get("tag"):
            line += f" [magenta]#{a['tag']}[/magenta]"
        if a.get("note"):
            line += f"  [yellow]{a['note']}[/yellow]"
        console.print(line)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _kind_icon(kind: str) -> str:
    return {
        "avoid": "[red]x[/red]",
        "focus": "[yellow]*[/yellow]",
        "done":  "[green]+[/green]",
        "note":  "[blue]i[/blue]",
    }.get(kind, "?")


def _bail(console: Any, exc: httpx.HTTPStatusError) -> None:
    """Translate a 4xx/5xx into a CLI error message + exit."""

    status = exc.response.status_code
    if status == 404:
        body = _safe_json(exc)
        console.print(
            f"[red]error:[/red] {body.get('error', 'not found')}: "
            f"{body.get('detail', '')}"
        )
    elif status == 422:
        body = _safe_json(exc)
        console.print(f"[red]error:[/red] validation failed: {body.get('detail', body)}")
    else:
        console.print(
            f"[red]error:[/red] {status} {exc.response.text}"
        )
    raise SystemExit(1)


def _safe_json(exc: httpx.HTTPStatusError) -> dict[str, Any]:
    try:
        return exc.response.json() if exc.response.text else {}
    except ValueError:
        return {"detail": exc.response.text}
