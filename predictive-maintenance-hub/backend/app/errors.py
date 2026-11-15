"""Application errors mapped to JSON responses by the Flask error handlers."""
from __future__ import annotations


class AppError(Exception):
    status = 500
    code = "internal_error"

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field


class ValidationError(AppError):
    status = 422
    code = "validation_error"


class NotFound(AppError):
    status = 404
    code = "not_found"


class Conflict(AppError):
    status = 409
    code = "conflict"


class Unauthorized(AppError):
    status = 401
    code = "unauthorized"


class Forbidden(AppError):
    status = 403
    code = "forbidden"
