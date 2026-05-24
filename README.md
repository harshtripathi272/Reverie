<div align="center">

# Reverie

### **Cognitive observability, replay, and comparative debugging for autonomous AI agents.**

*Chrome DevTools for AI agents. OpenTelemetry for agent cognition.*

[![tests](https://img.shields.io/badge/tests-409%20green-22c55e.svg)](#testing)
[![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![node](https://img.shields.io/badge/node-20%2B-339933.svg)](https://nodejs.org)
[![license](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

</div>

---

## What it is

When you run an AI agent today it produces a river of invisible activity:
goals, tool calls, memory retrievals, retries, sub-agent spawns, validations.
You see none of it. When something goes wrong you have two options — read a
wall of JSON logs, or guess.

**Reverie is the tool that was missing.** It instruments your agent at the
runtime level, captures every cognitive event, normalizes them into a universal
schema, stores them in an append-only log, and lets you replay, compare, and
visualize the whole journey as a 3D world of glowing orbs.

For the long version, see [`ABOUT.md`](./ABOUT.md). For the architecture,
see [`SRS.md`](./SRS.md).

## Demo

```
reverie run python my_agent.py     # instrument any agent — zero code change
reverie runs list                   # see all your recorded runs
reverie replay <id> --jump-failure  # find the moment it broke
reverie compare <run-a> <run-b>     # find the moment two runs diverged
open http://localhost:3000          # explore in 3D
```

## Quick start

### Prerequisites

- **Python 3.11+** with [`uv`](https://docs.astral.sh/uv/) installed
- **Node.js 20+** with [`pnpm`](https://pnpm.io) installed

### Install everything

```bash
git clone https://github.com/<your-org>/reverie.git
cd reverie
make install
```

This creates a `.venv`, installs all four Python packages in editable mode,
and pulls the JS workspace.

### Boot the whole stack with one command

```bash
reverie start
```

This spawns the FastAPI backend, waits for it to become healthy, spawns the
Next.js explorer, and opens your browser at `http://localhost:3000`. Ctrl+C
once tears both processes down cleanly. Useful flags:

- `--no-web` — start only the API.
- `--no-browser` — don't auto-open.
- `--prod` — run the web app via `next start` (after `pnpm -C apps/web build`).
- `--backend-port N` / `--web-port N` — non-default ports.

### Instrument an agent and produce a recorded run

```bash
reverie run python examples/complex_agent.py
```

Your agent runs normally; Reverie hooks the OpenAI Agents SDK tracing system
and streams every event to the backend. No code changes needed.

Click any run in the 3D explorer to enter it. Click any orb for its full
event payload. Drag orbs around like nodes in Obsidian — positions are local
to your view and don't mutate the recorded data.

### Manual control (if you'd rather)

```bash
make dev               # backend on http://127.0.0.1:8000
pnpm -C apps/web dev   # web on http://localhost:3000
```

## What's in the box

| Layer | What it does |
|---|---|
| **Schema** | 22 cognitive event types, frozen v1.0 — TypeScript (Zod) + Python (Pydantic v2) — byte-identical wire format guaranteed by an interop test |
| **OpenAI Agents SDK adapter** | Auto-injects via `reverie run` using a `sitecustomize.py` hook — the same mechanism `opentelemetry-instrument` uses |
| **FastAPI + SQLite backend** | Append-only event log in WAL mode, atomic batch ingest, WebSocket fan-out, < 5 ms p50 ingestion |
| **Snapshot engine** | Reconstructs the full agent state at any point in any run via lazy checkpointing every 50 events |
| **Graph intelligence** | Builds the cognitive DAG, assigns L1–L4 zoom levels, runs all six SRS-defined anomaly heuristics (loop, hotspot, bottleneck, poison, explosion, abandon) |
| **Salience scorer** | Per-node 0.0–1.0 importance score; nodes < 0.10 hidden by default |
| **AI summary service** | Optional Claude-backed natural language explanations, DB-cached so the same region never gets summarized twice |
| **Comparative debugger** | Needleman-Wunsch alignment over event semantics, structured diff across all seven SRS dimensions, fault tree, AI narrative |
| **CLI** | 12 subcommands. Most ship `--json` for scripting |
| **3D renderer** | Next.js 15 + React Three Fiber 9 with custom Fresnel-rim shaders, ACES tone mapping, selective bloom |

## CLI reference

```text
reverie start                        Start backend + web + open browser.
       --backend-port N              Backend port (default 8000).
       --web-port N                  Web port (default 3000).
       --no-web                      Skip the web app.
       --no-browser                  Don't auto-open the browser.
       --dev / --prod                Use `next dev` (default) or `next start`.
reverie run <cmd...>                 Run any command with auto-instrumentation.
reverie status                       Ping the backend and show its health.
reverie runs list                    List recent runs (most recent first).
reverie runs show <id>               Show one run plus its event timeline.
reverie state <id> [--at N]          Cognitive state at a given event index.
reverie replay <id>                  Stream events to the terminal.
       --jump-failure                Skip ahead to the first failure event.
       --to N                        Replay the first N events only.
       --speed 1|2|5|10|instant      Pacing.
reverie graph <id> [--level N]       Render the cognitive DAG as ASCII.
reverie anomalies <id> [--kind K]    Surface the anomaly annotations.
reverie zoom <id>                    Per-zoom-level node distribution.
reverie summary <id> [--cluster ID]  AI summary of a graph cluster.
reverie compare <a> <b>              Diff + divergence + fault tree + narrative.
```

Add `--help` to any subcommand for the full option list.

## Examples

`examples/` ships three reference agents you can run instrumented:

- **`basic_agent.py`** — minimal happy path; emits ~10 events.
- **`complex_agent.py`** — multi-subagent run with intentional loops and a
  failing reviewer step. Triggers `loop` and `explosion` anomalies.
- **`failing_agent.py`** — single-thread run with a clean failure path; perfect
  for `reverie replay --jump-failure`.
- **`paired_runs.py`** — twin runs (one success, one failure) with the same
  goal; perfect for `reverie compare`.

```bash
# Get the comparative debugger gate test in one command:
reverie run python examples/paired_runs.py
reverie runs list --limit 2 --json | jq -r '.items[].id' | xargs reverie compare
```

## Configuration

Most things have sensible defaults. The knobs that matter most:

| Variable | Default | Used by |
|---|---|---|
| `REVERIE_BACKEND_URL` | `http://127.0.0.1:8000` | adapter, CLI, web app |
| `REVERIE_AGENT_ID` | `openai-agent` | adapter (label on emitted events) |
| `REVERIE_DISABLED` | unset | adapter (no-op when truthy) |
| `REVERIE_DB_PATH` | `data/reverie.db` | backend |
| `ANTHROPIC_API_KEY` | unset | AI summary service (no-op without) |
| `REVERIE_AI_DISABLED` | unset | force AI summaries off |
| `NEXT_PUBLIC_BACKEND_URL` | same as backend | web app rewrites |

## Project layout

```
reverie/
├── packages/
│   ├── schema/           — TypeScript types + Zod (the canonical wire format)
│   ├── schema-py/        — Pydantic v2 (parallel source of truth for Python)
│   └── adapter-openai/   — OpenAI Agents SDK adapter
├── apps/
│   ├── api/              — FastAPI backend + SQLite event log
│   └── web/              — Next.js 15 + R3F 3D explorer
├── cli/                  — `reverie` CLI
├── examples/             — reference agents (basic, complex, failing, paired)
├── scripts/              — smoke tests
├── ABOUT.md              — product vision (long-form)
├── SRS.md                — full architecture + 8-layer spec
├── CONTRIBUTING.md       — how to contribute
├── CODE_OF_CONDUCT.md    — community standards
└── LICENSE               — MIT
```

## Testing

The project ships **400+ tests** covering schema, adapter, backend, snapshot
engine, graph intelligence, anomaly detectors, salience scorer, AI client,
comparative debugger, and the CLI.

```bash
make test          # everything (Python + TypeScript)
make test-py       # Python only
make test-js       # TypeScript schema tests only
```

Cross-language interop is enforced by a fixture-based test: a Python script
emits a JSON file, and the TypeScript Zod schema validates it. Drift between
the two languages would fail this test immediately.

## Contributing

We welcome contributions. Read [`CONTRIBUTING.md`](./CONTRIBUTING.md) for
the development workflow, code style, and the schema-stability rules.

The schema is **frozen at v1.0**. Any new event types or fields are additive
only; breaking changes require a coordinated major-version bump in both the
Python and TypeScript implementations.

## Roadmap

The 21-week plan in [`SRS.md`](./SRS.md) is fully shipped. The current focus:

- **More adapters** — LangGraph, CrewAI, AutoGen, MCP, plus a generic Python
  SDK so anyone can instrument their own framework.
- **Replay session sync** — multiple users scrubbing the same run together.
- **Run pinning + retention policies** — prevent valuable failed runs from
  being garbage collected.
- **Saved comparisons** — pair-of-runs as first-class entities with
  shareable URLs.

## License

MIT — see [`LICENSE`](./LICENSE).

---

<sub>**Reverie** — Observe. Replay. Understand.</sub>
