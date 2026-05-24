"""Annotation routes — user feedback on nodes + agent guidance.

Endpoints
---------

  POST   /api/v1/runs/{run_id}/annotations
            Create one or many annotations on a run. Body may be a single
            ``AnnotationCreate`` or a ``{ "items": [...] }`` batch.

  GET    /api/v1/runs/{run_id}/annotations
            List all annotations attached to a run.

  DELETE /api/v1/runs/{run_id}/annotations
            Bulk-delete every annotation on a run.

  DELETE /api/v1/annotations/{annotation_id}
            Delete one annotation.

  GET    /api/v1/agents/{agent_id}/guidance
            Materialise the prompt-prefix the next run will see for this
            agent. Query params: ``kinds`` (csv), ``tag``, ``scope``.

  DELETE /api/v1/agents/{agent_id}/guidance
            Wipe all annotations for this agent (use with care).

The dependency wiring follows the same pattern as the rest of the app:
the lifespan installs an ``AnnotationStore`` singleton, request handlers
resolve it via :func:`get_annotation_store`.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from reverie_api.annotations import (
    Annotation,
    AnnotationBatchCreate,
    AnnotationCreate,
    AnnotationDeleteAck,
    AnnotationKind,
    AnnotationListResponse,
    AnnotationScope,
    AnnotationStore,
    Guidance,
    get_annotation_store,
    render_guidance,
)

router = APIRouter(prefix="/api/v1", tags=["annotations"])


# Both shapes are accepted on the create endpoint — single object OR
# `{items: [...]}` envelope. FastAPI doesn't union body models cleanly via
# response_model, so we accept a dict and dispatch manually.
@router.post(
    "/runs/{run_id}/annotations",
    status_code=201,
    summary="Create one or more annotations on a run",
)
async def create_annotations(
    run_id: str,
    body: dict = Body(...),
    store: AnnotationStore = Depends(get_annotation_store),
) -> JSONResponse:
    """Create annotations.

    Accepts EITHER a single annotation object OR a batch envelope of the
    shape ``{ "items": [...] }``. The latter is preferred for bulk
    operations from the 3D UI.
    """

    if isinstance(body, dict) and "items" in body:
        try:
            batch = AnnotationBatchCreate.model_validate(body)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        items = await store.create_many(run_id, batch.items)
        payload = AnnotationListResponse(items=items)
        return JSONResponse(
            content=jsonable_encoder(payload, by_alias=True),
            status_code=201,
        )

    try:
        single = AnnotationCreate.model_validate(body)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    ann = await store.create_one(run_id, single)
    return JSONResponse(
        content=jsonable_encoder(ann, by_alias=True),
        status_code=201,
    )


@router.get(
    "/runs/{run_id}/annotations",
    response_model=AnnotationListResponse,
    response_model_by_alias=True,
    summary="List all annotations on a run",
)
async def list_annotations_for_run(
    run_id: str,
    store: AnnotationStore = Depends(get_annotation_store),
) -> AnnotationListResponse:
    items = await store.list_for_run(run_id)
    return AnnotationListResponse(items=items)


@router.delete(
    "/runs/{run_id}/annotations",
    response_model=AnnotationDeleteAck,
    response_model_by_alias=True,
    summary="Delete every annotation on a run",
)
async def delete_annotations_for_run(
    run_id: str,
    store: AnnotationStore = Depends(get_annotation_store),
) -> AnnotationDeleteAck:
    count = await store.delete_for_run(run_id)
    return AnnotationDeleteAck(deleted=count)


@router.delete(
    "/annotations/{annotation_id}",
    response_model=AnnotationDeleteAck,
    response_model_by_alias=True,
    summary="Delete one annotation",
)
async def delete_annotation(
    annotation_id: str,
    store: AnnotationStore = Depends(get_annotation_store),
) -> AnnotationDeleteAck:
    removed = await store.delete_one(annotation_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"annotation not found: {annotation_id}")
    return AnnotationDeleteAck(deleted=1)


# ---------------------------------------------------------------------------
# Guidance
# ---------------------------------------------------------------------------


@router.get(
    "/agents/{agent_id}/guidance",
    response_model=Guidance,
    response_model_by_alias=True,
    summary="Materialise the prompt-prefix the next run will see",
)
async def get_guidance(
    agent_id: str,
    store: AnnotationStore = Depends(get_annotation_store),
    kinds: str | None = Query(
        default=None,
        description="Comma-separated annotation kinds to include (default: avoid,focus,done).",
    ),
    scope: AnnotationScope | None = Query(
        default=None, description="Filter by annotation scope."
    ),
    tag: str | None = Query(
        default=None,
        description="Only annotations with this tag (or no tag) are included.",
    ),
) -> Guidance:
    parsed_kinds: list[AnnotationKind] | None
    if kinds is None:
        # Default: prompt-prefix-relevant kinds (drop pure notes).
        parsed_kinds = ["avoid", "focus", "done"]
    elif kinds.strip() == "":
        parsed_kinds = None  # "no filter" if explicitly empty
    else:
        raw = [k.strip() for k in kinds.split(",") if k.strip()]
        valid = {"avoid", "focus", "done", "note"}
        invalid = [k for k in raw if k not in valid]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"invalid annotation kinds: {invalid}",
            )
        parsed_kinds = [k for k in raw]  # type: ignore[misc]

    annotations = await store.list_for_agent(
        agent_id,
        kinds=parsed_kinds,
        scope=scope,
        tag=tag,
    )
    event_types = await store.list_event_types([a.node_id for a in annotations])
    return render_guidance(
        agent_id=agent_id, annotations=annotations, event_types=event_types
    )


@router.delete(
    "/agents/{agent_id}/guidance",
    response_model=AnnotationDeleteAck,
    response_model_by_alias=True,
    summary="Wipe all annotations for an agent",
)
async def clear_guidance(
    agent_id: str,
    store: AnnotationStore = Depends(get_annotation_store),
) -> AnnotationDeleteAck:
    count = await store.delete_for_agent(agent_id)
    return AnnotationDeleteAck(deleted=count)
