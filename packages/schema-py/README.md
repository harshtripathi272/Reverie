# reverie-schema (Python)

Pydantic v2 models for the Reverie `CognitiveEvent` schema (v1.0). This is the
canonical Python definition used by:

- `reverie-adapter-openai` — for emitting events
- `reverie-api` — for validating events on ingress

The wire format is **camelCase JSON**, identical to the TypeScript schema in
`@reverie/schema`. Internally, Python code uses `snake_case` field names; the
Pydantic models translate via `alias_generator=to_camel`.

## Usage

```python
from reverie_schema import CognitiveEvent, GoalPayload

event = CognitiveEvent(
    type="goal.created",
    run_id="...",
    session_id="...",
    agent_id="my-agent",
    payload=GoalPayload(intent="...", priority="high", context=""),
)

# Wire serialization (camelCase, ready for HTTP / DB):
event.model_dump_json()

# Inbound validation (raises ValidationError on failure):
CognitiveEvent.model_validate_json(raw_json)
```

## Install (editable, dev)

```
uv pip install -e ".[dev]"
pytest
```
