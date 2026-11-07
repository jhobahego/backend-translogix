"""Domain-level exceptions for business logic and entity lifecycles.

Decoupled from HTTP and database layers. Presentation layers map these
exceptions to standard HTTP response codes (e.g. 404, 409, 422).
"""
from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain-level exceptions."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class EntityNotFoundError(DomainError):
    """Raised when an entity is not found in the domain model."""

    def __init__(self, entity_name: str, entity_id: str | int) -> None:
        super().__init__(f"{entity_name} with identifier {entity_id!r} not found")
        self.entity_name = entity_name
        self.entity_id = entity_id


class BusinessRuleViolationError(DomainError):
    """Raised when an operation violates a core business rule."""


class InvalidStateTransitionError(BusinessRuleViolationError):
    """Raised when an invalid state transition is attempted on an entity."""

    def __init__(
        self, current_state: str, target_state: str, reason: str | None = None
    ) -> None:
        msg = f"Cannot transition from state {current_state!r} to {target_state!r}"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)
        self.current_state = current_state
        self.target_state = target_state
        self.reason = reason


__all__ = [
    "BusinessRuleViolationError",
    "DomainError",
    "EntityNotFoundError",
    "InvalidStateTransitionError",
]
