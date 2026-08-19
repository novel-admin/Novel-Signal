class PriceMonitoringError(Exception):
    code = "price_monitoring_error"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class PriceNotFound(PriceMonitoringError):
    code = "price_not_found"


class PriceConflict(PriceMonitoringError):
    code = "price_conflict"


class PriceValidation(PriceMonitoringError):
    code = "price_validation"
