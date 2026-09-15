"""Puertos de lectura administrativa."""

from __future__ import annotations

from typing import Protocol
from collections.abc import Iterator
from .analytics import AnalyticsQuery, EvaluationTrend, EvaluationAnalytics

from ..evaluaciones.schemas import ModuleKey
from .schemas import (
    AdminEvaluationDetail,
    AdminEvaluationPage,
    AdminEvaluationQuery,
    AdminEvaluationSummary,
    AdminLoadPage,
    AdminLoadQuery,
    AdminMasterPage,
    AdminMasterQuery,
    AdminMutation,
    AdminQABulkResolution,
    AdminQAPage,
    AdminQAQuery,
    AdminQAReview,
    AdminQASummary,
    EvaluationCorrectionRequest,
    ImportManifest,
    ImportPreview,
    ImportResult,
    MasterMutationRequest,
    MasterResource,
    QABulkDuplicateRequest,
    QAReviewRequest,
    UserMutationRequest,
)


class AdminRepositoryError(RuntimeError):
    """Error técnico al leer la superficie administrativa."""


class QARejectNotFoundError(AdminRepositoryError):
    """La incidencia solicitada no existe en la cuarentena."""


class ImportPreviewNotFoundError(AdminRepositoryError):
    """El preview no existe o no pertenece al usuario autenticado."""


class ImportStateError(AdminRepositoryError):
    """El manifiesto no se encuentra en un estado confirmable."""


class EvaluationNotFoundError(AdminRepositoryError):
    """La evaluación solicitada no existe o está fuera del alcance del usuario."""


class AdminMutationError(AdminRepositoryError):
    """Una mutación administrativa fue rechazada por una regla de integridad."""


class AdminMutationConflictError(AdminMutationError):
    """La mutación entra en conflicto con una clave o una operación previa."""


class AdminMutationForbiddenError(AdminMutationError):
    """La función SQL rechazó la mutación por permisos."""


class AdminRepository(Protocol):
    def list_evaluations(self, query: AdminEvaluationQuery) -> AdminEvaluationPage: ...

    def evaluation_counts(self, query: AdminEvaluationQuery): ...

    def evaluation_summary(self, query: AdminEvaluationQuery) -> AdminEvaluationSummary: ...

    def evaluation_trend(self, query: AnalyticsQuery) -> EvaluationTrend: ...

    def weekly_report(self, query): ...

    def evaluation_analytics(self, query: AnalyticsQuery) -> EvaluationAnalytics: ...

    def export_evaluations(self, query: AdminEvaluationQuery) -> Iterator[str]: ...

    def get_evaluation(
        self, module_key: ModuleKey, source_id: int, source_table: str | None = None
    ) -> AdminEvaluationDetail | None: ...

    def correct_evaluation(
        self,
        module_key: ModuleKey,
        source_id: int,
        request: EvaluationCorrectionRequest,
        values: dict[str, object],
        usuario_id: int,
    ) -> AdminMutation: ...

    def list_master(self, resource: MasterResource, query: AdminMasterQuery) -> AdminMasterPage: ...

    def mutate_master(
        self,
        resource: MasterResource,
        resource_id: int | None,
        request: MasterMutationRequest,
        usuario_id: int,
    ) -> AdminMutation: ...

    def mutate_user(
        self,
        usuario_id: int | None,
        request: UserMutationRequest,
        actor_id: int,
        values: dict[str, object],
    ) -> AdminMutation: ...

    def list_roles(self, query: AdminMasterQuery) -> AdminMasterPage: ...

    def list_users(self, query: AdminMasterQuery) -> AdminMasterPage: ...

    def list_imports(self, query: AdminLoadQuery) -> AdminLoadPage: ...

    def qa_summary(self) -> AdminQASummary: ...

    def list_qa(self, query: AdminQAQuery) -> AdminQAPage: ...

    def review_qa(
        self, rechazo_id: int, request: QAReviewRequest, usuario_id: int
    ) -> AdminQAReview: ...

    def confirm_qa_duplicates(
        self, request: QABulkDuplicateRequest, usuario_id: int
    ) -> AdminQABulkResolution: ...

    def create_import_preview(self, preview: ImportPreview, usuario_id: int) -> ImportPreview: ...

    def claim_import(
        self, preview_id: str, file_sha256: str, usuario_id: int
    ) -> ImportManifest: ...

    def complete_import(self, preview_id: str, usuario_id: int, result: ImportResult) -> None: ...

    def fail_import(self, preview_id: str, usuario_id: int, error: str) -> None: ...


class ImportPreviewError(ValueError):
    """El libro no tiene el formato de plantilla administrativa."""


__all__ = [
    "AdminRepository",
    "AdminRepositoryError",
    "AdminMutationError",
    "AdminMutationConflictError",
    "AdminMutationForbiddenError",
    "EvaluationNotFoundError",
    "ImportPreviewError",
    "ImportPreviewNotFoundError",
    "ImportStateError",
    "QARejectNotFoundError",
]
