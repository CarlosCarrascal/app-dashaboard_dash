"""Constantes del tablero: qué variables entran, cómo se llaman y dónde está el Excel."""

from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple

# Variables predictoras.
#
# Las columnas `*_lag` son promedios móviles con ventana configurable calculados en
# `nucleo/datos.py`. Las columnas originales (DPV, Rad, ETo, riego_lt_planta) se
# conservan en el panel para el estudio climático y la auditoría.
#
# `riego_lt_planta` es la única variable que varía entre módulos dentro de una misma
# semana; las climáticas son un dato del fundo, común a todos los módulos.
#
# Se usa `Lt/planta` y no `m3/ha` a propósito: en el archivo vigente esa segunda columna
# viene sumada sobre los turnos de riego y no está al grano del módulo. `nucleo/datos.py`
# lo detecta y lo explica en «Datos y calidad».
FEATURES: tuple[str, ...] = (
    "DPV_lag", "riego_lag", "Rad_lag", "ETo_lag", "gdd_lag", "TempMax", "TempMin",
)

# Las mismas variables SIN desfase — lo que hay antes de suponer ninguna regla temporal.
# «Impacto agronómico» y el resto del análisis descriptivo muestran ESTAS, no las de arriba:
# mostrar un promedio móvil bajo el título «la asociación cruda, antes de cualquier
# modelo» sería contradecir el propio texto de esa sección.
VARIABLES_DESCRIPTIVAS: tuple[str, ...] = (
    "DPV", "riego_lt_planta", "Rad", "ETo", "TempMax", "TempMin",
)

OBJETIVO = "KgHa"

# Subconjunto climático: lo que se mide una vez por semana para todo el fundo.
CLIMA: tuple[str, ...] = ("TempMax", "TempMin", "VarDia", "gdd_semana", "gdd_acum",
                          "Rad", "ETo", "DPV")

# Frutos (conteo) y Peso (peso medio del fruto): los dos componentes biológicos de los
# que sale el kg/ha, incorporados desde la hoja «Kg Reales». No entran a FEATURES —
# kg/ha ≈ Frutos × Peso × densidad de plantas, así que usarlas para predecir kg/ha sería
# casi tautológico. Sirven para ver si el clima/riego pesa distinto sobre el número de
# frutos que sobre su tamaño (ver «Frutos y peso» en Impacto agronómico).
FRUTOS_PESO: tuple[str, ...] = ("Frutos", "Peso")

# Temperatura base para los grados-día de crecimiento. Por debajo de este umbral la
# planta no acumula desarrollo. 4,4 °C (40 °F) es el valor de referencia para arándano
# en la literatura; se deja como constante y no como parámetro del usuario porque cambiar
# el umbral cambia todas las cifras del tablero y eso debe ser una decisión versionada.
TBASE_GDD = 4.4

ETIQUETAS: dict[str, str] = {
    # Variables originales (panel, estudio climático, auditoría)
    "DPV": "DPV (kPa)",
    "riego_lt_planta": "Riego (L/planta·sem)",
    "riego_m3_ha": "Riego (m³/ha, sin corregir)",
    "Rad": "Radiación solar",
    "ETo": "ETo (mm/sem)",
    "TempMax": "Temp. máxima (°C)",
    "TempMin": "Temp. mínima (°C)",
    "VarDia": "Amplitud térmica (°C)",
    "gdd_semana": "GDD de la semana (°C·día)",
    "gdd_acum": "GDD acumulados (°C·día)",
    "poda_fecha": "Fecha de poda (promedio por área)",
    "poda_fecha_min": "Primera fecha de poda del módulo",
    "poda_fecha_max": "Última fecha de poda del módulo",
    "poda_dispersion_dias": "Dispersión de poda (días)",
    "poda_n_lotes": "Lotes que aportan la poda",
    "poda_area_ha": "Área de poda (ha)",
    "Variedad": "Variedad dominante por área",
    "FSiembra": "Fecha de siembra (promedio por área)",
    "fecha_semana_aprox": "Fecha aproximada de la semana",
    "dias_desde_poda": "Días desde poda (proxy)",
    "edad_planta_anos": "Edad de planta (años, proxy)",
    "gdd_acum_poda_obs": "GDD observado desde poda",
    "gdd_semanas_poda_obs": "Semanas de GDD observadas desde poda",
    "flores_promedio": "Flores (promedio por turno)",
    "flores_desvio": "Flores, desvío entre turnos",
    "flores_n_turnos": "Turnos evaluados (floración)",
    "flores_dispersion_relativa": "Dispersión de floración entre turnos",
    "fecha_evaluacion": "Fecha de evaluación de floración",
    "nsem": "Número de semana",
    "KgHa": "Rendimiento (kg/ha)",
    "Frutos": "Frutos (por planta)",
    "Peso": "Peso del fruto (g)",
    # Features lagged (modelo XGBoost): promedio móvil dependiente del parámetro de ventana
    "DPV_lag": "DPV (prom. móvil) (kPa)",
    "riego_lag": "Riego (prom. móvil) (L/planta)",
    "Rad_lag": "Radiación (prom. móvil)",
    "ETo_lag": "ETo (prom. móvil) (mm)",
    "gdd_lag": "GDD (prom. móvil) (°C·día)",
}

# Qué mide cada variable y cómo leerla. Alimenta los tooltips y el glosario: la interfaz
# no debe pedirle al usuario que sepa de antemano qué es el DPV.
GLOSARIO: dict[str, str] = {
    # Variables originales
    "DPV": "Déficit de presión de vapor: cuánta sed le impone el aire a la planta. "
           "Alto = aire seco y caliente, la planta transpira más y puede cerrar estomas.",
    "riego_lt_planta": "Litros de agua aplicados por planta durante la semana, promediados "
                       "entre los turnos de riego del módulo.",
    "riego_m3_ha": "Metros cúbicos por hectárea tal como vienen en el archivo. En la "
                   "versión vigente esta columna está sumada sobre los turnos, así que su "
                   "magnitud no es una lámina de riego real.",
    "Rad": "Radiación solar incidente: la energía disponible para la fotosíntesis.",
    "ETo": "Evapotranspiración de referencia: cuánta agua evaporaría un cultivo patrón "
           "esa semana. Es la vara con la que se mide si el riego alcanza.",
    "TempMax": "Promedio semanal de la temperatura máxima diaria.",
    "TempMin": "Promedio semanal de la temperatura mínima diaria. Es la que más "
               "correlaciona con el rendimiento, por razones que el estudio examina.",
    "VarDia": "Diferencia entre la máxima y la mínima del día, promediada en la semana.",
    "gdd_semana": "Grados-día de crecimiento acumulados en la semana: mide el desarrollo "
                  "que permite la temperatura, no la temperatura en sí. Se calcula como "
                  "7 x (temperatura media - 4,4 °C), y no baja de cero.",
    "gdd_acum": "Suma de los grados-día desde la primera semana del año. Es el reloj "
                "fisiológico del cultivo: dos semanas con la misma temperatura pesan "
                "distinto según cuánto desarrollo se acumuló antes.",
    "KgHa": "Kilos cosechados por hectárea en la semana. Es lo que se quiere explicar.",
    "Frutos": "Número medio de frutos por planta esa semana, según la hoja «Kg Reales». "
              "kg/ha ≈ Frutos × Peso × densidad de plantas: junto con «Peso» es la "
              "descomposición biológica del rendimiento, no una variable independiente.",
    "Peso": "Peso medio de un fruto individual esa semana, en gramos. La otra mitad de "
            "la descomposición de kg/ha junto con «Frutos».",
    # Features lagged (modelo XGBoost)
    "DPV_lag": "Promedio móvil del DPV según las semanas seleccionadas en la barra lateral. "
               "Captura el estrés hídrico atmosférico sostenido.",
    "riego_lag": "Promedio móvil del riego (L/planta) según las semanas seleccionadas. "
                 "Evalúa el volumen de agua recibido durante el desarrollo o turgencia "
                 "del fruto.",
    "Rad_lag": "Promedio móvil de la radiación solar según la ventana elegida. "
               "La fotosíntesis acumulada en el período previo determina la materia "
               "seca y el peso.",
    "ETo_lag": "Promedio móvil de la ETo. Representa la demanda hídrica ambiental acumulada.",
    "gdd_lag": "Promedio móvil del GDD semanal. En esta campaña es casi una transformación "
                "de la temperatura media; no debe leerse como una señal independiente sin "
                "un origen agronómico desde poda.",
    "dias_desde_poda": "Diferencia aproximada entre el punto medio de la semana y la fecha "
                       "de poda ponderada por área. Es un reloj biológico proxy, no una fase "
                       "fenológica observada.",
    "poda_dispersion_dias": "Días entre la primera y la última poda de los lotes del módulo. "
                           "Una dispersión grande significa que una sola fecha de módulo "
                           "puede ocultar estados biológicos distintos.",
    "gdd_acum_poda_obs": "Suma de GDD de las semanas con cosecha observadas después de la "
                         "poda. No equivale al GDD completo desde poda si faltan semanas o "
                         "clima anterior a S01.",
    "flores_promedio": "Conteo real de flores por turno, promediado entre los turnos del "
                       "módulo esa semana. Es la primera fase fenológica MEDIDA del "
                       "tablero, no un proxy derivado de la fecha de poda. Fuente: hoja "
                       "EvFlores de «DAtos mes.xlsx».",
    "flores_dispersion_relativa": "Desvío entre turnos dividido por el promedio. Alta "
                                  "dispersión significa que el promedio de módulo puede "
                                  "ocultar turnos con floración muy distinta entre sí — no "
                                  "hay área por turno en esta hoja para ponderar mejor.",
}

# Configuración elegida por barrido de 108 combinaciones (2026-08-07), midiendo con
# «deja-una-semana-fuera» y reportando con «deja-un-bloque-fuera». Nunca al revés: elegir
# mirando la métrica que se reporta la infla.
#
# Contra la configuración anterior (prof 3, lr 0,03, sin regularización), promediando
# 8 semillas:
#
#     anterior : selección +0,344   honesta −0,116   MAE 757 kg/ha
#     ésta     : selección +0,402   honesta +0,053   MAE 686 kg/ha
#     baseline «predecir la media», partición honesta:  −0,147   MAE 756
#
# La anterior tenía el MAE de predecir el promedio: no medía nada. La mejora sobrevive al
# cambio de semilla con 5,1 desviaciones típicas de margen.
#
# Por qué árboles profundos con aprendizaje muy lento: la profundidad deja capturar
# interacciones entre clima y riego, y el freno viene de `min_child_weight` (ninguna hoja
# con menos de 10 observaciones) y de `reg_lambda`, no de amputar el árbol.
#
# Este barrido se hizo con las 6 variables SIN desfase. FEATURES pasó después a las 5
# variables `*_lag` más GDD (ver `docs/data/resumen_sesion.md` §6), y esta misma
# configuración —sin volver a barrer— ya mejoraba a la anterior en 21 desviaciones
# típicas (+0,204 contra −0,012) sobre el nuevo espacio.
#
# Re-barrido para las 7 variables con desfase (2026-08-07, §7 del resumen de sesión):
# 264 configuraciones (profundidad 3-8, lr 0,01-0,08, n 200-600, min_child_weight 1-20,
# reg_lambda 0-20), elegidas con «por_semana» y evaluadas con «por_bloque». Resultado:
# NINGUNA le gana a la configuración de abajo bajo la partición honesta. El mejor
# candidato por la métrica de selección (prof 7, lr 0,02, n 400) da, con 8 semillas,
# +0,1845 ± 0,0226 — empatado o levemente peor que ésta (+0,2040 ± 0,0102) y más
# inestable entre semillas. Cerrado: esta configuración ya está cerca del óptimo para
# el espacio actual de variables; no hace falta cambiarla.
PARAMS: dict[str, object] = {
    "n_estimators": 300,
    "max_depth": 6,
    "learning_rate": 0.01,
    "min_child_weight": 10,
    "reg_lambda": 5,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 0,
    # n_jobs=1 a propósito: con 452 filas el reparto entre hilos cuesta más de lo que
    # ahorra (medido: 17,4 s contra 18,8 s con dos hilos), y además fija el resultado.
    # El paralelismo que sí rinde es entre configuraciones, y lo hace `evaluacion.py`.
    "n_jobs": 1,
}

# Hojas que el Excel de campaña tiene que traer, con sus nombres tal como vienen.
HOJAS: frozenset[str] = frozenset(
    {"KgHa", "Temp Max-Min", "Rad y ET", "Riego", "DPV"}
)

# Copia de la campaña 2025 versionada en el repo. Sirve de atajo para abrir el tablero
# sin subir nada; `AQUANQA_XLSX` permite apuntar a otro archivo sin tocar el código.
XLSX_REPO = Path(
    os.environ.get(
        "AQUANQA_XLSX",
        Path(__file__).resolve().parents[3] / "docs" / "data" / "IA.final.xlsx",
    )
)

# Paleta. Azul = por debajo / valor bajo, rojo = por encima / valor alto, gris = totales.
AZUL = "#3B7DD8"
ROJO = "#E8443A"
VERDE = "#7FB069"
GRIS = "#5A6472"
NARANJA = "#D9822B"

# Iconos de Material Symbols, que Streamlit resuelve con la sintaxis `:material/nombre:`.
# Sin emojis: se ven distinto en cada sistema operativo y no admiten color de tema.
ICONO = {
    "resumen": ":material/lab_profile:",
    "conclusiones": ":material/fact_check:",
    "impacto": ":material/eco:",
    "r2": ":material/analytics:",
    "explicacion": ":material/psychology:",
    "metodologia": ":material/menu_book:",
    "correlaciones": ":material/grid_on:",
    "importancia": ":material/leaderboard:",
    "por_modulo": ":material/dashboard:",
    "auditoria": ":material/query_stats:",
    "clima": ":material/thermostat:",
    "modelo": ":material/account_tree:",
    "validacion": ":material/rule:",
    "datos": ":material/table_rows:",
    "aviso": ":material/warning:",
    "info": ":material/info:",
    "ok": ":material/check_circle:",
    "error": ":material/dangerous:",
}


class Seccion(NamedTuple):
    """Una entrada del menú lateral."""

    clave: str
    titulo: str
    icono: str
    resumen: str


# El orden separa deliberadamente tres preguntas que antes aparecían mezcladas:
# asociación agronómica, capacidad predictiva y explicación del modelo. Ninguna de ellas
# se presenta como efecto causal con la campaña disponible.
SECCIONES: tuple[Seccion, ...] = (
    Seccion("resumen", "Pregunta, datos y límites", ICONO["resumen"],
            "Qué queremos medir, qué permite la campaña actual y qué no"),
    Seccion("conclusiones", "Conclusiones y hallazgos", ICONO["conclusiones"],
            "Qué dice el conjunto de evidencias y qué no permite afirmar"),
    Seccion("impacto", "Impacto agronómico", ICONO["impacto"],
            "Asociación, calendario, rezagos, módulos, placebo, frutos y peso"),
    Seccion("r2", "Qué explica el R²", ICONO["r2"],
            "Modelo completo, familias de variables y aporte fuera de muestra"),
    Seccion("modelo", "Modelo predictivo", ICONO["modelo"],
            "Modelos simples, XGBoost, ventanas y validación temporal"),
    Seccion("explicacion", "Explicación del modelo", ICONO["explicacion"],
            "SHAP global y auditoría de una predicción, sin lectura causal"),
    Seccion("datos", "Datos y calidad", ICONO["datos"],
            "Hallazgos, panel consolidado, filtros y exportación"),
    Seccion("metodologia", "Marco metodológico y referencias", ICONO["metodologia"],
            "Qué sustenta cada fuente y qué falta antes de implementar DML"),
)

PODA_REPO = Path(
    os.environ.get(
        "AQUANQA_PODA_XLSX",
        Path(__file__).resolve().parents[3] / "docs" / "data" / "M_Poda.xlsx",
    )
)

# «DAtos mes.xlsx» trae la hoja EvFlores: conteo real de flores por fundo físico, módulo,
# turno y semana — la primera fase fenológica MEDIDA que tiene el tablero, no un proxy
# derivado de la poda. Mismo archivo tiene HistoricosVolumen, VarClima, Riego y Resumen2025,
# que no se integran todavía (ver docs/data/resumen_sesion.md §11).
FLORACION_REPO = Path(
    os.environ.get(
        "AQUANQA_FLORACION_XLSX",
        Path(__file__).resolve().parents[3] / "docs" / "data" / "DAtos mes.xlsx",
    )
)


def etiqueta(col: str) -> str:
    """Nombre legible de una columna; si no está en el diccionario, el nombre crudo."""
    return ETIQUETAS.get(col, col)


def glosa(col: str) -> str | None:
    """Explicación en lenguaje llano de una variable, para tooltips y glosario."""
    return GLOSARIO.get(col)
