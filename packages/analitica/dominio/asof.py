"""Construcción de variables que respeta la fecha de emisión."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analitica.dominio.compartido import fechas as _fechas

# Aliases públicos históricos: las primitivas viven en un módulo puro, pero la fachada
# ``asof`` sigue siendo el punto de importación documentado.
lunes_semana = _fechas.lunes_semana
ultimo_disponible = _fechas.ultimo_disponible


def agregar_fenologia(datos) -> dict[str, pd.DataFrame]:
    """Reduce censos al grano lote-fecha sin inventar extrapolaciones biológicas."""
    flores = datos.flores.copy()
    if not flores.empty:
        agregados = {
            "flores": ("n_flores", "sum"),
            "cuajo": ("cuajo", "sum"),
            "plantas_muestreadas": ("planta", "nunique"),
        }
        # Las yemas se cuentan en la misma evaluación que las flores y hasta ahora se
        # descartaban. Son la señal más temprana de la carga: una yema por abrir es una
        # flor futura, así que anticipan más que la propia floración.
        for columna in ("yemas_abiertas", "yemas_por_abrir"):
            if columna in flores:
                agregados[columna] = (columna, "sum")
        claves = ["lote_id", "fecha"]
        if "campania" in flores:
            claves.insert(0, "campania")
        flores = flores.groupby(claves, as_index=False).agg(**agregados)
        flores["tasa_cuajo_observada"] = flores.cuajo / flores.flores.replace(0, np.nan)
        if {"yemas_abiertas", "yemas_por_abrir"} <= set(flores):
            total_yemas = (flores.yemas_abiertas + flores.yemas_por_abrir).replace(0, np.nan)
            flores["proporcion_yemas_abiertas"] = flores.yemas_abiertas / total_yemas
            flores["yemas_por_planta"] = total_yemas / flores.plantas_muestreadas.replace(0, np.nan)

    estados = datos.estados.copy()
    if not estados.empty:
        claves = ["lote_id", "fecha"]
        if "campania" in estados:
            claves.insert(0, "campania")
        estados = estados.groupby(claves, as_index=False)[["e1", "e2", "e3", "e4", "e5"]].sum()
        total = estados[["e1", "e2", "e3", "e4", "e5"]].sum(axis=1).replace(0, np.nan)
        for estado in ("e1", "e2", "e3", "e4", "e5"):
            estados[f"prop_{estado}"] = estados[estado] / total
        estados["frutos_muestra"] = total
        estados["indice_estado"] = sum(i * estados[f"prop_e{i}"] for i in range(1, 6))

    bayas = datos.bayas.copy()
    if not bayas.empty:
        claves = ["lote_id", "fecha"]
        if "campania" in bayas:
            claves.insert(0, "campania")
        bayas = bayas.groupby(claves, as_index=False).agg(
            diametro_baya_mm=("diametro", "mean"),
            sd_diametro_baya_mm=("diametro", "std"),
            bayas_muestreadas=("diametro", "count"),
        )

    # Brotes: el primer censo del ciclo, anterior incluso a las yemas.
    #
    # Solo se usa el conteo. Las columnas de grado de desarrollo `des1..des3` existen en el
    # origen pero están vacías —comprobado el 2026-08-19: `des1` tiene 240 valores de 3.385
    # registros y `des2`/`des3` cinco entre las dos—, así que agregarlas produciría una
    # variable con 93 % de huecos que no informa de nada. Si algún día se llenan, se
    # incorporan acá.
    brotes = getattr(datos, "brotes", pd.DataFrame()).copy()
    if not brotes.empty:
        claves = ["lote_id", "fecha"]
        if "campania" in brotes:
            claves.insert(0, "campania")
        brotes = brotes.groupby(claves, as_index=False).agg(
            brotes_total=("brotes", "sum"),
            plantas_brotes=("planta", "nunique"),
        )
        brotes["brotes_por_planta"] = brotes.brotes_total / brotes.plantas_brotes.replace(0, np.nan)

    # Ramas: la estructura sobre la que se apoya toda la carga. El grosor distingue las que
    # sostienen fruto de las que no, y por eso se cuentan por separado a partir de 5 mm.
    ramas = getattr(datos, "ramas", pd.DataFrame()).copy()
    if not ramas.empty:
        agregados = {"plantas_ramas": ("planta", "nunique")}
        for columna in ("ramas_menor5", "ramas_mayor5", "nro_rama", "diametro"):
            if columna in ramas:
                agregados[columna] = (columna, "mean" if columna == "diametro" else "sum")
        claves = ["lote_id", "fecha"]
        if "campania" in ramas:
            claves.insert(0, "campania")
        ramas = ramas.groupby(claves, as_index=False).agg(**agregados)
        if "diametro" in ramas:
            ramas = ramas.rename(columns={"diametro": "diametro_rama_mm"})
        if {"ramas_menor5", "ramas_mayor5"} <= set(ramas):
            total = (ramas.ramas_menor5 + ramas.ramas_mayor5).replace(0, np.nan)
            ramas["ramas_por_planta"] = total / ramas.plantas_ramas.replace(0, np.nan)
            ramas["proporcion_ramas_gruesas"] = ramas.ramas_mayor5 / total

    return {
        "flores": flores,
        "estados": estados,
        "bayas": bayas,
        "brotes": brotes,
        "ramas": ramas,
    }


def enriquecer_asof(objetivos: pd.DataFrame, datos) -> pd.DataFrame:
    """Añade censos, poda y clima acumulado conocidos al emitir el forecast."""
    panel = objetivos.copy()
    agregados = agregar_fenologia(datos)
    for nombre, columnas in (
        # El orden sigue el ciclo del cultivo: rama, brote, yema, flor, cuajado, fruto.
        ("ramas", ["ramas_por_planta", "proporcion_ramas_gruesas", "diametro_rama_mm"]),
        ("brotes", ["brotes_por_planta"]),
        (
            "flores",
            [
                "flores",
                "cuajo",
                "plantas_muestreadas",
                "tasa_cuajo_observada",
                "yemas_por_planta",
                "proporcion_yemas_abiertas",
            ],
        ),
        ("estados", ["frutos_muestra", "indice_estado", *[f"prop_e{i}" for i in range(1, 6)]]),
        ("bayas", ["diametro_baya_mm", "sd_diametro_baya_mm", "bayas_muestreadas"]),
    ):
        tabla = agregados[nombre]
        # Solo se piden las columnas que ese censo trajo de verdad. Una evaluación puede no
        # registrar yemas, o un lote no tener censo de ramas, y eso no debe tumbar el panel
        # entero: la variable simplemente no existe para esas filas.
        presentes = [c for c in columnas if c in tabla]
        if not presentes:
            continue
        entidades = (
            ["campania", "lote_id"]
            if {"campania", "lote_id"} <= set(panel) and {"campania", "lote_id"} <= set(tabla)
            else "lote_id"
        )
        panel = ultimo_disponible(panel, tabla, presentes, entidad=entidades)
        panel = panel.rename(columns={"fecha_observada": f"fecha_{nombre}"})

    poda = datos.poda.copy()
    if not poda.empty:
        poda = poda.sort_values("fecha_inicio").drop_duplicates(
            ["lote_id", "campania"], keep="last"
        )
        panel = panel.merge(
            poda[["lote_id", "campania", "fecha_inicio"]].rename(
                columns={"fecha_inicio": "fecha_poda"}
            ),
            on=["lote_id", "campania"],
            how="left",
        )
        panel["dias_desde_poda"] = (
            pd.to_datetime(panel.fecha_emision) - pd.to_datetime(panel.fecha_poda)
        ).dt.days
        panel.loc[panel.fecha_poda > panel.fecha_emision, ["fecha_poda", "dias_desde_poda"]] = [
            pd.NaT,
            np.nan,
        ]

    clima = datos.clima.copy()
    if not clima.empty:
        clima["fecha"] = pd.to_datetime(clima.fecha_hora).dt.normalize()
        diario = clima.groupby("fecha", as_index=False).agg(
            temp_media=("temp", "mean"),
            temp_max=("temp_alta", "max"),
            temp_min=("temp_baja", "min"),
            humedad=("humedad", "mean"),
            radiacion=("rad_sol", "sum"),
            eto=("et_mm", "sum"),
            lluvia=("lluvia", "sum"),
        )
        # DPV y acumulación térmica se derivan con la información cerrada del día. Se
        # mantienen las cuatro bases publicadas como candidatas; el modelo no asume que
        # 4,4 °C sea universal para Sekoya Pop–Trujillo.
        presion_saturacion = 0.6108 * np.exp(
            17.27 * diario.temp_media / (diario.temp_media + 237.3)
        )
        diario["dpv_kpa"] = presion_saturacion * (1 - diario.humedad / 100).clip(lower=0)
        for base in (0.0, 4.4, 7.0, 8.0):
            etiqueta = str(base).replace(".", "_")
            diario[f"gdd_{etiqueta}"] = (diario.temp_media - base).clip(lower=0)
        # El clima es común a los módulos. Cada fila solo acumula los 7/28 días anteriores
        # a la emisión; nunca usa el clima de la semana objetivo futura.
        diario = diario.set_index("fecha").sort_index()
        for ventana in (7, 28):
            rodante = diario.rolling(f"{ventana}D", closed="both").agg(
                {
                    "temp_media": "mean",
                    "temp_max": "max",
                    "temp_min": "min",
                    "humedad": "mean",
                    "dpv_kpa": "mean",
                    "radiacion": "sum",
                    "eto": "sum",
                    "lluvia": "sum",
                    "gdd_0_0": "sum",
                    "gdd_4_4": "sum",
                    "gdd_7_0": "sum",
                    "gdd_8_0": "sum",
                }
            )
            rodante.columns = [f"{c}_{ventana}d" for c in rodante.columns]
            rodante = rodante.reset_index().rename(columns={"fecha": "fecha_emision"})
            panel = panel.merge(rodante, on="fecha_emision", how="left")

    # El riego está registrado por módulo, no por lote. Se incorpora como señal de módulo
    # con la advertencia implícita de que varias parcelas comparten el mismo tratamiento.
    # Nunca se proyecta riego futuro: solo se acumula hasta la fecha de emisión.
    riego = getattr(datos, "riego", pd.DataFrame()).copy()
    if not riego.empty and {"modulo", "fecha"} <= set(riego):
        riego["fecha"] = pd.to_datetime(riego.fecha, errors="coerce").dt.normalize()
        diario_riego = riego.groupby(["modulo", "fecha"], as_index=False).agg(
            riego_agua_m3=("agua_m3", "sum"),
            riego_lamina_mm=("lamina_mm", "sum"),
            riego_reposicion_pct=("reposicion_pct", "mean"),
        )
        acumulados_por_ventana = []
        for ventana in (7, 28):
            acumulados = []
            for modulo, grupo in diario_riego.groupby("modulo", dropna=False):
                serie = grupo.set_index("fecha").sort_index()
                rodante = serie.rolling(f"{ventana}D", closed="both").agg(
                    {
                        "riego_agua_m3": "sum",
                        "riego_lamina_mm": "sum",
                        "riego_reposicion_pct": "mean",
                    }
                )
                rodante = rodante.reset_index()
                rodante["modulo"] = modulo
                rodante["fecha_emision"] = rodante.pop("fecha")
                rodante = rodante.rename(
                    columns={
                        c: f"{c}_{ventana}d"
                        for c in ("riego_agua_m3", "riego_lamina_mm", "riego_reposicion_pct")
                    }
                )
                acumulados.append(rodante)
            if acumulados:
                acumulados_por_ventana.append(pd.concat(acumulados, ignore_index=True))
        if acumulados_por_ventana:
            riego_asof = acumulados_por_ventana[0]
            for acumulado in acumulados_por_ventana[1:]:
                riego_asof = riego_asof.merge(
                    acumulado, on=["modulo", "fecha_emision"], how="outer", validate="1:1"
                )
            panel = panel.merge(riego_asof, on=["modulo", "fecha_emision"], how="left")
    return panel


def detectar_fuga(panel: pd.DataFrame) -> pd.DataFrame:
    """Devuelve una fila por campo fechado que viola la semántica as-of."""
    violaciones = []
    for columna in ("fecha_flores", "fecha_estados", "fecha_bayas", "fecha_poda"):
        if columna not in panel:
            continue
        mascara = pd.to_datetime(panel[columna], errors="coerce") > pd.to_datetime(
            panel["fecha_emision"], errors="coerce"
        )
        if mascara.any():
            violaciones.append({"campo": columna, "afectados": int(mascara.sum())})
    return pd.DataFrame(violaciones, columns=["campo", "afectados"])
