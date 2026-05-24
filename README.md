# Reverie

> Cognitive observability, replay, and comparative debugging for autonomous AI agents.
> Chrome DevTools for AI agents. OpenTelemetry for agent cognition.

**Status:** Phase 0 — Schema + Adapter (in progress)

## What this is

Reverie instruments AI agent runtimes (starting with the OpenAI Agents SDK), captures
every meaningful cognitive event (goals, tool calls, memory retrievals, retries,
sub-agent spawning, validations, reflections), normalizes them into a universal
schema, stores them in an append-only event log, and provides replay plus comparative
debugging.

The 3D glowing-orb visualization comes last (Phase 5). Infrastructure comes first.

See [`ABOUT.md`](./ABOUT.md) for the product vision and [`SRS.md`](./SRS.md) for the
full architecture and 21-week build plan.

## Repository layout

```
reverie/
├── packages/
│   ├── schema/          TypeScript types + Zod validators (npm package)
│   ├── schema-py/       Python Pydantic models (pip package)
│   └── adapter-openai/  OpenAI Agents SDK adapter (Python)
├── apps/
│   └── api/             FastAPI backend + SQLite event log
├── cli/                 `reverie` CLI entry point
├── examples/            Reference agents for testing
└── docker-compose.yml
```

## Build phases (gate-driven)

| Phase | Scope | Gate |
|---|---|---|
| **0** | Schema + Adapter + API + CLI | Real OpenAI agent run produces validated events in SQLite |
| 1 | Snapshot + observational replay | Replay a failed run in the terminal, identify failure event |
| 2 | Graph intelligence + semantic zoom | 500-event trace navigable without overwhelm |
| 3 | Salience + AI summaries | Critical path of complex run understood in < 2 minutes |
| 4 | Comparative debugger | Identifies divergence point between paired success/fail runs |
| 5 | 3D spatial renderer + launch | The README GIF stops the scroll |

## Development

Requirements: Python 3.12+, Node 20+, pnpm 9+, uv 0.5+.

```
make install     # install all packages in editable mode
make dev         # start the API backend
make test        # run all tests
```

See per-package READMEs for details.

## License

TBD
