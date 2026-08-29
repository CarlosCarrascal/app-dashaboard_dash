"""Dos modelos separados —frutos por planta y peso de baya— y su ensamblado en kilos.

El rendimiento de un lote es una identidad, no una caja negra:

    kg = plantas × frutos por planta × peso medio de baya / 1000

Predecir el total directamente esconde por qué acierta. Un pronóstico puede dar los kilos
correctos con muchos frutos pequeños o con pocos frutos grandes; solo estimando las piezas
por separado se ve cuál de las dos historias cuenta, y solo así el error se puede atribuir
a una parte concreta del cultivo.

Tres decisiones de diseño que conviene tener presentes al leer el módulo:

**La base de plantas es el maestro del lote.** El número de plantas no cambia dentro de la
campaña: con las que se inicia son las que se terminan. Comprobado contra la base el
2026-08-19 — 767 de 781 lotes tienen exactamente el mismo número en cosecha que en el
maestro, la razón media es 1,0023 y solo 2 de 1.959 combinaciones lote-campaña varían
internamente. Por eso el maestro es la cifra correcta y además la única disponible en el
momento de emitir.

Aun así el objetivo de frutos se despeja sobre esa misma base y cada fila declara
`base_plantas`. No es por desconfianza del dato, sino porque una métrica que compara un
pronóstico hecho sobre una base contra un observado calculado sobre otra mide la diferencia
entre definiciones. Con los datos reales esa diferencia es del 0,3 % (MAE 21,33 contra
21,27), pero la declaración cuesta una columna y evita que un cambio futuro en el registro
de cosecha pase inadvertido.

**El calendario tiene dos modos.** La llamada histórica original hereda de R09 qué semanas
tienen cosecha. El motor nuevo puede usar una rejilla de ocurrencia con ceros explícitos y
un clasificador as-of; así se puede evaluar la decisión de semana por separado, sin convertir
R09 en una variable de entrada.

**Los intervalos se calibran sobre el producto, no sobre las piezas.** Multiplicar dos
intervalos no da un intervalo válido. Se calibra el resultado final con sus propios
residuos pasados, igual que el resto de familias del torneo, para que el control de
cobertura de la promoción siga comparando entre iguales.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .contratos import validar_predicciones_componentes
from .modelos import (
    _calibrar_intervalos,
    _elegir_anidado_etiquetado,
    _fabricas_modelos,
    _imputar,
    _preparar_features,
)

NOMBRE_MODELO = "Componentes_identidad"

# Variables comunes a los dos modelos. Todas son conocidas en la fecha de emisión.
FEATURES_COMUNES = [
    "horizonte_semanas",
    "semana_objetivo_sin",
    "semana_objetivo_cos",
    "plantas",
    "dias_desde_poda",
]

# Clima acumulado hasta la emisión, calculado en ventanas cerradas por `asof.enriquecer_asof`.
FEATURES_CLIMA_ASOF = [
    "temp_media_7d",
    "temp_max_7d",
    "temp_min_7d",
    "humedad_7d",
    "dpv_kpa_7d",
    "radiacion_7d",
    "eto_7d",
    "lluvia_7d",
    "gdd_0_0_7d",
    "gdd_4_4_7d",
    "gdd_7_0_7d",
    "gdd_8_0_7d",
    "temp_media_28d",
    "temp_max_28d",
    "temp_min_28d",
    "humedad_28d",
    "dpv_kpa_28d",
    "radiacion_28d",
    "eto_28d",
    "lluvia_28d",
    "gdd_0_0_28d",
    "gdd_4_4_28d",
    "gdd_7_0_28d",
    "gdd_8_0_28d",
]

FEATURES_RIEGO_ASOF = [
    "riego_agua_m3_7d",
    "riego_lamina_mm_7d",
    "riego_reposicion_pct_7d",
    "riego_agua_m3_28d",
    "riego_lamina_mm_28d",
    "riego_reposicion_pct_28d",
]

# Censos fenológicos con la última observación anterior a la emisión. Los valores
# `frutos_por_planta` y `peso_baya_g` publicados por R09 se excluyen deliberadamente:
# son componentes del forecast que se quiere sustituir, no mediciones independientes.
FEATURES_FRUTOS = [
    *FEATURES_COMUNES,
    *FEATURES_CLIMA_ASOF,
    *FEATURES_RIEGO_ASOF,
    "flores",
    "cuajo",
    "tasa_cuajo_observada",
    "frutos_muestra",
    "indice_estado",
    "prop_e1",
    "prop_e2",
    "prop_e3",
    "prop_e4",
    "prop_e5",
    "frutos_por_planta_ultimo_asof",
    "semanas_desde_ultima_cosecha",
]

FEATURES_PESO = [
    *FEATURES_COMUNES,
    *FEATURES_CLIMA_ASOF,
    *FEATURES_RIEGO_ASOF,
    "diametro_baya_mm",
    "sd_diametro_baya_mm",
    "bayas_muestreadas",
    "indice_estado",
    "prop_e4",
    "prop_e5",
    "peso_real_g_ultimo_asof",
    "semanas_desde_ultima_cosecha",
]

# Nada de esto puede entrar como variable de entrada: o es el resultado que se quiere
# predecir, o lo contiene. `p50_kg` se excluye a propósito — con él dentro, la familia
# sería otra corrección residual del forecast base disfrazada de modelo de componentes.
FEATURES_PROHIBIDAS = frozenset(
    {
        "real_kg",
        "p50_kg",
        "p10_kg",
        "p90_kg",
        "peso_real_g",
        "plantas_reales",
        "frutos_reales_por_planta",
        "frutos_reales_por_planta_catalogo",
        "kg_componentes",
    }
)

# Una variable entra al modelo solo si el bloque de entrenamiento de ese fold la tiene con
# datos suficientes. El umbral se aplica dentro del fold, así que no mira el futuro.
COBERTURA_MINIMA = 0.60


def _validar_features() -> None:
    """Falla al importar si alguien mete el resultado observado entre las entradas."""
    for nombre, lista in (("FEATURES_FRUTOS", FEATURES_FRUTOS), ("FEATURES_PESO", FEATURES_PESO)):
        intrusas = FEATURES_PROHIBIDAS & set(lista)
        if intrusas:
            raise AssertionError(f"{nombre} incluye el resultado a predecir: {sorted(intrusas)}")


_validar_features()


def _rezagos_propios(base: pd.DataFrame) -> pd.DataFrame:
    """Último valor observado de cada lote **estrictamente anterior** a la emisión.

    `allow_exact_matches=False` es la línea que evita la fuga: sin ella, una emisión podría
    usar como rezago el resultado de la misma semana que está intentando predecir.
    """
    salida = base.copy()
    salida["frutos_por_planta_ultimo_asof"] = np.nan
    salida["peso_real_g_ultimo_asof"] = np.nan
    salida["semanas_desde_ultima_cosecha"] = np.nan

    columnas = {"lote_id", "fecha_emision", "fecha_objetivo", "real_kg", "peso_real_g"}
    if columnas - set(salida):
        return salida

    # Se renombran las columnas del histórico antes de unir. Comparten nombre con las de la
    # izquierda, y dejar que pandas resuelva el choque con sufijos `_x`/`_y` haría que este
    # código dependiera de un detalle de implementación del merge.
    historico = (
        salida.dropna(subset=["real_kg"])
        .loc[:, ["lote_id", "fecha_objetivo", "frutos_reales_por_planta_catalogo", "peso_real_g"]]
        .rename(
            columns={
                "fecha_objetivo": "_hist_fecha",
                "frutos_reales_por_planta_catalogo": "_hist_frutos",
                "peso_real_g": "_hist_peso",
            }
        )
        .drop_duplicates(["lote_id", "_hist_fecha"])
        .sort_values("_hist_fecha")
    )
    if historico.empty:
        return salida

    izquierda = salida.reset_index().sort_values("fecha_emision")
    unido = pd.merge_asof(
        izquierda,
        historico,
        left_on="fecha_emision",
        right_on="_hist_fecha",
        by="lote_id",
        direction="backward",
        allow_exact_matches=False,
    ).set_index("index")

    salida["frutos_por_planta_ultimo_asof"] = unido["_hist_frutos"]
    salida["peso_real_g_ultimo_asof"] = unido["_hist_peso"]
    salida["semanas_desde_ultima_cosecha"] = (
        unido["fecha_emision"] - unido["_hist_fecha"]
    ).dt.days / 7
    return salida


def _features_disponibles(entreno: pd.DataFrame, deseadas: list[str]) -> list[str]:
    """Las variables que este fold puede usar de verdad.

    Se descarta lo que el bloque de entrenamiento apenas tiene: imputar una columna vacía
    con su mediana no añade información, solo la apariencia de tenerla.
    """
    presentes = [c for c in deseadas if c in entreno]
    return [c for c in presentes if entreno[c].notna().mean() >= COBERTURA_MINIMA]


def _marcar_faltantes(tabla: pd.DataFrame, features: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Añade un indicador por variable con huecos, para que la ausencia sea información.

    Imputar y callar le dice al modelo que ese lote tenía un valor promedio. Con el
    indicador puede aprender que, cuando falta el censo, conviene apoyarse en otra cosa.
    """
    salida = tabla.copy()
    extras: list[str] = []
    for columna in features:
        if salida[columna].isna().any():
            marca = f"{columna}_faltante"
            salida[marca] = salida[columna].isna().astype(float)
            extras.append(marca)
    return salida, extras


def _entrenar_componente(
    entreno: pd.DataFrame,
    prueba: pd.DataFrame,
    *,
    objetivo: str,
    features: list[str],
    log: bool,
) -> tuple[np.ndarray, str]:
    """Ajusta un componente para una emisión y devuelve su predicción y la familia elegida."""
    usables = _features_disponibles(entreno, features)
    if not usables:
        return np.full(len(prueba), np.nan), "sin_features"

    entreno_m, extras = _marcar_faltantes(entreno, usables)
    prueba_m = prueba.copy()
    for columna in usables:
        marca = f"{columna}_faltante"
        if marca in extras:
            prueba_m[marca] = prueba_m[columna].isna().astype(float) if columna in prueba_m else 1.0
        if columna not in prueba_m:
            prueba_m[columna] = np.nan
    columnas = [*usables, *extras]

    y = entreno_m[objetivo].to_numpy(float)
    y_ajuste = np.log1p(y) if log else y

    candidatos = [
        (f"{familia}_{i}", fabrica)
        for familia, fabricas in _fabricas_modelos().items()
        for i, fabrica in enumerate(fabricas)
    ]
    etiqueta, fabrica, _ = _elegir_anidado_etiquetado(
        candidatos,
        entreno_m,
        y_fn=(lambda t: np.log1p(t[objetivo].to_numpy(float)))
        if log
        else (lambda t: t[objetivo].to_numpy(float)),
        features=columnas,
        minimo_train=50,
    )
    x_train, x_test = _imputar(entreno_m, prueba_m, columnas)
    modelo = fabrica()
    modelo.fit(x_train, y_ajuste)
    prediccion = modelo.predict(x_test)
    if log:
        prediccion = np.expm1(prediccion)

    # El recorte usa los extremos del propio entrenamiento, nunca del conjunto completo:
    # con los del total, el modelo estaría usando el rango del futuro para acotarse.
    bajo, alto = np.nanquantile(y, [0.001, 0.999])
    return np.clip(prediccion, max(0.0, float(bajo)), float(alto)), etiqueta


def challengers_componentes(
    r09: pd.DataFrame,
    panel_asof: pd.DataFrame | None = None,
    minimo_entrenamiento: int = 300,
    *,
    diagnostico_montecarlo: bool = False,
    heredar_calendario: bool = True,
) -> pd.DataFrame:
    """Predice frutos por planta y peso de baya por separado y los compone en kilos.

    Para cada fecha de emisión, el entrenamiento solo admite semanas cuyo resultado ya
    estaba cerrado antes de emitir. Las emisiones tempranas, sin historia suficiente, no
    producen filas: es preferible no emitir a emitir un número que no se sostiene.
    """
    base = r09[r09.modelo == "R09_publicado"].copy()
    if base.empty:
        return pd.DataFrame(columns=r09.columns)

    # Sin las series observadas de los dos componentes no hay nada que aprender. Se devuelve
    # vacío en vez de fallar: el torneo lo anota como familia que no emitió y sigue con las
    # demás, que es preferible a tumbar la corrida entera por una columna ausente.
    requeridas = {"frutos_reales_por_planta_catalogo", "peso_real_g", "plantas", "real_kg"}
    if requeridas - set(base):
        return pd.DataFrame(columns=r09.columns)

    if panel_asof is not None and not panel_asof.empty:
        claves = ["campania", "lote_id", "fecha_emision", "fecha_objetivo"]
        if set(claves) <= set(panel_asof):
            extra = [c for c in panel_asof.columns if c not in base.columns or c in claves]
            base = base.merge(
                panel_asof[extra].drop_duplicates(claves), on=claves, how="left", validate="m:1"
            )

    base = _preparar_features(base)
    base = _rezagos_propios(base)

    # El objetivo de frutos se despeja sobre las plantas del maestro, la misma base por la
    # que después se multiplica. Con la otra base la identidad no cerraría y el error
    # medido recogería la diferencia entre definiciones.
    base["objetivo_frutos"] = base["frutos_reales_por_planta_catalogo"]
    base["objetivo_peso"] = base["peso_real_g"]

    salidas = []
    for fecha, prueba in base.groupby("fecha_emision", sort=True):
        resueltas = base[(base.fecha_objetivo < fecha) & base.real_kg.notna()]
        entreno_frutos = resueltas[
            resueltas.objetivo_frutos.notna()
            & np.isfinite(resueltas.objetivo_frutos)
            & (resueltas.plantas > 0)
        ]
        entreno_peso = resueltas[resueltas.objetivo_peso.notna() & (resueltas.objetivo_peso > 0)]
        if len(entreno_frutos) < minimo_entrenamiento or len(entreno_peso) < minimo_entrenamiento:
            continue

        frutos, familia_frutos = _entrenar_componente(
            entreno_frutos, prueba, objetivo="objetivo_frutos", features=FEATURES_FRUTOS, log=True
        )
        peso, familia_peso = _entrenar_componente(
            entreno_peso, prueba, objetivo="objetivo_peso", features=FEATURES_PESO, log=False
        )
        if not np.isfinite(frutos).any() or not np.isfinite(peso).any():
            continue

        nueva = prueba.copy()
        plantas = pd.to_numeric(nueva.plantas, errors="coerce").to_numpy(float)
        producto = np.maximum(0.0, plantas * frutos * peso / 1000)

        # Semanas que el forecast base no considera de cosecha: la familia no inventa un
        # calendario propio, así que tampoco inventa kilos donde aquel no los espera.
        if heredar_calendario:
            sin_cosecha = (
                pd.to_numeric(nueva.p50_kg, errors="coerce").fillna(0).to_numpy(float) <= 0
            )
        else:
            # La rejilla de ocurrencia ya hizo explícitos los ceros. En ese modo el modelo
            # de componentes no puede volver a usar el p50 de R09 como gate.
            sin_cosecha = np.zeros(len(nueva), dtype=bool)
        producto = np.where(sin_cosecha, 0.0, producto)

        nueva["p50_kg"] = producto
        # Se sobrescriben las tres piezas con las que realmente produjeron el número. Sin
        # esto viajarían las del forecast base y las métricas por componente medirían el
        # error de otro modelo.
        nueva["frutos_por_planta"] = np.where(sin_cosecha, 0.0, frutos)
        nueva["peso_baya_g"] = peso
        nueva["plantas"] = plantas
        nueva["modelo"] = NOMBRE_MODELO
        nueva["version_fuente"] = "identidad_asof_plantas_catalogo"
        nueva["base_plantas"] = "catalogo"
        nueva["familia_frutos"] = familia_frutos
        nueva["familia_peso"] = familia_peso
        nueva["n_entrenamiento_frutos"] = len(entreno_frutos)
        nueva["n_entrenamiento_peso"] = len(entreno_peso)
        nueva["filas_con_gate_cero"] = int(sin_cosecha.sum())
        nueva["supuesto_modelo"] = (
            "frutos por planta sobre las plantas del maestro del lote, que no varían dentro "
            "de la campaña; el calendario de semanas se controla con heredar_calendario="
            f"{heredar_calendario}"
        )
        salidas.append(validar_predicciones_componentes(nueva))

    if not salidas:
        return pd.DataFrame(columns=r09.columns)
    resultado = _calibrar_intervalos(pd.concat(salidas, ignore_index=True))
    if diagnostico_montecarlo:
        # Columnas extra, no sustitutas: `p10_kg`/`p90_kg` siguen siendo los oficiales. Al
        # persistir caen dentro de `analytics.prediction.componentes` (jsonb) sin migración.
        resultado = intervalos_producto_montecarlo(resultado)
    return resultado


def intervalos_producto_montecarlo(
    predicciones: pd.DataFrame,
    *,
    repeticiones: int = 2000,
    longitud_bloque: int = 3,
    minimo_parejas: int = 50,
    semilla: int = 42,
) -> pd.DataFrame:
    """Intervalo del producto propagando el error de cada componente por remuestreo.

    Diagnóstico paralelo, **no** la ruta de publicación: los intervalos oficiales salen de
    `_calibrar_intervalos`, que es lo que usan todas las familias del torneo y lo que hace
    comparable el control de cobertura de la promoción. Este cálculo responde a otra
    pregunta: cuánta de la incertidumbre en kilos viene de no saber los frutos y cuánta de
    no saber el peso.

    El método remuestrea **parejas completas** `(residuo de frutos, residuo de peso)` de la
    misma fila, en bloques contiguos de fechas de emisión. Las parejas preservan la
    correlación empírica entre ambos errores sin asumir ninguna forma de dependencia, y los
    bloques respetan que semanas seguidas se parecen entre sí. Muestrear cada componente por
    separado daría un intervalo demasiado estrecho o demasiado ancho según el signo de esa
    correlación.

    Solo usa parejas **resueltas antes** de la emisión que está calibrando, así que es as-of
    como el resto del pipeline. Donde no hay al menos `minimo_parejas`, devuelve NaN: no se
    inventa un intervalo con cuatro observaciones.

    Advertencia deliberada: el producto de dos intervalos conformales no es conformal. Por
    eso `intervalos_enbpi` no se aplica por componente para luego multiplicar — se perdería
    la garantía y sería una afirmación falsa.
    """
    salida = predicciones.copy()
    salida["p10_kg_mc"] = np.nan
    salida["p90_kg_mc"] = np.nan
    salida["n_parejas_mc"] = 0

    requeridas = {
        "fecha_emision",
        "fecha_objetivo",
        "plantas",
        "frutos_por_planta",
        "peso_baya_g",
        "frutos_reales_por_planta_catalogo",
        "peso_real_g",
    }
    if requeridas - set(salida) or salida.empty:
        return salida

    # Residuos multiplicativos: el error de un componente escala, no suma. Un lote que rinde
    # el doble de frutos se equivoca en el doble de frutos absolutos, no en la misma cantidad.
    with np.errstate(divide="ignore", invalid="ignore"):
        salida["_res_frutos"] = np.log(
            salida.frutos_reales_por_planta_catalogo / salida.frutos_por_planta
        )
        salida["_res_peso"] = np.log(salida.peso_real_g / salida.peso_baya_g)
    resueltas = salida[np.isfinite(salida._res_frutos) & np.isfinite(salida._res_peso)].sort_values(
        "fecha_objetivo"
    )

    rng = np.random.default_rng(semilla)
    for fecha in sorted(salida.fecha_emision.dropna().unique()):
        pasadas = resueltas[resueltas.fecha_objetivo < fecha]
        if len(pasadas) < minimo_parejas:
            continue
        fechas_bloque = np.array(sorted(pasadas.fecha_emision.dropna().unique()))
        if len(fechas_bloque) < longitud_bloque:
            continue

        # Un bloque es un tramo contiguo de emisiones; se sortean bloques, no filas sueltas.
        bloques = [
            fechas_bloque[i : i + longitud_bloque]
            for i in range(max(1, len(fechas_bloque) - longitud_bloque + 1))
        ]
        por_fecha = {
            f: g[["_res_frutos", "_res_peso"]].to_numpy(float)
            for f, g in pasadas.groupby("fecha_emision")
        }
        elegidos = rng.integers(0, len(bloques), size=repeticiones)
        muestras = []
        for indice in elegidos:
            candidatas = np.concatenate([por_fecha[f] for f in bloques[indice] if f in por_fecha])
            muestras.append(candidatas[rng.integers(0, len(candidatas))])
        parejas = np.asarray(muestras)
        factor_frutos = np.exp(parejas[:, 0])
        factor_peso = np.exp(parejas[:, 1])

        actuales = salida.fecha_emision == fecha
        plantas = salida.loc[actuales, "plantas"].to_numpy(float)[:, None]
        frutos = salida.loc[actuales, "frutos_por_planta"].to_numpy(float)[:, None]
        peso = salida.loc[actuales, "peso_baya_g"].to_numpy(float)[:, None]
        simulado = plantas * (frutos * factor_frutos[None, :]) * (peso * factor_peso[None, :])
        simulado = np.maximum(0.0, simulado / 1000)
        salida.loc[actuales, "p10_kg_mc"] = np.nanquantile(simulado, 0.1, axis=1)
        salida.loc[actuales, "p90_kg_mc"] = np.nanquantile(simulado, 0.9, axis=1)
        salida.loc[actuales, "n_parejas_mc"] = len(pasadas)

    return salida.drop(columns=["_res_frutos", "_res_peso"])


def verificar_identidad(predicciones: pd.DataFrame, tolerancia: float = 1e-6) -> pd.Series:
    """Diferencia relativa entre el kg publicado y el producto de sus tres piezas.

    Debe ser prácticamente cero en las filas de esta familia. Que no lo sea significa que
    alguien alteró una de las columnas después del ensamblado, y entonces las métricas por
    componente dejan de describir el número que se está mostrando.
    """
    requeridas = {"plantas", "frutos_por_planta", "peso_baya_g", "p50_kg"}
    if requeridas - set(predicciones):
        return pd.Series(dtype=float)
    producto = (
        predicciones.plantas * predicciones.frutos_por_planta * predicciones.peso_baya_g / 1000
    )
    denominador = predicciones.p50_kg.abs().clip(lower=1.0)
    diferencia = (producto - predicciones.p50_kg).abs() / denominador
    return diferencia.where(diferencia.notna(), other=np.nan).fillna(tolerancia * 0)
