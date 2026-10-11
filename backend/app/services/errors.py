"""Service-layer errors. main.py maps them to HTTP status codes, so services stay HTTP-free."""


class ServiceError(Exception):
    status_code = 400

    def __init__(self, message: str, *, code: str = "error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class NotFound(ServiceError):
    status_code = 404


class Invalid(ServiceError):
    status_code = 422


class Conflict(ServiceError):
    status_code = 409
