# Reverie — top-level developer commands.
#
# Cross-platform notes:
#   - On Windows, GNU Make is available via Chocolatey, scoop, or git-for-windows.
#   - PowerShell-native equivalents are documented in each target.
#   - The Python venv lives at ./.venv and the activation path is .venv\Scripts.

PY      := .venv/Scripts/python.exe
UV      := py -m uv
PNPM    := pnpm

.PHONY: help install install-py install-js test test-py test-js typecheck \
        fixtures clean dev smoke build-web bundle binary

help:
	@echo "Reverie developer targets:"
	@echo "  make install      install all packages (Python + JS)"
	@echo "  make test         run every test suite"
	@echo "  make typecheck    run TypeScript type-check"
	@echo "  make fixtures     regenerate cross-language fixtures"
	@echo "  make build-web    static-export the 3D explorer to apps/web/out"
	@echo "  make bundle       bundle the web app into the API wheel"
	@echo "  make binary       build a single standalone binary with PyInstaller"
	@echo "  make dev          start the FastAPI backend (uvicorn, with reload)"
	@echo "  make smoke        end-to-end smoke test against a running backend"
	@echo "  make clean        remove build artifacts"

# -----------------------------------------------------------------------------
# Install
# -----------------------------------------------------------------------------

install: install-py install-js

install-py:
	$(UV) venv .venv --python 3.13
	$(UV) pip install --python $(PY) -e "packages/schema-py[dev]"
	$(UV) pip install --python $(PY) -e "apps/api[dev]"
	$(UV) pip install --python $(PY) -e "packages/adapter-openai[dev]"
	$(UV) pip install --python $(PY) -e "cli[dev]"

install-js:
	$(PNPM) install

# -----------------------------------------------------------------------------
# Test
# -----------------------------------------------------------------------------

# `pytest` from the repo root picks up the top-level pytest.ini, which scopes
# both the schema-py and api test suites and enables async mode.
test: fixtures test-py test-js

test-py:
	$(PY) -m pytest

test-js:
	$(PNPM) -C packages/schema test

typecheck:
	$(PNPM) -C packages/schema typecheck

# -----------------------------------------------------------------------------
# Cross-language fixtures
# -----------------------------------------------------------------------------

fixtures:
	$(PY) packages/schema-py/scripts/emit_fixtures.py

# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------

dev:
	$(PY) -m reverie_api

smoke:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke.ps1

# -----------------------------------------------------------------------------
# Distribution builds
# -----------------------------------------------------------------------------

# Build the 3D explorer as a static export, ready to be served by the API.
build-web:
	$(PNPM) -C apps/web build:static

# Bundle the static export into the reverie-api package source tree so the
# next pip/wheel build picks it up automatically.
bundle: build-web
	$(PY) scripts/bundle_web_app.py

# Build a single standalone binary that includes Python, the API, the CLI,
# and the bundled web app. Output lands in build_dist/.
binary: bundle
	$(PY) scripts/build_binary.py

# -----------------------------------------------------------------------------
# Clean
# -----------------------------------------------------------------------------

clean:
	$(PNPM) -C packages/schema exec rm -rf dist node_modules || true
	rm -rf packages/schema-py/.pytest_cache
	rm -rf packages/schema-py/src/reverie_schema.egg-info
	rm -rf packages/schema-py/build packages/schema-py/dist
	rm -rf apps/api/.pytest_cache
	rm -rf apps/api/src/reverie_api.egg-info
	rm -rf apps/api/build apps/api/dist
	rm -rf data
