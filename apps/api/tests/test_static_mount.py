"""Tests for the bundled-web-app static mount.

The static mount turns a single ``uvicorn reverie_api.main:app`` process
into a complete one-port stack: API on ``/api/v1/*`` and the 3D explorer
served from ``/``.

These tests cover:

  - ``find_web_static_dir`` resolution order (env override > package > source).
  - ``mount_web_app`` is a no-op when no export is built.
  - The SPA fallback handler serves ``index.html`` for unknown deep paths so
    the client-side router can render a 404.
  - The static mount doesn't shadow API routes.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from reverie_api.config import Settings
from reverie_api.main import create_app
from reverie_api.static import find_web_static_dir, mount_web_app


@pytest.fixture
def fake_static_dir(tmp_path: Path) -> Path:
    """Build a tiny stand-in for the Next.js export."""

    out = tmp_path / "fake_out"
    (out / "_next" / "static").mkdir(parents=True)
    (out / "index.html").write_text(
        "<html><body>FAKE STATIC ROOT</body></html>", encoding="utf-8"
    )
    (out / "run").mkdir()
    (out / "run" / "index.html").write_text(
        "<html><body>FAKE RUN PAGE</body></html>", encoding="utf-8"
    )
    (out / "_next" / "static" / "asset.js").write_text(
        "console.log('asset')", encoding="utf-8"
    )
    return out


def test_find_web_static_dir_uses_env_override(
    monkeypatch: pytest.MonkeyPatch, fake_static_dir: Path
):
    monkeypatch.setenv("REVERIE_WEB_STATIC_DIR", str(fake_static_dir))
    found = find_web_static_dir()
    assert found is not None
    assert found.resolve() == fake_static_dir.resolve()


def test_find_web_static_dir_returns_none_when_path_missing_index(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("REVERIE_WEB_STATIC_DIR", str(empty))
    # No index.html in override → fall through to package/source resolution,
    # which may or may not find one. We only assert that an explicit
    # invalid override doesn't crash and is ignored.
    # (Other resolution paths can still resolve to a real bundle.)
    result = find_web_static_dir()
    assert result is None or result != empty.resolve()


@pytest.mark.asyncio
async def test_static_root_serves_index_html(
    monkeypatch: pytest.MonkeyPatch, fake_static_dir: Path, tmp_path: Path
):
    monkeypatch.setenv("REVERIE_WEB_STATIC_DIR", str(fake_static_dir))

    settings = Settings(db_path=tmp_path / "test.db", env="development")
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.get("/")
            assert resp.status_code == 200
            assert "FAKE STATIC ROOT" in resp.text


@pytest.mark.asyncio
async def test_static_subpath_serves_nested_index(
    monkeypatch: pytest.MonkeyPatch, fake_static_dir: Path, tmp_path: Path
):
    monkeypatch.setenv("REVERIE_WEB_STATIC_DIR", str(fake_static_dir))

    settings = Settings(db_path=tmp_path / "test.db", env="development")
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.get("/run")
            assert resp.status_code == 200
            assert "FAKE RUN PAGE" in resp.text


@pytest.mark.asyncio
async def test_unknown_deep_path_falls_back_to_index(
    monkeypatch: pytest.MonkeyPatch, fake_static_dir: Path, tmp_path: Path
):
    monkeypatch.setenv("REVERIE_WEB_STATIC_DIR", str(fake_static_dir))

    settings = Settings(db_path=tmp_path / "test.db", env="development")
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.get("/totally-unknown-route")
            # SPA fallback: 200 + the root shell, not 404.
            assert resp.status_code == 200
            assert "FAKE STATIC ROOT" in resp.text


@pytest.mark.asyncio
async def test_static_mount_does_not_shadow_api(
    monkeypatch: pytest.MonkeyPatch, fake_static_dir: Path, tmp_path: Path
):
    monkeypatch.setenv("REVERIE_WEB_STATIC_DIR", str(fake_static_dir))

    settings = Settings(db_path=tmp_path / "test.db", env="development")
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            # API endpoint must still reach the FastAPI router.
            api = await client.get("/api/v1/runs?limit=1")
            assert api.status_code == 200
            # Health endpoint too.
            health = await client.get("/health")
            assert health.status_code == 200
            assert health.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_static_assets_served_from_next_subpath(
    monkeypatch: pytest.MonkeyPatch, fake_static_dir: Path, tmp_path: Path
):
    monkeypatch.setenv("REVERIE_WEB_STATIC_DIR", str(fake_static_dir))

    settings = Settings(db_path=tmp_path / "test.db", env="development")
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.get("/_next/static/asset.js")
            assert resp.status_code == 200
            assert "console.log" in resp.text


def test_mount_is_noop_when_export_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """The API has to start cleanly even if no static export was built."""

    # Point the override at a directory that has no index.html.
    monkeypatch.setenv("REVERIE_WEB_STATIC_DIR", str(tmp_path / "nonexistent"))

    # Calling mount_web_app on a fresh app must not raise.
    from fastapi import FastAPI

    app = FastAPI()
    result = mount_web_app(app)
    # Either no static dir was found anywhere → returns None; or the dev
    # tree's apps/web/out is present → returns its path. We only assert
    # that the call doesn't crash and the app remains usable.
    assert result is None or result.exists()
