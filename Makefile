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
        fixtures clean dev

help:
	@echo "Reverie developer targets:"
	@echo "  make install      install all packages (Python + JS)"
	@echo "  make test         run every test suite"
	@echo "  make typecheck    run TypeScript type-check"
	@echo "  make fixtures     regenerate cross-language fixtures"
	@echo "  make dev          (Phase 0.2+) start the API backend"
	@echo "  make clean        remove build artifacts"

# -----------------------------------------------------------------------------
# Install
# -----------------------------------------------------------------------------

install: install-py install-js

install-py:
	$(UV) venv .venv --python 3.13
	$(UV) pip install --python $(PY) -e "packages/schema-py[dev]"

install-js:
	$(PNPM) install

# -----------------------------------------------------------------------------
# Test
# -----------------------------------------------------------------------------

test: fixtures test-py test-js

test-py:
	$(PY) -m pytest packages/schema-py

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
# Phase 0.2+ (placeholder targets)
# -----------------------------------------------------------------------------

dev:
	@echo "[Reverie] Phase 0.2 not implemented yet — will start the FastAPI backend."

# -----------------------------------------------------------------------------
# Clean
# -----------------------------------------------------------------------------

clean:
	$(PNPM) -C packages/schema exec rm -rf dist node_modules || true
	rm -rf packages/schema-py/.pytest_cache
	rm -rf packages/schema-py/src/reverie_schema.egg-info
	rm -rf packages/schema-py/build packages/schema-py/dist
