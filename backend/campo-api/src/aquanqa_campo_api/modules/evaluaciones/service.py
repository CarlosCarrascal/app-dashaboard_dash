"""Casos de uso del registro de evaluaciones."""

from uuid import UUID

from .repository import EvaluationRepository
from .rules import normalize_evaluation
from .schemas import (
    EvaluationCreate,
    EvaluationHistoryPage,
    EvaluationHistoryQuery,
    EvaluationPatch,
    EvaluationReceipt,
)


class EvaluationService:
    def __init__(self, repository: EvaluationRepository):
        self._repository = repository

    def register(self, payload: EvaluationCreate) -> EvaluationReceipt:
        return self._repository.save(normalize_evaluation(payload)).receipt

    def register_many(self, payloads: list[EvaluationCreate]) -> list[EvaluationReceipt]:
        """Valida todo el lote antes de pedir una única transacción al repositorio."""
        normalized = [normalize_evaluation(payload) for payload in payloads]
        return [stored.receipt for stored in self._repository.save_many(normalized)]

    def find_by_client_id(self, client_id: UUID) -> EvaluationReceipt | None:
        stored = self._repository.get_by_client_id(client_id)
        return None if stored is None else stored.receipt

    def update(self, payload: EvaluationPatch) -> EvaluationReceipt:
        return self._repository.update(normalize_evaluation(payload)).receipt

    def list_history(self, query: EvaluationHistoryQuery) -> EvaluationHistoryPage:
        stored = self._repository.list_history(
            evaluador_id=query.evaluador_id,
            evaluador_dni=query.evaluador_dni,
            module_key=query.module_key,
            limit=query.limit,
            offset=query.offset,
        )
        return EvaluationHistoryPage(
            items=stored.items,
            has_more=stored.has_more,
            next_offset=query.offset + len(stored.items) if stored.has_more else None,
        )


__all__ = ["EvaluationService"]
