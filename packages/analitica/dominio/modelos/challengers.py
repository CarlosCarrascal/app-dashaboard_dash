"""Challengers estadísticos, de ML y fenológicos bajo cortes temporales comunes."""

from __future__ import annotations

import warnings
from collections.abc import Callable

import numpy as np
import pandas as pd

FEATURES_CORRECCION = [
    "p50_kg",
    "horizonte_semanas",
    "plantas",
    "frutos_por_planta",
    "peso_baya_g",
    "semana_objetivo_sin",
    "semana_objetivo_cos",
]


def _calibrar_intervalos(predicciones: pd.DataFrame, minimo: int = 30) -> pd.DataFrame:
    salida = predicciones.copy().sort_values("fecha_emision")
    salida["p10_kg"] = np.nan
    salida["p90_kg"] = np.nan
    salida["n_calibracion"] = 0
    for modelo in salida.modelo.unique():
        mascara_modelo = salida.modelo == modelo
        fechas = sorted(salida.loc[mascara_modelo, "fecha_emision"].unique())
        for fecha in fechas:
            actual = mascara_modelo & salida.fecha_emision.eq(fecha)
            pasadas = salida[
                mascara_modelo & salida.fecha_emision.lt(fecha) & salida.real_kg.notna()
            ]
            residuos = (pasadas.real_kg - pasadas.p50_kg).dropna()
            n = len(residuos)
            pred = salida.loc[actual, "p50_kg"]
            if n >= minimo:
                q10, q90 = residuos.quantile([0.1, 0.9])
                salida.loc[actual, "p10_kg"] = np.minimum(pred, (pred + q10).clip(lower=0))
                salida.loc[actual, "p90_kg"] = np.maximum(pred, pred + q90)
            else:
                salida.loc[actual, "p10_kg"] = 0.5 * pred
                salida.loc[actual, "p90_kg"] = 1.5 * pred
            salida.loc[actual, "n_calibracion"] = n
    salida["confianza"] = np.where(salida.n_calibracion >= 50, "media", "baja")
    return salida


def intervalos_enbpi(
    estimador,
    x_entrenamiento: np.ndarray,
    y_entrenamiento: np.ndarray,
    x_prueba: np.ndarray,
    confianza: float = 0.80,
    bloques: int = 10,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Intervalos conformales secuenciales MAPIE/EnbPI para un estimador compatible.

    El bootstrap preserva bloques temporales y, por diseño, solo recibe el conjunto de
    entrenamiento del fold. La función se mantiene separada del torneo para poder auditar
    la calibración de intervalos sin confundirla con la selección del modelo puntual.
    """
    try:
        from mapie.regression import TimeSeriesRegressor
        from mapie.subsample import BlockBootstrap
    except ImportError as exc:  # pragma: no cover - depende del extra de producción
        raise RuntimeError("Instale MAPIE para habilitar intervalos EnbPI.") from exc

    n = len(y_entrenamiento)
    if n < 20:
        raise ValueError("EnbPI requiere al menos 20 observaciones de entrenamiento.")
    longitud = max(2, min(n // max(2, bloques), n // 2))
    cv = BlockBootstrap(
        n_resamplings=30,
        length=longitud,
        overlapping=True,
        random_state=42,
    )
    modelo = TimeSeriesRegressor(
        estimator=estimador,
        method="enbpi",
        cv=cv,
        n_jobs=-1,
        agg_function="mean",
        random_state=42,
    )
    modelo.fit(x_entrenamiento, y_entrenamiento)
    p50, intervalo = modelo.predict(
        x_prueba,
        ensemble=True,
        confidence_level=confianza,
        allow_infinite_bounds=True,
    )
    # MAPIE 1.x devuelve (n, 2, niveles); la última dimensión corresponde al nivel pedido.
    return p50, intervalo[:, 0, -1], intervalo[:, 1, -1]


def challenger_componentes_publicados(r09: pd.DataFrame) -> pd.DataFrame:
    """No entrena nada: reexpresa la aritmética interna del propio R09.

    Toma `frutos_total × peso_baya / 1000` tal como los publica el forecast y los compara
    contra su kg publicado, así que mide la consistencia interna de R09 y no la calidad de
    un modelo. **No incluye el factor plantas**, de modo que no es comparable con la
    identidad de tres factores de `componentes.py`.

    Antes se llamaba `Fenologico_componentes` y declaraba `version_fuente="plantas×frutos×
    peso"`, una fórmula que no es la que calcula. El nombre sugería además un modelo
    fenológico entrenado que nunca existió.
    """
    base = r09[r09.modelo == "R09_publicado"].copy()
    base = base[base.kg_componentes.notna()].copy()
    base["modelo"] = "R09_componentes_publicados"
    base["version_fuente"] = "frutos_total×peso_baya/1000"
    base["p50_kg"] = base.kg_componentes.clip(lower=0)
    base["supuesto_modelo"] = (
        "frutos_total y peso_baya son los publicados por R09; no interviene el número de "
        "plantas, así que no reconstruye la identidad completa del rendimiento"
    )
    return _calibrar_intervalos(base)


# Alias de compatibilidad para un ciclo, por si algún consumidor externo lo importaba por
# el nombre viejo. Las filas ya persistidas conservan `Fenologico_componentes`; no se
# reescribe el histórico.
challenger_fenologico = challenger_componentes_publicados


def challenger_combinacion(
    predicciones: pd.DataFrame,
    minimo_historial: int = 30,
) -> pd.DataFrame:
    """Combinación inversa al MAE calibrada únicamente con emisiones ya resueltas.

    Para cada fecha y banda, los pesos usan errores de objetivos terminados antes de la
    emisión. El candidato solo se produce cuando existen al menos dos modelos comparables;
    por tanto puede entrar al mismo torneo sin obtener información privilegiada.
    """
    if predicciones.empty:
        return pd.DataFrame(columns=predicciones.columns)
    claves = ["campania", "lote_id", "fecha_emision", "fecha_objetivo"]
    base = predicciones.copy()
    salidas = []
    for (fecha, banda), actuales in base.groupby(["fecha_emision", "banda_horizonte"], sort=True):
        pasado = base[
            (base.fecha_objetivo < fecha)
            & (base.banda_horizonte == banda)
            & base.real_kg.notna()
            & base.p50_kg.notna()
        ].copy()
        errores = (
            pasado.assign(error=(pasado.real_kg - pasado.p50_kg).abs())
            .groupby("modelo")
            .agg(mae=("error", "mean"), n=("error", "size"))
        )
        errores = errores[(errores.n >= minimo_historial) & errores.mae.gt(0)]
        modelos = sorted(set(actuales.modelo).intersection(errores.index))
        if len(modelos) < 2:
            continue
        pesos = (1 / errores.loc[modelos, "mae"]).rename("peso")
        pesos = pesos / pesos.sum()
        candidatos = actuales[actuales.modelo.isin(modelos)].copy()
        conteos = candidatos.groupby(claves).modelo.nunique()
        completas = conteos[conteos == len(modelos)].index
        if completas.empty:
            continue
        candidatos = candidatos.set_index(claves).loc[completas].reset_index()
        candidatos["peso_modelo"] = candidatos.modelo.map(pesos)
        metadata = (
            candidatos.sort_values("modelo")
            .drop_duplicates(claves)
            .set_index(claves)
            .drop(columns=["modelo", "p10_kg", "p50_kg", "p90_kg"], errors="ignore")
        )
        cuantiles = (
            candidatos.assign(
                p10_kg=candidatos.p10_kg * candidatos.peso_modelo,
                p50_kg=candidatos.p50_kg * candidatos.peso_modelo,
                p90_kg=candidatos.p90_kg * candidatos.peso_modelo,
            )
            .groupby(claves)[["p10_kg", "p50_kg", "p90_kg"]]
            .sum(min_count=len(modelos))
        )
        nueva = metadata.join(cuantiles).reset_index()
        # La metadata se hereda de una de las filas combinadas, así que puede arrastrar las
        # marcas de autoría de un modelo que sí estima componentes. Sus kilos son una media
        # ponderada y no el producto de esas piezas, de modo que mantener la declaración
        # haría que el control de identidad le exigiera una coherencia que no puede tener.
        nueva = nueva.drop(
            columns=[
                "base_plantas",
                "familia_frutos",
                "familia_peso",
                "filas_con_gate_cero",
                "n_entrenamiento_frutos",
                "n_entrenamiento_peso",
                "supuesto_modelo",
            ],
            errors="ignore",
        )
        nueva["modelo"] = "Combinacion_ponderada"
        nueva["version_fuente"] = "pesos_mae_asof"
        nueva["confianza"] = "media"
        nueva["modelos_combinados"] = ",".join(modelos)
        nueva["pesos_combinacion"] = ",".join(f"{modelo}:{pesos[modelo]:.6f}" for modelo in modelos)
        salidas.append(nueva)
    if not salidas:
        return pd.DataFrame(columns=predicciones.columns)
    salida = pd.concat(salidas, ignore_index=True, sort=False)
    salida["p10_kg"] = np.minimum(salida.p10_kg, salida.p50_kg)
    salida["p90_kg"] = np.maximum(salida.p90_kg, salida.p50_kg)
    return salida


def _preparar_features(tabla: pd.DataFrame) -> pd.DataFrame:
    x = tabla.copy()
    semana = x.fecha_objetivo.dt.isocalendar().week.astype(float)
    x["semana_objetivo_sin"] = np.sin(2 * np.pi * semana / 52.18)
    x["semana_objetivo_cos"] = np.cos(2 * np.pi * semana / 52.18)
    return x


def _imputar(
    entreno: pd.DataFrame, prueba: pd.DataFrame, features: list[str] | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Imputa con las medianas del entrenamiento, nunca con las del conjunto completo.

    `features` se parametriza para que la familia de componentes pueda reutilizar esto con
    su propio juego de variables; por omisión mantiene el de la corrección residual.
    """
    columnas = list(features or FEATURES_CORRECCION)
    medianas = entreno[columnas].median().fillna(0)
    return (
        entreno[columnas].fillna(medianas).to_numpy(float),
        prueba[columnas].fillna(medianas).to_numpy(float),
    )


def _fabricas_modelos() -> dict[str, list[Callable[[], object]]]:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from xgboost import XGBRegressor

    return {
        "Ridge": [
            lambda: make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
            lambda: make_pipeline(StandardScaler(), Ridge(alpha=10.0)),
        ],
        "Random_Forest": [
            lambda: RandomForestRegressor(
                n_estimators=120,
                max_depth=8,
                min_samples_leaf=8,
                max_features=0.8,
                random_state=42,
                n_jobs=1,
            ),
            lambda: RandomForestRegressor(
                n_estimators=120,
                max_depth=12,
                min_samples_leaf=15,
                max_features=0.7,
                random_state=42,
                n_jobs=1,
            ),
        ],
        "XGBoost": [
            lambda: XGBRegressor(
                n_estimators=160,
                max_depth=4,
                learning_rate=0.04,
                min_child_weight=10,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_lambda=5,
                objective="reg:squarederror",
                random_state=42,
                n_jobs=1,
            ),
            lambda: XGBRegressor(
                n_estimators=120,
                max_depth=3,
                learning_rate=0.06,
                min_child_weight=15,
                subsample=0.9,
                colsample_bytree=0.9,
                reg_lambda=10,
                objective="reg:squarederror",
                random_state=42,
                n_jobs=1,
            ),
        ],
    }


def _elegir_anidado_etiquetado(
    candidatos: list[tuple[str, Callable[[], object]]],
    entrenamiento: pd.DataFrame,
    *,
    y_fn: Callable[[pd.DataFrame], np.ndarray],
    features: list[str],
    minimo_train: int = 100,
) -> tuple[str, Callable[[], object], float]:
    """Elige candidato con el último bloque temporal del entrenamiento; nunca K-fold.

    El corte es por `fecha_objetivo`, así que la parte de validación interna es siempre
    posterior a la de ajuste: una partición aleatoria dejaría semanas futuras dentro del
    entrenamiento y elegiría el candidato que mejor se aprende el futuro.

    Devuelve además la etiqueta del ganador, para poder auditar qué familia se eligió en
    cada emisión sin tener que emitirlas todas como modelos separados.
    """
    etiqueta_defecto, fabrica_defecto = candidatos[0]
    fechas = np.array(sorted(entrenamiento.fecha_objetivo.unique()))
    if len(fechas) < 5:
        return etiqueta_defecto, fabrica_defecto, np.nan
    corte = fechas[max(1, int(len(fechas) * 0.8))]
    train = entrenamiento[entrenamiento.fecha_objetivo < corte]
    valid = entrenamiento[entrenamiento.fecha_objetivo >= corte]
    if len(train) < minimo_train or valid.empty:
        return etiqueta_defecto, fabrica_defecto, np.nan
    x_train, x_valid = _imputar(train, valid, features)
    y_train = y_fn(train)
    y_valid = y_fn(valid)
    mejor_etiqueta, mejor, mejor_mae = etiqueta_defecto, fabrica_defecto, np.inf
    for etiqueta, fabrica in candidatos:
        modelo = fabrica()
        modelo.fit(x_train, y_train)
        valor = float(np.mean(np.abs(y_valid - modelo.predict(x_valid))))
        if valor < mejor_mae:
            mejor_etiqueta, mejor, mejor_mae = etiqueta, fabrica, valor
    return mejor_etiqueta, mejor, mejor_mae


def _elegir_anidado(
    fabricas: list[Callable[[], object]], entrenamiento: pd.DataFrame
) -> tuple[Callable[[], object], float]:
    """Selección para la corrección residual; conserva la firma que ya consumen los tests."""
    _, fabrica, mae_interno = _elegir_anidado_etiquetado(
        [("", f) for f in fabricas],
        entrenamiento,
        y_fn=lambda t: (t.real_kg - t.p50_kg).to_numpy(float),
        features=FEATURES_CORRECCION,
    )
    return fabrica, mae_interno


def challengers_ml(r09: pd.DataFrame, minimo_entrenamiento: int = 500) -> pd.DataFrame:
    """Corrección residual rolling-origin de R09 con Ridge, RF y XGBoost.

    Para una emisión, el entrenamiento solo admite objetivos terminados antes de emitir;
    por tanto tampoco aprende el error de forecasts previos cuyo resultado aún no existía.
    """
    base = _preparar_features(r09[r09.modelo == "R09_publicado"].copy())
    salidas = []
    for fecha, prueba in base.groupby("fecha_emision", sort=True):
        entreno = base[(base.fecha_objetivo < fecha) & base.real_kg.notna()].copy()
        if len(entreno) < minimo_entrenamiento:
            continue
        x_train, x_test = _imputar(entreno, prueba)
        residual = (entreno.real_kg - entreno.p50_kg).to_numpy(float)
        for nombre, fabricas in _fabricas_modelos().items():
            fabrica, mae_interno = _elegir_anidado(fabricas, entreno)
            modelo = fabrica()
            modelo.fit(x_train, residual)
            nueva = prueba.copy()
            nueva["p50_kg"] = np.maximum(0, prueba.p50_kg + modelo.predict(x_test))
            nueva["modelo"] = nombre
            nueva["version_fuente"] = "correccion_residual_nested_rolling"
            nueva["mae_fold_interno"] = mae_interno
            salidas.append(nueva)
    if not salidas:
        return pd.DataFrame(columns=r09.columns)
    return _calibrar_intervalos(pd.concat(salidas, ignore_index=True))


def entrenar_challengers_finales(
    r09: pd.DataFrame, minimo_entrenamiento: int = 500
) -> dict[str, tuple[object, pd.DataFrame, pd.Series]]:
    """Ajusta artefactos finales sobre errores observables antes de la última emisión."""
    base = _preparar_features(r09[r09.modelo == "R09_publicado"].copy())
    if base.empty:
        return {}
    ultima = base.fecha_emision.max()
    entreno = base[(base.fecha_objetivo < ultima) & base.real_kg.notna()].copy()
    if len(entreno) < minimo_entrenamiento:
        return {}
    medianas = entreno[FEATURES_CORRECCION].median().fillna(0)
    x = entreno[FEATURES_CORRECCION].fillna(medianas)
    y = entreno.real_kg - entreno.p50_kg
    resultado = {}
    for nombre, fabricas in _fabricas_modelos().items():
        fabrica, _ = _elegir_anidado(fabricas, entreno)
        modelo = fabrica().fit(x, y)
        resultado[nombre] = (modelo, x, y)
    return resultado


def challengers_statsforecast(
    r09: pd.DataFrame, cosecha: pd.DataFrame, max_cortes: int = 8
) -> pd.DataFrame:
    """Modelos Nixtla en cortes externos representativos y con elegibilidad explícita.

    AutoARIMA por lote es costoso y no es identificable en series cortas/constantes. Se
    muestrean hasta ocho emisiones distribuidas en el tiempo y la regla de promoción mide
    la cobertura contra todo R09; por ello esta evaluación parcial nunca queda disimulada.
    """
    try:
        from statsforecast import StatsForecast
        from statsforecast.models import (
            ADIDA,
            AutoARIMA,
            AutoETS,
            CrostonClassic,
        )
    except ImportError as exc:  # pragma: no cover - depende del extra de producción
        raise RuntimeError("Instale el paquete analítico para habilitar StatsForecast.") from exc

    h = cosecha.copy()
    h["ds"] = pd.to_datetime(h.fecha).dt.normalize()
    h["ds"] = h.ds - pd.to_timedelta(h.ds.dt.weekday, unit="D")
    h = (
        h.groupby(["lote_id", "ds"], as_index=False)
        .kg.sum()
        .rename(columns={"lote_id": "unique_id", "kg": "y"})
    )
    objetivos = r09[r09.modelo == "R09_publicado"].copy()
    fechas = np.array(sorted(objetivos.fecha_emision.unique()))
    if len(fechas) > max_cortes:
        indices = np.linspace(0, len(fechas) - 1, max_cortes, dtype=int)
        objetivos = objetivos[objetivos.fecha_emision.isin(fechas[np.unique(indices)])]
    salidas = []
    for fecha, prueba in objetivos.groupby("fecha_emision", sort=True):
        ids = prueba.lote_id.dropna().unique()
        inicio = max(h.ds.min(), fecha - pd.Timedelta(weeks=104))
        semanas = pd.date_range(inicio, fecha - pd.Timedelta(weeks=1), freq="W-MON")
        rejilla = pd.MultiIndex.from_product([ids, semanas], names=["unique_id", "ds"])
        entreno = h[(h.unique_id.isin(ids)) & (h.ds < fecha)].set_index(["unique_id", "ds"])
        entreno = entreno.reindex(rejilla, fill_value=0).reset_index()
        if entreno.empty or len(semanas) < 10:
            continue
        elegibilidad = entreno.groupby("unique_id").y.agg(
            positivas=lambda s: int((s > 0).sum()), desviacion="std"
        )
        grupos_modelo = [
            (entreno, [CrostonClassic(), ADIDA()], ["CrostonClassic", "ADIDA"]),
            (
                entreno[
                    entreno.unique_id.isin(
                        elegibilidad[
                            (elegibilidad.positivas >= 12) & elegibilidad.desviacion.gt(0)
                        ].index
                    )
                ],
                [AutoETS(season_length=1)],
                ["AutoETS"],
            ),
            (
                entreno[
                    entreno.unique_id.isin(
                        elegibilidad[
                            (elegibilidad.positivas >= 26) & elegibilidad.desviacion.gt(0)
                        ].index
                    )
                ],
                [
                    AutoARIMA(
                        season_length=1,
                        seasonal=False,
                        max_p=2,
                        max_q=2,
                        max_order=4,
                        approximation=True,
                        nmodels=10,
                    )
                ],
                ["AutoARIMA"],
            ),
        ]
        for entreno_modelo, modelos, nombres in grupos_modelo:
            if entreno_modelo.empty:
                continue
            # Un proceso evita que Windows replique SciPy/Numba por cada CPU y agote el
            # archivo de paginación. Las advertencias de convergencia quedan representadas
            # por menor cobertura; no se imprimen miles de veces en la ejecución.
            sf = StatsForecast(models=modelos, freq="W-MON", n_jobs=1)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                pronostico = sf.forecast(df=entreno_modelo, h=10)
            for nombre in nombres:
                candidato = prueba.merge(
                    pronostico[["unique_id", "ds", nombre]],
                    left_on=["lote_id", "fecha_objetivo"],
                    right_on=["unique_id", "ds"],
                    how="left",
                )
                candidato = candidato[candidato[nombre].notna()].copy()
                candidato["p50_kg"] = candidato[nombre].clip(lower=0)
                candidato["modelo"] = nombre
                candidato["version_fuente"] = "statsforecast_rolling_origin_elegible"
                candidato["criterio_elegibilidad"] = (
                    "intermitente"
                    if nombre in {"CrostonClassic", "ADIDA"}
                    else "positivas>=12"
                    if nombre == "AutoETS"
                    else "positivas>=26"
                )
                salidas.append(candidato.drop(columns=["unique_id", "ds", nombre]))
    if not salidas:
        return pd.DataFrame(columns=r09.columns)
    return _calibrar_intervalos(pd.concat(salidas, ignore_index=True))
