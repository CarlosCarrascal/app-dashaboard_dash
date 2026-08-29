"""Callbacks de la mesa operativa de Proyección.

Cada salida visual tiene un único responsable. Los callbacks solo leen resultados ya
persistidos; nunca abren Excel ni ejecutan el motor de proyección.
"""

from __future__ import annotations

import datetime as dt
import time
from functools import lru_cache

import pandas as pd
from dash import Input, Output, State, callback, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from analitica.nucleo.exportar import Hoja, construir_libro
from servicios.proyeccion import estado_proyeccion as datos
from servicios.proyeccion import estado_replay_proyeccion

from .proyeccion_charts import (
    curva_operativa_actual,
    curvas_por_fundo,
    figura_matriz_six,
    historico_y_desviacion,
)
from .proyeccion_domain import (
    HORIZONTE_SEMANAS,
    R09_REFERENCIA,
    SERIES_HISTORICAS,
    agrupar_replay_historico,
    alinear_replay_con_real_comun,
    aplicar_horizonte,
    enriquecer,
    filas_grid,
    filtrar_ubicacion,
    inicio_ventana_operativa,
    limitar_ventana_semanal,
    matriz_six,
    meta_descarga,
    metricas_replay_historico,
    plan_semanal,
    preparar_real,
    preparar_replay_historico,
    resumen_fundos,
    seleccionar_modelo_operativo,
    seleccionar_r09_referencia,
    vista_descarga,
    vista_trazabilidad,
)
from .proyeccion_views import (
    contexto_corrida,
    resumen_principal,
    tabla_plan,
    tabla_six,
)

TTL_VISTA_SEGUNDOS = 300

_COLUMNAS_ESTADO_MODELO = (
    "estado_modelo",
    "model_status",
    "estado_release",
    "release_estado",
    "estado_publicacion",
    "publicacion",
)
_MARCAS_MODELO_OCULTO = (
    "rejected",
    "rechazad",
    "experimental",
    "withdrawn",
    "retirad",
)
_PREFERENCIA_SERIES = (
    "HibridoOcurrenciaOnline_v2",
    "MacroLegacy_v1",
    R09_REFERENCIA,
)


def _instante_cache() -> int:
    return int(time.time() // TTL_VISTA_SEGUNDOS)


def _campanias(tabla: pd.DataFrame) -> set[str]:
    if not isinstance(tabla, pd.DataFrame) or tabla.empty or "campania" not in tabla:
        return set()
    return set(tabla["campania"].dropna().astype(str))


def _misma_campania(tabla: pd.DataFrame, referencia: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(tabla, pd.DataFrame) or tabla.empty:
        return pd.DataFrame()
    campanias = _campanias(referencia)
    if campanias and "campania" in tabla:
        return tabla[tabla["campania"].astype(str).isin(campanias)].copy()
    return tabla.copy()


def _tabla_completa(estado: dict | None = None) -> pd.DataFrame:
    if estado is None:
        return _bases_cache(_instante_cache())[1]
    return enriquecer(seleccionar_modelo_operativo(estado), estado.get("lotes"))


def _real_completo(estado: dict, modelo: pd.DataFrame) -> pd.DataFrame:
    return preparar_real(_misma_campania(estado.get("cosecha_real", pd.DataFrame()), modelo))


def _r09_completo(estado: dict, modelo: pd.DataFrame) -> pd.DataFrame:
    return enriquecer(
        _misma_campania(seleccionar_r09_referencia(estado), modelo), estado.get("lotes")
    )


@lru_cache(maxsize=2)
def _bases_cache(minuto: int) -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    del minuto
    estado = datos()
    modelo = enriquecer(seleccionar_modelo_operativo(estado), estado.get("lotes"))
    real = _real_completo(estado, modelo)
    r09 = _r09_completo(estado, modelo)
    return estado, modelo, real, r09


def _opciones(tabla: pd.DataFrame, columna: str) -> list[dict[str, str]]:
    if tabla.empty or columna not in tabla:
        return []
    valores = sorted(tabla[columna].dropna().astype(str).unique())
    return [{"label": valor, "value": valor} for valor in valores]


def _seleccion_valida(actual, opciones: list[dict[str, str]]) -> list[str]:
    permitidos = {opcion["value"] for opcion in opciones}
    valores = actual if isinstance(actual, list) else ([actual] if actual else [])
    return [str(valor) for valor in valores if str(valor) in permitidos]


def _valor_si_cambio(actual, nuevo: list[str]):
    """Evita cascadas de callbacks cuando la selección válida no cambió."""
    actual_normalizado = actual if isinstance(actual, list) else ([actual] if actual else [])
    return no_update if [str(valor) for valor in actual_normalizado] == nuevo else nuevo


def _estado_modelo_oculto(valor: object) -> bool:
    if valor is None or (not isinstance(valor, (dict, list, tuple)) and pd.isna(valor)):
        return False
    texto = str(valor).strip().casefold()
    return any(marca in texto for marca in _MARCAS_MODELO_OCULTO)


def _filtrar_modelos_visibles(tabla: pd.DataFrame) -> pd.DataFrame:
    """Retira releases que el servicio marca expresamente como no publicables.

    La ausencia de una columna de gobierno conserva el comportamiento vigente. La UI no
    infiere el estado por el nombre del modelo: solo obedece marcas explícitas del servicio.
    """
    if not isinstance(tabla, pd.DataFrame) or tabla.empty:
        return pd.DataFrame()
    salida = tabla.copy()
    for columna in _COLUMNAS_ESTADO_MODELO:
        if columna in salida:
            salida = salida.loc[~salida[columna].map(_estado_modelo_oculto)].copy()
    return salida


def _periodos_cerrados(real: pd.DataFrame) -> pd.DataFrame:
    """Devuelve las claves campaña-semana que el servicio declaró evaluables."""
    if (
        not isinstance(real, pd.DataFrame)
        or real.empty
        or "campania" not in real
        or "fecha_objetivo" not in real
    ):
        return pd.DataFrame(columns=["campania", "fecha_objetivo"])
    salida = real[["campania", "fecha_objetivo"]].copy()
    salida["campania"] = salida["campania"].astype(str)
    fechas = pd.to_datetime(salida["fecha_objetivo"], errors="coerce")
    salida["fecha_objetivo"] = fechas.dt.to_period("W-SUN").dt.start_time
    return salida.dropna().drop_duplicates().reset_index(drop=True)


def _restringir_a_periodos_cerrados(replay: pd.DataFrame, periodos: pd.DataFrame) -> pd.DataFrame:
    """Impide que una predicción sin real cerrado se convierta en un real cero."""
    if not isinstance(replay, pd.DataFrame) or replay.empty or periodos.empty:
        return pd.DataFrame(columns=replay.columns if isinstance(replay, pd.DataFrame) else None)
    salida = replay.copy()
    salida["campania"] = salida["campania"].astype(str)
    fechas = pd.to_datetime(salida["fecha_objetivo"], errors="coerce")
    salida["fecha_objetivo"] = fechas.dt.to_period("W-SUN").dt.start_time
    return salida.merge(periodos, on=["campania", "fecha_objetivo"], how="inner")


def _campanias_evaluables(replay: pd.DataFrame) -> list[str]:
    """Ordena campañas concretas por su fecha objetivo cerrada más reciente."""
    if (
        not isinstance(replay, pd.DataFrame)
        or replay.empty
        or "campania" not in replay
        or "fecha_objetivo" not in replay
    ):
        return []
    salida = replay.copy()
    salida["fecha_objetivo"] = pd.to_datetime(salida["fecha_objetivo"], errors="coerce")
    if "emitio_prediccion" in salida:
        emitio = salida["emitio_prediccion"].fillna(False).astype(bool)
        salida = salida.loc[emitio]
    salida = salida.dropna(subset=["campania", "fecha_objetivo"])
    if salida.empty:
        return []
    recientes = salida.groupby(salida["campania"].astype(str))["fecha_objetivo"].max()
    return recientes.sort_values(ascending=False, kind="stable").index.astype(str).tolist()


def _seleccionar_serie_visible(serie: object, disponibles: list[str]) -> str | None:
    actual = str(serie) if serie not in (None, "") else None
    if actual in disponibles:
        return actual
    for preferida in _PREFERENCIA_SERIES:
        if preferida in disponibles:
            return preferida
    return disponibles[0] if disponibles else None


def _seleccionar_campania_concreta(campania: object, disponibles: list[str]) -> str | None:
    actual = str(campania) if campania not in (None, "") else None
    return actual if actual in disponibles else (disponibles[0] if disponibles else None)


def _nowcast_para_vista(
    estado: dict,
    modelo: pd.DataFrame,
    fundo,
    modulo,
    lote,
) -> pd.DataFrame:
    """Devuelve el cierre semanal solo como comparación del ámbito operativo.

    La release del nowcast está agregada por fundo/empresa, no por módulo o lote.
    Por eso no se muestra cuando el agrónomo baja a esos niveles: dibujar el total de
    un fundo como si fuera el lote seleccionado sería una comparación engañosa.
    """
    tabla = estado.get("nowcast_cierre", pd.DataFrame())
    if not isinstance(tabla, pd.DataFrame) or tabla.empty:
        return pd.DataFrame()

    def _seleccionado(valor) -> bool:
        if isinstance(valor, str):
            return valor not in ("", "Todos")
        return any(item not in (None, "", "Todos") for item in (valor or []))

    if _seleccionado(modulo) or _seleccionado(lote):
        return pd.DataFrame()

    salida = tabla.copy()
    if "campania" in modelo and not modelo.empty and "campania" in salida:
        campanias = set(modelo["campania"].dropna().astype(str))
        salida = salida[salida["campania"].astype(str).isin(campanias)].copy()
    if salida.empty or "fundo" not in salida:
        return pd.DataFrame()

    if not _seleccionado(fundo):
        # La fila Empresa es la única que representa el total de la operación.
        return salida[salida["fundo"].astype(str).eq("Empresa")].copy()

    fundos = [fundo] if isinstance(fundo, str) else list(fundo or [])
    fundos = [str(valor) for valor in fundos if valor not in (None, "", "Todos")]
    seleccion = salida[salida["fundo"].astype(str).isin(fundos)].copy()
    if not seleccion.empty and len(fundos) == 1:
        return seleccion
    if seleccion.empty:
        return pd.DataFrame()

    numericas = [
        columna
        for columna in (
            "kg_lun_mar",
            "p50_kg",
            "real_kg",
            "macro_kg",
            "r09_presemana_kg",
            "r09_misma_semana_kg",
        )
        if columna in seleccion
    ]
    agrupada = seleccion.groupby(
        [
            columna
            for columna in ("campania", "semana_inicio", "semana_cierre", "fecha_corte")
            if columna in seleccion
        ],
        as_index=False,
    )[numericas].sum(min_count=1)
    agrupada["fundo"] = "Selección"
    return agrupada


def _resolver_vista(
    fundo,
    modulo,
    lote,
    horizonte: str | None,
) -> dict[str, object]:
    estado, modelo_total, real_total, r09_total = _bases_cache(_instante_cache())

    inicio = inicio_ventana_operativa(modelo_total, real_total)
    horizonte = horizonte or HORIZONTE_SEMANAS
    modelo_horizonte = aplicar_horizonte(modelo_total, horizonte, inicio=inicio)
    r09_horizonte = aplicar_horizonte(r09_total, horizonte, inicio=inicio)
    hibrido_v2_total = enriquecer(
        _misma_campania(estado.get("hibrido_v2", pd.DataFrame()), modelo_total),
        estado.get("lotes"),
    )
    fin = (
        pd.to_datetime(modelo_horizonte.get("semana_inicio"), errors="coerce").max()
        if not modelo_horizonte.empty
        else pd.NaT
    )
    inicio_grafico = pd.to_datetime(inicio, errors="coerce")
    if pd.notna(inicio_grafico):
        inicio_grafico -= pd.Timedelta(days=7)

    def _ventana_grafico(tabla: pd.DataFrame) -> pd.DataFrame:
        if tabla.empty:
            return tabla.copy()
        salida = tabla.copy()
        if pd.notna(inicio_grafico):
            salida = salida[salida["semana_inicio"] >= inicio_grafico]
        if pd.notna(fin):
            salida = salida[salida["semana_inicio"] <= fin]
        return salida

    return {
        "estado": estado,
        "inicio": inicio,
        "modelo_total": modelo_total,
        "modelo_fundos": filtrar_ubicacion(modelo_horizonte, fundo, modulo, lote),
        "modelo": filtrar_ubicacion(modelo_horizonte, fundo, modulo, lote),
        "modelo_grafico": filtrar_ubicacion(_ventana_grafico(modelo_total), fundo, modulo, lote),
        "real_fundos": filtrar_ubicacion(real_total, fundo, modulo, lote),
        "real": filtrar_ubicacion(real_total, fundo, modulo, lote),
        "r09": filtrar_ubicacion(r09_horizonte, fundo, modulo, lote),
        "r09_grafico": filtrar_ubicacion(_ventana_grafico(r09_total), fundo, modulo, lote),
        "hibrido_v2": filtrar_ubicacion(
            aplicar_horizonte(
                hibrido_v2_total,
                horizonte,
                inicio=inicio,
            ),
            fundo,
            modulo,
            lote,
        ),
        "nowcast": _nowcast_para_vista(estado, modelo_total, fundo, modulo, lote),
    }


@callback(
    Output("proy-modulo", "options"),
    Output("proy-modulo", "value"),
    Input("proy-fundo", "value"),
    Input("proy-limpiar", "n_clicks"),
    State("proy-modulo", "value"),
)
def _modulos(fundo, _limpiar, seleccion_actual):
    tabla = filtrar_ubicacion(_tabla_completa(), fundo=fundo)
    opciones = _opciones(tabla, "modulo")
    if ctx.triggered_id == "proy-limpiar":
        return opciones, _valor_si_cambio(seleccion_actual, [])
    seleccion = _seleccion_valida(seleccion_actual, opciones)
    return opciones, _valor_si_cambio(seleccion_actual, seleccion)


@callback(
    Output("proy-lote", "options"),
    Output("proy-lote", "value"),
    Input("proy-fundo", "value"),
    Input("proy-modulo", "value"),
    Input("proy-limpiar", "n_clicks"),
    State("proy-lote", "value"),
)
def _lotes(fundo, modulo, _limpiar, seleccion_actual):
    tabla = filtrar_ubicacion(_tabla_completa(), fundo=fundo, modulo=modulo)
    opciones = _opciones(tabla, "lote")
    if ctx.triggered_id == "proy-limpiar":
        return opciones, _valor_si_cambio(seleccion_actual, [])
    seleccion = _seleccion_valida(seleccion_actual, opciones)
    return opciones, _valor_si_cambio(seleccion_actual, seleccion)


@callback(
    Output("proy-fundo", "value"),
    Input("proy-limpiar", "n_clicks"),
    prevent_initial_call=True,
)
def _limpiar_filtros(n_clicks):
    if not n_clicks:
        raise PreventUpdate
    return []


@callback(
    Output("proy-contexto", "children"),
    Output("proy-resumen-principal", "children"),
    Output("proy-curva", "figure"),
    Output("proy-curvas-fundos", "figure"),
    Output("proy-plan-semanal", "children"),
    Input("proy-fundo", "value"),
    Input("proy-modulo", "value"),
    Input("proy-lote", "value"),
    Input("proy-horizonte", "value"),
    Input("proy-mostrar-r09", "value"),
    Input("proy-mostrar-nowcast", "value"),
    Input("proy-mostrar-hibrido-v2", "value"),
)
def _actualizar(fundo, modulo, lote, horizonte, mostrar_r09, mostrar_nowcast, mostrar_hibrido_v2):
    vista = _resolver_vista(fundo, modulo, lote, horizonte)
    modelo = vista["modelo"]
    modelo_fundos = vista["modelo_fundos"]
    real = vista["real"]
    real_fundos = vista["real_fundos"]
    r09 = vista["r09_grafico"]
    mostrar = "mostrar" in (mostrar_r09 or [])
    mostrar_cierre = "mostrar" in (mostrar_nowcast or [])
    mostrar_hibrido_v2_actual = "mostrar" in (mostrar_hibrido_v2 or [])

    return (
        contexto_corrida(vista["modelo_total"]),
        resumen_principal(modelo),
        curva_operativa_actual(
            vista["modelo_grafico"],
            r09,
            real,
            mostrar_r09=mostrar,
            nowcast=vista["nowcast"],
            mostrar_nowcast=mostrar_cierre,
            hibrido_v2=vista["hibrido_v2"],
            mostrar_hibrido_v2=mostrar_hibrido_v2_actual,
        ),
        curvas_por_fundo(modelo_fundos, real_fundos),
        tabla_plan(modelo),
    )


@callback(
    Output("proy-grid", "rowData"),
    Output("proy-resumen-tabla", "children"),
    Input("proy-vista-secundaria", "value"),
    Input("proy-fundo", "value"),
    Input("proy-modulo", "value"),
    Input("proy-lote", "value"),
    Input("proy-horizonte", "value"),
)
def _actualizar_detalle(vista_activa, fundo, modulo, lote, horizonte):
    if vista_activa != "detalle":
        return no_update, no_update
    modelo = _resolver_vista(fundo, modulo, lote, horizonte)["modelo"]
    filas = filas_grid(modelo)
    if modelo.empty:
        return [], html.Span("Sin registros para este filtro")
    resumen = f"{len(filas):,.0f} registros · {modelo['lote_id'].nunique():,.0f} lotes".replace(
        ",", "."
    )
    return filas, html.Span(resumen)


def _tarjeta_historica(rotulo: str, valor: str, detalle: str, tono: str = "") -> html.Div:
    return html.Div(
        [html.Span(rotulo), html.Strong(valor), html.Small(detalle)],
        className=f"aq-proy-history-card {tono}".strip(),
    )


def _metrica_pct(valor: object, *, signo: bool = False) -> str:
    numero = pd.to_numeric(pd.Series([valor]), errors="coerce").iloc[0]
    if pd.isna(numero):
        return "—"
    formato = f"{100 * float(numero):+,.1f} %" if signo else f"{100 * float(numero):,.1f} %"
    return formato.replace(",", ".")


def _metrica_kg(valor: object) -> str:
    numero = pd.to_numeric(pd.Series([valor]), errors="coerce").iloc[0]
    return "—" if pd.isna(numero) else f"{float(numero):,.0f} kg".replace(",", ".")


def _metrica_ratio(valor: object) -> str:
    numero = pd.to_numeric(pd.Series([valor]), errors="coerce").iloc[0]
    return "—" if pd.isna(numero) else f"{float(numero):.2f}"


@callback(
    Output("proy-hist-resumen", "children"),
    Output("proy-hist-grafico", "figure"),
    Output("proy-hist-estado", "children"),
    Output("proy-hist-campania", "options"),
    Output("proy-hist-campania", "value"),
    Output("proy-hist-serie", "options"),
    Output("proy-hist-serie", "value"),
    Output("proy-hist-ventana-wrap", "style"),
    Input("proy-vista-secundaria", "value"),
    Input("proy-hist-campania", "value"),
    Input("proy-hist-serie", "value"),
    Input("proy-hist-grano", "value"),
    Input("proy-hist-ventana", "value"),
    Input("proy-fundo", "value"),
    Input("proy-modulo", "value"),
    Input("proy-lote", "value"),
)
def _actualizar_historico(vista_activa, campanias, serie, grano, ventana, fundo, modulo, lote):
    if vista_activa != "precision":
        return (
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
        )
    estado_replay = estado_replay_proyeccion()
    replay_total = _filtrar_modelos_visibles(
        preparar_replay_historico(estado_replay.get("replay_detalle", pd.DataFrame()))
    )
    periodos_cerrados = _periodos_cerrados(estado_replay.get("real_detalle", pd.DataFrame()))
    replay_cerrado = _restringir_a_periodos_cerrados(replay_total, periodos_cerrados)
    campanias_disponibles = _campanias_evaluables(replay_cerrado)
    opciones_campania = [{"label": valor, "value": valor} for valor in campanias_disponibles]
    seleccion = _seleccionar_campania_concreta(campanias, campanias_disponibles)

    # Las series disponibles pertenecen a la campaña seleccionada. Construir este
    # selector con el conjunto global ofrecía, por ejemplo, R09 en C2025 aunque no
    # existiera una release R09 aprobada bajo el contrato C2025.
    replay_campania = replay_cerrado
    if seleccion is not None and "campania" in replay_campania:
        replay_campania = replay_campania[
            replay_campania["campania"].astype(str).eq(seleccion)
        ].copy()
    disponibles = set(replay_campania.get("modelo", pd.Series(dtype=str)).dropna().astype(str))
    codigos_modelo = [codigo for codigo in SERIES_HISTORICAS if codigo in disponibles]
    opciones_modelo = [
        {"label": SERIES_HISTORICAS[codigo], "value": codigo} for codigo in codigos_modelo
    ]
    serie_actual = _seleccionar_serie_visible(serie, codigos_modelo)
    etiqueta_serie = SERIES_HISTORICAS.get(str(serie_actual), str(serie_actual or "Proyección"))

    replay = alinear_replay_con_real_comun(
        replay_campania,
        estado_replay.get("real_detalle", pd.DataFrame()),
        str(serie_actual),
    )
    replay = _restringir_a_periodos_cerrados(replay, periodos_cerrados)
    grano_actual = str(grano or "semana")
    if seleccion is None:
        replay = replay.iloc[0:0].copy()
    replay = filtrar_ubicacion(replay, fundo, modulo, lote)
    estilo_ventana = (
        {"display": "block"} if (grano or "semana") == "semana" else {"display": "none"}
    )
    if (grano or "semana") == "semana":
        replay = limitar_ventana_semanal(replay, ventana or "12")
    agrupada = agrupar_replay_historico(replay, grano or "semana")
    metricas = metricas_replay_historico(agrupada, replay)
    figura = historico_y_desviacion(
        agrupada,
        nombre_serie=etiqueta_serie,
        granularidad=grano or "mes",
    )
    if agrupada.empty:
        estado = (
            "No existe un replay evaluable para esta combinación. "
            "La página no completa el histórico con datos futuros ni con una curva inventada."
        )
        return (
            [],
            figura,
            estado,
            opciones_campania,
            seleccion,
            opciones_modelo,
            serie_actual,
            estilo_ventana,
        )
    periodos = int(metricas["periodos"])
    semanas = int(metricas.get("semanas", 0))
    fechas_comparables = pd.to_datetime(
        replay.get("fecha_objetivo", pd.Series(dtype="datetime64[ns]")),
        errors="coerce",
    ).dropna()
    if fechas_comparables.empty:
        ventana_comparable = "ventana comparable certificada"
    else:
        inicio_comparable = fechas_comparables.min()
        fin_comparable = fechas_comparables.max() + pd.Timedelta(days=6)
        ventana_comparable = (
            f"ventana comparable {inicio_comparable:%d/%m/%Y}–{fin_comparable:%d/%m/%Y}"
        )
    if (grano or "semana") == "mes":
        detalle_periodos = (
            f"{periodos} mes{'es' if periodos != 1 else ''} evaluado"
            f"{'s' if periodos != 1 else ''} · "
            f"{semanas} semana{'s' if semanas != 1 else ''} · {ventana_comparable}"
        )
    elif (grano or "semana") == "campania":
        detalle_periodos = (
            f"Total de {seleccion} en {ventana_comparable} · "
            f"{semanas} semana{'s' if semanas != 1 else ''} evaluada"
            f"{'s' if semanas != 1 else ''}"
        )
    else:
        detalle_periodos = (
            f"{semanas} semana{'s' if semanas != 1 else ''} evaluada"
            f"{'s' if semanas != 1 else ''} · {ventana_comparable}"
        )
    rotulo_error = {
        "semana": "WAPE semanal",
        "mes": "WAPE mensual",
        "campania": "WAPE de campaña",
    }.get(grano_actual, "WAPE operativo")
    detalle_error = f"Error absoluto ponderado a nivel {grano_actual}"
    wape_operacional = float(metricas.get("wape_operacional", metricas.get("wape", float("nan"))))
    wape_condicionado = float(metricas.get("wape_condicionado", float("nan")))
    bias_pct = float(metricas.get("sesgo", float("nan")))
    cobertura = 100 * float(metricas.get("cobertura_volumen", float("nan")))
    cobertura_texto = _metrica_pct(metricas.get("cobertura_volumen"))
    precision_ok = (
        pd.notna(wape_operacional)
        and wape_operacional <= 0.15
        and pd.notna(bias_pct)
        and abs(bias_pct) <= 0.10
        and pd.notna(cobertura)
        and cobertura >= 90
    )
    resumen = [
        _tarjeta_historica(
            "Cosecha real evaluada",
            f"{metricas['real_kg']:,.0f} kg".replace(",", "."),
            detalle_periodos,
        ),
        _tarjeta_historica(
            "Proyección evaluada",
            f"{metricas['proyectado_kg']:,.0f} kg".replace(",", "."),
            etiqueta_serie,
            "is-model",
        ),
        _tarjeta_historica(
            rotulo_error,
            _metrica_pct(wape_operacional),
            detalle_error,
            "is-good" if precision_ok else "is-warn",
        ),
        _tarjeta_historica(
            "WAPE condicionado",
            _metrica_pct(wape_condicionado),
            "Solo filas con emisión del modelo",
            "is-model",
        ),
        _tarjeta_historica(
            "MAE / RMSE",
            f"{_metrica_kg(metricas.get('mae_kg'))} · {_metrica_kg(metricas.get('rmse_kg'))}",
            f"Error medio y error penalizado · {periodos} período(s)",
        ),
        _tarjeta_historica(
            "Bias",
            _metrica_pct(bias_pct, signo=True),
            "+ sobreestima · − subestima",
            "is-good" if pd.notna(bias_pct) and abs(bias_pct) <= 0.10 else "is-warn",
        ),
        _tarjeta_historica(
            "MASE / RMSSE",
            f"{_metrica_ratio(metricas.get('mase'))} · {_metrica_ratio(metricas.get('rmsse'))}",
            "< 1 mejora al Naive; — si no hay escala",
        ),
        _tarjeta_historica(
            "Cobertura de volumen",
            cobertura_texto,
            (
                f"{metricas.get('filas_emitidas', 0):,.0f} / "
                f"{metricas.get('filas_evaluadas', 0):,.0f} "
                "lote-semana emitidos"
            ).replace(",", "."),
            "is-good" if cobertura >= 90 else "is-warn",
        ),
    ]
    if str(serie_actual) == R09_REFERENCIA:
        if cobertura < 90:
            estado = (
                "R09 publicado: cada barra disponible usa una emisión anterior a la cosecha, "
                f"pero solo cubre {cobertura:.1f} % del volumen real de esta selección. "
                "No es comparable como campaña completa: la ausencia se marca como falta de "
                "cobertura, penaliza el WAPE operacional y se excluye del WAPE condicionado. "
                "R09 sigue siendo una referencia operativa, no un algoritmo."
            )
        else:
            estado = (
                "R09 publicado: cada barra usa una emisión anterior a la cosecha. "
                "Se muestra como referencia operativa; no es un algoritmo."
            )
    elif str(serie_actual) == "MacroLegacy_v1":
        wape_fino = 100 * float(metricas.get("wape_lote_semana", float("nan")))
        estado = (
            "Replay de la fórmula Python/ProySemanal con parámetros automáticos as-of. "
            f"El WAPE lote-semana es {wape_fino:.1f} %: el volumen agregado puede acercarse, "
            "pero la asignación entre lotes todavía no es suficientemente precisa."
        )
    else:
        estado = (
            f"{etiqueta_serie}: cada barra usa una predicción emitida antes de conocer la "
            "cosecha. El WAPE operativo penaliza las emisiones faltantes; el condicionado "
            "mide únicamente las filas emitidas. "
            f"MAE {_metrica_kg(metricas.get('mae_kg'))}, "
            f"RMSE {_metrica_kg(metricas.get('rmse_kg'))}, "
            f"Bias {_metrica_pct(bias_pct, signo=True)}, "
            f"MASE {_metrica_ratio(metricas.get('mase'))} y "
            f"RMSSE {_metrica_ratio(metricas.get('rmsse'))}. "
            "La explicación es predictiva, no causal."
        )
    return (
        resumen,
        figura,
        estado,
        opciones_campania,
        seleccion,
        opciones_modelo,
        serie_actual,
        estilo_ventana,
    )


@callback(
    Output("proy-six", "figure"),
    Output("proy-six-tabla", "children"),
    Input("proy-vista-secundaria", "value"),
)
def _actualizar_six(vista_activa):
    if vista_activa != "six":
        return no_update, no_update
    replay = estado_replay_proyeccion().get("replay", pd.DataFrame())
    matriz = matriz_six(replay)
    return figura_matriz_six(matriz), tabla_six(matriz)


@callback(
    Output("proy-descarga-csv", "data"),
    Input("proy-btn-csv", "n_clicks"),
    State("proy-fundo", "value"),
    State("proy-modulo", "value"),
    State("proy-lote", "value"),
    State("proy-horizonte", "value"),
    prevent_initial_call=True,
)
def _descargar_csv(n_clicks, fundo, modulo, lote, horizonte):
    if not n_clicks:
        raise PreventUpdate
    tabla = _resolver_vista(fundo, modulo, lote, horizonte)["modelo"]
    if tabla.empty:
        raise PreventUpdate
    nombre = f"aquanqa_plan_cosecha_{dt.date.today():%Y%m%d}.csv"
    return dcc.send_data_frame(vista_descarga(tabla).to_csv, nombre, index=False)


@callback(
    Output("proy-descarga-excel", "data"),
    Input("proy-btn-excel", "n_clicks"),
    State("proy-fundo", "value"),
    State("proy-modulo", "value"),
    State("proy-lote", "value"),
    State("proy-horizonte", "value"),
    prevent_initial_call=True,
)
def _descargar_excel(n_clicks, fundo, modulo, lote, horizonte):
    if not n_clicks:
        raise PreventUpdate
    vista = _resolver_vista(fundo, modulo, lote, horizonte)
    tabla = vista["modelo"]
    if tabla.empty:
        raise PreventUpdate
    resumen = resumen_fundos(tabla).rename(
        columns={
            "fundo": "Fundo",
            "proxima_semana_kg": "Próxima semana (kg)",
            "total_periodo_kg": "Total del período (kg)",
            "semana_pico": "Semana pico",
            "kg_pico": "Pico (kg)",
            "estado": "Estado",
        }
    )
    plan_exportacion = plan_semanal(tabla).rename(
        columns={
            "semana_inicio": "Inicio de semana",
            "total_kg": "Total (kg)",
            "semana_cierre": "Cierre de semana",
            "semana_iso": "Semana ISO",
            "rango_semana": "Período",
        }
    )
    hojas = [
        Hoja(
            nombre="Resumen",
            titulo="Resumen operativo por fundo",
            nota="Volumen consolidado para la selección descargada.",
            datos=resumen,
        ),
        Hoja(
            nombre="Plan semanal",
            titulo="Plan semanal de cosecha",
            nota=(
                "Volumen semanal calculado por ModeloOperativoActual_v1, réplica Python "
                "de ProySemanal con sus parámetros y calendario operativos."
            ),
            datos=plan_exportacion,
        ),
        Hoja(
            nombre="Detalle lote paña",
            titulo="Detalle por lote y paña",
            nota="Frutos, peso y kilos por lote y paña para uso operativo.",
            datos=vista_descarga(tabla),
        ),
        Hoja(
            nombre="Auditoría técnica",
            titulo="Trazabilidad de la corrida",
            nota=(
                "Detalle técnico de archivos y hashes. La hoja permanece oculta para no "
                "interferir con el uso diario; puede mostrarse en Excel para auditoría."
            ),
            datos=vista_trazabilidad(tabla),
            oculta=True,
        ),
    ]
    libro = construir_libro(
        hojas,
        meta_descarga(tabla, vista["estado"]),
        titulo_portada="Aqu Anqa · Plan semanal de cosecha",
        subtitulo_portada="Modelo Python · resumen operativo listo para campo",
    )
    nombre = f"aquanqa_plan_cosecha_{dt.date.today():%Y%m%d}.xlsx"
    return dcc.send_bytes(libro, nombre)


__all__ = [
    "_tabla_completa",
    "_modulos",
    "_lotes",
    "_actualizar",
    "_descargar_csv",
    "_descargar_excel",
]
