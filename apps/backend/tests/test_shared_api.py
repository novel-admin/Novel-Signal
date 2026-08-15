import pytest
from fastapi import HTTPException
from novel_signal.api.dependencies import require_internal_access


def test_internal_access_gate_rejects_missing_token() -> None:
    with pytest.raises(HTTPException) as error:
        require_internal_access(None)
    assert error.value.status_code == 401
