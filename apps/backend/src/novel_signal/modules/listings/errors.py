class ListingError(Exception):
    code = "listing_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.code


class ListingNotFound(ListingError):
    code = "listing_not_found"


class ListingConflict(ListingError):
    code = "listing_conflict"


class ListingValidation(ListingError):
    code = "listing_invalid_request"
