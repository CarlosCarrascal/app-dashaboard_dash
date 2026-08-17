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
        ui.tabla_desde_df(filas),
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
    return html.Div([
        ui.titulo_seccion("Tres resultados que deben mantenerse separados"),
        ui.tabla_desde_df(filas),
    ])


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
    return html.Div([
        ui.titulo_seccion("Tabla agronómica necesaria antes de DML"),
        ui.tabla_desde_df(filas),
        ui.semaforo(
            "aviso",
            "Frutos y peso deben analizarse como **resultados secundarios** para "
            "entender cuajado y llenado. No deben entrar como predictores de kg/ha ni "
            "como controles posteriores al clima o al riego. La fecha de poda ya se usa "
            "como control temporal proxy; la fase fenológica observada aún falta.",
        ),
    ])


def layout():
    return html.Div(
        className="space-y-6",
        children=[
            ui.parrafo(
                "Las referencias justifican decisiones de método; no aportan "
                "coeficientes transferibles a Aqu Anqa. Los PDFs pesqueros se conservan "
                "como apoyo de bioestadística, estimación e incertidumbre, no como "
                "evidencia agronómica directa."
            ),
            _capas(),
            html.Div([ui.titulo_seccion("Fuentes académicas revisadas"), _fuentes()]),
            _datos_faltantes(),
        ],
    )
