"""Nowcast puro de cierre semanal con reconciliacion empresa -> fundos.

El modulo no lee archivos ni bases de datos. Recibe un panel as-of con una fila
por campania, lunes objetivo y fundo. Aprende exclusivamente de semanas
anteriores cerradas, combina Macro h1 con el ritmo observado lunes-martes,
estima un unico total empresa y lo reparte exactamente entre fundos.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final

import numpy as np
import pandas as pd
from scipy.optimize import nnls

EPS: Final[float] = 1_000.0
COLUMNAS_REQUERIDAS: Final[tuple[str, ...]] = (
    "campania",
    "fecha_objetivo",
    "fecha_corte_asof",
    "fundo_operativo",
    "macro_kg",
    "montue_kg",
    "dias_montue_observados",
    "real_kg",
)


class ContratoNowcastError(ValueError):
    """El panel no respeta la semantica temporal o el grano requeridos."""


@dataclass(frozen=True)
class ConfiguracionNowcastCierre:
    lookback_share: int = 4
    shrink_fundo: float = 4.0
    lookback_modelo: int = 4
    regularizacion: float = 1.0
    peso_ritmo_prior: float = 0.50
    umbral_cola: float = 0.20
    retencion_correccion_cola: float = 0.25
    share_min: float = 0.15
    share_max: float = 0.65
    escala_min: float = 0.70
    escala_max: float = 1.30
    peso_participacion_montue: float = 0.40
    shrink_reconciliacion_semanas: float = 0.0
    retencion_reconciliacion_cola: float = 0.25
    dias_montue_requeridos: int = 2

    @property
    def id(self) -> str:
        return (
            "NowcastCierreAdaptativo_v1__"
            f"s{self.lookback_share}-sf{self.shrink_fundo:.0f}-"
            f"m{self.lookback_modelo}-r{self.regularizacion:.1f}-"
            f"p{self.peso_ritmo_prior:.2f}-c{self.umbral_cola:.2f}-"
            f"tc{self.retencion_correccion_cola:.2f}__"
            f"pm{self.peso_participacion_montue:.2f}-"
            f"k{self.shrink_reconciliacion_semanas:.0f}-"
            f"tc{self.retencion_reconciliacion_cola:.2f}"
        )


CONFIGURACION_CONGELADA: Final[ConfiguracionNowcastCierre] = ConfiguracionNowcastCierre()


@dataclass(frozen=True)
class ResultadoNowcastCierre:
    predicciones: pd.DataFrame
    empresa: pd.DataFrame
    configuracion_id: str
    configuracion: dict[str, object]


def validar_contrato_asof(panel: pd.DataFrame) -> pd.DataFrame:
    """Valida y normaliza el panel sin completar datos faltantes con cero."""
    faltantes = sorted(set(COLUMNAS_REQUERIDAS).difference(panel.columns))
    if faltantes:
        raise ContratoNowcastError(f"Faltan columnas requeridas: {faltantes}")
    salida = panel.copy()
    salida["campania"] = salida.campania.astype(str).str.strip()
    salida["fundo_operativo"] = salida.fundo_operativo.astype(str).str.strip()
    salida["fecha_objetivo"] = pd.to_datetime(salida.fecha_objetivo, errors="coerce").dt.normalize()
    salida["fecha_corte_asof"] = pd.to_datetime(
        salida.fecha_corte_asof, errors="coerce"
    ).dt.normalize()
    for columna in ("macro_kg", "montue_kg", "real_kg"):
        salida[columna] = pd.to_numeric(salida[columna], errors="coerce")
    salida["dias_montue_observados"] = pd.to_numeric(salida.dias_montue_observados, errors="coerce")

    if salida[["campania", "fundo_operativo"]].eq("").any().any():
        raise ContratoNowcastError("Campania y fundo no pueden estar vacios")
    if salida[["fecha_objetivo", "fecha_corte_asof"]].isna().any().any():
        raise ContratoNowcastError("Las fechas del contrato deben ser validas")
    if not salida.fecha_objetivo.dt.dayofweek.eq(0).all():
        raise ContratoNowcastError("fecha_objetivo debe ser el lunes de la semana")
    duplicadas = salida.duplicated(["campania", "fecha_objetivo", "fundo_operativo"], keep=False)
    if duplicadas.any():
        raise ContratoNowcastError("El grano campania-semana-fundo no es unico")
    if salida[["macro_kg", "montue_kg"]].isna().any().any():
        raise ContratoNowcastError("Macro y Mon-Mar no pueden ser nulos")
    if salida[["macro_kg", "montue_kg"]].lt(0).any().any():
        raise ContratoNowcastError("Macro y Mon-Mar no pueden ser negativos")
    if (
        salida.dias_montue_observados.isna().any()
        or not salida.dias_montue_observados.between(0, 2, inclusive="both").all()
    ):
        raise ContratoNowcastError("dias_montue_observados debe estar entre 0 y 2")

    lunes = salida.fecha_objetivo
    martes = lunes + pd.Timedelta(days=1)
    if (salida.fecha_corte_asof < lunes).any() or (salida.fecha_corte_asof > martes).any():
        raise ContratoNowcastError(
            "El corte as-of solo puede contener lunes y martes de la semana objetivo"
        )
    salida["montue_completo"] = salida.dias_montue_observados.eq(2) & salida.fecha_corte_asof.eq(
        martes
    )
    return salida.sort_values(
        ["campania", "fecha_objetivo", "fundo_operativo"], kind="stable"
    ).reset_index(drop=True)


def _estimar_pace_online(
    tabla: pd.DataFrame,
    cfg: ConfiguracionNowcastCierre,
) -> pd.DataFrame:
    salida = tabla.copy()
    salida["pace_kg"] = salida.macro_kg.astype(float)
    salida["share_estimado"] = np.nan
    salida["pace_disponible"] = False
    salida["n_share_global"] = 0
    salida["n_share_fundo"] = 0

    for fecha in salida.fecha_objetivo.drop_duplicates().sort_values():
        actuales = salida.index[salida.fecha_objetivo.eq(fecha)]
        historia = salida.loc[salida.fecha_objetivo.lt(fecha) & salida.montue_completo].copy()
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
        for indice in actuales:
            fila = salida.loc[indice]
            local = historia.loc[historia.fundo_operativo.eq(fila.fundo_operativo), "share"]
            share_local = float(local.median()) if len(local) else share_global
            peso_local = len(local) / (len(local) + cfg.shrink_fundo)
            share = peso_local * share_local + (1.0 - peso_local) * share_global
            share = float(np.clip(share, cfg.share_min, cfg.share_max))
            pace = max(float(fila.montue_kg), float(fila.montue_kg) / share)
            salida.at[indice, "pace_kg"] = pace
            salida.at[indice, "share_estimado"] = share
            salida.at[indice, "pace_disponible"] = bool(fila.montue_completo and fila.montue_kg > 0)
            salida.at[indice, "n_share_global"] = int(len(historia))
            salida.at[indice, "n_share_fundo"] = int(len(local))
    return salida


def _ajustar_coeficientes(
    historia: pd.DataFrame,
    cfg: ConfiguracionNowcastCierre,
) -> tuple[float, float, int]:
    historia = historia.loc[
        historia.montue_completo
        & historia.real_kg.ge(0)
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
    matriz = np.column_stack(
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
        xw = matriz * pesos_finales[:, None]
        yw = objetivo * pesos_finales
        beta, _ = nnls(
            np.vstack([xw, raiz * np.eye(2)]),
            np.concatenate([yw, raiz * prior]),
        )
        residuo = objetivo - matriz @ beta
        centro = float(np.median(residuo))
        mad = float(np.median(np.abs(residuo - centro)))
        escala_robusta = max(1.4826 * mad, 0.03)
        limite = 1.5 * escala_robusta
        absoluto = np.abs(residuo - centro)
        pesos_robustos = np.where(
            absoluto <= limite,
            1.0,
            limite / np.maximum(absoluto, 1e-12),
        )

    escala = float(beta.sum())
    if not np.isfinite(escala) or escala <= 0:
        beta = prior.copy()
        escala = 1.0
    peso_ritmo = float(np.clip(beta[1] / escala, 0.0, 1.0))
    escala = float(np.clip(escala, cfg.escala_min, cfg.escala_max))
    return escala * (1.0 - peso_ritmo), escala * peso_ritmo, int(len(historia))


def _estimar_total_adaptativo(
    tabla: pd.DataFrame,
    cfg: ConfiguracionNowcastCierre,
) -> pd.DataFrame:
    salida = _estimar_pace_online(tabla, cfg)
    salida["candidate_base_kg"] = salida.macro_kg.astype(float)
    salida["coef_macro"] = 1.0
    salida["coef_pace"] = 0.0
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
        crudo = np.where(disponible, coef_macro * macro + coef_pace * pace, macro)
        indices = salida.index[mascara]
        fase_cola = np.zeros(len(indices), dtype=bool)
        for posicion, indice in enumerate(indices):
            fundo = salida.at[indice, "fundo_operativo"]
            historia_fundo = salida.loc[
                salida.fecha_objetivo.lt(fecha)
                & salida.fundo_operativo.eq(fundo)
                & salida.macro_kg.gt(0),
                "macro_kg",
            ]
            if len(historia_fundo) >= 3:
                referencia = float(historia_fundo.quantile(0.90))
                fase_cola[posicion] = bool(
                    referencia > 0 and macro[posicion] < cfg.umbral_cola * referencia
                )
        retencion = np.where(fase_cola, cfg.retencion_correccion_cola, 1.0)
        candidato = macro + retencion * (crudo - macro)
        escala = coef_macro + coef_pace
        peso_ritmo = coef_pace / escala if escala else 0.0
        salida.loc[mascara, "candidate_base_kg"] = np.maximum(candidato, 0.0)
        salida.loc[mascara, "coef_macro"] = coef_macro
        salida.loc[mascara, "coef_pace"] = coef_pace
        salida.loc[mascara, "escala_adaptativa"] = escala
        salida.loc[mascara, "peso_ritmo_adaptativo"] = peso_ritmo
        salida.loc[mascara, "n_entrenamiento"] = n
        salida.loc[mascara, "fase_bajo_volumen"] = fase_cola
        salida.loc[mascara, "retencion_correccion"] = retencion
    return salida


def _reconciliar_empresa_fundos(
    tabla: pd.DataFrame,
    cfg: ConfiguracionNowcastCierre,
) -> pd.DataFrame:
    salida = tabla.copy()
    salida["candidate_kg"] = np.nan
    salida["recon_share_macro"] = np.nan
    salida["recon_share_montue"] = np.nan
    salida["recon_alpha"] = np.nan
    salida["recon_total_empresa_kg"] = np.nan
    salida["estado_nowcast"] = "datos_montue_insuficientes"
    salida["motivo_no_evaluable"] = "requiere_lunes_y_martes_completos"

    fechas = list(salida.fecha_objetivo.drop_duplicates().sort_values())
    for posicion, fecha in enumerate(fechas):
        indices = list(salida.index[salida.fecha_objetivo.eq(fecha)])
        bloque = salida.loc[indices]
        if not bool(bloque.montue_completo.all()):
            continue
        total_empresa = float(bloque.candidate_base_kg.sum())
        total_macro = float(bloque.macro_kg.clip(lower=0).sum())
        total_montue = float(bloque.montue_kg.clip(lower=0).sum())
        share_macro = (
            bloque.macro_kg.clip(lower=0).to_numpy(float) / total_macro
            if total_macro > 0
            else np.repeat(1.0 / len(indices), len(indices))
        )
        share_montue = (
            bloque.montue_kg.clip(lower=0).to_numpy(float) / total_montue
            if total_montue > 0
            else share_macro.copy()
        )
        evidencia = (
            1.0
            if cfg.shrink_reconciliacion_semanas <= 0
            else posicion / (posicion + cfg.shrink_reconciliacion_semanas)
        )
        alpha = cfg.peso_participacion_montue * evidencia
        if bool(bloque.fase_bajo_volumen.all()):
            alpha *= cfg.retencion_reconciliacion_cola
        if total_montue <= 0:
            alpha = 0.0
        alpha = float(np.clip(alpha, 0.0, 1.0))
        shares = (1.0 - alpha) * share_macro + alpha * share_montue
        shares = shares / float(shares.sum())
        asignacion = total_empresa * shares
        asignacion[-1] += total_empresa - float(asignacion.sum())

        salida.loc[indices, "candidate_kg"] = asignacion
        salida.loc[indices, "recon_share_macro"] = share_macro
        salida.loc[indices, "recon_share_montue"] = share_montue
        salida.loc[indices, "recon_alpha"] = alpha
        salida.loc[indices, "recon_total_empresa_kg"] = total_empresa
        salida.loc[indices, "estado_nowcast"] = "calculado"
        salida.loc[indices, "motivo_no_evaluable"] = None
    return salida


def calcular_nowcast_cierre_adaptativo(
    panel: pd.DataFrame,
    *,
    configuracion: ConfiguracionNowcastCierre = CONFIGURACION_CONGELADA,
) -> ResultadoNowcastCierre:
    """Calcula cierres online independientes por campania y auditables."""
    contrato = validar_contrato_asof(panel)
    bloques: list[pd.DataFrame] = []
    for _, campania in contrato.groupby("campania", sort=False):
        base = _estimar_total_adaptativo(campania.reset_index(drop=True), configuracion)
        bloques.append(_reconciliar_empresa_fundos(base, configuracion))
    predicciones = (
        pd.concat(bloques, ignore_index=True)
        .sort_values(["campania", "fecha_objetivo", "fundo_operativo"], kind="stable")
        .reset_index(drop=True)
    )
    empresa = predicciones.groupby(["campania", "fecha_objetivo"], as_index=False).agg(
        real_kg=("real_kg", "sum"),
        macro_kg=("macro_kg", "sum"),
        montue_kg=("montue_kg", "sum"),
        total_adaptativo_kg=("candidate_base_kg", "sum"),
        candidate_kg=("candidate_kg", lambda x: x.sum(min_count=1)),
        fondos=("fundo_operativo", "nunique"),
        fondos_montue_completos=("montue_completo", "sum"),
    )
    empresa["error_reconciliacion_kg"] = (empresa.candidate_kg - empresa.total_adaptativo_kg).abs()
    empresa["estado_nowcast"] = np.where(
        empresa.candidate_kg.notna(), "calculado", "datos_montue_insuficientes"
    )
    return ResultadoNowcastCierre(
        predicciones=predicciones,
        empresa=empresa,
        configuracion_id=configuracion.id,
        configuracion=asdict(configuracion),
    )


__all__ = [
    "COLUMNAS_REQUERIDAS",
    "CONFIGURACION_CONGELADA",
    "ConfiguracionNowcastCierre",
    "ContratoNowcastError",
    "ResultadoNowcastCierre",
    "calcular_nowcast_cierre_adaptativo",
    "validar_contrato_asof",
]
