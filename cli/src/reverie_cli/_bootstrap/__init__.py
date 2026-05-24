"""Bootstrap helpers for ``reverie run``.

This package's *directory* is what gets prepended to ``PYTHONPATH`` so Python's
``site.py`` finds the sibling ``sitecustomize.py`` and imports it before user
code runs. The package itself is a normal Python package so callers can also
locate the bootstrap directory via ``reverie_cli._bootstrap.dir_path()``.
"""

from __future__ import annotations

from pathlib import Path


def dir_path() -> Path:
    """Return the directory that should be prepended to ``PYTHONPATH``."""

    return Path(__file__).resolve().parent
