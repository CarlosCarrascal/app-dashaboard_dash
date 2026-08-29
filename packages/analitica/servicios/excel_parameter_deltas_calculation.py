"""Cálculo y evaluación as-of del screening de deltas Excel."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from .excel_parameter_deltas_io import cargar_snapshots, inventariar_libros
from .excel_parameter_deltas_normalization import FUNDOS, PARAMETROS
from .small_data import cargar_universo_lote

SEMANA_MAX_DESARROLLO = 30
SEMANAS_HOLDOUT = (31, 32, 33)
ROOT_DEFAULT = Path(r"C:\Users\CCARRASCAL\Downloads\Proyecciones")
RUN_ID_DEFAULT = 76
CAMPANIA_DEFAULT = "C2026"
FEATURE_SETS: dict[str, tuple[str, ...]] = {
    "sin_correccion": (),
    "amplitud": (
        "delta_log_n_shrunk",
        "delta_log_a_shrunk",
        "lotes_agregados_frac_shrunk",
    ),
    "calendario": (
        "delta_x_dias_shrunk",
        "delta_o_dias_shrunk",
        "delta_fepas1_dias_shrunk",
    ),
    "compacto": (
        "delta_log_n_shrunk",
        "delta_fepas1_dias_shrunk",
        "lotes_agregados_frac_shrunk",
    ),
    "combinado": (
        "delta_log_n_shrunk",
        "delta_log_a_shrunk",
        "delta_x_dias_shrunk",
        "delta_fepas1_dias_shrunk",
        "lotes_agregados_frac_shrunk",
        "lotes_retirados_frac_shrunk",
    ),
}
FEATURES_CRUDAS = (
    "delta_log_n",
    "delta_log_a",
    "delta_x_dias",
    "delta_o_dias",
    "delta_b_miles",
    "delta_fepas1_dias",
    "delta_calendario_dias",
    "lotes_agregados_frac",
    "lotes_retirados_frac",
    "share_parametros_cambiados",
    "share_calendario_cambiado",
)


@dataclass(frozen=True)
class Configuracion:
    feature_set: str
    alpha: float
    shrink_features: float
    shrink_prediccion: float
    clip_log: float

    @property
    def id(self) -> str:
        return (
            f"{self.feature_set}-a{self.alpha:g}-kf{self.shrink_features:g}-"
            f"kp{self.shrink_prediccion:g}-c{self.clip_log:g}"
        )


def _mediana_finita(valores: pd.Series | np.ndarray) -> float:
    serie = pd.Series(valores, dtype=float).replace([np.inf, -np.inf], np.nan).dropna()
    return float(serie.median()) if len(serie) else 0.0


def calcular_delta_snapshot(
    anterior: pd.DataFrame,
    actual: pd.DataFrame,
    *,
    semana_anterior: int,
    semana_actual: int,
    fundo_operativo: str,
) -> dict[str, object]:
    """Resume el cambio experto entre dos snapshots ya disponibles al corte."""

    prev = anterior.set_index("clave_lote", drop=False)
    curr = actual.set_index("clave_lote", drop=False)
    comunes = prev.index.intersection(curr.index)
    agregados = curr.index.difference(prev.index)
    retirados = prev.index.difference(curr.index)
    if not len(curr):
        raise ValueError("Snapshot actual sin lotes")
    p = prev.loc[comunes]
    c = curr.loc[comunes]
    xcols = ["X1", "X2", "X3"]
    ocols = ["O1", "O2", "O3"]
    ncols = ["N1", "N2", "N3"]
    acols = ["A1", "A2", "A3"]
    bcols = ["B1", "B2", "B3"]
    eps = 1e-6

    def media_fila(tabla: pd.DataFrame, cols: list[str]) -> pd.Series:
        return tabla[cols].apply(pd.to_numeric, errors="coerce").mean(axis=1)

    n_prev = p[ncols].apply(pd.to_numeric, errors="coerce").clip(lower=0).sum(axis=1)
    n_curr = c[ncols].apply(pd.to_numeric, errors="coerce").clip(lower=0).sum(axis=1)
    a_prev = media_fila(p, acols).clip(lower=eps)
    a_curr = media_fila(c, acols).clip(lower=eps)
    fepas = sorted(
        set(col for col in p.columns if re.fullmatch(r"FePas\d+", col))
        & set(col for col in c.columns if re.fullmatch(r"FePas\d+", col)),
        key=lambda x: int(x[5:]),
    )
    calendario_deltas = []
    for columna in fepas:
        dias = (pd.to_datetime(c[columna]) - pd.to_datetime(p[columna])).dt.days
        calendario_deltas.extend(pd.to_numeric(dias, errors="coerce").dropna().tolist())
    fepas1 = (
        (pd.to_datetime(c["FePas1"]) - pd.to_datetime(p["FePas1"])).dt.days
        if "FePas1" in c and "FePas1" in p
        else pd.Series(dtype=float)
    )
    parametros_prev = p[list(PARAMETROS)].apply(pd.to_numeric, errors="coerce")
    parametros_curr = c[list(PARAMETROS)].apply(pd.to_numeric, errors="coerce")
    cambio_param = (parametros_curr - parametros_prev).abs().gt(1e-9).any(axis=1)
    cambio_cal = pd.Series(False, index=comunes)
    for columna in fepas:
        cambio_cal |= pd.to_datetime(c[columna]).ne(pd.to_datetime(p[columna]))
    return {
        "semana_emision": int(semana_actual),
        "semana_emision_anterior": int(semana_anterior),
        "gap_emisiones": int(semana_actual - semana_anterior),
        "semana_objetivo": int(semana_actual + 1),
        "fundo_operativo": fundo_operativo,
        "n_actual": int(len(curr)),
        "n_anterior": int(len(prev)),
        "n_comunes": int(len(comunes)),
        "n_agregados": int(len(agregados)),
        "n_retirados": int(len(retirados)),
        "delta_x_dias": _mediana_finita(media_fila(c, xcols) - media_fila(p, xcols)),
        "delta_o_dias": _mediana_finita(media_fila(c, ocols) - media_fila(p, ocols)),
        "delta_log_n": _mediana_finita(np.log((n_curr + eps) / (n_prev + eps))),
        "delta_log_a": _mediana_finita(np.log((a_curr + eps) / (a_prev + eps))),
        "delta_b_miles": 1000.0 * _mediana_finita(media_fila(c, bcols) - media_fila(p, bcols)),
        "delta_fepas1_dias": _mediana_finita(fepas1),
        "delta_calendario_dias": _mediana_finita(calendario_deltas),
        "lotes_agregados_frac": float(len(agregados) / max(len(curr), 1)),
        "lotes_retirados_frac": float(len(retirados) / max(len(prev), 1)),
        "share_parametros_cambiados": float(cambio_param.mean()) if len(cambio_param) else 0.0,
        "share_calendario_cambiado": float(cambio_cal.mean()) if len(cambio_cal) else 0.0,
    }


def construir_deltas(
    manifest: pd.DataFrame,
    snapshots: Mapping[tuple[int, str], pd.DataFrame],
) -> pd.DataFrame:
    filas: list[dict[str, object]] = []
    for fundo in FUNDOS:
        semanas = sorted(
            int(s) for s in manifest.loc[manifest.fundo_operativo.eq(fundo), "semana_emision"]
        )
        for actual in semanas[1:]:
            anterior = max(s for s in semanas if s < actual)
            filas.append(
                calcular_delta_snapshot(
                    snapshots[(anterior, fundo)],
                    snapshots[(actual, fundo)],
                    semana_anterior=anterior,
                    semana_actual=actual,
                    fundo_operativo=fundo,
                )
            )
    return (
        pd.DataFrame(filas)
        .sort_values(["semana_objetivo", "fundo_operativo"], kind="stable")
        .reset_index(drop=True)
    )


def aplicar_shrinkage_features(tabla: pd.DataFrame, k: float) -> pd.DataFrame:
    salida = tabla.copy()
    for _semana, indices in salida.groupby("semana_emision", sort=True).groups.items():
        bloque = salida.loc[indices]
        pesos = bloque.n_comunes.clip(lower=1).astype(float)
        for feature in FEATURES_CRUDAS:
            valores = pd.to_numeric(bloque[feature], errors="coerce").fillna(0.0)
            global_semana = float(np.average(valores, weights=pesos))
            confianza = pesos / (pesos + float(k))
            salida.loc[indices, f"{feature}_shrunk"] = (
                confianza * valores + (1.0 - confianza) * global_semana
            )
    return salida


def construir_contrato(
    deltas: pd.DataFrame,
    *,
    run_id: int = RUN_ID_DEFAULT,
    campania: str = CAMPANIA_DEFAULT,
) -> pd.DataFrame:
    universo = cargar_universo_lote(run_id=run_id, campania=campania)
    base = universo.groupby(["campania", "semana_objetivo", "fundo_operativo"], as_index=False).agg(
        macro_kg=("macro_kg", "sum"),
        real_kg=("real_kg", "sum"),
        r09_kg=("r09_kg", "sum"),
        r09_disponible=("r09_emitio", "all"),
        n_lotes_macro=("lote_id", "nunique"),
    )
    contrato = deltas.merge(
        base,
        on=["semana_objetivo", "fundo_operativo"],
        how="inner",
        validate="one_to_one",
    )
    contrato["residuo_objetivo"] = np.log1p(contrato.real_kg.clip(lower=0.0)) - np.log1p(
        contrato.macro_kg.clip(lower=0.0)
    )
    contrato["r09_disponible"] = contrato.r09_disponible.fillna(False).astype(bool)
    return contrato.sort_values(["semana_objetivo", "fundo_operativo"], kind="stable").reset_index(
        drop=True
    )


def _ajustar_predecir(
    entrenamiento: pd.DataFrame,
    objetivo: pd.DataFrame,
    config: Configuracion,
) -> tuple[np.ndarray, int]:
    columnas = list(FEATURE_SETS[config.feature_set])
    if not columnas:
        return objetivo.macro_kg.to_numpy(float), 0
    if len(entrenamiento) < 8 or entrenamiento.semana_objetivo.nunique() < 2:
        return objetivo.macro_kg.to_numpy(float), 0
    x_train = entrenamiento[columnas].replace([np.inf, -np.inf], np.nan)
    medianas = x_train.median(numeric_only=True).fillna(0.0)
    x_train = x_train.fillna(medianas).fillna(0.0)
    x_test = objetivo[columnas].replace([np.inf, -np.inf], np.nan).fillna(medianas).fillna(0.0)
    escalador = StandardScaler()
    xt = escalador.fit_transform(x_train)
    xv = escalador.transform(x_test)
    modelo = Ridge(alpha=config.alpha).fit(xt, entrenamiento.residuo_objetivo.to_numpy(float))
    correccion = np.asarray(modelo.predict(xv), dtype=float)
    confianza = len(entrenamiento) / (len(entrenamiento) + config.shrink_prediccion)
    correccion = np.clip(confianza * correccion, -config.clip_log, config.clip_log)
    pred = np.expm1(np.log1p(objetivo.macro_kg.to_numpy(float)) + correccion)
    return np.maximum(pred, 0.0), int(len(entrenamiento))


def predecir_temporal(contrato: pd.DataFrame, config: Configuracion) -> pd.DataFrame:
    """Predice sin usar el real de la semana fuente ni de semanas posteriores."""

    salida = aplicar_shrinkage_features(contrato, config.shrink_features)
    salida["candidate_kg"] = salida.macro_kg.astype(float)
    salida["n_entrenamiento"] = 0
    for semana in sorted(map(int, salida.semana_objetivo.unique())):
        indices = salida.index[salida.semana_objetivo.eq(semana)]
        objetivo = salida.loc[indices]
        source_week = int(objetivo.semana_emision.min())
        if objetivo.semana_emision.nunique() != 1:
            raise AssertionError("Una semana objetivo mezcla emisiones Excel")
        entrenamiento = salida.loc[
            salida.semana_objetivo.le(source_week - 1)
            & salida.semana_objetivo.le(SEMANA_MAX_DESARROLLO)
        ].copy()
        pred, n = _ajustar_predecir(entrenamiento, objetivo, config)
        salida.loc[indices, "candidate_kg"] = pred
        salida.loc[indices, "n_entrenamiento"] = n
    return salida


def configuraciones() -> list[Configuracion]:
    baseline = Configuracion("sin_correccion", 0.0, 0.0, 0.0, 0.0)
    candidatos = [
        Configuracion(features, alpha, kf, kp, clip)
        for features in FEATURE_SETS
        if features != "sin_correccion"
        for alpha in (5.0, 20.0, 100.0)
        for kf in (20.0, 60.0)
        for kp in (12.0, 30.0)
        for clip in (0.20, 0.35)
    ]
    return [baseline, *candidatos]


def _metricas(tabla: pd.DataFrame, columna: str, grano: tuple[str, ...]) -> dict[str, float | int]:
    if tabla.empty:
        return {
            "wape": np.nan,
            "sesgo": np.nan,
            "mae_kg": np.nan,
            "n": 0,
            "real_kg": 0.0,
            "pred_kg": 0.0,
        }
    agregado = tabla.groupby(list(grano), as_index=False, dropna=False).agg(
        real_kg=("real_kg", "sum"), pred_kg=(columna, "sum")
    )
    error = agregado.pred_kg - agregado.real_kg
    denominador = float(agregado.real_kg.abs().sum())
    return {
        "wape": float(error.abs().sum() / denominador) if denominador else np.nan,
        "sesgo": float(error.sum() / denominador) if denominador else np.nan,
        "mae_kg": float(error.abs().mean()),
        "n": int(len(agregado)),
        "real_kg": float(agregado.real_kg.sum()),
        "pred_kg": float(agregado.pred_kg.sum()),
    }


def _evaluar_periodo(tabla: pd.DataFrame) -> dict[str, object]:
    r09 = tabla.loc[tabla.r09_disponible].copy()
    return {
        "semanas": sorted(map(int, tabla.semana_objetivo.unique())),
        "empresa": {
            "candidato": _metricas(tabla, "candidate_kg", ("semana_objetivo",)),
            "macro": _metricas(tabla, "macro_kg", ("semana_objetivo",)),
            "r09_condicionado": _metricas(r09, "r09_kg", ("semana_objetivo",))
            if len(r09)
            else None,
        },
        "fundo": {
            "candidato": _metricas(tabla, "candidate_kg", ("semana_objetivo", "fundo_operativo")),
            "macro": _metricas(tabla, "macro_kg", ("semana_objetivo", "fundo_operativo")),
            "r09_condicionado": _metricas(r09, "r09_kg", ("semana_objetivo", "fundo_operativo"))
            if len(r09)
            else None,
        },
    }


def seleccionar_configuracion(contrato: pd.DataFrame) -> tuple[Configuracion, pd.DataFrame]:
    desarrollo = contrato.semana_objetivo.le(SEMANA_MAX_DESARROLLO)
    ranking = []
    for config in configuraciones():
        pred = predecir_temporal(contrato, config)
        bloque = pred.loc[desarrollo]
        holdout = pred.loc[pred.semana_objetivo.isin(SEMANAS_HOLDOUT)]
        empresa = _metricas(bloque, "candidate_kg", ("semana_objetivo",))
        fundo = _metricas(bloque, "candidate_kg", ("semana_objetivo", "fundo_operativo"))
        holdout_empresa = _metricas(holdout, "candidate_kg", ("semana_objetivo",))
        ranking.append(
            {
                "configuracion_id": config.id,
                "configuracion": config,
                "wape_empresa": empresa["wape"],
                "wape_fundo": fundo["wape"],
                "sesgo_empresa": empresa["sesgo"],
                "wape_holdout_diagnostico": holdout_empresa["wape"],
                "sesgo_holdout_diagnostico": holdout_empresa["sesgo"],
            }
        )
    tabla = pd.DataFrame(ranking)
    elegibles = tabla.loc[tabla.sesgo_empresa.abs().le(0.25)].copy()
    if elegibles.empty:
        elegibles = tabla.copy()
    elegibles["score"] = 0.7 * elegibles.wape_empresa + 0.3 * elegibles.wape_fundo
    elegibles = elegibles.sort_values(["score", "wape_empresa", "wape_fundo"], kind="stable")
    return elegibles.iloc[0].configuracion, elegibles.reset_index(drop=True)


def _keyset(tabla: pd.DataFrame) -> str:
    columnas = ["campania", "semana_emision", "semana_objetivo", "fundo_operativo"]
    texto = (
        tabla[columnas].sort_values(columnas).astype(str).agg("|".join, axis=1).str.cat(sep="\n")
    )
    return hashlib.sha256(texto.encode()).hexdigest()


def ejecutar(
    *,
    root: str | Path = ROOT_DEFAULT,
    run_id: int = RUN_ID_DEFAULT,
    campania: str = CAMPANIA_DEFAULT,
) -> dict[str, object]:
    manifest, incidencias = inventariar_libros(root)
    snapshots = cargar_snapshots(manifest)
    deltas = construir_deltas(manifest, snapshots)
    contrato = construir_contrato(deltas, run_id=run_id, campania=campania)
    if contrato.empty:
        raise RuntimeError("No fue posible alinear deltas Excel con Macro/real h1")
    ganador, ranking = seleccionar_configuracion(contrato)
    pred = predecir_temporal(contrato, ganador)
    desarrollo = pred.loc[pred.semana_objetivo.le(SEMANA_MAX_DESARROLLO)].copy()
    holdout = pred.loc[pred.semana_objetivo.isin(SEMANAS_HOLDOUT)].copy()
    semanas_canonicas = sorted(map(int, manifest.semana_emision.unique()))
    semanas_faltantes = sorted(set(range(24, 36)) - set(semanas_canonicas))
    anios_poda = sorted(
        {
            int(pd.to_datetime(snapshot["FePas1"], errors="coerce").dropna().dt.year.mode().iloc[0])
            for snapshot in snapshots.values()
            if "FePas1" in snapshot
            and pd.to_datetime(snapshot["FePas1"], errors="coerce").notna().any()
        }
    )
    delta_resumen = {
        "transiciones": int(len(deltas)),
        "semanas_fuente": sorted(map(int, deltas.semana_emision.unique())),
        "semanas_objetivo": sorted(map(int, deltas.semana_objetivo.unique())),
        "lotes_agregados": int(deltas.n_agregados.sum()),
        "lotes_retirados": int(deltas.n_retirados.sum()),
        "mediana_share_parametros_cambiados": float(deltas.share_parametros_cambiados.median()),
        "mediana_share_calendario_cambiado": float(deltas.share_calendario_cambiado.median()),
        "transiciones_gap_mayor_1": int(deltas.gap_emisiones.gt(1).sum()),
    }
    evidencia_suficiente = bool(
        desarrollo.semana_objetivo.nunique() >= 6
        and holdout.semana_objetivo.nunique() >= 3
        and len(anios_poda) >= 2
    )
    cand_holdout = _metricas(holdout, "candidate_kg", ("semana_objetivo",))
    macro_holdout = _metricas(holdout, "macro_kg", ("semana_objetivo",))
    mejora_holdout = (
        (macro_holdout["wape"] - cand_holdout["wape"]) / macro_holdout["wape"]
        if macro_holdout["wape"] and np.isfinite(macro_holdout["wape"])
        else np.nan
    )
    mejora_observada = bool(
        np.isfinite(mejora_holdout)
        and mejora_holdout >= 0.05
        and abs(cand_holdout["sesgo"]) <= 0.10
    )
    ranking_deltas = ranking.loc[
        ranking.configuracion.map(lambda cfg: cfg.feature_set != "sin_correccion")
    ].copy()
    mejor_delta_desarrollo = ranking_deltas.iloc[0]
    oracle_holdout = ranking_deltas.sort_values(
        ["wape_holdout_diagnostico", "sesgo_holdout_diagnostico"],
        key=lambda serie: serie.abs() if serie.name == "sesgo_holdout_diagnostico" else serie,
        kind="stable",
    ).iloc[0]
    delta_mejora_desarrollo = bool(
        float(mejor_delta_desarrollo.wape_empresa)
        < float(_metricas(desarrollo, "macro_kg", ("semana_objetivo",))["wape"])
    )
    return {
        "schema": "screening-excel-parameter-deltas-v1",
        "campania": campania,
        "run_macro_congelada": run_id,
        "r09_como_predictor": False,
        "persistido": False,
        "publicado": False,
        "seleccion": "configuración solo con C2026 objetivo <= S30; S31-S33 reservadas",
        "configuracion_ganadora": asdict(ganador),
        "features_usadas": list(FEATURE_SETS[ganador.feature_set]),
        "trazabilidad": {
            "root": str(Path(root).resolve()),
            "libros_canonicos": int(len(manifest)),
            "semanas_canonicas": semanas_canonicas,
            "semanas_sin_cadena_completa": semanas_faltantes,
            "incidencias": incidencias.to_dict("records"),
            "anios_detectados_en_fepas": anios_poda,
            "campanias_externas_disponibles": [],
            "nota_externa": (
                "Los libros semanales S24-S35 auditados contienen calendarios 2026; "
                "no existe una cadena equivalente versionada para C2024/C2025 en este alcance."
            ),
        },
        "deltas": delta_resumen,
        "evaluation_contract": {
            "keyset_sha256": _keyset(pred),
            "n_fundo_semana": int(len(pred)),
            "n_semanas_desarrollo": int(desarrollo.semana_objetivo.nunique()),
            "semanas_desarrollo": sorted(map(int, desarrollo.semana_objetivo.unique())),
            "n_semanas_holdout": int(holdout.semana_objetivo.nunique()),
            "semanas_holdout": sorted(map(int, holdout.semana_objetivo.unique())),
            "regla_asof": "archivo fuente S < semana objetivo; entrenamiento target <= S-1",
        },
        "desarrollo": _evaluar_periodo(desarrollo),
        "holdout": _evaluar_periodo(holdout),
        "contrato_completo": _evaluar_periodo(pred),
        "mejora_relativa_holdout_vs_macro": float(mejora_holdout)
        if np.isfinite(mejora_holdout)
        else None,
        "diagnostico_deltas": {
            "alguna_configuracion_mejora_macro_en_desarrollo": delta_mejora_desarrollo,
            "mejor_delta_segun_desarrollo": {
                "configuracion": asdict(mejor_delta_desarrollo.configuracion),
                "wape_desarrollo": float(mejor_delta_desarrollo.wape_empresa),
                "wape_holdout": float(mejor_delta_desarrollo.wape_holdout_diagnostico),
            },
            "mejor_delta_oracle_holdout_prohibido": {
                "nota": "Se informa solo para probar robustez; no se usó para seleccionar.",
                "configuracion": asdict(oracle_holdout.configuracion),
                "wape_holdout": float(oracle_holdout.wape_holdout_diagnostico),
                "sesgo_holdout": float(oracle_holdout.sesgo_holdout_diagnostico),
            },
        },
        "ranking_desarrollo": [
            {
                **{k: v for k, v in fila.items() if k != "configuracion"},
                "configuracion": asdict(fila["configuracion"]),
            }
            for fila in ranking.head(12).to_dict("records")
        ],
        "veredicto": {
            "mejora_observada_holdout": mejora_observada,
            "evidencia_suficiente_para_afirmar_mejora": evidencia_suficiente and mejora_observada,
            "publicable": False,
            "bloqueo": (
                "Los deltas no mejoran Macro ni siquiera en desarrollo; además S30 no "
                "tiene base canónica, el desarrollo y holdout no alcanzan 6 y 3 semanas, "
                "y no hay campaña externa versionada."
                if not delta_mejora_desarrollo
                else None
                if evidencia_suficiente
                else (
                    "Cadena insuficiente: S30 no tiene base canónica; el desarrollo y holdout "
                    "no alcanzan 6 y 3 semanas, y no hay campaña externa versionada."
                )
            ),
        },
        "detalle": pred.to_dict("records"),
    }


__all__ = [
    "CAMPANIA_DEFAULT",
    "Configuracion",
    "FEATURES_CRUDAS",
    "FEATURE_SETS",
    "RUN_ID_DEFAULT",
    "ROOT_DEFAULT",
    "SEMANA_MAX_DESARROLLO",
    "SEMANAS_HOLDOUT",
    "_ajustar_predecir",
    "_evaluar_periodo",
    "_keyset",
    "_mediana_finita",
    "_metricas",
    "aplicar_shrinkage_features",
    "calcular_delta_snapshot",
    "configuraciones",
    "construir_contrato",
    "construir_deltas",
    "ejecutar",
    "predecir_temporal",
    "seleccionar_configuracion",
]
