"""Proyección de cosecha: lo que un agrónomo necesita para programar la semana.

Es la primera página del grupo analítico con controles interactivos. Los callbacks usan
`dash` plano y no `dash_extensions.enrich` a propósito: esa variante existe para los
callbacks que mueven el panel Excel por `ServersideOutput`, y acá no hay nada de eso — los
datos vienen de `servicios.analytics`, que ya los cachea en el servidor por minuto.

Todo lo que se ve y todo lo que se descarga respeta los mismos filtros. Esa equivalencia es
la parte no negociable: un plan que no coincide con lo que se llevó a campo no sirve.
"""

from __future__ import annotations

import datetime as dt
import json

import dash
import dash_ag_grid as dag
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dcc, html
from dash.exceptions import PreventUpdate

from analitica.config import VALORES_ANALITICOS, etiqueta
from analitica.nucleo.exportar import Hoja, construir_libro
from analitica.proyeccion.fenologico_v1 import (
    EscenarioFenologico,
    aplicar_escenario_fenologico,
)
from components import ui
from pages.analitica._comun import (
    datos,
    estado_fuente,
    indicador_precision,
    numero,
    panel_glosario,
)
from servicios.analytics import enviar_escenario_revision, guardar_escenario_proyeccion

dash.register_page(
    __name__, path="/analitica/proyeccion", name="Proyección", order=5, grupo="Plataforma analítica"
)

ESCENARIOS = {
    "p10_kg": "Conservador",
    "p50_kg": "Esperado",
    "p90_kg": "Optimista",
}

# Los rótulos de KPI necesitan el adjetivo concordado con «kilos», no el nombre del
# escenario en singular: «Kilos conservadors» era el resultado de añadirle una s.
ESCENARIOS_PLURAL = {
    "p10_kg": "Kilos en escenario conservador",
    "p50_kg": "Kilos esperados",
    "p90_kg": "Kilos en escenario optimista",
}

# Columnas de la tabla operativa, en el orden en que se leen: dónde, cuándo, cuánto, y
# después el detalle que permite juzgar si el número tiene sentido.
COLUMNAS_TABLA = [
    "fundo",
    "modulo",
    "turno",
    "lote",
    "variedad",
    "semana_iso",
    "fecha_objetivo",
    "banda_horizonte",
    "p50_kg",
    "p10_kg",
    "p90_kg",
    "rango_relativo",
    "kg_ha",
    "kg_planta",
    "probabilidad_cosecha",
    "kg_condicional",
    "plantas",
    "frutos_por_planta",
    "peso_baya_g",
    "confianza",
]

# Un lote entra en la lista de menos firmes cuando su margen supera el volumen que se le
# espera: el pronóstico puede errar por más de lo que el lote entero va a dar.
#
# El umbral es 1,0 y no 0,5 porque los márgenes de esta emisión son anchos de por sí — la
# mediana medida el 2026-08-19 es 0,95, y con 0,5 el aviso señalaría el 81 % de los lotes y
# no distinguiría nada. Con 1,0 quedan los que de verdad no se pueden comprometer.
UMBRAL_RANGO_ANCHO = 1.0

# Por debajo de este volumen el ratio deja de tener sentido: un lote con 200 g previstos
# daría un «margen del 10.000 %» que solo refleja que el denominador es despreciable. Sin
# este piso la media del ratio llegaba a 4,8e20.
VOLUMEN_MINIMO_RATIO_KG = 1.0


def _componentes_dict(valor) -> dict:
    if isinstance(valor, dict):
        convertido = valor
    elif isinstance(valor, str):
        try:
            convertido = json.loads(valor)
            convertido = convertido if isinstance(convertido, dict) else {}
        except json.JSONDecodeError:
            return {}
    else:
        return {}
    # Compatibilidad con corridas creadas antes de aplanar el JSON de componentes.
    anidado = convertido.get("componentes")
    if isinstance(anidado, dict):
        return {**anidado, **{k: v for k, v in convertido.items() if k != "componentes"}}
    return convertido


def _seleccionar_proyeccion(estado: dict, fuente_modelo: str | None) -> pd.DataFrame:
    """Separa físicamente el plan oficial de la corrida experimental."""
    clave = "proyeccion_experimental" if fuente_modelo == "challenger" else "proyeccion"
    tabla = estado.get(clave, pd.DataFrame())
    return tabla.copy() if isinstance(tabla, pd.DataFrame) else pd.DataFrame()


# ── Preparación de datos ─────────────────────────────────────────────────────


def _enriquecer(proy: pd.DataFrame, lotes: pd.DataFrame) -> pd.DataFrame:
    """Añade atributos del lote y las unidades con que el agrónomo juzga un número.

    El área se toma **una vez por lote** desde el maestro. Sumarla desde esta tabla la
    contaría una vez por semana y el kg/ha saldría dividido por un área inflada: es el
    defecto B-4 que ADR-0004 obliga a resolver en la dimensión, no en el hecho.
    """
    if proy.empty:
        return proy
    tabla = proy.copy()
    # PostgreSQL entrega `date`, que pandas guarda como `object`: sin esta conversión el
    # `.dt` de más abajo falla y la página se queda en blanco. Se hace una sola vez, acá,
    # porque es el único punto por el que entran los datos a la página.
    for columna in ("fecha_objetivo", "fecha_emision"):
        if columna in tabla:
            tabla[columna] = pd.to_datetime(tabla[columna], errors="coerce")
    if "componentes" in tabla:
        metadatos = tabla.componentes.map(_componentes_dict)
        for columna in (
            "probabilidad_cosecha",
            "kg_condicional",
            "ocurrencia_gate",
            "factor_asignacion_cosecha",
        ):
            if columna not in tabla:
                tabla[columna] = metadatos.map(lambda valor, nombre=columna: valor.get(nombre))
    if lotes is not None and not lotes.empty:
        atributos = ["lote_id", "variedad", "turno", "area_ha", "n_plantas"]
        disponibles = [c for c in atributos if c in lotes]
        tabla = tabla.merge(lotes[disponibles].drop_duplicates("lote_id"), on="lote_id", how="left")
    for columna in ("variedad", "turno", "area_ha", "n_plantas"):
        if columna not in tabla:
            tabla[columna] = None

    # El negocio habla de «semana 34», no de «semana del 17/08»: así están numeradas las
    # proyecciones semanales que ya se emiten. Se muestran las dos, porque el número
    # identifica y la fecha ubica.
    tabla["semana_iso"] = tabla.fecha_objetivo.dt.isocalendar().week.astype("Int64")

    p50 = pd.to_numeric(tabla.p50_kg, errors="coerce")
    ancho = pd.to_numeric(tabla.p90_kg, errors="coerce") - pd.to_numeric(
        tabla.p10_kg, errors="coerce"
    )
    tabla["rango_relativo"] = (ancho / p50.where(p50 >= VOLUMEN_MINIMO_RATIO_KG)).replace(
        [float("inf"), float("-inf")], pd.NA
    )
    area = pd.to_numeric(tabla.area_ha, errors="coerce")
    plantas = pd.to_numeric(tabla.n_plantas, errors="coerce")
    tabla["kg_ha"] = p50 / area.where(area > 0)
    tabla["kg_planta"] = p50 / plantas.where(plantas > 0)
    return tabla


def _aplicar_simulacion(
    tabla: pd.DataFrame,
    *,
    fuente_modelo: str,
    plantas_pct: float = 0,
    cuajado_pct: float = 0,
    caida_frutos_pct: float = 0,
    riego_pct: float = 0,
    temp_delta_c: float = 0,
    dpv_delta_kpa: float = 0,
    poda_delta_dias: int = 0,
    desplazamiento_semanas: int = 0,
) -> tuple[pd.DataFrame, list[str]]:
    cambios = (
        plantas_pct,
        cuajado_pct,
        caida_frutos_pct,
        riego_pct,
        temp_delta_c,
        dpv_delta_kpa,
        poda_delta_dias,
        desplazamiento_semanas,
    )
    if tabla.empty or not any(float(valor or 0) != 0 for valor in cambios):
        return tabla, []
    if fuente_modelo != "challenger":
        return tabla, [
            "El plan oficial es de solo lectura. Selecciona el challenger para ejecutar escenarios."
        ]
    modelos = set(tabla.modelo.dropna()) if "modelo" in tabla else set()
    if "HibridoLegacyResidual_v1" in modelos:
        salida = tabla.copy()
        factor_plantas = 1 + float(plantas_pct or 0) / 100
        factor_frutos = (1 + float(cuajado_pct or 0) / 100) * (
            1 - float(caida_frutos_pct or 0) / 100
        )
        salida["plantas"] = pd.to_numeric(salida.plantas, errors="coerce") * factor_plantas
        salida["frutos_por_planta"] = (
            pd.to_numeric(salida.frutos_por_planta, errors="coerce") * factor_frutos
        )
        salida["p50_kg"] = (
            salida.plantas
            * salida.frutos_por_planta
            * pd.to_numeric(salida.peso_baya_g, errors="coerce")
            / 1000
        )
        for cuantiles in ("p10_kg", "p90_kg"):
            salida[cuantiles] = (
                pd.to_numeric(tabla[cuantiles], errors="coerce") * factor_plantas * factor_frutos
            )
        salida["componentes"] = (
            salida.componentes.map(
                lambda valor: {
                    **(_componentes_dict(valor)),
                    "escenario": {
                        "plantas_pct": float(plantas_pct or 0),
                        "carga_pct": float(cuajado_pct or 0),
                        "caida_frutos_pct": float(caida_frutos_pct or 0),
                        "etiqueta_causal": False,
                    },
                }
            )
            if "componentes" in salida
            else None
        )
        advertencias = []
        if any(
            float(valor or 0) != 0
            for valor in (
                riego_pct,
                temp_delta_c,
                dpv_delta_kpa,
                poda_delta_dias,
                desplazamiento_semanas,
            )
        ):
            advertencias.append(
                "El híbrido solo recalculó plantas y carga/frutos en este simulador; riego, "
                "clima, poda y calendario requieren reemitir el motor con un escenario "
                "versionado. No se tradujeron automáticamente a causalidad."
            )
        return salida, advertencias
    if not tabla.modelo.eq("FenologicoComponentes_v1").any():
        return tabla, [
            "La corrida challenger disponible no es FenologicoComponentes_v1 ni "
            "HibridoLegacyResidual_v1; no se ejecutó un escenario."
        ]
    return aplicar_escenario_fenologico(
        tabla,
        EscenarioFenologico(
            nombre="what_if_dashboard",
            plantas_pct=float(plantas_pct or 0),
            cuajado_pct=float(cuajado_pct or 0),
            caida_frutos_pct=float(caida_frutos_pct or 0),
            riego_pct=float(riego_pct or 0),
            temp_delta_c=float(temp_delta_c or 0),
            dpv_delta_kpa=float(dpv_delta_kpa or 0),
            poda_delta_dias=int(poda_delta_dias or 0),
            desplazamiento_semanas=int(desplazamiento_semanas or 0),
        ),
    )


def _tabla_interactiva(
    estado: dict,
    fuente_modelo: str = "oficial",
    ajuste_plantas: float = 0,
    ajuste_cuajado: float = 0,
    caida_frutos: float = 0,
    ajuste_riego: float = 0,
    clima_escenario: str = "base",
    ajuste_poda: int = 0,
    desplazamiento: int = 0,
    temp_delta: float = 0,
    dpv_delta: float = 0,
) -> tuple[pd.DataFrame, list[str]]:
    tabla = _enriquecer(_seleccionar_proyeccion(estado, fuente_modelo), estado.get("lotes"))
    clima_guiado = {
        "base": (0.0, 0.0),
        "fresco": (-1.0, -0.1),
        "calido": (1.0, 0.1),
    }.get(clima_escenario or "base", (0.0, 0.0))
    return _aplicar_simulacion(
        tabla,
        fuente_modelo=fuente_modelo or "oficial",
        plantas_pct=ajuste_plantas,
        cuajado_pct=ajuste_cuajado,
        caida_frutos_pct=caida_frutos,
        riego_pct=ajuste_riego,
        temp_delta_c=float(temp_delta or 0) + clima_guiado[0],
        dpv_delta_kpa=float(dpv_delta or 0) + clima_guiado[1],
        poda_delta_dias=ajuste_poda,
        desplazamiento_semanas=desplazamiento,
    )


def _filtrar(tabla, fundos, modulos, lotes, bandas, semanas) -> pd.DataFrame:
    """El mismo filtro para el gráfico, la tabla, los avisos y las descargas."""
    if tabla is None or tabla.empty:
        return pd.DataFrame()
    filtrada = tabla
    for columna, valores in (
        ("fundo", fundos),
        ("modulo", modulos),
        ("lote", lotes),
        ("banda_horizonte", bandas),
    ):
        if valores:
            filtrada = filtrada[filtrada[columna].isin(valores)]
    if semanas and len(semanas) == 2:
        fechas = sorted(pd.to_datetime(tabla.fecha_objetivo).dropna().unique())
        if fechas:
            inicio, fin = int(semanas[0]), int(semanas[1])
            permitidas = set(fechas[inicio : fin + 1])
            filtrada = filtrada[pd.to_datetime(filtrada.fecha_objetivo).isin(permitidas)]
    return filtrada


def _plan_semanal(filtrada: pd.DataFrame, escenario: str) -> pd.DataFrame:
    """Kilos por semana con su peso relativo y el acumulado: la unidad de planificación."""
    if filtrada.empty:
        return pd.DataFrame()
    plan = (
        filtrada.groupby("fecha_objetivo", as_index=False)[["p10_kg", "p50_kg", "p90_kg"]]
        .sum()
        .sort_values("fecha_objetivo")
    )
    total = plan[escenario].sum()
    plan["porcentaje"] = plan[escenario] / total if total else 0
    plan["acumulado"] = plan.porcentaje.cumsum()
    plan["ancho_relativo"] = (plan.p90_kg - plan.p10_kg) / plan.p50_kg.where(plan.p50_kg > 0)
    return plan


def _resumen_campania(filtrada: pd.DataFrame, escenario: str = "p50_kg") -> pd.DataFrame:
    """Inicio, pico, fin y volumen derivados de la misma suma reconciliada por lotes."""
    if filtrada.empty:
        return pd.DataFrame()
    semanal = (
        filtrada.groupby(["fundo", "modulo", "fecha_objetivo"], dropna=False, as_index=False)[
            ["p10_kg", "p50_kg", "p90_kg"]
        ]
        .sum()
        .sort_values("fecha_objetivo")
    )
    filas = []
    for (fundo, modulo), grupo in semanal.groupby(["fundo", "modulo"], dropna=False):
        positivas = grupo[grupo[escenario] > 0]
        if positivas.empty:
            continue
        pico = positivas.loc[positivas[escenario].idxmax()]
        filas.append(
            {
                "fundo": fundo,
                "modulo": modulo,
                "inicio_probable": positivas.fecha_objetivo.min(),
                "pico_probable": pico.fecha_objetivo,
                "fin_probable": positivas.fecha_objetivo.max(),
                "kg_campania": positivas[escenario].sum(),
                "kg_pico_semanal": pico[escenario],
                "p10_kg": positivas.p10_kg.sum(),
                "p90_kg": positivas.p90_kg.sum(),
            }
        )
    return pd.DataFrame(filas)


def _panel_campania(filtrada: pd.DataFrame, escenario: str) -> html.Div:
    resumen = _resumen_campania(filtrada, escenario)
    if resumen.empty:
        return ui.semaforo("aviso", "No hay volumen para construir el escenario de campaña.")
    vista = resumen.copy()
    for columna in ("inicio_probable", "pico_probable", "fin_probable"):
        vista[columna] = pd.to_datetime(vista[columna]).dt.strftime("%d/%m/%Y")
    for columna in ("kg_campania", "kg_pico_semanal", "p10_kg", "p90_kg"):
        vista[columna] = vista[columna].map(ui.miles)
    vista.columns = [etiqueta(c) for c in vista.columns]
    mensual = filtrada.copy()
    mensual["mes"] = pd.to_datetime(mensual.fecha_objetivo).dt.to_period("M").astype(str)
    mensual = mensual.groupby("mes", as_index=False)[["p10_kg", "p50_kg", "p90_kg"]].sum()
    figura = go.Figure(
        go.Bar(x=mensual.mes, y=mensual[escenario], marker_color="#0e7490")
    ).update_layout(
        template="plotly_white",
        height=320,
        margin={"l": 30, "r": 20, "t": 20, "b": 30},
        yaxis_title="kilos",
        xaxis_title="mes de cosecha",
    )
    return html.Div(
        [
            ui.semaforo(
                "info",
                "**Escenario de poda y campaña.** Inicio, pico y fin son resultados "
                "predictivos del calendario seleccionado; no son fechas garantizadas.",
            ),
            dcc.Graph(figure=figura, config={"displayModeBar": False}),
            ui.tabla_desde_df(vista, plano=True),
        ],
        className="space-y-4",
    )


def _panel_explicacion(filtrada: pd.DataFrame, evidencia: pd.DataFrame) -> html.Div:
    if filtrada.empty:
        return html.Div()
    fila = filtrada.iloc[0]
    componentes = _componentes_dict(fila.get("componentes"))
    modelos = componentes.get("modelos_componentes", {})
    features = componentes.get("features", {})
    piezas = pd.DataFrame(
        [
            {
                "Pieza": "Ocurrencia",
                "Valor": fila.get("probabilidad_cosecha"),
                "Modelo": modelos.get("ocurrencia"),
            },
            {"Pieza": "Plantas", "Valor": fila.get("plantas"), "Modelo": "maestro de lotes"},
            {
                "Pieza": "Frutos/planta",
                "Valor": fila.get("frutos_por_planta"),
                "Modelo": modelos.get("frutos"),
            },
            {
                "Pieza": "Peso de baya (g)",
                "Valor": fila.get("peso_baya_g"),
                "Modelo": modelos.get("peso"),
            },
            {
                "Pieza": "Kg si ocurre cosecha",
                "Valor": fila.get("kg_condicional"),
                "Modelo": "identidad biológica",
            },
            {
                "Pieza": "Factor de calibración de volumen",
                "Valor": fila.get("factor_asignacion_cosecha"),
                "Modelo": modelos.get("volumen_directo", "reconciliación as-of"),
            },
            {
                "Pieza": "Kg esperados",
                "Valor": fila.get("p50_kg"),
                "Modelo": modelos.get("volumen_directo", "volumen directo as-of"),
            },
        ]
    )
    piezas["Valor"] = pd.to_numeric(piezas.Valor, errors="coerce").map(
        lambda valor: "—" if pd.isna(valor) else numero(valor, 2)
    )
    evid = evidencia.copy() if isinstance(evidencia, pd.DataFrame) else pd.DataFrame()
    if not evid.empty and "modelo" in evid:
        evid = evid[evid.modelo.eq(str(fila.get("modelo")))]
    if not evid.empty:
        evid = evid[evid.admitida.fillna(False)].head(30)
        columnas = [
            c
            for c in (
                "objetivo",
                "predictor",
                "hipotesis",
                "referencias",
                "claim_id",
                "metodo",
                "n_efectivo",
                "estimacion",
                "q_value",
                "limitacion",
            )
            if c in evid
        ]
        tabla_evidencia = ui.tabla_desde_df(evid[columnas], plano=True)
    else:
        declaradas = [
            {"Componente": pieza, "Variables usadas": ", ".join(valores)}
            for pieza, valores in features.items()
        ]
        tabla_evidencia = (
            ui.tabla_desde_df(pd.DataFrame(declaradas), plano=True)
            if declaradas
            else ui.parrafo("Esta corrida no tiene evidencia por feature persistida.")
        )
    return html.Div(
        [
            ui.semaforo(
                "info",
                "**Descomposición:** ocurrencia, plantas, frutos/planta y peso se estiman por "
                "separado; el volumen central se entrena sobre kg reales anteriores al corte y "
                "se reconcilia con un factor visible. "
                "Las relaciones, SHAP y sensibilidades explican asociaciones predictivas; "
                "no prueban causalidad agronómica.",
            ),
            ui.tabla_desde_df(piezas, plano=True),
            tabla_evidencia,
        ],
        className="space-y-3",
    )


def _estado_operativo_fuentes(estado: dict) -> html.Div:
    access = estado.get("fuente_access", pd.DataFrame())
    fuentes = estado.get("fuentes", pd.DataFrame())
    if isinstance(access, pd.DataFrame) and not access.empty:
        partes = []
        for fila in access.sort_values("campania").itertuples(index=False):
            version = getattr(fila, "version_maxima_r09", None)
            version = "sin versión" if pd.isna(version) else version
            campania = getattr(fila, "campania", None)
            campania = "campaña no declarada" if pd.isna(campania) else campania
            partes.append(
                f"{campania}: {fila.nombre_archivo} · R09 hasta {version} · "
                f"extraído {pd.to_datetime(fila.extraido_en):%d/%m/%Y %H:%M} · "
                f"SHA-256 {str(fila.sha256)[:12]}…"
            )
        access_texto = "; ".join(partes)
    else:
        access_texto = "Snapshot físico Access aún no registrado en raw.source_snapshot."
    cobertura = ""
    if isinstance(fuentes, pd.DataFrame) and not fuentes.empty:
        tablas = fuentes.iloc[0].get("tablas") or {}
        if isinstance(tablas, dict):
            nombres = ("cosecha", "poda", "flores", "estados", "bayas", "clima", "riego")
            cobertura = " · ".join(f"{n}: {ui.miles(tablas.get(n, 0))}" for n in nombres)
    return html.Details(
        className="aq-source-details group",
        children=[
            html.Summary(
                [
                    ui.icono("datos-calidad", "h-4 w-4"),
                    html.Span("Origen y cobertura de datos"),
                    html.Span("Access → PostgreSQL", className="aq-source-badge"),
                    ui.icono("chevron-down", "ml-auto h-4 w-4"),
                ]
            ),
            dcc.Markdown(
                f"**Fuente operativa:** {access_texto}\n\n"
                f"**Cobertura del snapshot analítico:** "
                f"{cobertura or 'sin detalle disponible'}.\n\n"
                "Los Excel semanales no sustituyen esta fuente; una versión provisional "
                "debe quedar identificada como backfill antes de aparecer aquí.",
                className="prose prose-sm max-w-none",
            ),
        ],
    )


# ── Layout ───────────────────────────────────────────────────────────────────


def _controles_legacy() -> html.Div:
    return html.Div(
        className="aq-data-filters grid gap-4 md:grid-cols-2",
        children=[
            html.Div(
                className="md:col-span-2",
                children=[
                    html.Label("Qué proyección revisar", className=ui.SUBTITULO),
                    dcc.RadioItems(
                        id="proy-fuente-modelo",
                        options=[
                            {
                                "label": " Oficial vigente (R09 mientras no sea superado)",
                                "value": "oficial",
                            },
                            {
                                "label": " Challenger Híbrido Legacy–ML",
                                "value": "challenger",
                            },
                        ],
                        value="oficial",
                        inline=True,
                        className="mt-1 flex flex-wrap gap-5 text-sm text-slate-600",
                        persistence=True,
                        persistence_type="session",
                    ),
                ],
            ),
            html.Div(
                [
                    html.Label("Fundo", className=ui.SUBTITULO),
                    dcc.Dropdown(
                        id="proy-fundo",
                        multi=True,
                        placeholder="Todos",
                        persistence=True,
                        persistence_type="session",
                    ),
                ]
            ),
            html.Div(
                [
                    html.Label("Módulo", className=ui.SUBTITULO),
                    dcc.Dropdown(
                        id="proy-modulo",
                        multi=True,
                        placeholder="Todos",
                        persistence=True,
                        persistence_type="session",
                    ),
                ]
            ),
            html.Div(
                [
                    html.Label("Lote", className=ui.SUBTITULO),
                    dcc.Dropdown(
                        id="proy-lote",
                        multi=True,
                        placeholder="Todos",
                        persistence=True,
                        persistence_type="session",
                    ),
                ]
            ),
            html.Div(
                [
                    html.Label("Para qué se va a usar", className=ui.SUBTITULO),
                    dcc.Dropdown(
                        id="proy-banda",
                        multi=True,
                        placeholder="Todos los plazos",
                        persistence=True,
                        persistence_type="session",
                    ),
                ]
            ),
            html.Div(
                className="md:col-span-2",
                children=[
                    html.Label("Semanas de cosecha", className=ui.SUBTITULO),
                    dcc.RangeSlider(
                        id="proy-semanas", step=1, allowCross=False, tooltip={"placement": "bottom"}
                    ),
                ],
            ),
            html.Div(
                className="md:col-span-2",
                children=[
                    html.Label("Escenario con el que planificar", className=ui.SUBTITULO),
                    dcc.RadioItems(
                        id="proy-escenario",
                        options=[
                            {"label": f" {nombre}", "value": clave}
                            for clave, nombre in ESCENARIOS.items()
                        ],
                        value="p50_kg",
                        inline=True,
                        className="mt-1 flex flex-wrap gap-4 text-sm text-slate-600",
                        persistence=True,
                        persistence_type="session",
                    ),
                ],
            ),
            html.Details(
                className="md:col-span-2 rounded-xl border border-stone-200 bg-stone-50 p-4",
                open=True,
                children=[
                    html.Summary(
                        "Simulador guiado del challenger",
                        className="cursor-pointer font-semibold",
                    ),
                    html.Div(
                        className="mt-4 grid gap-5 md:grid-cols-3",
                        children=[
                            html.Div(
                                [
                                    html.Label("Plantas productivas (%)", className=ui.SUBTITULO),
                                    dcc.Slider(
                                        id="proy-ajuste-plantas",
                                        min=-20,
                                        max=20,
                                        step=2,
                                        value=0,
                                        marks={-20: "-20", 0: "0", 20: "+20"},
                                    ),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Label("Cuajado o carga (%)", className=ui.SUBTITULO),
                                    dcc.Slider(
                                        id="proy-ajuste-cuajado",
                                        min=-40,
                                        max=40,
                                        step=5,
                                        value=0,
                                        marks={-40: "-40", 0: "0", 40: "+40"},
                                    ),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        "Caída futura de frutos (%)", className=ui.SUBTITULO
                                    ),
                                    dcc.Slider(
                                        id="proy-caida-frutos",
                                        min=0,
                                        max=50,
                                        step=5,
                                        value=0,
                                        marks={0: "0", 25: "25", 50: "50"},
                                    ),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Label("Riego planificado (%)", className=ui.SUBTITULO),
                                    dcc.Slider(
                                        id="proy-ajuste-riego",
                                        min=-30,
                                        max=30,
                                        step=5,
                                        value=0,
                                        marks={-30: "-30", 0: "base", 30: "+30"},
                                    ),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Label("Escenario climático", className=ui.SUBTITULO),
                                    dcc.Dropdown(
                                        id="proy-clima-escenario",
                                        options=[
                                            {"label": "Base explícito", "value": "base"},
                                            {"label": "Más fresco / menor DPV", "value": "fresco"},
                                            {"label": "Más cálido / mayor DPV", "value": "calido"},
                                        ],
                                        value="base",
                                        clearable=False,
                                    ),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        "Mover fecha de poda (días)", className=ui.SUBTITULO
                                    ),
                                    dcc.Slider(
                                        id="proy-ajuste-poda",
                                        min=-28,
                                        max=28,
                                        step=7,
                                        value=0,
                                        marks={-28: "-28", 0: "0", 28: "+28"},
                                    ),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        "Mover calendario de pañas (semanas)",
                                        className=ui.SUBTITULO,
                                    ),
                                    dcc.Slider(
                                        id="proy-desplazamiento",
                                        min=-3,
                                        max=3,
                                        step=1,
                                        value=0,
                                        marks={-3: "-3", 0: "0", 3: "+3"},
                                    ),
                                ]
                            ),
                        ],
                    ),
                    ui.parrafo(
                        "Estos controles vuelven a ejecutar las sensibilidades locales guardadas "
                        "por el challenger. Cuajado, riego y clima solo cambian una fila cuando "
                        "esa variable fue usada por sus componentes; nunca se presentan "
                        "como causas.",
                    ),
                ],
            ),
            html.Details(
                className="md:col-span-2 rounded-xl border border-stone-200 bg-white p-4",
                children=[
                    html.Summary(
                        "Modo experto y referencia legacy",
                        className="cursor-pointer font-semibold",
                    ),
                    html.Div(
                        className="mt-4 grid gap-4 md:grid-cols-2",
                        children=[
                            html.Div(
                                [
                                    html.Label(
                                        "Temperatura futura: cambio °C", className=ui.SUBTITULO
                                    ),
                                    dcc.Input(
                                        id="proy-temp-delta",
                                        type="number",
                                        value=0,
                                        step=0.5,
                                        className="w-full rounded-md border p-2",
                                    ),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Label("DPV futuro: cambio kPa", className=ui.SUBTITULO),
                                    dcc.Input(
                                        id="proy-dpv-delta",
                                        type="number",
                                        value=0,
                                        step=0.1,
                                        className="w-full rounded-md border p-2",
                                    ),
                                ]
                            ),
                        ],
                    ),
                    ui.parrafo(
                        "Los parámetros X/O/N/A/B de la macro se conservan únicamente como "
                        "referencia legacy. La corrección híbrida solo recalcula los componentes "
                        "admitidos y deja cualquier efecto climático como pendiente de reemisión.",
                    ),
                ],
            ),
            html.Div(id="proy-simulador-aviso", className="md:col-span-2"),
            html.Div(
                className="md:col-span-2 grid gap-3 md:grid-cols-[1fr_auto_auto]",
                children=[
                    dcc.Input(
                        id="proy-nombre-escenario",
                        type="text",
                        placeholder="Nombre del escenario",
                        className="rounded-md border border-stone-300 p-2",
                    ),
                    html.Button(
                        "Guardar simulación",
                        id="proy-guardar-escenario",
                        className="rounded-md bg-slate-900 px-4 py-2 text-sm text-white",
                    ),
                    html.Button(
                        "Enviar a revisión",
                        id="proy-enviar-revision",
                        className="rounded-md border border-slate-400 px-4 py-2 text-sm",
                    ),
                    dcc.Store(id="proy-scenario-id", storage_type="session"),
                    html.Div(id="proy-gobierno-aviso", className="md:col-span-3"),
                ],
            ),
        ],
    )


def _filtros_operativos() -> html.Div:
    return html.Div(
        className="aq-data-filters aq-filter-grid",
        children=[
            html.Div(
                className="aq-filter-wide",
                children=[
                    html.Label("Ver el detalle de", className=ui.SUBTITULO),
                    dcc.RadioItems(
                        id="proy-fuente-modelo",
                        options=[
                            {"label": " R09 · plan vigente", "value": "oficial"},
                            {
                                "label": " Nuevo · Fenológico por componentes",
                                "value": "challenger",
                            },
                        ],
                        value="oficial",
                        inline=True,
                        className="aq-model-switch",
                        persistence=True,
                        persistence_type="session",
                    ),
                ],
            ),
            html.Div(
                [
                    html.Label("Fundo", className=ui.SUBTITULO),
                    dcc.Dropdown(
                        id="proy-fundo",
                        multi=True,
                        placeholder="Todos",
                        persistence=True,
                        persistence_type="session",
                    ),
                ]
            ),
            html.Div(
                [
                    html.Label("Módulo", className=ui.SUBTITULO),
                    dcc.Dropdown(
                        id="proy-modulo",
                        multi=True,
                        placeholder="Todos",
                        persistence=True,
                        persistence_type="session",
                    ),
                ]
            ),
            html.Div(
                [
                    html.Label("Lote", className=ui.SUBTITULO),
                    dcc.Dropdown(
                        id="proy-lote",
                        multi=True,
                        placeholder="Todos",
                        persistence=True,
                        persistence_type="session",
                    ),
                ]
            ),
            html.Div(
                [
                    html.Label("Uso", className=ui.SUBTITULO),
                    dcc.Dropdown(
                        id="proy-banda",
                        multi=True,
                        placeholder="Todos los plazos",
                        persistence=True,
                        persistence_type="session",
                    ),
                ]
            ),
            html.Div(
                className="aq-filter-wide",
                children=[
                    html.Label("Ventana de planificación", className=ui.SUBTITULO),
                    dcc.RangeSlider(
                        id="proy-semanas",
                        step=1,
                        allowCross=False,
                        tooltip={"placement": "bottom"},
                    ),
                ],
            ),
            html.Div(
                className="aq-filter-wide",
                children=[
                    html.Label("Nivel de seguridad", className=ui.SUBTITULO),
                    dcc.RadioItems(
                        id="proy-escenario",
                        options=[
                            {"label": f" {nombre}", "value": clave}
                            for clave, nombre in ESCENARIOS.items()
                        ],
                        value="p50_kg",
                        inline=True,
                        className="aq-confidence-switch",
                        persistence=True,
                        persistence_type="session",
                    ),
                ],
            ),
        ],
    )


def _slider_escenario(
    nombre: str,
    control_id: str,
    minimo: int,
    maximo: int,
    paso: int,
    valor: int,
    marcas: dict,
) -> html.Div:
    return html.Div(
        className="aq-scenario-control",
        children=[
            html.Label(nombre, className=ui.SUBTITULO),
            dcc.Slider(
                id=control_id,
                min=minimo,
                max=maximo,
                step=paso,
                value=valor,
                marks=marcas,
                tooltip={"placement": "bottom"},
            ),
        ],
    )


def _simulador() -> html.Div:
    return html.Div(
        className="space-y-4 aq-data-filters",
        children=[
            html.P(
                "Solo modifica el challenger. Si una variable no fue admitida por el "
                "modelo, el tablero no inventa un efecto.",
                className="text-sm leading-relaxed text-slate-500",
            ),
            _slider_escenario(
                "Plantas productivas (%)",
                "proy-ajuste-plantas",
                -20,
                20,
                2,
                0,
                {-20: "-20", 0: "0", 20: "+20"},
            ),
            _slider_escenario(
                "Cuajado o carga (%)",
                "proy-ajuste-cuajado",
                -40,
                40,
                5,
                0,
                {-40: "-40", 0: "0", 40: "+40"},
            ),
            _slider_escenario(
                "Caída futura de frutos (%)",
                "proy-caida-frutos",
                0,
                50,
                5,
                0,
                {0: "0", 25: "25", 50: "50"},
            ),
            _slider_escenario(
                "Riego planificado (%)",
                "proy-ajuste-riego",
                -30,
                30,
                5,
                0,
                {-30: "-30", 0: "base", 30: "+30"},
            ),
            html.Div(
                [
                    html.Label("Clima futuro", className=ui.SUBTITULO),
                    dcc.Dropdown(
                        id="proy-clima-escenario",
                        options=[
                            {"label": "Base explícito", "value": "base"},
                            {"label": "Más fresco / menor DPV", "value": "fresco"},
                            {"label": "Más cálido / mayor DPV", "value": "calido"},
                        ],
                        value="base",
                        clearable=False,
                    ),
                ]
            ),
            _slider_escenario(
                "Mover fecha de poda (días)",
                "proy-ajuste-poda",
                -28,
                28,
                7,
                0,
                {-28: "-28", 0: "0", 28: "+28"},
            ),
            _slider_escenario(
                "Mover calendario de pañas (semanas)",
                "proy-desplazamiento",
                -3,
                3,
                1,
                0,
                {-3: "-3", 0: "0", 3: "+3"},
            ),
            html.Details(
                className="aq-expert-controls",
                children=[
                    html.Summary("Ajuste experto"),
                    html.Div(
                        [
                            html.Label("Temperatura (Δ °C)"),
                            dcc.Input(id="proy-temp-delta", type="number", value=0, step=0.5),
                            html.Label("DPV (Δ kPa)"),
                            dcc.Input(id="proy-dpv-delta", type="number", value=0, step=0.1),
                        ],
                        className="aq-expert-grid",
                    ),
                    html.P(
                        "X/O/N/A/B pertenecen a la macro legacy y no gobiernan el modelo nuevo.",
                        className="mt-3 text-xs text-slate-500",
                    ),
                ],
            ),
            html.Div(id="proy-simulador-aviso"),
        ],
    )


def _acciones_plan() -> html.Div:
    return html.Div(
        className="space-y-3",
        children=[
            dcc.Input(
                id="proy-nombre-escenario",
                type="text",
                placeholder="Nombre del escenario",
                className="aq-text-input",
            ),
            html.Div(
                [
                    html.Button(
                        "Guardar borrador",
                        id="proy-guardar-escenario",
                        className="aq-btn aq-btn-primary",
                    ),
                    html.Button(
                        "Enviar a revisión",
                        id="proy-enviar-revision",
                        className="aq-btn aq-btn-secondary",
                    ),
                ],
                className="aq-action-grid",
            ),
            dcc.Store(id="proy-scenario-id", storage_type="session"),
            html.Div(id="proy-gobierno-aviso"),
            html.Div(
                [
                    html.Button(
                        "Descargar Excel", id="proy-btn-excel", className="aq-btn aq-btn-primary"
                    ),
                    html.Button("CSV", id="proy-btn-csv", className="aq-btn aq-btn-ghost"),
                ],
                className="aq-action-grid",
            ),
            dcc.Download(id="proy-descarga-excel"),
            dcc.Download(id="proy-descarga-csv"),
        ],
    )


def _metrica_operativa(metricas: pd.DataFrame, modelo: str) -> pd.Series | None:
    if not isinstance(metricas, pd.DataFrame) or metricas.empty:
        return None
    filas = metricas[metricas.modelo.eq(modelo)]
    if filas.empty:
        return None
    operativa = filas[filas.banda_horizonte.eq("operativo")]
    return (operativa if not operativa.empty else filas).iloc[0]


def _texto_metrica(fila: pd.Series | None, nombre: str, porcentaje: bool = False) -> str:
    """Presenta una métrica sin convertir un dato ausente en una falsa precisión."""
    if fila is None or nombre not in fila or pd.isna(fila.get(nombre)):
        return "Pendiente"
    valor = float(fila[nombre])
    return f"{100 * valor:.1f} %" if porcentaje else f"{valor:.3f}"


def _figura_replay(replay: pd.DataFrame, fecha_emision: pd.Timestamp) -> go.Figure:
    """Curva de una emisión histórica: predicciones congeladas contra el real posterior."""
    figura = go.Figure()
    tramo = replay[replay.fecha_emision.eq(fecha_emision)].copy()
    if tramo.empty:
        return figura.update_layout(template="plotly_white", height=330)
    real = (
        tramo.groupby("fecha_objetivo", as_index=False, sort=True)
        .real_kg.first()
        .sort_values("fecha_objetivo")
    )
    figura.add_trace(
        go.Scatter(
            x=real.fecha_objetivo,
            y=real.real_kg,
            name="Real posterior",
            mode="lines+markers",
            line={"color": "#111827", "width": 3},
        )
    )
    colores = {
        "R09_publicado": "#64748b",
        "MacroLegacy_v1": "#b45309",
        "HibridoLegacyResidual_v1": "#18735b",
        "FenologicoComponentes_v1": "#2563eb",
    }
    nombres = {
        "R09_publicado": "R09 publicado",
        "MacroLegacy_v1": "Macro legacy",
        "HibridoLegacyResidual_v1": "Híbrido Legacy–ML",
        "FenologicoComponentes_v1": "Fenológico v1",
    }
    for modelo in (
        "R09_publicado",
        "MacroLegacy_v1",
        "HibridoLegacyResidual_v1",
        "FenologicoComponentes_v1",
    ):
        serie = tramo[tramo.modelo.eq(modelo)].sort_values("fecha_objetivo")
        if serie.empty:
            continue
        figura.add_trace(
            go.Scatter(
                x=serie.fecha_objetivo,
                y=serie.p50_kg,
                name=nombres[modelo],
                mode="lines+markers",
                line={"color": colores[modelo], "width": 2.5},
            )
        )
    figura.update_layout(
        template="plotly_white",
        height=350,
        margin={"l": 35, "r": 15, "t": 30, "b": 35},
        yaxis_title="kg por semana",
        xaxis_title=None,
        legend={"orientation": "h", "y": 1.12, "x": 0},
        hovermode="x unified",
    )
    return figura


def _figura_curva_historica(curva: pd.DataFrame) -> go.Figure:
    """Curva completa: real observado y predicciones vintage por semana."""

    figura = go.Figure()
    if not isinstance(curva, pd.DataFrame) or curva.empty:
        return figura.update_layout(template="plotly_white", height=380)
    tabla = curva.copy()
    tabla["fecha_objetivo"] = pd.to_datetime(tabla.fecha_objetivo, errors="coerce")
    colores = {
        "Real cosechado": "#111827",
        "R09_publicado": "#64748b",
        "MacroLegacy_v1": "#b45309",
        "HibridoLegacyResidual_v1": "#18735b",
        "FenologicoComponentes_v1": "#2563eb",
    }
    nombres = {
        "Real cosechado": "Real cosechado",
        "R09_publicado": "R09 histórico",
        "MacroLegacy_v1": "Macro legacy histórica",
        "HibridoLegacyResidual_v1": "Híbrido Legacy–ML histórico",
        "FenologicoComponentes_v1": "Fenológico v1 histórico",
    }
    for modelo in (
        "Real cosechado",
        "R09_publicado",
        "MacroLegacy_v1",
        "HibridoLegacyResidual_v1",
        "FenologicoComponentes_v1",
    ):
        serie = tabla[tabla.modelo.eq(modelo)].sort_values("fecha_objetivo")
        if serie.empty:
            continue
        figura.add_trace(
            go.Scatter(
                x=serie.fecha_objetivo,
                y=serie.p50_kg,
                name=nombres[modelo],
                mode="lines+markers",
                line={"color": colores[modelo], "width": 3 if modelo == "Real cosechado" else 2.5},
                customdata=serie[["origen_emision_min", "origen_emision_max"]].to_numpy()
                if {"origen_emision_min", "origen_emision_max"} <= set(serie)
                else None,
                hovertemplate=(
                    "%{x|%d/%m/%Y}<br>kg: %{y:,.0f}"
                    "<br>Emisión más antigua: %{customdata[0]|%d/%m/%Y}"
                    "<br>Emisión más reciente: %{customdata[1]|%d/%m/%Y}<extra></extra>"
                    if modelo != "Real cosechado"
                    else "%{x|%d/%m/%Y}<br>kg reales: %{y:,.0f}<extra></extra>"
                ),
            )
        )
    figura.update_layout(
        template="plotly_white",
        height=410,
        margin={"l": 45, "r": 20, "t": 35, "b": 45},
        yaxis_title="kg por semana",
        xaxis_title=None,
        legend={"orientation": "h", "y": 1.12, "x": 0},
        hovermode="x unified",
    )
    return figura


def _panel_replay(estado: dict) -> html.Div:
    """Hace visible la prueba que permite afirmar si el nuevo modelo mejora al vigente."""
    replay = estado.get("replay", pd.DataFrame())
    if not isinstance(replay, pd.DataFrame) or replay.empty:
        return ui.semaforo(
            "aviso",
            "Todavía no existe un replay histórico terminado para esta versión. "
            "La proyección futura puede consultarse, pero no debe presentarse como una "
            "mejora hasta comparar predicciones congeladas contra cosecha real posterior.",
        )
    replay = replay.copy()
    replay["fecha_emision"] = pd.to_datetime(replay.fecha_emision, errors="coerce")
    replay["fecha_objetivo"] = pd.to_datetime(replay.fecha_objetivo, errors="coerce")
    metricas = estado.get("metricas_comparacion", pd.DataFrame())
    modelo_nuevo = "HibridoLegacyResidual_v1"
    if (
        not isinstance(metricas, pd.DataFrame)
        or metricas.empty
        or metricas[metricas.modelo.eq(modelo_nuevo)].empty
    ):
        modelo_nuevo = "FenologicoComponentes_v1"
    etiqueta_nuevo = (
        "Híbrido Legacy–ML"
        if modelo_nuevo == "HibridoLegacyResidual_v1"
        else "Fenológico por componentes"
    )
    emisiones = []
    for fecha in sorted(replay.fecha_emision.dropna().unique()):
        modelos = set(replay.loc[replay.fecha_emision.eq(fecha), "modelo"])
        if {"R09_publicado", modelo_nuevo} <= modelos:
            emisiones.append(pd.Timestamp(fecha))
    if not emisiones:
        return ui.semaforo(
            "aviso",
            "El replay tiene observaciones, pero todavía no comparte una emisión entre R09 "
            f"y {etiqueta_nuevo}. No se muestra un ranking con universos distintos.",
        )
    fecha_emision = emisiones[-1]
    meta = estado.get("replay_meta", pd.DataFrame())
    meta_row = meta.iloc[0] if isinstance(meta, pd.DataFrame) and not meta.empty else None
    run_id = int(replay.run_id.iloc[0]) if "run_id" in replay else None
    r09 = _metrica_operativa(metricas, "R09_publicado")
    nuevo = _metrica_operativa(metricas, modelo_nuevo)
    replay_versiones = set()
    if "version_fuente" in replay:
        replay_versiones = set(
            replay.loc[replay.modelo.eq(modelo_nuevo), "version_fuente"].dropna().astype(str)
        )
    plan_actual = _seleccionar_proyeccion(estado, "challenger")
    version_actual = (
        str(plan_actual.version_fuente.dropna().iloc[0])
        if not plan_actual.empty
        and "version_fuente" in plan_actual
        and not plan_actual.version_fuente.dropna().empty
        else None
    )
    misma_version = not version_actual or not replay_versiones or version_actual in replay_versiones
    wape_r09 = float(r09.wape) if r09 is not None and pd.notna(r09.get("wape")) else None
    wape_nuevo = float(nuevo.wape) if nuevo is not None and pd.notna(nuevo.get("wape")) else None
    mase_r09 = float(r09.mase) if r09 is not None and pd.notna(r09.get("mase")) else None
    mase_nuevo = float(nuevo.mase) if nuevo is not None and pd.notna(nuevo.get("mase")) else None
    mejora_historica = (
        wape_r09 is not None
        and wape_nuevo is not None
        and mase_r09 is not None
        and mase_nuevo is not None
        and wape_nuevo < wape_r09
        and mase_nuevo < mase_r09
    )
    mejora = mejora_historica and misma_version
    tabla = (
        replay[replay.fecha_emision.eq(fecha_emision)]
        .pivot_table(index="fecha_objetivo", columns="modelo", values="p50_kg", aggfunc="sum")
        .reset_index()
    )
    if not tabla.empty:
        reales = (
            replay[replay.fecha_emision.eq(fecha_emision)]
            .groupby("fecha_objetivo", as_index=False)
            .real_kg.first()
        )
        tabla = tabla.merge(reales, on="fecha_objetivo", how="left")
        tabla = tabla.rename(
            columns={
                "fecha_objetivo": "Semana objetivo",
                "real_kg": "Real posterior (kg)",
                "R09_publicado": "R09 publicado (kg)",
                "HibridoLegacyResidual_v1": "Híbrido Legacy–ML (kg)",
                "FenologicoComponentes_v1": "Fenológico v1 (kg)",
            }
        )
        tabla["Semana objetivo"] = pd.to_datetime(tabla["Semana objetivo"]).dt.strftime("%d/%m/%Y")
        for columna in tabla.columns[1:]:
            tabla[columna] = pd.to_numeric(tabla[columna], errors="coerce").map(
                lambda valor: "—" if pd.isna(valor) else ui.miles(valor)
            )
        tabla = tabla.head(12)
    estado_replay = (
        f"Replay n.º {run_id} · emisión evaluada {fecha_emision:%d/%m/%Y} · "
        f"{len(emisiones)} emisiones comunes"
    )
    if replay_versiones:
        estado_replay += f" · versión {', '.join(sorted(replay_versiones))}"
    if meta_row is not None and pd.notna(meta_row.get("snapshot_id")):
        estado_replay += f" · snapshot {int(meta_row['snapshot_id'])}"
    plan_run = (
        int(pd.to_numeric(plan_actual.run_id, errors="coerce").max())
        if not plan_actual.empty and "run_id" in plan_actual
        else None
    )
    nota_version = (
        f"El replay es de {', '.join(sorted(replay_versiones))}, pero el plan actual es "
        f"{version_actual}; sus métricas no se transfieren automáticamente a la corrida actual."
        if not misma_version and version_actual
        else (
            "El plan actual y este replay son corridas distintas; el replay valida el algoritmo "
            "con datos históricos, no reemplaza la validación del snapshot actual."
            if plan_run is not None and run_id is not None and plan_run != run_id
            else (
                "Cada predicción del replay se emitió antes de conocer la cosecha real "
                "de su semana objetivo."
            )
        )
    )
    veredicto = (
        f"En este replay {etiqueta_nuevo} mejora simultáneamente WAPE y "
        "MASE frente al resultado R09. "
        "Eso es evidencia comparativa, no causalidad ni autorización automática "
        "de publicación."
        if mejora_historica and misma_version
        else (
            "El replay histórico mejora ambos indicadores, pero corresponde a una "
            "versión anterior; "
            "todavía no demuestra que la versión actual sea mejor."
            if mejora_historica and not misma_version
            else (
                "Este replay no demuestra una mejora simultánea en WAPE y MASE; "
                "el plan R09 sigue siendo la referencia operativa."
            )
        )
    )
    tarjetas = html.Div(
        className="aq-replay-cards",
        children=[
            html.Div(
                [
                    html.Span("R09 · RESULTADO PUBLICADO", className="aq-replay-label"),
                    html.Div(_texto_metrica(r09, "wape", True), className="aq-replay-value"),
                    html.Small(
                        f"MASE {_texto_metrica(r09, 'mase')} · sesgo "
                        f"{_texto_metrica(r09, 'sesgo_pct', False)} %"
                    ),
                ],
                className="aq-replay-card",
            ),
            html.Div(
                [
                    html.Span(
                        f"{etiqueta_nuevo.upper()} · NUEVO MODELO"
                        if misma_version
                        else f"{etiqueta_nuevo.upper()} · VERSIÓN ANTERIOR",
                        className="aq-replay-label aq-replay-label-new",
                    ),
                    html.Div(_texto_metrica(nuevo, "wape", True), className="aq-replay-value"),
                    html.Small(
                        f"MASE {_texto_metrica(nuevo, 'mase')} · sesgo "
                        f"{_texto_metrica(nuevo, 'sesgo_pct', False)} %"
                    ),
                ],
                className="aq-replay-card aq-replay-card-new",
            ),
            html.Div(
                [
                    html.Span("LECTURA DEL REPLAY", className="aq-replay-label"),
                    html.Div(
                        "Mejor en ambos"
                        if mejora
                        else (
                            "Mejor versión anterior"
                            if mejora_historica
                            else "Sin mejora comprobada"
                        ),
                        className="aq-replay-value aq-replay-verdict",
                    ),
                    html.Small(f"{ui.miles(len(replay))} agregados lote-semana con real"),
                ],
                className="aq-replay-card aq-replay-card-result",
            ),
        ],
    )
    return html.Div(
        className="aq-replay-panel",
        children=[
            html.Div(estado_replay, className="aq-replay-meta"),
            html.P(
                "Aquí sí se mide precisión: se congela cada emisión histórica, se ocultan sus "
                "semanas posteriores y después se compara contra lo que realmente ocurrió.",
                className="aq-replay-intro",
            ),
            tarjetas,
            dcc.Graph(
                figure=(
                    _figura_curva_historica(estado.get("curva_historica", pd.DataFrame()))
                    if isinstance(estado.get("curva_historica"), pd.DataFrame)
                    and not estado.get("curva_historica").empty
                    else _figura_replay(replay, fecha_emision)
                ),
                config={"displayModeBar": False},
            ),
            ui.tabla_desde_df(tabla, plano=True) if not tabla.empty else html.Div(),
            html.P(f"{veredicto} {nota_version}", className="aq-replay-note"),
        ],
    )


def _comparacion_modelos(
    estado: dict,
    fundos,
    modulos,
    lotes,
    bandas,
    fechas_objetivo,
) -> html.Div:
    oficial = _enriquecer(_seleccionar_proyeccion(estado, "oficial"), estado.get("lotes"))
    challenger = _seleccionar_proyeccion(estado, "challenger")
    modelo_nuevo = "HibridoLegacyResidual_v1"
    if (
        challenger.empty
        or "modelo" not in challenger
        or not challenger.modelo.eq(modelo_nuevo).any()
    ):
        modelo_nuevo = "FenologicoComponentes_v1"
    etiqueta_nuevo = (
        "Híbrido Legacy–ML"
        if modelo_nuevo == "HibridoLegacyResidual_v1"
        else "Fenológico por componentes"
    )
    nuevo = _enriquecer(challenger[challenger.modelo.eq(modelo_nuevo)], estado.get("lotes"))
    if nuevo.empty:
        return html.Div(
            className="aq-compare-empty",
            children=[
                html.Div("Nuevo modelo pendiente de emisión", className="aq-compare-empty-title"),
                html.P(
                    "El motor ya existe, pero hace falta una corrida project exitosa para "
                    "compararlo en el dashboard con R09."
                ),
                html.Code(
                    "npm run analytics:project -- --source postgres "
                    "--modelo-proyeccion HibridoLegacyResidual_v1 --horizonte-semanas 10"
                ),
            ],
        )

    def preparar(tabla: pd.DataFrame) -> pd.DataFrame:
        filtrada = _filtrar(tabla, fundos, modulos, lotes, bandas, None)
        if fechas_objetivo:
            fechas = pd.Series(pd.to_datetime(fechas_objetivo))
            semanas = fechas - pd.to_timedelta(fechas.dt.weekday, unit="D")
            fecha_tabla = pd.to_datetime(filtrada.fecha_objetivo)
            semana_tabla = fecha_tabla - pd.to_timedelta(fecha_tabla.dt.weekday, unit="D")
            filtrada = filtrada[semana_tabla.isin(set(semanas))]
        return filtrada

    oficial = preparar(oficial)
    nuevo = preparar(nuevo)
    # La comparación visual debe empezar por lo que realmente ocurrió. Las dos emisiones
    # actuales pueden tener fechas de corte distintas, por lo que se usa el corte más
    # temprano para no dibujar observaciones que el forecast antiguo no podía conocer.
    real = estado.get("cosecha_real", pd.DataFrame())
    if not isinstance(real, pd.DataFrame):
        real = pd.DataFrame()
    if not real.empty:
        real = real.copy()
        real["fecha_objetivo"] = pd.to_datetime(real.fecha_objetivo, errors="coerce")
        for columna, valores in (
            ("fundo", fundos),
            ("modulo", modulos),
            ("lote", lotes),
        ):
            if valores and columna in real:
                real = real[real[columna].isin(valores)]
        campanias = set(oficial.campania.dropna().astype(str)) & set(
            nuevo.campania.dropna().astype(str)
        )
        if campanias and "campania" in real:
            real = real[real.campania.astype(str).isin(campanias)]
        emisiones = pd.concat(
            [oficial[["fecha_emision"]], nuevo[["fecha_emision"]]], ignore_index=True
        )
        corte_comun = pd.to_datetime(emisiones.fecha_emision, errors="coerce").min()
        real = real[real.fecha_objetivo.lt(corte_comun)]
    for tabla in (oficial, nuevo):
        fecha = pd.to_datetime(tabla.fecha_objetivo)
        tabla["semana_operativa"] = fecha - pd.to_timedelta(fecha.dt.weekday, unit="D")
    semanas_comunes = set(oficial.semana_operativa.dropna()).intersection(
        set(nuevo.semana_operativa.dropna())
    )
    oficial = oficial[oficial.semana_operativa.isin(semanas_comunes)]
    nuevo = nuevo[nuevo.semana_operativa.isin(semanas_comunes)]
    claves = ["lote_id", "semana_operativa"]
    pares = oficial[claves + ["p50_kg"]].merge(
        nuevo[claves + ["p50_kg"]],
        on=claves,
        how="inner",
        suffixes=("_r09", "_nuevo"),
    )
    if pares.empty:
        return ui.semaforo(
            "aviso",
            "Las dos emisiones no comparten lote-semana en el alcance seleccionado. "
            "No se calcula una brecha con universos distintos.",
        )

    total_r09 = float(pares.p50_kg_r09.sum())
    total_nuevo = float(pares.p50_kg_nuevo.sum())
    diferencia = total_nuevo - total_r09
    diferencia_pct = diferencia / total_r09 if total_r09 else float("nan")
    volumen_r09_comun = float(pd.to_numeric(oficial.p50_kg, errors="coerce").sum())
    cobertura = total_r09 / volumen_r09_comun if volumen_r09_comun else 0.0
    metricas = estado.get("metricas_comparacion", pd.DataFrame())
    # Las métricas solo adornan el plan si el replay corresponde a la misma versión del
    # challenger. Un replay de `rejilla_independiente_asof` no certifica una emisión
    # `direct_volume_v2`, aunque ambas se llamen FenologicoComponentes_v1.
    replay = estado.get("replay", pd.DataFrame())
    version_actual = (
        str(nuevo.version_fuente.dropna().iloc[0])
        if "version_fuente" in nuevo and not nuevo.version_fuente.dropna().empty
        else None
    )
    versiones_replay = set()
    if isinstance(replay, pd.DataFrame) and not replay.empty and "version_fuente" in replay:
        versiones_replay = set(
            replay.loc[replay.modelo.eq(modelo_nuevo), "version_fuente"].dropna().astype(str)
        )
    if version_actual and versiones_replay and version_actual not in versiones_replay:
        metricas = pd.DataFrame()
    metrica_r09 = _metrica_operativa(metricas, "R09_publicado")
    metrica_nuevo = _metrica_operativa(metricas, modelo_nuevo)
    emision_r09 = pd.to_datetime(oficial.fecha_emision, errors="coerce").max()
    emision_nuevo = pd.to_datetime(nuevo.fecha_emision, errors="coerce").max()

    serie_r09 = oficial.groupby("semana_operativa", as_index=False).p50_kg.sum()
    serie_nuevo = nuevo.groupby("semana_operativa", as_index=False).p50_kg.sum()
    figura = go.Figure()
    if not real.empty:
        serie_real = real.groupby("fecha_objetivo", as_index=False).real_kg.sum()
        figura.add_trace(
            go.Scatter(
                x=serie_real.fecha_objetivo,
                y=serie_real.real_kg,
                name="Real cosechado",
                mode="lines+markers",
                line={"color": "#111827", "width": 3},
            )
        )
    figura.add_trace(
        go.Scatter(
            x=serie_r09.semana_operativa,
            y=serie_r09.p50_kg,
            name="R09 publicado",
            mode="lines+markers",
            line={"color": "#64748b", "width": 2},
        )
    )
    figura.add_trace(
        go.Scatter(
            x=serie_nuevo.semana_operativa,
            y=serie_nuevo.p50_kg,
            name=etiqueta_nuevo,
            mode="lines+markers",
            line={"color": "#18735b", "width": 3},
        )
    )
    figura.update_layout(
        template="plotly_white",
        height=390,
        margin={"l": 20, "r": 10, "t": 12, "b": 20},
        yaxis_title="kg",
        legend={"orientation": "h", "y": 1.13, "x": 0},
        hovermode="x unified",
    )
    curva_historica = estado.get("curva_historica", pd.DataFrame())
    usa_curva_historica = isinstance(curva_historica, pd.DataFrame) and not curva_historica.empty
    if usa_curva_historica:
        figura = _figura_curva_historica(curva_historica)
    if not real.empty and not usa_curva_historica:
        corte_grafica = pd.to_datetime(real.fecha_objetivo).max()
        figura.add_vline(
            x=corte_grafica,
            line_dash="dot",
            line_color="#94a3b8",
            annotation_text="Última semana real disponible",
            annotation_position="top left",
        )

    def valor_metrica(fila: pd.Series | None, nombre: str, porcentaje: bool = False) -> str:
        if fila is None or nombre not in fila or pd.isna(fila.get(nombre)):
            return "Pendiente"
        valor = float(fila[nombre])
        return f"{100 * valor:.1f} %" if porcentaje else f"{valor:.3f}"

    def valor_sesgo(fila: pd.Series | None) -> str:
        if fila is None or pd.isna(fila.get("sesgo_pct")):
            return "Pendiente"
        return f"{float(fila['sesgo_pct']):+.1f} %"

    decisiones = estado.get("decisiones", pd.DataFrame())
    promovido = (
        isinstance(decisiones, pd.DataFrame)
        and not decisiones.empty
        and decisiones.campeon.eq(modelo_nuevo).any()
    )
    veredicto = (
        "Promovido: el modelo nuevo superó los controles."
        if promovido
        else "Challenger: comparar en campo; el forecast operativo R09 continúa vigente."
    )
    muestra_componentes = {}
    if "componentes" in nuevo and not nuevo.componentes.dropna().empty:
        muestra_componentes = _componentes_dict(nuevo.componentes.dropna().iloc[0])
    modelos_componentes = muestra_componentes.get(
        "modelos_componentes",
        {"modelo_base": "MacroLegacy_v1", "modelo_correccion": "Ridge con splines"},
    )
    bloques_features = muestra_componentes.get("features", {})
    n_features = len(
        {
            feature
            for bloque in bloques_features.values()
            if isinstance(bloque, list)
            for feature in bloque
        }
    )
    version_fuente = (
        str(nuevo.version_fuente.dropna().iloc[0])
        if "version_fuente" in nuevo and not nuevo.version_fuente.dropna().empty
        else "versión no informada"
    )
    return html.Div(
        className="aq-compare-body",
        children=[
            html.Div(
                className="aq-compare-cards",
                children=[
                    html.Div(
                        [
                            html.Span("PLAN VIGENTE", className="aq-model-tag aq-model-tag-old"),
                            html.H3("Forecast operativo R09", className="aq-model-name"),
                            html.Div(f"{ui.miles(total_r09)} kg", className="aq-model-total"),
                            html.P(
                                f"WAPE 1–2 sem: {valor_metrica(metrica_r09, 'wape', True)} · "
                                f"sesgo: {valor_sesgo(metrica_r09)}"
                            ),
                            html.Small(
                                f"MASE {valor_metrica(metrica_r09, 'mase')} · replay pareado"
                            ),
                            html.Small(
                                f"Emisión: {emision_r09:%d/%m/%Y}"
                                if pd.notna(emision_r09)
                                else "Emisión pendiente",
                                className="text-slate-500",
                            ),
                        ],
                        className="aq-model-card aq-model-card-old",
                    ),
                    html.Div(
                        [
                            html.Span("PLAN CHALLENGER", className="aq-model-tag aq-model-tag-new"),
                            html.H3(etiqueta_nuevo, className="aq-model-name"),
                            html.Div(f"{ui.miles(total_nuevo)} kg", className="aq-model-total"),
                            html.P(
                                f"WAPE 1–2 sem: "
                                f"{valor_metrica(metrica_nuevo, 'wape', True)} · "
                                f"sesgo: {valor_sesgo(metrica_nuevo)}"
                            ),
                            html.Small(
                                f"MASE {valor_metrica(metrica_nuevo, 'mase')} · replay pareado"
                            ),
                            html.Small(
                                f"Emisión: {emision_nuevo:%d/%m/%Y}"
                                if pd.notna(emision_nuevo)
                                else "Emisión pendiente",
                                className="text-slate-500",
                            ),
                        ],
                        className="aq-model-card aq-model-card-new",
                    ),
                    html.Div(
                        [
                            html.Span("BRECHA ENTRE PLANES", className="aq-model-tag"),
                            html.H3(
                                ("+" if diferencia >= 0 else "") + f"{ui.miles(diferencia)} kg",
                                className="aq-model-total",
                            ),
                            html.Div(
                                "—" if pd.isna(diferencia_pct) else f"{diferencia_pct:+.1%}",
                                className="aq-compare-delta",
                            ),
                            html.P(
                                f"{len(semanas_comunes)} semanas comunes · cubre "
                                f"{cobertura:.0%} del volumen del plan vigente. No es una métrica "
                                f"de precisión. {veredicto}"
                            ),
                        ],
                        className="aq-model-card aq-model-card-delta",
                    ),
                ],
            ),
            dcc.Graph(figure=figura, config={"displayModeBar": False}),
            html.P(
                (
                    "La gráfica principal es un replay histórico stitched: negro es la cosecha "
                    "real completa; azul y verde son las predicciones vintage, elegidas con una "
                    "emisión anterior a cada semana objetivo. Cada punto conserva su origen."
                    if usa_curva_historica
                    else (
                        "La línea negra muestra los kg realmente cosechados hasta el corte. "
                        "Desde ahí continúan las dos proyecciones. La precisión solo se "
                        "interpreta con el replay temporal a una misma fecha, contra cosecha "
                        "real posterior."
                    )
                ),
                className="aq-compare-note",
            ),
            html.Div(
                [
                    html.Span("QUÉ MODELO SE ESTÁ USANDO", className="aq-method-label"),
                    html.P(
                        f"{modelo_nuevo} · {version_fuente}. "
                        f"Base: {modelos_componentes.get('modelo_base', 'no informado')}; "
                        "corrección: "
                        f"{modelos_componentes.get('modelo_correccion', 'no informado')}. "
                        f"La identidad conserva frutos/planta × peso de baya × plantas. "
                        f"Usa {n_features or 'las'} variables candidatas construidas as-of.",
                    ),
                    html.Small(
                        "La curva legacy aporta las tres oleadas y el crecimiento de peso; "
                        "Relaciones y Descubrimientos solo aportan variables y rezagos candidatos "
                        "dentro de los folds. La corrección Ridge es asociativa, no causal; R09 "
                        "no entra como predictor."
                    ),
                ],
                className="aq-model-method",
            ),
        ],
    )


def layout():
    estado = datos()
    return html.Div(
        className="aq-projection-workspace",
        children=[
            html.Header(
                className="aq-projection-hero",
                children=[
                    html.Div(
                        [
                            html.Span("OPERACIÓN DIARIA", className="aq-hero-eyebrow"),
                            html.H1("Mesa de cosecha", className="aq-hero-title"),
                            html.P(
                                "Compara la cosecha real con R09 y el modelo híbrido, detecta "
                                "semanas críticas y baja el detalle que irá a campo.",
                                className="aq-hero-copy",
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.Span("PLAN R09", className="aq-status-dot aq-status-official"),
                            html.Span("OFICIAL", className="aq-status-label"),
                            html.Span("Híbrido Legacy–ML", className="aq-status-dot aq-status-new"),
                            html.Span("CHALLENGER", className="aq-status-label"),
                        ],
                        className="aq-hero-status",
                    ),
                ],
            ),
            ui.panel(
                "Plan vigente R09 frente al nuevo modelo",
                html.Div(id="proy-comparacion", children=ui.esqueleto_seccion("h-48")),
                ayuda=(
                    "R09 es el resultado operativo publicado por el proceso vigente, no un "
                    "algoritmo comparable por nombre. El challenger sí es un modelo nuevo."
                ),
            ),
            ui.panel(
                "¿Cuál predice mejor? Replay histórico ciego",
                html.Div(id="proy-replay", children=ui.esqueleto_seccion("h-64")),
                ayuda=(
                    "La emisión se congela antes de la cosecha y luego se compara con el real. "
                    "Esta es la prueba que sustenta una promoción."
                ),
            ),
            estado_fuente(estado),
            html.Div(id="proy-aviso-emision"),
            html.Div(
                className="aq-projection-grid",
                children=[
                    html.Main(
                        className="aq-projection-main",
                        children=[
                            ui.panel(
                                "Alcance del plan",
                                _filtros_operativos(),
                                ayuda="Filtros compartidos por gráficos, tablas y descargas.",
                            ),
                            html.P(
                                "Vistas disponibles: Plan semanal · Detalle por lote · "
                                "Poda y campaña · Explicación. Modelo nuevo: Híbrido "
                                "Legacy–ML con corrección residual.",
                                className="sr-only",
                            ),
                            dcc.Tabs(
                                id="proy-modo",
                                value="plan_semanal",
                                persistence=True,
                                persistence_type="session",
                                className="aq-work-tabs",
                                children=[
                                    dcc.Tab(
                                        label="Plan semanal",
                                        value="plan_semanal",
                                        children=html.Div(
                                            className="space-y-4 pt-4",
                                            children=[
                                                html.Div(id="proy-kpis"),
                                                ui.panel(
                                                    "Curva semanal de cosecha",
                                                    dcc.Graph(
                                                        id="proy-curva",
                                                        config={"displayModeBar": False},
                                                    ),
                                                    html.Div(id="proy-plan-semanal"),
                                                    ayuda="Volumen y margen P10–P90.",
                                                ),
                                                ui.panel(
                                                    "Atención esta semana",
                                                    html.Div(id="proy-riesgo"),
                                                    ayuda=(
                                                        "Lotes con margen ancho o datos "
                                                        "incompletos."
                                                    ),
                                                ),
                                            ],
                                        ),
                                    ),
                                    dcc.Tab(
                                        label="Detalle por lote",
                                        value="detalle_lote",
                                        children=html.Div(
                                            className="pt-4",
                                            children=ui.panel(
                                                "Lotes a cosechar",
                                                html.Div(
                                                    id="proy-resumen-tabla",
                                                    className="text-xs text-slate-500",
                                                ),
                                                html.Div(
                                                    className=(
                                                        "overflow-hidden rounded-xl border "
                                                        "border-stone-200/80 bg-white"
                                                    ),
                                                    children=dag.AgGrid(
                                                        id="proy-grid",
                                                        columnDefs=[],
                                                        rowData=[],
                                                        defaultColDef={
                                                            "sortable": True,
                                                            "filter": True,
                                                            "resizable": True,
                                                        },
                                                        dashGridOptions={
                                                            "pagination": True,
                                                            "paginationPageSize": 25,
                                                        },
                                                        style={"height": "620px"},
                                                        className="ag-theme-alpine",
                                                    ),
                                                ),
                                                ayuda=(
                                                    "Ordena y filtra para preparar la visita "
                                                    "a campo."
                                                ),
                                            ),
                                        ),
                                    ),
                                    dcc.Tab(
                                        label="Poda y campaña",
                                        value="poda_campania",
                                        children=html.Div(
                                            id="proy-campania", className="space-y-4 pt-4"
                                        ),
                                    ),
                                    dcc.Tab(
                                        label="Cómo se calculó",
                                        value="explicacion",
                                        children=html.Div(
                                            className="pt-4",
                                            children=ui.panel(
                                                "Componentes y evidencia",
                                                html.Div(id="proy-explicacion"),
                                                ayuda="Variables, rezagos y evidencia del fold.",
                                            ),
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Aside(
                        className="aq-projection-aside",
                        children=[
                            ui.panel(
                                "Simular una decisión",
                                _simulador(),
                                ayuda="What-if del challenger; no altera el plan oficial.",
                            ),
                            ui.panel(
                                "Guardar y compartir",
                                _acciones_plan(),
                                ayuda=("Borrador → revisión → aprobación → publicación."),
                            ),
                            ui.panel(
                                "Precisión comprobada",
                                indicador_precision(estado),
                                plegable=True,
                                abierto=False,
                                ayuda="Backtesting temporal, no ajuste dentro de muestra.",
                            ),
                            _estado_operativo_fuentes(estado),
                        ],
                    ),
                ],
            ),
            ui.semaforo(
                "aviso",
                "**El forecast operativo R09 continúa vigente hasta que el challenger "
                "supere el backtesting.** "
                "Las relaciones y sensibilidades son predictivas, no causales. Los horizontes "
                "de 7 a 10 semanas son escenarios y deben revisarse con nueva información.",
            ),
            panel_glosario(
                [
                    "p50_kg",
                    "p10_kg",
                    "p90_kg",
                    "banda_horizonte",
                    "confianza",
                    "rango_relativo",
                    "kg_ha",
                    "probabilidad_cosecha",
                    "kg_condicional",
                    "plantas",
                    "frutos_por_planta",
                    "peso_baya_g",
                ]
            ),
        ],
    )


# ── Callbacks ────────────────────────────────────────────────────────────────


def _tabla_completa(fuente_modelo: str = "oficial") -> pd.DataFrame:
    estado = datos()
    return _enriquecer(_seleccionar_proyeccion(estado, fuente_modelo), estado.get("lotes"))


@callback(
    Output("proy-fundo", "options"),
    Output("proy-banda", "options"),
    Output("proy-semanas", "min"),
    Output("proy-semanas", "max"),
    Output("proy-semanas", "value"),
    Output("proy-semanas", "marks"),
    Output("proy-aviso-emision", "children"),
    Input("proy-fuente-modelo", "value"),
)
def _inicializar(fuente_modelo):
    tabla = _tabla_completa(fuente_modelo)
    if tabla.empty:
        aviso = ui.semaforo(
            "aviso",
            "No hay una corrida para la fuente seleccionada. El challenger solo aparece "
            "después de ejecutar analytics:project con HibridoLegacyResidual_v1.",
        )
        return [], [], 0, 0, [0, 0], {}, aviso

    fundos = [{"label": f, "value": f} for f in sorted(tabla.fundo.dropna().unique())]
    bandas = [
        {"label": VALORES_ANALITICOS["banda_horizonte"].get(b, b), "value": b}
        for b in ("operativo", "planificacion", "escenario")
        if b in set(tabla.banda_horizonte.dropna())
    ]
    fechas = sorted(pd.to_datetime(tabla.fecha_objetivo).dropna().unique())
    maximo = max(0, len(fechas) - 1)
    # Una marca cada dos semanas: con una por semana las etiquetas se solapan.
    marcas = {i: pd.Timestamp(f).strftime("%d/%m") for i, f in enumerate(fechas) if i % 2 == 0}

    emision = pd.to_datetime(tabla.fecha_emision).max()
    aviso = ui.semaforo(
        "aviso" if fuente_modelo == "challenger" else "info",
        f"**Pronóstico emitido el {emision:%d/%m/%Y}.** Cubre de la semana del "
        f"{pd.Timestamp(fechas[0]):%d/%m} a la del {pd.Timestamp(fechas[-1]):%d/%m} sobre "
        f"{ui.miles(tabla.lote_id.nunique())} lotes. "
        + (
            "Es experimental: no reemplaza R09 ni puede publicarse sin superar los gates."
            if fuente_modelo == "challenger"
            else "Es la salida oficial vigente."
        ),
    )
    return fundos, bandas, 0, maximo, [0, maximo], marcas, aviso


@callback(
    Output("proy-modulo", "options"),
    Input("proy-fundo", "value"),
    Input("proy-fuente-modelo", "value"),
)
def _modulos(fundos, fuente_modelo="oficial"):
    tabla = _tabla_completa(fuente_modelo)
    if tabla.empty:
        return []
    if fundos:
        tabla = tabla[tabla.fundo.isin(fundos)]
    return [{"label": m, "value": m} for m in sorted(tabla.modulo.dropna().unique())]


@callback(
    Output("proy-lote", "options"),
    Input("proy-fundo", "value"),
    Input("proy-modulo", "value"),
    Input("proy-fuente-modelo", "value"),
)
def _lotes(fundos, modulos, fuente_modelo="oficial"):
    tabla = _tabla_completa(fuente_modelo)
    if tabla.empty:
        return []
    if fundos:
        tabla = tabla[tabla.fundo.isin(fundos)]
    if modulos:
        tabla = tabla[tabla.modulo.isin(modulos)]
    return [{"label": lote, "value": lote} for lote in sorted(tabla.lote.dropna().unique())]


@callback(
    Output("proy-comparacion", "children"),
    Output("proy-replay", "children"),
    Output("proy-kpis", "children"),
    Output("proy-curva", "figure"),
    Output("proy-plan-semanal", "children"),
    Output("proy-grid", "columnDefs"),
    Output("proy-grid", "rowData"),
    Output("proy-resumen-tabla", "children"),
    Output("proy-riesgo", "children"),
    Output("proy-campania", "children"),
    Output("proy-explicacion", "children"),
    Output("proy-simulador-aviso", "children"),
    Input("proy-fundo", "value"),
    Input("proy-modulo", "value"),
    Input("proy-lote", "value"),
    Input("proy-banda", "value"),
    Input("proy-semanas", "value"),
    Input("proy-escenario", "value"),
    Input("proy-fuente-modelo", "value"),
    Input("proy-ajuste-plantas", "value"),
    Input("proy-ajuste-cuajado", "value"),
    Input("proy-caida-frutos", "value"),
    Input("proy-ajuste-riego", "value"),
    Input("proy-clima-escenario", "value"),
    Input("proy-ajuste-poda", "value"),
    Input("proy-desplazamiento", "value"),
    Input("proy-temp-delta", "value"),
    Input("proy-dpv-delta", "value"),
)
def _actualizar(
    fundos,
    modulos,
    lotes,
    bandas,
    semanas,
    escenario,
    fuente_modelo,
    ajuste_plantas,
    ajuste_cuajado,
    caida_frutos,
    ajuste_riego,
    clima_escenario,
    ajuste_poda,
    desplazamiento,
    temp_delta,
    dpv_delta,
):
    estado = datos()
    completa, advertencias = _tabla_interactiva(
        estado,
        fuente_modelo,
        ajuste_plantas,
        ajuste_cuajado,
        caida_frutos,
        ajuste_riego,
        clima_escenario,
        ajuste_poda,
        desplazamiento,
        temp_delta,
        dpv_delta,
    )
    filtrada = _filtrar(completa, fundos, modulos, lotes, bandas, semanas)
    escenario = escenario or "p50_kg"
    fechas_comparacion = (
        pd.to_datetime(filtrada.fecha_objetivo).dropna().tolist() if not filtrada.empty else None
    )
    comparacion = _comparacion_modelos(
        estado,
        fundos,
        modulos,
        lotes,
        bandas,
        fechas_comparacion,
    )
    replay = _panel_replay(estado)
    historial_real = estado.get("cosecha_real", pd.DataFrame())
    if isinstance(historial_real, pd.DataFrame) and not historial_real.empty and not filtrada.empty:
        historial_real = historial_real.copy()
        ids = set(filtrada.lote_id.dropna()) if "lote_id" in filtrada else set()
        if ids and "lote_id" in historial_real:
            historial_real = historial_real[historial_real.lote_id.isin(ids)]
        campanias = set(filtrada.campania.dropna().astype(str)) if "campania" in filtrada else set()
        if campanias and "campania" in historial_real:
            historial_real = historial_real[historial_real.campania.astype(str).isin(campanias)]
        corte = pd.to_datetime(filtrada.fecha_emision, errors="coerce").max()
        historial_real["fecha_objetivo"] = pd.to_datetime(
            historial_real.fecha_objetivo, errors="coerce"
        )
        if pd.notna(corte):
            historial_real = historial_real[historial_real.fecha_objetivo < corte]

    if filtrada.empty:
        vacio = ui.semaforo(
            "aviso", "Ningún lote cumple los filtros seleccionados. Prueba a ampliarlos."
        )
        figura = go.Figure().update_layout(template="plotly_white", height=340)
        return (
            comparacion,
            replay,
            vacio,
            figura,
            html.Div(),
            [],
            [],
            "",
            html.Div(),
            html.Div(),
            html.Div(),
            ui.semaforo("aviso", " ".join(advertencias)) if advertencias else html.Div(),
        )

    aviso_simulador = ui.semaforo("aviso", " ".join(advertencias)) if advertencias else html.Div()

    return (
        comparacion,
        replay,
        _kpis(filtrada, escenario),
        _figura(filtrada, escenario, historial_real),
        _tabla_plan(filtrada, escenario),
        _columnas_grid(),
        _filas_grid(filtrada),
        f"Mostrando {ui.miles(len(filtrada))} filas de "
        f"{ui.miles(filtrada.lote_id.nunique())} lotes.",
        _panel_riesgo(filtrada),
        _panel_campania(filtrada, escenario),
        _panel_explicacion(filtrada, estado.get("evidencia_features", pd.DataFrame())),
        aviso_simulador,
    )


@callback(
    Output("proy-scenario-id", "data"),
    Output("proy-gobierno-aviso", "children"),
    Input("proy-guardar-escenario", "n_clicks"),
    Input("proy-enviar-revision", "n_clicks"),
    State("proy-scenario-id", "data"),
    State("proy-nombre-escenario", "value"),
    State("proy-modo", "value"),
    State("proy-fuente-modelo", "value"),
    State("proy-ajuste-plantas", "value"),
    State("proy-ajuste-cuajado", "value"),
    State("proy-caida-frutos", "value"),
    State("proy-ajuste-riego", "value"),
    State("proy-clima-escenario", "value"),
    State("proy-ajuste-poda", "value"),
    State("proy-desplazamiento", "value"),
    State("proy-temp-delta", "value"),
    State("proy-dpv-delta", "value"),
    prevent_initial_call=True,
)
def _gobernar_escenario(
    guardar,
    revisar,
    scenario_id,
    nombre,
    modo,
    fuente_modelo,
    plantas,
    cuajado,
    caida,
    riego,
    clima,
    poda,
    desplazamiento,
    temperatura,
    dpv,
):
    del guardar, revisar
    try:
        if dash.ctx.triggered_id == "proy-enviar-revision":
            if not scenario_id:
                return None, ui.semaforo("aviso", "Primero guarda la simulación.")
            enviar_escenario_revision(int(scenario_id))
            return scenario_id, ui.semaforo(
                "ok", f"Escenario n.º {scenario_id} enviado a revisión."
            )
        estado = datos()
        runs = estado.get("runs", pd.DataFrame())
        proyectos = runs[runs.tipo.eq("project")] if not runs.empty else pd.DataFrame()
        run_base_id = int(proyectos.iloc[0].run_id) if not proyectos.empty else None
        _, advertencias = _tabla_interactiva(
            estado,
            fuente_modelo,
            plantas,
            cuajado,
            caida,
            riego,
            clima,
            poda,
            desplazamiento,
            temperatura,
            dpv,
        )
        parametros = {
            "modelo": (
                "HibridoLegacyResidual_v1" if fuente_modelo == "challenger" else "R09_publicado"
            ),
            "fuente_modelo": fuente_modelo,
            "plantas_pct": plantas or 0,
            "cuajado_pct": cuajado or 0,
            "caida_frutos_pct": caida or 0,
            "riego_pct": riego or 0,
            "clima_escenario": clima or "base",
            "poda_delta_dias": poda or 0,
            "desplazamiento_semanas": desplazamiento or 0,
            "temp_delta_c": temperatura or 0,
            "dpv_delta_kpa": dpv or 0,
            "etiqueta_causal": False,
        }
        nuevo_id = guardar_escenario_proyeccion(
            nombre=nombre or f"Escenario {dt.datetime.now():%Y-%m-%d %H:%M}",
            modo_decision=modo or "plan_semanal",
            run_base_id=run_base_id,
            parametros=parametros,
            advertencias=advertencias,
        )
        return nuevo_id, ui.semaforo(
            "ok", f"Escenario n.º {nuevo_id} guardado; todavía no está aprobado ni publicado."
        )
    except Exception as exc:
        return scenario_id, ui.semaforo(
            "error", f"No se pudo cambiar el escenario: {type(exc).__name__}: {exc}"
        )


def _kpis(filtrada: pd.DataFrame, escenario: str) -> html.Div:
    plan = _plan_semanal(filtrada, escenario)
    pico = plan.loc[plan[escenario].idxmax()] if not plan.empty else None
    # Cuántas semanas concentran el 80 % del volumen: dice dónde va a doler el personal.
    concentracion = int((plan.acumulado <= 0.8).sum() + 1) if not plan.empty else 0
    total = filtrada[escenario].sum()
    return ui.fila_kpi(
        [
            ui.kpi(
                ESCENARIOS_PLURAL[escenario],
                numero(total, 0),
                f"Total del filtro actual, escenario {ESCENARIOS[escenario].lower()}.",
                serie=plan[escenario].tolist() if not plan.empty else None,
                ayuda="Suma de los lotes seleccionados en el escenario elegido.",
            ),
            ui.kpi(
                "Escenario conservador",
                numero(filtrada.p10_kg.sum(), 0),
                "1 de cada 10 semanas debería quedar por debajo. No es un piso garantizado.",
            ),
            ui.kpi(
                "Semana más cargada",
                f"{pd.Timestamp(pico.fecha_objetivo):%d/%m}" if pico is not None else "—",
                f"{numero(pico[escenario], 0)} kg, el {100 * pico.porcentaje:.0f} % del período."
                if pico is not None
                else "",
                ayuda="Donde se concentra la mayor exigencia de cuadrilla y packing.",
            ),
            ui.kpi(
                "Semanas que concentran el 80 %",
                str(concentracion),
                f"De {len(plan)} semanas del período.",
                ayuda="Cuanto menor sea, más se concentra el esfuerzo en pocas semanas.",
            ),
        ]
    )


def _figura(
    filtrada: pd.DataFrame,
    escenario: str,
    historial_real: pd.DataFrame | None = None,
) -> go.Figure:
    plan = _plan_semanal(filtrada, escenario)
    figura = go.Figure()
    if isinstance(historial_real, pd.DataFrame) and not historial_real.empty:
        real = historial_real.copy()
        real["fecha_objetivo"] = pd.to_datetime(real.fecha_objetivo, errors="coerce")
        real["real_kg"] = pd.to_numeric(real.real_kg, errors="coerce")
        real = real.dropna(subset=["fecha_objetivo", "real_kg"])
        if not real.empty:
            real = real.groupby("fecha_objetivo", as_index=False).real_kg.sum()
            figura.add_trace(
                go.Scatter(
                    x=real.fecha_objetivo,
                    y=real.real_kg,
                    name="Real cosechado",
                    mode="lines+markers",
                    line={"color": "#111827", "width": 3},
                )
            )
    if not plan.empty:
        figura.add_trace(
            go.Scatter(
                x=plan.fecha_objetivo,
                y=plan.p90_kg,
                name="Optimista",
                line={"width": 0},
                hoverinfo="skip",
                showlegend=False,
            )
        )
        figura.add_trace(
            go.Scatter(
                x=plan.fecha_objetivo,
                y=plan.p10_kg,
                name="Margen",
                fill="tonexty",
                fillcolor="rgba(14,116,144,0.14)",
                line={"width": 0},
                hoverinfo="skip",
            )
        )
        figura.add_trace(
            go.Scatter(
                x=plan.fecha_objetivo,
                y=plan[escenario],
                name=ESCENARIOS[escenario],
                line={"color": "#0e7490", "width": 2.5},
                mode="lines+markers",
            )
        )
    figura.update_layout(
        template="plotly_white",
        height=360,
        margin={"l": 30, "r": 20, "t": 20, "b": 30},
        yaxis_title="kilos",
        xaxis_title=None,
        legend={"orientation": "h", "y": 1.12, "x": 0},
    )
    if isinstance(historial_real, pd.DataFrame) and not historial_real.empty:
        fechas = pd.to_datetime(historial_real.fecha_objetivo, errors="coerce").dropna()
        if not fechas.empty:
            figura.add_vline(
                x=fechas.max(),
                line_dash="dot",
                line_color="#94a3b8",
                annotation_text="Última semana real",
                annotation_position="top left",
            )
    return figura


def _tabla_plan(filtrada: pd.DataFrame, escenario: str) -> html.Div:
    plan = _plan_semanal(filtrada, escenario)
    if plan.empty:
        return html.Div()
    # El encabezado sigue al escenario elegido: con el conservador activo, una columna fija
    # llamada «Kilos esperados» mostraría el mismo número que la columna «Conservador» y
    # daría a entender que son dos cifras distintas.
    vista = pd.DataFrame(
        {
            "Sem": plan.fecha_objetivo.dt.isocalendar().week.astype(int),
            "Semana del": plan.fecha_objetivo.dt.strftime("%d/%m/%Y"),
            f"{ESCENARIOS_PLURAL[escenario]} (kg)": plan[escenario].map(lambda v: ui.miles(v)),
            "Conservador": plan.p10_kg.map(lambda v: ui.miles(v)),
            "Optimista": plan.p90_kg.map(lambda v: ui.miles(v)),
            "Ancho del margen": plan.ancho_relativo.map(
                lambda v: "—" if pd.isna(v) else f"{100 * v:.0f} %".replace(".", ",")
            ),
            "% del total": plan.porcentaje.map(lambda v: f"{100 * v:.1f} %".replace(".", ",")),
            "Acumulado": plan.acumulado.map(lambda v: f"{100 * v:.0f} %".replace(".", ",")),
        }
    )
    return ui.tabla_desde_df(vista, plano=True)


def _columnas_grid() -> list[dict]:
    """Definiciones de columna con nombre legible y orden numérico preservado.

    El separador de miles se aplica con un formateador de presentación, nunca convirtiendo
    el número a texto: si se convirtiera, la tabla ordenaría alfabéticamente y «9.000»
    quedaría por encima de «80.000».
    """
    numericas = {
        "p50_kg",
        "p10_kg",
        "p90_kg",
        "kg_ha",
        "plantas",
        "kg_planta",
        "frutos_por_planta",
        "peso_baya_g",
        "rango_relativo",
        "probabilidad_cosecha",
        "kg_condicional",
    }
    # La semana es un identificador, no una magnitud: sin separador de millar.
    enteras = {"semana_iso"}
    miles = {"p50_kg", "p10_kg", "p90_kg", "kg_ha", "kg_condicional", "plantas"}
    columnas = []
    for campo in COLUMNAS_TABLA:
        definicion: dict = {"field": campo, "headerName": etiqueta(campo)}
        if campo in enteras:
            definicion["type"] = "numericColumn"
        elif campo in numericas:
            definicion["type"] = "numericColumn"
            formato = ",.0f" if campo in miles else ".2f"
            if campo in {"rango_relativo", "probabilidad_cosecha"}:
                definicion["valueFormatter"] = {
                    "function": "params.value == null ? '' : d3.format('.0%')(params.value)"
                }
            else:
                definicion["valueFormatter"] = {
                    "function": f"params.value == null ? '' : d3.format('{formato}')(params.value)"
                }
        columnas.append(definicion)
    return columnas


def _filas_grid(filtrada: pd.DataFrame) -> list[dict]:
    vista = filtrada.copy()
    vista["banda_horizonte"] = vista.banda_horizonte.map(
        lambda b: VALORES_ANALITICOS["banda_horizonte"].get(b, b)
    )
    vista["confianza"] = vista.confianza.map(lambda c: VALORES_ANALITICOS["confianza"].get(c, c))
    vista["fecha_objetivo"] = pd.to_datetime(vista.fecha_objetivo).dt.strftime("%d/%m/%Y")
    presentes = [c for c in COLUMNAS_TABLA if c in vista]
    return vista[presentes].to_dict("records")


def _lotes_de_riesgo(filtrada: pd.DataFrame) -> pd.DataFrame:
    ancho = filtrada.rango_relativo > UMBRAL_RANGO_ANCHO
    floja = filtrada.confianza.astype(str).str.lower() == "baja"
    return filtrada[ancho.fillna(False) | floja].sort_values("p50_kg", ascending=False)


def _panel_riesgo(filtrada: pd.DataFrame) -> html.Div:
    riesgo = _lotes_de_riesgo(filtrada)
    if riesgo.empty:
        return ui.semaforo(
            "ok",
            "**Ningún lote del filtro tiene un margen mayor a la mitad de su volumen "
            "previsto.** El plan se puede comprometer con el detalle de arriba.",
        )
    kilos = riesgo.p50_kg.sum()
    parte = 100 * kilos / filtrada.p50_kg.sum() if filtrada.p50_kg.sum() else 0
    vista = riesgo.head(25)[
        [
            c
            for c in (
                "fundo",
                "modulo",
                "lote",
                "fecha_objetivo",
                "p50_kg",
                "rango_relativo",
                "confianza",
            )
            if c in riesgo
        ]
    ].copy()
    vista["fecha_objetivo"] = pd.to_datetime(vista.fecha_objetivo).dt.strftime("%d/%m/%Y")
    vista["p50_kg"] = vista.p50_kg.map(lambda v: ui.miles(v))
    vista["rango_relativo"] = vista.rango_relativo.map(
        lambda v: "—" if pd.isna(v) else f"{100 * v:.0f} %".replace(".", ",")
    )
    vista["confianza"] = vista.confianza.map(lambda c: VALORES_ANALITICOS["confianza"].get(c, c))
    vista.columns = [etiqueta(c) for c in vista.columns]
    # El decimal se convierte por separado: aplicar `replace(".", ",")` a la frase entera
    # convertía también los separadores de millar de `ui.miles` y salía «1,224 lotes».
    porcentaje = f"{parte:.0f}".replace(".", ",")
    cuantos = (
        "1 lote-semana concentra"
        if len(riesgo) == 1
        else (f"{ui.miles(len(riesgo))} lotes-semana concentran")
    )
    hijos = [
        ui.semaforo(
            "aviso",
            f"**{cuantos} {ui.miles(kilos)} kg ({porcentaje} % del filtro) con margen ancho "
            "o confianza baja.**",
        ),
        ui.tabla_desde_df(vista, plano=True),
    ]
    if len(riesgo) > 25:
        hijos.append(
            html.P(
                f"Se muestran los 25 de mayor volumen, de {ui.miles(len(riesgo))}. "
                "La descarga incluye todos.",
                className="text-xs text-slate-400",
            )
        )
    return html.Div(hijos, className="space-y-3")


# ── Descargas ────────────────────────────────────────────────────────────────


def _meta(filtrada: pd.DataFrame, escenario: str, estado: dict) -> list[tuple[str, str]]:
    """Portada del Excel: de dónde salió el archivo y con qué filtros, para que se sostenga solo."""
    runs = estado["runs"]
    corrida = f"n.º {int(runs.iloc[0].run_id)}" if not runs.empty else "no registrada"
    huella = str(runs.iloc[0].firma_snapshot)[:12] if not runs.empty else "—"
    emision = pd.to_datetime(filtrada.fecha_emision).max()
    modelos = ", ".join(sorted(filtrada.modelo.dropna().astype(str).unique()))
    escenario_motor = (
        ", ".join(sorted(filtrada.escenario_nombre.dropna().astype(str).unique()))
        if "escenario_nombre" in filtrada
        else "base publicado"
    )
    return [
        ("Generado", dt.datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Corrida analítica", corrida),
        ("Huella de los datos", huella),
        ("Pronóstico emitido", f"{emision:%Y-%m-%d}"),
        ("Modelo", modelos or "—"),
        ("Escenario del motor", escenario_motor),
        ("Escenario", ESCENARIOS[escenario]),
        ("Fundos", ", ".join(sorted(filtrada.fundo.dropna().unique())) or "todos"),
        ("Lotes incluidos", str(filtrada.lote_id.nunique())),
        (
            "Semanas",
            f"{pd.to_datetime(filtrada.fecha_objetivo).min():%d/%m} a "
            f"{pd.to_datetime(filtrada.fecha_objetivo).max():%d/%m}",
        ),
        (
            "Advertencia",
            "El escenario conservador y el optimista no son garantías: son los "
            "valores que el modelo espera superar o no superar 1 de cada 10 veces. "
            "Los totales suman lotes, así que su margen es una suma de márgenes.",
        ),
    ]


def _vista_descarga(filtrada: pd.DataFrame) -> pd.DataFrame:
    presentes = [c for c in COLUMNAS_TABLA if c in filtrada]
    vista = filtrada[presentes].copy()
    vista["banda_horizonte"] = vista.banda_horizonte.map(
        lambda b: VALORES_ANALITICOS["banda_horizonte"].get(b, b)
    )
    vista.columns = [etiqueta(c) for c in presentes]
    return vista


@callback(
    Output("proy-descarga-excel", "data"),
    Input("proy-btn-excel", "n_clicks"),
    State("proy-fundo", "value"),
    State("proy-modulo", "value"),
    State("proy-lote", "value"),
    State("proy-banda", "value"),
    State("proy-semanas", "value"),
    State("proy-escenario", "value"),
    State("proy-fuente-modelo", "value"),
    State("proy-ajuste-plantas", "value"),
    State("proy-ajuste-cuajado", "value"),
    State("proy-caida-frutos", "value"),
    State("proy-ajuste-riego", "value"),
    State("proy-clima-escenario", "value"),
    State("proy-ajuste-poda", "value"),
    State("proy-desplazamiento", "value"),
    State("proy-temp-delta", "value"),
    State("proy-dpv-delta", "value"),
    prevent_initial_call=True,
)
def _descargar_excel(
    n,
    fundos,
    modulos,
    lotes,
    bandas,
    semanas,
    escenario,
    fuente_modelo,
    plantas,
    cuajado,
    caida,
    riego,
    clima,
    poda,
    desplazamiento,
    temperatura,
    dpv,
):
    if not n:
        raise PreventUpdate
    estado = datos()
    completa, _ = _tabla_interactiva(
        estado,
        fuente_modelo,
        plantas,
        cuajado,
        caida,
        riego,
        clima,
        poda,
        desplazamiento,
        temperatura,
        dpv,
    )
    filtrada = _filtrar(completa, fundos, modulos, lotes, bandas, semanas)
    if filtrada.empty:
        raise PreventUpdate
    escenario = escenario or "p50_kg"

    plan = _plan_semanal(filtrada, escenario)
    plan_vista = plan.rename(
        columns={
            "fecha_objetivo": "Semana",
            "p50_kg": "Esperado (kg)",
            "p10_kg": "Conservador (kg)",
            "p90_kg": "Optimista (kg)",
            "porcentaje": "% del total",
            "acumulado": "Acumulado",
            "ancho_relativo": "Ancho del margen",
        }
    )
    hojas = [
        Hoja(
            nombre="Plan semanal",
            titulo="Kilos esperados por semana",
            nota="Suma de los lotes filtrados. El margen del total es una suma de márgenes, "
            "no el margen exacto del total.",
            datos=plan_vista,
            porcentajes=("% del total", "Acumulado", "Ancho del margen"),
        ),
        Hoja(
            nombre="Detalle por lote",
            titulo="Proyección por lote y semana",
            nota="Plantas, frutos por planta y peso de baya multiplicados dan los kilos "
            "esperados. Las plantas son las del maestro del lote.",
            datos=_vista_descarga(filtrada),
        ),
    ]
    riesgo = _lotes_de_riesgo(filtrada)
    if not riesgo.empty:
        hojas.append(
            Hoja(
                nombre="Margen alto",
                titulo="Lotes menos firmes",
                nota="Margen mayor a la mitad del volumen previsto, o confianza baja por "
                "falta de historia propia del lote. Conviene evaluarlos en campo antes "
                "de comprometer despacho.",
                datos=_vista_descarga(riesgo),
            )
        )
    libro = construir_libro(hojas, _meta(filtrada, escenario, estado))
    nombre = f"aquanqa_proyeccion_{dt.date.today():%Y%m%d}.xlsx"
    return dcc.send_bytes(libro, nombre)


@callback(
    Output("proy-descarga-csv", "data"),
    Input("proy-btn-csv", "n_clicks"),
    State("proy-fundo", "value"),
    State("proy-modulo", "value"),
    State("proy-lote", "value"),
    State("proy-banda", "value"),
    State("proy-semanas", "value"),
    State("proy-fuente-modelo", "value"),
    State("proy-ajuste-plantas", "value"),
    State("proy-ajuste-cuajado", "value"),
    State("proy-caida-frutos", "value"),
    State("proy-ajuste-riego", "value"),
    State("proy-clima-escenario", "value"),
    State("proy-ajuste-poda", "value"),
    State("proy-desplazamiento", "value"),
    State("proy-temp-delta", "value"),
    State("proy-dpv-delta", "value"),
    prevent_initial_call=True,
)
def _descargar_csv(
    n,
    fundos,
    modulos,
    lotes,
    bandas,
    semanas,
    fuente_modelo,
    plantas,
    cuajado,
    caida,
    riego,
    clima,
    poda,
    desplazamiento,
    temperatura,
    dpv,
):
    if not n:
        raise PreventUpdate
    estado = datos()
    completa, _ = _tabla_interactiva(
        estado,
        fuente_modelo,
        plantas,
        cuajado,
        caida,
        riego,
        clima,
        poda,
        desplazamiento,
        temperatura,
        dpv,
    )
    filtrada = _filtrar(completa, fundos, modulos, lotes, bandas, semanas)
    if filtrada.empty:
        raise PreventUpdate
    return dcc.send_data_frame(
        _vista_descarga(filtrada).to_csv,
        f"aquanqa_proyeccion_{dt.date.today():%Y%m%d}.csv",
        index=False,
    )
