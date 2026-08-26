from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select

from novel_signal.collectors.amazon_in.public_pages import (
    AmazonChallengeError,
    AmazonPublicCollector,
)
from novel_signal.collectors.base import CaptureRequest
from novel_signal.config import get_settings
from novel_signal.db import SessionLocal
from novel_signal.modules.collection.execution import (
    CollectionExecutionError,
    CollectionExecutionResult,
    CollectionWorkItem,
)
from novel_signal.modules.collection.models import CollectionFailureType
from novel_signal.modules.collection.parsing import EnvelopeValidator, ParserRegistry
from novel_signal.modules.collection.pipeline import EvidencePipeline, NoopPublisher, PublishContext
from novel_signal.modules.keywords.models import Keyword
from novel_signal.modules.rank_visibility.models import DeviceProfile
from novel_signal.modules.rank_visibility.schemas import CaptureIngest, SerpResultIn
from novel_signal.modules.rank_visibility.service import RankVisibilityService
from novel_signal.modules.universe.models import CompetitorProduct, Marketplace, Product
from novel_signal.parsers.amazon_public import AmazonProductParser, AmazonSearchParser


class _SerpPublisher:
    def publish(
        self, context: PublishContext, records: tuple[dict[str, Any], ...]
    ) -> dict[str, Any]:
        with SessionLocal() as session:
            payload = CaptureIngest(
                keyword_id=self.keyword_id,
                marketplace=Marketplace.AMAZON_IN,
                geo_code="IN",
                device_profile=DeviceProfile.DESKTOP,
                captured_at=context.captured_at,
                source_job_id=str(context.job_id),
                parser_version=context.platform + ":" + context.page_type,
                ingestion_key=f"amazon-serp:{context.job_id}",
                capture_metadata={"raw_evidence_id": str(context.raw_evidence_id)},
                results=[SerpResultIn.model_validate(record) for record in records],
            )
            RankVisibilityService(session).ingest(payload)
        return {"published_records": len(records), "capture_published": True}

    def __init__(self, keyword_id: Any) -> None:
        self.keyword_id = keyword_id


class AmazonPublicExecutor:
    async def execute(self, item: CollectionWorkItem) -> CollectionExecutionResult:
        if item.job_type.value == "product_detail":
            return await self._execute_product(item)
        if item.keyword_id is None:
            raise CollectionExecutionError(
                "Amazon public SERP collection requires a keyword",
                failure_type=CollectionFailureType.VALIDATION_ERROR,
                code="keyword_required",
                retryable=False,
            )
        if item.attempt_id is None:
            raise CollectionExecutionError(
                "Amazon executor requires the claimed attempt ID",
                failure_type=CollectionFailureType.UNKNOWN,
                code="attempt_id_missing",
                retryable=False,
            )
        with SessionLocal() as session:
            keyword = session.scalar(select(Keyword).where(Keyword.id == item.keyword_id))
        if keyword is None:
            raise CollectionExecutionError(
                "Keyword for collection job was not found",
                failure_type=CollectionFailureType.VALIDATION_ERROR,
                code="keyword_not_found",
                retryable=False,
            )

        settings = get_settings()
        collector = AmazonPublicCollector(
            timeout_seconds=settings.collector_timeout_seconds,
            min_delay_seconds=settings.amazon_in_min_delay_seconds,
            max_delay_seconds=settings.amazon_in_max_delay_seconds,
        )
        request = CaptureRequest(
            url=collector.search_url(keyword.keyword_text),
            target_id=str(keyword.id),
            page_type="serp",
        )
        try:
            capture = await collector.capture(request)
        except AmazonChallengeError as error:
            raise CollectionExecutionError(
                str(error),
                failure_type=CollectionFailureType.CHALLENGE,
                code="challenge_detected",
                retryable=False,
            ) from error
        except httpx.HTTPStatusError as error:
            raise CollectionExecutionError(
                str(error),
                failure_type=CollectionFailureType.HTTP_ERROR,
                code="amazon_http_error",
                retryable=error.response.status_code >= 500,
                details={"status_code": error.response.status_code},
            ) from error

        registry = ParserRegistry()
        registry.register(AmazonSearchParser())
        pipeline = EvidencePipeline(parser_registry=registry)
        return pipeline.process(
            job_id=item.job_id,
            attempt_id=item.attempt_id,
            platform="amazon_in",
            request=request,
            capture=capture,
            validator=EnvelopeValidator(
                required_fields=("marketplace_product_id", "absolute_position", "placement_type")
            ),
            publisher=_SerpPublisher(keyword.id),
            captured_at=datetime.now(UTC),
        )

    async def _execute_product(self, item: CollectionWorkItem) -> CollectionExecutionResult:
        subject_id = item.product_id or item.competitor_product_id
        if subject_id is None:
            raise CollectionExecutionError(
                "Amazon product collection requires a product subject",
                failure_type=CollectionFailureType.VALIDATION_ERROR,
                code="product_required",
                retryable=False,
            )
        with SessionLocal() as session:
            subject = session.get(Product, subject_id) or session.get(CompetitorProduct, subject_id)
        asin = getattr(subject, "marketplace_product_id", None) if subject else None
        if not asin or item.attempt_id is None:
            raise CollectionExecutionError(
                "Amazon product must have an ASIN and claimed attempt",
                failure_type=CollectionFailureType.VALIDATION_ERROR,
                code="amazon_asin_required",
                retryable=False,
            )
        settings = get_settings()
        collector = AmazonPublicCollector(
            timeout_seconds=settings.collector_timeout_seconds,
            min_delay_seconds=settings.amazon_in_min_delay_seconds,
            max_delay_seconds=settings.amazon_in_max_delay_seconds,
        )
        request = CaptureRequest(collector.product_url(asin), str(subject_id), "product_detail")
        try:
            capture = await collector.capture(request)
        except AmazonChallengeError as error:
            raise CollectionExecutionError(
                str(error),
                failure_type=CollectionFailureType.CHALLENGE,
                code="challenge_detected",
                retryable=False,
            ) from error
        registry = ParserRegistry()
        registry.register(AmazonProductParser())
        return EvidencePipeline(parser_registry=registry).process(
            job_id=item.job_id,
            attempt_id=item.attempt_id,
            platform="amazon_in",
            request=request,
            capture=capture,
            validator=EnvelopeValidator(required_fields=("marketplace_product_id",)),
            publisher=NoopPublisher(),
            captured_at=datetime.now(UTC),
        )
