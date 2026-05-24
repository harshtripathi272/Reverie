"""``reverie guidance`` — preview or wipe the prompt-prefix the next run will see.

This is the read side of the annotations workflow:

    reverie annotate <run-id> <node-id> avoid --note "this is a dead end"
    reverie guidance <agent-id>            # what the next run will see
    reverie guidance <agent-id> --clear    # wipe everything

The guidance text is also what the adapter fetches automatically when
``REVERIE_USE_GUIDANCE=1`` is set on the next ``reverie run``.
"""

from __future__ import annotations

import json
from typing import Any

import click
import httpx

from reverie_cli.client import ReverieClient
from reverie_cli.formatting import make_console


@click.command(
    "guidance",
    short_help="Preview the prompt-prefix the next run will see for an agent.",
)
@click.argument("agent_id")
@click.option(
    "--clear",
    is_flag=True,
    help="Wipe ALL annotations for this agent (irreversible).",
)
@click.option(
    "--tag",
    default=None,
    help="Only annotations matching this topic (or untagged) are included.",
)
@click.option(
    "--kinds",
    default=None,
    help="Comma-separated kinds to include (default: avoid,focus,done).",
)
@click.option(
    "--backend",
    "backend_url",
    envvar="REVERIE_BACKEND_URL",
    default="http://127.0.0.1:8000",
    show_default=True,
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["pretty", "prompt", "markdown", "json"]),
    default="pretty",
    show_default=True,
    help="'prompt' emits the raw text the next agent run will see.",
)
def guidance_command(
    agent_id: str,
    clear: bool,
    tag: str | None,
    kinds: str | None,
    backend_url: str,
    fmt: str,
) -> None:
    """Render or clear the guidance for AGENT_ID."""

    console = make_console()

    if clear:
        try:
            with ReverieClient(backend_url) as client:
                resp = client._client.delete(  # noqa: SLF001
                    f"/api/v1/agents/{agent_id}/guidance"
                )
                resp.raise_for_status()
                body = resp.json()
        except httpx.HTTPStatusError as exc:
            _bail(console, exc)
        except httpx.HTTPError as exc:
            console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")
            raise SystemExit(1)
        console.print(
            f"[green]ok[/green] removed [bold]{body['deleted']}[/bold] "
            f"annotation(s) for agent [cyan]{agent_id}[/cyan]"
        )
        return

    params: dict[str, Any] = {}
    if tag is not None:
        params["tag"] = tag
    if kinds is not None:
        params["kinds"] = kinds

    try:
        with ReverieClient(backend_url) as client:
            resp = client._client.get(  # noqa: SLF001
                f"/api/v1/agents/{agent_id}/guidance",
                params=params,
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as exc:
        _bail(console, exc)
    except httpx.HTTPError as exc:
        console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    if fmt == "json":
        click.echo(json.dumps(payload, indent=2))
        return
    if fmt == "prompt":
        click.echo(payload.get("promptPrefix", ""))
        return
    if fmt == "markdown":
        click.echo(payload.get("markdown", ""))
        return

    # pretty
    items = payload.get("items", [])
    prefix = payload.get("promptPrefix", "")
    console.print(
        f"[bold]Guidance for agent[/bold] [cyan]{agent_id}[/cyan]  "
        f"({len(items)} annotation(s))"
    )
    if not prefix:
        console.print(
            "[dim]No prompt-prefix-relevant annotations yet. "
            "Use 'reverie annotate' to add some.[/dim]"
        )
        return
    console.print()
    console.print("[dim]--- prompt prefix the next run will see ---[/dim]")
    console.print(prefix)
    console.print("[dim]--- end ---[/dim]")
    console.print()
    console.print(
        "[dim]Set[/dim] [bold]REVERIE_USE_GUIDANCE=1[/bold] "
        "[dim]to make the next 'reverie run' inject this automatically.[/dim]"
    )


def _bail(console: Any, exc: httpx.HTTPStatusError) -> None:
    status = exc.response.status_code
    try:
        body = exc.response.json() if exc.response.text else {}
    except ValueError:
        body = {"detail": exc.response.text}
    if status == 404:
        console.print(
            f"[red]error:[/red] {body.get('error', 'not found')}: "
            f"{body.get('detail', '')}"
        )
    else:
        console.print(f"[red]error:[/red] {status} {body.get('detail', exc.response.text)}")
    raise SystemExit(1)
