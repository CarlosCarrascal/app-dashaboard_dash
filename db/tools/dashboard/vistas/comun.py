"""Piezas de interfaz reutilizables: formato, controles y explicación.

La regla que gobierna este módulo: **nada se muestra sin decir cómo se lee**. Un gráfico
con un párrafo estático debajo no cumple — el lector no sabe si el párrafo describe lo
que está viendo o lo que veía el autor. Por eso acá hay tarjetas de lectura, semáforos y
un glosario que se despliega donde se necesita, en vez de un bloque de texto al final.
"""

from __future__ import annotations

from collections.abc import Iterable

import streamlit as st

from config import GLOSARIO, ICONO, etiqueta, glosa

# ── Formato ──────────────────────────────────────────────────────────────────


def miles(v: float, formato: str = "{:,.0f}") -> str:
    """Número con punto como separador de miles, que es lo que se usa en el fundo."""
    return formato.format(v).replace(",", "@").replace(".", ",").replace("@", ".")


def entero(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


# ── Controles ────────────────────────────────────────────────────────────────


def selector_variable(
    opciones: Iterable[str], clave: str, rotulo: str = "Variable", indice: int = 0
) -> str:
    """Desplegable de variable, con su explicación como ayuda emergente."""
    ops = list(opciones)
    return st.selectbox(
        rotulo, ops, index=indice, format_func=etiqueta, key=clave,
        help="Pasá el cursor sobre el nombre en el glosario para ver qué mide cada una.",
    )


# ── Explicación ──────────────────────────────────────────────────────────────


def encabezado(titulo: str, ayuda: str | None = None, nivel: str = "###") -> None:
    """Título de bloque con un signo de ayuda al lado si hace falta."""
    if ayuda:
        col1, col2 = st.columns([20, 1])
        col1.markdown(f"{nivel} {titulo}")
        col2.markdown("")
        col2.button(":material/help:", key=f"ayuda_{titulo}", help=ayuda,
                    type="tertiary", disabled=True)
    else:
        st.markdown(f"{nivel} {titulo}")


def como_leer(texto: str, titulo: str = "Cómo se lee este gráfico") -> None:
    """Instrucción de lectura, plegada por omisión para no competir con el dato."""
    with st.expander(f"{ICONO['info']}  {titulo}", expanded=False):
        st.markdown(texto)


def semaforo(estado: str, mensaje: str) -> None:
    """Conclusión con color: verde confirma, ámbar matiza, rojo desmiente."""
    if estado == "ok":
        st.success(mensaje, icon=ICONO["ok"])
    elif estado == "aviso":
        st.warning(mensaje, icon=ICONO["aviso"])
    elif estado == "error":
        st.error(mensaje, icon=ICONO["error"])
    else:
        st.info(mensaje, icon=ICONO["info"])


def veredicto_de_prueba(
    pregunta: str, respuesta: str, estado: str, evidencia: str
) -> None:
    """Una prueba estadística presentada como pregunta, respuesta y evidencia.

    Es el formato que hace legible un resultado técnico para quien no lo es: primero qué
    se preguntó, después la respuesta en una línea, y solo entonces los números.
    """
    st.markdown(f"**{pregunta}**")
    semaforo(estado, respuesta)
    with st.expander(f"{ICONO['info']}  La evidencia detrás de esta respuesta"):
        st.markdown(evidencia)


def glosario(claves: Iterable[str] | None = None, titulo: str = "Glosario") -> None:
    """Despliega qué significa cada variable, en lenguaje llano."""
    claves = list(claves) if claves is not None else list(GLOSARIO)
    with st.expander(f"{ICONO['info']}  {titulo}"):
        for c in claves:
            texto = glosa(c)
            if texto:
                st.markdown(f"**{etiqueta(c)}** — {texto}")


def escala_correlacion() -> None:
    """Recordatorio de qué significa un r, para quien no lee correlaciones a diario."""
    st.caption(
        "**Cómo leer un coeficiente de correlación (r):** va de −1 a +1. "
        "Cerca de **0** no hay relación lineal. **Positivo** = cuando una sube, la otra "
        "tiende a subir. **Negativo** = cuando una sube, la otra tiende a bajar. "
        "Por encima de **|0,5|** se considera una asociación fuerte — lo que no significa "
        "que una cause la otra."
    )


def tarjetas(items: list[tuple[str, str, str | None]]) -> None:
    """Fila de métricas con su ayuda. Cada item es (rótulo, valor, ayuda)."""
    cols = st.columns(len(items))
    for col, (rotulo, valor, ayuda) in zip(cols, items, strict=True):
        col.metric(rotulo, valor, help=ayuda)


# ── Modo presentación ────────────────────────────────────────────────────────
# Interruptor temporal para mostrar el tablero sin las advertencias técnicas —
# `app.py` apaga `st.warning`/`st.error` mientras está activo. Acá solo vive el lector
# del interruptor y el bloque de explicación simple, para que cada gráfico pueda
# resumirse en una frase sin tecnicismos cuando se está presentando.


def presentando() -> bool:
    return bool(st.session_state.get("modo_presentacion", False))


def explica_simple(texto: str) -> None:
    """Un resumen del gráfico en una frase, sin tecnicismos — solo en modo presentación.

    No reemplaza a `como_leer`: ese sigue explicando el gráfico en detalle para quien
    quiera auditar el número. Esto es la versión de un renglón para quien solo necesita
    llevarse la idea.
    """
    if presentando():
        st.markdown(f"🔎 **En simple:** {texto}")
