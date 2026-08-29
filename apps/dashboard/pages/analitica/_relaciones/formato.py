"""Traducción de cifras crudas al castellano con que se habla del cultivo."""

from __future__ import annotations

import pandas as pd

from analitica.config import etiqueta
from components import ui

from .textos import OBJETIVOS


def en_minuscula(texto: str) -> str:
    """Baja solo la primera letra: `.lower()` destruye siglas como E5, DPV o ETo."""
    return texto[:1].lower() + texto[1:] if texto else texto


def nombre_variable(clave: str) -> str:
    return en_minuscula(etiqueta(clave))


def nombre_objetivo(clave: str) -> str:
    return OBJETIVOS.get(clave, (nombre_variable(clave), "", "kilos"))[0]


def unidad_objetivo(clave: str) -> str:
    return OBJETIVOS.get(clave, ("", "", ""))[1]


def grupo_objetivo(clave: str) -> str:
    return OBJETIVOS.get(clave, ("", "", "kilos"))[2]


def numero(valor: float, decimales: int = 1) -> str:
    if pd.isna(valor):
        return "—"
    if abs(valor) >= 1000:
        return ui.miles(valor)
    return f"{valor:,.{decimales}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def efecto_legible(respuesta: str, efecto: float) -> tuple[str, str]:
    """El efecto en la unidad en que se habla de esa variable.

    Las proporciones se guardan entre 0 y 1, y decir «0,004 más de descarte» no lo entiende
    nadie: se pasa a puntos porcentuales, que es como se conversa en planta.
    """
    unidad = unidad_objetivo(respuesta)
    if unidad == "%":
        efecto, unidad = efecto * 100, "puntos de descarte"
    if abs(efecto) < 0.05:
        # Correlación real con recorrido nulo: decir «0,0» leería como error de cálculo.
        return "menos de 0,1", unidad
    decimales = 0 if abs(efecto) >= 100 else (1 if abs(efecto) >= 1 else 2)
    return numero(efecto, decimales).lstrip("-"), unidad


def frase_efecto(fila: dict) -> str:
    """El hallazgo dicho en unidades reales, que es lo único que permite dimensionarlo.

    Se expresa sobre el recorrido intercuartílico del predictor —el rango en que se mueve la
    mitad central de los lotes— y no sobre «una unidad más», porque una unidad puede ser un
    salto que nunca ocurre en la práctica: nadie duplica el calibre de un módulo.
    """
    efecto = fila.get("efecto_rango_iqr")
    if efecto is None or pd.isna(efecto):
        return ""
    efecto = float(efecto)
    respuesta = fila["respuesta"]
    cifra, unidad = efecto_legible(respuesta, efecto)
    direccion = "más" if efecto > 0 else "menos"
    # Cuando la unidad ya nombra la variable —«flores», «puntos de descarte»— añadir «de
    # flores por planta» detrás sonaría a tartamudeo.
    nombre = nombre_objetivo(respuesta)
    if unidad and (unidad in nombre or nombre in unidad):
        medida = f"{cifra} {max(unidad, nombre, key=len)} {direccion}"
    else:
        medida = f"{cifra} {unidad} {direccion} de {nombre}".replace("  ", " ")

    relativo = ""
    mediana = fila.get("mediana_respuesta")
    if mediana is not None and not pd.isna(mediana) and abs(mediana) > 0:
        pct = abs(100 * efecto / mediana)
        if pct >= 150:
            # Un «719 % sobre lo habitual» no se procesa; «multiplica por 8» sí.
            relativo = f", que multiplica por {1 + pct / 100:.0f} lo habitual"
        elif pct >= 3:
            relativo = f", un {pct:.0f} % sobre lo habitual"
    return (
        f"Pasar del cuarto más bajo al más alto de {nombre_variable(fila['predictor'])} "
        f"acompaña a **{medida}**{relativo}."
    )
