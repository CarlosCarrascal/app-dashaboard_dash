"""Cálculo puro: del Excel al panel, del panel al modelo, del modelo a las métricas.

Ninguno de estos módulos importa Streamlit ni Plotly. Es la regla que sostiene la capa:
se puede ejecutar y probar desde una consola, sin levantar la app.
"""

from nucleo import clima
from nucleo.datos import Hallazgo, Panel, cargar_panel, diagnostico_ventanas
from nucleo.evaluacion import (
    CONJUNTOS,
    PARTICIONES,
    PLAN_VALIDACION,
    REFERENCIAS,
    Conjunto,
    Medicion,
    Particion,
    Paso,
    Referencia,
    aporte_por_grupo,
    aporte_por_variable,
    comparar_familias,
    correlaciones_con_objetivo,
    descomposicion_varianza,
    medir,
    tabla_validacion,
)
from nucleo.informe import construir as construir_informe
from nucleo.modelo import Ajuste, Consistencia, entrenar, verificar_consistencia

__all__ = [
    "CONJUNTOS", "PARTICIONES", "PLAN_VALIDACION", "REFERENCIAS",
    "Ajuste", "Conjunto", "Consistencia", "Hallazgo", "Medicion", "Panel", "Particion",
    "Paso", "Referencia", "aporte_por_grupo", "aporte_por_variable", "cargar_panel",
    "diagnostico_ventanas", "clima",
    "comparar_familias", "construir_informe", "correlaciones_con_objetivo",
    "descomposicion_varianza", "entrenar", "medir", "tabla_validacion",
    "verificar_consistencia",
]
