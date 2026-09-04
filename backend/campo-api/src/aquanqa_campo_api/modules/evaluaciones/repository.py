"""Puerto de persistencia del módulo de evaluaciones."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from .rules import NormalizedEvaluation
from .schemas import EvaluationHistoryItem, EvaluationReceipt, ModuleKey


class EvaluationRepositoryError(RuntimeError):
    """Error técnico al acceder a la persistencia de evaluaciones."""


class LocationNotFoundError(EvaluationRepositoryError):
    """El lote recibido no existe o no es elegible para captura."""


class EvaluatorNotFoundError(EvaluationRepositoryError):
    """El evaluador enviado no existe o está inactivo."""


class IdempotencyConflictError(EvaluationRepositoryError):
    """El mismo UUID local llegó con otro contenido o módulo."""


class EvaluationNotFoundError(EvaluationRepositoryError):
    """La evaluación móvil solicitada no existe o no puede editarse."""


class EvaluationConflictError(EvaluationRepositoryError):
    """La edición entra en conflicto con otra evaluación existente."""


@dataclass(frozen=True)
class StoredEvaluation:
    receipt: EvaluationReceipt


@dataclass(frozen=True)
class StoredHistoryPage:
    items: list[EvaluationHistoryItem]
    has_more: bool


class EvaluationRepository(Protocol):
    def save(self, normalized: NormalizedEvaluation) -> StoredEvaluation: ...

    def save_many(
        self, normalized: Sequence[NormalizedEvaluation]
    ) -> list[StoredEvaluation]: ...

    def get_by_client_id(self, client_id: UUID) -> StoredEvaluation | None: ...

    def update(self, normalized: NormalizedEvaluation) -> StoredEvaluation: ...

    def list_history(
        self,
        *,
        evaluador_id: int | None,
        evaluador_dni: str | None,
        module_key: ModuleKey | None,
        limit: int,
        offset: int,
    ) -> StoredHistoryPage: ...


__all__ = [
    "EvaluationRepository",
    "EvaluationRepositoryError",
    "EvaluatorNotFoundError",
    "EvaluationConflictError",
    "EvaluationNotFoundError",
    "IdempotencyConflictError",
    "LocationNotFoundError",
    "StoredEvaluation",
    "StoredHistoryPage",
]
