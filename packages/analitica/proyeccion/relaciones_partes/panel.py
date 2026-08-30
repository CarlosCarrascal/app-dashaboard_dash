"""Construcción del panel de relaciones."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..compartido import lunes_semana
from ..ensamblaje import _auditoria_dataframe, _merge_auditado, _registrar_base


def _agregar_semana(tabla: pd.DataFrame, fecha: str = "fecha") -> pd.DataFrame:
    salida = tabla.copy()
    salida["fecha_semana"] = lunes_semana(salida[fecha])
    return salida


def _clima_semanal(clima: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if clima.empty:
        return pd.DataFrame(), pd.DataFrame()
    c = clima.copy()
    c["fecha"] = pd.to_datetime(c.fecha_hora).dt.normalize()
    diario = c.groupby("fecha", as_index=False).agg(
        temp_media=("temp", "mean"),
        temp_max=("temp_alta", "max"),
        temp_min=("temp_baja", "min"),
        humedad=("humedad", "mean"),
        radiacion=("rad_sol", "sum"),
        eto=("et_mm", "sum"),
        lluvia=("lluvia", "sum"),
    )
    diario["dpv_kpa"] = (
        0.6108
        * np.exp(17.27 * diario.temp_media / (diario.temp_media + 237.3))
        * (1 - diario.humedad.clip(0, 100) / 100)
    )
    for base, nombre in ((0.0, "gdd_0"), (4.4, "gdd_4_4"), (7.0, "gdd_7"), (8.0, "gdd_8")):
        diario[nombre] = (diario.temp_media - base).clip(lower=0)
    diario["fecha_semana"] = lunes_semana(diario.fecha)
    semanal = diario.groupby("fecha_semana", as_index=False).agg(
        temp_media=("temp_media", "mean"),
        temp_max=("temp_max", "max"),
        temp_min=("temp_min", "min"),
        humedad=("humedad", "mean"),
        dpv_kpa=("dpv_kpa", "mean"),
        radiacion=("radiacion", "sum"),
        eto=("eto", "sum"),
        lluvia=("lluvia", "sum"),
        gdd_0=("gdd_0", "sum"),
        gdd_4_4=("gdd_4_4", "sum"),
        gdd_7=("gdd_7", "sum"),
        gdd_8=("gdd_8", "sum"),
    )
    return semanal, diario


def construir_panel_relaciones(
    datos, *, devolver_auditoria: bool = False
) -> pd.DataFrame | tuple[pd.DataFrame, pd.DataFrame]:
    """Panel lote-semana con variables observadas; sin imputar censos inexistentes.

    Cuando ``devolver_auditoria`` es verdadero devuelve también una fila por unión. La
    opción es opt-in para no romper consumidores históricos que esperan solo el DataFrame.
    """
    auditoria: list[dict] = []
    h = _agregar_semana(datos.cosecha)
    cosecha = h.groupby(
        ["campania", "lote_id", "empresa", "fundo", "modulo", "lote", "fecha_semana"],
        dropna=False,
        as_index=False,
    ).agg(
        kg=("kg", "sum"),
        peso_real_g=("peso_baya", "mean"),
        plantas_cosechadas=("plantas_cosechadas", "max"),
        area_ha=("area_ha", "max"),
        plantas_maestro=("plantas_maestro", "max"),
    )
    cosecha["kg_ha"] = cosecha.kg / cosecha.area_ha.replace(0, np.nan)

    paneles = [("cosecha", cosecha)]
    if not datos.flores.empty:
        f = _agregar_semana(datos.flores)
        f = f.groupby(["lote_id", "fecha_semana"], as_index=False).agg(
            flores=("n_flores", "sum"),
            cuajo=("cuajo", "sum"),
            plantas_flores=("planta", "nunique"),
        )
        f["flores_por_planta_muestra"] = f.flores / f.plantas_flores.replace(0, np.nan)
        f["tasa_cuajo_observada"] = f.cuajo / f.flores.replace(0, np.nan)
        paneles.append(("flores", f))
    if not datos.estados.empty:
        e = _agregar_semana(datos.estados)
        e = e.groupby(["lote_id", "fecha_semana"], as_index=False).agg(
            **{f"e{i}": (f"e{i}", "sum") for i in range(1, 6)},
            plantas_estados=("planta", "nunique"),
        )
        total = e[[f"e{i}" for i in range(1, 6)]].sum(axis=1).replace(0, np.nan)
        e["frutos_por_planta_muestra"] = total / e.plantas_estados.replace(0, np.nan)
        for i in range(1, 6):
            e[f"prop_e{i}"] = e[f"e{i}"] / total
        e["indice_estado"] = sum(i * e[f"prop_e{i}"] for i in range(1, 6))
        paneles.append(("estados", e))
    if not datos.bayas.empty:
        b = _agregar_semana(datos.bayas)
        b = b.groupby(["lote_id", "fecha_semana"], as_index=False).agg(
            diametro_baya_mm=("diametro", "mean"), bayas_muestreadas=("diametro", "count")
        )
        paneles.append(("bayas", b))

    # Yemas: se cuentan en la misma evaluación que las flores y describen la carga antes de
    # que la flor exista. Una yema por abrir es una flor futura.
    if not datos.flores.empty and {"yemas_abiertas", "yemas_por_abrir"} <= set(datos.flores):
        y = _agregar_semana(datos.flores)
        y = y.groupby(["lote_id", "fecha_semana"], as_index=False).agg(
            yemas_abiertas=("yemas_abiertas", "sum"),
            yemas_por_abrir=("yemas_por_abrir", "sum"),
            plantas_yemas=("planta", "nunique"),
        )
        total_yemas = (y.yemas_abiertas + y.yemas_por_abrir).replace(0, np.nan)
        y["yemas_por_planta"] = total_yemas / y.plantas_yemas.replace(0, np.nan)
        y["proporcion_yemas_abiertas"] = y.yemas_abiertas / total_yemas
        paneles.append(
            (
                "yemas",
                y[["lote_id", "fecha_semana", "yemas_por_planta", "proporcion_yemas_abiertas"]],
            )
        )

    # Brotes: el primer censo del ciclo, anterior a las yemas.
    brotes = getattr(datos, "brotes", pd.DataFrame())
    if not brotes.empty:
        br = _agregar_semana(brotes)
        br = br.groupby(["lote_id", "fecha_semana"], as_index=False).agg(
            brotes_total=("brotes", "sum"), plantas_brotes=("planta", "nunique")
        )
        br["brotes_por_planta"] = br.brotes_total / br.plantas_brotes.replace(0, np.nan)
        paneles.append(("brotes", br[["lote_id", "fecha_semana", "brotes_por_planta"]]))

    # Ramas: la estructura que sostiene la carga. El corte en 5 mm separa las que llevan
    # fruto de las que no, así que su proporción describe la capacidad del lote.
    ramas = getattr(datos, "ramas", pd.DataFrame())
    if not ramas.empty:
        ra = _agregar_semana(ramas)
        ra = ra.groupby(["lote_id", "fecha_semana"], as_index=False).agg(
            ramas_menor5=("ramas_menor5", "sum"),
            ramas_mayor5=("ramas_mayor5", "sum"),
            diametro_rama_mm=("diametro", "mean"),
            plantas_ramas=("planta", "nunique"),
        )
        total_ramas = (ra.ramas_menor5 + ra.ramas_mayor5).replace(0, np.nan)
        ra["ramas_por_planta"] = total_ramas / ra.plantas_ramas.replace(0, np.nan)
        ra["proporcion_ramas_gruesas"] = ra.ramas_mayor5 / total_ramas
        paneles.append(
            (
                "ramas",
                ra[
                    [
                        "lote_id",
                        "fecha_semana",
                        "ramas_por_planta",
                        "proporcion_ramas_gruesas",
                        "diametro_rama_mm",
                    ]
                ],
            )
        )

    panel = paneles[0][1]
    grano_panel = ["lote_id", "fecha_semana"]
    _registrar_base(
        panel,
        auditoria=auditoria,
        nombre="cosecha_agregada",
        unidad="lote-semana",
        grano=grano_panel,
    )
    for nombre, otro in paneles[1:]:
        panel = _merge_auditado(
            panel,
            otro,
            auditoria=auditoria,
            nombre=f"cosecha_{nombre}",
            unidad="lote-semana",
            on=grano_panel,
            how="outer",
            validate="one_to_one",
            grano_salida=grano_panel,
        )
    if not datos.lotes.empty:
        identidad = datos.lotes.rename(columns={"n_plantas": "plantas_catalogo"})
        columnas = [
            "lote_id",
            "empresa",
            "fundo",
            "modulo",
            "lote",
            "variedad",
            "area_ha",
            "plantas_catalogo",
        ]
        existentes = [c for c in columnas if c in identidad]
        panel = _merge_auditado(
            panel,
            identidad[existentes],
            auditoria=auditoria,
            nombre="catalogo_lotes",
            unidad="lote-semana",
            on=["lote_id"],
            how="left",
            validate="many_to_one",
            grano_salida=grano_panel,
            suffixes=("", "_cat"),
        )
        for columna in ("empresa", "fundo", "modulo", "lote", "area_ha"):
            cat = f"{columna}_cat"
            if cat in panel:
                panel[columna] = panel.get(columna).fillna(panel[cat])
                panel = panel.drop(columns=cat)

    clima_semana, _ = _clima_semanal(datos.clima)
    if not clima_semana.empty:
        panel = _merge_auditado(
            panel,
            clima_semana,
            auditoria=auditoria,
            nombre="clima_semanal",
            unidad="lote-semana",
            on=["fecha_semana"],
            how="left",
            validate="many_to_one",
            grano_salida=grano_panel,
        )
    if not datos.riego.empty:
        r = _agregar_semana(datos.riego)
        r = r.groupby(["modulo_id", "fecha_semana"], as_index=False).agg(
            agua_m3=("agua_m3", "sum"),
            lamina_mm=("lamina_mm", "sum"),
            reposicion_pct=("reposicion_pct", "mean"),
            riego_estimado=("estimado", "max"),
        )
        # La tabla de lotes contractual no expone modulo_id; se recupera de riego mediante
        # la etiqueta del módulo. La clave tiene que incluir el fundo: «M01» existe en dos
        # fundos distintos, así que unir solo por `modulo` emparejaba cada lote con los dos
        # módulos homónimos y duplicaba 20.868 filas del panel —el 30 %—, inflando la
        # muestra de toda relación que tocara el riego.
        claves = [c for c in ("empresa", "fundo", "modulo") if c in datos.riego and c in panel]
        if not claves:
            raise ValueError("No hay una clave de negocio para relacionar riego con el panel.")
        mapa = datos.riego[[*claves, "modulo_id"]].drop_duplicates()
        ambiguos = mapa.groupby(claves).modulo_id.nunique()
        if (ambiguos > 1).any():
            raise ValueError(
                "La clave de módulo no identifica un modulo_id único: "
                f"{ambiguos[ambiguos > 1].index.tolist()[:5]}. Unir por ella duplicaría el panel."
            )
        panel = _merge_auditado(
            panel,
            mapa,
            auditoria=auditoria,
            nombre="riego_mapa_modulo",
            unidad="lote-semana",
            on=claves,
            how="left",
            validate="many_to_one",
            grano_salida=grano_panel,
        )
        panel = _merge_auditado(
            panel,
            r,
            auditoria=auditoria,
            nombre="riego_semanal",
            unidad="lote-semana",
            on=["modulo_id", "fecha_semana"],
            how="left",
            validate="many_to_one",
            grano_salida=grano_panel,
        )

    if "indice_estado" in panel:
        panel = panel.sort_values(["lote_id", "fecha_semana"])
        panel["velocidad_estado"] = panel.groupby("lote_id").indice_estado.diff()
    if {"plantas_catalogo", "frutos_por_planta_muestra", "peso_real_g"} <= set(panel):
        panel["kg_componentes_muestra"] = (
            panel.plantas_catalogo * panel.frutos_por_planta_muestra * panel.peso_real_g / 1000
        )
    panel = panel.sort_values(["fecha_semana", "lote_id"]).reset_index(drop=True)
    if devolver_auditoria:
        return panel, _auditoria_dataframe(auditoria)
    return panel


__all__ = ["construir_panel_relaciones"]
