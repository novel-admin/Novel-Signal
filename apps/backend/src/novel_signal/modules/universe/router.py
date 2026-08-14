import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from novel_signal.db import get_db
from novel_signal.modules.universe.csv_service import (
    CsvEntity,
    CsvValidationFailure,
    UniverseCsvService,
)
from novel_signal.modules.universe.errors import (
    UniverseConflictError,
    UniverseNotFoundError,
    UniverseValidationError,
)
from novel_signal.modules.universe.models import (
    BattleCardStatus,
    Marketplace,
    PositioningTier,
    TrackingTier,
)
from novel_signal.modules.universe.schemas import (
    BattleCardCreate,
    BattleCardItemCreate,
    BattleCardItemList,
    BattleCardItemRead,
    BattleCardItemUpdate,
    BattleCardList,
    BattleCardRead,
    BattleCardUpdate,
    CompetitorCreate,
    CompetitorList,
    CompetitorProductCreate,
    CompetitorProductList,
    CompetitorProductRead,
    CompetitorProductUpdate,
    CompetitorRead,
    CompetitorUpdate,
    CsvImportRequest,
    CsvImportResult,
    CsvValidationResult,
    ProductCreate,
    ProductList,
    ProductRead,
    ProductUpdate,
)
from novel_signal.modules.universe.service import UniverseService

router = APIRouter(prefix="/universe", tags=["S1 Universe"])
SessionDependency = Annotated[Session, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]
StatusFilter = Annotated[BattleCardStatus | None, Query(alias="status")]


def get_service(session: SessionDependency) -> UniverseService:
    return UniverseService(session)


ServiceDependency = Annotated[UniverseService, Depends(get_service)]


def get_csv_service(session: SessionDependency) -> UniverseCsvService:
    return UniverseCsvService(session)


CsvServiceDependency = Annotated[UniverseCsvService, Depends(get_csv_service)]


def execute[ResultT](operation: Callable[[], ResultT]) -> ResultT:
    try:
        return operation()
    except UniverseNotFoundError as error:
        raise HTTPException(
            status_code=404, detail={"code": error.code, "message": error.message}
        ) from error
    except UniverseConflictError as error:
        raise HTTPException(
            status_code=409, detail={"code": error.code, "message": error.message}
        ) from error
    except UniverseValidationError as error:
        raise HTTPException(
            status_code=422, detail={"code": error.code, "message": error.message}
        ) from error


@router.get("/meta")
def module_meta() -> dict[str, str]:
    return {"module": "S1 Universe", "status": "implemented"}


@router.get("/csv/{entity}/template", response_class=Response)
def download_csv_template(entity: CsvEntity, service: CsvServiceDependency) -> Response:
    return csv_response(service.template(entity), f"{entity}-template.csv")


@router.post("/csv/{entity}/dry-run", response_model=CsvValidationResult)
def dry_run_csv(
    entity: CsvEntity, payload: CsvImportRequest, service: CsvServiceDependency
) -> CsvValidationResult:
    result, _ = service.validate(entity, payload.csv_text)
    return result


@router.post("/csv/{entity}/import", response_model=CsvImportResult)
def import_csv(
    entity: CsvEntity, payload: CsvImportRequest, service: CsvServiceDependency
) -> CsvImportResult:
    try:
        return execute(lambda: service.import_rows(entity, payload.csv_text))
    except CsvValidationFailure as error:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "csv_validation_failed",
                "message": "CSV validation failed; no rows were imported",
                "result": error.result.model_dump(mode="json"),
            },
        ) from error


@router.get("/csv/{entity}/export", response_class=Response)
def export_csv(
    entity: CsvEntity,
    service: CsvServiceDependency,
    include_archived: bool = False,
) -> Response:
    return csv_response(service.export(entity, include_archived=include_archived), f"{entity}.csv")


def csv_response(content: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/competitors", response_model=CompetitorList)
def list_competitors(
    service: ServiceDependency,
    include_archived: bool = False,
    limit: Limit = 50,
    offset: Offset = 0,
    search: str | None = None,
    positioning_tier: PositioningTier | None = None,
    category_presence: str | None = None,
) -> CompetitorList:
    items, total = service.list_competitors(
        include_archived=include_archived,
        limit=limit,
        offset=offset,
        search=search,
        positioning_tier=positioning_tier,
        category_presence=category_presence,
    )
    return CompetitorList(items=items, total=total, limit=limit, offset=offset)


@router.post("/competitors", response_model=CompetitorRead, status_code=201)
def create_competitor(payload: CompetitorCreate, service: ServiceDependency) -> CompetitorRead:
    return CompetitorRead.model_validate(execute(lambda: service.create_competitor(payload)))


@router.get("/competitors/{entity_id}", response_model=CompetitorRead)
def get_competitor(entity_id: uuid.UUID, service: ServiceDependency) -> CompetitorRead:
    return CompetitorRead.model_validate(execute(lambda: service.get_competitor(entity_id)))


@router.patch("/competitors/{entity_id}", response_model=CompetitorRead)
def update_competitor(
    entity_id: uuid.UUID, payload: CompetitorUpdate, service: ServiceDependency
) -> CompetitorRead:
    return CompetitorRead.model_validate(
        execute(lambda: service.update_competitor(entity_id, payload))
    )


@router.post("/competitors/{entity_id}/archive", response_model=CompetitorRead)
def archive_competitor(entity_id: uuid.UUID, service: ServiceDependency) -> CompetitorRead:
    return CompetitorRead.model_validate(execute(lambda: service.archive_competitor(entity_id)))


@router.post("/competitors/{entity_id}/restore", response_model=CompetitorRead)
def restore_competitor(entity_id: uuid.UUID, service: ServiceDependency) -> CompetitorRead:
    return CompetitorRead.model_validate(execute(lambda: service.restore_competitor(entity_id)))


@router.get("/products", response_model=ProductList)
def list_products(
    service: ServiceDependency,
    include_archived: bool = False,
    limit: Limit = 50,
    offset: Offset = 0,
    internal_sku: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    marketplace: Marketplace | None = None,
    tracking_tier: TrackingTier | None = None,
) -> ProductList:
    items, total = service.list_products(
        include_archived=include_archived,
        limit=limit,
        offset=offset,
        internal_sku=internal_sku,
        brand=brand,
        category=category,
        marketplace=marketplace,
        tracking_tier=tracking_tier,
    )
    return ProductList(items=items, total=total, limit=limit, offset=offset)


@router.post("/products", response_model=ProductRead, status_code=201)
def create_product(payload: ProductCreate, service: ServiceDependency) -> ProductRead:
    return ProductRead.model_validate(execute(lambda: service.create_product(payload)))


@router.get("/products/{entity_id}", response_model=ProductRead)
def get_product(entity_id: uuid.UUID, service: ServiceDependency) -> ProductRead:
    return ProductRead.model_validate(execute(lambda: service.get_product(entity_id)))


@router.patch("/products/{entity_id}", response_model=ProductRead)
def update_product(
    entity_id: uuid.UUID, payload: ProductUpdate, service: ServiceDependency
) -> ProductRead:
    return ProductRead.model_validate(execute(lambda: service.update_product(entity_id, payload)))


@router.post("/products/{entity_id}/archive", response_model=ProductRead)
def archive_product(entity_id: uuid.UUID, service: ServiceDependency) -> ProductRead:
    return ProductRead.model_validate(execute(lambda: service.archive_product(entity_id)))


@router.post("/products/{entity_id}/restore", response_model=ProductRead)
def restore_product(entity_id: uuid.UUID, service: ServiceDependency) -> ProductRead:
    return ProductRead.model_validate(execute(lambda: service.restore_product(entity_id)))


@router.get("/competitor-products", response_model=CompetitorProductList)
def list_competitor_products(
    service: ServiceDependency,
    include_archived: bool = False,
    limit: Limit = 50,
    offset: Offset = 0,
    competitor_id: uuid.UUID | None = None,
    brand: str | None = None,
    category: str | None = None,
    marketplace: Marketplace | None = None,
    tracking_tier: TrackingTier | None = None,
) -> CompetitorProductList:
    items, total = service.list_competitor_products(
        include_archived=include_archived,
        limit=limit,
        offset=offset,
        competitor_id=competitor_id,
        brand=brand,
        category=category,
        marketplace=marketplace,
        tracking_tier=tracking_tier,
    )
    return CompetitorProductList(items=items, total=total, limit=limit, offset=offset)


@router.post("/competitor-products", response_model=CompetitorProductRead, status_code=201)
def create_competitor_product(
    payload: CompetitorProductCreate, service: ServiceDependency
) -> CompetitorProductRead:
    return CompetitorProductRead.model_validate(
        execute(lambda: service.create_competitor_product(payload))
    )


@router.get("/competitor-products/{entity_id}", response_model=CompetitorProductRead)
def get_competitor_product(
    entity_id: uuid.UUID, service: ServiceDependency
) -> CompetitorProductRead:
    return CompetitorProductRead.model_validate(
        execute(lambda: service.get_competitor_product(entity_id))
    )


@router.patch("/competitor-products/{entity_id}", response_model=CompetitorProductRead)
def update_competitor_product(
    entity_id: uuid.UUID, payload: CompetitorProductUpdate, service: ServiceDependency
) -> CompetitorProductRead:
    return CompetitorProductRead.model_validate(
        execute(lambda: service.update_competitor_product(entity_id, payload))
    )


@router.post("/competitor-products/{entity_id}/archive", response_model=CompetitorProductRead)
def archive_competitor_product(
    entity_id: uuid.UUID, service: ServiceDependency
) -> CompetitorProductRead:
    return CompetitorProductRead.model_validate(
        execute(lambda: service.archive_competitor_product(entity_id))
    )


@router.post("/competitor-products/{entity_id}/restore", response_model=CompetitorProductRead)
def restore_competitor_product(
    entity_id: uuid.UUID, service: ServiceDependency
) -> CompetitorProductRead:
    return CompetitorProductRead.model_validate(
        execute(lambda: service.restore_competitor_product(entity_id))
    )


@router.get("/battle-cards", response_model=BattleCardList)
def list_battle_cards(
    service: ServiceDependency,
    include_archived: bool = False,
    limit: Limit = 50,
    offset: Offset = 0,
    product_id: uuid.UUID | None = None,
    status_filter: StatusFilter = None,
) -> BattleCardList:
    items, total = service.list_battle_cards(
        include_archived=include_archived,
        limit=limit,
        offset=offset,
        product_id=product_id,
        status=status_filter,
    )
    return BattleCardList(items=items, total=total, limit=limit, offset=offset)


@router.post("/battle-cards", response_model=BattleCardRead, status_code=201)
def create_battle_card(payload: BattleCardCreate, service: ServiceDependency) -> BattleCardRead:
    return BattleCardRead.model_validate(execute(lambda: service.create_battle_card(payload)))


@router.get("/battle-cards/{entity_id}", response_model=BattleCardRead)
def get_battle_card(entity_id: uuid.UUID, service: ServiceDependency) -> BattleCardRead:
    return BattleCardRead.model_validate(execute(lambda: service.get_battle_card(entity_id)))


@router.patch("/battle-cards/{entity_id}", response_model=BattleCardRead)
def update_battle_card(
    entity_id: uuid.UUID, payload: BattleCardUpdate, service: ServiceDependency
) -> BattleCardRead:
    return BattleCardRead.model_validate(
        execute(lambda: service.update_battle_card(entity_id, payload))
    )


@router.post("/battle-cards/{entity_id}/archive", response_model=BattleCardRead)
def archive_battle_card(entity_id: uuid.UUID, service: ServiceDependency) -> BattleCardRead:
    return BattleCardRead.model_validate(execute(lambda: service.archive_battle_card(entity_id)))


@router.post("/battle-cards/{entity_id}/restore", response_model=BattleCardRead)
def restore_battle_card(entity_id: uuid.UUID, service: ServiceDependency) -> BattleCardRead:
    return BattleCardRead.model_validate(execute(lambda: service.restore_battle_card(entity_id)))


@router.get("/battle-card-items", response_model=BattleCardItemList)
def list_battle_card_items(
    service: ServiceDependency,
    include_archived: bool = False,
    limit: Limit = 50,
    offset: Offset = 0,
    battle_card_id: uuid.UUID | None = None,
    competitor_product_id: uuid.UUID | None = None,
) -> BattleCardItemList:
    items, total = service.list_battle_card_items(
        include_archived=include_archived,
        limit=limit,
        offset=offset,
        battle_card_id=battle_card_id,
        competitor_product_id=competitor_product_id,
    )
    return BattleCardItemList(items=items, total=total, limit=limit, offset=offset)


@router.post("/battle-card-items", response_model=BattleCardItemRead, status_code=201)
def create_battle_card_item(
    payload: BattleCardItemCreate, service: ServiceDependency
) -> BattleCardItemRead:
    return BattleCardItemRead.model_validate(
        execute(lambda: service.create_battle_card_item(payload))
    )


@router.get("/battle-card-items/{entity_id}", response_model=BattleCardItemRead)
def get_battle_card_item(entity_id: uuid.UUID, service: ServiceDependency) -> BattleCardItemRead:
    return BattleCardItemRead.model_validate(
        execute(lambda: service.get_battle_card_item(entity_id))
    )


@router.patch("/battle-card-items/{entity_id}", response_model=BattleCardItemRead)
def update_battle_card_item(
    entity_id: uuid.UUID, payload: BattleCardItemUpdate, service: ServiceDependency
) -> BattleCardItemRead:
    return BattleCardItemRead.model_validate(
        execute(lambda: service.update_battle_card_item(entity_id, payload))
    )


@router.post("/battle-card-items/{entity_id}/archive", response_model=BattleCardItemRead)
def archive_battle_card_item(
    entity_id: uuid.UUID, service: ServiceDependency
) -> BattleCardItemRead:
    return BattleCardItemRead.model_validate(
        execute(lambda: service.archive_battle_card_item(entity_id))
    )


@router.post("/battle-card-items/{entity_id}/restore", response_model=BattleCardItemRead)
def restore_battle_card_item(
    entity_id: uuid.UUID, service: ServiceDependency
) -> BattleCardItemRead:
    return BattleCardItemRead.model_validate(
        execute(lambda: service.restore_battle_card_item(entity_id))
    )
