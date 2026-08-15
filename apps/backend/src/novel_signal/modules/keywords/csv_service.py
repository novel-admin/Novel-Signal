from __future__ import annotations

import csv
import io
import uuid
from enum import StrEnum

from pydantic import ValidationError
from sqlalchemy.orm import Session

from novel_signal.modules.keywords.models import Keyword, KeywordSource, TrackingTarget
from novel_signal.modules.keywords.repository import KeywordRepository
from novel_signal.modules.keywords.schemas import (
    CsvImportResult,
    CsvRowError,
    CsvValidationResult,
    KeywordCreate,
    SourceWrite,
    TrackingTargetCreate,
    normalize_keyword,
)
from novel_signal.modules.universe.models import CompetitorProduct, Product


class CsvEntity(StrEnum):
    KEYWORDS = "keywords"
    TRACKING_TARGETS = "tracking-targets"


HEADERS = {
    CsvEntity.KEYWORDS: [
        "keyword_text",
        "marketplace",
        "category",
        "tier",
        "tracking_status",
        "intent_cluster",
        "sources",
        "volume_estimate",
        "seasonality_index",
        "notes",
    ],
    CsvEntity.TRACKING_TARGETS: [
        "keyword_id",
        "product_id",
        "competitor_product_id",
        "cadence_minutes",
        "enabled",
    ],
}
SAMPLES = {
    CsvEntity.KEYWORDS: [
        "baby diapers",
        "amazon_in",
        "Baby Care",
        "T1",
        "active",
        "generic_category",
        "manual|autocomplete",
        "",
        "",
        "Sample row — replace before import",
    ],
    CsvEntity.TRACKING_TARGETS: [
        "00000000-0000-4000-8000-000000000001",
        "00000000-0000-4000-8000-000000000002",
        "",
        "240",
        "true",
    ],
}


class CsvValidationFailure(Exception):
    def __init__(self, result: CsvValidationResult) -> None:
        self.result = result


class KeywordCsvService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = KeywordRepository(session)

    def template(self, entity: CsvEntity) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(HEADERS[entity])
        writer.writerow(SAMPLES[entity])
        return output.getvalue()

    def validate(
        self, entity: CsvEntity, text: str
    ) -> tuple[CsvValidationResult, list[KeywordCreate | TrackingTargetCreate]]:
        errors: list[CsvRowError] = []
        parsed: list[KeywordCreate | TrackingTargetCreate] = []
        try:
            reader = csv.DictReader(io.StringIO(text, newline=""))
            if reader.fieldnames is None:
                raise ValueError("header row is required")
            missing = [field for field in HEADERS[entity] if field not in reader.fieldnames]
            if missing:
                raise ValueError(f"missing columns: {', '.join(missing)}")
            rows = list(reader)
        except (csv.Error, ValueError) as error:
            result = CsvValidationResult(
                valid=False,
                total_rows=0,
                valid_rows=0,
                invalid_rows=1,
                errors=[CsvRowError(row=1, field="csv", message=str(error))],
            )
            return result, []
        seen: set[tuple[object, ...]] = set()
        for number, row in enumerate(rows, 2):
            row_errors: list[CsvRowError] = []
            try:
                payload = (
                    self._parse_keyword(row)
                    if entity is CsvEntity.KEYWORDS
                    else self._parse_target(row)
                )
                identity = self._identity(entity, payload)
                if identity in seen:
                    row_errors.append(
                        CsvRowError(row=number, field="identity", message="duplicate row in CSV")
                    )
                seen.add(identity)
                if not row_errors:
                    self._database_validate(entity, payload, number, row_errors)
                if not row_errors:
                    parsed.append(payload)
            except ValidationError as error:
                for item in error.errors():
                    row_errors.append(
                        CsvRowError(
                            row=number,
                            field=".".join(map(str, item["loc"])),
                            message=str(item["msg"]),
                        )
                    )
            except (ValueError, TypeError) as error:
                row_errors.append(CsvRowError(row=number, field="row", message=str(error)))
            errors.extend(row_errors)
        invalid_rows = len({error.row for error in errors})
        result = CsvValidationResult(
            valid=not errors,
            total_rows=len(rows),
            valid_rows=len(rows) - invalid_rows,
            invalid_rows=invalid_rows,
            errors=errors,
        )
        return result, parsed

    def import_rows(self, entity: CsvEntity, text: str) -> CsvImportResult:
        result, rows = self.validate(entity, text)
        if not result.valid:
            raise CsvValidationFailure(result)
        try:
            for payload in rows:
                if isinstance(payload, KeywordCreate):
                    existing = self.repository.get_keyword_by_identity(
                        payload.marketplace, normalize_keyword(payload.keyword_text)
                    )
                    if existing is None:
                        values = payload.model_dump(exclude={"sources"})
                        model = Keyword(
                            **values, normalized_text=normalize_keyword(payload.keyword_text)
                        )
                        model.sources = [
                            KeywordSource(**source.model_dump()) for source in payload.sources
                        ]
                        self.session.add(model)
                    else:
                        existing_sources = {
                            (source.source_type, source.source_reference)
                            for source in existing.sources
                        }
                        for source in payload.sources:
                            if (
                                source.source_type,
                                source.source_reference,
                            ) not in existing_sources:
                                existing.sources.append(KeywordSource(**source.model_dump()))
                else:
                    self.session.add(TrackingTarget(**payload.model_dump()))
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return CsvImportResult(imported_rows=len(rows), entity=entity.value)

    def export(self, entity: CsvEntity, include_archived: bool) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(HEADERS[entity])
        if entity is CsvEntity.KEYWORDS:
            keyword_rows, _ = self.repository.list_keywords(
                include_archived=include_archived, limit=200, offset=0
            )
            for keyword_item in keyword_rows:
                writer.writerow(
                    [
                        keyword_item.keyword_text,
                        keyword_item.marketplace.value,
                        keyword_item.category or "",
                        keyword_item.tier.value,
                        keyword_item.tracking_status.value,
                        keyword_item.intent_cluster.value,
                        "|".join(source.source_type.value for source in keyword_item.sources),
                        keyword_item.volume_estimate or "",
                        keyword_item.seasonality_index or "",
                        keyword_item.notes or "",
                    ]
                )
        else:
            target_rows, _ = self.repository.list_targets(
                include_archived=include_archived, limit=200, offset=0
            )
            for target_item in target_rows:
                writer.writerow(
                    [
                        target_item.keyword_id,
                        target_item.product_id or "",
                        target_item.competitor_product_id or "",
                        target_item.cadence_minutes,
                        str(target_item.enabled).lower(),
                    ]
                )
        return output.getvalue()

    def _parse_keyword(self, row: dict[str, str | None]) -> KeywordCreate:
        sources = [
            SourceWrite(source_type=value.strip())
            for value in (row.get("sources") or "").split("|")
            if value.strip()
        ]
        return KeywordCreate(
            keyword_text=row.get("keyword_text") or "",
            marketplace=row.get("marketplace") or "amazon_in",
            category=row.get("category") or None,
            tier=row.get("tier") or "",
            tracking_status=row.get("tracking_status") or "active",
            intent_cluster=row.get("intent_cluster") or "unclassified",
            sources=sources,
            volume_estimate=int(row.get("volume_estimate") or "0")
            if row.get("volume_estimate")
            else None,
            seasonality_index=int(row.get("seasonality_index") or "0")
            if row.get("seasonality_index")
            else None,
            notes=row.get("notes") or None,
        )

    def _parse_target(self, row: dict[str, str | None]) -> TrackingTargetCreate:
        enabled = (row.get("enabled") or "true").strip().lower()
        if enabled not in {"true", "false", "1", "0"}:
            raise ValueError("enabled must be true or false")
        return TrackingTargetCreate(
            keyword_id=uuid.UUID(row.get("keyword_id") or ""),
            product_id=uuid.UUID(row["product_id"]) if row.get("product_id") else None,
            competitor_product_id=uuid.UUID(row["competitor_product_id"])
            if row.get("competitor_product_id")
            else None,
            cadence_minutes=int(row.get("cadence_minutes") or "240"),
            enabled=enabled in {"true", "1"},
        )

    def _identity(
        self, entity: CsvEntity, payload: KeywordCreate | TrackingTargetCreate
    ) -> tuple[object, ...]:
        if entity is CsvEntity.KEYWORDS:
            assert isinstance(payload, KeywordCreate)
            return (payload.marketplace, normalize_keyword(payload.keyword_text))
        assert isinstance(payload, TrackingTargetCreate)
        return (payload.keyword_id, payload.product_id, payload.competitor_product_id)

    def _database_validate(
        self,
        entity: CsvEntity,
        payload: KeywordCreate | TrackingTargetCreate,
        row: int,
        errors: list[CsvRowError],
    ) -> None:
        if entity is CsvEntity.KEYWORDS:
            assert isinstance(payload, KeywordCreate)
            keyword = payload
            existing = self.repository.get_keyword_by_identity(
                keyword.marketplace, normalize_keyword(keyword.keyword_text)
            )
            if existing is not None:
                existing_sources = {
                    (source.source_type, source.source_reference) for source in existing.sources
                }
                requested_sources = {
                    (source.source_type, source.source_reference) for source in keyword.sources
                }
                if requested_sources - existing_sources:
                    return
                errors.append(
                    CsvRowError(
                        row=row,
                        field="sources",
                        message="keyword and all supplied provenance sources already exist",
                    )
                )
            return
        assert isinstance(payload, TrackingTargetCreate)
        target = payload
        keyword_record = self.repository.get_keyword(target.keyword_id)
        if keyword_record is None or keyword_record.archived_at is not None:
            errors.append(
                CsvRowError(row=row, field="keyword_id", message="active keyword not found")
            )
        product_record: Product | CompetitorProduct | None
        if target.product_id is not None:
            product_record = self.repository.get_product(target.product_id)
        elif target.competitor_product_id is not None:
            product_record = self.repository.get_competitor_product(target.competitor_product_id)
        else:
            product_record = None
        if product_record is None or product_record.archived_at is not None:
            errors.append(
                CsvRowError(row=row, field="target", message="active target product not found")
            )
        if self.repository.target_exists(
            target.keyword_id, target.product_id, target.competitor_product_id
        ):
            errors.append(
                CsvRowError(
                    row=row, field="identity", message="active tracking target already exists"
                )
            )
