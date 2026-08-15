class UniverseError(Exception):
    """Base exception for S1 universe operations."""

    code = "universe_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.code


class UniverseNotFoundError(UniverseError):
    code = "universe_not_found"


class UniverseConflictError(UniverseError):
    code = "universe_conflict"


class UniverseValidationError(UniverseError):
    code = "universe_invalid_request"
