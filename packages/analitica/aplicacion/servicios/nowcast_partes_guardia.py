"""Guardia jerárquica y reconciliación exacta por fundo."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from analitica.aplicacion.servicios.nowcast_partes_adaptativo import (
    BASE_CONGELADA,
    agregar_empresa,
    metricas,
)
from analitica.aplicacion.servicios.nowcast_partes_adaptativo import (
    bootstrap_pareado as _bootstrap_pareado,
)
from analitica.aplicacion.servicios.nowcast_partes_adaptativo import (
    construir_contrato as _construir_contrato_adaptativo,
)
from analitica.aplicacion.servicios.nowcast_partes_adaptativo import (
    predecir_online as _predecir_online,
)
from analitica.aplicacion.servicios.nowcast_partes_base import (
    ACCESS_DEFAULT,
    R09_ACCESS_DEFAULT,
    RUNS_CERTIFICADOS,
    diagnostico_shares,
    sha256_archivo,
)


@dataclass(frozen=True)
class ConfiguracionFundGuard:
    min_semanas_fundo: int
    shrink_evidencia: float
    ganancia_minima_pp: float
    retencion_maxima: float
    cambio_maximo_relativo: float

    @property
    def id(self) -> str:
        return (
            f"n{self.min_semanas_fundo}-k{self.shrink_evidencia:.0f}-"
            f"g{self.ganancia_minima_pp:.1f}-r{self.retencion_maxima:.2f}-"
            f"c{self.cambio_maximo_relativo:.2f}"
        )


@dataclass(frozen=True)
class ConfiguracionReconciliacionFundos:
    peso_participacion_montue: float
    shrink_semanas: float
    retencion_cola: float

    @property
    def id(self) -> str:
        return (
            f"pm{self.peso_participacion_montue:.2f}-"
            f"k{self.shrink_semanas:.0f}-tc{self.retencion_cola:.2f}"
        )


def _wape(tabla: pd.DataFrame, columna: str) -> float:
    denominador = float(tabla.real_kg.abs().sum())
    if not denominador:
        return np.nan
    return float((tabla[columna] - tabla.real_kg).abs().sum() / denominador)


def _evidencia_fundo(
    historia: pd.DataFrame,
    fundo: str,
    cfg: ConfiguracionFundGuard,
) -> tuple[bool, float, int, float]:
    local = historia.loc[
        historia.fundo_operativo.eq(fundo)
        & historia.real_kg.ge(0)
        & historia.macro_kg.notna()
        & historia.candidate_base_kg.notna()
    ].copy()
    n_semanas = int(local.fecha_objetivo.nunique())
    if n_semanas < cfg.min_semanas_fundo or float(local.real_kg.sum()) <= 0:
        return False, 0.0, n_semanas, np.nan
    wape_macro = _wape(local, "macro_kg")
    wape_base = _wape(local, "candidate_base_kg")
    ganancia_pp = float(100.0 * (wape_macro - wape_base))
    justifica = bool(ganancia_pp >= cfg.ganancia_minima_pp)
    retencion = min(
        cfg.retencion_maxima,
        n_semanas / (n_semanas + cfg.shrink_evidencia),
    )
    return justifica, float(retencion if justifica else 0.0), n_semanas, ganancia_pp


def _aplicar_guardia_online(
    prediccion_base: pd.DataFrame,
    cfg: ConfiguracionFundGuard,
) -> pd.DataFrame:
    """Aplica la guardia usando solo errores de fechas anteriores."""
    salida = (
        prediccion_base.sort_values(["fecha_objetivo", "fundo_operativo"], kind="stable")
        .reset_index(drop=True)
        .copy()
    )
    salida["candidate_base_kg"] = salida.candidate_kg.astype(float)
    salida["candidate_kg"] = salida.macro_kg.astype(float)
    salida["guard_retencion"] = 0.0
    salida["guard_n_semanas"] = 0
    salida["guard_ganancia_historica_pp"] = np.nan
    salida["guard_ruta"] = "macro_fallback"

    for fecha in salida.fecha_objetivo.drop_duplicates().sort_values():
        historia = salida.loc[salida.fecha_objetivo.lt(fecha)]
        for indice in salida.index[salida.fecha_objetivo.eq(fecha)]:
            fundo = str(salida.at[indice, "fundo_operativo"])
            justifica, retencion, n, ganancia = _evidencia_fundo(historia, fundo, cfg)
            salida.at[indice, "guard_n_semanas"] = n
            salida.at[indice, "guard_ganancia_historica_pp"] = ganancia
            if not justifica or retencion <= 0:
                continue
            macro = float(salida.at[indice, "macro_kg"])
            base = float(salida.at[indice, "candidate_base_kg"])
            limite = cfg.cambio_maximo_relativo * max(macro, 0.0)
            correccion = float(np.clip(base - macro, -limite, limite))
            salida.at[indice, "candidate_kg"] = max(0.0, macro + retencion * correccion)
            salida.at[indice, "guard_retencion"] = retencion
            salida.at[indice, "guard_ruta"] = "adaptive_shrunk"
    return salida


def _reconciliar_total_empresa_online(
    prediccion_base: pd.DataFrame,
    cfg: ConfiguracionReconciliacionFundos,
) -> pd.DataFrame:
    """Reparte el total adaptativo sin permitir que los fundos lo alteren."""
    salida = (
        prediccion_base.sort_values(["fecha_objetivo", "fundo_operativo"], kind="stable")
        .reset_index(drop=True)
        .copy()
    )
    salida["candidate_base_kg"] = salida.candidate_kg.astype(float)
    salida["candidate_kg"] = 0.0
    salida["recon_share_macro"] = np.nan
    salida["recon_share_montue"] = np.nan
    salida["recon_alpha"] = 0.0
    salida["recon_total_empresa_kg"] = np.nan
    salida["guard_ruta"] = "reconciliado_empresa"

    fechas = list(salida.fecha_objetivo.drop_duplicates().sort_values())
    for posicion, fecha in enumerate(fechas):
        indices = list(salida.index[salida.fecha_objetivo.eq(fecha)])
        bloque = salida.loc[indices]
        total_empresa = float(bloque.candidate_base_kg.sum())
        total_macro = float(bloque.macro_kg.clip(lower=0).sum())
        total_montue = float(bloque.montue_kg.clip(lower=0).sum())

        if total_macro > 0:
            share_macro = bloque.macro_kg.clip(lower=0).to_numpy(float) / total_macro
        else:
            share_macro = np.repeat(1.0 / len(indices), len(indices))
        if total_montue > 0:
            share_montue = bloque.montue_kg.clip(lower=0).to_numpy(float) / total_montue
        else:
            share_montue = share_macro.copy()

        evidencia = 1.0 if cfg.shrink_semanas <= 0 else posicion / (posicion + cfg.shrink_semanas)
        alpha = cfg.peso_participacion_montue * evidencia
        if "fase_bajo_volumen" in bloque and bool(bloque.fase_bajo_volumen.all()):
            alpha *= cfg.retencion_cola
        if total_montue <= 0:
            alpha = 0.0
        alpha = float(np.clip(alpha, 0.0, 1.0))

        shares = (1.0 - alpha) * share_macro + alpha * share_montue
        suma_share = float(shares.sum())
        shares = shares / suma_share if suma_share > 0 else share_macro
        asignacion = total_empresa * shares
        # Cierre numerico exacto: el ultimo fundo absorbe solo el residuo de
        # coma flotante, no una correccion estadistica.
        asignacion[-1] += total_empresa - float(asignacion.sum())

        salida.loc[indices, "candidate_kg"] = asignacion
        salida.loc[indices, "recon_share_macro"] = share_macro
        salida.loc[indices, "recon_share_montue"] = share_montue
        salida.loc[indices, "recon_alpha"] = alpha
        salida.loc[indices, "recon_total_empresa_kg"] = total_empresa
    return salida


def _deterioros_por_fundo(
    tabla: pd.DataFrame,
    referencia: str = "macro_kg",
) -> dict[str, dict[str, float | int]]:
    resultado: dict[str, dict[str, float | int]] = {}
    for fundo, bloque in tabla.groupby("fundo_operativo"):
        candidato = metricas(bloque, "candidate_kg")
        ref = metricas(bloque, referencia)
        resultado[str(fundo)] = {
            "wape_candidato": float(candidato["wape"]),
            "wape_referencia": float(ref["wape"]),
            "deterioro_pp": float(100.0 * (candidato["wape"] - ref["wape"])),
            "n": int(len(bloque)),
        }
    return resultado


def _max_deterioro(tabla: pd.DataFrame, referencia: str = "macro_kg") -> float:
    pareado = tabla.loc[tabla[referencia].notna()].copy()
    deterioros = _deterioros_por_fundo(pareado, referencia)
    return max((float(v["deterioro_pp"]) for v in deterioros.values()), default=0.0)


def _configuraciones_guardia() -> list[ConfiguracionFundGuard]:
    candidatas = [
        ConfiguracionFundGuard(n, k, g, r, c)
        for n in (2, 3, 4)
        for k in (2.0, 4.0, 8.0)
        for g in (0.0, 2.0, 5.0)
        for r in (0.50, 0.75, 1.00)
        for c in (0.35, 0.60)
    ]
    # Control seguro: reproduce Macro y garantiza que la busqueda nunca fuerce
    # una correccion que viole el limite por fundo.
    candidatas.append(ConfiguracionFundGuard(999, 8.0, 99.0, 0.0, 0.0))
    return candidatas


def _seleccionar_guardia(
    desarrollo_base: pd.DataFrame,
) -> tuple[ConfiguracionFundGuard, pd.DataFrame]:
    ranking: list[dict[str, float | int | str | bool]] = []
    candidatas = _configuraciones_guardia()
    for cfg in candidatas:
        pred = _aplicar_guardia_online(desarrollo_base, cfg)
        empresa = agregar_empresa(pred, ["candidate_kg"])
        met = metricas(empresa, "candidate_kg")
        max_det = _max_deterioro(pred)
        ranking.append(
            {
                "configuracion_id": cfg.id,
                **met,
                "max_deterioro_fundo_pp": max_det,
                "cumple_guardia_10pp": bool(max_det <= 10.0 + 1e-12),
            }
        )
    orden = pd.DataFrame(ranking)
    elegibles = orden.loc[orden.cumple_guardia_10pp & orden.sesgo.abs().le(0.15)].copy()
    if elegibles.empty:
        raise RuntimeError("Ninguna politica cumplio el limite de 10 pp por fundo")
    elegibles = elegibles.sort_values(
        ["wape", "max_deterioro_fundo_pp", "mae_kg"], kind="stable"
    ).reset_index(drop=True)
    ganador_id = str(elegibles.iloc[0].configuracion_id)
    ganador = next(cfg for cfg in candidatas if cfg.id == ganador_id)
    return ganador, elegibles


def _configuraciones_reconciliacion() -> list[ConfiguracionReconciliacionFundos]:
    return [
        ConfiguracionReconciliacionFundos(peso, shrink, cola)
        for peso in (0.0, 0.10, 0.25, 0.40, 0.60, 0.80, 1.0)
        for shrink in (0.0, 2.0, 4.0, 8.0)
        for cola in (0.25, 0.50, 1.0)
    ]


def _seleccionar_reconciliacion(
    desarrollo_base: pd.DataFrame,
) -> tuple[ConfiguracionReconciliacionFundos, pd.DataFrame]:
    """Elige shares en desarrollo; R09 no participa en la seleccion."""
    ranking: list[dict[str, float | int | str | bool]] = []
    candidatas = _configuraciones_reconciliacion()
    for cfg in candidatas:
        pred = _reconciliar_total_empresa_online(desarrollo_base, cfg)
        empresa = agregar_empresa(pred, ["candidate_kg"])
        met = metricas(empresa, "candidate_kg")
        max_det = _max_deterioro(pred)
        ranking.append(
            {
                "configuracion_id": cfg.id,
                **met,
                "wape_fundo_semana": _wape(pred, "candidate_kg"),
                "max_deterioro_fundo_pp": max_det,
                "cumple_guardia_10pp": bool(max_det <= 10.0 + 1e-12),
                "reconciliacion_max_error_kg": float(
                    pred.groupby("fecha_objetivo")
                    .apply(
                        lambda x: abs(
                            float(x.candidate_kg.sum()) - float(x.candidate_base_kg.sum())
                        ),
                        include_groups=False,
                    )
                    .max()
                ),
            }
        )
    orden = pd.DataFrame(ranking)
    elegibles = orden.loc[
        orden.cumple_guardia_10pp
        & orden.sesgo.abs().le(0.15)
        & orden.reconciliacion_max_error_kg.le(1e-6)
    ].copy()
    if elegibles.empty:
        raise RuntimeError("Ninguna reconciliacion cumplio el limite por fundo")
    elegibles = elegibles.sort_values(
        ["wape", "wape_fundo_semana", "max_deterioro_fundo_pp", "mae_kg"],
        kind="stable",
    ).reset_index(drop=True)
    ganador_id = str(elegibles.iloc[0].configuracion_id)
    ganador = next(cfg for cfg in candidatas if cfg.id == ganador_id)
    return ganador, elegibles


def _evaluar(tabla: pd.DataFrame) -> dict[str, object]:
    empresa = agregar_empresa(tabla, ["candidate_kg", "candidate_base_kg", "macro_kg"])
    return {
        "n_fundo_semana": int(len(tabla)),
        "n_semanas": int(tabla.fecha_objetivo.nunique()),
        "real_kg": float(tabla.real_kg.sum()),
        "guardia": metricas(empresa, "candidate_kg"),
        "adaptativo_sin_guardia": metricas(empresa, "candidate_base_kg"),
        "macro": metricas(empresa, "macro_kg"),
        "max_deterioro_fundo_vs_macro_pp": _max_deterioro(tabla),
        "max_deterioro_fundo_vs_r09_presemana_pp": _max_deterioro(tabla, "r09_presemana_kg"),
        "max_deterioro_fundo_vs_r09_misma_semana_pp": _max_deterioro(
            tabla, "r09_misma_semana_kg"
        ),
        "gate_fundos_vs_macro_10pp": bool(_max_deterioro(tabla) <= 10.0),
        "gate_fundos_vs_r09_presemana_10pp": bool(
            _max_deterioro(tabla, "r09_presemana_kg") <= 10.0
        ),
        "gate_fundos_vs_r09_misma_semana_10pp": bool(
            _max_deterioro(tabla, "r09_misma_semana_kg") <= 10.0
        ),
        "por_fundo_vs_macro": _deterioros_por_fundo(tabla),
        "pareado_vs_macro": _bootstrap_pareado(tabla, "macro_kg"),
        "pareado_vs_r09_presemana": _bootstrap_pareado(tabla, "r09_presemana_kg"),
        "pareado_vs_r09_misma_semana": _bootstrap_pareado(tabla, "r09_misma_semana_kg"),
        "rutas": {str(k): int(v) for k, v in tabla.guard_ruta.value_counts(dropna=False).items()},
        "reconciliacion_max_error_kg": (
            float(
                (
                    tabla.groupby("fecha_objetivo").candidate_kg.sum()
                    - tabla.groupby("fecha_objetivo").candidate_base_kg.sum()
                )
                .abs()
                .max()
            )
            if "recon_total_empresa_kg" in tabla
            else None
        ),
    }


def _hash_configuracion(
    base: object,
    guardia: ConfiguracionFundGuard,
    reconciliacion: ConfiguracionReconciliacionFundos,
) -> str:
    contenido = json.dumps(
        {
            "base": asdict(base),
            "guardia": asdict(guardia),
            "reconciliacion": asdict(reconciliacion),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def ejecutar_fund_guard(
    *,
    access: Path = ACCESS_DEFAULT,
    r09_access: Path = R09_ACCESS_DEFAULT,
) -> dict[str, object]:
    contratos = {
        campania: _construir_contrato_adaptativo(
            campania=campania,
            run_id=run_id,
            access=access,
            r09_access=r09_access,
        )
        for campania, run_id in RUNS_CERTIFICADOS.items()
    }
    base = {
        campania: _predecir_online(contrato, BASE_CONGELADA)
        for campania, contrato in contratos.items()
    }
    desarrollo_base = base["C2026"].loc[base["C2026"].semana_objetivo.le(30)].copy()
    guardia, ranking_guardia = _seleccionar_guardia(desarrollo_base)
    reconciliacion, ranking_reconciliacion = _seleccionar_reconciliacion(desarrollo_base)
    predicciones_guardia = {
        campania: _aplicar_guardia_online(pred, guardia) for campania, pred in base.items()
    }
    predicciones_reconciliadas = {
        campania: _reconciliar_total_empresa_online(pred, reconciliacion)
        for campania, pred in base.items()
    }
    desarrollo_guardia = predicciones_guardia["C2026"].loc[lambda x: x.semana_objetivo.le(30)]
    desarrollo_reconciliado = predicciones_reconciliadas["C2026"].loc[
        lambda x: x.semana_objetivo.le(30)
    ]
    wape_guardia = metricas(
        agregar_empresa(desarrollo_guardia, ["candidate_kg"]), "candidate_kg"
    )["wape"]
    wape_reconciliado = metricas(
        agregar_empresa(desarrollo_reconciliado, ["candidate_kg"]), "candidate_kg"
    )["wape"]
    if wape_reconciliado <= wape_guardia and _max_deterioro(desarrollo_reconciliado) <= 10.0:
        variante_seleccionada = "reconciliacion_total_empresa"
        predicciones = predicciones_reconciliadas
    else:
        variante_seleccionada = "guardia_local"
        predicciones = predicciones_guardia

    def evaluar_coleccion(coleccion: dict[str, pd.DataFrame]) -> dict[str, object]:
        c2026_local = coleccion["C2026"]
        return {
            "desarrollo_C2026_hasta_S30": _evaluar(
                c2026_local.loc[c2026_local.semana_objetivo.le(30)]
            ),
            "holdout_C2026_S31_S33": _evaluar(
                c2026_local.loc[c2026_local.semana_objetivo.between(31, 33)]
            ),
            "externa_C2024": _evaluar(coleccion["C2024"]),
            "externa_C2025": _evaluar(coleccion["C2025"]),
        }

    evaluaciones = evaluar_coleccion(predicciones)
    evaluaciones_guardia_local = evaluar_coleccion(predicciones_guardia)
    evaluaciones_reconciliacion = evaluar_coleccion(predicciones_reconciliadas)
    detalle_columnas = [
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
        "candidate_base_kg",
        "candidate_kg",
        "r09_presemana_kg",
        "r09_misma_semana_kg",
        "guard_retencion",
        "guard_n_semanas",
        "guard_ganancia_historica_pp",
        "recon_share_macro",
        "recon_share_montue",
        "recon_alpha",
        "recon_total_empresa_kg",
        "guard_ruta",
    ]
    for pred in predicciones.values():
        for columna in detalle_columnas:
            if columna not in pred:
                pred[columna] = np.nan
    return {
        "schema": "screening-adaptive-nowcast-fund-guard-v2",
        "producto": (
            "cierre intra-semanal adaptativo con guardia jerarquica y "
            "reconciliacion exacta por fundo"
        ),
        "variante_seleccionada": variante_seleccionada,
        "configuracion_base_congelada": {
            "id": BASE_CONGELADA.id,
            **asdict(BASE_CONGELADA),
        },
        "configuracion_guardia_congelada": {
            "id": guardia.id,
            **asdict(guardia),
        },
        "configuracion_reconciliacion_congelada": {
            "id": reconciliacion.id,
            **asdict(reconciliacion),
        },
        "configuracion_sha256": _hash_configuracion(BASE_CONGELADA, guardia, reconciliacion),
        "seleccion": (
            "solo C2026 <= S30; total empresa adaptativo fijo; shares Macro/"
            "Mon-Mar seleccionados por WAPE fundo-semana, sujetos a deterioro "
            "maximo por fundo <= 10 pp vs Macro; R09 solo auditoria posterior"
        ),
        "runs_macro": RUNS_CERTIFICADOS,
        "fuente_reales": str(access),
        "fuente_r09": str(r09_access),
        "sha256_fuente_reales": sha256_archivo(access),
        "sha256_fuente_r09": sha256_archivo(r09_access),
        "diagnostico_shares": {
            campania: diagnostico_shares(contrato) for campania, contrato in contratos.items()
        },
        "evaluaciones": evaluaciones,
        "evaluaciones_guardia_local": evaluaciones_guardia_local,
        "evaluaciones_reconciliacion": evaluaciones_reconciliacion,
        "ranking_desarrollo_guardia": ranking_guardia.head(30).to_dict("records"),
        "ranking_desarrollo_reconciliacion": ranking_reconciliacion.head(30).to_dict("records"),
        "detalle": {
            campania: pred[detalle_columnas].to_dict("records")
            for campania, pred in predicciones.items()
        },
        "r09_como_predictor": False,
        "persistencia_postgresql": False,
        "publicado_dashboard": False,
    }


__all__ = [
    "BASE_CONGELADA",
    "ConfiguracionFundGuard",
    "ConfiguracionReconciliacionFundos",
    "ejecutar_fund_guard",
]
