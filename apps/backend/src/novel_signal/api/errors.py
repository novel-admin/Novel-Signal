from typing import Any

from fastapi import HTTPException, status


def api_error(
    detail: str,
    *,
    code: str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    fields: dict[str, Any] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": detail, "fields": fields or {}},
    )
