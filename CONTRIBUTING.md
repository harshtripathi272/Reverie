# Contributing to Reverie

Thank you for your interest in helping build cognitive observability for AI
agents. This guide gets you from zero to a passing PR in the shortest path
possible.

---

## Development setup

### Prerequisites

- **Python 3.11+** with [`uv`](https://docs.astral.sh/uv/) installed.
- **Node.js 20+** with [`pnpm 9+`](https://pnpm.io) installed.
- **Git** (you're already here).
- **Make** is convenient but not required — every target is reproducible
  with raw commands.

### One-time install

```bash
git clone https://github.com/<your-org>/reverie.git
cd reverie
make install
```

This creates `.venv/`, installs the four Python packages (`schema-py`,
`adapter-openai`, `api`, `cli`) in editable mode, and runs `pnpm install` for
the JS workspace.

### Verify the install

```bash
make test    # 400+ tests should pass; ~45 s on a modern laptop
```

If `make test` is green, you're set up correctly.

---

## Repository layout

```
reverie/
├── packages/
│   ├── schema/           TypeScript types + Zod (the canonical wire format)
│   ├── schema-py/        Pydantic v2 (parallel source of truth for Python)
│   └── adapter-openai/   OpenAI Agents SDK adapter
├── apps/
│   ├── api/              FastAPI backend + SQLite event log
│   └── web/              Next.js 15 + R3F 3D explorer
├── cli/                  `reverie` CLI (Click-based)
├── examples/             reference agents
└── scripts/              smoke tests
```

A change in any one package usually triggers test runs in others — the
tests are fast enough that running the full suite is the recommended
default.

---

## How we work

### Branching

- `main` is always green and shippable.
- Feature branches are named `feature/<short-desc>` (e.g. `feature/langgraph-adapter`).
- Bug fixes are named `fix/<short-desc>`.
- Open a draft PR early. Push commits as you work. Mark it ready when tests pass.

### Commits

Conventional Commits keep the history scannable:

```
feat(adapter-openai): map TaskSpanData to planner.updated
fix(api): handle empty event batch with 400 not 422
docs(readme): add LangGraph adapter to roadmap
test(graph): cover the orphan parent_id case in critical path
```

### Pull requests

Every PR must:

- **Include tests.** New behavior needs tests; bug fixes need a regression
  test that fails before the fix and passes after.
- **Keep `make test` green.** CI will catch you, but local is faster.
- **Update docs.** If you change a CLI flag, an env var, or a public API,
  update `README.md` and any relevant doc strings.
- **Be small enough to review.** Aim for < 500 lines changed. Larger
  changes should be split or warrant an upfront design discussion in an
  issue.

---

## The schema is frozen

The `CognitiveEvent` schema is the project's moat. It is **frozen at v1.0**.

You may **add** new event types, payload variants, or optional fields. You
may **never** remove fields, rename fields, change a field's type, or alter
the wire format.

Any additive change must be applied to **both** the TypeScript Zod schema
(`packages/schema/`) and the Python Pydantic models (`packages/schema-py/`)
in the same PR. The cross-language interop test will fail if you forget.

If you genuinely need a breaking change, that's a v2 conversation — open an
issue first.

---

## Code style

### Python

- **Type-annotate everything.** No `Any` unless you can defend it.
- **Pydantic v2 throughout.** No raw dicts crossing module boundaries.
- **`ruff` formats and lints.** `ruff check` should pass.
- **Tests live next to the code they test.** `apps/api/tests/test_*.py`
  for backend tests, `packages/.../tests/test_*.py` for package tests.

### TypeScript

- **`strict: true`** in `tsconfig.json`. No suppressions without a comment.
- **Inferred types over explicit when possible** — `z.infer<typeof Schema>`
  is preferred to redeclaring shapes.
- **Camel-case wire format** is mandatory for any data that crosses an
  HTTP boundary.

### Shaders / GLSL

The 3D renderer ships a couple of small custom shaders (the orb halo, etc.).
Keep them inline in the component file with `/* glsl */` template literals
so the editor can highlight them. Add a comment block above each shader
explaining the intent.

---

## Testing

### Local

```bash
make test           # everything
make test-py        # Python only
make test-js        # TypeScript schema tests only
pnpm -C apps/web typecheck   # frontend strict TS check
```

### What to test

- **Pure functions** — exhaustive happy-path + every rejection class.
- **API endpoints** — happy path + 4xx + 5xx + edge cases (empty batch,
  duplicate ids, oversized payload).
- **Adapter mapping** — every `*SpanData` variant, both start and end.
- **CLI commands** — exit codes, JSON output, error paths.

### What we don't test

- Three.js rendering output. We typecheck the components and trust
  inspection for visual regressions.
- The Anthropic API itself. Use `pytest-httpx` to mock it.

---

## Adding a new adapter

If you want to add a runtime (LangGraph, CrewAI, AutoGen, MCP, etc.):

1. Create `packages/adapter-<name>/` with a `pyproject.toml` mirroring the
   OpenAI adapter's structure.
2. Implement a `<name>_runtime.auto()` function that registers the adapter's
   trace processor.
3. Map every meaningful runtime event into a `CognitiveEvent`. If a runtime
   concept doesn't fit any existing event type, wrap it in `GenericPayload`
   for forward-compat — don't invent new event types in a side-package.
4. Write tests using the same pattern as `adapter-openai/tests/test_mapper.py`.
5. Add an end-to-end integration test that runs a fake span lifecycle
   through the adapter and asserts the right events arrive.
6. Document it in the README and the SRS roadmap.

---

## Reporting bugs

Open an issue with:

- **What you expected.**
- **What actually happened.**
- **A minimal reproduction.** Ideally an `examples/...` script that exhibits
  the bug.
- **Your environment** — Python version, Node version, OS.

Security issues should be reported privately. See `SECURITY.md` if it exists,
otherwise email the maintainers.

---

## Code of conduct

By participating, you agree to abide by [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md).

---

Thanks for contributing. Reverie gets better the more agents people instrument
it on.
