# Security policy

## Supported versions

Reverie is pre-1.0. Security fixes land on `main`. We don't backport to
older tags. Pin to a recent commit if you're running this in production.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Instead, email the maintainers directly. Include:

- The vulnerable component (schema, adapter, backend, CLI, web app).
- A description of the issue and its impact.
- Steps to reproduce.
- Any proof-of-concept code or fixture.

We'll acknowledge receipt within three business days, work with you on a
fix, and credit you in the release notes when the patch ships (unless you
prefer to remain anonymous).

## What's in scope

- Authentication or authorisation bypass on the API.
- Code injection through events (e.g. a malicious payload that escapes the
  schema validator).
- Cross-site scripting in the 3D explorer.
- Denial of service against ingestion or replay.
- Secret leakage from the AI summary cache or the snapshot store.

## What's out of scope

- Anything that requires the attacker already to have local filesystem
  access (Reverie's threat model assumes the developer's machine is
  trusted).
- Issues in third-party dependencies that don't have a CVE — file those
  upstream first.
- The OpenAI Agents SDK itself — please report those to the SDK team.
