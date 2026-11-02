class ServiceError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidRequest(ServiceError):
    status_code = 422
    code = "invalid_request"


class Unauthorized(ServiceError):
    status_code = 401
    code = "unauthorized"


class Forbidden(ServiceError):
    status_code = 403
    code = "forbidden"


class NotFound(ServiceError):
    status_code = 404
    code = "not_found"


class Conflict(ServiceError):
    status_code = 409
    code = "conflict"


class ProviderNotConfigured(ServiceError):
    status_code = 503
    code = "provider_not_configured"
