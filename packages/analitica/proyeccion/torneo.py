"""Evaluación común y regla auditable champion–challenger."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .componentes import challengers_componentes
from .contratos import ResultadoTorneo
from .fenologico_v1 import backtest_fenologico_v1
from .hibrido_legacy import (
    NOMBRE_MODELO as NOMBRE_MODELO_HIBRIDO,
)
from .hibrido_legacy import (
    backtest_hibrido_v1,
    backtest_macro_legacy_v1,
)
from .metricas import (
    bootstrap_diferencia_wape_pareada,
    metricas_pronostico,
    porcentaje_series_ganadas,
    wape,
)
from .modelos import (
    challenger_combinacion,
    challenger_componentes_publicados,
    challengers_ml,
    challengers_statsforecast,
)

REGLA_PROMOCION = {
    "mejora_relativa_wape": 0.05,
    "mejora_relativa_mase": 0.05,
    "sesgo_absoluto_max_pct": 10,
    "cobertura_p10_p90": [0.75, 0.85],
    "volumen_cubierto_min": 0.90,
    "deterioro_fundo_max": 0.10,
    "campanias_ganadas_min": 2,
    "requiere_sin_fuga": True,
    "requiere_reproducible": True,
    # No es un umbral de desempeño: exige que un modelo que publica plantas, frutos por
    # planta y peso de baya produzca con ellos exactamente el kg que muestra.
    "requiere_identidad_coherente": True,
}


def _identidad_coherente(pareadas: pd.DataFrame, modelo: str, tolerancia: float = 1e-6) -> bool:
    """Si el modelo publica las tres piezas del rendimiento, su producto debe dar su kg.

    Es una comprobación de corrección, no un umbral de desempeño: no exige que el modelo
    acierte más, sino que el número que muestra sea el que sus propios componentes
    producen. Un modelo que no publica componentes propios no se ve afectado.
    """
    filas = pareadas[pareadas.modelo == modelo]
    requeridas = {"plantas", "frutos_por_planta", "peso_baya_g", "p50_kg"}
    if filas.empty or requeridas - set(filas):
        return True
    if "base_plantas" not in filas or filas.base_plantas.isna().all():
        return True
    producto = filas.plantas * filas.frutos_por_planta * filas.peso_baya_g / 1000
    if "probabilidad_cosecha" in filas:
        producto = producto * pd.to_numeric(filas.probabilidad_cosecha, errors="coerce")
    if "factor_asignacion_cosecha" in filas:
        producto = producto * pd.to_numeric(
            filas.factor_asignacion_cosecha, errors="coerce"
        ).fillna(1.0)
    diferencia = (producto - filas.p50_kg).abs() / filas.p50_kg.abs().clip(lower=1.0)
    return bool(diferencia.max() <= tolerancia) if diferencia.notna().any() else True


def _evaluacion_segmentada(predicciones: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    filas = []
    for claves, grupo in predicciones.groupby(["modelo", *columnas], dropna=False):
        grupo = grupo.dropna(subset=["real_kg", "p50_kg"])
        if grupo.empty:
            continue
        clave = claves if isinstance(claves, tuple) else (claves,)
        filas.append(
            {
                "modelo": clave[0],
                **dict(zip(columnas, clave[1:], strict=True)),
                "wape": wape(grupo.real_kg, grupo.p50_kg),
                "n": len(grupo),
                "volumen_real_kg": float(grupo.real_kg.sum()),
            }
        )
    return pd.DataFrame(filas)


def decidir_campeon(
    predicciones: pd.DataFrame,
    metricas: pd.DataFrame,
    *,
    sin_fuga: bool = True,
    reproducible: bool = True,
) -> pd.DataFrame:
    decisiones = []
    # El contrato siempre devuelve las tres bandas, aun si el histórico disponible todavía
    # no alcanza 7–10 semanas. La ausencia de evaluación también es una decisión auditable.
    for banda in ("operativo", "planificacion", "escenario"):
        tabla = metricas[metricas.banda_horizonte == banda]
        base_total = predicciones[
            (predicciones.banda_horizonte == banda) & (predicciones.modelo == "R09_publicado")
        ].copy()
        candidatos = tabla[tabla.modelo != "R09_publicado"].modelo.unique()
        evaluaciones = []
        claves = ["campania", "lote_id", "fecha_emision", "fecha_objetivo"]
        for modelo in candidatos:
            candidato = predicciones[
                (predicciones.banda_horizonte == banda) & (predicciones.modelo == modelo)
            ].copy()
            comunes = base_total[claves].merge(
                candidato[claves].drop_duplicates(), on=claves, how="inner"
            )
            if comunes.empty:
                continue
            base_par = base_total.merge(comunes, on=claves, how="inner")
            cand_par = candidato.merge(comunes, on=claves, how="inner")
            pareadas = pd.concat([base_par, cand_par], ignore_index=True, sort=False)
            m = metricas_pronostico(pareadas)
            b = m[m.modelo == "R09_publicado"]
            c = m[m.modelo == modelo]
            if b.empty or c.empty or not np.isfinite(c.iloc[0].mase):
                continue
            evaluaciones.append(
                {
                    "modelo": modelo,
                    "base": b.iloc[0],
                    "candidato": c.iloc[0],
                    "pareadas": pareadas,
                    "volumen_base_total": float(base_total.real_kg.dropna().abs().sum()),
                }
            )
        if base_total.empty or not evaluaciones:
            decisiones.append(
                {
                    "banda_horizonte": banda,
                    "campeon": "R09_publicado",
                    "challenger": None,
                    "resultado": "retener",
                    "cumple": False,
                    "justificacion": "No existe challenger comparable en este horizonte.",
                }
            )
            continue

        def puntaje(evaluacion):
            base_e, candidato_e = evaluacion["base"], evaluacion["candidato"]
            mejora_w = 1 - candidato_e.wape / base_e.wape if base_e.wape > 0 else -np.inf
            mejora_m = 1 - candidato_e.mase / base_e.mase if base_e.mase > 0 else -np.inf
            volumen = evaluacion["volumen_base_total"]
            cobertura = candidato_e.volumen_real_kg / volumen if volumen else 0
            # Un modelo de nicho no desplaza a uno evaluado sobre el volumen operativo.
            return (cobertura >= 0.90, min(mejora_w, mejora_m), cobertura)

        evaluacion = max(evaluaciones, key=puntaje)
        base, mejor = evaluacion["base"], evaluacion["candidato"]
        pareadas = evaluacion["pareadas"]
        mejora_wape = 1 - mejor.wape / base.wape if base.wape > 0 else -np.inf
        mejora_mase = 1 - mejor.mase / base.mase if base.mase > 0 else -np.inf
        volumen_total = evaluacion["volumen_base_total"]
        cobertura_volumen = (
            min(1.0, float(mejor.volumen_real_kg) / volumen_total) if volumen_total else 0
        )
        diferencia_wape_ic_inferior, diferencia_wape_ic_superior = (
            bootstrap_diferencia_wape_pareada(pareadas, str(mejor.modelo))
        )
        porcentaje_lotes_ganados = porcentaje_series_ganadas(pareadas, str(mejor.modelo))

        camp = _evaluacion_segmentada(pareadas, ["banda_horizonte", "campania"])
        pivot_c = camp.pivot(index="campania", columns="modelo", values="wape")
        camp_ganadas = int(
            (pivot_c.get(mejor.modelo, np.inf) < pivot_c.get("R09_publicado", -np.inf)).sum()
        )
        fundo = _evaluacion_segmentada(pareadas, ["banda_horizonte", "fundo"])
        pivot_f = fundo.pivot(index="fundo", columns="modelo", values="wape")
        if mejor.modelo in pivot_f and "R09_publicado" in pivot_f:
            deterioro = ((pivot_f[mejor.modelo] / pivot_f.R09_publicado) - 1).replace(
                [np.inf, -np.inf], np.nan
            )
            deterioro_max = float(deterioro.max()) if deterioro.notna().any() else np.inf
        else:
            deterioro_max = np.inf
        checks = {
            "mejora_wape": mejora_wape >= 0.05,
            "mejora_mase": mejora_mase >= 0.05,
            "sesgo": abs(mejor.sesgo_pct) <= 10,
            "cobertura_intervalo": 0.75 <= mejor.cobertura_80 <= 0.85,
            "volumen": cobertura_volumen >= 0.90,
            "fundo": deterioro_max <= 0.10,
            "campanias": camp_ganadas >= 2,
            "sin_fuga": sin_fuga,
            "reproducible": reproducible,
            "identidad_componentes_coherente": _identidad_coherente(pareadas, str(mejor.modelo)),
        }
        checks = {nombre: bool(valor) for nombre, valor in checks.items()}
        cumple = all(checks.values())
        decisiones.append(
            {
                "banda_horizonte": banda,
                "campeon": str(mejor.modelo) if cumple else "R09_publicado",
                "challenger": str(mejor.modelo),
                "resultado": "promover" if cumple else "retener",
                "cumple": cumple,
                "mejora_wape": mejora_wape,
                "mejora_mase": mejora_mase,
                "cobertura_volumen": cobertura_volumen,
                "porcentaje_lotes_ganados": porcentaje_lotes_ganados,
                "diferencia_wape_ic_inferior": diferencia_wape_ic_inferior,
                "diferencia_wape_ic_superior": diferencia_wape_ic_superior,
                "campanias_ganadas": camp_ganadas,
                "deterioro_fundo_max": deterioro_max,
                "checks": json.dumps(checks, ensure_ascii=False),
                "justificacion": (
                    f"Promoción aprobada frente a R09: {mejor.modelo}."
                    if cumple
                    else "Sin mejora estadísticamente comprobada; R09 continúa como campeón."
                ),
            }
        )
    return pd.DataFrame(decisiones)


def _familia_componentes(contexto: dict) -> pd.DataFrame:
    return challengers_componentes(
        contexto["backtest"],
        panel_asof=contexto.get("panel_asof"),
        diagnostico_montecarlo=contexto.get("diagnostico_montecarlo", False),
    )


def _familia_ml(contexto: dict) -> pd.DataFrame:
    return challengers_ml(contexto["backtest"])


def _familia_statsforecast(contexto: dict) -> pd.DataFrame:
    return challengers_statsforecast(contexto["backtest"], contexto["cosecha"])


def _familia_fenologico_v1(contexto: dict) -> pd.DataFrame:
    datos = contexto.get("datos")
    if datos is None:
        return pd.DataFrame()
    emisiones = contexto["backtest"][["campania", "fecha_emision"]].drop_duplicates()
    resultado = backtest_fenologico_v1(
        datos,
        emisiones,
        max_cortes=int(contexto.get("fenologico_max_cortes", 8) or 8),
        usar_mixedlm=bool(contexto.get("fenologico_usar_mixedlm", False)),
    )
    contexto["evidencia_features"] = resultado.evidencia_features
    contexto["advertencias_fenologico"] = resultado.advertencias
    return resultado.predicciones


def _familia_hibrido_legacy(contexto: dict) -> pd.DataFrame:
    """Replay del híbrido legacy-residual sobre los mismos cortes del torneo."""

    datos = contexto.get("datos")
    if datos is None:
        return pd.DataFrame()
    emisiones = contexto["backtest"][["campania", "fecha_emision"]].drop_duplicates()
    partes = []
    for campania in sorted(emisiones.campania.dropna().astype(str).unique()):
        parte_emisiones = emisiones[emisiones.campania.astype(str).eq(campania)]
        predicciones, advertencias = backtest_hibrido_v1(
            datos,
            parte_emisiones,
            campania=campania,
            horizonte_semanas=int(contexto.get("horizonte_semanas", 10) or 10),
            minimo_entrenamiento=int(contexto.get("hibrido_minimo_entrenamiento", 30) or 30),
            max_cortes=int(contexto.get("hibrido_max_cortes", 8) or 8),
        )
        contexto.setdefault("advertencias_hibrido", []).extend(
            [f"{campania}: {aviso}" for aviso in advertencias]
        )
        if not predicciones.empty:
            partes.append(predicciones)
    return pd.concat(partes, ignore_index=True, sort=False) if partes else pd.DataFrame()


def _familia_macro_legacy(contexto: dict) -> pd.DataFrame:
    """Baseline matemático de la macro; no es la emisión R09 publicada."""

    datos = contexto.get("datos")
    if datos is None:
        return pd.DataFrame()
    emisiones = contexto["backtest"][["campania", "fecha_emision"]].drop_duplicates()
    partes = []
    for campania in sorted(emisiones.campania.dropna().astype(str).unique()):
        parte_emisiones = emisiones[emisiones.campania.astype(str).eq(campania)]
        predicciones, advertencias = backtest_macro_legacy_v1(
            datos,
            parte_emisiones,
            campania=campania,
            horizonte_semanas=int(contexto.get("horizonte_semanas", 10) or 10),
            max_cortes=int(contexto.get("hibrido_max_cortes", 8) or 8),
        )
        contexto.setdefault("advertencias_macro_legacy", []).extend(
            [f"{campania}: {aviso}" for aviso in advertencias]
        )
        if not predicciones.empty:
            partes.append(predicciones)
    return pd.concat(partes, ignore_index=True, sort=False) if partes else pd.DataFrame()


# Alta de una familia challenger: una entrada acá, sin tocar el cuerpo de `ejecutar_torneo`.
# `aviso_vacia` es obligatorio a propósito — una familia que no emite filas debe decir por
# qué, o su ausencia en el ranking se lee como que compitió y perdió.
FAMILIAS_CHALLENGER: tuple[dict, ...] = (
    {
        "clave": "macro_legacy",
        "funcion": _familia_macro_legacy,
        "aviso_vacia": (
            "MacroLegacy_v1 no emitió filas: faltan historia de cosecha, poda o lotes "
            "suficientes para calibrar la curva legacy as-of."
        ),
    },
    {
        "clave": "hibrido_legacy",
        "funcion": _familia_hibrido_legacy,
        "aviso_vacia": (
            f"{NOMBRE_MODELO_HIBRIDO} no emitió filas: faltan historia de cosecha, poda o "
            "parámetros suficientes para calibrar la curva legacy as-of."
        ),
    },
    {
        "clave": "fenologico_v1",
        "funcion": _familia_fenologico_v1,
        "aviso_vacia": (
            "FenologicoComponentes_v1 no emitió filas: faltan cosecha real resuelta, "
            "maestro de lotes o historia as-of suficiente."
        ),
    },
    {
        "clave": "componentes",
        "funcion": _familia_componentes,
        "aviso_vacia": (
            "La familia de componentes no emitió filas: historia resuelta insuficiente "
            "antes de las emisiones evaluadas."
        ),
    },
    {
        "clave": "ml",
        "funcion": _familia_ml,
        "aviso_vacia": (
            "Las familias de corrección residual no emitieron filas: entrenamiento "
            "insuficiente antes de las emisiones evaluadas."
        ),
    },
    {
        "clave": "statsforecast",
        "funcion": _familia_statsforecast,
        "aviso_vacia": "Los modelos de serie no emitieron filas para estas emisiones.",
    },
)


def ejecutar_torneo(
    backtest: pd.DataFrame,
    cosecha: pd.DataFrame,
    *,
    incluir_ml: bool = True,
    incluir_statsforecast: bool = True,
    incluir_componentes: bool = True,
    incluir_fenologico_v1: bool = True,
    incluir_macro_legacy: bool = True,
    incluir_hibrido_legacy: bool = True,
    fenologico_usar_mixedlm: bool = False,
    datos=None,
    panel_asof: pd.DataFrame | None = None,
    diagnostico_montecarlo: bool = False,
    sin_fuga: bool = True,
    reproducible: bool = True,
    fenologico_max_cortes: int = 8,
    horizonte_semanas: int = 10,
) -> ResultadoTorneo:
    partes = [backtest, challenger_componentes_publicados(backtest)]
    advertencias: list[str] = []
    contexto = {
        "backtest": backtest,
        "cosecha": cosecha,
        "panel_asof": panel_asof,
        "diagnostico_montecarlo": diagnostico_montecarlo,
        "datos": datos,
        "fenologico_max_cortes": fenologico_max_cortes,
        "fenologico_usar_mixedlm": fenologico_usar_mixedlm,
        "horizonte_semanas": horizonte_semanas,
        "hibrido_minimo_entrenamiento": 30,
        "hibrido_max_cortes": fenologico_max_cortes,
    }
    habilitadas = {
        "macro_legacy": incluir_macro_legacy,
        "hibrido_legacy": incluir_hibrido_legacy,
        "fenologico_v1": incluir_fenologico_v1,
        "componentes": incluir_componentes,
        "ml": incluir_ml,
        "statsforecast": incluir_statsforecast,
    }
    for familia in FAMILIAS_CHALLENGER:
        if not habilitadas.get(familia["clave"], False):
            continue
        try:
            parte = familia["funcion"](contexto)
        except RuntimeError as exc:
            # Dependencia opcional ausente o backend no disponible: se anota y se sigue. El
            # torneo no debe caerse porque falte una familia.
            advertencias.append(str(exc))
            continue
        if parte.empty:
            advertencias.append(familia["aviso_vacia"])
            continue
        partes.append(parte)
        advertencias.extend(contexto.pop("advertencias_fenologico", []))
        advertencias.extend(contexto.pop("advertencias_hibrido", []))
        advertencias.extend(contexto.pop("advertencias_macro_legacy", []))

    if incluir_componentes and (panel_asof is None or panel_asof.empty):
        advertencias.append(
            "La familia de componentes corrió sin panel as-of: solo usó calendario, plantas "
            "y rezagos propios, sin censos fenológicos ni clima."
        )
    predicciones = pd.concat([p for p in partes if not p.empty], ignore_index=True)
    combinacion = challenger_combinacion(predicciones)
    if not combinacion.empty:
        predicciones = pd.concat([predicciones, combinacion], ignore_index=True, sort=False)
    metricas = metricas_pronostico(predicciones)
    decisiones = decidir_campeon(
        predicciones, metricas, sin_fuga=sin_fuga, reproducible=reproducible
    )
    return ResultadoTorneo(
        predicciones,
        metricas,
        decisiones,
        advertencias,
        contexto.get("evidencia_features", pd.DataFrame()),
    )
