"""``reverie status`` — backend health probe."""

from __future__ import annotations

import click
import httpx

from reverie_cli.client import ReverieClient
from reverie_cli.formatting import make_console


@click.command("status", short_help="Check backend health.")
@click.option(
    "--backend",
    "backend_url",
    envvar="REVERIE_BACKEND_URL",
    default="http://127.0.0.1:8000",
    show_default=True,
)
def status_command(backend_url: str) -> None:
    """Ping the configured backend and report its status."""

    console = make_console()
    try:
        with ReverieClient(backend_url) as client:
            body = client.health()
    except httpx.HTTPError as exc:
        console.print(
            f"[bold red]✗[/bold red] cannot reach {backend_url}: "
            f"[dim]{type(exc).__name__}: {exc}[/dim]"
        )
        raise SystemExit(1)
    except Exception as exc:
        # Defensive — never leak a raw traceback to the user.
        console.print(
            f"[bold red]✗[/bold red] unexpected error contacting {backend_url}: "
            f"[dim]{type(exc).__name__}: {exc}[/dim]"
        )
        raise SystemExit(2)

    status = body.get("status", "unknown")
    version = body.get("version", "?")
    user_version = body.get("dbUserVersion", "?")
    console.print(f"[bold green]✓[/bold green] {backend_url}")
    console.print(f"  status:        {status}")
    console.print(f"  version:       {version}")
    console.print(f"  db migrations: schema v{user_version}")
