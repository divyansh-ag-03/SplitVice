"""
Application exception hierarchy.

All domain exceptions inherit from AppException. The global exception handler
in main.py converts these to JSON responses with the correct HTTP status code.

Usage in services:
    raise NotFoundError("User not found")
    raise ConflictError("Email already registered")
"""


class AppException(Exception):
    """Base class for all application exceptions."""

    status_code: int = 500
    default_detail: str = "An unexpected error occurred"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class NotFoundError(AppException):
    status_code = 404
    default_detail = "Resource not found"


class ConflictError(AppException):
    status_code = 409
    default_detail = "Resource already exists"


class ForbiddenError(AppException):
    status_code = 403
    default_detail = "You do not have permission to perform this action"


class UnauthorizedError(AppException):
    status_code = 401
    default_detail = "Authentication required"


class ValidationError(AppException):
    """
    Domain-level validation error (distinct from Pydantic's 422).
    Used when business rules are violated after schema validation passes.
    """

    status_code = 422
    default_detail = "Validation failed"
