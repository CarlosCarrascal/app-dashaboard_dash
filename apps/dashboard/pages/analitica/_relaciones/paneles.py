"""Los bloques visibles de la página, cada uno con su explicación de cómo se lee."""

from __future__ import annotations

import pandas as pd
from dash import dcc, html

from components import ui

from . import graficos
from .analisis import DESFASES_SOLIDO, SEMANAS_SOLIDO, Barrido
from .formato import (
    efecto_legible,
    en_minuscula,
    frase_efecto,
    nombre_objetivo,
    nombre_variable,
    numero,
)
from .textos import (
    BLOQUES_GRAFICO,
    ESTADOS_VARIABLE,
    FAMILIAS,
    INVENTARIO_VARIABLES,
    LECCIONES,
    MEDICION,
)

SIN_BARRIDO = (
    "Todavía no hay resultados del barrido de relaciones. Se generan con la corrida de "
    "relaciones sobre los censos de campo."
)


def _veredicto(*fragmentos) -> html.P:
    """La conclusión de un panel, en una línea y sin caja.

    Ni alerta ni párrafo. Una caja de color compite con el gráfico que tiene al lado, y un
    párrafo de cinco líneas repitiendo cifras que el gráfico ya muestra no lo lee nadie.
    """
    return html.P(list(fragmentos), className="px-1 text-[15px] leading-relaxed text-slate-700")


def _dato(valor: str) -> html.Strong:
    return html.Strong(valor, className="font-semibold text-slate-900")


def _entrada(titulo: str, cuerpo: str, marca: str = "", pie: str = "") -> html.Div:
    """Una entrada de lista: subtítulo, una frase y un pie opcional.

    Sin caja y sin párrafos. La página tenía cuatro estilos de tarjeta compitiendo, y al
    quitarlos quedaron bloques de texto corrido igual de difíciles de recorrer. Lo que se
    lee de un vistazo es una línea con jerarquía, no un párrafo bien escrito.
    """
    encabezado = [html.Span(titulo, className="text-sm font-semibold text-slate-900")]
    if marca:
        encabezado.insert(
            0,
            html.Span(
                marca,
                className="mr-2 font-mono text-xs font-semibold tabular-nums text-slate-400",
            ),
        )
    hijos = [html.Div(encabezado)]
    if cuerpo:
        hijos.append(dcc.Markdown(cuerpo, className="prose prose-sm max-w-none"))
    if pie:
        hijos.append(html.Div(pie, className="text-xs leading-relaxed text-slate-500"))
    return html.Div(hijos, className="space-y-1")


def _lista(entradas) -> html.Div:
    """Entradas separadas por una línea fina, no por cuatro cajas apiladas."""
    return html.Div(
        className="divide-y divide-stone-200/70 [&>*]:py-3 [&>*:first-child]:pt-0 "
        "[&>*:last-child]:pb-0",
        children=list(entradas),
    )


# ── Apertura ─────────────────────────────────────────────────────────────────


def kpis(hallazgos: pd.DataFrame, barrido: Barrido) -> html.Div:
    solidos = int((hallazgos.nivel == "solido").sum()) if not hallazgos.empty else 0
    hipotesis = int((hallazgos.nivel == "hipotesis").sum()) if not hallazgos.empty else 0
    # «Sólido» describe el respaldo de un par concreto, no la fiabilidad del conjunto. Si el
    # total de supervivientes apenas supera lo que saldría por azar, llamarlos sólidos
    # contradice el propio embudo de más abajo: el rótulo tiene que ceder ante el recuento.
    margen_estrecho = (
        barrido.hay_datos
        and barrido.esperados_por_azar
        and barrido.supervivientes / barrido.esperados_por_azar < 1.5
    )
    nota_solidos = (
        f"{SEMANAS_SOLIDO} semanas o más, en {DESFASES_SOLIDO} desfases contiguos. "
        "Aun así, el conjunto no se separa del azar: úsense como pistas."
        if margen_estrecho
        else f"{SEMANAS_SOLIDO} semanas o más, en {DESFASES_SOLIDO} desfases contiguos."
    )
    return ui.fila_kpi(
        [
            ui.kpi(
                "Cruces probados",
                ui.miles(barrido.pruebas) if barrido.hay_datos else "—",
                "Cada variable contra cada resultado, en nueve desfases.",
                ayuda="Una prueba es un trío de predictor, resultado y semanas de desfase.",
            ),
            ui.kpi(
                "Esperados por azar",
                str(barrido.esperados_por_azar) if barrido.hay_datos else "—",
                "Los que saldrían «significativos» aunque no hubiera nada.",
            ),
            ui.kpi(
                "Con más respaldo" if margen_estrecho else "Patrones sólidos",
                str(solidos) if solidos else "—",
                nota_solidos,
            ),
            ui.kpi(
                "Pistas por confirmar",
                str(hipotesis) if hipotesis else "—",
                "Pasan los filtros con muestra corta. Orientan qué medir.",
            ),
        ]
    )


def sintesis(hallazgos: pd.DataFrame) -> html.Div:
    """El hallazgo en una frase, y el enlace a donde vive la decisión.

    Esta página es la evidencia; lo que se puede afirmar y con qué alcance se publica en
    Descubrimientos. Repetirlo acá haría que las dos se contradijeran al primer cambio.
    """
    if hallazgos.empty:
        return ui.semaforo("aviso", SIN_BARRIDO)
    solidos = hallazgos[hallazgos.nivel == "solido"]
    if solidos.empty:
        return ui.semaforo(
            "aviso",
            "**Ningún cruce alcanza el nivel de sólido.** Todos los que pasan los filtros lo "
            "hacen con muestra corta o en un solo desfase.",
        )
    mejor = solidos.iloc[0]
    efecto = frase_efecto(mejor.to_dict())
    # Sin caja de color: es la entrada a la página, no una alerta. Una franja verde acá
    # compite con los KPI de arriba y con los semáforos que sí avisan de algo.
    return html.Div(
        className="space-y-2 px-1",
        children=[
            html.P(
                className="text-[15px] leading-relaxed text-slate-800",
                children=[
                    "La relación más fuerte medida es ",
                    html.Strong(
                        f"{nombre_variable(mejor.predictor)} → {nombre_objetivo(mejor.respuesta)}",
                        className="text-slate-900",
                    ),
                    f", con una correlación de {numero(abs(mejor.correlacion_parcial), 2)} "
                    f"sobre {int(mejor.n_efectivo)} semanas.",
                ],
            ),
            dcc.Markdown(efecto, className="prose prose-sm max-w-none text-slate-600")
            if efecto
            else html.Div(),
            html.P(
                className="text-sm text-slate-500",
                children=[
                    "Acá está la evidencia: qué se cruzó, qué sobrevivió y de qué tamaño es "
                    "cada efecto. Lo que se puede afirmar con ella se publica en ",
                    dcc.Link(
                        "Descubrimientos",
                        href="/analitica/descubrimientos",
                        className="font-medium text-teal-700 underline underline-offset-2",
                    ),
                    ".",
                ],
            ),
        ],
    )


# ── La matriz ────────────────────────────────────────────────────────────────


def panel_matriz(matriz: pd.DataFrame) -> html.Div:
    if matriz.empty:
        return ui.semaforo("aviso", SIN_BARRIDO)
    vivos = matriz[matriz.sobrevive] if "sobrevive" in matriz else pd.DataFrame()
    pares = (
        int(vivos[["predictor", "respuesta"]].drop_duplicates().shape[0])
        if not vivos.empty and {"predictor", "respuesta"} <= set(vivos.columns)
        else 0
    )
    return html.Div(
        className="space-y-3",
        children=[
            dcc.Graph(figure=graficos.mapa_matriz(matriz), config={"displayModeBar": False}),
            ui.como_leer(
                f"Este mapa muestra una celda por cada uno de los {pares} pares de variables "
                "que sobrevivieron; varios desfases del mismo par se consolidan en una sola "
                "celda. "
                "Cada fila es algo que se mide y cada columna algo que se quiere explicar. "
                "El color dice si van juntos: **verde, suben a la vez; naranja, cuando uno "
                "sube el otro baja.** Cuanto más intenso, más fuerte.\n\n"
                "**Las celdas en blanco son la parte importante.** No son huecos: son cruces "
                "que se probaron y no pasaron los filtros. Que un clima no aparezca contra "
                "el peso significa que se buscó y no había nada, no que falte el dato.\n\n"
                "De cada par se pinta solo el desfase de mayor efecto. Al pasar el ratón "
                "aparece cuál es y sobre cuántas semanas se midió.\n\n"
                "Todo está descontando el calendario y el módulo. Sin ese descuento casi "
                "todo saldría verde, porque clima y cosecha siguen la misma estación del "
                "año.\n\n"
                "**No todas las filas valen lo mismo, y la razón es cómo se mide cada una.** "
                "El calibre viene de la línea de packing, que pesa cada lote que entra a "
                "planta: por eso da 0,66 contra el peso, donde el censo de bayas de campo "
                "—dos fechas en total— daba 0,26. Cubre 15 de los 26 módulos y se pondera "
                "por kilos, no como promedio simple, que trataría igual una entrada de 3 t "
                "que una de 50 kg.\n\n"
                "El clima, en cambio, sale de **una sola estación para los cinco fundos**: "
                "todos los lotes de una semana comparten el mismo dato, así que lo que "
                "cuenta como muestra son las semanas y no los lotes. La columna «unidad de "
                "análisis» de la tabla de abajo lo declara par por par.",
                "Cómo se lee la matriz",
            ),
        ],
    )


def panel_desfases(matriz: pd.DataFrame) -> html.Div:
    if matriz.empty:
        return ui.semaforo("aviso", SIN_BARRIDO)
    return html.Div(
        className="space-y-3",
        children=[
            ui.parrafo(
                "Nada de lo que pasa en el campo se nota el mismo día. Este gráfico recorre "
                "las relaciones más fuertes moviendo el desfase semana a semana, para ver "
                "**cuándo** aparece cada una."
            ),
            dcc.Graph(figure=graficos.perfil_desfases(matriz), config={"displayModeBar": False}),
            ui.como_leer(
                "Cada línea es una relación; el eje horizontal, cuántas semanas se mira "
                "hacia atrás. Los puntos grandes son los desfases que pasaron todos los "
                "filtros.\n\n"
                "**Lo que hay que buscar es una curva con forma.** Una relación real sube, "
                "llega a un máximo y baja: hay un momento en que la señal manda y antes o "
                "después se diluye. Ese pico es la antelación con la que sirve.\n\n"
                "**Una línea que salta de arriba a abajo entre semanas contiguas es ruido**, "
                "por alto que llegue en su mejor punto. Que un mismo par sobreviva en varios "
                "desfases seguidos es lo que separa un patrón de una casualidad — y es "
                "exactamente el criterio que usa la clasificación de esta página.",
                "Cómo se lee el perfil de desfases",
            ),
        ],
    )


# ── Magnitudes ───────────────────────────────────────────────────────────────


def panel_efectos(hallazgos: pd.DataFrame) -> html.Div:
    solidos = hallazgos[hallazgos.nivel == "solido"] if not hallazgos.empty else pd.DataFrame()
    if solidos.empty:
        return ui.semaforo(
            "aviso",
            f"**Ningún patrón alcanza el nivel de sólido.** Hace falta que se sostenga sobre "
            f"al menos {SEMANAS_SOLIDO} semanas independientes y en {DESFASES_SOLIDO} o más "
            "desfases contiguos.",
        )
    bloques = [
        html.Div(
            className="space-y-1.5",
            children=[
                html.H4(titulo, className="text-sm font-semibold text-slate-900"),
                html.P(explicacion, className="text-sm leading-snug text-slate-500"),
                dcc.Graph(figure=figura, config={"displayModeBar": False}),
            ],
        )
        for titulo, explicacion, figura in graficos.efectos_por_unidad(solidos)
    ]
    return html.Div(
        className="space-y-5",
        children=[
            ui.parrafo(
                "Una correlación no dice si algo importa. Estos gráficos traducen cada "
                "relación a **kilos, gramos y puntos de descarte**, que es la única forma de "
                "saber si mueve la aguja."
            ),
            *bloques,
            ui.como_leer(
                "Cada barra responde una sola pregunta: si un lote pasa del cuarto más bajo "
                "al más alto en esa variable, ¿cuánto cambia el resultado?\n\n"
                "Se elige ese recorrido y no «una unidad más» porque una unidad puede ser un "
                "salto que nunca ocurre: nadie duplica el calibre de un módulo.\n\n"
                "Van separados por unidad —kilos, gramos, puntos de descarte— en vez de "
                "juntos en una escala común. Ponerlos en un mismo eje obligaría a "
                "normalizar, y eso haría que el descarte, cuyo valor habitual es 0,3 %, "
                "pareciera lo más importante de la finca por mover dos puntos.",
                "Cómo se leen estos gráficos",
            ),
        ],
    )


def _fila_tabla(fila: dict, motivo: bool = False) -> dict:
    efecto = fila.get("efecto_rango_iqr")
    cifra, unidad = (
        efecto_legible(fila["respuesta"], float(efecto))
        if efecto is not None and pd.notna(efecto)
        else ("—", "")
    )
    salida = {
        "Cuando sube": nombre_variable(fila["predictor"]),
        "Qué cambia": nombre_objetivo(fila["respuesta"]),
        "Hacia dónde": "sube" if fila["correlacion_parcial"] > 0 else "baja",
        "Cuánto": f"{cifra} {unidad}".strip(),
        "Correlación": numero(fila["correlacion_parcial"], 2),
    }
    if motivo:
        falta = []
        if fila["n_efectivo"] < SEMANAS_SOLIDO:
            falta.append(f"solo {int(fila['n_efectivo'])} semanas medidas")
        if fila["desfases_que_sobreviven"] < DESFASES_SOLIDO:
            plural = "s" if fila["desfases_que_sobreviven"] > 1 else ""
            falta.append(f"aparece en {int(fila['desfases_que_sobreviven'])} desfase{plural}")
        salida["Por qué no basta"] = " · ".join(falta) or "respaldo limitado"
        return salida
    salida["Cuándo se nota"] = (
        "misma semana"
        if fila["rezago_semanas"] == 0
        else f"{int(fila['rezago_semanas'])} semanas después"
    )
    salida["Unidad de análisis"] = fila["unidad_analisis"]
    salida["Semanas de respaldo"] = numero(fila["n_efectivo"], 0)
    return salida


def tabla_solidos(hallazgos: pd.DataFrame) -> html.Div:
    solidos = hallazgos[hallazgos.nivel == "solido"] if not hallazgos.empty else pd.DataFrame()
    if solidos.empty:
        return html.Div()
    filas = [_fila_tabla(f) for f in solidos.to_dict("records")]
    return ui.panel(
        "Todos los patrones sólidos, en detalle",
        html.P(
            f"{len(solidos)} relaciones con respaldo suficiente: al menos {SEMANAS_SOLIDO} "
            f"semanas independientes y presencia en {DESFASES_SOLIDO} o más desfases "
            "contiguos. Una relación que aparece y desaparece de una semana a otra no llega "
            "aquí.",
            className="text-sm leading-relaxed text-slate-500",
        ),
        ui.tabla_desde_df(pd.DataFrame(filas), plano=True),
        plegable=True,
        abierto=False,
        ayuda="Listado completo con efecto, desfase, unidad y muestra.",
    )


def tabla_hipotesis(hallazgos: pd.DataFrame) -> html.Div:
    hipotesis = hallazgos[hallazgos.nivel == "hipotesis"] if not hallazgos.empty else pd.DataFrame()
    if hipotesis.empty:
        return html.Div()
    filas = [_fila_tabla(f, motivo=True) for f in hipotesis.head(25).to_dict("records")]
    return ui.panel(
        "Pistas que aún no son conclusiones",
        html.P(
            f"{len(hipotesis)} relaciones pasan los filtros sin respaldo suficiente para "
            "sostener una decisión. Casi todas fallan por lo mismo —pocas semanas de "
            "muestra— y eso no se arregla con más análisis, sino midiendo más seguido: "
            "sirven para decidir qué medir mejor.",
            className="text-sm leading-relaxed text-slate-500",
        ),
        ui.tabla_desde_df(pd.DataFrame(filas), plano=True),
        plegable=True,
        abierto=False,
        ayuda="Relaciones con respaldo insuficiente para decidir sobre ellas.",
    )


# ── Filtrado ─────────────────────────────────────────────────────────────────


def panel_filtrado(barrido: Barrido) -> html.Div:
    if not barrido.hay_datos:
        return ui.semaforo("aviso", SIN_BARRIDO)
    if barrido.supervivientes == 0:
        veredicto = ui.semaforo(
            "aviso",
            f"Se probaron **{ui.miles(barrido.pruebas)} cruces** y **ninguna sobrevive** a "
            "los filtros. No es un fallo del análisis: **no encontrar nada es un resultado "
            "legítimo**, y significa que con esta medición no hay señal que sostenga una "
            "decisión.",
        )
    else:
        # Las cifras las dice el embudo. Repetirlas en prosa obliga a leer dos veces lo
        # mismo, así que acá solo va la comparación que el gráfico no puede hacer solo.
        azar = barrido.esperados_por_azar
        # La afirmación se modula con la distancia al azar, y no al revés. Sobrevivir a los
        # filtros no significa nada por sí solo: lo que informa es cuánto supera el
        # recuento a lo que saldría sin ninguna relación real. Con la inferencia anterior
        # —que contaba filas en vez de semanas— esa distancia era de 284 contra 74 y parecía
        # holgada; medida bien es de 109 contra 74, que es otra conversación.
        razon = barrido.supervivientes / azar if azar else float("inf")
        if razon >= 3:
            juicio = ", así que el conjunto no se explica por azar"
        elif razon >= 1.5:
            juicio = (
                f", así que hay señal, pero el margen es estrecho: apenas "
                f"{razon:.1f} veces lo que saldría de una base sin ninguna relación real"
            )
        else:
            juicio = (
                ", una diferencia demasiado corta para distinguirla del azar. Conviene "
                "tratar todo lo de esta página como exploratorio"
            )
        veredicto = _veredicto(
            "De ",
            _dato(f"{ui.miles(barrido.pruebas)} cruces probados"),
            " quedan ",
            _dato(ui.miles(barrido.supervivientes)),
            (
                f" (pruebas por desfase; corresponden a "
                f"{ui.miles(barrido.pares_supervivientes)} pares distintos)"
                if barrido.pares_supervivientes
                else " (pruebas por desfase)"
            ),
            ". Por puro azar se esperaba" + ("n unos " if azar != 1 else " "),
            _dato(str(azar)),
            juicio
            + f". Otros {ui.miles(barrido.placebo)} "
            + ("cayeron" if barrido.placebo != 1 else "cayó")
            + " en el placebo, porque lo que medían era el calendario.",
        )
    return html.Div(
        className="space-y-3",
        children=[
            veredicto,
            dcc.Graph(figure=graficos.embudo_filtrado(barrido), config={"displayModeBar": False}),
            ui.como_leer(
                "Cada barra es lo que queda tras aplicar un filtro más. La línea roja marca "
                "cuántos cruces saldrían «significativos» **aunque no existiera ninguna "
                "relación real**, solo por haber probado tantas veces.\n\n"
                "Los filtros, en orden:\n\n"
                "1. **Señal aparente** — el cruce da un coeficiente que no parece casualidad.\n"
                "2. **Placebo** — se compara contra una serie inventada que solo conoce la "
                "fecha. Si la explica igual de bien, lo medido era el calendario.\n"
                "3. **Corrección** — dos ajustes encadenados: uno por haberse quedado con el "
                "mejor de nueve desfases, y otro por el número total de pares evaluados.\n\n"
                "La comparación decisiva es la última barra contra la línea roja. Si fueran "
                "parecidas, no habría nada que celebrar.\n\n"
                "También cambia cuánto vale cada resultado. Una relación que el equipo "
                "agronómico había planteado de antemano **no es lo mismo** que una que "
                "aparece al cruzar cientos de combinaciones: la primera se puso a prueba, la "
                "segunda se encontró buscando. El paso siguiente para estas es **volver a "
                "comprobarlos** con datos de una campaña nueva.",
                "Cómo se lee el embudo",
            ),
        ],
    )


def panel_lecciones() -> html.Div:
    """Tres casos concretos que enseñan a no leer mal el resto de la página.

    Cada uno en tres renglones —el número, por qué engaña, qué hacer— porque el lector
    llega acá después de cinco gráficos y un párrafo más no lo va a leer.
    """
    return _lista(_entrada(titulo, porque, pie=hacer) for titulo, porque, hacer in LECCIONES)


# ── Aporte al modelo e inventario ────────────────────────────────────────────


def panel_importancia(estado) -> html.Div:
    """Qué necesita el modelo de pronóstico, que no es lo mismo que qué se relaciona."""
    permutacion = estado.get("permutacion", pd.DataFrame())
    if permutacion.empty:
        return ui.semaforo(
            "aviso",
            "Todavía no se ha ejecutado el análisis de importancia. Se genera con la corrida "
            "de entrenamiento, no con la de relaciones.",
        )
    vista = permutacion.copy()
    vista["nombre"] = vista.familia.map(lambda f: FAMILIAS.get(f, (f, ""))[0])
    vista = vista.sort_values("aumento_mae")
    vista["aporta"] = vista.ic_inferior > 0
    utiles = vista[vista.aporta]
    if not utiles.empty:
        ganadora = utiles.iloc[-1]
        # Una línea, sin caja: la composición del grupo y el veredicto de cada uno ya están
        # en la tabla de abajo, y el gráfico ya muestra cuáles cruzan el cero.
        veredicto = _veredicto(
            "Lo que sostiene el pronóstico es ",
            _dato(en_minuscula(ganadora.nombre)),
            ": sin ese grupo el error crece ",
            _dato(f"{ui.miles(ganadora.aumento_mae)} kg"),
            " por pronóstico. Los grupos en gris no muestran un aporte distinguible de cero.",
        )
    else:
        veredicto = ui.semaforo(
            "aviso",
            "**Ningún grupo de variables aporta de forma distinguible.** Todos los márgenes "
            "cruzan el cero, así que la respuesta honesta es que con estos datos no se sabe "
            "cuál sostiene el resultado.",
        )
    detalle = pd.DataFrame(
        [
            {
                "Grupo": fila.nombre,
                "De qué está hecho": en_minuscula(FAMILIAS.get(fila.familia, ("", ""))[1]),
                "Kilos de error que evita": ui.miles(fila.aumento_mae)
                if fila.aporta
                else "No distinguible de cero",
            }
            for fila in vista.iloc[::-1].itertuples(index=False)
        ]
    )
    return html.Div(
        className="space-y-3",
        children=[
            veredicto,
            dcc.Graph(figure=graficos.importancia(vista), config={"displayModeBar": False}),
            ui.tabla_desde_df(detalle, plano=True),
            ui.como_leer(
                "Esto responde una pregunta distinta a la de la matriz. Allí: qué se mueve "
                "junto a qué en el cultivo. Aquí: qué necesita el modelo para acertar.\n\n"
                "No dan lo mismo. Una variable puede relacionarse fuerte con la cosecha y no "
                "aportar nada al pronóstico, porque otra ya contaba esa misma historia.\n\n"
                "Se mide barajando los valores de un grupo entre semanas y viendo cuántos "
                "kilos de error se añaden. **Si el margen toca el cero, ese grupo no aporta "
                "de forma demostrable.**",
                "Por qué esto no es lo mismo que las relaciones",
            ),
        ],
    )


def panel_inventario() -> html.Div:
    conteo = dict.fromkeys(ESTADOS_VARIABLE, 0)
    for _, _, estado_var, _ in INVENTARIO_VARIABLES:
        conteo[estado_var] += 1
    filas = [
        {
            "Grupo": grupo,
            "Qué se mide": nombre,
            "Estado": ESTADOS_VARIABLE[estado_var],
            "Detalle": detalle,
        }
        for grupo, nombre, estado_var, detalle in INVENTARIO_VARIABLES
    ]
    # La categoría se nombra aunque esté vacía: es la que hace visible el próximo dato que
    # se levante en campo y nadie aproveche.
    sin_usar = (
        f"{conteo['sin_usar']} se registran en campo y todavía no se usan. "
        if conteo["sin_usar"]
        else "Ninguna se registra en campo sin usarse. "
    )
    return html.Div(
        className="space-y-3",
        children=[
            html.P(
                f"{conteo['modelo'] + conteo['relacion']} de {len(INVENTARIO_VARIABLES)} "
                f"cosas entran hoy al análisis. {sin_usar}{conteo['sin_dato']} no existen "
                "en ninguna tabla.",
                className="text-sm leading-relaxed text-slate-500",
            ),
            ui.como_leer(
                "Esta tabla existe para que una ausencia se pueda interpretar. Si una "
                "variable no aparece en la matriz, **puede ser que no importe, o puede ser "
                "que nunca se haya probado** — y sin este inventario las dos cosas se leen "
                "igual.\n\n"
                "Las que figuran como no registradas no son un descuido del análisis: "
                "sencillamente no existen en ninguna tabla de la base.",
                "Para qué sirve este inventario",
            ),
            ui.tabla_desde_df(pd.DataFrame(filas), plano=True),
        ],
    )


def panel_medicion() -> html.Div:
    """El cierre: qué cambiar en la forma de medir. Es una decisión de inversión.

    En tabla y no en cinco fichas: son cinco opciones que compiten por el mismo presupuesto,
    y compararlas es justamente lo que se viene a hacer acá.
    """
    tabla = pd.DataFrame(
        [
            {"#": str(i), "Qué hacer": titulo, "Cómo está hoy": hoy, "Qué desbloquea": beneficio}
            for i, (titulo, hoy, beneficio) in enumerate(MEDICION, start=1)
        ]
    )
    return html.Div(
        className="space-y-2",
        children=[
            html.P(
                "Ordenado por lo que desbloquea. Los límites de las secciones anteriores, "
                "leídos al derecho.",
                className="px-1 text-sm text-slate-500",
            ),
            ui.tabla_desde_df(tabla, plano=True),
        ],
    )


__all__ = [
    "BLOQUES_GRAFICO",
    "kpis",
    "panel_desfases",
    "panel_efectos",
    "panel_filtrado",
    "panel_importancia",
    "panel_inventario",
    "panel_lecciones",
    "panel_matriz",
    "panel_medicion",
    "sintesis",
    "tabla_hipotesis",
    "tabla_solidos",
]
