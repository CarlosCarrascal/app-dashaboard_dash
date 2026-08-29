"""Presentación común de resultados versionados de ``analytics``.

Todo lo que se muestra en `/analitica/*` pasa por acá antes de llegar a la pantalla: las
cabeceras se traducen con `analitica.config.etiqueta`, los valores codificados con
`VALORES_ANALITICOS` y los números con `FORMATO_ANALITICO`. La regla es que ningún nombre
de columna de PostgreSQL ni ningún enum en inglés llegue a la interfaz — quien la usa
conoce el cultivo, no el esquema de la base.
"""

from __future__ import annotations

from collections.abc import Iterable
from numbers import Real

import pandas as pd
from dash import html

from analitica.config import (
    ETIQUETAS_ANALITICAS,
    FORMATO_ANALITICO,
    VALORES_ANALITICOS,
    etiqueta,
    glosa,
)
from components import ui
from servicios.analytics import estado_analitico


def datos() -> dict[str, object]:
    return estado_analitico()


# ── Formato de valores ───────────────────────────────────────────────────────


def numero(valor, decimales: int = 2) -> str:
    """Número con punto de millar, que es la convención del resto del tablero.

    Antes usaba el formato por defecto de Python (coma), así que la misma cifra salía
    `3,911,651` en Proyección y `3.911.651` en las demás páginas.
    """
    if pd.isna(valor):
        return "—"
    return ui.miles(float(valor), f"{{:,.{decimales}f}}")


def _formatear(columna: str, valor) -> str:
    """Aplica el formato declarado para esa columna en `FORMATO_ANALITICO`."""
    if valor is None or (not isinstance(valor, (list, dict)) and pd.isna(valor)):
        return "—"
    # Los campos `jsonb` llegan como dict o list. Volcarlos con `json.dumps` deja llaves y
    # comillas escapadas en mitad de la tabla; se leen mucho mejor como pares sueltos.
    if isinstance(valor, dict):
        return " · ".join(f"{etiqueta(k)}: {_escalar(v)}" for k, v in valor.items()) or "—"
    if isinstance(valor, list):
        return ", ".join(str(v) for v in valor) or "—"

    clave = FORMATO_ANALITICO.get(columna)
    try:
        match clave:
            case "miles0":
                return ui.miles(float(valor))
            case "archivo":
                # De la ruta completa solo importa el nombre: la carpeta se repite en todas
                # las filas y empuja el resto de la tabla fuera de la pantalla.
                return str(valor).replace("\\", "/").rsplit("/", 1)[-1]
            case "entero":
                return f"{int(valor)}"
            # Dos escalas distintas de porcentaje conviven en `analytics.metric`: la
            # mayoría llega como fracción, pero `sesgo_pct` ya viene en puntos.
            case "pct_frac":
                return f"{float(valor) * 100:.1f} %".replace(".", ",")
            case "pct_pp":
                return f"{float(valor):.1f} %".replace(".", ",")
            case "dec1" | "dec2" | "dec3":
                return f"{float(valor):.{int(clave[-1])}f}".replace(".", ",")
            case "signo3":
                return f"{float(valor):+.3f}".replace(".", ",")
    except (TypeError, ValueError):
        pass
    return str(valor)


def _escalar(valor) -> str:
    """Un valor suelto dentro de un campo `jsonb`, con punto de millar si es un entero grande."""
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    if isinstance(valor, int) and abs(valor) >= 1000:
        return ui.miles(valor)
    return str(valor)


# Columnas cuyo contenido es el nombre de otra variable, no un valor. En el barrido de
# relaciones, `predictor` vale `gdd_4_4` o `frutos_por_planta_muestra`: hay que traducirlas
# con el mismo diccionario que las cabeceras, o el nombre técnico llega a la pantalla.
COLUMNAS_CON_NOMBRES_DE_VARIABLE = frozenset({"predictor", "respuesta", "variable"})


def valor_legible(columna: str, valor):
    """Traduce un valor codificado de la base a su nombre en español."""
    if columna in COLUMNAS_CON_NOMBRES_DE_VARIABLE and isinstance(valor, str):
        return etiqueta(valor)
    mapa = VALORES_ANALITICOS.get(columna)
    if mapa and isinstance(valor, str):
        return mapa.get(valor, valor)
    return valor


# Se ordenan de más largo a más corto para que `frutos_por_planta_muestra` se sustituya
# entero antes de que `frutos_por_planta` se coma su prefijo.
_VARIABLES_EN_TEXTO = sorted(ETIQUETAS_ANALITICAS, key=len, reverse=True)


def frase_legible(texto: str) -> str:
    """Sustituye los nombres técnicos de variable que el pipeline deja dentro de una frase.

    Las conclusiones se redactan en `proyeccion/relaciones.py` con el nombre de columna
    literal («asociación entre tasa_cuajo_observada y frutos_por_planta_muestra»). El texto
    guardado conserva ese nombre a propósito, porque es el que permite auditarlo; lo que se
    traduce es la copia que se muestra.
    """
    if not isinstance(texto, str):
        return texto
    for variable in _VARIABLES_EN_TEXTO:
        if "_" in variable and variable in texto:
            texto = texto.replace(variable, etiqueta(variable))
    return texto


# ── Bloques reutilizables ────────────────────────────────────────────────────


def estado_fuente(estado: dict[str, object]) -> html.Div:
    """De dónde salieron los números que se están viendo, sin jerga de base de datos."""
    if estado["error"]:
        return ui.semaforo(
            "error",
            "**Fuente oficial · PostgreSQL.** No se pudo leer el histórico de análisis. "
            "La página se abre igual, pero "
            "las cifras no están disponibles hasta que la base responda.\n\n"
            f"Detalle técnico: {estado['error']}",
        )
    runs = estado["runs"]
    if runs.empty:
        return ui.semaforo(
            "aviso",
            "**Fuente oficial · PostgreSQL.** Todavía no se ha ejecutado ningún análisis. "
            "Las pantallas de esta sección "
            "muestran resultados ya calculados y guardados; hasta que exista una ejecución, "
            "no hay nada que mostrar.",
        )
    ultimo = runs.iloc[0]
    fallback = bool((ultimo.cobertura or {}).get("fallback", False))
    tipo = valor_legible("tipo", ultimo.tipo)
    estado_corrida = valor_legible("estado", ultimo.estado)
    corte = ""
    if "corte_datos" in runs and pd.notna(ultimo.corte_datos):
        corte = f" con datos hasta el {pd.Timestamp(ultimo.corte_datos):%d/%m/%Y}"

    if fallback:
        return ui.semaforo(
            "aviso",
            f"**Los datos vienen del Excel de respaldo, no de la base.** Última ejecución: "
            f"{tipo.lower()} n.º {int(ultimo.run_id)} ({estado_corrida.lower()}){corte}. "
            "El respaldo no conserva el histórico versionado, así que la comparación de "
            "modelos no puede considerarse oficial.",
        )
    # Que todo esté en orden es el caso normal, y el caso normal no merece una caja verde
    # de cuatro líneas: es contexto, no una conclusión. Los casos de arriba —fallo de base,
    # sin corridas, respaldo en Excel— sí interrumpen, y por eso siguen siendo semáforos.
    huella = str(ultimo.firma_snapshot)[:12]
    partes = [
        ("PostgreSQL · base de producción", None),
        (f"{tipo.lower()} n.º {int(ultimo.run_id)}", estado_corrida.lower()),
    ]
    if corte:
        partes.append((corte.replace(" con datos hasta el ", "datos hasta "), None))
    return html.Div(
        className="flex flex-wrap items-center gap-x-2 gap-y-1 px-1 text-xs text-slate-500",
        children=[
            ui.icono("datos-calidad", "h-3.5 w-3.5 text-slate-400"),
            *[
                html.Span(
                    texto,
                    title=titulo,
                    className="after:ml-2 after:text-slate-300 after:content-['·']",
                )
                for texto, titulo in partes
            ],
            html.Code(
                huella,
                title="Huella de los datos: dos ejecuciones con la misma huella partieron "
                "exactamente de los mismos datos.",
                className="rounded bg-stone-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-500",
            ),
        ],
    )


# Qué es cada tabla del origen, en términos de la operación y no del esquema.
FUENTES = {
    "forecast": (
        "Proyección semanal publicada",
        "El pronóstico que el equipo ya venía emitiendo cada semana por lote, con "
        "sus versiones. Es el punto de partida y el modelo a superar.",
    ),
    "cosecha": (
        "Cosecha registrada",
        "Kilos efectivamente cosechados por lote y día, con el peso de baya y las "
        "plantas cosechadas. Es la verdad contra la que se mide todo.",
    ),
    "flores": (
        "Censo de floración",
        "Conteo de flores y cuajado por planta en las evaluaciones de campo.",
    ),
    "estados": (
        "Censo de estados fenológicos",
        "Reparto de frutos entre los estados E1 a E5, que marca cuán avanzado va el "
        "lote hacia la cosecha.",
    ),
    "bayas": (
        "Medición de bayas",
        "Diámetro de fruto medido en campo, que anticipa el peso final.",
    ),
    "poda": (
        "Registro de poda",
        "Fecha de poda por lote: el reloj biológico desde el que se cuenta todo.",
    ),
    "clima": (
        "Estación meteorológica",
        "Temperatura, humedad, radiación, evapotranspiración y lluvia. Es un dato del "
        "fundo, común a todos sus módulos.",
    ),
    "riego": (
        "Riego aplicado",
        "Agua entregada por turno y día, con la lámina y el porcentaje de reposición.",
    ),
    "lotes": (
        "Maestro de lotes",
        "Área, número de plantas, variedad y turno de cada lote. De acá sale el área "
        "para el kg/ha, tomada una vez por lote.",
    ),
}


def panel_fuentes(estado: dict[str, object]) -> html.Div:
    """Con qué datos se hizo el análisis que se está viendo.

    Sale del snapshot de la corrida, no de una consulta al estado actual de la base. Esa
    diferencia importa: describe los datos que de verdad entraron en el cálculo, con su
    corte, y no lo que hay hoy en la base — que puede haber cambiado desde entonces.
    """
    fuentes = estado.get("fuentes")
    if fuentes is None or fuentes.empty:
        return ui.semaforo(
            "aviso",
            "Todavía no hay una corrida registrada de la que leer el origen de los datos.",
        )
    fila = fuentes.iloc[0]
    tablas = fila.tablas or {}
    if not isinstance(tablas, dict) or not tablas:
        return ui.semaforo("aviso", "La corrida no registró el detalle de sus fuentes.")

    conteos = {
        clave: cantidad
        for clave, cantidad in tablas.items()
        if isinstance(cantidad, Real) and not isinstance(cantidad, bool)
    }
    if not conteos:
        return ui.semaforo(
            "aviso",
            "La corrida registró archivos de respaldo, pero no reportó el conteo de registros "
            "por fuente.",
        )

    filas = []
    for clave, cantidad in sorted(conteos.items(), key=lambda x: -x[1]):
        nombre, descripcion = FUENTES.get(clave, (clave, "—"))
        filas.append(
            {"Fuente": nombre, "Qué contiene": descripcion, "Registros": ui.miles(cantidad)}
        )
    total = sum(conteos.values())

    corte = ""
    if pd.notna(fila.corte_datos):
        corte = f" con datos hasta el {pd.Timestamp(fila.corte_datos):%d/%m/%Y}"
    fallback = bool((fila.cobertura or {}).get("fallback", False))
    advertencias = list(fila.advertencias or [])

    hijos = [
        ui.semaforo(
            "aviso" if fallback else "ok",
            f"**El análisis se hizo con {ui.miles(total)} registros de "
            f"{len(tablas)} fuentes distintas**{corte}. "
            + (
                "Vienen del Excel de respaldo, no de la base, así que no pueden sostener una "
                "publicación oficial."
                if fallback
                else "Todas vienen de PostgreSQL, la base de producción."
            ),
        ),
        ui.tabla_desde_df(pd.DataFrame(filas), plano=True),
        ui.parrafo(
            f"Huella de estos datos: `{str(fila.firma)[:12]}`. Dos análisis con la misma "
            "huella partieron exactamente del mismo material, aunque se hayan ejecutado en "
            "días distintos. Es lo que permite reproducir un número meses después."
        ),
    ]
    control_access = estado.get("fuente_access_control")
    snapshot_visible = fila.get("source_snapshot_id")
    control_valido = isinstance(control_access, pd.DataFrame) and not control_access.empty
    if control_valido:
        control = control_access.iloc[0]
        control_snapshot = control.get("source_snapshot_id")
        try:
            control_valido = (
                pd.notna(snapshot_visible)
                and pd.notna(control_snapshot)
                and int(snapshot_visible) == int(control_snapshot)
            )
        except (TypeError, ValueError):
            control_valido = False
    if not control_valido:
        hijos.append(
            ui.semaforo(
                "aviso",
                "**Estado del snapshot Access: no verificable.** La corrida visible no está "
                "vinculada de forma segura con un snapshot físico Access.",
            )
        )
    else:
        completo = control.get("snapshot_completo")
        alcance = control.get("alcance")
        catalogo = control.get("tablas_catalogo")
        extraidas = control.get("tablas_extraidas")
        omitidas = control.get("tablas_omitidas")
        completo_conocido = pd.notna(completo)
        completo_valor = bool(completo) if completo_conocido else False
        detalle = []
        if pd.notna(catalogo) and pd.notna(extraidas):
            detalle.append(f"{int(extraidas)} de {int(catalogo)} tablas del catálogo")
        if pd.notna(omitidas) and int(omitidas) > 0:
            detalle.append(f"{int(omitidas)} omitidas")
        detalle_legible = f" ({', '.join(detalle)})" if detalle else ""
        if completo_valor and alcance == "completo":
            hijos.append(
                ui.semaforo(
                    "ok",
                    "**Snapshot Access completo**"
                    f"{detalle_legible}. El origen está listo para una carga completa.",
                )
            )
        elif (completo_conocido and not completo_valor) or alcance == "parcial":
            hijos.append(
                ui.semaforo(
                    "aviso",
                    "**Snapshot Access parcial**"
                    f"{detalle_legible}. No debe usarse para reemplazar todas las tablas de `raw`.",
                )
            )
        else:
            hijos.append(
                ui.semaforo(
                    "aviso",
                    "El manifiesto Access no permite confirmar si el snapshot está completo; "
                    "la carga completa debe detenerse hasta verificarlo.",
                )
            )
    if advertencias:
        hijos.append(
            ui.semaforo(
                "aviso",
                "**Avisos registrados al leer los datos:** " + "; ".join(map(str, advertencias)),
            )
        )
    return html.Div(hijos, className="space-y-3")


def _fila_campeon(estado: dict[str, object], banda: str = "operativo") -> pd.Series | None:
    """Métricas del modelo que hoy produce los números, en el plazo indicado."""
    decisiones, metricas = estado["decisiones"], estado["metricas"]
    if decisiones.empty or metricas.empty:
        return None
    fila = decisiones[decisiones.banda_horizonte == banda]
    if fila.empty:
        return None
    campeon = fila.iloc[0].campeon
    candidatas = metricas[(metricas.modelo == campeon) & (metricas.banda_horizonte == banda)]
    return candidatas.iloc[0] if not candidatas.empty else None


def indicador_precision(estado: dict[str, object], banda: str = "operativo") -> html.Div:
    """Qué tan fiable es hoy el pronóstico que se está mostrando.

    Las cuatro cifras responden preguntas distintas y hay que leerlas juntas: cuánto se
    equivoca, hacia qué lado, si el margen anunciado se cumple, y si todo eso vale más que
    la regla más simple. Un acierto alto con sesgo alto significa que el error se concentra
    en una dirección, y eso en packing cuesta más que un error simétrico del mismo tamaño.

    Se calcula sobre el plazo de compromiso porque es el que sostiene decisiones firmes; los
    plazos largos siempre salen peor y mezclarlos daría una cifra optimista de más.
    """
    fila = _fila_campeon(estado, banda)
    if fila is None:
        return ui.semaforo(
            "aviso",
            "Todavía no hay una medición de precisión: hace falta una comparación de "
            "modelos con cosecha real para poder calcularla.",
        )

    plazo = VALORES_ANALITICOS["banda_horizonte"].get(banda, banda)
    modelo = valor_legible("modelo", fila.modelo)
    wape = float(fila.wape) if pd.notna(fila.wape) else None
    sesgo = float(fila.sesgo_pct) if pd.notna(fila.sesgo_pct) else None
    # Algunas corridas antiguas no persistieron intervalos P10/P90. La página
    # debe seguir abriendo y mostrar el KPI como no disponible, no romper toda
    # la navegación por un atributo ausente.
    cobertura_valor = fila.get("cobertura_80")
    cobertura = float(cobertura_valor) if pd.notna(cobertura_valor) else None
    mase = float(fila.mase) if pd.notna(fila.mase) else None
    casos = int(fila.n) if pd.notna(fila.n) else 0

    acierto = f"{max(0.0, 100 * (1 - wape)):.1f} %".replace(".", ",") if wape is not None else "—"
    direccion = "de más" if (sesgo or 0) > 0 else "de menos"
    return html.Div(
        className="space-y-3",
        children=[
            ui.fila_kpi(
                [
                    ui.kpi(
                        "Acierto en volumen",
                        acierto,
                        f"Sobre {ui.miles(casos)} semanas ya cosechadas, en el plazo de "
                        "compromiso.",
                        ayuda="100 % menos el error de volumen: de cada 100 kg cosechados, "
                        "cuántos acertó el pronóstico.",
                    ),
                    ui.kpi(
                        "Se equivoca hacia",
                        _formatear("sesgo_pct", abs(sesgo)) if sesgo is not None else "—",
                        f"Promete {direccion} de lo que después llega.",
                        ayuda="Sesgo sistemático. Un error de este tamaño repetido siempre en "
                        "la misma dirección cuesta más que uno simétrico.",
                    ),
                    ui.kpi(
                        "Cumple su margen",
                        _formatear("cobertura_80", cobertura) if cobertura is not None else "—",
                        "De cada 100 semanas, en cuántas la cosecha cayó dentro del rango "
                        "anunciado. Debería rondar 80 %.",
                        ayuda="Si baja mucho de 80, el rango miente; si sube mucho, es tan "
                        "ancho que no informa.",
                    ),
                    ui.kpi(
                        "Frente al método simple",
                        _formatear("mase", mase) if mase is not None else "—",
                        "Por debajo de 1 aporta sobre repetir la semana anterior; en 1 o más, no.",
                        ayuda="Error del modelo dividido por el de repetir la semana anterior.",
                    ),
                ]
            ),
            ui.parrafo(
                f"Medido sobre **{modelo}**, el modelo que hoy produce los números, en el "
                f"plazo de **{plazo.lower()}**. Sale de pronosticar semanas del pasado sin "
                "dejarle ver lo que vino después, así que es lo más parecido a cómo se "
                "comportará la próxima vez."
            ),
        ],
    )


def tabla(
    df: pd.DataFrame,
    columnas: list[str],
    *,
    limite: int = 20,
    vacio: str = "Todavía no hay resultados guardados para esta sección.",
    como_leer: str | None = None,
    titulo_lectura: str = "Cómo se lee esta tabla",
) -> html.Div:
    """Tabla lista para mostrar: cabeceras, valores y números ya traducidos.

    Devuelve un aviso cuando no hay filas, en vez de una tabla de una sola celda que dice
    «Sin resultados persistidos» — esa forma anterior era indistinguible de un dato real.

    Cuando recorta filas lo dice explícitamente al pie: un `head()` silencioso hace creer
    que se está viendo todo.
    """
    if df is None or df.empty:
        return ui.semaforo("aviso", vacio)

    presentes = [c for c in columnas if c in df]
    if not presentes:
        return ui.semaforo("aviso", vacio)

    total = len(df)
    salida = df[presentes].head(limite).copy()
    for columna in presentes:
        salida[columna] = [_formatear(columna, valor_legible(columna, v)) for v in salida[columna]]
    salida.columns = [etiqueta(c) for c in presentes]

    hijos: list = [ui.tabla_desde_df(salida, plano=True)]
    if total > limite:
        hijos.append(
            html.P(
                f"Se muestran {limite} de {ui.miles(total)} filas. La descarga del paquete "
                "de auditoría contiene todas.",
                className="text-xs text-slate-400",
            )
        )
    if como_leer:
        hijos.append(ui.como_leer(como_leer, titulo_lectura))
    return html.Div(hijos, className="space-y-3")


def panel_glosario(claves: Iterable[str], titulo: str = "Qué significa cada término") -> html.Div:
    """Definiciones de los términos de la página, plegadas al pie.

    Se filtran las claves sin glosa antes de construirlo: `ui.glosario` las omite en
    silencio y un panel vacío es peor que ninguno.
    """
    con_glosa = [c for c in claves if glosa(c)]
    if not con_glosa:
        return html.Div()
    return ui.panel(
        titulo,
        ui.glosario(con_glosa, plano=True),
        plegable=True,
        abierto=False,
        ayuda="Definiciones en lenguaje llano de los términos que aparecen en esta página.",
    )
