class ServiceError(Exception):
    """Base class for business-rule errors; the API layer maps them to HTTP responses."""


class NotFoundError(ServiceError):
    pass


class ConflictError(ServiceError):
    pass
