class KeywordError(Exception):
    code = "keyword_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.code


class KeywordNotFoundError(KeywordError):
    code = "keyword_not_found"


class KeywordConflictError(KeywordError):
    code = "keyword_conflict"


class KeywordValidationError(KeywordError):
    code = "keyword_invalid_request"
