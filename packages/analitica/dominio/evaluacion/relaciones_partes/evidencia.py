"""Claims, hallazgos y sensibilidad de la evidencia relacional."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

REFERENCIAS_HIPOTESIS = {
    "H1": ["HEAT_HARVEST_2012", "KIRK_ISAACS_2012"],
    "H2": ["CA244NI", "GIBBS_2016_POLLINATION"],
    "H3": ["CA244NI", "HEAT_HARVEST_2012"],
    "H4": ["WAN_2024_FRUIT"],
    "H5": ["CA244NI", "GIBBS_2016_POLLINATION"],
    "H6": ["HOLZAPFEL_2004_IRRIGATION"],
    "H6_R": ["HOLZAPFEL_2004_IRRIGATION"],
}


# Cómo se clasifica cada relación. El criterio es explícito a propósito: sin él, «sólido»
# y «pista» se convierten en juicios de quien mira el gráfico.
#
# - sólido: sobrevive a la corrección por multiplicidad y al placebo, tiene al menos 40
#   semanas independientes y la relación se mantiene en 3 o más desfases contiguos.
# - hipótesis: sobrevive, pero con menos respaldo. Sirve para decidir qué medir mejor.
# - ruido: no sobrevive. Se cuenta, no se muestra.
SEMANAS_SOLIDO = 40
DESFASES_SOLIDO = 3


def clasificar_hallazgos(matriz: pd.DataFrame) -> pd.DataFrame:
    """Un hallazgo por par, con su nivel de confianza declarado.

    La distinción entre patrón sólido e hipótesis no es cosmética: determina qué se puede
    llevar a una decisión de manejo y qué solo justifica seguir midiendo.
    """
    if matriz.empty or "sobrevive" not in matriz:
        return pd.DataFrame()
    vivos = matriz[matriz.sobrevive].copy()
    if vivos.empty:
        return pd.DataFrame()
    vivos["magnitud"] = vivos.correlacion_parcial.abs()
    mejores = vivos.sort_values("magnitud").groupby(["predictor", "respuesta"]).tail(1)
    respaldo = (
        vivos.groupby(["predictor", "respuesta"])
        .rezago_semanas.agg(["size", "min", "max"])
        .rename(
            columns={"size": "desfases_que_sobreviven", "min": "desfase_min", "max": "desfase_max"}
        )
    )
    hallazgos = mejores.merge(respaldo, on=["predictor", "respuesta"])
    hallazgos["nivel"] = np.where(
        (hallazgos.n_efectivo >= SEMANAS_SOLIDO)
        & (hallazgos.desfases_que_sobreviven >= DESFASES_SOLIDO),
        "solido",
        "hipotesis",
    )
    return hallazgos.sort_values(["nivel", "magnitud"], ascending=[True, False]).reset_index(
        drop=True
    )


def hallazgos_matriz(matriz: pd.DataFrame) -> pd.DataFrame:
    """Un hallazgo por par, no uno por desfase."""
    if matriz.empty or "sobrevive" not in matriz:
        return pd.DataFrame()
    vivos = matriz[matriz.sobrevive].copy()
    if vivos.empty:
        return pd.DataFrame()
    vivos["magnitud"] = vivos.correlacion_parcial.abs()
    mejores = vivos.sort_values("magnitud").groupby(["predictor", "respuesta"]).tail(1)
    desfases = (
        vivos.groupby(["predictor", "respuesta"])
        .rezago_semanas.agg(["size", "min", "max"])
        .rename(
            columns={"size": "desfases_que_sobreviven", "min": "desfase_min", "max": "desfase_max"}
        )
    )
    return (
        mejores.merge(desfases, on=["predictor", "respuesta"])
        .sort_values("magnitud", ascending=False)
        .reset_index(drop=True)
    )


def resumen_matriz(matriz: pd.DataFrame, alfa: float = 0.05) -> dict[str, float]:
    """Cuántos hallazgos hay y cuántos se esperarían por puro azar."""
    if matriz.empty:
        return {}
    pruebas = len(matriz)
    pares = int(matriz.groupby(["predictor", "respuesta"]).ngroups)
    hallazgos = hallazgos_matriz(matriz)
    return {
        "pruebas": pruebas,
        "pares": pares,
        "sin_corregir": int((matriz.p_pearson < alfa).sum()),
        "esperados_por_azar": round(alfa * pruebas, 1),
        "pares_que_sobreviven": int(len(hallazgos)),
        "pruebas_que_sobreviven": int(matriz.sobrevive.sum()),
        "descartados_por_placebo": int(matriz.placebo_supera_estimacion.sum()),
    }


def generar_claims(
    relaciones: pd.DataFrame, inferencia: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Una conclusión prudente por hipótesis; ninguna recibe etiqueta causal."""
    if relaciones.empty:
        return pd.DataFrame()
    claims = []
    for hipotesis_id, grupo in relaciones.groupby("hipotesis_id"):
        mejor = grupo.sort_values(["p_ajustado_bh", "pearson"], ascending=[True, False]).iloc[0]
        concuerda = True
        if inferencia is not None and not inferencia.empty:
            mixto = inferencia[
                (inferencia.hipotesis_id == hipotesis_id) & (inferencia.metodo == "MixedLM")
            ]
            valores = pd.to_numeric(mixto.get("p_valor"), errors="coerce").dropna()
            if not valores.empty:
                concuerda = bool(valores.min() < 0.05)
        estable = bool(
            mejor.p_ajustado_bh < 0.05
            and mejor.n_efectivo >= SEMANAS_SOLIDO
            and np.isfinite(mejor.pearson_ic_inferior)
            and np.isfinite(mejor.pearson_ic_superior)
            and not mejor.placebo_supera_estimacion
            and (pd.isna(mejor.estabilidad_signo_modulo) or mejor.estabilidad_signo_modulo >= 0.6)
            and concuerda
        )
        clase = "temporal" if estable and mejor.rezago_semanas > 0 else "correlacional"
        grado = (
            "temporal estable"
            if estable and mejor.rezago_semanas > 0
            else ("correlacional estable" if estable else "exploratoria")
        )
        estimacion_ic = (
            f"r={mejor.pearson:+.2f}; IC95% {mejor.pearson_ic_inferior:+.2f} a "
            f"{mejor.pearson_ic_superior:+.2f}"
            if np.isfinite(mejor.pearson_ic_inferior)
            else f"r={mejor.pearson:+.2f}; IC no estimable"
        )
        afirmacion = (
            f"Se observa una asociación {grado} "
            f"entre {mejor.predictor} y {mejor.respuesta} a {int(mejor.rezago_semanas)} semanas "
            f"({estimacion_ic}). No identifica un efecto causal."
        )
        huella = hashlib.sha1(
            f"{hipotesis_id}:{mejor.predictor}:{mejor.respuesta}".encode(), usedforsecurity=False
        ).hexdigest()[:12]
        metodos = []
        if inferencia is not None and not inferencia.empty:
            registros = inferencia[inferencia.hipotesis_id == hipotesis_id][
                ["metodo", "estado", "n", "estimacion", "p_valor"]
            ].to_dict("records")
            metodos = [
                {k: None if pd.isna(v) else v for k, v in registro.items()}
                for registro in registros
            ]
        claims.append(
            {
                "claim_id": f"{hipotesis_id.lower()}-{huella}",
                "hipotesis_id": hipotesis_id,
                "hipotesis": mejor.hipotesis,
                "clase_evidencia": clase,
                "estado": "consistente" if estable else "exploratorio",
                "afirmacion": afirmacion,
                "estimacion": mejor.pearson,
                "intervalo_inferior": mejor.pearson_ic_inferior,
                "intervalo_superior": mejor.pearson_ic_superior,
                "unidad": "correlacion",
                "n_efectivo": mejor.n_efectivo,
                "alcance": json.dumps(
                    {
                        "rezago_semanas": int(mejor.rezago_semanas),
                        "predictor": mejor.predictor,
                        "respuesta": mejor.respuesta,
                        "modulos": int(mejor.modulos),
                        "inferencia_complementaria": metodos,
                    },
                    allow_nan=False,
                ),
                "supuestos": json.dumps(
                    [
                        "estacionalidad controlada con seno/coseno",
                        "interceptos de módulo aproximados con indicadores",
                    ]
                ),
                "limitaciones": json.dumps(
                    [
                        "diseño observacional",
                        "clima común reduce n efectivo",
                        "faltan polinización, suelo y nutrición",
                    ]
                ),
                "referencias": json.dumps(REFERENCIAS_HIPOTESIS.get(hipotesis_id, [])),
            }
        )
    return pd.DataFrame(claims)


def sensibilidad_gdd(panel: pd.DataFrame) -> pd.DataFrame:
    """Compara bases térmicas publicadas sin escoger con todo el conjunto."""
    filas = []
    for base in ("gdd_0", "gdd_4_4", "gdd_7", "gdd_8"):
        if base not in panel or "flores_por_planta_muestra" not in panel:
            continue
        muestra = panel[[base, "flores_por_planta_muestra"]].dropna()
        filas.append(
            {
                "temperatura_base_c": float(base.replace("gdd_", "").replace("_", ".")),
                "n": len(muestra),
                "correlacion_floracion": muestra.corr().iloc[0, 1] if len(muestra) >= 3 else np.nan,
                "estado": "hipotesis; seleccionar solo dentro de folds de entrenamiento",
            }
        )
    return pd.DataFrame(filas)


__all__ = [
    "REFERENCIAS_HIPOTESIS",
    "SEMANAS_SOLIDO",
    "DESFASES_SOLIDO",
    "clasificar_hallazgos",
    "hallazgos_matriz",
    "resumen_matriz",
    "generar_claims",
    "sensibilidad_gdd",
]
