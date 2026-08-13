"""Capa de presentación: una sección por módulo, más los constructores de figuras.

Cada sección expone `render(...)`. Las que tienen controles llevan `@st.fragment`: sin
eso, mover un selector reejecuta el script entero. Es seguro porque ningún control afecta
a otra sección — si alguno llegara a hacerlo, necesitaría `st.rerun(scope="app")`.

`graficos` no importa Streamlit: recibe datos y devuelve figuras de Plotly.
"""

from vistas import (
    auditoria,
    clima,
    conclusiones,
    correlaciones,
    datos_calidad,
    explicacion,
    graficos,
    impacto,
    importancia,
    metodologia,
    modelo,
    panel_consolidado,
    por_modulo,
    resumen,
    validacion,
)

__all__ = [
    "auditoria", "clima", "conclusiones", "correlaciones", "datos_calidad", "explicacion", "graficos",
    "impacto", "importancia", "metodologia", "modelo", "panel_consolidado",
    "por_modulo", "resumen", "validacion",
]
