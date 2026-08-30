"""Contratos y configuracion inmutable de la certificacion de replay."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Serie:
    modelo: str
    version: str
    uso: str


@dataclass(frozen=True)
class Certificacion:
    campania: str
    run_id: int
    series: tuple[Serie, ...]
    nota: str
    horizontes: tuple[int, ...] = (1,)
    granularidad: str = "lote_semana"
    curva_stitched: bool = True
    cerrado_hasta_override: date | None = None


CERTIFICACIONES = (
    Certificacion(
        campania="C2026",
        run_id=76,
        series=(
            Serie("R09_publicado", "emision_publicada_no_algoritmo", "referencia"),
            Serie("MacroLegacy_v1", "macro_legacy_postgres_auto_asof_v2", "historico"),
            Serie(
                "HibridoOcurrenciaOnline_v2",
                "macro_hurdle_online_full_coverage_v2",
                "historico",
            ),
        ),
        nota="Replay cerrado hasta 10-16/08; 17-23/08 permanece parcial.",
    ),
    Certificacion(
        campania="C2025",
        run_id=78,
        series=(
            Serie(
                "MacroLegacy_v1",
                "macro_legacy_postgres_auto_asof_full_campaign",
                "historico",
            ),
            Serie(
                "HibridoOcurrenciaOnline_v2",
                "macro_hurdle_online_full_coverage_v2",
                "historico",
            ),
        ),
        nota=(
            "Campaña completa para Macro e Híbrido. R09 no se certifica aquí porque "
            "solo cubre ocho semanas comparables."
        ),
    ),
    Certificacion(
        campania="C2026",
        run_id=73,
        series=(
            Serie(
                "MacroLegacy_v1",
                "macro_legacy_reconstruida_v2",
                "screening",
            ),
        ),
        nota=(
            "Baseline multihorizonte congelado para preflight 1/2/4/6. "
            "No es visible ni publicable en el dashboard."
        ),
        horizontes=(1, 2, 4, 6),
        granularidad="lote_emision_semana",
        curva_stitched=False,
        cerrado_hasta_override=date(2026, 8, 16),
    ),
)

RUNS_RECHAZADOS = (81, 82, 83)

RELEASE_OPERATIVA = {
    "campania": "C2026",
    "run_id": 65,
    "modelo": "ModeloOperativoActual_v1",
    "version": "v1-auto",
    "nota": (
        "Emisión operativa ProySemanal_34 con parámetros PostgreSQL automáticos; "
        "no constituye evaluación histórica ni usa un denominador real futuro."
    ),
}


__all__ = [
    "CERTIFICACIONES",
    "Certificacion",
    "RELEASE_OPERATIVA",
    "RUNS_RECHAZADOS",
    "Serie",
]
