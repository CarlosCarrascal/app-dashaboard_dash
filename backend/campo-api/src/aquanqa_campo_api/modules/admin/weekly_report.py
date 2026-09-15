"""Weekly observed counts for repeatable evaluation presentations."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field
from .schemas import AdminEvaluationQuery

class WeeklyReportQuery(AdminEvaluationQuery):
    module_key: Literal['flores'] = 'flores'
    metric: Literal['n_flores', 'cuajo'] = 'n_flores'
    weeks: int = Field(default=26, ge=4, le=53)

class WeeklyReportPoint(BaseModel):
    week: date
    fundo_id: int
    fundo: str
    modulo_id: int
    modulo: str
    evaluations: int
    available: int
    total: float | None
    mean: float | None

class WeeklyReport(BaseModel):
    metric: str
    unit: str = 'conteo por evaluación'
    desde: date | None
    hasta: date | None
    grano: str | None
    grains: list[str]
    points: list[WeeklyReportPoint]
