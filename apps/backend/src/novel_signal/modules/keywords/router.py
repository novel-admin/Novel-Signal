import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from novel_signal.db import get_db
from novel_signal.modules.keywords.csv_service import (
    CsvEntity,
    CsvValidationFailure,
    KeywordCsvService,
)
from novel_signal.modules.keywords.errors import (
    KeywordConflictError,
    KeywordNotFoundError,
    KeywordValidationError,
)
from novel_signal.modules.keywords.models import (
    IntentCluster,
    KeywordSourceType,
    KeywordTrackingStatus,
)
from novel_signal.modules.keywords.schemas import (
    BulkKeywordUpdate,
    BulkResult,
    CsvImportRequest,
    CsvImportResult,
    CsvValidationResult,
    KeywordCreate,
    KeywordList,
    KeywordRead,
    KeywordUpdate,
    TrackingTargetCreate,
    TrackingTargetList,
    TrackingTargetRead,
    TrackingTargetUpdate,
)
from novel_signal.modules.keywords.service import KeywordService
from novel_signal.modules.universe.models import Marketplace, TrackingTier

router = APIRouter(prefix="/keywords", tags=["S2 Keywords"])
SessionDep = Annotated[Session, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]


def get_service(session: SessionDep) -> KeywordService:
    return KeywordService(session)


def get_csv_service(session: SessionDep) -> KeywordCsvService:
    return KeywordCsvService(session)


ServiceDep = Annotated[KeywordService, Depends(get_service)]
CsvServiceDep = Annotated[KeywordCsvService, Depends(get_csv_service)]


def execute[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except KeywordNotFoundError as error:
        raise HTTPException(404, detail={"code": error.code, "message": error.message}) from error
    except KeywordConflictError as error:
        raise HTTPException(409, detail={"code": error.code, "message": error.message}) from error
    except KeywordValidationError as error:
        raise HTTPException(422, detail={"code": error.code, "message": error.message}) from error


@router.get("/meta")
def module_meta() -> dict[str, str]:
    return {"module": "S2 Keywords", "status": "implemented"}


@router.get("", response_model=KeywordList)
def list_keywords(
    service: ServiceDep,
    include_archived: bool = False,
    limit: Limit = 50,
    offset: Offset = 0,
    search: str | None = None,
    source: KeywordSourceType | None = None,
    tier: TrackingTier | None = None,
    tracking_status: KeywordTrackingStatus | None = None,
    intent_cluster: IntentCluster | None = None,
    marketplace: Marketplace | None = None,
    category: str | None = None,
    priority_only: bool = False,
) -> KeywordList:
    items, total = service.list_keywords(
        include_archived=include_archived,
        limit=limit,
        offset=offset,
        search=search,
        source=source,
        tier=tier,
        tracking_status=tracking_status,
        intent_cluster=intent_cluster,
        marketplace=marketplace,
        category=category,
        priority_only=priority_only,
    )
    return KeywordList(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=KeywordRead, status_code=201)
def create_keyword(payload: KeywordCreate, service: ServiceDep) -> KeywordRead:
    return KeywordRead.model_validate(execute(lambda: service.create_keyword(payload)))


@router.get("/tracking-targets", response_model=TrackingTargetList)
def list_targets(
    service: ServiceDep,
    include_archived: bool = False,
    limit: Limit = 50,
    offset: Offset = 0,
    keyword_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    competitor_product_id: uuid.UUID | None = None,
    enabled: bool | None = None,
    cadence_minutes: int | None = Query(default=None, gt=0),
) -> TrackingTargetList:
    items, total = service.list_targets(
        include_archived=include_archived,
        limit=limit,
        offset=offset,
        keyword_id=keyword_id,
        product_id=product_id,
        competitor_product_id=competitor_product_id,
        enabled=enabled,
        cadence_minutes=cadence_minutes,
    )
    return TrackingTargetList(items=items, total=total, limit=limit, offset=offset)


@router.get("/{entity_id}", response_model=KeywordRead)
def get_keyword(entity_id: uuid.UUID, service: ServiceDep) -> KeywordRead:
    return KeywordRead.model_validate(execute(lambda: service.get_keyword(entity_id)))


@router.patch("/{entity_id}", response_model=KeywordRead)
def update_keyword(
    entity_id: uuid.UUID, payload: KeywordUpdate, service: ServiceDep
) -> KeywordRead:
    return KeywordRead.model_validate(execute(lambda: service.update_keyword(entity_id, payload)))


@router.post("/{entity_id}/archive", response_model=KeywordRead)
def archive_keyword(entity_id: uuid.UUID, service: ServiceDep) -> KeywordRead:
    return KeywordRead.model_validate(execute(lambda: service.archive_keyword(entity_id)))


@router.post("/{entity_id}/restore", response_model=KeywordRead)
def restore_keyword(entity_id: uuid.UUID, service: ServiceDep) -> KeywordRead:
    return KeywordRead.model_validate(execute(lambda: service.restore_keyword(entity_id)))


@router.post("/bulk/update", response_model=BulkResult)
def bulk_update(payload: BulkKeywordUpdate, service: ServiceDep) -> BulkResult:
    return BulkResult(updated=execute(lambda: service.bulk_update(payload)))


@router.post("/tracking-targets", response_model=TrackingTargetRead, status_code=201)
def create_target(payload: TrackingTargetCreate, service: ServiceDep) -> TrackingTargetRead:
    return TrackingTargetRead.model_validate(execute(lambda: service.create_target(payload)))


@router.get("/tracking-targets/{entity_id}", response_model=TrackingTargetRead)
def get_target(entity_id: uuid.UUID, service: ServiceDep) -> TrackingTargetRead:
    return TrackingTargetRead.model_validate(execute(lambda: service.get_target(entity_id)))


@router.patch("/tracking-targets/{entity_id}", response_model=TrackingTargetRead)
def update_target(
    entity_id: uuid.UUID, payload: TrackingTargetUpdate, service: ServiceDep
) -> TrackingTargetRead:
    return TrackingTargetRead.model_validate(
        execute(lambda: service.update_target(entity_id, payload))
    )


@router.post("/tracking-targets/{entity_id}/archive", response_model=TrackingTargetRead)
def archive_target(entity_id: uuid.UUID, service: ServiceDep) -> TrackingTargetRead:
    return TrackingTargetRead.model_validate(execute(lambda: service.archive_target(entity_id)))


@router.post("/tracking-targets/{entity_id}/restore", response_model=TrackingTargetRead)
def restore_target(entity_id: uuid.UUID, service: ServiceDep) -> TrackingTargetRead:
    return TrackingTargetRead.model_validate(execute(lambda: service.restore_target(entity_id)))


def csv_response(content: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/csv/{entity}/template", response_class=Response)
def template(entity: CsvEntity, service: CsvServiceDep) -> Response:
    return csv_response(service.template(entity), f"{entity.value}-template.csv")


@router.post("/csv/{entity}/dry-run", response_model=CsvValidationResult)
def dry_run(
    entity: CsvEntity, payload: CsvImportRequest, service: CsvServiceDep
) -> CsvValidationResult:
    return service.validate(entity, payload.csv_text)[0]


@router.post("/csv/{entity}/import", response_model=CsvImportResult)
def import_csv(
    entity: CsvEntity, payload: CsvImportRequest, service: CsvServiceDep
) -> CsvImportResult:
    try:
        return service.import_rows(entity, payload.csv_text)
    except CsvValidationFailure as error:
        raise HTTPException(
            422,
            detail={
                "code": "csv_validation_failed",
                "message": "CSV validation failed; no rows imported",
                "result": error.result.model_dump(mode="json"),
            },
        ) from error


@router.get("/csv/{entity}/export", response_class=Response)
def export(entity: CsvEntity, service: CsvServiceDep, include_archived: bool = False) -> Response:
    return csv_response(service.export(entity, include_archived), f"{entity.value}.csv")
