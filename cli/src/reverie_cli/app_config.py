"""Global CLI configuration — ``~/.reverie/config.json``.

Why this exists
---------------

``reverie start`` and the manual development-mode commands need to know
where the Reverie repository lives so they can:

  - Find the FastAPI backend's Python environment (``.venv/Scripts/python``).
  - Find the Next.js web app to run via ``pnpm -C apps/web dev``.

For developers working *inside* the repo, the auto-detect logic in
``commands/start.py`` walks upward from the cwd until it finds the marker
files. That stops working the moment the user runs ``reverie start`` from
outside the repo — for example from their own product's directory.

The fix is a tiny global config: ``~/.reverie/config.json``. ``reverie init``
writes it; every other command reads it as a fallback when auto-detect
returns nothing.

Schema
------

.. code-block:: json

    {
      "version": 1,
      "repo_path": "/abs/path/to/reverie",
      "backend_url": "http://127.0.0.1:8000",
      "data_dir": "/abs/path/to/data"
    }

Only ``repo_path`` is mandatory. Every other field is optional and falls
back to the same defaults the rest of the CLI uses.

Cross-platform
--------------

We use the user's home directory (``Path.home() / ".reverie"``) directly
instead of pulling in a dependency like ``platformdirs``. This is
intentional: a tiny config file in a stable location is what users expect,
and we can vendor `platformdirs` later if cross-platform XDG concerns
arise.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR = Path.home() / ".reverie"
CONFIG_FILE = CONFIG_DIR / "config.json"
CONFIG_VERSION = 1


@dataclass
class AppConfig:
    """In-memory shape of ``~/.reverie/config.json``."""

    repo_path: Path | None = None
    backend_url: str | None = None
    data_dir: Path | None = None
    version: int = CONFIG_VERSION

    def to_dict(self) -> dict:
        """Serialise. Skips ``None`` fields so the file stays minimal."""

        out: dict = {"version": self.version}
        if self.repo_path is not None:
            out["repo_path"] = str(self.repo_path)
        if self.backend_url is not None:
            out["backend_url"] = self.backend_url
        if self.data_dir is not None:
            out["data_dir"] = str(self.data_dir)
        return out

    @classmethod
    def from_dict(cls, raw: dict) -> "AppConfig":
        return cls(
            version=int(raw.get("version", CONFIG_VERSION)),
            repo_path=_to_path(raw.get("repo_path")),
            backend_url=raw.get("backend_url"),
            data_dir=_to_path(raw.get("data_dir")),
        )


def _to_path(value: str | None) -> Path | None:
    if value is None:
        return None
    return Path(value).expanduser().resolve()


def load_config() -> AppConfig:
    """Read ``~/.reverie/config.json`` if it exists; return defaults if not.

    Never raises. A malformed file is treated as missing — we just log to
    stderr so the user can recover.
    """

    # Resolve the module attribute lazily so tests that monkeypatch CONFIG_FILE
    # see their override.
    cfg_file = CONFIG_FILE
    if not cfg_file.exists():
        return AppConfig()
    try:
        raw = json.loads(cfg_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        # Defensive — better to fall back to auto-detect than to fail.
        import sys

        sys.stderr.write(
            f"[reverie] warning: failed to read {cfg_file}: "
            f"{type(exc).__name__}: {exc}\n"
        )
        return AppConfig()
    if not isinstance(raw, dict):
        return AppConfig()
    return AppConfig.from_dict(raw)


def save_config(cfg: AppConfig) -> Path:
    """Write the config to disk. Returns the file path."""

    cfg_dir = CONFIG_DIR
    cfg_file = CONFIG_FILE
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text(
        json.dumps(cfg.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    # Best-effort: tighten permissions on POSIX. No-op on Windows.
    try:
        os.chmod(cfg_file, 0o600)
    except OSError:
        pass
    return cfg_file


def detect_repo_path(start: Path | None = None) -> Path | None:
    """Walk upward from ``start`` looking for a Reverie checkout.

    A directory is considered a Reverie checkout when it contains both
    ``apps/api`` and either ``Makefile`` or ``pyproject.toml``.
    """

    cwd = (start or Path.cwd()).resolve()
    candidates = [cwd, *cwd.parents]
    for c in candidates:
        if not (c / "apps" / "api").exists():
            continue
        if (c / "Makefile").exists() or (c / "pyproject.toml").exists():
            return c
    return None


def resolve_repo_path(override: Path | None = None) -> Path | None:
    """Find the Reverie repo, in priority order:

    1. Explicit ``--repo`` argument (``override``).
    2. ``REVERIE_REPO`` environment variable.
    3. ``~/.reverie/config.json`` ``repo_path`` field.
    4. Walk upward from cwd looking for marker files.
    """

    if override is not None:
        return override.resolve()

    env = os.environ.get("REVERIE_REPO", "").strip()
    if env:
        candidate = Path(env).expanduser()
        if candidate.exists():
            return candidate.resolve()

    cfg = load_config()
    if cfg.repo_path is not None and cfg.repo_path.exists():
        return cfg.repo_path

    return detect_repo_path()
