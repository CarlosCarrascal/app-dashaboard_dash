"""Relaciones de packing y sus paneles."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .estadistica import (
    _bh,
    _efecto_practico,
    _p_agrupado,
    _placebo_parcial,
    _residuos_controles,
)
from .panel import _agregar_semana, _clima_semanal

PREDICTORES_EXTERNOS = [
    "temp_min",
    "temp_max",
    "temp_media",
    "humedad",
    "dpv_kpa",
    "eto",
    "radiacion",
    "lluvia",
    "gdd_4_4",
    "lamina_mm",
    "agua_m3",
    "reposicion_pct",
]


def panel_packing(datos) -> pd.DataFrame:
    """Panel módulo-semana con calibre real, defectos y acidez junto al peso cosechado.

    **Por qué vive aparte del panel de lote.** El packing se registra por módulo, no por
    lote, y solo para 15 de los 26 módulos. Mezclarlo con el panel principal obligaría a
    repartir un calibre de módulo entre sus lotes, que es inventar una variación que nadie
    midió. Un bloque propio con su unidad de análisis declarada es más honesto y además
    permite decir con precisión a qué parte de la operación aplica cada conclusión.

    Lo que aporta a cambio: tres campañas de calibre medido en línea, frente a las dos
    fechas del censo de bayas de campo. Para todo lo que tenga que ver con el peso del
    fruto, esta es la mejor medición disponible.
    """
    packing = getattr(datos, "packing", pd.DataFrame())
    if packing is None or packing.empty or datos.cosecha.empty:
        return pd.DataFrame()

    p = packing.copy()
    p["fecha_semana"] = _agregar_semana(p, "fecha_cosecha").fecha_semana
    p["peso_kg"] = pd.to_numeric(p.peso_kg, errors="coerce")
    p["calibre_mm"] = pd.to_numeric(p.calibre_mm, errors="coerce")

    # El calibre se pondera por kilos: un lote de 3 t en calibre 20 pesa más en la media
    # que uno de 50 kg en calibre 14. Un promedio simple daría el mismo peso a los dos.
    p["calibre_por_kg"] = p.calibre_mm * p.peso_kg
    agregado = p.groupby(["modulo", "fecha_semana"], as_index=False).agg(
        kg_packing=("peso_kg", "sum"),
        kg_con_calibre=("calibre_por_kg", "sum"),
        calibres_distintos=("calibre", "nunique"),
    )
    agregado["calibre_medio_mm"] = agregado.kg_con_calibre / agregado.kg_packing.replace(0, np.nan)

    # Descarte y exportable: qué proporción del volumen se pierde por calidad.
    if "clase" in p:
        clase = p.assign(
            es_descarte=p.clase.astype(str).str.contains("descarte", case=False, na=False)
        )
        perdida = clase.groupby(["modulo", "fecha_semana"], as_index=False).apply(
            lambda g: pd.Series(
                {
                    "proporcion_descarte": (
                        g.loc[g.es_descarte, "peso_kg"].sum() / g.peso_kg.sum()
                        if g.peso_kg.sum() > 0
                        else np.nan
                    )
                }
            ),
            include_groups=False,
        )
        agregado = agregado.merge(perdida, on=["modulo", "fecha_semana"], how="left")

    for columna in ("acidez", "defecto"):
        if columna in p:
            valores = pd.to_numeric(p[columna], errors="coerce")
            if valores.notna().any():
                media = (
                    p.assign(**{columna: valores})
                    .groupby(["modulo", "fecha_semana"], as_index=False)[columna]
                    .mean()
                )
                agregado = agregado.merge(media, on=["modulo", "fecha_semana"], how="left")

    # Cosecha agregada al mismo grano, para poder relacionarla con el calibre.
    h = _agregar_semana(datos.cosecha)
    cosecha = h.groupby(["modulo", "fecha_semana"], as_index=False).agg(
        kg_cosecha=("kg", "sum"),
        peso_real_g=("peso_baya", "mean"),
        lotes=("lote_id", "nunique"),
    )
    # El área se toma una vez por lote, nunca sumando la columna del hecho: un lote aparece
    # en varias filas de cosecha dentro de la misma semana —un registro por día y turno— y
    # sumar `area_ha` contaba su superficie tantas veces como veces se cosechó. Inflaba 762
    # de los 1.017 grupos módulo-semana, hasta 2,67 veces, y hundía `kg_ha_modulo` en la
    # misma proporción. Es el defecto B-4 del ADR-0004, en el bloque de packing.
    area = (
        h.drop_duplicates(["modulo", "fecha_semana", "lote_id"])
        .groupby(["modulo", "fecha_semana"], as_index=False)
        .agg(area_ha=("area_ha", "sum"))
    )
    cosecha = cosecha.merge(area, on=["modulo", "fecha_semana"], how="left")
    cosecha["kg_ha_modulo"] = cosecha.kg_cosecha / cosecha.area_ha.replace(0, np.nan)

    panel = agregado.merge(cosecha, on=["modulo", "fecha_semana"], how="inner")

    # Clima de la semana, que es común a todos los módulos: se une por fecha.
    clima_semana, _ = _clima_semanal(datos.clima)
    if not clima_semana.empty:
        panel = panel.merge(clima_semana, on="fecha_semana", how="left")
    return panel.sort_values(["fecha_semana", "modulo"]).reset_index(drop=True)


def relaciones_packing(panel: pd.DataFrame, minimo_semanas: int = 12) -> pd.DataFrame:
    """Qué se relaciona con el calibre real y con la pérdida por descarte.

    Mismo tratamiento que la matriz general —controles de calendario y módulo, corrección
    por multiplicidad, placebo— pero sobre la unidad que corresponde a estos datos.
    """
    if panel.empty:
        return pd.DataFrame()

    respuestas = [
        c
        for c in ("calibre_medio_mm", "peso_real_g", "proporcion_descarte", "kg_ha_modulo")
        if c in panel and panel[c].notna().sum() > 30
    ]
    predictores = [
        c for c in (*PREDICTORES_EXTERNOS, "calibre_medio_mm", "proporcion_descarte") if c in panel
    ]
    orden = panel.sort_values(["modulo", "fecha_semana"]).copy()
    filas = []
    vistos: set[tuple[str, str]] = set()
    for respuesta in respuestas:
        for predictor in predictores:
            if predictor == respuesta:
                continue
            # Cuando las dos variables son respuestas del mismo bloque —calibre y descarte,
            # por ejemplo— cruzarlas en ambos sentidos duplica la misma correlación. Se
            # conserva un solo sentido, el alfabético, para que no aparezca dos veces.
            if predictor in respuestas and (respuesta, predictor) in vistos:
                continue
            vistos.add((predictor, respuesta))
            for rezago in range(0, 7):
                orden["x"] = orden.groupby("modulo")[predictor].shift(rezago)
                muestra = orden.dropna(subset=["x", respuesta, "fecha_semana"]).copy()
                muestra = muestra.rename(columns={respuesta: "y"})
                semanas = muestra.fecha_semana.nunique()
                if semanas < minimo_semanas or muestra.x.nunique() < 3 or muestra.y.nunique() < 3:
                    continue
                pearson, p_crudo = stats.pearsonr(muestra.x, muestra.y)
                if not np.isfinite(pearson):
                    continue
                residuos_x = _residuos_controles(muestra, "x")
                residuos_y = _residuos_controles(muestra, "y")
                parcial = float(np.corrcoef(residuos_x, residuos_y)[0, 1])
                efecto = _efecto_practico(muestra, residuos_x, residuos_y)
                # La significancia se calcula sobre la parcial —que es la que se publica— y
                # con errores agrupados. Antes salía del `pearsonr` crudo sobre todas las
                # filas: dos discrepancias a la vez, el coeficiente y el tamaño de muestra.
                p_valor, gl = _p_agrupado(
                    residuos_x, residuos_y, muestra[["fecha_semana", "modulo"]]
                )
                placebo = _placebo_parcial(orden, predictor, respuesta, rezago, "modulo", 25)
                filas.append(
                    {
                        "predictor": predictor,
                        "respuesta": respuesta,
                        "unidad": "modulo_semana",
                        "rezago_semanas": rezago,
                        "n": len(muestra),
                        "n_efectivo": int(semanas),
                        "grados_libertad": int(gl),
                        "modulos": int(muestra.modulo.nunique()),
                        "pearson": float(pearson),
                        "p_crudo_sin_agrupar": float(p_crudo),
                        "p_pearson": float(p_valor),
                        "correlacion_parcial": parcial,
                        "placebo_futuro": placebo,
                        **efecto,
                    }
                )

    salida = pd.DataFrame(filas)
    if salida.empty:
        return salida
    desfases = salida.groupby(["predictor", "respuesta"]).rezago_semanas.transform("size")
    salida["desfases_probados"] = desfases
    salida["p_seleccion_desfase"] = 1 - np.power(1 - salida.p_pearson.clip(0, 1), desfases)
    salida["p_ajustado_bh"] = _bh(salida.p_seleccion_desfase)
    salida["placebo_supera_estimacion"] = (
        salida.placebo_futuro.abs() > salida.correlacion_parcial.abs()
    ).fillna(False)
    salida["sobrevive"] = (
        (salida.p_ajustado_bh < 0.05)
        & ~salida.placebo_supera_estimacion
        & (salida.correlacion_parcial.abs() >= 0.1)
    )
    return salida.sort_values("p_ajustado_bh").reset_index(drop=True)


__all__ = ["panel_packing", "relaciones_packing"]
