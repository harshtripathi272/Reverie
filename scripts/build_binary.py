"""Build a single-file standalone Reverie binary with PyInstaller.

Output
------

A platform-specific executable in ``build_dist/`` that bundles:

  - The Python interpreter
  - All four Reverie packages (schema, adapter, api, cli)
  - The static-export 3D explorer
  - All transitive dependencies (FastAPI, uvicorn, httpx, etc.)

Users who download this binary need NEITHER Python NOR Node installed —
they just run ``./reverie start`` and everything works.

Prerequisites
-------------

  pip install pyinstaller
  pnpm -C apps/web build:static
  python scripts/bundle_web_app.py

Then:

  python scripts/build_binary.py

The build is platform-specific: a Windows binary built on Windows, a
Linux binary built on Linux, a macOS binary built on macOS. CI does
this automatically; local builds produce a binary for whatever OS you
run on.

Quirks worth knowing
--------------------

- ``reverie_api/_web_static`` is added with ``--add-data``. Without it
  the binary serves the API but renders a blank page.
- ``--collect-all uvicorn`` is required because uvicorn imports its
  workers dynamically and PyInstaller's static analysis misses them.
- We use ``--onefile`` for distribution simplicity. Cold-start is
  ~1-2s slower than ``--onedir`` because the bundle has to extract.
- On Windows we don't sign the binary — users will see SmartScreen
  warnings until we set up code signing as a follow-up.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINT = REPO_ROOT / "cli" / "src" / "reverie_cli" / "_entry.py"
BUILD_DIR = REPO_ROOT / "build_dist"
WORK_DIR = REPO_ROOT / "build_work"


def _resolve_pyinstaller() -> list[str]:
    """Return the argv prefix that runs PyInstaller, or raise."""

    # Prefer ``python -m PyInstaller`` so we use the same interpreter that's
    # running this script — keeps the bundled packages aligned with the
    # interpreter that built them.
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print(
            "error: PyInstaller is not installed.\n"
            "       Install it with: pip install pyinstaller",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return [sys.executable, "-m", "PyInstaller"]


def _ensure_entry_point() -> None:
    """Generate a minimal entry-point script.

    PyInstaller works best when the entry-point module is a clean,
    importable script with a ``if __name__ == "__main__"`` block — not a
    deeply-nested package's ``__main__.py``. So we write one next to the
    CLI source.
    """

    if ENTRY_POINT.exists():
        return
    ENTRY_POINT.write_text(
        '"""Reverie standalone-binary entry point."""\n\n'
        "from reverie_cli.main import cli\n\n"
        'if __name__ == "__main__":\n'
        "    cli()\n",
        encoding="utf-8",
    )
    print(f"created entry point at {ENTRY_POINT.relative_to(REPO_ROOT)}")


def _ensure_bundled_static() -> None:
    """Verify the static web app is bundled before we package."""

    static_dir = REPO_ROOT / "apps" / "api" / "src" / "reverie_api" / "_web_static"
    if not (static_dir / "index.html").exists():
        print(
            "warning: web app not bundled into the API package.\n"
            "         the binary will serve the API headless. To include\n"
            "         the 3D explorer, run:\n"
            "           pnpm -C apps/web build:static\n"
            "           python scripts/bundle_web_app.py\n"
            "         then re-run this script.",
            file=sys.stderr,
        )


def build(*, onefile: bool, name: str, clean: bool) -> int:
    _ensure_entry_point()
    _ensure_bundled_static()

    if clean:
        for d in (BUILD_DIR, WORK_DIR):
            if d.exists():
                print(f"removing {d.relative_to(REPO_ROOT)}/")
                shutil.rmtree(d)

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    # Cross-platform path separator for --add-data (PyInstaller uses : on
    # POSIX and ; on Windows).
    sep = ";" if os.name == "nt" else ":"

    static_src = REPO_ROOT / "apps" / "api" / "src" / "reverie_api" / "_web_static"
    add_data_args: list[str] = []
    if static_src.exists():
        add_data_args = [
            "--add-data",
            f"{static_src}{sep}reverie_api/_web_static",
        ]

    cmd: list[str] = [
        *_resolve_pyinstaller(),
        "--name", name,
        "--noconfirm",
        "--clean",
        "--distpath", str(BUILD_DIR),
        "--workpath", str(WORK_DIR),
        "--specpath", str(WORK_DIR),
        # Bundling strategy.
        "--onefile" if onefile else "--onedir",
        # Console app, not a windowed GUI.
        "--console",
        # Collect everything for libs that import dynamically.
        "--collect-all", "uvicorn",
        "--collect-all", "fastapi",
        "--collect-all", "starlette",
        "--collect-all", "reverie_api",
        "--collect-all", "reverie_cli",
        "--collect-all", "reverie_schema",
        "--collect-all", "reverie_openai",
        # Hidden imports — modules that PyInstaller's static analysis misses.
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "uvicorn.lifespan.off",
        "--hidden-import", "uvicorn.protocols.http.h11_impl",
        "--hidden-import", "uvicorn.protocols.websockets.websockets_impl",
        "--hidden-import", "uvicorn.loops.asyncio",
        "--hidden-import", "aiosqlite",
        # Static assets to include.
        *add_data_args,
        # Entry point.
        str(ENTRY_POINT),
    ]

    print("running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if result.returncode != 0:
        return result.returncode

    # Find the output binary.
    bin_name = f"{name}.exe" if os.name == "nt" else name
    bin_path = (BUILD_DIR / bin_name) if onefile else (BUILD_DIR / name / bin_name)

    if bin_path.exists():
        size_mb = bin_path.stat().st_size / (1024 * 1024)
        print()
        print(f"ok: built {bin_path.relative_to(REPO_ROOT)} ({size_mb:.1f} MB)")
        print(f"    try: {bin_path} --help")
    else:
        print(
            f"warning: build completed but binary not found at "
            f"{bin_path.relative_to(REPO_ROOT)}",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="Produce a directory bundle instead of a single file (faster startup).",
    )
    parser.add_argument(
        "--name",
        default="reverie",
        help="Output binary name (default: reverie).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete previous build artifacts before rebuilding.",
    )
    args = parser.parse_args()

    return build(onefile=not args.onedir, name=args.name, clean=args.clean)


if __name__ == "__main__":
    sys.exit(main())
