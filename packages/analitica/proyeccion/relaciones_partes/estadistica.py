"""Evaluación estadística de relaciones y matrices."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class Hipotesis:
    codigo: str
    enunciado: str
    predictor: str
    respuesta: str
    rezagos: tuple[int, ...]
    clase_maxima: str = "temporal"


HIPOTESIS = (
    Hipotesis(
        "H1",
        "Poda y acumulación térmica preceden a la floración.",
        "gdd_4_4",
        "flores_por_planta_muestra",
        tuple(range(0, 9)),
    ),
    Hipotesis(
        "H2",
        "Flores y cuajado preceden al número de frutos observados.",
        "tasa_cuajo_observada",
        "frutos_por_planta_muestra",
        tuple(range(0, 7)),
    ),
    Hipotesis(
        "H3",
        "La distribución E1–E5 anticipa la semana de cosecha.",
        "prop_e5",
        "kg_ha",
        tuple(range(0, 11)),
    ),
    Hipotesis(
        "H4",
        "El diámetro y estado de baya anticipan el peso cosechado.",
        "diametro_baya_mm",
        "peso_real_g",
        tuple(range(0, 7)),
    ),
    Hipotesis(
        "H5",
        "Plantas, frutos por planta y peso descomponen el volumen.",
        "kg_componentes_muestra",
        "kg",
        (0, 1, 2),
    ),
    Hipotesis(
        "H6",
        "Clima y riego se asocian con transición fenológica y peso.",
        "dpv_kpa",
        "velocidad_estado",
        tuple(range(0, 7)),
    ),
    Hipotesis(
        "H6_R",
        "Riego aplicado se asocia con el peso de baya.",
        "lamina_mm",
        "peso_real_g",
        tuple(range(0, 7)),
    ),
)


# ── Matriz completa de relaciones ────────────────────────────────────────────
#
# Las hipótesis de arriba son las siete preguntas que el equipo agronómico formuló de
# antemano. La matriz es lo contrario: cruza todo con todo para **descubrir** relaciones que
# nadie había pensado. Son dos cosas distintas y se reportan por separado, porque una
# hipótesis previa y un hallazgo de un barrido de cientos de combinaciones no tienen el
# mismo valor probatorio aunque salga el mismo número.

# Lo que se quiere explicar, y a qué parte del rendimiento pertenece.
RESPUESTAS_MATRIZ = {
    "flores_por_planta_muestra": "frutos",
    "frutos_por_planta_muestra": "frutos",
    "tasa_cuajo_observada": "frutos",
    "velocidad_estado": "frutos",
    "indice_estado": "frutos",
    "peso_real_g": "peso",
    "diametro_baya_mm": "peso",
    "kg_ha": "kilos",
}

# Variables del propio cultivo, en el orden de la cadena. Solo se cruzan contra respuestas
# **posteriores** en el ciclo: preguntar si el peso de la baya explica las ramas sería
# invertir el tiempo biológico.
PREDICTORES_CULTIVO = [
    "ramas_por_planta",
    "proporcion_ramas_gruesas",
    "diametro_rama_mm",
    "brotes_por_planta",
    "yemas_por_planta",
    "proporcion_yemas_abiertas",
    "flores_por_planta_muestra",
    "tasa_cuajo_observada",
    "frutos_por_planta_muestra",
    "indice_estado",
    "prop_e1",
    "prop_e5",
    "diametro_baya_mm",
]

# Orden del ciclo, para no cruzar hacia atrás en el tiempo.
ORDEN_CICLO = {
    "ramas_por_planta": 1,
    "proporcion_ramas_gruesas": 1,
    "diametro_rama_mm": 1,
    "brotes_por_planta": 2,
    "yemas_por_planta": 3,
    "proporcion_yemas_abiertas": 3,
    "flores_por_planta_muestra": 4,
    "tasa_cuajo_observada": 5,
    "frutos_por_planta_muestra": 6,
    "indice_estado": 7,
    "prop_e1": 7,
    "prop_e5": 7,
    "velocidad_estado": 7,
    "diametro_baya_mm": 8,
    "peso_real_g": 9,
    "kg_ha": 10,
}

# Condiciones externas. Se cruzan contra todas las respuestas, sin restricción de orden:
# el clima actúa en cualquier momento del ciclo.
PREDICTORES_EXTERNOS = [
    "temp_min",
    "temp_max",
    "temp_media",
    "humedad",
    "dpv_kpa",
    "eto",
    "radiacion",
    "lluvia",
    "gdd_4_4",
    "lamina_mm",
    "agua_m3",
    "reposicion_pct",
]

REZAGOS_MATRIZ = tuple(range(0, 9))


def _residuos_controles(tabla: pd.DataFrame, variable: str) -> np.ndarray:
    semana = tabla.fecha_semana.dt.isocalendar().week.astype(float)
    controles = pd.DataFrame(
        {
            "intercepto": 1.0,
            "semana_sin": np.sin(2 * np.pi * semana / 52.18),
            "semana_cos": np.cos(2 * np.pi * semana / 52.18),
        },
        index=tabla.index,
    )
    if "modulo" in tabla:
        controles = pd.concat(
            [controles, pd.get_dummies(tabla.modulo, prefix="mod", drop_first=True, dtype=float)],
            axis=1,
        )
    x = controles.to_numpy(float)
    y = tabla[variable].to_numpy(float)
    return y - x @ np.linalg.lstsq(x, y, rcond=None)[0]


def _p_agrupado(
    residuos_x: np.ndarray, residuos_y: np.ndarray, grupos: pd.DataFrame
) -> tuple[float, int]:
    """Significancia de la correlación parcial con errores agrupados."""
    x = np.asarray(residuos_x, dtype=float)
    y = np.asarray(residuos_y, dtype=float)
    sxx = float(x @ x)
    if not np.isfinite(sxx) or sxx <= 0:
        return 1.0, 0
    beta = float(x @ y) / sxx
    e = y - beta * x
    peor_p, peor_gl = 0.0, 0
    for columna in grupos.columns:
        codigos = pd.factorize(grupos[columna])[0]
        n_grupos = int(codigos.max()) + 1 if len(codigos) else 0
        if n_grupos < 3:
            continue
        puntajes = np.bincount(codigos, weights=x * e, minlength=n_grupos)
        meat = float(puntajes @ puntajes)
        ajuste = n_grupos / max(n_grupos - 1, 1)
        varianza = ajuste * meat / (sxx**2)
        if not np.isfinite(varianza) or varianza <= 0:
            continue
        gl = n_grupos - 1
        p = float(2 * stats.t.sf(abs(beta) / np.sqrt(varianza), gl))
        if p >= peor_p:
            peor_p, peor_gl = p, gl
    if peor_gl == 0:
        return 1.0, 0
    return min(max(peor_p, 0.0), 1.0), peor_gl


def _placebo_parcial(
    orden: pd.DataFrame, predictor: str, respuesta: str, rezago: int, grupo: str, minimo: int
) -> float:
    """El placebo medido con la misma vara que la estimación: correlación parcial."""
    futuro = orden.groupby(grupo)[predictor].shift(-(rezago + 1))
    columnas = ["fecha_semana", respuesta] + (["modulo"] if "modulo" in orden else [])
    m = orden[columnas].assign(x=futuro).dropna(subset=["x", respuesta, "fecha_semana"])
    if len(m) < minimo or m.x.nunique() < 3 or m[respuesta].nunique() < 3:
        return float("nan")
    m = m.rename(columns={respuesta: "y"})
    r = float(np.corrcoef(_residuos_controles(m, "x"), _residuos_controles(m, "y"))[0, 1])
    return r if np.isfinite(r) else float("nan")


def _ic_bootstrap_bloques(tabla: pd.DataFrame, repeticiones: int = 300) -> tuple[float, float]:
    t = tabla[["fecha_semana", "x", "y"]].dropna().copy()
    t["xx"], t["yy"], t["xy"] = t.x * t.x, t.y * t.y, t.x * t.y
    suficientes = (
        t.groupby("fecha_semana", sort=True)
        .agg(
            n=("x", "size"),
            sx=("x", "sum"),
            sy=("y", "sum"),
            sxx=("xx", "sum"),
            syy=("yy", "sum"),
            sxy=("xy", "sum"),
        )
        .to_numpy(float)
    )
    n_fechas = len(suficientes)
    if n_fechas < 5:
        return np.nan, np.nan
    longitud = min(3, n_fechas)
    bloques = np.array(
        [suficientes[i : i + longitud].sum(axis=0) for i in range(n_fechas - longitud + 1)]
    )
    rng = np.random.default_rng(42)
    valores = []
    for _ in range(repeticiones):
        elegidos = rng.integers(0, len(bloques), size=int(np.ceil(n_fechas / longitud)))
        n, sx, sy, sxx, syy, sxy = bloques[elegidos].sum(axis=0)
        numerador = n * sxy - sx * sy
        denominador = np.sqrt((n * sxx - sx * sx) * (n * syy - sy * sy))
        if denominador > 0:
            valores.append(numerador / denominador)
    return tuple(map(float, np.quantile(valores, [0.025, 0.975]))) if valores else (np.nan, np.nan)


def _bh(pvalores: pd.Series) -> pd.Series:
    p = pvalores.fillna(1).to_numpy(float)
    orden = np.argsort(p)
    ajustado = np.empty(len(p))
    ordenados = p[orden] * len(p) / np.arange(1, len(p) + 1)
    ordenados = np.minimum.accumulate(ordenados[::-1])[::-1].clip(0, 1)
    ajustado[orden] = ordenados
    return pd.Series(ajustado, index=pvalores.index)


def evaluar_relaciones(panel: pd.DataFrame, minimo_n: int = 25) -> pd.DataFrame:
    resultados = []
    for hipotesis in HIPOTESIS:
        if hipotesis.predictor not in panel or hipotesis.respuesta not in panel:
            continue
        orden = panel.sort_values(["lote_id", "fecha_semana"]).copy()
        for rezago in hipotesis.rezagos:
            orden["x"] = orden.groupby("lote_id")[hipotesis.predictor].shift(rezago)
            muestra = orden.dropna(subset=["x", hipotesis.respuesta, "fecha_semana"]).copy()
            muestra = muestra.rename(columns={hipotesis.respuesta: "y"})
            if len(muestra) < minimo_n or muestra.x.nunique() < 3 or muestra.y.nunique() < 3:
                continue
            pearson, p_pearson = stats.pearsonr(muestra.x, muestra.y)
            spearman, p_spearman = stats.spearmanr(muestra.x, muestra.y)
            rx = _residuos_controles(muestra, "x")
            ry = _residuos_controles(muestra, "y")
            parcial = float(np.corrcoef(rx, ry)[0, 1])
            inferior, superior = _ic_bootstrap_bloques(muestra)
            por_modulo = (
                muestra.groupby("modulo")
                .apply(
                    lambda g: (
                        g.x.corr(g.y)
                        if len(g) >= 8 and g.x.nunique() > 1 and g.y.nunique() > 1
                        else np.nan
                    ),
                    include_groups=False,
                )
                .dropna()
                if "modulo" in muestra
                else pd.Series(dtype=float)
            )
            # Placebo: una señal futura no debería parecer más fuerte que la rezagada.
            futuro = orden.groupby("lote_id")[hipotesis.predictor].shift(-(rezago + 1))
            placebo_m = pd.DataFrame({"x": futuro, "y": orden[hipotesis.respuesta]}).dropna()
            placebo = placebo_m.x.corr(placebo_m.y) if len(placebo_m) >= minimo_n else np.nan
            resultados.append(
                {
                    "hipotesis_id": hipotesis.codigo,
                    "hipotesis": hipotesis.enunciado,
                    "predictor": hipotesis.predictor,
                    "respuesta": hipotesis.respuesta,
                    "rezago_semanas": rezago,
                    "n": len(muestra),
                    "n_efectivo": int(muestra.fecha_semana.nunique()),
                    "pearson": float(pearson),
                    "pearson_ic_inferior": inferior,
                    "pearson_ic_superior": superior,
                    "p_pearson": float(p_pearson),
                    "spearman": float(spearman),
                    "p_spearman": float(p_spearman),
                    "correlacion_parcial": parcial,
                    "placebo_futuro": placebo,
                    "modulos": int(muestra.modulo.nunique()) if "modulo" in muestra else 0,
                    "estabilidad_signo_modulo": float(
                        (np.sign(por_modulo) == np.sign(pearson)).mean()
                    )
                    if len(por_modulo)
                    else np.nan,
                    "clase_evidencia": "temporal" if rezago > 0 else "correlacional",
                }
            )
    salida = pd.DataFrame(resultados)
    if not salida.empty:
        salida["p_ajustado_bh"] = _bh(salida.p_pearson)
        salida["placebo_supera_estimacion"] = salida.placebo_futuro.abs() > salida.pearson.abs()
    return salida


def _pares_matriz() -> list[tuple[str, str, str]]:
    """Todos los cruces que tienen sentido biológico, como (predictor, respuesta, tipo).

    Del cultivo solo se cruza hacia adelante en el ciclo: las ramas pueden explicar las
    flores, pero preguntar si el peso de la baya explica las ramas es preguntar si el futuro
    causa el pasado. Las externas se cruzan contra todo, porque el clima actúa en cualquier
    momento.
    """
    pares = []
    for respuesta in RESPUESTAS_MATRIZ:
        orden_respuesta = ORDEN_CICLO.get(respuesta, 99)
        for predictor in PREDICTORES_CULTIVO:
            if predictor == respuesta:
                continue
            if ORDEN_CICLO.get(predictor, 0) >= orden_respuesta:
                continue
            pares.append((predictor, respuesta, "cultivo"))
        for predictor in PREDICTORES_EXTERNOS:
            pares.append((predictor, respuesta, "externa"))
    return pares


def _efecto_practico(
    muestra: pd.DataFrame, residuos_x: np.ndarray, residuos_y: np.ndarray
) -> dict[str, float]:
    """Traduce la correlación a un efecto en las unidades reales de cada variable."""
    varianza = float(np.var(residuos_x))
    if varianza <= 0:
        return {
            "pendiente": np.nan,
            "efecto_rango_iqr": np.nan,
            "iqr_predictor": np.nan,
            "mediana_respuesta": np.nan,
        }
    pendiente = float(np.cov(residuos_x, residuos_y, ddof=0)[0, 1] / varianza)
    x = muestra.x.astype(float)
    iqr = float(x.quantile(0.75) - x.quantile(0.25))
    return {
        "pendiente": pendiente,
        "efecto_rango_iqr": pendiente * iqr,
        "iqr_predictor": iqr,
        "mediana_respuesta": float(muestra.y.astype(float).median()),
    }


def evaluar_matriz_relaciones(
    panel: pd.DataFrame,
    minimo_n: int = 25,
    minimo_semanas: int = 8,
) -> pd.DataFrame:
    """Cruza cada variable con cada respuesta y cada desfase, y corrige la multiplicidad."""
    if panel.empty:
        return pd.DataFrame()

    orden = panel.sort_values(["lote_id", "fecha_semana"]).copy()
    resultados = []
    for predictor, respuesta, tipo in _pares_matriz():
        if predictor not in orden or respuesta not in orden:
            continue
        for rezago in REZAGOS_MATRIZ:
            orden["x"] = orden.groupby("lote_id")[predictor].shift(rezago)
            muestra = orden.dropna(subset=["x", respuesta, "fecha_semana"]).copy()
            muestra = muestra.rename(columns={respuesta: "y"})
            semanas = muestra.fecha_semana.nunique()
            # El tamaño que cuenta es el de semanas distintas, no el de filas.
            if (
                len(muestra) < minimo_n
                or semanas < minimo_semanas
                or muestra.x.nunique() < 3
                or muestra.y.nunique() < 3
            ):
                continue
            pearson, p_crudo = stats.pearsonr(muestra.x, muestra.y)
            if not np.isfinite(pearson):
                continue
            residuos_x = _residuos_controles(muestra, "x")
            residuos_y = _residuos_controles(muestra, "y")
            parcial = float(np.corrcoef(residuos_x, residuos_y)[0, 1])
            p_pearson, gl = _p_agrupado(
                residuos_x, residuos_y, muestra[["fecha_semana", "lote_id"]]
            )
            placebo = _placebo_parcial(orden, predictor, respuesta, rezago, "lote_id", minimo_n)
            efecto = _efecto_practico(muestra, residuos_x, residuos_y)
            resultados.append(
                {
                    "predictor": predictor,
                    "respuesta": respuesta,
                    "tipo_predictor": tipo,
                    "componente": RESPUESTAS_MATRIZ[respuesta],
                    "rezago_semanas": rezago,
                    "n": len(muestra),
                    "n_efectivo": int(semanas),
                    "grados_libertad": int(gl),
                    "modulos": int(muestra.modulo.nunique()) if "modulo" in muestra else 0,
                    "pearson": float(pearson),
                    "p_crudo_sin_agrupar": float(p_crudo),
                    "p_pearson": float(p_pearson),
                    "correlacion_parcial": parcial,
                    "placebo_futuro": placebo,
                    **efecto,
                }
            )

    salida = pd.DataFrame(resultados)
    if salida.empty:
        return salida
    desfases = salida.groupby(["predictor", "respuesta"]).rezago_semanas.transform("size")
    salida["desfases_probados"] = desfases
    salida["p_seleccion_desfase"] = 1 - np.power(1 - salida.p_pearson.clip(0, 1), desfases)
    salida["p_ajustado_bh"] = _bh(salida.p_seleccion_desfase)
    salida["placebo_supera_estimacion"] = (
        salida.placebo_futuro.abs() > salida.correlacion_parcial.abs()
    ).fillna(False)
    salida["sobrevive"] = (
        (salida.p_ajustado_bh < 0.05)
        & ~salida.placebo_supera_estimacion
        & (salida.correlacion_parcial.abs() >= 0.1)
    )
    return salida.sort_values("p_ajustado_bh").reset_index(drop=True)


__all__ = [
    "Hipotesis",
    "HIPOTESIS",
    "RESPUESTAS_MATRIZ",
    "PREDICTORES_CULTIVO",
    "ORDEN_CICLO",
    "PREDICTORES_EXTERNOS",
    "REZAGOS_MATRIZ",
    "evaluar_relaciones",
    "evaluar_matriz_relaciones",
]
