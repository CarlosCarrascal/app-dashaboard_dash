"""Flujo adaptativo online del servicio de nowcast."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import nnls

from analitica.aplicacion.servicios.nowcast_partes_base import (
    ACCESS_DEFAULT,
    EPS,
    FUNDOS,
    R09_ACCESS_DEFAULT,
    RUNS_CERTIFICADOS,
    diagnostico_shares,
    leer_diario,
    normalizar_fundo_r09,
    sha256_archivo,
)
from analitica.aplicacion.servicios.parametros_nowcast import leer_macro_h1, leer_reales_r09_fundo


@dataclass(frozen=True)
class ConfiguracionAdaptativa:
    lookback_share: int
    shrink_fundo: float
    lookback_modelo: int
    regularizacion: float
    peso_ritmo_prior: float
    umbral_cola: float
    retencion_correccion_cola: float
    share_min: float = 0.15
    share_max: float = 0.65
    escala_min: float = 0.70
    escala_max: float = 1.30

    @property
    def id(self) -> str:
        return (
            f"s{self.lookback_share}-sf{self.shrink_fundo:.0f}-"
            f"m{self.lookback_modelo}-r{self.regularizacion:.1f}-"
            f"p{self.peso_ritmo_prior:.2f}-c{self.umbral_cola:.2f}-"
            f"tc{self.retencion_correccion_cola:.2f}"
        )


def _metricas_adaptativa(tabla: pd.DataFrame, columna: str) -> dict[str, float | int]:
    if tabla.empty:
        return {"wape": np.nan, "sesgo": np.nan, "mae_kg": np.nan, "n": 0}
    error = tabla[columna].astype(float) - tabla.real_kg.astype(float)
    denominador = float(tabla.real_kg.abs().sum())
    return {
        "wape": float(error.abs().sum() / denominador) if denominador else np.nan,
        "sesgo": float(error.sum() / denominador) if denominador else np.nan,
        "mae_kg": float(error.abs().mean()),
        "n": int(len(tabla)),
    }


def _agregar_empresa(tabla: pd.DataFrame, columnas: Iterable[str]) -> pd.DataFrame:
    agregaciones = {"real_kg": ("real_kg", "sum")}
    for columna in columnas:
        agregaciones[columna] = (columna, "sum")
    return tabla.groupby(["campania", "fecha_objetivo"], as_index=False).agg(**agregaciones)


def _hash_keyset(tabla: pd.DataFrame) -> str:
    columnas = ["campania", "fecha_objetivo", "fundo_operativo"]
    texto = (
        tabla[columnas]
        .sort_values(columnas, kind="stable")
        .astype(str)
        .agg("|".join, axis=1)
        .str.cat(sep="\n")
    )
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _estimar_pace_online(tabla: pd.DataFrame, cfg: ConfiguracionAdaptativa) -> pd.DataFrame:
    salida = (
        tabla.sort_values(["fecha_objetivo", "fundo_operativo"], kind="stable")
        .reset_index(drop=True)
        .copy()
    )
    salida["pace_kg"] = salida.macro_kg.astype(float)
    salida["share_estimado"] = np.nan
    salida["pace_disponible"] = False
    salida["n_share_global"] = 0
    salida["n_share_fundo"] = 0
    for fecha in salida.fecha_objetivo.drop_duplicates().sort_values():
        actual_idx = salida.index[salida.fecha_objetivo.eq(fecha)]
        historia = salida.loc[salida.fecha_objetivo.lt(fecha)].copy()
        if cfg.lookback_share:
            fechas = sorted(historia.fecha_objetivo.unique())[-cfg.lookback_share :]
            historia = historia.loc[historia.fecha_objetivo.isin(fechas)]
        historia = historia.loc[historia.real_kg.gt(0)].copy()
        historia["share"] = historia.montue_kg / historia.real_kg
        historia = historia.loc[
            historia.share.between(cfg.share_min, cfg.share_max, inclusive="both")
        ]
        if historia.empty:
            continue
        share_global = float(historia.share.median())
        for indice in actual_idx:
            fila = salida.loc[indice]
            local = historia.loc[historia.fundo_operativo.eq(fila.fundo_operativo), "share"]
            share_local = float(local.median()) if len(local) else share_global
            peso_local = len(local) / (len(local) + cfg.shrink_fundo)
            share = peso_local * share_local + (1.0 - peso_local) * share_global
            share = float(np.clip(share, cfg.share_min, cfg.share_max))
            pace = max(float(fila.montue_kg), float(fila.montue_kg) / share)
            salida.at[indice, "pace_kg"] = pace
            salida.at[indice, "share_estimado"] = share
            salida.at[indice, "pace_disponible"] = bool(fila.montue_kg > 0)
            salida.at[indice, "n_share_global"] = int(len(historia))
            salida.at[indice, "n_share_fundo"] = int(len(local))
    return salida


def _ajustar_coeficientes(
    historia: pd.DataFrame,
    cfg: ConfiguracionAdaptativa,
) -> tuple[float, float, int]:
    historia = historia.loc[
        historia.real_kg.ge(0)
        & historia.macro_kg.gt(0)
        & historia.pace_kg.ge(0)
        & historia.pace_disponible
    ].copy()
    if cfg.lookback_modelo:
        fechas = sorted(historia.fecha_objetivo.unique())[-cfg.lookback_modelo :]
        historia = historia.loc[historia.fecha_objetivo.isin(fechas)]
    prior = np.array([1.0 - cfg.peso_ritmo_prior, cfg.peso_ritmo_prior], dtype=float)
    if len(historia) < 8 or historia.fecha_objetivo.nunique() < 2:
        return float(prior[0]), float(prior[1]), int(len(historia))
    base = historia.macro_kg.to_numpy(float) + EPS
    objetivo = (historia.real_kg.to_numpy(float) + EPS) / base
    x = np.column_stack(
        [
            np.ones(len(historia), dtype=float),
            (historia.pace_kg.to_numpy(float) + EPS) / base,
        ]
    )
    mediana = max(float(np.median(historia.real_kg.to_numpy(float))), 1.0)
    pesos = np.sqrt(np.clip(historia.real_kg.to_numpy(float) / mediana, 0.25, 4.0))
    beta = prior.copy()
    pesos_robustos = np.ones(len(historia), dtype=float)
    raiz = float(np.sqrt(cfg.regularizacion))
    for _ in range(4):
        pesos_finales = pesos * np.sqrt(pesos_robustos)
        xw = x * pesos_finales[:, None]
        yw = objetivo * pesos_finales
        x_aug = np.vstack([xw, raiz * np.eye(2)])
        y_aug = np.concatenate([yw, raiz * prior])
        beta, _ = nnls(x_aug, y_aug)
        residuo = objetivo - x @ beta
        centro = float(np.median(residuo))
        mad = float(np.median(np.abs(residuo - centro)))
        escala_robusta = max(1.4826 * mad, 0.03)
        limite = 1.5 * escala_robusta
        absoluto = np.abs(residuo - centro)
        pesos_robustos = np.where(absoluto <= limite, 1.0, limite / np.maximum(absoluto, 1e-12))
    escala = float(beta.sum())
    if not np.isfinite(escala) or escala <= 0:
        beta = prior.copy()
        escala = 1.0
    peso_ritmo = float(beta[1] / escala)
    peso_ritmo = float(np.clip(peso_ritmo, 0.0, 1.0))
    escala = float(np.clip(escala, cfg.escala_min, cfg.escala_max))
    return escala * (1.0 - peso_ritmo), escala * peso_ritmo, int(len(historia))


def _predecir_online(tabla: pd.DataFrame, cfg: ConfiguracionAdaptativa) -> pd.DataFrame:
    salida = _estimar_pace_online(tabla, cfg)
    salida["candidate_kg"] = salida.macro_kg.astype(float)
    salida["coef_macro"] = 1.0
    salida["coef_pace"] = 0.0
    salida["intercepto_relativo"] = 1.0
    salida["escala_adaptativa"] = 1.0
    salida["peso_ritmo_adaptativo"] = 0.0
    salida["n_entrenamiento"] = 0
    salida["fase_bajo_volumen"] = False
    salida["retencion_correccion"] = 1.0
    for fecha in salida.fecha_objetivo.drop_duplicates().sort_values():
        mascara = salida.fecha_objetivo.eq(fecha)
        historia = salida.loc[salida.fecha_objetivo.lt(fecha)]
        coef_macro, coef_pace, n = _ajustar_coeficientes(historia, cfg)
        disponible = salida.loc[mascara, "pace_disponible"].to_numpy(bool)
        macro = salida.loc[mascara, "macro_kg"].to_numpy(float)
        pace = salida.loc[mascara, "pace_kg"].to_numpy(float)
        candidato_crudo = np.where(disponible, coef_macro * macro + coef_pace * pace, macro)
        indices_actuales = salida.index[mascara]
        fase_cola = np.zeros(len(indices_actuales), dtype=bool)
        for posicion, indice in enumerate(indices_actuales):
            fondo = salida.at[indice, "fundo_operativo"]
            historia_fundo = salida.loc[
                salida.fecha_objetivo.lt(fecha)
                & salida.fundo_operativo.eq(fondo)
                & salida.macro_kg.gt(0),
                "macro_kg",
            ]
            if len(historia_fundo) >= 3:
                referencia_volumen = float(historia_fundo.quantile(0.90))
                fase_cola[posicion] = bool(
                    referencia_volumen > 0
                    and macro[posicion] < cfg.umbral_cola * referencia_volumen
                )
        retencion = np.where(fase_cola, cfg.retencion_correccion_cola, 1.0)
        candidato = macro + retencion * (candidato_crudo - macro)
        escala = coef_macro + coef_pace
        peso_ritmo = coef_pace / escala if escala else 0.0
        salida.loc[mascara, "candidate_kg"] = np.maximum(candidato, 0.0)
        salida.loc[mascara, "coef_macro"] = coef_macro
        salida.loc[mascara, "coef_pace"] = coef_pace
        salida.loc[mascara, "intercepto_relativo"] = coef_macro
        salida.loc[mascara, "escala_adaptativa"] = escala
        salida.loc[mascara, "peso_ritmo_adaptativo"] = peso_ritmo
        salida.loc[mascara, "n_entrenamiento"] = n
        salida.loc[mascara, "fase_bajo_volumen"] = fase_cola
        salida.loc[mascara, "retencion_correccion"] = retencion
    return salida


def _bootstrap_pareado(
    tabla: pd.DataFrame,
    referencia: str,
    *,
    repeticiones: int = 5_000,
) -> dict[str, object] | None:
    pareado = tabla.loc[tabla.candidate_kg.notna() & tabla[referencia].notna()].copy()
    if pareado.empty:
        return None
    empresa = _agregar_empresa(pareado, ["candidate_kg", referencia])
    met_c = _metricas_adaptativa(empresa, "candidate_kg")
    met_r = _metricas_adaptativa(empresa, referencia)
    ec = (empresa.candidate_kg - empresa.real_kg).abs().to_numpy(float)
    er = (empresa[referencia] - empresa.real_kg).abs().to_numpy(float)
    den = empresa.real_kg.abs().to_numpy(float)
    rng = np.random.default_rng(20260825)
    diferencias: list[float] = []
    for _ in range(repeticiones):
        indices = rng.integers(0, len(empresa), len(empresa))
        denominador = float(den[indices].sum())
        if denominador:
            diferencias.append(float((ec[indices].sum() - er[indices].sum()) / denominador))
    intervalo = np.quantile(diferencias, [0.025, 0.975]) if diferencias else [np.nan, np.nan]
    por_fundo: dict[str, object] = {}
    for fundo, bloque in pareado.groupby("fundo_operativo"):
        mc = _metricas_adaptativa(bloque, "candidate_kg")
        mr = _metricas_adaptativa(bloque, referencia)
        por_fundo[str(fundo)] = {
            "candidato": mc,
            "referencia": mr,
            "diferencia_wape_pp": float(100.0 * (mc["wape"] - mr["wape"])),
        }
    return {
        "n_fundo_semana": int(len(pareado)),
        "n_semanas": int(len(empresa)),
        "keyset_sha256": _hash_keyset(pareado),
        "candidato_empresa": met_c,
        "referencia_empresa": met_r,
        "diferencia_wape_pp": float(100.0 * (met_c["wape"] - met_r["wape"])),
        "semanas_ganadas": int((ec < er).sum()),
        "bootstrap_diferencia_wape_pp_ic95": [
            float(100.0 * intervalo[0]),
            float(100.0 * intervalo[1]),
        ],
        "por_fundo": por_fundo,
    }


def _construir_contrato_adaptativo(
    *,
    campania: str,
    run_id: int,
    access: Path,
    r09_access: Path,
) -> pd.DataFrame:
    macro = leer_macro_h1(campania, run_id=run_id).copy()
    macro = macro.groupby(
        [
            "campania",
            "fecha_emision",
            "fecha_objetivo",
            "semana_emision",
            "semana_objetivo",
            "fundo_operativo",
        ],
        as_index=False,
    ).macro_kg.sum()
    diario = leer_diario(access, campania)
    diario["fecha_objetivo"] = diario.fecha - pd.to_timedelta(diario.dia_iso - 1, unit="D")
    diario["es_montue"] = diario.dia_iso.le(2)
    semanal = diario.groupby(["fecha_objetivo", "fundo_operativo"], as_index=False).agg(
        real_kg=("kg", "sum"),
        montue_kg=("kg", lambda x: float(x[diario.loc[x.index, "es_montue"]].sum())),
        fecha_max=("fecha", "max"),
    )
    watermark = pd.Timestamp(diario.fecha.max()).normalize()
    macro = macro.loc[macro.fecha_objetivo.add(pd.Timedelta(days=6)).le(watermark)].copy()
    tabla = macro.merge(
        semanal,
        on=["fecha_objetivo", "fundo_operativo"],
        how="left",
        validate="one_to_one",
    )
    tabla[["real_kg", "montue_kg"]] = tabla[["real_kg", "montue_kg"]].fillna(0.0)
    _, r09 = leer_reales_r09_fundo(r09_access, campania)
    r09["fundo_operativo"] = r09.fundo_operativo.map(normalizar_fundo_r09)
    r09 = r09.groupby(
        ["semana_emision", "semana_objetivo", "fundo_operativo"], as_index=False
    ).r09_kg.sum()
    pre = r09.rename(columns={"r09_kg": "r09_presemana_kg"})
    tabla = tabla.merge(
        pre,
        on=["semana_emision", "semana_objetivo", "fundo_operativo"],
        how="left",
        validate="one_to_one",
    )
    misma = r09.loc[r09.semana_emision.eq(r09.semana_objetivo)].rename(
        columns={"r09_kg": "r09_misma_semana_kg"}
    )
    misma = misma[["semana_objetivo", "fundo_operativo", "r09_misma_semana_kg"]]
    tabla = tabla.merge(
        misma,
        on=["semana_objetivo", "fundo_operativo"],
        how="left",
        validate="many_to_one",
    )
    tabla["watermark"] = watermark
    return tabla.sort_values(["fecha_objetivo", "fundo_operativo"], kind="stable").reset_index(
        drop=True
    )


def _evaluar_bloque(tabla: pd.DataFrame) -> dict[str, object]:
    empresa = _agregar_empresa(tabla, ["candidate_kg", "macro_kg"])
    return {
        "n_fundo_semana": int(len(tabla)),
        "n_semanas": int(tabla.fecha_objetivo.nunique()),
        "real_kg": float(tabla.real_kg.sum()),
        "candidato": _metricas_adaptativa(empresa, "candidate_kg"),
        "macro": _metricas_adaptativa(empresa, "macro_kg"),
        "pareado_vs_macro": _bootstrap_pareado(tabla, "macro_kg"),
        "pareado_vs_r09_presemana": _bootstrap_pareado(tabla, "r09_presemana_kg"),
        "pareado_vs_r09_misma_semana": _bootstrap_pareado(tabla, "r09_misma_semana_kg"),
    }


def _configuraciones() -> list[ConfiguracionAdaptativa]:
    return [
        ConfiguracionAdaptativa(s, sf, m, r, p, c, tc)
        for s in (4, 8, 0)
        for sf in (4.0, 16.0)
        for m in (4, 8, 0)
        for r in (1.0, 4.0, 16.0)
        for p in (0.25, 0.50, 0.75)
        for c, tc in ((0.20, 0.25), (0.20, 0.50), (0.35, 0.25))
    ]


def _seleccionar_configuracion(
    desarrollo: pd.DataFrame,
) -> tuple[ConfiguracionAdaptativa, pd.DataFrame]:
    ranking: list[dict[str, object]] = []
    candidatas = _configuraciones()
    for cfg in candidatas:
        pred = _predecir_online(desarrollo, cfg)
        empresa = _agregar_empresa(pred, ["candidate_kg"])
        metricas = _metricas_adaptativa(empresa, "candidate_kg")
        ranking.append({"configuracion_id": cfg.id, **metricas})
    orden = pd.DataFrame(ranking)
    elegibles = orden.loc[orden.sesgo.abs().le(0.15)].copy()
    if elegibles.empty:
        elegibles = orden.copy()
    elegibles = elegibles.sort_values(["wape", "mae_kg", "sesgo"], kind="stable")
    ganador_id = str(elegibles.iloc[0].configuracion_id)
    ganador = next(cfg for cfg in candidatas if cfg.id == ganador_id)
    return ganador, elegibles.reset_index(drop=True)


def ejecutar(
    *,
    access: Path = ACCESS_DEFAULT,
    r09_access: Path = R09_ACCESS_DEFAULT,
) -> dict[str, object]:
    """Ejecuta el screening adaptativo con la selección congelada requerida."""
    contratos = {
        campania: _construir_contrato_adaptativo(
            campania=campania,
            run_id=run_id,
            access=access,
            r09_access=r09_access,
        )
        for campania, run_id in RUNS_CERTIFICADOS.items()
    }
    desarrollo = contratos["C2026"].loc[contratos["C2026"].semana_objetivo.le(30)].copy()
    cfg, ranking = _seleccionar_configuracion(desarrollo)

    predicciones = {
        campania: _predecir_online(contrato, cfg) for campania, contrato in contratos.items()
    }
    c2026 = predicciones["C2026"]
    evaluaciones = {
        "desarrollo_C2026_hasta_S30": _evaluar_bloque(c2026.loc[c2026.semana_objetivo.le(30)]),
        "holdout_C2026_S31_S33": _evaluar_bloque(
            c2026.loc[c2026.semana_objetivo.between(31, 33)]
        ),
        "externa_C2024": _evaluar_bloque(predicciones["C2024"]),
        "externa_C2025": _evaluar_bloque(predicciones["C2025"]),
    }
    detalles = {
        campania: pred[
            [
                "campania",
                "fecha_emision",
                "fecha_objetivo",
                "semana_emision",
                "semana_objetivo",
                "fundo_operativo",
                "real_kg",
                "montue_kg",
                "macro_kg",
                "pace_kg",
                "candidate_kg",
                "r09_presemana_kg",
                "r09_misma_semana_kg",
                "share_estimado",
                "coef_macro",
                "coef_pace",
                "intercepto_relativo",
                "escala_adaptativa",
                "peso_ritmo_adaptativo",
                "n_entrenamiento",
                "fase_bajo_volumen",
                "retencion_correccion",
            ]
        ].to_dict("records")
        for campania, pred in predicciones.items()
    }
    return {
        "schema": "screening-adaptive-nowcast-v1",
        "producto": "cierre intra-semanal con Macro h1 + ritmo lunes-martes",
        "configuracion_congelada": {"id": cfg.id, **asdict(cfg)},
        "seleccion": "solo C2026 <= S30; configuracion congelada fuera de desarrollo",
        "runs_macro": RUNS_CERTIFICADOS,
        "fuente_reales": str(access),
        "fuente_r09": str(r09_access),
        "sha256_fuente_reales": sha256_archivo(access),
        "sha256_fuente_r09": sha256_archivo(r09_access),
        "diagnostico_shares": {
            campania: diagnostico_shares(contrato) for campania, contrato in contratos.items()
        },
        "metodologia": [
            "combinacion online: pesos temporales reestimados solo con cierres anteriores",
            "actualizacion Bayes-linear aproximada: regularizacion hacia una mezcla prior",
            "NNLS robusto IRLS-Huber en escala relativa para pocos datos",
            "salvaguarda de fase: retraccion hacia Macro en colas de bajo volumen",
        ],
        "evaluaciones": evaluaciones,
        "ranking_desarrollo": ranking.head(25).to_dict("records"),
        "detalle": detalles,
        "r09_como_predictor": False,
        "persistencia_postgresql": False,
        "publicado_dashboard": False,
    }


# Aliases privados históricos: las fachadas antiguas siguen apuntando a la
# implementación única del servicio, sin mantener una segunda copia ejecutable.
_metricas = _metricas_adaptativa
_sha256_archivo = sha256_archivo
_diagnostico_shares = diagnostico_shares
_normalizar_fundo_r09 = normalizar_fundo_r09
_bootstrap_pareado = _bootstrap_pareado
_construir_contrato = _construir_contrato_adaptativo


def agregar_empresa(tabla: pd.DataFrame, columnas: Iterable[str]) -> pd.DataFrame:
    return _agregar_empresa(tabla, columnas)


def bootstrap_pareado(tabla: pd.DataFrame, referencia: str, *, repeticiones: int = 5_000):
    return _bootstrap_pareado(tabla, referencia, repeticiones=repeticiones)


def metricas_adaptativa(tabla: pd.DataFrame, columna: str) -> dict[str, float | int]:
    return _metricas_adaptativa(tabla, columna)


def metricas(tabla: pd.DataFrame, columna: str) -> dict[str, float | int]:
    """Alias de compatibilidad para los screenings adaptativos históricos."""
    return _metricas_adaptativa(tabla, columna)


def construir_contrato(*, campania: str, run_id: int, access: Path, r09_access: Path):
    return _construir_contrato_adaptativo(
        campania=campania,
        run_id=run_id,
        access=access,
        r09_access=r09_access,
    )


def predecir_online(tabla: pd.DataFrame, cfg: ConfiguracionAdaptativa):
    return _predecir_online(tabla, cfg)


BASE_CONGELADA = ConfiguracionAdaptativa(
    lookback_share=4,
    shrink_fundo=4.0,
    lookback_modelo=4,
    regularizacion=1.0,
    peso_ritmo_prior=0.50,
    umbral_cola=0.20,
    retencion_correccion_cola=0.25,
)


__all__ = [
    "ACCESS_DEFAULT",
    "BASE_CONGELADA",
    "ConfiguracionAdaptativa",
    "EPS",
    "FUNDOS",
    "R09_ACCESS_DEFAULT",
    "RUNS_CERTIFICADOS",
    "agregar_empresa",
    "bootstrap_pareado",
    "ejecutar",
    "metricas",
    "predecir_online",
]
