<div align="center">

# Reverie

### **Cognitive observability, replay, and comparative debugging for autonomous AI agents.**

*Chrome DevTools for AI agents. OpenTelemetry for agent cognition.*

[![tests](https://img.shields.io/badge/tests-409%20green-22c55e.svg)](#testing)
[![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![node](https://img.shields.io/badge/node-20%2B-339933.svg)](https://nodejs.org)
[![license](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

</div>

<div align="center">

### The 3D cognitive explorer

<img src="sc/graph.png" alt="Reverie 3D orb world — each orb is a cognitive event, connections show causality" width="800" />

*Every orb is a thought. Every connection is a causal link. Orbit, zoom, drag, click.*

---

### Click any orb to inspect the full event

<img src="sc/details.png" alt="Reverie detail panel — full event payload with URLs, queries, token costs" width="800" />

*Full payload: tool name, input args, output, URLs (clickable), token cost, latency. Annotate with Avoid / Focus / Done to steer the next run.*

</div>

---

## Table of contents

- [What it is](#what-it-is)
- [Why you'd use it](#why-youd-use-it)
- [Quick start (5 minutes)](#quick-start-5-minutes)
  - [Prerequisites](#prerequisites)
  - [Install](#install)
  - [Boot the whole stack with one command](#boot-the-whole-stack-with-one-command)
  - [Record your first run](#record-your-first-run)
  - [Open it in 3D](#open-it-in-3d)
- [The 3D explorer](#the-3d-explorer)
  - [Reading the orb world at a glance](#reading-the-orb-world-at-a-glance)
  - [Controls](#controls)
  - [The HUD](#the-hud)
  - [Zoom levels (L1–L4)](#zoom-levels-l1l4)
- [The CLI in detail](#the-cli-in-detail)
- [Recipes](#recipes)
- [Using Reverie in your own project](#using-reverie-in-your-own-project)
  - [Option 1: Zero-code-change with reverie run](#option-1-zero-code-change-with-reverie-run-recommended)
  - [Option 2: One-line import](#option-2-one-line-import-in-your-code)
  - [Option 3: Add as a dependency](#option-3-add-reverie-as-a-dependency-in-your-project)
  - [Option 4: Direct HTTP API (any framework)](#option-4-direct-http-api-any-framework-any-language)
- [Configuration reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [What's in the box](#whats-in-the-box)
- [Project layout](#project-layout)
- [Testing](#testing)
- [Contributing](#contributing)
- [Roadmap](#roadmap)
- [License](#license)

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

For the long-form vision, see [`ABOUT.md`](./ABOUT.md). For the architecture,
see [`SRS.md`](./SRS.md).

## Why you'd use it

- **A run failed and you need to know why.** Open it in the explorer,
  jump to the failure, walk the cause-and-effect chain backward.
- **Two runs of the same prompt produced different outcomes.** Hand both
  runs to `reverie compare` and Reverie tells you the exact moment they
  diverged and what was different about each path.
- **Your agent is burning tokens and you can't tell where.** The salience
  scorer surfaces hot spots; the anomaly detector flags retry loops and
  explosion patterns automatically.
- **You want to understand a complex multi-agent run.** Zoom from the top-
  level mission down to individual tool calls without drowning in detail.
- **You want to share what your agent did.** Export a replay, share the
  run ID, link teammates straight into the explorer.

---

## Quick start (5 minutes)

### Prerequisites

You need three things on your machine before installing.

| Requirement | Why | How to install |
|---|---|---|
| **Python 3.11+** | Backend, adapter, and CLI | [python.org](https://www.python.org/downloads/) |
| **`uv`** (fast Python package manager) | Creates the venv and installs Python packages | `pip install uv` or see [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/) |
| **Node.js 20+ with `pnpm`** | The 3D web explorer (only needed for development; not for end-users running the bundled binary) | [nodejs.org](https://nodejs.org/) then `npm install -g pnpm@10` |

Optional but recommended:

- **GNU `make`** — used by the install/test/dev shortcuts. On Windows it
  comes with Git for Windows, scoop, or Chocolatey. If you don't want it,
  every command in this README has a no-make equivalent.
- **An [Anthropic API key](https://console.anthropic.com/)** — enables the
  AI summary feature. Reverie works without it; AI buttons just become
  no-ops.

### Three ways to install

**1. Single binary (simplest, end-user)**

Download the pre-built binary for your OS from the
[releases page](https://github.com/your-org/reverie/releases):

```bash
# macOS/Linux
chmod +x reverie-linux-x64
./reverie-linux-x64 start

# Windows
./reverie-windows-x64.exe start
```

No Python, no Node, no pnpm. The binary bundles the entire stack —
backend, adapter, CLI, and the 3D explorer — into one file. ~30 MB.

**2. PyPI install (recommended for Python users)**

```bash
pipx install reverie-obs
reverie start
```

The `pipx` install gives you `reverie` on your PATH, with the 3D
explorer bundled in (no Node toolchain needed). Use `pip install reverie-obs`
if you'd rather install into your project's venv.

**3. From source (for development)**

```bash
git clone https://github.com/<your-org>/reverie.git
cd reverie
make install
```

This:

1. Creates a `.venv/` virtualenv under the repo root.
2. Installs the four Python packages in editable mode (`schema-py`, `api`,
   `adapter-openai`, `cli`).
3. Installs the JS workspace (`pnpm install`).

If you don't have `make`:

```bash
uv venv .venv --python 3.13
uv pip install --python .venv/bin/python -e "packages/schema-py[dev]"
uv pip install --python .venv/bin/python -e "apps/api[dev]"
uv pip install --python .venv/bin/python -e "packages/adapter-openai[dev]"
uv pip install --python .venv/bin/python -e "cli[dev]"
pnpm install
```

On **Windows**, replace `.venv/bin/python` with `.venv/Scripts/python.exe`.

After install, activate the venv so `reverie` is on your `PATH`:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (cmd)
.venv\Scripts\activate.bat
```

Verify:

```bash
reverie --help
```

### Boot the whole stack with one command

```bash
reverie start
```

This single command:

1. Spawns the FastAPI backend on port `8000`.
2. Polls `/health` until it's actually serving.
3. Spawns the Next.js 3D explorer on port `3000`.
4. Opens your default browser at `http://localhost:3000`.
5. Forwards both processes' logs to your terminal.

Press **Ctrl+C** once and Reverie stops both processes cleanly.

Useful flags:

| Flag | What it does |
|---|---|
| `--no-web` | Skip the web app — useful if you only want the API. |
| `--no-browser` | Don't auto-open the browser. |
| `--prod` | Use `next start` (faster, needs `pnpm -C apps/web build` first). |
| `--backend-port 9000` | Use a different port for the backend. |
| `--web-port 4000` | Use a different port for the web app. |
| `--repo /path/to/reverie` | Point at a checkout other than the cwd. |

If you'd rather start the pieces yourself:

```bash
make dev               # backend on http://127.0.0.1:8000
pnpm -C apps/web dev   # web on http://localhost:3000
```

### Record your first run

In a second terminal (with the venv activated):

```bash
reverie run python examples/complex_agent.py
```

This is a synthetic agent that runs without needing any API keys. It emits
~30 events including a deliberate retry loop and a failed validation. You'll
see events stream into the dashboard in real time.

Other examples that ship with the repo:

- **`examples/basic_agent.py`** — minimal happy path, ~10 events.
- **`examples/complex_agent.py`** — multi-subagent run with intentional
  loops and a failing reviewer. Triggers the `loop` and `explosion`
  anomaly detectors.
- **`examples/failing_agent.py`** — single-thread run with a clean failure
  path. Pair with `reverie replay --jump-failure`.
- **`examples/paired_runs.py`** — emits two runs (one success, one
  failure) of the same goal. Pair with `reverie compare`.

### Open it in 3D

Open `http://localhost:3000`. You'll see a list of recent runs. Click any
one to enter the explorer.

What you should see immediately:

- A black void with stars in the distance.
- Glowing orbs floating in 3D, color-coded by event type.
- Lines of light connecting parents to children.
- A HUD overlay with the run name, event count, and zoom controls.

Click any orb to open its detail panel. Drag any orb to reposition it (your
positions are local to the browser session and don't mutate the recorded
data). Right-click and drag to pan; mouse wheel to zoom; left-click and
drag empty space to orbit.

That's the entire happy path. Everything below is depth on each piece.

---

## The 3D explorer

### Reading the orb world at a glance

Every orb is one cognitive event. Color encodes type. Size encodes
salience (importance). Pulsing means something is unusual.

| Color | Type | Meaning |
|---|---|---|
| **Violet (large)** | `goal.created`, `goal.updated`, `goal.completed`, `goal.failed` | A high-level objective. Big and central. |
| **Cyan-blue** | `tool.called`, `tool.returned` | The agent invoked an external tool. |
| **Emerald** | `memory.retrieved`, `memory.stored` | A memory operation. |
| **Amber (pulsing)** | `retry.triggered` | The agent hit a failure and is trying again. Visible warning light. |
| **Red (intense pulse)** | Anything ending in `.failed` | Something blew up. Hard to miss. |
| **Purple** | `reflection.generated` | The agent paused to think about its own progress. |
| **Teal** | `subagent.spawned`, `subagent.completed` | Helper agent got delegated to. |
| **White hover ring** | — | "I'm hovering this orb" affordance. |
| **Colored selection ring** | — | "I'm currently selected" affordance. |

The thicker the connection, the more important that hop is. Connections
on the **critical path** (the chain of events that produced the run's
final outcome) are visibly thicker and brighter, with a flowing point of
light during replay.

### Controls

| Action | What it does |
|---|---|
| **Left-click empty space + drag** | Orbit the camera. |
| **Mouse wheel** | Zoom toward/away from the cursor. |
| **Right-click + drag** | Pan (truck/dolly). |
| **Left-click an orb** | Select it. The detail panel opens with the full event payload. |
| **Click + drag an orb** | Move it (Obsidian-style). Camera orbit auto-disables during drag. |
| **Hover an orb** | Thin white ring appears. Halo brightens slightly. |
| **Click selected orb again** | Deselect. |
| **Reset view** | Frames the whole graph. Button in the top-right HUD. |
| **Frame selected** | Flies the camera to the selected orb. Button in the HUD. |

A click that travels less than ~4 world units before pointer-up is treated
as a click (toggles selection). Anything more is a drag.

### The HUD

Stuff layered on top of the 3D scene:

- **Header** (top-left). Run ID, agent ID, status (running/completed/failed),
  total event count.
- **Run stats** (top-right). Duration, total tokens, tool calls, retries.
- **Legend** (bottom-left). Color key for the orb types currently visible.
- **View controls** (bottom-right). Reset view, frame selected, zoom-level
  selector.
- **Node detail panel** (right side). Opens when you select an orb. Shows
  the full event payload (timestamp, parent ID, kind, payload JSON).
- **Loading overlay** — a brief spinner while the initial graph loads.

### Zoom levels (L1–L4)

The same run can be viewed at four levels of detail. Switch with the
zoom-level dropdown in the HUD.

| Level | Shows | Typical orb count | When to use |
|---|---|---|---|
| **L1 — Mission** | Top-level goals only. | 1–5 orbs | "What was the agent trying to do?" |
| **L2 — Task** | Subtasks and major delegations. | 5–30 orbs | "How was the work divided up?" |
| **L3 — Operation** | Individual tool calls and memory ops. | 30–200 orbs | "What did the agent actually do?" |
| **L4 — Raw** | Every event including retries and intermediate states. | 200–10,000+ | Deep debugging. |

Salience filtering layers on top of zoom: events scoring below 0.10 are
hidden by default at any level. The salience score is computed from
critical-path membership, anomaly markers, and resource consumption.

---

## The CLI in detail

Every CLI command takes `--help` for the full list of flags. Most ship a
`--json` flag so you can pipe results into other tools.

### `reverie init` — make the CLI accessible from anywhere

Saves the path of your Reverie checkout (or installation) to
`~/.reverie/config.json`. After this, every other command — `start`, `run`,
`annotate`, `guidance` — works from any directory on your machine.

```bash
# From inside the Reverie checkout (auto-detects):
reverie init

# From anywhere, with explicit path:
reverie init --repo /path/to/reverie

# Inspect / clear:
reverie init --show
reverie init --clear
```

Resolution order for the repo path: explicit `--repo` flag → `REVERIE_REPO`
env var → saved config → walk upward from cwd looking for marker files.

### `reverie start` — boot everything

Spawns the backend, waits for it to be healthy, spawns the web app, opens
your browser. Ctrl+C cleans up both processes.

```bash
reverie start
reverie start --no-browser
reverie start --backend-port 9000 --web-port 4000
reverie start --no-web              # API only
reverie start --prod                # uses `next start` (build first)
```

### `reverie run <cmd...>` — auto-instrument any command

```bash
reverie run python my_agent.py
reverie run --agent-id my-prod-bot python my_agent.py
reverie run python -m my_agent_pkg
```

Reverie injects a `sitecustomize.py` hook into the subprocess Python
environment. The OpenAI Agents SDK adapter latches onto the SDK's tracing
system and translates every span into a Reverie cognitive event. **No
changes to your agent code are required.** If the backend is unreachable
the adapter degrades silently — your agent runs unchanged.

Useful flags:

- `--agent-id ID` — label for the run (overrides `REVERIE_AGENT_ID`).
- `--no-trace` — disable instrumentation entirely (handy for A/B
  comparison runs).

### `reverie status` — backend health

```bash
reverie status
reverie status --json
```

Pings the backend, reports version, uptime, and total run count.

### `reverie runs list` / `reverie runs show <id>`

```bash
reverie runs list
reverie runs list --limit 5 --json
reverie runs show <run-id>
reverie runs show <run-id> --tail 20
```

`list` returns runs newest-first. `show` includes the run summary plus
the recorded event timeline.

### `reverie state <id>` — agent state at any moment

```bash
reverie state <run-id>           # final state
reverie state <run-id> --at 50   # state after the 50th event
```

Reconstructs the cognitive state from the snapshot store: active goals,
working memory contents, recent tool results, cumulative token usage.

### `reverie replay <id>` — terminal replay

```bash
reverie replay <run-id>                          # 1× speed
reverie replay <run-id> --speed 5                # 5× speed
reverie replay <run-id> --speed instant          # no pacing
reverie replay <run-id> --jump-failure           # skip ahead to first failure
reverie replay <run-id> --to 100                 # only the first 100 events
```

Streams the event timeline to stdout with sensible formatting and color.
This is the feature that proves Reverie isn't a demo — it's useful even
without graphics.

### `reverie graph <id>` — ASCII cognitive DAG

```bash
reverie graph <run-id>
reverie graph <run-id> --level 2     # render at zoom level 2 only
```

ASCII tree of the cognitive DAG. Useful for piping into a notes file or
diffing across runs.

### `reverie anomalies <id>` — surface flagged regions

```bash
reverie anomalies <run-id>
reverie anomalies <run-id> --kind loop
reverie anomalies <run-id> --json
```

Lists every anomaly the graph engine flagged: loops, hotspots, bottlenecks,
poison memory, branching explosions, abandoned threads.

### `reverie zoom <id>` — node distribution per zoom level

```bash
reverie zoom <run-id>
```

Shows how many nodes appear at each of L1–L4 — a quick sanity check that
the run isn't pathologically dense or sparse.

### `reverie summary <id>` — AI-written summaries

```bash
reverie summary <run-id>                          # top-level summary
reverie summary <run-id> --cluster <cluster-id>   # specific cluster
```

Requires `ANTHROPIC_API_KEY` to be set. The result is cached in the
database keyed by content hash, so the same region never gets summarized
twice.

### `reverie compare <run-a> <run-b>` — comparative debugger

```bash
reverie compare <run-a> <run-b>
reverie compare <run-a> <run-b> --json
```

The flagship debugging feature. Lines up two runs by **meaning** (not by
event index — extra retries don't throw off the alignment), pinpoints
the first divergence, computes the structured diff across all seven
dimensions, walks the fault tree backward from the failure to its root
cause, and writes an AI narrative explaining what went wrong (if the API
key is set).

### `reverie annotate` and `reverie guidance` — steer the next run with feedback

After a run finishes, you can mark nodes in the graph as `avoid`,
`focus`, `done`, or `note`. Those annotations are attached to the agent
(not just the run) and the **next** run automatically receives them as a
system-prompt prefix when you opt in.

```bash
# Mark a dead-end so the agent doesn't try it again next time.
reverie annotate <run-id> <node-id> avoid --note "this approach was too broad"

# Mark a promising direction for the agent to focus on.
reverie annotate <run-id> <node-id> focus --note "the cached lookup was efficient"

# Mark something as already done — agent skips it on repeat encounter.
reverie annotate <run-id> <node-id> done

# List or clear annotations on a run.
reverie annotations <run-id>
reverie annotations <run-id> --clear

# Preview what the next run will see.
reverie guidance <agent-id>
reverie guidance <agent-id> --format prompt    # raw text
reverie guidance <agent-id> --format markdown  # for humans
reverie guidance <agent-id> --tag research     # filter by topic
reverie guidance <agent-id> --clear            # wipe all guidance for this agent

# Activate the feedback loop for the next run.
REVERIE_USE_GUIDANCE=1 reverie run python my_agent.py
```

The agent receives a clean prompt prefix like:

```
PRIOR RUN GUIDANCE FROM USER:

Avoid these approaches (the user marked them as dead-ends):
  - tool.called: this approach was too broad

Focus on these directions (the user marked them as promising):
  - memory.retrieved: the cached lookup was efficient
```

This is a **between-runs** mechanism, not mid-flight intervention. Runs
are immutable; annotations live alongside them. You always run the agent
again, with the user-curated context applied.

---

## Recipes

### Find why your agent failed

```bash
# 1. Run the failing agent.
reverie run python my_agent.py

# 2. Note the run ID printed at the end. Then:
reverie replay <run-id> --jump-failure
```

Or in the explorer: open the run, the failure orb is the obvious red one.
Click it, read the parent chain.

### Compare a working run vs. a broken run

```bash
# Capture both runs.
reverie run python my_agent.py            # the good one
reverie run python my_agent_changed.py    # the bad one

# Grab the two most recent run IDs and compare.
reverie runs list --limit 2 --json | jq -r '.items[].id' | xargs reverie compare
```

The output shows the divergence point, the diff per dimension, and the
fault tree.

### Make your CI fail on regressions

A simple heuristic: a regression is a run with a new `loop` or
`bottleneck` anomaly that wasn't in the baseline.

```bash
reverie run python my_agent.py
RUN_ID=$(reverie runs list --limit 1 --json | jq -r '.items[0].id')

# Fail if the run has any loop anomalies.
reverie anomalies "$RUN_ID" --kind loop --json | jq -e '.items | length == 0'
```

### Export a run for archiving

```bash
reverie runs show <run-id> --json > runs/<run-id>.json
```

Re-import isn't supported (yet) — this is for archiving and external
analysis only.

---

## Using Reverie in your own project

Reverie is designed to plug into **any** project that runs AI agents. You
don't need to restructure your code, add decorators, or change your
architecture. Here are the four ways to integrate, from easiest to most
flexible.

---

### Option 1: Zero-code-change with `reverie run` (recommended)

If your agent uses the **OpenAI Agents SDK**, just prefix your normal
command with `reverie run`:

```bash
# Instead of:
python my_product/agent.py

# You do:
reverie run python my_product/agent.py

# Works with modules too:
reverie run python -m my_product.agent

# Works with console scripts:
reverie run my-agent-cli do-the-thing
```

**How it works:** Reverie injects a `sitecustomize.py` hook into the
subprocess's Python environment (the same mechanism OpenTelemetry uses).
This hook calls `reverie_openai.auto()` before your code runs, which
registers a tracing processor on the OpenAI Agents SDK. Your agent code
is never modified, never imported differently, never slowed down.

**Your project structure stays exactly the same:**

```
my-product/
├── my_product/
│   ├── agent.py          <-- unchanged, no Reverie imports
│   ├── tools.py
│   └── ...
├── pyproject.toml
└── ...
```

**Requirements:**
- The Reverie CLI must be installed (it is after `make install` in the
  Reverie repo, or `pip install reverie-cli` once published).
- The `reverie-adapter-openai` package must be importable in the same
  Python environment as your agent.
- The Reverie backend must be running (`reverie start` or `make dev`).

---

### Option 2: One-line import in your code

If you want instrumentation to always be active — for example in a
production service, a long-running daemon, or a Jupyter notebook — add
one line at the top of your entrypoint:

```python
# my_product/main.py

import reverie_openai
reverie_openai.auto()   # <-- one line, that's it

# ... rest of your agent code, completely unchanged
from agents import Agent, Runner

agent = Agent(name="my-bot", instructions="Summarize documents")
result = Runner.run_sync(agent, "Summarize the Q4 report")
```

**Properties of `auto()`:**
- **Idempotent** — safe to call multiple times (only installs once).
- **Non-blocking** — events go to a background thread; your agent never
  waits on Reverie.
- **Graceful degradation** — if the backend is unreachable, events are
  silently dropped. Your agent runs unchanged.
- **Configurable via env vars** — set `REVERIE_BACKEND_URL`,
  `REVERIE_AGENT_ID`, or `REVERIE_DISABLED` to control behavior without
  touching code.

---

### Option 3: Add Reverie as a dependency in your project

If you want your project to always ship with Reverie instrumentation
available:

```toml
# my-product/pyproject.toml

[project]
dependencies = [
    "openai-agents>=0.17",
    "reverie-adapter-openai",    # <-- add this
    # ... your other deps
]
```

Then either use `reverie run` (Option 1) or call `reverie_openai.auto()`
in code (Option 2). The adapter is ~400 lines and adds no heavy
dependencies beyond `httpx`.

---

### Option 4: Direct HTTP API (any framework, any language)

If you're using **LangGraph, CrewAI, AutoGen, a custom framework, or
even a non-Python agent**, you can emit events directly to the Reverie
backend's HTTP API. This works from any language that can make HTTP
requests.

**Single event:**

```python
import httpx

event = {
    "id": "evt-001",
    "runId": "run-abc-123",
    "parentId": None,
    "type": "goal.created",
    "agentId": "my-agent",
    "timestamp": "2026-05-25T10:00:00Z",
    "duration": 0,
    "payload": {
        "description": "Summarize the quarterly report"
    },
    "meta": {}
}

resp = httpx.post("http://127.0.0.1:8000/events", json=event)
# 201 Created on success, 422 on validation failure
```

**Batch (up to 50 events at once):**

```python
events = [event1, event2, event3, ...]
resp = httpx.post("http://127.0.0.1:8000/events/batch", json={"events": events})
```

**From JavaScript/TypeScript:**

```typescript
const event = {
  id: "evt-001",
  runId: "run-abc-123",
  parentId: null,
  type: "tool.called",
  agentId: "my-agent",
  timestamp: new Date().toISOString(),
  duration: 1200,
  payload: { tool: "web_search", input: { query: "latest news" } },
  meta: {}
};

await fetch("http://127.0.0.1:8000/events", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(event),
});
```

**From any language with curl:**

```bash
curl -X POST http://127.0.0.1:8000/events \
  -H "Content-Type: application/json" \
  -d '{"id":"evt-001","runId":"run-abc","parentId":null,"type":"goal.created","agentId":"my-agent","timestamp":"2026-05-25T10:00:00Z","duration":0,"payload":{"description":"Do the thing"},"meta":{}}'
```

**The 22 event types you can emit:**

| Type | When to emit it |
|---|---|
| `goal.created` | Agent sets a new objective |
| `goal.updated` | Goal description or priority changes |
| `goal.completed` | Goal achieved successfully |
| `goal.failed` | Goal abandoned or impossible |
| `tool.called` | Agent invokes an external tool |
| `tool.returned` | Tool returns a result |
| `memory.retrieved` | Agent looks something up from memory |
| `memory.stored` | Agent saves something to memory |
| `retry.triggered` | A failed operation is being retried |
| `validation.passed` | A check succeeded |
| `validation.failed` | A check failed |
| `reflection.generated` | Agent reflects on its own progress |
| `subagent.spawned` | Agent delegates to a helper agent |
| `subagent.completed` | Helper agent finished its work |
| `planning.started` | Agent begins planning a strategy |
| `planning.completed` | Plan is finalized |
| `context.overflow` | Context window hit its limit |
| `context.compressed` | Context was summarized to save space |
| `decision.made` | Agent chose between alternatives |
| `error.occurred` | An unexpected error happened |
| `guardrail.triggered` | A safety guardrail activated |
| `custom` | Anything else — use `payload` for details |

The full schema with all field definitions is in [`SRS.md`](./SRS.md).
Both endpoints validate every event against the schema — malformed
events get a `422` with a clear error message, never silently accepted.

---

### Typical workflow in a real product

```bash
# Terminal 1 — Start Reverie (once, leave it running in the background)
cd /path/to/reverie
reverie start

# Terminal 2 — Run your product's agent (from your project directory)
cd /path/to/my-product
reverie run python -m my_product.agent

# Browser — Watch it live
# http://localhost:3000 shows the run appearing in real time.
# After the run finishes: replay, compare, debug.
```

**Important:** The Reverie backend stores everything locally in
`data/reverie.db` (SQLite). Nothing leaves your machine unless you
explicitly request an AI summary (which calls the Claude API).

---

### What if my framework isn't supported yet?

| Framework | Status |
|---|---|
| **OpenAI Agents SDK** | Fully supported (auto-inject via `reverie run`) |
| **LangGraph** | On the roadmap | instructions 
| **CrewAI** | On the roadmap |
| **AutoGen** | On the roadmap |
| **MCP** | On the roadmap |
| **Custom / other** | Use the HTTP API directly (Option 4 above) |

The schema is **frozen at v1.0** — no removals, no renames, no type
changes. Only additive changes. Build against it with confidence; it
won't break under you.

---

## Configuration reference

Most things have sensible defaults. The knobs that matter most:

| Variable | Default | Used by | What it does |
|---|---|---|---|
| `REVERIE_BACKEND_URL` | `http://127.0.0.1:8000` | adapter, CLI, web | Where the backend lives. |
| `REVERIE_AGENT_ID` | `openai-agent` | adapter | Label attached to every event in the run. |
| `REVERIE_DISABLED` | unset | adapter | When truthy, the adapter no-ops — no events emitted. |
| `REVERIE_DB_PATH` | `data/reverie.db` | backend | Path to the SQLite event log. |
| `REVERIE_PORT` | `8000` | backend | Backend port. |
| `REVERIE_ENV` | `development` | backend | `production` disables auto-reload. |
| `ANTHROPIC_API_KEY` | unset | AI summaries | Enables Claude-powered summarization. |
| `REVERIE_AI_DISABLED` | unset | AI summaries | Force AI summaries off even with a key set. |
| `REVERIE_AI_MODEL` | `claude-3-5-sonnet-latest` | AI summaries | Model used by the summarizer. |
| `NEXT_PUBLIC_BACKEND_URL` | same as backend | web app | Backend URL for the browser-side fetches. |
| `PORT` | `3000` | web app | Web app port. |

Everything is plain env vars — drop them in a `.env` file at the repo
root, your shell rc, or pass them inline:

```bash
ANTHROPIC_API_KEY=sk-ant-... reverie summary <run-id>
```

---

## Troubleshooting

### `reverie: command not found`

Activate the venv:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\Activate.ps1
```

Or invoke the venv binary directly:

```bash
.venv/bin/reverie --help
.venv\Scripts\reverie.exe --help     # Windows
```

### `reverie start` says "backend did not become healthy"

- Check whether port `8000` is already in use:
  `curl http://127.0.0.1:8000/health` should return `{"status":"ok"}`.
- Inspect the backend logs in the same terminal — uvicorn prints
  startup errors there.
- Pass `--backend-port 9001` to use a different port.
- On Windows, your firewall may block localhost binds the first time.
  Allow the prompt that pops up.

### `pnpm: command not found` during `reverie start`

Install pnpm globally:

```bash
npm install -g pnpm@10
```

Or pass `--no-web` and start the web app yourself.

### Web app shows "Failed to connect to backend"

- Confirm the backend is running: `reverie status`.
- Confirm the web app is pointing at the right URL: check
  `NEXT_PUBLIC_BACKEND_URL` in your env.
- If you started the backend on a non-default port, set
  `NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:9001` and restart the web app.

### "AI summary not available"

You don't have `ANTHROPIC_API_KEY` set, or `REVERIE_AI_DISABLED=1` is
forcing it off. Set the key in your shell or a `.env` file and restart
`reverie start`.

### My agent runs but no events appear

- Confirm you're using `reverie run`, not running the agent directly.
- Confirm the backend was running when the agent started — events emitted
  before the backend exists are queued in-memory and dropped when the
  agent exits.
- Confirm `REVERIE_DISABLED` is not set in your environment.

### The 3D world is laggy or runs hot

- Drop the device pixel ratio: open browser devtools and set
  `window.devicePixelRatio = 1`.
- Switch to a higher zoom level (L2 or L3) — fewer orbs onscreen.
- Disable bloom temporarily: edit `apps/web/src/components/scene/scene.tsx`
  and comment out the `<Bloom>` element.

### Tests are failing on `main`

The schema has tight cross-language guarantees. Run
`make fixtures && make test`. If only the TS tests fail, regenerate
fixtures from the Python side and re-run.

---

## FAQ

**Q: Does Reverie modify my agent's behavior?**
No. The adapter listens to the OpenAI Agents SDK's tracing system; your
agent's code path doesn't change. If the backend is unreachable, events
are dropped and your agent continues without interruption.

**Q: Does this re-execute my agent during replay?**
No. Replay plays back the recorded event stream. LLM calls are
nondeterministic — re-execution would produce different outputs every
time. Reverie is closer to a DVR than a debugger that steps through code.

**Q: Where is my data stored?**
Locally, in `data/reverie.db` (SQLite, WAL mode). Nothing leaves your
machine except optional Claude API calls when you ask for a summary.

**Q: Can I use this with closed-source agents I don't control the code of?**
Yes, as long as they use the OpenAI Agents SDK or a framework Reverie
has an adapter for. The instrumentation hooks at the SDK level, not at
your code.

**Q: Will it work with `<my favorite framework>`?**
Today: OpenAI Agents SDK only. Soon: LangGraph, CrewAI, AutoGen, MCP.
Or emit events yourself against the documented HTTP API.

**Q: How much overhead does the instrumentation add?**
Per-event ingest p50 is well under 5ms. The adapter writes to a
background queue so your agent never blocks on Reverie. In practice the
overhead is invisible.

**Q: Can multiple people watch the same run live?**
Yes — every connected web client subscribes to the run via WebSocket
and receives event updates as they're ingested.

**Q: Can I delete a run?**
Right now: by deleting it from the SQLite database directly
(`sqlite3 data/reverie.db "DELETE FROM runs WHERE id = '...';"`).
A `reverie runs delete` command is on the roadmap.

**Q: Does it support traces from multiple machines?**
The current backend assumes a single host. Multi-host federation isn't
in scope for v1.0, but the schema is designed to support it.

**Q: Is the schema really frozen?**
Yes. v1.0 of the cognitive event schema is fixed — no removals, no
renames, no type changes. New event types and new fields can be added,
but existing shapes are forever. This is intentional and important: the
schema is the platform's foundation for ecosystem growth.

---

## What's in the box

| Layer | What it does |
|---|---|
| **Schema** | 22 cognitive event types, frozen v1.0. TypeScript (Zod) + Python (Pydantic v2). Byte-identical wire format guaranteed by an interop test. |
| **OpenAI Agents SDK adapter** | Auto-injects via `reverie run` using a `sitecustomize.py` hook (the same mechanism `opentelemetry-instrument` uses). Zero code changes to your agent. |
| **FastAPI + SQLite backend** | Append-only event log in WAL mode, atomic batch ingest, WebSocket fan-out, < 5 ms p50 ingest. |
| **Snapshot engine** | Reconstructs the full agent state at any point in any run via lazy checkpointing every 50 events. |
| **Graph intelligence** | Builds the cognitive DAG, assigns L1–L4 zoom levels, runs all six SRS-defined anomaly heuristics (loop, hotspot, bottleneck, poison, explosion, abandon). |
| **Salience scorer** | Per-node 0.0–1.0 importance score; nodes < 0.10 hidden by default. |
| **AI summary service** | Optional Claude-backed natural-language explanations. DB-cached so the same region never gets summarized twice. |
| **Comparative debugger** | Needleman-Wunsch alignment over event semantics, structured diff across all seven SRS dimensions, fault tree, AI narrative. |
| **CLI** | 12 subcommands. Most ship `--json` for scripting. |
| **3D renderer** | Next.js 15 + React Three Fiber 9. Custom Fresnel-rim shaders, ACES filmic tone mapping, selective bloom on emissive surfaces, damped orbit camera, drag-to-move orbs, glassmorphic HUD. |

## Project layout

```
reverie/
├── packages/
│   ├── schema/           — TypeScript types + Zod (canonical wire format)
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
├── SECURITY.md           — vulnerability disclosure
└── LICENSE               — MIT
```

## Testing

The project ships **400+ tests** covering schema, adapter, backend,
snapshot engine, graph intelligence, anomaly detectors, salience
scorer, AI client, comparative debugger, and the CLI.

```bash
make test          # everything (Python + TypeScript)
make test-py       # Python only
make test-js       # TypeScript schema tests only
make typecheck     # TS type-check only
```

Cross-language interop is enforced by a fixture-based test: a Python
script emits a JSON file, and the TypeScript Zod schema validates it.
Drift between the two languages would fail this test immediately.

## Contributing

Contributions welcome. Read [`CONTRIBUTING.md`](./CONTRIBUTING.md) for
the development workflow, code style, and the schema-stability rules.

The schema is **frozen at v1.0**. Any new event types or fields are
additive only; breaking changes require a coordinated major-version
bump in both the Python and TypeScript implementations.

Found a security issue? See [`SECURITY.md`](./SECURITY.md) for
responsible-disclosure instructions.


## License

MIT — see [`LICENSE`](./LICENSE).

---

<sub>**Reverie** — Observe. Replay. Understand.</sub>
