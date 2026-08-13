from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CaptureRequest:
    url: str
    target_id: str
    page_type: str


@dataclass(frozen=True)
class CaptureResult:
    final_url: str
    body: bytes
    content_type: str
    challenge_detected: bool = False


class Collector(Protocol):
    async def capture(self, request: CaptureRequest) -> CaptureResult: ...
