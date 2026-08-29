"""Orquestación del modelo fenológico por componentes.

Este módulo contiene la implementación de las operaciones históricas de
predicción, backtest y proyección. La fachada
``analitica.proyeccion.fenologico_v1`` solo conserva la superficie de
compatibilidad y reexporta estas funciones.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import ajuste as _ajuste
from . import evidencia as _evidencia
from . import panel as _panel
from .contratos import ResultadoFenologico
from .especificacion import (
    FEATURES_CLIMA,
    FEATURES_FENOLOGIA,
    FEATURES_FRUTOS,
    FEATURES_OCURRENCIA,
    FEATURES_PESO,
    FEATURES_RIEGO,
    NOMBRE_MODELO,
)
from .incertidumbre import (
    aplicar_escenario_fenologico,
    intervalos_volumen_directo,
    sensibilidades,
)

_normalizar_emisiones = _panel.normalizar_emisiones
_campania_mas_reciente = _panel.campania_mas_reciente
_emisiones_historial = _panel.emisiones_historial
construir_panel_fenologico = _panel.construir_panel_fenologico
auditar_panel_fenologico = _panel.auditar_panel_fenologico
evaluar_evidencia_fold = _evidencia.evaluar_evidencia_fold
_predecir = _ajuste.predecir
_ajustar_regresor = _ajuste.ajustar_regresor
_ajustar_clasificador = _ajuste.ajustar_clasificador


def _predecir_emision(
    panel: pd.DataFrame,
    emision: pd.Timestamp,
    *,
    minimo_entrenamiento: int,
    campania: str | None = None,
    usar_mixedlm: bool = True,
) -> ResultadoFenologico:
    entrenamiento = panel[
        (panel.fecha_emision < emision) & (panel.fecha_objetivo < emision) & panel.real_kg.notna()
    ].copy()
    # El panel contiene snapshots repetidos del mismo lote-semana porque cada emisión
    # histórica vuelve a observar objetivos ya cerrados. Para entrenar una emisión actual
    # se conserva el snapshot más reciente disponible de cada objetivo; así no se cuentan
    # 20 veces los mismos kg y el tiempo de ajuste no crece artificialmente con el número de
    # emisiones archivadas.
    entrenamiento = (
        entrenamiento.sort_values("fecha_emision")
        .drop_duplicates(["campania", "lote_id", "fecha_objetivo"], keep="last")
        .copy()
    )
    prueba = panel[panel.fecha_emision == emision].copy()
    if campania is not None and "campania" in prueba:
        prueba = prueba[prueba.campania.astype(str).eq(str(campania))].copy()
    if len(entrenamiento) < minimo_entrenamiento or prueba.empty:
        return ResultadoFenologico(
            pd.DataFrame(),
            advertencias=[f"{emision:%Y-%m-%d}: historia as-of insuficiente."],
        )
    positivos = entrenamiento.real_kg.gt(0)
    frutos_train = entrenamiento[
        positivos & entrenamiento.frutos_reales_por_planta_catalogo.notna()
    ]
    peso_train = entrenamiento[positivos & entrenamiento.peso_real_g.notna()]

    evidencia = pd.concat(
        [
            evaluar_evidencia_fold(
                entrenamiento,
                objetivo="ocurre_cosecha",
                features=FEATURES_OCURRENCIA,
            ),
            evaluar_evidencia_fold(
                frutos_train,
                objetivo="frutos_reales_por_planta_catalogo",
                features=FEATURES_FRUTOS,
            ),
            evaluar_evidencia_fold(
                peso_train,
                objetivo="peso_real_g",
                features=FEATURES_PESO,
            ),
        ],
        ignore_index=True,
    )

    def admitidas(objetivo: str, defecto: list[str]) -> list[str]:
        seleccion = evidencia[
            (evidencia.objetivo == objetivo) & evidencia.admitida
        ].predictor.tolist()
        # Las cuatro temperaturas base compiten dentro del fold. Conservarlas todas
        # convertiría la autoridad bibliográfica en cuatro columnas colineales.
        candidatas_gdd = [
            feature
            for feature in seleccion
            if feature.startswith(("gdd_0_0_", "gdd_4_4_", "gdd_7_0_", "gdd_8_0_"))
        ]
        elegidas_gdd = []
        for ventana in ("7d", "28d"):
            candidatas = [f for f in candidatas_gdd if f.endswith(ventana)]
            if not candidatas:
                continue
            ranking = evidencia[
                (evidencia.objetivo == objetivo) & evidencia.predictor.isin(candidatas)
            ].copy()
            ranking["orden_q"] = ranking.q_value.fillna(1.0)
            ranking["orden_rho"] = -ranking.estimacion.abs().fillna(0)
            elegidas_gdd.append(
                ranking.sort_values(["orden_q", "orden_rho", "predictor"]).predictor.iloc[0]
            )
        seleccion = [f for f in seleccion if f not in candidatas_gdd or f in elegidas_gdd]
        descartadas = set(candidatas_gdd) - set(elegidas_gdd)
        if descartadas:
            mascara = (evidencia.objetivo == objetivo) & evidencia.predictor.isin(descartadas)
            evidencia.loc[mascara, "admitida"] = False
            evidencia.loc[mascara, "estado"] = "base_termica_no_seleccionada_fold"
        return seleccion or [f for f in defecto if f in entrenamiento]

    try:
        modelo_ocurre = _ajustar_clasificador(
            entrenamiento, admitidas("ocurre_cosecha", FEATURES_OCURRENCIA)
        )
        modelo_frutos = _ajustar_regresor(
            frutos_train,
            "frutos_reales_por_planta_catalogo",
            admitidas("frutos_reales_por_planta_catalogo", FEATURES_FRUTOS),
            usar_mixedlm=usar_mixedlm,
        )
        modelo_peso = _ajustar_regresor(
            peso_train,
            "peso_real_g",
            admitidas("peso_real_g", FEATURES_PESO),
            usar_mixedlm=usar_mixedlm,
        )
        # Ruta directa de volumen: se entrena solo con kg reales anteriores a la
        # emisión. No reemplaza la descomposición; sirve para que la escala semanal no
        # quede gobernada por una probabilidad de ocurrencia extremadamente esparsa.
        modelo_volumen = _ajustar_regresor(
            entrenamiento,
            "real_kg",
            admitidas("real_kg", FEATURES_OCURRENCIA),
            usar_mixedlm=usar_mixedlm,
        )
    except ValueError as exc:
        return ResultadoFenologico(pd.DataFrame(), evidencia, [str(exc)])

    prob = _predecir(modelo_ocurre, prueba, probabilidad=True)
    frutos = _predecir(modelo_frutos, prueba)
    peso_crudo = _predecir(modelo_peso, prueba)
    pesos_observados = pd.to_numeric(peso_train.peso_real_g, errors="coerce")
    pesos_observados = pesos_observados[pesos_observados.gt(0)].dropna()
    # Un peso negativo o cero no es una extrapolación agronómica válida. Puede aparecer
    # cuando MixedLM queda con una parte fija negativa en un corte temprano. Se reemplaza
    # por el percentil inferior observado antes de la emisión; el conteo queda en la
    # metadata para que la calidad no confunda la protección física con señal aprendida.
    limite_peso_inferior = (
        float(max(0.1, pesos_observados.quantile(0.05))) if not pesos_observados.empty else 0.1
    )
    peso_ajustado = peso_crudo < limite_peso_inferior
    peso = np.maximum(peso_crudo, limite_peso_inferior)
    plantas = pd.to_numeric(prueba.plantas, errors="coerce").to_numpy(float)
    kg_condicional = np.maximum(0, plantas * frutos * peso / 1000)
    volumen_directo = _predecir(modelo_volumen, prueba)
    kg_base = np.maximum(0, prob * kg_condicional)
    # El estimador directo fija el nivel. La identidad biológica aporta la forma relativa
    # entre semanas futuras para que la curva no se vuelva plana cuando el modelo de kg
    # encuentra varios lotes con características casi constantes. Se normaliza a la media
    # del horizonte, por lo que no crea volumen adicional.
    if "fecha_objetivo" in prueba and np.nanmean(kg_base) > 1e-9:
        forma = (
            pd.Series(kg_base, index=prueba.index)
            .groupby(pd.to_datetime(prueba.fecha_objetivo).dt.normalize())
            .transform("sum")
        )
        forma = forma / max(float(forma.mean()), 1e-9)
        p50 = np.maximum(0, volumen_directo * forma.to_numpy(float))
    else:
        forma = pd.Series(1.0, index=prueba.index)
        p50 = np.maximum(0, volumen_directo)
    factor_prueba = np.divide(
        p50,
        kg_base,
        out=np.zeros_like(p50, dtype=float),
        where=kg_base > 1e-9,
    )
    q10, q90, n_calibracion = intervalos_volumen_directo(entrenamiento, modelo_volumen)
    if np.isfinite(q10) and np.isfinite(q90):
        p10 = np.minimum(p50, np.maximum(0, p50 + q10))
        p90 = np.maximum(p50, p50 + q90)
    else:
        p10 = np.full(len(prueba), np.nan)
        p90 = np.full(len(prueba), np.nan)

    salida = prueba.copy()
    salida["modelo"] = NOMBRE_MODELO
    salida["version_fuente"] = "rejilla_independiente_asof_direct_volume_v2"
    salida["probabilidad_cosecha"] = prob
    salida["ocurrencia_gate"] = prob >= 0.5
    salida["frutos_por_planta"] = frutos
    salida["peso_baya_g"] = peso
    salida["kg_condicional"] = kg_condicional
    salida["factor_asignacion_cosecha"] = np.asarray(factor_prueba, dtype=float)
    salida["p10_kg"] = p10
    salida["p50_kg"] = p50
    salida["p90_kg"] = p90
    salida["base_plantas"] = "catalogo"
    faltantes = (
        salida[[c for c in (*FEATURES_FENOLOGIA, *FEATURES_CLIMA, *FEATURES_RIEGO) if c in salida]]
        .isna()
        .mean(axis=1)
    )
    salida["confianza"] = np.select(
        [faltantes.le(0.20) & (n_calibracion >= 100), faltantes.le(0.50)],
        ["alta", "media"],
        default="baja",
    )
    sensibilidades_modelo = sensibilidades(
        prueba, modelo_ocurre, modelo_frutos, modelo_peso, prob, frutos, peso
    )
    features_usadas = {
        "ocurrencia": modelo_ocurre.features,
        "frutos": modelo_frutos.features,
        "peso": modelo_peso.features,
    }
    modelos = {
        "ocurrencia": modelo_ocurre.nombre,
        "frutos": modelo_frutos.nombre,
        "peso": modelo_peso.nombre,
        "volumen_directo": modelo_volumen.nombre,
    }
    salida["componentes"] = [
        {
            "modelo": NOMBRE_MODELO,
            "formula": (
                "volumen directo as-of; factor de reconciliación × P(cosecha) × plantas × "
                "frutos/planta × peso / 1000"
            ),
            "modelos_componentes": modelos,
            "features": features_usadas,
            "sensibilidades": sensibilidades_modelo,
            "n_calibracion_intervalo": n_calibracion,
            "metodo_intervalo": "split_conformal_temporal_sobre_residuos_anteriores",
            "calibracion_volumen": {
                "metodo": "modelo_directo_real_kg_entrenado_asof",
                "modelo": modelo_volumen.nombre,
                "n_validacion": int(n_calibracion),
                "factor_es_reconciliacion": True,
                "forma_horizonte": "kg_base_normalizado_por_semana",
            },
            "proteccion_peso": {
                "limite_inferior_g": limite_peso_inferior,
                "filas_ajustadas": int(peso_ajustado.sum()),
                "metodo": "percentil_05_peso_observado_anterior_a_emision",
            },
            "calendario_fuente": "rejilla_lotes_independiente_de_R09",
            "etiqueta_causal": False,
        }
        for sensibilidad in sensibilidades_modelo
    ]
    salida["modo_proyeccion"] = "fenologico_independiente_asof"
    salida["corte_asof"] = emision
    salida["calendario_fuente"] = "rejilla_lotes_independiente_de_R09"
    evidencia["fecha_emision"] = emision
    evidencia["modelo_componente"] = evidencia.objetivo.map(
        {
            "ocurre_cosecha": modelo_ocurre.nombre,
            "frutos_reales_por_planta_catalogo": modelo_frutos.nombre,
            "peso_real_g": modelo_peso.nombre,
        }
    )
    return ResultadoFenologico(salida, evidencia)


def backtest_fenologico_v1(
    datos,
    emisiones: pd.DataFrame,
    *,
    horizonte_semanas: int = 10,
    minimo_entrenamiento: int = 300,
    max_cortes: int = 8,
    usar_mixedlm: bool = False,
) -> ResultadoFenologico:
    """Replay rolling-origin del modelo nuevo, en cortes comunes pero sin features de R09."""

    emisiones_n = _normalizar_emisiones(emisiones, _campania_mas_reciente(datos))
    fecha_corte = pd.to_datetime(emisiones_n.fecha_emision).max()
    campania_objetivo = _campania_mas_reciente(datos)
    emisiones_panel = _emisiones_historial(
        datos,
        emisiones_n,
        campania_objetivo=campania_objetivo,
        fecha_corte=fecha_corte,
    )
    panel = construir_panel_fenologico(datos, emisiones_panel, horizonte_semanas=horizonte_semanas)
    auditoria = auditar_panel_fenologico(
        panel,
        n_emisiones=len(emisiones_panel),
        n_lotes=panel.lote_id.nunique(),
        horizonte_semanas=horizonte_semanas,
        filas_esperadas=(
            panel[["campania", "fecha_emision", "lote_id"]].drop_duplicates().shape[0]
            * horizonte_semanas
        ),
    )
    evaluaciones = emisiones_n.sort_values(["fecha_emision", "campania"])

    # Un corte de backtest solo es evaluable si al menos uno de sus objetivos ya fue
    # observado. El panel marca ``real_kg`` únicamente hasta la última semana real
    # disponible; escoger simplemente las últimas emisiones R09 puede seleccionar S34/S35
    # cuando todavía no existe cosecha para la primera semana proyectada. En ese caso el
    # modelo sí entrena y emite filas, pero el replay queda sin métrica y la interfaz puede
    # confundirlo con un resultado de precisión.
    objetivos_resueltos = panel.loc[
        panel.real_kg.notna(), ["campania", "fecha_emision"]
    ].drop_duplicates()
    evaluaciones_evaluables = evaluaciones.merge(
        objetivos_resueltos.assign(_objetivo_resuelto=True),
        on=["campania", "fecha_emision"],
        how="inner",
        validate="1:1",
    )
    descartadas = len(evaluaciones) - len(evaluaciones_evaluables)
    advertencias = []
    if descartadas:
        advertencias.append(
            f"Se descartaron {descartadas} emisiones sin objetivos reales cerrados; "
            "no se usan para medir precisión."
        )
    if max_cortes and len(evaluaciones_evaluables) > max_cortes:
        evaluar = evaluaciones_evaluables.iloc[-max_cortes:]
    else:
        evaluar = evaluaciones_evaluables
    predicciones = []
    evidencias = []
    for fila in evaluar.itertuples(index=False):
        resultado = _predecir_emision(
            panel,
            pd.Timestamp(fila.fecha_emision),
            minimo_entrenamiento=minimo_entrenamiento,
            campania=str(fila.campania),
            usar_mixedlm=usar_mixedlm,
        )
        if not resultado.predicciones.empty:
            predicciones.append(resultado.predicciones)
        if not resultado.evidencia_features.empty:
            evidencias.append(resultado.evidencia_features)
        advertencias.extend(resultado.advertencias)
    return ResultadoFenologico(
        pd.concat(predicciones, ignore_index=True, sort=False) if predicciones else pd.DataFrame(),
        pd.concat(evidencias, ignore_index=True, sort=False) if evidencias else pd.DataFrame(),
        advertencias,
        auditoria,
    )


def proyectar_fenologico_v1(
    datos,
    *,
    fecha_emision: object | None = None,
    horizonte_semanas: int = 10,
    minimo_entrenamiento: int = 300,
    usar_mixedlm: bool = True,
) -> ResultadoFenologico:
    """Proyección vigente; genera historia semanal interna sin tomar el calendario R09."""

    corte = pd.Timestamp(fecha_emision or pd.Timestamp.today()).normalize()
    campania = _campania_mas_reciente(datos)
    fechas = pd.date_range(corte - pd.Timedelta(weeks=60), corte, freq="W-MON")
    if corte not in fechas:
        fechas = fechas.append(pd.DatetimeIndex([corte])).sort_values()
    emisiones_actuales = pd.DataFrame({"campania": campania, "fecha_emision": fechas})
    emisiones = _emisiones_historial(
        datos,
        emisiones_actuales,
        campania_objetivo=campania,
        fecha_corte=corte,
    )
    clave_actual = (campania, corte)
    emisiones_hist = emisiones[
        ~(
            emisiones.campania.astype(str).eq(str(clave_actual[0]))
            & pd.to_datetime(emisiones.fecha_emision).eq(clave_actual[1])
        )
    ].copy()
    panel_partes = []
    if not emisiones_hist.empty:
        # Para el entrenamiento basta el objetivo de la semana siguiente. Los objetivos
        # posteriores ya aparecen como observaciones en otra emisión histórica y volver a
        # generarlos por cada horizonte solo infla el panel sin añadir información.
        panel_partes.append(construir_panel_fenologico(datos, emisiones_hist, horizonte_semanas=1))
    panel_partes.append(
        construir_panel_fenologico(
            datos,
            pd.DataFrame({"campania": [campania], "fecha_emision": [corte]}),
            horizonte_semanas=horizonte_semanas,
        )
    )
    filas_esperadas = sum(len(parte) for parte in panel_partes)
    panel = pd.concat(panel_partes, ignore_index=True, sort=False)
    resultado = _predecir_emision(
        panel,
        corte,
        minimo_entrenamiento=minimo_entrenamiento,
        campania=campania,
        usar_mixedlm=usar_mixedlm,
    )
    resultado.auditoria = auditar_panel_fenologico(
        panel,
        n_emisiones=len(emisiones),
        n_lotes=panel.lote_id.nunique(),
        horizonte_semanas=horizonte_semanas,
        filas_esperadas=filas_esperadas,
    )
    return resultado


__all__ = [
    "aplicar_escenario_fenologico",
    "backtest_fenologico_v1",
    "proyectar_fenologico_v1",
]
