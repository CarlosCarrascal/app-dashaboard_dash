"""Descomposición de oleadas de cosecha — Método Bhattacharya (1967).

Filtros en cascada (Campaña → Fundo → Módulo → Turno → Lote → Paña) con datos
reales de PostgreSQL.  Tres oleadas gaussianas (P1 P2 P3) calibradas por SciPy,
decaimiento exponencial de calibre, proyección semanal de kilos, simulador
what-if en vivo.  Usa `ui.panel` / `ui.tarjetas` / `ui.parrafo` y la paleta
`aq-*` del dashboard para que todo sea visualmente consistente con la página
de Proyección.
"""

from __future__ import annotations

import io
from contextlib import suppress

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dcc, html

from analitica.nucleo.bhattacharya import (
    ParametrosBhattacharya,
    proyectar_curva_oleadas,
    simular_escenario,
)
from analitica.servicios.servicio_bhattacharya import (
    calibrar_todos_los_lotes,
    cargar_datos_desde_db,
    generar_proyeccion_empresa,
)
from components import ui

dash.register_page(
    __name__,
    path="/analitica/bhattacharya",
    name="Oleadas (Bhattacharya)",
    order=6,
    grupo="Plataforma analítica",
)

# ── Paleta ────────────────────────────────────────────────────────────────────
_P1 = "#2563eb"
_P2 = "#059669"
_P3 = "#7c3aed"
_TOT = "#111827"
_PESO = "#b45309"

# ── Caché ─────────────────────────────────────────────────────────────────────
_CACHE_PARAMS: dict[str, ParametrosBhattacharya] = {}
_CACHE_DF: pd.DataFrame | None = None


def _cargar_df(campania: str = "C2026") -> pd.DataFrame:
    global _CACHE_DF, _CACHE_PARAMS
    if _CACHE_DF is None or (_CACHE_DF["campania"].iloc[0] != campania if len(_CACHE_DF) else True):
        try:
            _CACHE_DF = cargar_datos_desde_db(campania=campania)
            _CACHE_PARAMS = {}
        except Exception:
            _CACHE_DF = pd.DataFrame()
    return _CACHE_DF


def _params(campania: str = "C2026") -> dict[str, ParametrosBhattacharya]:
    global _CACHE_PARAMS
    if not _CACHE_PARAMS:
        with suppress(Exception):
            _CACHE_PARAMS, _ = calibrar_todos_los_lotes(campania=campania)
    return _CACHE_PARAMS


# ── Layout ────────────────────────────────────────────────────────────────────


def layout() -> html.Div:
    df = _cargar_df("C2026")
    campanias = sorted(df["campania"].unique().tolist()) if not df.empty else ["C2026"]
    camp_opts = [{"label": c, "value": c} for c in campanias]
    camp_ini = "C2026" if "C2026" in campanias else (campanias[0] if campanias else "C2026")

    return html.Div(
        className="aq-projection-workspace",
        children=[
            ui.fuente_oficial(),
            # ── Hero ───────────────────────────────────────────────────────
            html.Header(
                className="aq-projection-hero",
                children=[
                    html.Div(
                        [
                            html.Span("DESCOMPOSICIÓN POBLACIONAL", className="aq-hero-eyebrow"),
                            html.H1("Oleadas de Cosecha — Bhattacharya", className="aq-hero-title"),
                            html.P(
                                "Calibración de 3 oleadas gaussianas (P1, P2, P3), "
                                "decaimiento exponencial de calibre y proyección "
                                "semanal de kilos por lote.",
                                className="aq-hero-copy",
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.Span(
                                "OLEADA 1",
                                className="aq-status-dot",
                                style={"color": _P1, "background": "#dbeafe"},
                            ),
                            html.Span("P1", className="aq-status-label"),
                            html.Span(
                                "OLEADA 2",
                                className="aq-status-dot",
                                style={"color": _P2, "background": "#d1fae5"},
                            ),
                            html.Span("P2", className="aq-status-label"),
                            html.Span(
                                "OLEADA 3",
                                className="aq-status-dot",
                                style={"color": _P3, "background": "#ede9fe"},
                            ),
                            html.Span("P3", className="aq-status-label"),
                        ],
                        className="aq-hero-status",
                    ),
                ],
            ),
            # ── Filtros ────────────────────────────────────────────────────
            ui.panel(
                "Selección de lote",
                html.Div(
                    className="aq-filter-grid aq-data-filters",
                    children=[
                        html.Div(
                            [
                                html.Label("Campaña", className=ui.SUBTITULO),
                                dcc.Dropdown(
                                    id="bhat-sel-campania",
                                    options=camp_opts,
                                    value=camp_ini,
                                    clearable=False,
                                ),
                            ]
                        ),
                        html.Div(
                            [
                                html.Label("Fundo", className=ui.SUBTITULO),
                                dcc.Dropdown(id="bhat-sel-fundo", placeholder="Todos"),
                            ]
                        ),
                        html.Div(
                            [
                                html.Label("Módulo", className=ui.SUBTITULO),
                                dcc.Dropdown(id="bhat-sel-modulo", placeholder="Todos"),
                            ]
                        ),
                        html.Div(
                            [
                                html.Label("Turno", className=ui.SUBTITULO),
                                dcc.Dropdown(id="bhat-sel-turno", placeholder="Todos"),
                            ]
                        ),
                        html.Div(
                            [
                                html.Label("Lote", className=ui.SUBTITULO),
                                dcc.Dropdown(
                                    id="bhat-sel-lote", placeholder="Seleccionar…", clearable=False
                                ),
                            ]
                        ),
                        html.Div(
                            [
                                html.Label("Hasta paña", className=ui.SUBTITULO),
                                dcc.Dropdown(id="bhat-sel-pana", placeholder="Todas"),
                            ]
                        ),
                    ],
                ),
                ayuda="Filtros en cascada: cada selector se actualiza según el anterior.",
            ),
            # ── KPIs ──────────────────────────────────────────────────────
            html.Div(id="bhat-kpis"),
            # ── Gráficos ──────────────────────────────────────────────────
            html.Div(
                className="aq-projection-grid",
                children=[
                    html.Main(
                        className="aq-projection-main",
                        children=[
                            ui.panel(
                                "Curvas de cosecha por oleada",
                                dcc.Graph(
                                    id="bhat-graf-oleadas",
                                    config={"displayModeBar": False},
                                ),
                                ayuda=(
                                    "Frutos estimados por planta. Las áreas sombreadas son "
                                    "las 3 oleadas individuales; la línea oscura es la suma."
                                ),
                            ),
                        ],
                    ),
                    html.Aside(
                        className="aq-projection-aside",
                        children=[
                            ui.panel(
                                "Decaimiento de calibre",
                                dcc.Graph(
                                    id="bhat-graf-calibre",
                                    config={"displayModeBar": False},
                                ),
                                aside=html.Span(
                                    id="bhat-badge-peso",
                                    className="aq-source-badge",
                                    children="a=? b=?",
                                ),
                                ayuda="Peso(t) = a · exp(b · t).  Pérdida de gramos por día.",
                            ),
                            ui.panel(
                                "Resumen del lote",
                                html.Div(id="bhat-resumen-lote"),
                                ayuda="Parámetros calibrados y datos del ajuste.",
                            ),
                        ],
                    ),
                ],
            ),
            # ── Simulador What-If ─────────────────────────────────────────
            ui.panel(
                "Simulador de oleadas y calibración experta",
                html.P(
                    "Mueve los controles para evaluar retrasos térmicos o "
                    "variaciones de carga. El gráfico y la tabla se recalculan "
                    "en vivo sin volver a calibrar.",
                    className="text-sm leading-relaxed text-slate-500",
                ),
                html.Div(
                    className="aq-data-filters",
                    children=[
                        html.Div(
                            className="grid gap-4 md:grid-cols-4",
                            children=[
                                _slider(
                                    "Pico oleada 1 (días)",
                                    "bhat-sl-dmu1",
                                    -25,
                                    25,
                                    1,
                                    0,
                                    {-20: "-20d", 0: "base", 20: "+20d"},
                                ),
                                _slider(
                                    "Retraso oleada 2 (días)",
                                    "bhat-sl-dmu2",
                                    -20,
                                    30,
                                    1,
                                    0,
                                    {-10: "-10d", 0: "base", 20: "+20d"},
                                ),
                                _slider(
                                    "Carga oleada 2 (%)",
                                    "bhat-sl-fn2",
                                    0.4,
                                    1.6,
                                    0.05,
                                    1.0,
                                    {0.5: "50%", 1.0: "100%", 1.5: "150%"},
                                ),
                                _slider(
                                    "Peso inicial baya (g)",
                                    "bhat-sl-pa",
                                    3.0,
                                    6.5,
                                    0.1,
                                    4.6,
                                    {3.5: "3.5g", 4.5: "4.5g", 5.5: "5.5g"},
                                ),
                            ],
                        ),
                    ],
                ),
                html.Div(
                    className="flex gap-3 mt-1",
                    children=[
                        html.Button(
                            "Restablecer valores",
                            id="bhat-btn-reset",
                            className="aq-btn aq-btn-ghost",
                        ),
                        html.Button(
                            "Exportar a Excel",
                            id="bhat-btn-exportar",
                            className="aq-btn aq-btn-primary",
                        ),
                        dcc.Download(id="bhat-download-excel"),
                    ],
                ),
                plegable=True,
                abierto=True,
                ayuda="Solo afecta la visualización, no modifica la calibración guardada.",
            ),
            # ── Tabla detallada ───────────────────────────────────────────
            ui.panel(
                "Proyección semanal detallada",
                html.Div(id="bhat-resumen-kg", className="text-xs text-slate-500"),
                html.Div(
                    id="bhat-tabla",
                    className="overflow-hidden rounded-xl border border-stone-200/80 bg-white",
                ),
                ayuda="Réplica automatizada de la hoja 2Pob_fit del Excel.",
            ),
        ],
    )


def _slider(nombre, control_id, mn, mx, step, val, marks):
    return html.Div(
        className="aq-scenario-control",
        children=[
            html.Label(nombre, className=ui.SUBTITULO),
            dcc.Slider(
                id=control_id,
                min=mn,
                max=mx,
                step=step,
                value=val,
                marks=marks,
                tooltip={"placement": "bottom"},
            ),
        ],
    )


# ── Cascada de filtros ────────────────────────────────────────────────────────


@callback(
    Output("bhat-sel-fundo", "options"),
    Output("bhat-sel-fundo", "value"),
    Output("bhat-sel-modulo", "options"),
    Output("bhat-sel-modulo", "value"),
    Output("bhat-sel-turno", "options"),
    Output("bhat-sel-turno", "value"),
    Output("bhat-sel-lote", "options"),
    Output("bhat-sel-lote", "value"),
    Output("bhat-sel-pana", "options"),
    Output("bhat-sel-pana", "value"),
    Input("bhat-sel-campania", "value"),
    Input("bhat-sel-fundo", "value"),
    Input("bhat-sel-modulo", "value"),
    Input("bhat-sel-turno", "value"),
    Input("bhat-sel-lote", "value"),
)
def _cascada(campania, fundo, modulo, turno, lote):
    df = _cargar_df(campania or "C2026")
    if df.empty:
        v = [{"label": "(sin datos)", "value": ""}]
        return v, None, v, None, v, None, v, None, v, None

    def _o(s):
        return [
            {"label": v, "value": v}
            for v in sorted(x for x in s.dropna().unique() if x and str(x) != "SIN_IDENTIFICAR")
        ]

    fo = _o(df["fundo"])
    d1 = df[df["fundo"] == fundo] if fundo else df
    mo = _o(d1["modulo"])
    d2 = d1[d1["modulo"] == modulo] if modulo else d1
    to = _o(d2["turno"])
    d3 = d2[d2["turno"] == turno] if turno else d2
    lo = _o(d3["lote"])
    ls = lote if lote and lote in [x["value"] for x in lo] else (lo[0]["value"] if lo else None)
    d4 = d3[d3["lote"] == ls] if ls else d3
    pv = sorted(int(p) for p in d4["pana"].dropna().unique() if p)
    po = [{"label": f"Paña {p}", "value": p} for p in pv]
    pm = pv[-1] if pv else None
    return fo, fundo, mo, modulo, to, turno, lo, ls, po, pm


# ── Callback principal ────────────────────────────────────────────────────────


@callback(
    Output("bhat-kpis", "children"),
    Output("bhat-graf-oleadas", "figure"),
    Output("bhat-graf-calibre", "figure"),
    Output("bhat-badge-peso", "children"),
    Output("bhat-resumen-lote", "children"),
    Output("bhat-tabla", "children"),
    Output("bhat-resumen-kg", "children"),
    Input("bhat-sel-lote", "value"),
    Input("bhat-sel-campania", "value"),
    Input("bhat-sel-pana", "value"),
    Input("bhat-sl-dmu1", "value"),
    Input("bhat-sl-dmu2", "value"),
    Input("bhat-sl-fn2", "value"),
    Input("bhat-sl-pa", "value"),
)
def _vista(lote, campania, pana_max, dmu1, dmu2, fn2, pa):
    pdict = _params(campania or "C2026")
    pb = pdict.get(lote) if lote else None
    if pb is None:
        aviso = ui.semaforo(
            "error",
            "**Fuente oficial · PostgreSQL.** No hay parámetros publicados para el lote "
            "seleccionado. No se muestran datos de demostración ni se usa Excel/Access.",
        )
        return aviso, go.Figure(), go.Figure(), "—", aviso, aviso, ""

    p = simular_escenario(
        pb,
        delta_mu1=float(dmu1 or 0),
        delta_mu2=float(dmu2 or 0),
        factor_N2=float(fn2 if fn2 is not None else 1.0),
        nuevo_peso_a=float(pa) if pa else None,
    )

    df = proyectar_curva_oleadas(p, t_start=140, t_end=430, step_days=7)

    # Datos observados
    raw = _cargar_df(campania or "C2026")
    obs = (
        raw[(raw["lote"] == lote) & (raw["pana"] <= pana_max)]
        if lote and pana_max and not raw.empty
        else pd.DataFrame()
    )

    kpis = ui.tarjetas(
        [
            (
                "Oleada 1 — Pico X₁",
                f"{p.mu1:.1f} d",
                f"σ₁ = {p.sigma1:.1f} d — N₁ = {p.N1:,.0f} frt/pl",
            ),
            (
                "Oleada 2 — Pico X₂",
                f"{p.mu2:.1f} d",
                f"σ₂ = {p.sigma2:.1f} d — N₂ = {p.N2:,.0f} frt/pl — +{p.mu2 - p.mu1:.0f} d",
            ),
            (
                "Oleada 3 — Pico X₃",
                f"{p.mu3:.1f} d",
                f"σ₃ = {p.sigma3:.1f} d — N₃ = {p.N3:,.0f} frt/pl — +{p.mu3 - p.mu2:.0f} d",
            ),
            (
                "Calibre a·e^(bt)",
                f"{p.peso_a:.2f} g",
                f"b = {p.peso_b:.5f} — {p.n_plantas:,} plantas",
            ),
        ]
    )

    fig_ol = _fig_oleadas(df, obs, p)
    fig_cal = _fig_calibre(df)
    badge = f"a = {p.peso_a:.2f}   b = {p.peso_b:.5f}"

    resumen = _resumen_lote(p, obs)
    tabla, kg_txt = _tabla(df)

    return kpis, fig_ol, fig_cal, badge, resumen, tabla, kg_txt


# ── Reset sliders ─────────────────────────────────────────────────────────────


@callback(
    Output("bhat-sl-dmu1", "value"),
    Output("bhat-sl-dmu2", "value"),
    Output("bhat-sl-fn2", "value"),
    Output("bhat-sl-pa", "value"),
    Input("bhat-btn-reset", "n_clicks"),
    State("bhat-sel-lote", "value"),
    prevent_initial_call=True,
)
def _reset(_, lote):
    p = _params().get(lote)
    return 0, 0, 1.0, round(p.peso_a, 1) if p else 4.6


# ── Exportar ──────────────────────────────────────────────────────────────────


@callback(
    Output("bhat-download-excel", "data"),
    Input("bhat-btn-exportar", "n_clicks"),
    State("bhat-sel-lote", "value"),
    State("bhat-sel-campania", "value"),
    prevent_initial_call=True,
)
def _exportar(_, lote, campania):
    pd_map = _params(campania or "C2026")
    p = pd_map.get(lote)
    if p is None:
        return None
    df = proyectar_curva_oleadas(p, t_start=140, t_end=430, step_days=7)
    _, df_par = calibrar_todos_los_lotes(campania=campania or "C2026")
    df_det, df_mat = generar_proyeccion_empresa(pd_map)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="2Pob_fit", index=False)
        df_mat.to_excel(w, sheet_name="Proyeccion_Semanal", index=False)
        df_par.to_excel(w, sheet_name="Parametros", index=False)
    buf.seek(0)
    return dcc.send_bytes(buf.getvalue(), f"Bhattacharya_{lote or 'empresa'}.xlsx")


# ── Gráficos ──────────────────────────────────────────────────────────────────


def _fig_oleadas(df, obs, p):
    fig = go.Figure()
    for col, name, color, fc in [
        ("FrtEst_p1", "Oleada 1 (P1)", _P1, "rgba(37,99,235,0.10)"),
        ("FrtEst_p2", "Oleada 2 (P2)", _P2, "rgba(5,150,105,0.10)"),
        ("FrtEst_p3", "Oleada 3 (P3)", _P3, "rgba(124,58,237,0.10)"),
    ]:
        fig.add_trace(
            go.Scatter(
                x=df["DDP"],
                y=df[col],
                name=name,
                fill="tozeroy",
                mode="lines",
                line=dict(color=color, width=1.8),
                fillcolor=fc,
                hovertemplate=f"<b>{name}</b><br>DDP: %{{x}} d<br>%{{y:.2f}} frt/pl<extra></extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=df["DDP"],
            y=df["TotalEst"],
            name="Total estimado",
            mode="lines",
            line=dict(color=_TOT, width=3),
            hovertemplate="<b>Total</b><br>DDP: %{x} d<br>%{y:.2f} frt/pl<extra></extra>",
        )
    )
    if not obs.empty and "t_dias" in obs and "frutos_obs" in obs:
        o = obs.dropna(subset=["t_dias", "frutos_obs"])
        if not o.empty:
            fig.add_trace(
                go.Scatter(
                    x=o["t_dias"].astype(float),
                    y=o["frutos_obs"].astype(float) / max(p.n_plantas, 1),
                    name="Pañas reales",
                    mode="markers",
                    marker=dict(color="#dc2626", size=8, symbol="circle-open", line=dict(width=2)),
                )
            )
    for mu, c in [(p.mu1, _P1), (p.mu2, _P2), (p.mu3, _P3)]:
        fig.add_vline(x=mu, line_dash="dot", line_color=c, line_width=1, opacity=0.45)

    fig.update_layout(
        template="plotly_white",
        height=370,
        margin=dict(l=35, r=15, t=25, b=35),
        xaxis_title="Días desde poda (DDP)",
        yaxis_title="Frutos / planta",
        legend=dict(orientation="h", y=1.12, x=0, font=dict(size=11)),
        hovermode="x unified",
    )
    return fig


def _fig_calibre(df):
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["DDP"],
            y=df["PesoMedio_g"],
            name="Peso baya (g)",
            mode="lines",
            line=dict(color=_PESO, width=2.5),
            hovertemplate="<b>Calibre</b><br>DDP: %{x} d<br>%{y:.2f} g<extra></extra>",
        )
    )
    fig.update_layout(
        template="plotly_white",
        height=250,
        margin=dict(l=35, r=15, t=15, b=35),
        xaxis_title="Días desde poda",
        yaxis_title="Gramos / baya",
        yaxis_range=[1.0, 7.0],
        hovermode="x unified",
    )
    return fig


# ── Resumen del lote ──────────────────────────────────────────────────────────


def _resumen_lote(p, obs):
    fecha = p.fecha_poda.strftime("%d/%m/%Y") if p.fecha_poda else "—"
    n_panas = len(obs) if not obs.empty else p.panas_observadas
    total_frt = p.N1 + p.N2 + p.N3
    items = [
        ("Lote", f"{p.lote}"),
        ("Fundo", f"{p.fundo or '—'}"),
        ("Módulo / Turno", f"{p.modulo or '—'} / {p.turno or '—'}"),
        ("Fecha de poda", fecha),
        ("Plantas", f"{p.n_plantas:,}"),
        ("Pañas observadas", f"{n_panas}"),
        ("Carga total", f"{total_frt:,.0f} frt/pl"),
        ("RMSE ajuste", f"{p.rmse_total:.2f}"),
    ]
    filas = [
        html.Tr(
            [
                html.Td(
                    k,
                    className=(
                        "py-1 pr-3 text-xs text-slate-400 font-medium "
                        "whitespace-nowrap align-top"
                    ),
                ),
                html.Td(v, className="py-1 text-xs font-mono text-slate-700"),
            ]
        )
        for k, v in items
    ]
    return html.Table(filas, className="w-full")


# ── Tabla semanal ─────────────────────────────────────────────────────────────


def _tabla(df):
    kg_total = df["Kg_Semanal_Total"].sum()
    txt = f"Total campaña estimado: {kg_total:,.0f} kg"

    cols = [
        ("DDP", ""),
        ("Fecha", ""),
        ("Sem.", ""),
        ("Frt P1", "text-right"),
        ("Frt P2", "text-right"),
        ("Frt P3", "text-right"),
        ("Total", "text-right"),
        ("Peso (g)", "text-right"),
        ("Kg sem.", "text-right"),
        ("Kg acum.", "text-right"),
    ]
    th_cls = "py-2 px-2.5 text-left whitespace-nowrap"
    encab = html.Thead(
        className=(
            "bg-stone-50 text-[0.65rem] font-semibold uppercase tracking-wide "
            "text-slate-500 sticky top-0 border-b border-stone-200 z-10"
        ),
        children=[html.Tr([html.Th(c, className=f"{th_cls} {a}") for c, a in cols])],
    )

    td_base = "py-1.5 px-2.5 font-mono text-[0.72rem]"
    filas = []
    for i, r in df.iterrows():
        bg = "" if i % 2 == 0 else "bg-stone-50/50"
        filas.append(
            html.Tr(
                className=f"{bg} border-b border-stone-100 hover:bg-blue-50/30 transition-colors",
                children=[
                    html.Td(str(r["DDP"]), className=f"{td_base} text-slate-800 font-semibold"),
                    html.Td(str(r["Fecha"]), className=f"{td_base} text-slate-600"),
                    html.Td(str(r["Semana"]), className=f"{td_base} text-slate-600"),
                    html.Td(
                        f"{r['FrtEst_p1']:.2f}",
                        className=f"{td_base} text-right",
                        style={"color": _P1},
                    ),
                    html.Td(
                        f"{r['FrtEst_p2']:.2f}",
                        className=f"{td_base} text-right",
                        style={"color": _P2},
                    ),
                    html.Td(
                        f"{r['FrtEst_p3']:.2f}",
                        className=f"{td_base} text-right",
                        style={"color": _P3},
                    ),
                    html.Td(
                        f"{r['TotalEst']:.2f}",
                        className=f"{td_base} text-right font-bold text-slate-900",
                    ),
                    html.Td(
                        f"{r['PesoMedio_g']:.2f}",
                        className=f"{td_base} text-right",
                        style={"color": _PESO},
                    ),
                    html.Td(
                        f"{r['Kg_Semanal_Total']:,.0f}",
                        className=f"{td_base} text-right font-bold text-slate-800",
                    ),
                    html.Td(
                        f"{r['Kg_Acumulados']:,.0f}",
                        className=f"{td_base} text-right text-slate-400",
                    ),
                ],
            )
        )

    tabla = html.Div(
        className="max-h-[440px] overflow-y-auto",
        children=[
            html.Table(
                className="w-full border-collapse",
                children=[encab, html.Tbody(filas)],
            )
        ],
    )
    return tabla, txt
