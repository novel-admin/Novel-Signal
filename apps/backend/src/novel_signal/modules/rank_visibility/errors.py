class RankVisibilityError(Exception):
    code = "rank_visibility_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.code


class RankVisibilityNotFoundError(RankVisibilityError):
    code = "rank_visibility_not_found"


class RankVisibilityConflictError(RankVisibilityError):
    code = "duplicate_ingestion"


class RankVisibilityValidationError(RankVisibilityError):
    code = "rank_visibility_invalid_request"
