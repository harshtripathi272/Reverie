# @reverie/schema

The canonical TypeScript types and Zod validators for Reverie's `CognitiveEvent`
schema (v1.0). This is the wire format spoken between adapters, the API, and any
client consumer.

## Wire format

All field names are **camelCase**. The schema is locked at `schemaVersion: "1.0"` —
new event types or fields require a minor version bump and additive-only changes.

## Usage

```ts
import {
  CognitiveEvent,
  CognitiveEventSchema,
  parseCognitiveEvent,
} from "@reverie/schema";

const event: CognitiveEvent = parseCognitiveEvent(jsonFromNetwork);
```

`parseCognitiveEvent` throws a `ZodError` on invalid input. Use
`CognitiveEventSchema.safeParse(...)` if you want a result-style API.

## Build / test

```
pnpm install
pnpm build
pnpm test
```
