# reverie-api

The Reverie ingestion backend. FastAPI on top of SQLite, with append-only
event storage and a WebSocket fan-out for live subscribers.

## Endpoints (Phase 0)

| Method | Path | Purpose |
|---|---|---|
| `GET`    | `/health`                          | Liveness check |
| `POST`   | `/api/v1/runs`                     | Create a run |
| `GET`    | `/api/v1/runs`                     | List runs (paginated) |
| `GET`    | `/api/v1/runs/{run_id}`            | Get one run |
| `PATCH`  | `/api/v1/runs/{run_id}`            | Update status / completedAt / goal |
| `DELETE` | `/api/v1/runs/{run_id}`            | Delete run + cascade events (refused if pinned) |
| `PATCH`  | `/api/v1/runs/{run_id}/pin`        | Pin / unpin a run |
| `GET`    | `/api/v1/runs/{run_id}/events`     | Get all events for a run, in timestamp order |
| `POST`   | `/api/v1/events`                   | Ingest one event |
| `POST`   | `/api/v1/events/batch`             | Ingest up to 1000 events atomically |
| `WS`     | `/stream?runId=<id>`               | Live event stream for one run |

## Configuration

Environment variables (all optional, prefix `REVERIE_`):

| Var | Default | Description |
|---|---|---|
| `REVERIE_DB_PATH`     | `data/reverie.db`              | SQLite file path |
| `REVERIE_HOST`        | `127.0.0.1`                    | Bind host |
| `REVERIE_PORT`        | `8000`                         | Bind port |
| `REVERIE_CORS_ORIGINS`| `http://localhost:3000`        | Comma-separated allowed origins |
| `REVERIE_ENV`         | `development`                  | Environment label |

## Run

```
uv pip install --python ../../.venv/Scripts/python.exe -e ".[dev]"
python -m reverie_api
```

Then visit `http://localhost:8000/docs` for the OpenAPI UI.

## Test

```
pytest
```
