---
name: Bug report
about: Report something that's broken
title: "[bug] "
labels: bug
---

## Summary

A one-line description of the bug.

## Expected

What you thought would happen.

## Actual

What actually happened. Paste error messages, stack traces, or screenshots
inside fenced code blocks.

## Reproduction

The minimal way to make the bug appear. Ideally a self-contained example
under `examples/...`. If that's overkill, the exact CLI command sequence
is fine.

```bash
# example
reverie run python my_agent.py
reverie replay <id> --jump-failure
```

## Environment

- Reverie version / commit:
- Python version:
- Node version:
- OS:
- Backend running on (default `localhost:8000`?):

## Anything else

Logs, screenshots, hunches about the cause, etc.
