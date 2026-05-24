"""Reverie command-line interface.

Public surface is intentionally small — most users only ever invoke
``reverie`` as a console script. The Click root group is exposed as
``reverie_cli.cli`` for advanced embedding.

``__version__`` is defined here (above any sub-module imports) so command
modules can do ``from reverie_cli import __version__`` without circular
imports.
"""

from __future__ import annotations

__version__ = "0.1.0"


def _resolve_cli():
    """Lazy accessor that avoids a circular import at module-load time."""

    from reverie_cli.main import cli as _cli

    return _cli


# Re-export ``cli`` lazily via __getattr__ so ``from reverie_cli import cli`` works.
def __getattr__(name: str):  # pragma: no cover — trivial
    if name == "cli":
        return _resolve_cli()
    raise AttributeError(name)


__all__ = ["cli", "__version__"]
