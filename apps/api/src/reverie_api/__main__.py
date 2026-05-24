"""Entry point: ``python -m reverie_api`` runs the dev server."""

from __future__ import annotations

import logging

import uvicorn

from reverie_api.config import load_settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = load_settings()
    uvicorn.run(
        "reverie_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_dev,
        log_level="info",
    )


if __name__ == "__main__":
    main()
