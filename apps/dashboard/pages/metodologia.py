"""Página «Marco metodológico y referencias» — puerto completo de
Contenido estático, sin dependencia del panel.
"""

from __future__ import annotations

import dash
import pandas as pd
from dash import html

from analitica import settings
from components import ui

dash.register_page(
    __name__, path="/metodologia", name="Marco metodológico y referencias",
    order=1, grupo="Referencia",
)

FUENTES = (
    (
        "Data Science for Weather Impacts on Crop Yield",
        "fsufs-04-00052.pdf",
        "Información Mutua, relaciones no lineales, extremos y remuestreo.",
        "No convierte dependencia en causalidad y usa una serie histórica mucho mayor.",
    ),
    (
        "Weather by production-management phases",
        "sustainability-18-03806-v2.pdf",
        "Codificar el clima por fases reales en vez de promedios de toda la campaña.",
        "Sus fases son operaciones de manejo y su modelo profundo no se traslada a 50 semanas.",
    ),
    (
        "Crop diversification under climate change",
        "isprs-archives-XLVIII-1-W2-2023-1379-2023.pdf",
        "DML, CATE, solapamiento y heterogeneidad ambiental del efecto.",
        "Requiere un tratamiento definido y datos suficientes en tratados y controles.",
    ),
    (
        "Comparing XGBoost and DML for rice nitrogen",
        "remotesensing-18-00420.pdf",
        "Separar predicción de efecto causal y evitar variables posteriores al tratamiento.",
        "Sus efectos son locales a otra explotación y no son cifras transferibles.",
    ),
    (
        "Economic Causal Inference Based on DML",
        "2502.19898v1.pdf",
        "Ortogonalización, cross-fitting y tratamientos binarios o continuos.",
        "Es una guía con datos simulados, no validación agrícola de nuestra campaña.",
    ),
)


def _fuentes() -> html.Div:
    carpeta = settings.XLSX_REPO.parent / "new.info"
    filas = pd.DataFrame([
        {
            "Fuente": titulo,
            "Archivo local": archivo,
            "Qué sustenta": aporta,
            "Qué no autoriza": limite,
            "Disponible": "Sí" if (carpeta / archivo).is_file() else "No",
        }
        for titulo, archivo, aporta, limite in FUENTES
    ])
    return html.Div([
        ui.tabla_desde_df(filas, plano=True),
        html.P(f"Carpeta revisada: {carpeta}", className="mt-1 text-xs text-slate-500"),
    ])


def _capas() -> html.Div:
    filas = pd.DataFrame([
        {
            "Capa": "Asociación estadística",
            "Pregunta": "¿Qué variables se mueven junto con kg/ha, frutos o peso?",
            "Herramientas": "Pearson, Spearman, forma, rezagos, placebo, control temporal",
            "Estado": "Implementada",
        },
        {
            "Capa": "Aporte predictivo",
            "Pregunta": "¿Qué mejora la predicción fuera de muestra?",
            "Herramientas": "R², ablación, grupos, XGBoost y validación temporal",
            "Estado": "Implementada",
        },
        {
            "Capa": "Efecto agronómico estimado",
            "Pregunta": "¿Cuánto cambiaría el resultado al cambiar la exposición?",
            "Herramientas": "DML/CATE con tratamiento, confusores, solapamiento e IC",
            "Estado": "No identificable con la campaña actual",
        },
    ])
    return ui.panel(
        "1 · Tres resultados que deben mantenerse separados",
        ui.parrafo(
            "El tablero separa asociación, predicción y efecto agronómico porque cada "
            "pregunta necesita datos y supuestos distintos. Una capa no reemplaza a la otra."
        ),
        ui.tabla_desde_df(filas, plano=True),
        ayuda="Frontera entre lo que observamos, lo que predecimos y lo que podríamos atribuir.",
    )


def _datos_faltantes() -> html.Div:
    filas = pd.DataFrame(
        [
            ("Campaña", "Separar año, estación y decisiones de manejo", "Falta replicación"),
            ("Fundo y módulo", "Unidad observacional y agrupación", "Disponible"),
            ("Fecha de poda", "Origen del tiempo agronómico", "Disponible en M_Poda, a nivel lote"),
            ("Días desde poda", "Alinear módulos con calendarios distintos", "Derivable; proxy de módulo"),
            ("Fase fenológica", "Asignar la exposición al proceso biológico correcto", "Falta"),
            ("Clima por fase", "Temperatura, DPV, radiación y ETo en ventanas reales", "Falta"),
            ("Riego con cadencia", "Distinguir día, semana, cero y dato faltante", "Parcial"),
            ("Variedad y edad", "Confusores y modificadores del efecto", "Parcial en M_Poda"),
            ("Densidad", "Convertir componentes por planta a total comparable", "Falta"),
            ("Fertilización y eventos", "Evitar atribuir al clima decisiones operativas", "Falta"),
            ("Frutos y peso", "Resultados biológicos secundarios, no controles del kg/ha", "Parcial"),
        ],
        columns=["Campo", "Para qué se necesita", "Estado actual"],
    )
    return ui.panel(
        "3 · Qué falta para estimar un efecto agronómico",
        ui.parrafo(
            "La campaña actual permite asociación y diagnóstico predictivo. Para hablar de "
            "cuánto cambiaría el resultado al modificar una exposición faltan controles, "
            "tratamientos y replicación suficientes."
        ),
        ui.tabla_desde_df(filas, plano=True),
        ui.semaforo(
            "aviso",
            "Frutos y peso deben analizarse como **resultados secundarios** para "
            "entender cuajado y llenado. No deben entrar como predictores de kg/ha ni "
            "como controles posteriores al clima o al riego. La fecha de poda ya se usa "
            "como control temporal proxy; la fase fenológica observada aún falta.",
        ),
        ayuda="Inventario de información necesaria antes de una estimación causal.",
    )


def _resumen() -> html.Div:
    carpeta = settings.XLSX_REPO.parent / "new.info"
    disponibles = sum((carpeta / archivo).is_file() for _, archivo, _, _ in FUENTES)
    faltantes = 0
    parciales = 0
    filas = [
        ("Campaña", "Separar año, estación y decisiones de manejo", "Falta replicación"),
        ("Fundo y módulo", "Unidad observacional y agrupación", "Disponible"),
        ("Fecha de poda", "Origen del tiempo agronómico", "Disponible en M_Poda, a nivel lote"),
        ("Días desde poda", "Alinear módulos con calendarios distintos", "Derivable; proxy de módulo"),
        ("Fase fenológica", "Asignar la exposición al proceso biológico correcto", "Falta"),
        ("Clima por fase", "Temperatura, DPV, radiación y ETo en ventanas reales", "Falta"),
        ("Riego con cadencia", "Distinguir día, semana, cero y dato faltante", "Parcial"),
        ("Variedad y edad", "Confusores y modificadores del efecto", "Parcial en M_Poda"),
        ("Densidad", "Convertir componentes por planta a total comparable", "Falta"),
        ("Fertilización y eventos", "Evitar atribuir al clima decisiones operativas", "Falta"),
        ("Frutos y peso", "Resultados biológicos secundarios, no controles del kg/ha", "Parcial"),
    ]
    for _, _, estado in filas:
        faltantes += estado == "Falta"
        parciales += estado.startswith("Parcial")
    return ui.fila_kpi([
        ui.kpi(
            "Capas de análisis",
            "3",
            nota="Asociación, predicción y efecto agronómico.",
        ),
        ui.kpi(
            "Fuentes revisadas",
            str(len(FUENTES)),
            nota="Referencias usadas para justificar decisiones de método.",
        ),
        ui.kpi(
            "PDF disponibles",
            f"{disponibles} / {len(FUENTES)}",
            nota="Archivos encontrados en la carpeta local del proyecto.",
        ),
        ui.kpi(
            "Campos pendientes",
            str(faltantes),
            nota=f"{parciales} campos están disponibles solo de forma parcial.",
        ),
    ])


def _respuesta_corta() -> html.Div:
    return ui.panel(
        "Respuesta corta",
        ui.semaforo(
            "aviso",
            "**El tablero ya separa tres preguntas, pero no puede convertir asociación "
            "en causalidad con esta campaña.** Las referencias sirven para justificar el "
            "método y sus límites; no aportan coeficientes transferibles a Aqu Anqa.",
        ),
        html.Div(
            className="grid gap-4",
            children=[
                html.Div([
                    html.Div("Este análisis responde", className="text-sm font-semibold text-slate-700"),
                    html.P(
                        "Qué sostiene cada capa del tablero, qué referencias orientan la "
                        "elección y qué información todavía falta.",
                        className="mt-1.5 text-sm leading-relaxed text-slate-600",
                    ),
                ]),
                html.Div([
                    html.Div("Cómo ayuda al modelo", className="text-sm font-semibold text-slate-700"),
                    html.P(
                        "Evita mezclar evidencia observacional, capacidad predictiva y "
                        "efectos causales en una sola conclusión.",
                        className="mt-1.5 text-sm leading-relaxed text-slate-600",
                    ),
                ]),
            ],
        ),
        ayuda="La conclusión metodológica que conecta Referencia con el resto del dashboard.",
    )


def layout():
    return html.Div(
        className="space-y-4",
        children=[
            ui.encabezado_pagina(
                "¿Qué podemos afirmar y qué todavía no?",
                "El marco metodológico mantiene separadas la asociación, la predicción y "
                "la estimación de un efecto agronómico.",
            ),
            _resumen(),
            _respuesta_corta(),
            _capas(),
            ui.panel(
                "2 · Fuentes académicas revisadas",
                ui.parrafo(
                    "Las referencias justifican decisiones de método; no aportan coeficientes "
                    "transferibles a Aqu Anqa. Los PDFs se conservan como apoyo de bioestadística, "
                    "estimación e incertidumbre, no como evidencia agronómica directa."
                ),
                _fuentes(),
                ayuda="Qué ideas se tomaron de cada fuente y qué límites impiden trasladarlas directamente.",
            ),
            _datos_faltantes(),
        ],
    )
