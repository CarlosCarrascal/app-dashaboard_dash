"""Servicio de screening de correctores simples por fundo-semana.

El servicio conserva la lógica histórica de
``screening_small_data_farm.py``: MacroLegacy se usa como estructura biológica,
la corrección se aprende solo con semanas cerradas antes de la emisión y R09
se incorpora después de predecir, únicamente para comparación.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
import psycopg
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from analitica.settings import postgres_dsn

RUNS_H1 = {"C2024": 76, "C2025": 78, "C2026": 76}
CIERRES = {
    "C2024": pd.Timestamp("2025-04-20"),
    "C2025": pd.Timestamp("2026-03-01"),
    "C2026": pd.Timestamp("2026-08-16"),
}
FUNDOS = ("Arena", "Ayllu", "Kawsay", "Quri")


@dataclass(frozen=True)
class Config:
    objetivo: str
    alpha: float
    limite_inferior: float
    limite_superior: float
    ventana_misma_campania: int
    incluir_clima: bool
    incluir_fenologia: bool


def _fundo(valor: object) -> str:
    clave = str(valor or "").strip().casefold()
    if clave in {"aqu anqa 1", "arena", "arena azul"}:
        return "Arena"
    if clave in {"aqu anqa 2", "quri", "quri allpa"}:
        return "Quri"
    if clave in {"aqu anqa 3", "aqu anqa 5", "kawsay", "kawsay allpa"}:
        return "Kawsay"
    if clave in {"aqu anqa 4", "ayllu", "ayllu allpa"}:
        return "Ayllu"
    return str(valor)


def _numero(componentes: object, clave: str) -> float:
    if not isinstance(componentes, dict):
        return np.nan
    valor = componentes.get(clave)
    try:
        return float(valor) if valor is not None else np.nan
    except (TypeError, ValueError):
        return np.nan


def leer_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    consulta = """
        SELECT campania, fecha_emision, fecha_objetivo, horizonte_semanas,
               lote_id, fundo, modulo, p50_kg, real_kg, plantas, componentes
        FROM analytics.prediction
        WHERE run_id=%s AND campania=%s AND modelo=%s
          AND horizonte_semanas=1 AND fecha_emision < fecha_objetivo
    """
    macros: list[pd.DataFrame] = []
    referencias: list[pd.DataFrame] = []
    with psycopg.connect(postgres_dsn()) as conexion:
        for campania, run_id in RUNS_H1.items():
            for modelo, destino in (
                ("MacroLegacy_v1", macros),
                ("R09_publicado", referencias),
            ):
                with conexion.cursor() as cursor:
                    cursor.execute(consulta, (run_id, campania, modelo))
                    columnas = [d.name for d in cursor.description]
                    tabla = pd.DataFrame(cursor.fetchall(), columns=columnas)
                tabla["fecha_emision"] = pd.to_datetime(tabla.fecha_emision).dt.normalize()
                tabla["fecha_objetivo"] = pd.to_datetime(tabla.fecha_objetivo).dt.normalize()
                tabla = tabla[
                    tabla.fecha_objetivo.add(pd.Timedelta(days=6)).le(CIERRES[campania])
                ].copy()
                destino.append(tabla)
    return pd.concat(macros, ignore_index=True), pd.concat(referencias, ignore_index=True)


def construir_fundo_semana(macro: pd.DataFrame) -> pd.DataFrame:
    t = macro.copy()
    t["fundo_operativo"] = t.fundo.map(_fundo)
    t["macro_activo"] = pd.to_numeric(t.p50_kg, errors="coerce").fillna(0).gt(0).astype(int)
    t["plantas"] = pd.to_numeric(t.plantas, errors="coerce").fillna(0)
    claves_componentes = (
        "flores",
        "frutos_muestra",
        "dias_desde_poda",
        "indice_estado",
        "gdd_7_0_7d",
        "gdd_7_0_28d",
        "temp_media_7d",
        "dpv_kpa_7d",
        "eto_7d",
        "kg_ultimas_4_semanas_asof",
        "real_acumulado",
    )
    for clave in claves_componentes:
        t[clave] = t.componentes.map(lambda x, k=clave: _numero(x, k))
    dimensiones = ["campania", "fecha_emision", "fecha_objetivo", "fundo_operativo"]
    semanal = t.groupby(dimensiones, as_index=False, dropna=False).agg(
        macro_kg=("p50_kg", "sum"),
        real_kg=("real_kg", "sum"),
        n_lotes=("lote_id", "nunique"),
        n_lotes_activos=("macro_activo", "sum"),
        plantas=("plantas", "sum"),
        flores=("flores", "sum"),
        frutos_muestra=("frutos_muestra", "sum"),
        dias_desde_poda=("dias_desde_poda", "median"),
        indice_estado=("indice_estado", "median"),
        gdd_7d=("gdd_7_0_7d", "median"),
        gdd_28d=("gdd_7_0_28d", "median"),
        temp_media_7d=("temp_media_7d", "median"),
        dpv_7d=("dpv_kpa_7d", "median"),
        eto_7d=("eto_7d", "median"),
        kg_ultimas_4=("kg_ultimas_4_semanas_asof", "sum"),
        real_acumulado_feature=("real_acumulado", "sum"),
    )
    semanal["semana_fin"] = semanal.fecha_objetivo + pd.Timedelta(days=6)
    semana_iso = semanal.fecha_objetivo.dt.isocalendar().week.astype(float)
    semanal["semana_sin"] = np.sin(2 * np.pi * semana_iso / 52.1775)
    semanal["semana_cos"] = np.cos(2 * np.pi * semana_iso / 52.1775)
    semanal["log_macro"] = np.log1p(semanal.macro_kg.clip(lower=0))
    semanal["log_plantas"] = np.log1p(semanal.plantas.clip(lower=0))
    semanal["prop_lotes_activos"] = semanal.n_lotes_activos.div(
        semanal.n_lotes.replace(0, np.nan)
    ).fillna(0)

    # Historia estrictamente disponible: una semana entra solo si cerró antes de
    # la fecha de emisión. No se usa la semana que está transcurriendo al emitir.
    historias: list[dict[str, float]] = []
    for _, fila in semanal.iterrows():
        h = semanal[
            semanal.fundo_operativo.eq(fila.fundo_operativo)
            & semanal.semana_fin.lt(fila.fecha_emision)
        ].sort_values("fecha_objetivo")
        misma = h[h.campania.eq(fila.campania)]
        ultimas = misma.tail(4)
        ultimo = misma.tail(1)
        ratio = (
            ultimas.real_kg.sum() / ultimas.macro_kg.sum() if ultimas.macro_kg.sum() > 0 else 1.0
        )
        historias.append(
            {
                "ultimo_real_cerrado": float(ultimo.real_kg.iloc[0]) if len(ultimo) else 0.0,
                "media_real_4": float(ultimas.real_kg.mean()) if len(ultimas) else 0.0,
                "ratio_real_macro_4": float(np.clip(ratio, 0.35, 2.5)),
                "n_cerradas_campania": float(len(misma)),
            }
        )
    semanal = pd.concat([semanal.reset_index(drop=True), pd.DataFrame(historias)], axis=1)
    semanal["log_ultimo_real"] = np.log1p(semanal.ultimo_real_cerrado)
    semanal["log_media_real_4"] = np.log1p(semanal.media_real_4)
    for fundo in FUNDOS:
        semanal[f"fundo_{fundo}"] = semanal.fundo_operativo.eq(fundo).astype(float)
    return semanal.sort_values(["fecha_objetivo", "fundo_operativo"]).reset_index(drop=True)


def _features(config: Config) -> list[str]:
    columnas = [
        "log_macro",
        "log_plantas",
        "prop_lotes_activos",
        "semana_sin",
        "semana_cos",
        "log_ultimo_real",
        "log_media_real_4",
        "ratio_real_macro_4",
        "n_cerradas_campania",
        *[f"fundo_{f}" for f in FUNDOS],
    ]
    if config.incluir_clima:
        columnas += ["gdd_7d", "gdd_28d", "temp_media_7d", "dpv_7d", "eto_7d"]
    if config.incluir_fenologia:
        columnas += ["flores", "frutos_muestra", "dias_desde_poda", "indice_estado", "kg_ultimas_4"]
    return columnas


def _clave_modelo(config: Config) -> tuple[object, ...]:
    """Identifica un ajuste Ridge; los límites se aplican después de predecir."""

    return (
        config.objetivo,
        config.alpha,
        config.ventana_misma_campania,
        config.incluir_clima,
        config.incluir_fenologia,
    )


def predecir_rolling(panel: pd.DataFrame, config: Config) -> pd.DataFrame:
    salidas: list[dict[str, object]] = []
    columnas = _features(config)
    ordenado = panel.sort_values(["fecha_emision", "fecha_objetivo", "fundo_operativo"])
    # Todos los fundos de una misma emisión/objetivo comparten exactamente el
    # mismo conjunto de entrenamiento. Ajustar una vez por grupo evita repetir
    # cuatro veces el mismo Ridge sin alterar el replay.
    for (_, _), grupo in ordenado.groupby(
        ["fecha_emision", "fecha_objetivo"], sort=True, dropna=False
    ):
        fila_referencia = grupo.iloc[0]
        entreno = panel[
            panel.semana_fin.lt(fila_referencia.fecha_emision) & panel.real_kg.notna()
        ].copy()
        # Se permite toda campaña histórica cerrada, pero dentro de la campaña
        # actual solo se retiene la historia reciente para adaptarse al manejo.
        anterior = entreno[entreno.campania.ne(fila_referencia.campania)]
        actual = (
            entreno[entreno.campania.eq(fila_referencia.campania)]
            .sort_values("fecha_objetivo")
            .groupby("fundo_operativo", group_keys=False)
            .tail(config.ventana_misma_campania)
        )
        entreno = pd.concat([anterior, actual], ignore_index=True).drop_duplicates(
            ["campania", "fecha_objetivo", "fundo_operativo"]
        )
        predicciones = grupo.macro_kg.astype(float).to_numpy(copy=True)
        if len(entreno) >= 24 and entreno.real_kg.gt(0).sum() >= 12:
            x_train = entreno[columnas].replace([np.inf, -np.inf], np.nan)
            medianas = x_train.median(numeric_only=True).fillna(0)
            x_train = x_train.fillna(medianas).fillna(0)
            x_test = grupo[columnas].replace([np.inf, -np.inf], np.nan)
            x_test = x_test.fillna(medianas).fillna(0)
            scaler = StandardScaler()
            xt = scaler.fit_transform(x_train)
            xv = scaler.transform(x_test)
            if config.objetivo == "log_real":
                y = np.log1p(entreno.real_kg.clip(lower=0))
                modelo = Ridge(alpha=config.alpha).fit(xt, y)
                predicciones = np.expm1(modelo.predict(xv))
            else:
                valido = entreno.macro_kg.gt(0) & entreno.real_kg.ge(0)
                if valido.sum() >= 12:
                    xt = scaler.fit_transform(x_train.loc[valido])
                    xv = scaler.transform(x_test)
                    y = np.log(
                        (entreno.loc[valido, "real_kg"] + 1) / (entreno.loc[valido, "macro_kg"] + 1)
                    )
                    modelo = Ridge(alpha=config.alpha).fit(xt, y)
                    factores = np.exp(modelo.predict(xv))
                    predicciones = grupo.macro_kg.astype(float).to_numpy() * factores
        for (_, fila), pred in zip(grupo.iterrows(), predicciones, strict=True):
            minimo = float(fila.macro_kg) * config.limite_inferior
            maximo = float(fila.macro_kg) * config.limite_superior
            if fila.macro_kg > 0:
                pred = float(np.clip(pred, minimo, maximo))
            else:
                pred = max(0.0, float(pred))
            salidas.append({**fila.to_dict(), "candidate_kg": pred})
    return pd.DataFrame(salidas)


def metricas_empresa(panel: pd.DataFrame, columna: str) -> dict[str, object]:
    semanal = panel.groupby(["campania", "fecha_emision", "fecha_objetivo"], as_index=False).agg(
        pred_kg=(columna, "sum"), real_kg=("real_kg", "sum")
    )
    error = semanal.pred_kg - semanal.real_kg
    denom = float(semanal.real_kg.abs().sum())
    return {
        "wape": float(error.abs().sum() / denom) if denom else np.nan,
        "sesgo": float(error.sum() / denom) if denom else np.nan,
        "mae_kg": float(error.abs().mean()),
        "n_semanas": int(len(semanal)),
    }


def comparar_r09(panel: pd.DataFrame, r09: pd.DataFrame, campania: str) -> dict[str, object]:
    c = (
        panel[panel.campania.eq(campania)]
        .groupby(["campania", "fecha_emision", "fecha_objetivo"], as_index=False)
        .agg(
            candidate_kg=("candidate_kg", "sum"),
            macro_kg=("macro_kg", "sum"),
            real_kg=("real_kg", "sum"),
        )
    )
    r = (
        r09[r09.campania.eq(campania)]
        .groupby(["campania", "fecha_emision", "fecha_objetivo"], as_index=False)
        .agg(r09_kg=("p50_kg", "sum"))
    )
    comun = c.merge(r, on=["campania", "fecha_emision", "fecha_objetivo"], validate="one_to_one")
    denom = float(comun.real_kg.abs().sum())
    salida: dict[str, object] = {"n": int(len(comun)), "por_modelo": {}}
    for nombre, columna in (
        ("candidate", "candidate_kg"),
        ("macro", "macro_kg"),
        ("r09", "r09_kg"),
    ):
        error = comun[columna] - comun.real_kg
        salida["por_modelo"][nombre] = {
            "wape": float(error.abs().sum() / denom) if denom else np.nan,
            "sesgo": float(error.sum() / denom) if denom else np.nan,
            "mae_kg": float(error.abs().mean()),
        }
    salida["semanas_ganadas_r09"] = float(
        ((comun.candidate_kg - comun.real_kg).abs() < (comun.r09_kg - comun.real_kg).abs()).mean()
    )
    return salida


def configuraciones() -> list[Config]:
    return [
        Config(objetivo, alpha, limites[0], limites[1], ventana, clima, fenologia)
        for objetivo in ("log_real", "residuo_log")
        for alpha in (1.0, 10.0, 50.0)
        for limites in ((0.70, 1.35), (0.85, 1.20))
        for ventana in (4, 8)
        for clima, fenologia in ((False, False), (True, False), (False, True), (True, True))
    ]


def ejecutar() -> dict[str, object]:
    macro, r09 = leer_panel()
    panel = construir_fundo_semana(macro)
    rankings: list[dict[str, object]] = []
    cache: dict[tuple[object, ...], pd.DataFrame] = {}
    for config in configuraciones():
        clave_modelo = _clave_modelo(config)
        if clave_modelo not in cache:
            # Predecir una sola vez por ajuste. El clip se recalcula abajo para
            # cada par de límites sin volver a entrenar.
            config_sin_clip = Config(
                config.objetivo,
                config.alpha,
                0.0,
                1e9,
                config.ventana_misma_campania,
                config.incluir_clima,
                config.incluir_fenologia,
            )
            cache[clave_modelo] = predecir_rolling(panel, config_sin_clip)
        pred = cache[clave_modelo].copy()
        macro_kg = pred.macro_kg.astype(float)
        pred["candidate_kg"] = np.where(
            macro_kg.gt(0),
            pred.candidate_kg.clip(
                lower=macro_kg * config.limite_inferior,
                upper=macro_kg * config.limite_superior,
            ),
            pred.candidate_kg.clip(lower=0),
        )
        desarrollo = metricas_empresa(pred[pred.campania.isin(["C2024", "C2025"])], "candidate_kg")
        clave_config = json.dumps(asdict(config), sort_keys=True)
        cache[clave_config] = pred
        rankings.append({"config": asdict(config), "desarrollo": desarrollo})
    rankings.sort(key=lambda x: (x["desarrollo"]["wape"], abs(x["desarrollo"]["sesgo"])))
    finalistas = []
    for fila in rankings[:8]:
        config = Config(**fila["config"])
        pred = cache[json.dumps(asdict(config), sort_keys=True)]
        finalistas.append(
            {
                **fila,
                "externo_c2026": comparar_r09(pred, r09, "C2026"),
                "ablacion": {
                    "clima": config.incluir_clima,
                    "fenologia": config.incluir_fenologia,
                },
            }
        )
    mejor = finalistas[0]
    return {
        "schema": "small-data-farm-candidate-v1",
        "runs": RUNS_H1,
        "cierres": {k: str(v.date()) for k, v in CIERRES.items()},
        "n_configuraciones": len(rankings),
        "seleccion": "solo C2024+C2025; C2026 externa",
        "ranking_desarrollo": rankings[:16],
        "finalistas": finalistas,
        "mejor": mejor,
        "publicable": False,
    }
