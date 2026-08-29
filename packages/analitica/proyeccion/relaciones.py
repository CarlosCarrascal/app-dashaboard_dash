"""Fachada compatible para relaciones agronómicas e inferencia longitudinal.

La implementación está organizada por responsabilidad en :mod:`relaciones_partes`.
Este módulo conserva las rutas históricas, incluidos los helpers privados que usan
consumidores y pruebas existentes.
"""

from __future__ import annotations

from .ensamblaje import (
    AUDITORIA_ENSAMBLADO_COLUMNAS,  # noqa: F401
    _auditoria_dataframe,  # noqa: F401
    _claves_no_emparejadas,  # noqa: F401
    _filas_duplicadas,  # noqa: F401
    _merge_auditado,  # noqa: F401
    _registrar_base,  # noqa: F401
)
from .relaciones_partes.estadistica import (
    HIPOTESIS,
    ORDEN_CICLO,
    PREDICTORES_CULTIVO,
    PREDICTORES_EXTERNOS,
    RESPUESTAS_MATRIZ,
    REZAGOS_MATRIZ,
    Hipotesis,
    _bh,
    _efecto_practico,
    _ic_bootstrap_bloques,
    _p_agrupado,
    _pares_matriz,
    _placebo_parcial,
    _residuos_controles,
    evaluar_matriz_relaciones,
    evaluar_relaciones,
)
from .relaciones_partes.evidencia import (
    DESFASES_SOLIDO,
    REFERENCIAS_HIPOTESIS,
    SEMANAS_SOLIDO,
    clasificar_hallazgos,
    generar_claims,
    hallazgos_matriz,
    resumen_matriz,
    sensibilidad_gdd,
)
from .relaciones_partes.packing import panel_packing, relaciones_packing
from .relaciones_partes.panel import (
    _agregar_semana,
    _clima_semanal,
    construir_panel_relaciones,
)

# Metadato documental histórico. No participa en los cálculos y se conserva aquí para
# que los consumidores que lo importan desde ``relaciones`` mantengan la misma ruta.
DAG_AGRONOMICO = {
    "version": "1.0.0",
    "nodos": [
        "poda",
        "temperatura",
        "gdd",
        "floracion",
        "polinizacion_no_observada",
        "cuajo",
        "estados_e1_e5",
        "diametro",
        "peso_baya",
        "frutos_por_planta",
        "plantas_productivas",
        "kg",
        "riego",
        "eto",
        "dpv",
        "suelo_no_observado",
        "nutricion_no_observada",
    ],
    "aristas": [
        ["poda", "floracion"],
        ["temperatura", "gdd"],
        ["gdd", "floracion"],
        ["floracion", "cuajo"],
        ["polinizacion_no_observada", "cuajo"],
        ["cuajo", "estados_e1_e5"],
        ["estados_e1_e5", "diametro"],
        ["diametro", "peso_baya"],
        ["frutos_por_planta", "kg"],
        ["plantas_productivas", "kg"],
        ["peso_baya", "kg"],
        ["riego", "peso_baya"],
        ["eto", "riego"],
        ["dpv", "peso_baya"],
        ["suelo_no_observado", "peso_baya"],
        ["nutricion_no_observada", "peso_baya"],
    ],
    "nota": "El DAG declara supuestos; no convierte asociaciones observacionales en causas.",
}


__all__ = [
    "AUDITORIA_ENSAMBLADO_COLUMNAS",
    "DAG_AGRONOMICO",
    "DESFASES_SOLIDO",
    "HIPOTESIS",
    "ORDEN_CICLO",
    "PREDICTORES_CULTIVO",
    "PREDICTORES_EXTERNOS",
    "REFERENCIAS_HIPOTESIS",
    "REZAGOS_MATRIZ",
    "RESPUESTAS_MATRIZ",
    "SEMANAS_SOLIDO",
    "Hipotesis",
    "_agregar_semana",
    "_auditoria_dataframe",
    "_bh",
    "_claves_no_emparejadas",
    "_clima_semanal",
    "_efecto_practico",
    "_filas_duplicadas",
    "_ic_bootstrap_bloques",
    "_merge_auditado",
    "_p_agrupado",
    "_pares_matriz",
    "_placebo_parcial",
    "_registrar_base",
    "_residuos_controles",
    "clasificar_hallazgos",
    "construir_panel_relaciones",
    "evaluar_matriz_relaciones",
    "evaluar_relaciones",
    "generar_claims",
    "hallazgos_matriz",
    "panel_packing",
    "relaciones_packing",
    "resumen_matriz",
    "sensibilidad_gdd",
]
