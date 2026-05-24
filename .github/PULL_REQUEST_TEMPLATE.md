# Summary

<!-- One paragraph: what changes, and why. -->

## Type

<!-- Check all that apply. -->
- [ ] Bug fix
- [ ] New feature
- [ ] Refactor (no behavior change)
- [ ] Documentation
- [ ] Test-only
- [ ] Schema change (see checklist below)

## Schema-change checklist

If this PR touches the `CognitiveEvent` schema:

- [ ] Change is **additive only** (no removed fields, no renamed fields, no
      type changes).
- [ ] Updated **both** the TypeScript Zod schema (`packages/schema/`) and
      the Python Pydantic models (`packages/schema-py/`).
- [ ] Regenerated cross-language fixtures
      (`scripts/emit_fixtures.py`).
- [ ] Cross-language interop test still passes.

## Tests

- [ ] New behavior is covered by tests.
- [ ] Bug fixes include a regression test.
- [ ] `make test` passes locally.

## Documentation

- [ ] Public CLI flags / API endpoints / env vars are documented in
      `README.md`.
- [ ] If this changes the architecture meaningfully, `SRS.md` is updated.

## Breaking changes

<!-- Anything a user has to do differently after this PR? -->

## Related issues

<!-- Closes #123, refs #456 -->
