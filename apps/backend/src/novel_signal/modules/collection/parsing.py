from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from novel_signal.parsers.base import PageParser, ParsedEnvelope


class ParserNotRegisteredError(LookupError):
    pass


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[tuple[str, str], PageParser] = {}

    def register(self, parser: PageParser) -> None:
        self._parsers[(parser.platform, parser.page_type)] = parser

    def get(self, platform: str, page_type: str) -> PageParser:
        parser = self._parsers.get((platform, page_type))
        if parser is None:
            raise ParserNotRegisteredError(f"No parser registered for {platform}/{page_type}")
        return parser


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    record_index: int | None = None
    field: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "record_index": self.record_index,
            "field": self.field,
        }


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    issues: tuple[ValidationIssue, ...]
    field_fill_rate: float
    row_count: int


class EnvelopeValidator:
    """Generic schema/completeness gate. Domain modules can supply stricter required fields."""

    def __init__(self, *, required_fields: tuple[str, ...] = (), minimum_rows: int = 1) -> None:
        if minimum_rows < 0:
            raise ValueError("minimum_rows must be non-negative")
        self.required_fields = required_fields
        self.minimum_rows = minimum_rows

    def validate(
        self,
        envelope: ParsedEnvelope,
        *,
        expected_page_type: str,
        expected_parser_version: str,
    ) -> ValidationResult:
        issues: list[ValidationIssue] = []
        if envelope.page_type != expected_page_type:
            issues.append(
                ValidationIssue(
                    code="page_type_mismatch",
                    message=(
                        f"Parser returned {envelope.page_type!r}; expected {expected_page_type!r}"
                    ),
                )
            )
        if envelope.parser_version != expected_parser_version:
            issues.append(
                ValidationIssue(
                    code="parser_version_mismatch",
                    message=(
                        f"Parser returned {envelope.parser_version!r}; "
                        f"expected {expected_parser_version!r}"
                    ),
                )
            )
        if len(envelope.records) < self.minimum_rows:
            issues.append(
                ValidationIssue(
                    code="row_count_below_minimum",
                    message=(
                        f"Parser returned {len(envelope.records)} rows; "
                        f"minimum is {self.minimum_rows}"
                    ),
                )
            )

        expected_cells = len(envelope.records) * len(self.required_fields)
        filled_cells = 0
        for index, record in enumerate(envelope.records):
            if not isinstance(record, dict):
                issues.append(
                    ValidationIssue(
                        code="record_not_object",
                        message="Parsed record must be an object",
                        record_index=index,
                    )
                )
                continue
            for field in self.required_fields:
                value = record.get(field)
                if value is None or (isinstance(value, str) and not value.strip()):
                    issues.append(
                        ValidationIssue(
                            code="required_field_missing",
                            message=f"Required field {field!r} is missing or blank",
                            record_index=index,
                            field=field,
                        )
                    )
                else:
                    filled_cells += 1

        fill_rate = 1.0 if expected_cells == 0 else filled_cells / expected_cells
        return ValidationResult(
            valid=not issues,
            issues=tuple(issues),
            field_fill_rate=fill_rate,
            row_count=len(envelope.records),
        )
