"""Replay ciego del corrector de ocurrencia sobre la curva operativa.

El modelo no sustituye la curva agronómica de ProySemanal. Estima si cada lote
realmente aporta volumen en la semana y cuánto aporta cuando ocurre; después
combina esa señal al 50 % con la curva base. Toda calibración usa exclusivamente
semanas anteriores a la semana objetivo.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

NOMBRE_MODELO = "HibridoOcurrenciaOnline_v1"
VERSION_MODELO = "hurdle_histgb_online_fund_equal_blend_v1"


@dataclass(frozen=True)
class ConfiguracionHibridoOcurrencia:
    semanas_calentamiento: int = 5
    peso_curva_legacy: float = 0.5
    escala_minima: float = 0.65
    escala_maxima: float = 1.60


def _fundo_operativo(valor: object) -> str:
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


def _preparar_panel(tabla: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    requeridas = {
        "campania",
        "fundo",
        "modulo",
        "lote",
        "lote_id",
        "fecha_emision",
        "fecha_objetivo",
        "p50_kg",
        "real_kg",
    }
    faltantes = sorted(requeridas.difference(tabla.columns))
    if faltantes:
        raise ValueError(f"Faltan columnas para el replay de ocurrencia: {faltantes}")

    panel = tabla.copy()
    panel["fecha_objetivo"] = pd.to_datetime(panel["fecha_objetivo"], errors="raise").dt.normalize()
    panel["fecha_emision"] = pd.to_datetime(panel["fecha_emision"], errors="raise").dt.normalize()
    if panel["fecha_emision"].ge(panel["fecha_objetivo"]).any():
        raise ValueError("El panel contiene una emisión contemporánea o posterior al objetivo")
    panel["semana_cierre"] = panel["fecha_objetivo"] + pd.Timedelta(days=6)
    panel["p50_kg"] = pd.to_numeric(panel["p50_kg"], errors="coerce").fillna(0.0).clip(lower=0)
    # NaN significa "resultado todavía desconocido". Convertirlo a cero aquí
    # hacía que una semana futura pareciera una semana observada sin cosecha y
    # contaminaba los rezagos, la ocurrencia y el acumulado.
    panel["real_kg"] = pd.to_numeric(panel["real_kg"], errors="coerce").clip(lower=0)
    panel["real_kg_observada"] = panel["real_kg"]
    panel["fundo_calibracion"] = panel["fundo"].map(_fundo_operativo)
    panel = panel.sort_values(
        ["campania", "lote_id", "fecha_objetivo", "fecha_emision"]
    ).reset_index(drop=True)

    panel["base_log"] = np.log1p(panel["p50_kg"])
    panel["semana_ordinal"] = (
        (panel["fecha_objetivo"] - panel["fecha_objetivo"].min()).dt.days // 7
    ).astype(float)
    for columna in ("fundo", "modulo", "lote"):
        niveles = {
            valor: indice
            for indice, valor in enumerate(sorted(panel[columna].astype(str).unique()))
        }
        panel[f"{columna}_codigo"] = panel[columna].astype(str).map(niveles).astype(float)

    # Las features de historia se construyen por lote y fecha objetivo, usando
    # únicamente fechas estrictamente anteriores. No usamos shift de filas:
    # varias emisiones pueden repetir el mismo lote-semana y una repetición no
    # es una nueva cosecha.
    columnas_historia = [
        "real_suma_4",
        "ocurrencia_4",
        "real_acumulado",
        "ocurre",
        *[f"real_lag_{i}" for i in range(1, 5)],
        *[f"base_lag_{i}" for i in range(1, 5)],
    ]
    for columna in columnas_historia:
        panel[columna] = np.nan

    for (_, _lote_id), indices in panel.groupby(["campania", "lote_id"], sort=False).groups.items():
        indices = list(indices)
        bloque = panel.loc[indices].sort_values(["fecha_objetivo", "fecha_emision"])
        observados = (
            bloque.loc[
                bloque["real_kg_observada"].notna(),
                ["fecha_objetivo", "real_kg_observada", "p50_kg"],
            ]
            .sort_values("fecha_objetivo")
            .groupby("fecha_objetivo", as_index=False)
            .agg(real_kg=("real_kg_observada", "first"), base_kg=("p50_kg", "first"))
        )
        observados["semana_cierre"] = observados["fecha_objetivo"] + pd.Timedelta(days=6)
        for indice in bloque.index:
            fecha = panel.at[indice, "fecha_objetivo"]
            # Una semana anterior sólo es información disponible si además ya
            # cerró antes de la emisión. El orden del calendario por sí solo no
            # basta cuando se emite dentro de la semana en curso.
            emision = panel.at[indice, "fecha_emision"]
            previo = observados.loc[
                observados["fecha_objetivo"].lt(fecha) & observados["semana_cierre"].lt(emision)
            ]
            if previo.empty:
                panel.at[indice, "real_suma_4"] = 0.0
                panel.at[indice, "ocurrencia_4"] = 0.0
                panel.at[indice, "real_acumulado"] = 0.0
            else:
                ultimos = previo.tail(4)
                panel.at[indice, "real_suma_4"] = float(ultimos["real_kg"].sum())
                panel.at[indice, "ocurrencia_4"] = float(ultimos["real_kg"].gt(0).mean())
                panel.at[indice, "real_acumulado"] = float(previo["real_kg"].sum())
                for rezago, (_, fila) in enumerate(previo.tail(4).iloc[::-1].iterrows(), start=1):
                    panel.at[indice, f"real_lag_{rezago}"] = float(fila["real_kg"])
                    panel.at[indice, f"base_lag_{rezago}"] = float(fila["base_kg"])
            # La etiqueta de ocurrencia solo es objetivo conocido para una fila
            # cuya cosecha ya está observada; nunca imputamos futuro como cero.
            valor_actual = panel.at[indice, "real_kg_observada"]
            if pd.notna(valor_actual):
                panel.at[indice, "ocurre"] = int(float(valor_actual) > 0)

    panel["real_kg"] = panel["real_kg_observada"]

    features = [
        "p50_kg",
        "base_log",
        "semana_ordinal",
        "fundo_codigo",
        "modulo_codigo",
        "real_suma_4",
        "ocurrencia_4",
        "real_acumulado",
        *[f"real_lag_{i}" for i in range(1, 5)],
        *[f"base_lag_{i}" for i in range(1, 5)],
    ]
    return panel, features


def _escala_por_fundo(
    historial_oos: pd.DataFrame,
    config: ConfiguracionHibridoOcurrencia,
    fecha_emision: pd.Timestamp | None = None,
) -> dict:
    historial_oos = historial_oos.loc[historial_oos["real_kg"].notna()].copy()
    if fecha_emision is not None and "semana_cierre" in historial_oos:
        historial_oos = historial_oos.loc[historial_oos["semana_cierre"].lt(fecha_emision)]
    if historial_oos.empty:
        return {}
    agregado = historial_oos.groupby("fundo_calibracion", dropna=False)[
        ["real_kg", "hurdle_raw"]
    ].sum()
    escala = agregado.real_kg.div(agregado.hurdle_raw.replace(0, np.nan)).fillna(1.0)
    return escala.clip(config.escala_minima, config.escala_maxima).to_dict()


def ejecutar_replay_hibrido_ocurrencia(
    curva_legacy: pd.DataFrame,
    config: ConfiguracionHibridoOcurrencia | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ejecuta rolling-origin; devuelve predicción lote-semana y resumen semanal."""
    config = config or ConfiguracionHibridoOcurrencia()
    if not 0 <= config.peso_curva_legacy <= 1:
        raise ValueError("peso_curva_legacy debe estar entre 0 y 1")
    panel, features = _preparar_panel(curva_legacy)
    fechas = sorted(panel["fecha_objetivo"].dropna().unique())
    if len(fechas) <= config.semanas_calentamiento:
        return pd.DataFrame(), pd.DataFrame()

    salidas: list[pd.DataFrame] = []
    historial_oos = pd.DataFrame(
        columns=["fundo_calibracion", "real_kg", "hurdle_raw", "semana_cierre"]
    )
    for fecha in fechas[config.semanas_calentamiento :]:
        prueba = panel[panel.fecha_objetivo.eq(fecha)].copy()
        # Entrenar para la fecha de prueba más temprana evita que una misma
        # emisión reciba etiquetas de semanas que aún no estaban cerradas.
        emision_minima = prueba["fecha_emision"].min()
        entrenamiento = panel.loc[
            panel["fecha_objetivo"].lt(fecha) & panel["semana_cierre"].lt(emision_minima)
        ].copy()
        # El panel puede contener semanas futuras cuyo real todavía no existe.
        # Esas filas sirven para construir la prueba/curva, pero nunca pueden
        # entrar al ajuste del clasificador como una etiqueta NaN.
        entrenamiento_modelo = entrenamiento.loc[entrenamiento["ocurre"].notna()].copy()
        y_train = entrenamiento_modelo["ocurre"].astype(int)
        x_train = entrenamiento_modelo[features].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        x_test = prueba[features].replace([np.inf, -np.inf], np.nan).fillna(0.0)

        if y_train.nunique() < 2:
            probabilidad = np.repeat(
                float(y_train.mean()) if not y_train.empty else 0.0, len(prueba)
            )
        else:
            clasificador = HistGradientBoostingClassifier(
                max_iter=80,
                max_leaf_nodes=15,
                min_samples_leaf=30,
                l2_regularization=2.0,
                learning_rate=0.06,
                random_state=7,
            )
            clasificador.fit(x_train, y_train)
            probabilidad = clasificador.predict_proba(x_test)[:, 1]

        positivos = entrenamiento_modelo[entrenamiento_modelo.real_kg.gt(0)]
        if len(positivos) < 20:
            valor_positivo = np.repeat(
                float(positivos.real_kg.median()) if not positivos.empty else 0.0, len(prueba)
            )
        else:
            regresor = HistGradientBoostingRegressor(
                loss="poisson",
                max_iter=100,
                max_leaf_nodes=15,
                min_samples_leaf=25,
                l2_regularization=5.0,
                learning_rate=0.05,
                random_state=7,
            )
            regresor.fit(positivos[features].fillna(0.0), positivos.real_kg)
            valor_positivo = regresor.predict(x_test).clip(min=0)

        # La calibración volumétrica se actualiza únicamente con predicciones OOS de
        # semanas anteriores. Reescalar sobre el propio entrenamiento reducía el error
        # aparente dentro de muestra, pero no mejoró el replay ciego.
        escala_entrenamiento = 1.0

        prueba["kg_legacy_base"] = prueba["p50_kg"]
        prueba["probabilidad_ocurrencia"] = np.clip(probabilidad, 0.0, 1.0)
        prueba["kg_si_ocurre"] = np.clip(valor_positivo, 0.0, None)
        prueba["escala_entrenamiento"] = escala_entrenamiento
        prueba["hurdle_raw"] = (
            prueba.probabilidad_ocurrencia * prueba.kg_si_ocurre * escala_entrenamiento
        )
        escalas = _escala_por_fundo(historial_oos, config, emision_minima)
        prueba["escala_online_fundo"] = prueba.fundo_calibracion.map(escalas).fillna(1.0)
        prueba["hurdle_calibrado"] = prueba.hurdle_raw * prueba.escala_online_fundo
        prueba["p50_hibrido"] = (
            config.peso_curva_legacy * prueba.p50_kg
            + (1 - config.peso_curva_legacy) * prueba.hurdle_calibrado
        ).clip(lower=0)
        prueba["semanas_entrenamiento"] = entrenamiento.fecha_objetivo.nunique()
        salidas.append(prueba)
        # Sólo una cosecha ya observada puede enseñar al corrector online.
        # Las semanas futuras se conservan en la salida, pero no entran en la
        # escala por fundo ni en el feedback de emisiones posteriores.
        nuevo_historial = prueba.loc[
            prueba["real_kg"].notna(),
            ["fundo_calibracion", "real_kg", "hurdle_raw", "semana_cierre"],
        ]
        historial_oos = (
            nuevo_historial.reset_index(drop=True)
            if historial_oos.empty
            else pd.concat([historial_oos, nuevo_historial], ignore_index=True)
        )

    detalle = pd.concat(salidas, ignore_index=True)
    detalle["modelo"] = NOMBRE_MODELO
    detalle["version_modelo"] = VERSION_MODELO
    detalle["p50_kg"] = detalle.pop("p50_hibrido")
    detalle["p10_kg"] = np.nan
    detalle["p90_kg"] = np.nan
    detalle["confianza"] = "baja"
    detalle["tipo_prediccion"] = "replay"
    detalle["es_replay_ciego"] = True
    detalle["es_curva_stitched"] = True
    detalle["estado_evaluacion"] = "evaluada"
    detalle["origen_emision"] = detalle["fecha_emision"]
    detalle["componentes"] = detalle.apply(
        lambda fila: {
            "modelo_base": "MacroLegacy_v1",
            "kg_legacy": float(fila.kg_legacy_base),
            "probabilidad_ocurrencia": float(fila.probabilidad_ocurrencia),
            "kg_si_ocurre": float(fila.kg_si_ocurre),
            "kg_hurdle_calibrado": float(fila.hurdle_calibrado),
            "escala_online_fundo": float(fila.escala_online_fundo),
            "escala_entrenamiento": float(fila.escala_entrenamiento),
            "peso_legacy": config.peso_curva_legacy,
            "semanas_entrenamiento": int(fila.semanas_entrenamiento),
            "etiqueta_causal": False,
        },
        axis=1,
    )
    resumen = detalle.groupby("fecha_objetivo", as_index=False).agg(
        real_kg=("real_kg", lambda valores: valores.sum(min_count=1)),
        p50_kg=("p50_kg", "sum"),
        n_lotes=("lote_id", "nunique"),
    )
    return detalle, resumen


def metricas_semanales(resumen: pd.DataFrame) -> dict[str, float]:
    real = resumen.real_kg.to_numpy(float)
    pred = resumen.p50_kg.to_numpy(float)
    denominador = float(np.abs(real).sum())
    return {
        "wape": float(np.abs(pred - real).sum() / denominador) if denominador else np.nan,
        "mae_kg": float(np.abs(pred - real).mean()) if len(real) else np.nan,
        "sesgo_pct": float((pred - real).sum() / denominador * 100) if denominador else np.nan,
        "volumen_real_kg": float(real.sum()),
        "volumen_proyectado_kg": float(pred.sum()),
        "n_semanas": int(len(resumen)),
    }
