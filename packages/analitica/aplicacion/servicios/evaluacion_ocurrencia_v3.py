"""Evaluación reusable de OcurrenciaOnline v3 contra las versiones actuales.

La fachada histórica en :mod:`analitica.interfaces.scripts.evaluar_ocurrencia_v3` conserva
el CLI y los aliases de importación. Este servicio recibe los datos ya cargados
para que la composición de evaluación pueda reutilizarse sin depender de una
interfaz ejecutable.
"""

from __future__ import annotations

from analitica.aplicacion.servicios.replay import emisiones_completas, normalizar_modelo
from analitica.dominio.evaluacion.metricas import metricas_pronostico
from analitica.dominio.modelos.hibrido import backtest_macro_legacy_v1
from analitica.dominio.modelos.ocurrencia_v1 import ejecutar_replay_hibrido_ocurrencia
from analitica.dominio.modelos.ocurrencia_v2 import ejecutar_replay_hibrido_ocurrencia_v2
from analitica.dominio.modelos.ocurrencia_v3 import ejecutar_replay_hibrido_ocurrencia_v3
from analitica.infraestructura.fuentes import cargar_datos

# Compatibilidad con los nombres privados que exponía el script histórico.
_emisiones_completas = emisiones_completas
_normalizar_modelo = normalizar_modelo

__all__ = [
    "backtest_macro_legacy_v1",
    "cargar_datos",
    "ejecutar",
    "ejecutar_replay_hibrido_ocurrencia",
    "ejecutar_replay_hibrido_ocurrencia_v2",
    "ejecutar_replay_hibrido_ocurrencia_v3",
    "emisiones_completas",
    "evaluar",
    "evaluar_ocurrencia_v3",
    "metricas",
    "metricas_pronostico",
    "normalizar_modelo",
]


def _metricas(tabla, modelo: str) -> dict:
    semanal = tabla.groupby("fecha_objetivo", as_index=False).agg(
        real_kg=("real_kg", "sum"), p50_kg=("p50_kg", "sum")
    )
    semanal["modelo"] = modelo
    semanal["banda_horizonte"] = "operativo"
    semanal["serie_id"] = "C2026"
    semanal["p10_kg"] = float("nan")
    semanal["p90_kg"] = float("nan")
    fila = metricas_pronostico(semanal).iloc[0].to_dict()
    return {
        "modelo": modelo,
        "n_semanas": int(len(semanal)),
        "wape_semanal": fila.get("wape"),
        "mase": fila.get("mase"),
        "mae_kg": fila.get("mae_kg"),
        "sesgo_pct": fila.get("sesgo_pct"),
        "real_kg": fila.get("volumen_real_kg"),
        "predicho_kg": float(semanal.p50_kg.sum()),
    }


def evaluar(datos, campania: str = "C2026") -> dict:
    """Evalúa MacroLegacy y las tres versiones de OcurrenciaOnline en replay."""

    emisiones = emisiones_completas(datos, campania)
    macro = backtest_macro_legacy_v1(
        datos,
        emisiones,
        campania=campania,
        horizonte_semanas=1,
        max_cortes=None,
    )[0]
    macro = normalizar_modelo(macro)
    v1, _ = ejecutar_replay_hibrido_ocurrencia(macro)
    v2, _ = ejecutar_replay_hibrido_ocurrencia_v2(macro)
    v3, _ = ejecutar_replay_hibrido_ocurrencia_v3(macro)
    return {
        "MacroLegacy_v1": _metricas(macro, "MacroLegacy_v1"),
        "HibridoOcurrenciaOnline_v1": _metricas(v1, "HibridoOcurrenciaOnline_v1"),
        "HibridoOcurrenciaOnline_v2": _metricas(v2, "HibridoOcurrenciaOnline_v2"),
        "HibridoOcurrenciaOnline_v3": _metricas(v3, "HibridoOcurrenciaOnline_v3"),
    }


# Aliases de servicio útiles para consumidores que nombran la operación por su
# verbo de ejecución o por el nombre completo del evaluador.
ejecutar = evaluar
evaluar_ocurrencia_v3 = evaluar
metricas = _metricas
