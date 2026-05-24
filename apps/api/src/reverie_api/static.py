"""Serve the bundled web app from the FastAPI process.

Why this exists
---------------

For local development we run two processes — uvicorn for the API and
``next dev`` for the web app. That works for developers but it's a poor
fit for end users: they have to install Node and pnpm just to use a
Python tool.

The ``pipx install reverie`` workflow ships the web app as a static export
(``apps/web/out``) inside the ``reverie_api`` Python package. This module
mounts that export as a ``StaticFiles`` route at ``/`` so users only ever
need Python.

How it's wired
--------------

When ``apps/web/out`` is present (which it is on installed wheels and
during development if the user has run ``pnpm -C apps/web build:static``),
:func:`mount_web_app` mounts:

  - ``/_next/...``  → static assets (JS chunks, CSS, etc.)
  - ``/`` (last)    → the built HTML pages, with SPA-style fallback to
                       ``index.html`` for unknown routes.

The static mount must come AFTER all API routers — otherwise ``/`` would
shadow ``/api/v1/...``. We use a small fallback class instead of raw
``StaticFiles`` so URLs like ``/run?id=abc`` (where the query string is
the routing signal) resolve cleanly, AND so unknown deep paths fall back
to the SPA shell rather than returning 404.
"""

from __future__ import annotations

import logging
from importlib import resources
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


# In dev installs we resolve to apps/web/out. In wheel installs the build
# script copies that directory into ``reverie_api/_web_static``.
_PACKAGED_DIRNAME = "_web_static"


def find_web_static_dir() -> Path | None:
    """Locate the static-export directory.

    Resolution order:

    1. Directory bundled inside the installed package (``_web_static/``).
       This is the production case for wheels.

    2. ``../../web/out`` relative to the package source. This is the dev
       case — running directly from a checkout where the user has done
       ``pnpm -C apps/web build:static``.

    3. ``REVERIE_WEB_STATIC_DIR`` environment variable override.

    Returns ``None`` if no built export is found anywhere — the caller
    should fall back to running without web UI mounting.
    """

    import os

    override = os.environ.get("REVERIE_WEB_STATIC_DIR")
    if override:
        p = Path(override).expanduser().resolve()
        if (p / "index.html").exists():
            return p

    # Bundled-in-wheel location.
    try:
        with resources.as_file(
            resources.files("reverie_api").joinpath(_PACKAGED_DIRNAME)
        ) as p:
            packaged = Path(p)
        if packaged.is_dir() and (packaged / "index.html").exists():
            return packaged
    except (FileNotFoundError, ModuleNotFoundError, TypeError, OSError):
        pass

    # Source-tree fallback (`apps/web/out` next to `apps/api/src`).
    here = Path(__file__).resolve()
    # apps/api/src/reverie_api/static.py -> apps/api/src/reverie_api ->
    # apps/api/src -> apps/api -> apps -> apps/web -> apps/web/out
    candidate = here.parents[3] / "web" / "out"
    if (candidate / "index.html").exists():
        return candidate

    return None


class SPAStaticFiles(StaticFiles):
    """Static files server with SPA-style fallback.

    Two non-default behaviours:

    1. **Suffix-less URLs** (``/run``, ``/foo/bar``) get ``/index.html``
       served from the matching subdirectory if present, else the root
       ``index.html`` so client-side routing can take over.

    2. **404s never reach the user.** Anything that would 404 falls back to
       ``index.html`` so the SPA shell can render its "not found" view
       instead of the FastAPI default error.

    Starlette's ``StaticFiles`` returns a 404 :class:`Response` for missing
    files (rather than raising), so the override has to inspect the
    response status code rather than catching an exception.
    """

    async def get_response(self, path: str, scope):  # type: ignore[override]
        # Suffix-less URLs (no dot in last segment) → try ``<path>/index.html``
        # first so deep client-side routes that map to a sub-directory shell
        # work cleanly.
        if path and "." not in path.rsplit("/", 1)[-1] and not path.endswith("/"):
            try:
                sub_index = await super().get_response(f"{path}/index.html", scope)
                if sub_index.status_code == 200:
                    return sub_index
            except StarletteHTTPException as exc:
                if exc.status_code != 404:
                    raise
                # Fall through to the main lookup.

        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            response = None

        if response is not None and response.status_code != 404:
            return response

        # SPA fallback — serve the root shell so client-side routing wins.
        directory = self.directory  # type: ignore[attr-defined]
        if directory is None:
            if response is not None:
                return response
            raise StarletteHTTPException(status_code=404)
        root = Path(str(directory)) / "index.html"
        if root.exists():
            return FileResponse(root)
        if response is not None:
            return response
        raise StarletteHTTPException(status_code=404)


def mount_web_app(app: FastAPI) -> Path | None:
    """Mount the static web export onto ``app`` if it's available.

    Returns the directory it mounted (or ``None`` if no export was found,
    in which case the API runs headless).
    """

    static_dir = find_web_static_dir()
    if static_dir is None:
        logger.info(
            "reverie_api: no bundled web app found; API runs headless. "
            "Build the web app with 'pnpm -C apps/web build:static' to enable "
            "the 3D explorer at the same origin."
        )
        return None

    # The Next.js build emits everything under ``out/_next/...`` so we don't
    # need a separate mount for assets — the SPA static handler covers it.
    app.mount("/", SPAStaticFiles(directory=str(static_dir), html=True), name="web")
    logger.info("reverie_api: mounted web app from %s", static_dir)
    return static_dir
