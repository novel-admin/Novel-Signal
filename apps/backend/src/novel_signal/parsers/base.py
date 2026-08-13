from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ParsedEnvelope:
    parser_version: str
    page_type: str
    records: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...] = ()


class PageParser(Protocol):
    platform: str
    page_type: str
    version: str

    def parse(self, raw: bytes) -> ParsedEnvelope: ...
