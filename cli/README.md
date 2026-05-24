# reverie-cli

The `reverie` command-line interface.

## Commands

```
reverie run <cmd...>          Run any command with Reverie auto-instrumentation.
reverie status                Ping the configured backend and show its health.
reverie runs list             List recent runs.
reverie runs show <run-id>    Show one run plus its event timeline.
reverie replay <run-id>       Stream a run's events to the terminal (Phase 1 preview).
```

## How `reverie run` works

`reverie run python my_agent.py` does three things:

1. Prepends a small bootstrap directory to `PYTHONPATH`. The directory contains
   a `sitecustomize.py` that Python imports automatically before any user code.
2. The bootstrap calls `reverie_openai.auto()`, which registers a tracing
   processor with the OpenAI Agents SDK. Your agent code is unchanged.
3. Spawns your command as a subprocess and waits for it to exit, then exits
   with the same status code.

This works for any Python entrypoint — `python script.py`, `python -m module`,
`python -c "..."` — and is the same mechanism `opentelemetry-instrument` uses.

### Limitations of the bootstrap

If your project ships its own `sitecustomize.py`, our hook tries to import yours
afterward but cannot guarantee perfect compatibility. Set
`REVERIE_NO_SITECUSTOMIZE_CHAIN=1` to disable chaining if it causes issues.

For non-Python commands (`reverie run node app.js`), the CLI still runs the
command but no instrumentation is injected.

## Configuration

| Var | Default | Description |
|---|---|---|
| `REVERIE_BACKEND_URL` | `http://127.0.0.1:8000` | Backend base URL |
| `REVERIE_NO_SITECUSTOMIZE_CHAIN` | unset | Skip chaining to user's sitecustomize |

## Install

```
uv pip install -e ".[dev]"
reverie status
```
