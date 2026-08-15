from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from novel_signal.modules.universe.errors import UniverseConflictError
from novel_signal.modules.universe.models import (
    BattleCard,
    BattleCardItem,
    Competitor,
    CompetitorProduct,
    Product,
)
from novel_signal.modules.universe.repository import UniverseRepository
from novel_signal.modules.universe.schemas import (
    BattleCardFields,
    BattleCardItemCreate,
    CompetitorCreate,
    CompetitorProductCreate,
    CsvImportResult,
    CsvRowError,
    CsvValidationResult,
    ProductCreate,
)

CsvEntity = Literal[
    "competitors", "products", "competitor-products", "battle-cards", "battle-card-items"
]


@dataclass(frozen=True)
class CsvSpec:
    schema: type[BaseModel]
    model: type[Any]
    columns: tuple[str, ...]
    sample: tuple[str, ...]


SPECS: dict[CsvEntity, CsvSpec] = {
    "competitors": CsvSpec(
        CompetitorCreate,
        Competitor,
        (
            "name",
            "parent_company",
            "amazon_store_url",
            "amazon_seller_id",
            "category_presence",
            "positioning_tier",
            "threat_rating",
            "analyst_owner",
            "notes",
        ),
        (
            "Sample Competitor",
            "Sample Parent",
            "",
            "",
            "Baby Care",
            "mid",
            "3",
            "Sample Analyst",
            "Template sample only",
        ),
    ),
    "products": CsvSpec(
        ProductCreate,
        Product,
        (
            "internal_sku",
            "name",
            "brand",
            "category",
            "marketplace",
            "marketplace_product_id",
            "product_url",
            "pack_quantity",
            "pack_unit",
            "tracking_tier",
        ),
        (
            "SAMPLE-SKU-001",
            "Sample Product",
            "Sample Brand",
            "Baby Care",
            "amazon_in",
            "B0SAMPLE01",
            "https://www.amazon.in/dp/B0SAMPLE01",
            "4",
            "packs",
            "T1",
        ),
    ),
    "competitor-products": CsvSpec(
        CompetitorProductCreate,
        CompetitorProduct,
        (
            "competitor_name",
            "name",
            "brand",
            "category",
            "marketplace",
            "marketplace_product_id",
            "product_url",
            "pack_quantity",
            "pack_unit",
            "tracking_tier",
        ),
        (
            "Sample Competitor",
            "Sample Competitor Product",
            "Sample Brand",
            "Baby Care",
            "amazon_in",
            "B0SAMPLE02",
            "https://www.amazon.in/dp/B0SAMPLE02",
            "4",
            "packs",
            "T1",
        ),
    ),
    "battle-cards": CsvSpec(
        BattleCardFields,
        BattleCard,
        ("product_internal_sku", "name", "status", "comparison_notes"),
        (
            "SAMPLE-SKU-001",
            "Sample Battle Card",
            "draft",
            "Template sample only",
        ),
    ),
    "battle-card-items": CsvSpec(
        BattleCardItemCreate,
        BattleCardItem,
        (
            "battle_card_product_internal_sku",
            "battle_card_name",
            "competitor_marketplace",
            "competitor_marketplace_product_id",
            "priority_order",
            "same_pack_basis",
            "same_price_band",
            "same_category",
            "same_use_case",
            "notes",
        ),
        (
            "SAMPLE-SKU-001",
            "Sample Battle Card",
            "amazon_in",
            "B0SAMPLE02",
            "0",
            "true",
            "false",
            "true",
            "true",
            "Template sample only",
        ),
    ),
}


class UniverseCsvService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = UniverseRepository(session)

    def template(self, entity: CsvEntity) -> str:
        spec = SPECS[entity]
        return self._write_rows(spec.columns, [dict(zip(spec.columns, spec.sample, strict=True))])

    def validate(
        self, entity: CsvEntity, csv_text: str
    ) -> tuple[CsvValidationResult, list[dict[str, Any]]]:
        spec = SPECS[entity]
        rows, parse_errors = self._read_rows(csv_text, spec.columns)
        errors = list(parse_errors)
        normalized: list[dict[str, Any]] = []
        seen: dict[tuple[str, str], int] = {}
        invalid_rows: set[int] = {error.row for error in errors}
        for row_number, row in rows:
            row_errors, record = self._validate_row(entity, spec, row_number, row, seen)
            errors.extend(row_errors)
            if row_errors:
                invalid_rows.add(row_number)
            elif record is not None:
                normalized.append(record)
        total = len(rows)
        result = CsvValidationResult(
            valid=not errors,
            total_rows=total,
            valid_rows=max(0, total - len(invalid_rows)),
            invalid_rows=len(invalid_rows),
            errors=errors,
        )
        return result, normalized

    def import_rows(self, entity: CsvEntity, csv_text: str) -> CsvImportResult:
        validation, records = self.validate(entity, csv_text)
        if not validation.valid:
            raise CsvValidationFailure(validation)
        spec = SPECS[entity]
        try:
            for record in records:
                self.session.add(spec.model(**record))
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise UniverseConflictError(
                "CSV import conflicts with existing Universe data", code="csv_import_conflict"
            ) from error
        except Exception:
            self.session.rollback()
            raise
        return CsvImportResult(imported_rows=len(records), entity=entity)

    def export(self, entity: CsvEntity, *, include_archived: bool) -> str:
        spec = SPECS[entity]
        query = select(spec.model).order_by(spec.model.created_at, spec.model.id)
        if not include_archived:
            query = query.where(spec.model.archived_at.is_(None))
        records = self.session.scalars(query).all()
        rows = [self._export_row(entity, record) for record in records]
        return self._write_rows(spec.columns, rows)

    def _validate_row(
        self,
        entity: CsvEntity,
        spec: CsvSpec,
        row_number: int,
        row: dict[str, str],
        seen: dict[tuple[str, str], int],
    ) -> tuple[list[CsvRowError], dict[str, Any] | None]:
        errors: list[CsvRowError] = []
        values = {key: (value.strip() if value is not None else "") for key, value in row.items()}
        entity_id = self._uuid_value(values.pop("id", ""), row_number, "id", errors)
        archived_at = self._datetime_value(values.pop("archived_at", ""), row_number, errors)
        payload = {key: (None if value == "" else value) for key, value in values.items()}
        self._resolve_references(entity, row_number, payload, errors)
        if errors:
            return errors, None
        try:
            parsed = spec.schema.model_validate(payload)
        except ValidationError as error:
            for issue in error.errors():
                field = str(issue["loc"][-1]) if issue["loc"] else "row"
                errors.append(
                    CsvRowError(
                        row=row_number,
                        field=field,
                        code=str(issue["type"]),
                        message=str(issue["msg"]),
                    )
                )
            return errors, None
        if entity_id is not None and self.session.get(spec.model, entity_id) is not None:
            errors.append(
                CsvRowError(
                    row=row_number, field="id", code="id_conflict", message="This ID already exists"
                )
            )
        data = parsed.model_dump()
        self._business_validation(entity, row_number, data, entity_id, seen, errors)
        if errors:
            return errors, None
        return [], {**data, **({"id": entity_id} if entity_id else {}), "archived_at": archived_at}

    def _business_validation(
        self,
        entity: CsvEntity,
        row: int,
        data: dict[str, Any],
        entity_id: uuid.UUID | None,
        seen: dict[tuple[str, str], int],
        errors: list[CsvRowError],
    ) -> None:
        del entity_id
        if entity == "competitors":
            self._duplicate_or_conflict(
                row,
                "name",
                str(data["name"]).lower(),
                seen,
                errors,
                self.repository.active_competitor_name_exists(str(data["name"])),
            )
        elif entity == "products":
            self._duplicate_or_conflict(
                row,
                "internal_sku",
                str(data["internal_sku"]),
                seen,
                errors,
                self.repository.active_product_sku_exists(str(data["internal_sku"])),
            )
            identity = data.get("marketplace_product_id")
            if identity:
                self._duplicate_or_conflict(
                    row,
                    "marketplace_product_id",
                    f"{data['marketplace']}:{identity}",
                    seen,
                    errors,
                    self.repository.active_product_identity_exists(data["marketplace"], identity),
                )
        elif entity == "competitor-products":
            competitor = self.repository.get_competitor(data["competitor_id"])
            if competitor is None or competitor.archived_at is not None:
                errors.append(
                    CsvRowError(
                        row=row,
                        field="competitor_id",
                        code="missing_reference",
                        message="An active competitor with this ID is required",
                    )
                )
            identity = data.get("marketplace_product_id")
            if identity:
                key = f"{data['marketplace']}:{identity}"
                self._duplicate_or_conflict(
                    row,
                    "marketplace_product_id",
                    key,
                    seen,
                    errors,
                    self.repository.active_competitor_product_identity_exists(
                        data["marketplace"], identity
                    ),
                )
        elif entity == "battle-cards":
            product = self.repository.get_product(data["product_id"])
            if product is None or product.archived_at is not None:
                errors.append(
                    CsvRowError(
                        row=row,
                        field="product_id",
                        code="missing_reference",
                        message="An active owned product with this ID is required",
                    )
                )
        else:
            card = self.repository.get_battle_card(data["battle_card_id"])
            competitor_product = self.repository.get_competitor_product(
                data["competitor_product_id"]
            )
            if card is None or card.archived_at is not None:
                errors.append(
                    CsvRowError(
                        row=row,
                        field="battle_card_id",
                        code="missing_reference",
                        message="An active battle card with this ID is required",
                    )
                )
            if competitor_product is None or competitor_product.archived_at is not None:
                errors.append(
                    CsvRowError(
                        row=row,
                        field="competitor_product_id",
                        code="missing_reference",
                        message="An active competitor product with this ID is required",
                    )
                )
            key = f"{data['battle_card_id']}:{data['competitor_product_id']}"
            self._duplicate_or_conflict(
                row,
                "competitor_product_id",
                key,
                seen,
                errors,
                self.repository.active_battle_card_item_exists(
                    data["battle_card_id"], data["competitor_product_id"]
                ),
            )

    def _resolve_references(
        self,
        entity: CsvEntity,
        row: int,
        payload: dict[str, Any],
        errors: list[CsvRowError],
    ) -> None:
        if entity == "competitor-products":
            competitor_name = str(payload.pop("competitor_name", "") or "")
            competitor = self.repository.get_active_competitor_by_name(competitor_name)
            if competitor is None:
                errors.append(
                    CsvRowError(
                        row=row,
                        field="competitor_name",
                        code="missing_reference",
                        message="An active competitor with this name is required",
                    )
                )
            else:
                payload["competitor_id"] = competitor.id
        elif entity == "battle-cards":
            internal_sku = str(payload.pop("product_internal_sku", "") or "")
            product = self.repository.get_active_product_by_sku(internal_sku)
            if product is None:
                errors.append(
                    CsvRowError(
                        row=row,
                        field="product_internal_sku",
                        code="missing_reference",
                        message="An active owned product with this internal SKU is required",
                    )
                )
            else:
                payload["product_id"] = product.id
        elif entity == "battle-card-items":
            internal_sku = str(payload.pop("battle_card_product_internal_sku", "") or "")
            card_name = str(payload.pop("battle_card_name", "") or "")
            product = self.repository.get_active_product_by_sku(internal_sku)
            cards = (
                self.repository.get_active_battle_cards_by_reference(product.id, card_name)
                if product is not None
                else []
            )
            if len(cards) != 1:
                errors.append(
                    CsvRowError(
                        row=row,
                        field="battle_card_name",
                        code="ambiguous_reference" if len(cards) > 1 else "missing_reference",
                        message=(
                            "Battle-card reference is ambiguous"
                            if len(cards) > 1
                            else "An active battle card matching product SKU and name is required"
                        ),
                    )
                )
            else:
                payload["battle_card_id"] = cards[0].id
            marketplace = str(payload.pop("competitor_marketplace", "") or "")
            identity = str(payload.pop("competitor_marketplace_product_id", "") or "").upper()
            competitor_product = self.repository.get_active_competitor_product_by_identity(
                marketplace, identity
            )
            if competitor_product is None:
                errors.append(
                    CsvRowError(
                        row=row,
                        field="competitor_marketplace_product_id",
                        code="missing_reference",
                        message=(
                            "An active competitor product with this marketplace identity "
                            "is required"
                        ),
                    )
                )
            else:
                payload["competitor_product_id"] = competitor_product.id

    def _export_row(self, entity: CsvEntity, record: Any) -> dict[str, str]:
        if entity == "competitor-products":
            values = {
                "competitor_name": record.competitor.name,
                **{column: getattr(record, column) for column in SPECS[entity].columns[1:]},
            }
        elif entity == "battle-cards":
            values = {
                "product_internal_sku": record.product.internal_sku,
                "name": record.name,
                "status": record.status,
                "comparison_notes": record.comparison_notes,
            }
        elif entity == "battle-card-items":
            values = {
                "battle_card_product_internal_sku": record.battle_card.product.internal_sku,
                "battle_card_name": record.battle_card.name,
                "competitor_marketplace": record.competitor_product.marketplace,
                "competitor_marketplace_product_id": (
                    record.competitor_product.marketplace_product_id
                ),
                **{column: getattr(record, column) for column in SPECS[entity].columns[4:]},
            }
        else:
            values = {column: getattr(record, column) for column in SPECS[entity].columns}
        return {key: self._serialize(value) for key, value in values.items()}

    @staticmethod
    def _duplicate_or_conflict(
        row: int,
        field: str,
        key: str,
        seen: dict[tuple[str, str], int],
        errors: list[CsvRowError],
        database_conflict: bool,
    ) -> None:
        marker = (field, key)
        if marker in seen:
            errors.append(
                CsvRowError(
                    row=row,
                    field=field,
                    code="duplicate_csv_row",
                    message=f"Duplicates CSV row {seen[marker]}",
                )
            )
        elif database_conflict:
            errors.append(
                CsvRowError(
                    row=row,
                    field=field,
                    code="database_conflict",
                    message="Conflicts with an active database record",
                )
            )
        seen[marker] = row

    @staticmethod
    def _read_rows(
        csv_text: str, columns: tuple[str, ...]
    ) -> tuple[list[tuple[int, dict[str, str]]], list[CsvRowError]]:
        reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
        errors: list[CsvRowError] = []
        if reader.fieldnames is None:
            return [], [
                CsvRowError(
                    row=1,
                    field="header",
                    code="missing_header",
                    message="CSV header row is required",
                )
            ]
        missing = [column for column in columns if column not in reader.fieldnames]
        if missing:
            errors.append(
                CsvRowError(
                    row=1,
                    field="header",
                    code="missing_columns",
                    message=f"Missing columns: {', '.join(missing)}",
                )
            )
        try:
            rows = [(number, dict(row)) for number, row in enumerate(reader, start=2)]
        except csv.Error as error:
            errors.append(
                CsvRowError(
                    row=reader.line_num,
                    field="row",
                    code="malformed_csv",
                    message=str(error),
                )
            )
            rows = []
        return rows, errors

    @staticmethod
    def _uuid_value(
        value: str, row: int, field: str, errors: list[CsvRowError]
    ) -> uuid.UUID | None:
        if not value:
            return None
        try:
            return uuid.UUID(value)
        except ValueError:
            errors.append(
                CsvRowError(
                    row=row, field=field, code="invalid_uuid", message="Must be a valid UUID"
                )
            )
            return None

    @staticmethod
    def _datetime_value(value: str, row: int, errors: list[CsvRowError]) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            errors.append(
                CsvRowError(
                    row=row,
                    field="archived_at",
                    code="invalid_datetime",
                    message="Must be an ISO-8601 timestamp",
                )
            )
            return None

    @staticmethod
    def _serialize(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _write_rows(columns: tuple[str, ...], rows: list[dict[str, Any]]) -> str:
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()


class CsvValidationFailure(Exception):
    def __init__(self, result: CsvValidationResult) -> None:
        super().__init__("CSV validation failed")
        self.result = result
