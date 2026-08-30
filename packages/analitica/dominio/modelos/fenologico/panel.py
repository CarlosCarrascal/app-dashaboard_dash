"""Construcción, enriquecimiento as-of y auditoría del panel fenológico."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analitica.dominio.asof import detectar_fuga, enriquecer_asof
from analitica.dominio.compartido import lunes_semana, ultimo_disponible
from analitica.dominio.modelos.fenologico.especificacion import FEATURES_HISTORIAL
from analitica.dominio.versiones import banda_horizonte


def normalizar_emisiones(emisiones: pd.DataFrame, campania_defecto: str) -> pd.DataFrame:
    if emisiones.empty:
        return emisiones
    salida = emisiones.copy()
    if "campania" not in salida:
        salida["campania"] = campania_defecto
    salida["campania"] = salida.campania.fillna(campania_defecto).astype(str)
    salida["fecha_emision"] = pd.to_datetime(salida.fecha_emision, errors="coerce").dt.normalize()
    return salida.dropna(subset=["fecha_emision"]).drop_duplicates(["campania", "fecha_emision"])


def cosecha_real_semanal(datos) -> pd.DataFrame:
    """Cosecha observada por lote-semana; no usa ningún componente publicado por R09."""

    cosecha = datos.cosecha.copy()
    requeridas = {"lote_id", "fecha", "kg"}
    if cosecha.empty or requeridas - set(cosecha):
        return pd.DataFrame()
    cosecha["fecha_objetivo"] = lunes_semana(cosecha.fecha)
    cosecha["kg"] = pd.to_numeric(cosecha.kg, errors="coerce").fillna(0).clip(lower=0)
    cosecha["peso_baya"] = pd.to_numeric(
        cosecha.get("peso_baya", pd.Series(np.nan, index=cosecha.index)), errors="coerce"
    )
    cosecha["plantas_cosechadas"] = pd.to_numeric(
        cosecha.get("plantas_cosechadas", pd.Series(np.nan, index=cosecha.index)),
        errors="coerce",
    )
    cosecha["_kg_con_peso"] = cosecha.kg.where(cosecha.peso_baya.gt(0), 0)
    cosecha["_peso_x_kg"] = cosecha.peso_baya.fillna(0) * cosecha._kg_con_peso
    claves = ["campania", "lote_id", "fecha_objetivo"]
    reales = cosecha.groupby(claves, as_index=False).agg(
        real_kg=("kg", "sum"),
        _peso_x_kg=("_peso_x_kg", "sum"),
        _kg_con_peso=("_kg_con_peso", "sum"),
        plantas_reales=("plantas_cosechadas", "max"),
        pasada_real=("pana", "max") if "pana" in cosecha else ("kg", "size"),
    )
    reales["peso_real_g"] = reales._peso_x_kg / reales._kg_con_peso.replace(0, np.nan)
    lotes = datos.lotes.copy()
    if not lotes.empty and {"lote_id", "n_plantas"} <= set(lotes):
        reales = reales.merge(
            lotes[["lote_id", "n_plantas"]].drop_duplicates("lote_id"),
            on="lote_id",
            how="left",
            validate="m:1",
        )
        reales["plantas_catalogo"] = pd.to_numeric(reales.n_plantas, errors="coerce")
    else:
        reales["plantas_catalogo"] = np.nan
    reales["plantas_base"] = reales.plantas_catalogo.fillna(reales.plantas_reales)
    reales["frutos_reales_por_planta_catalogo"] = (
        reales.real_kg * 1000 / (reales.plantas_base * reales.peso_real_g).replace(0, np.nan)
    )
    return reales.drop(columns=["_peso_x_kg", "_kg_con_peso", "n_plantas"], errors="ignore")


def campania_mas_reciente(datos) -> str:
    candidatas = []
    for tabla in (datos.cosecha, datos.poda):
        if not tabla.empty and "campania" in tabla:
            candidatas.extend(tabla.campania.dropna().astype(str).tolist())
    return sorted(candidatas)[-1] if candidatas else "NO_DEFINIDA"


def emisiones_historial(
    datos,
    emisiones: pd.DataFrame,
    *,
    campania_objetivo: str,
    fecha_corte: pd.Timestamp,
) -> pd.DataFrame:
    """Añade emisiones sintéticas de campañas anteriores para entrenar el modelo."""

    existentes = set(
        zip(
            emisiones.campania.astype(str),
            pd.to_datetime(emisiones.fecha_emision).dt.normalize(),
            strict=True,
        )
    )
    campanias = set()
    for tabla in (datos.cosecha, datos.poda):
        if not tabla.empty and "campania" in tabla:
            campanias.update(tabla.campania.dropna().astype(str))

    filas: list[dict[str, object]] = []
    for campania in sorted(campanias):
        if campania == str(campania_objetivo):
            continue
        cosecha = datos.cosecha[datos.cosecha.campania.astype(str).eq(campania)]
        poda = datos.poda[datos.poda.campania.astype(str).eq(campania)]
        fechas = []
        if not poda.empty and "fecha_inicio" in poda:
            fechas.extend(pd.to_datetime(poda.fecha_inicio, errors="coerce").dropna().tolist())
        if not cosecha.empty and "fecha" in cosecha:
            fechas.extend(pd.to_datetime(cosecha.fecha, errors="coerce").dropna().tolist())
        if not fechas:
            continue
        inicio = min(fechas).normalize() + pd.Timedelta(weeks=6)
        fin = min(max(fechas).normalize() + pd.Timedelta(weeks=2), fecha_corte)
        if fin < inicio:
            continue
        # Ocho a doce snapshots por campaña son suficientes para representar el historial
        # cerrado; una emisión semanal de cada campaña duplicaría miles de lotes-semana sin
        # aportar observaciones nuevas al ajuste.
        for fecha in pd.date_range(inicio, fin, freq="4W-MON"):
            clave = (campania, pd.Timestamp(fecha).normalize())
            if clave not in existentes:
                filas.append({"campania": campania, "fecha_emision": fecha})
    if not filas:
        return emisiones
    return pd.concat([emisiones, pd.DataFrame(filas)], ignore_index=True).drop_duplicates(
        ["campania", "fecha_emision"]
    )


def agregar_historial_asof(panel: pd.DataFrame, reales: pd.DataFrame) -> pd.DataFrame:
    """Calcula volumen histórico del lote estrictamente anterior a cada emisión."""

    salida = panel.copy()
    for columna in FEATURES_HISTORIAL:
        salida[columna] = np.nan
    if reales.empty:
        return salida

    historico = reales.copy()
    historico["fecha_objetivo"] = pd.to_datetime(historico.fecha_objetivo, errors="coerce")
    historico["real_kg"] = pd.to_numeric(historico.real_kg, errors="coerce").fillna(0).clip(lower=0)
    historico["pasada_real"] = pd.to_numeric(historico.pasada_real, errors="coerce")
    historico = historico.sort_values(["campania", "lote_id", "fecha_objetivo"])

    # El bucle es por lote y campaña para evitar un merge_asof global que pueda mezclar
    # campañas cuando el mismo lote físico aparece en más de un año.
    for (campania, lote_id), grupo in historico.groupby(["campania", "lote_id"], sort=False):
        indices = salida.index[
            salida.campania.astype(str).eq(str(campania)) & salida.lote_id.eq(lote_id)
        ]
        if len(indices) == 0:
            continue
        grupo = grupo.sort_values("fecha_objetivo")
        fechas = grupo.fecha_objetivo.to_numpy(dtype="datetime64[ns]")
        kg = grupo.real_kg.to_numpy(float)
        pasada = grupo.pasada_real.to_numpy(float)
        acumulado = np.cumsum(kg)
        emisiones = (
            pd.to_datetime(salida.loc[indices, "fecha_emision"])
            .dt.normalize()
            .to_numpy(dtype="datetime64[ns]")
        )
        posiciones = np.searchsorted(fechas, emisiones, side="left") - 1
        valido = posiciones >= 0
        if not valido.any():
            continue
        posiciones_seguras = np.maximum(posiciones, 0)
        valores = salida.loc[indices].copy()
        valores.loc[valido, "kg_acumulado_asof"] = acumulado[posiciones_seguras[valido]]
        valores.loc[valido, "kg_ultima_cosecha_asof"] = kg[posiciones_seguras[valido]]
        valores.loc[valido, "pasada_ultima_asof"] = pasada[posiciones_seguras[valido]]
        semanas = []
        for posicion, fecha_emision in zip(posiciones, emisiones, strict=True):
            if posicion < 0:
                semanas.append(0.0)
                continue
            limite = pd.Timestamp(fecha_emision) - pd.Timedelta(weeks=4)
            semanas.append(
                float(
                    kg[
                        (fechas < np.datetime64(fecha_emision)) & (fechas > np.datetime64(limite))
                    ].sum()
                )
            )
        valores.loc[:, "kg_ultimas_4_semanas_asof"] = semanas
        valores.loc[:, "semanas_cosecha_asof"] = [
            max(0, int(posicion + 1)) for posicion in posiciones
        ]
        salida.loc[indices, FEATURES_HISTORIAL] = valores[FEATURES_HISTORIAL].to_numpy()
    return salida


def construir_panel_fenologico(
    datos,
    emisiones: pd.DataFrame,
    *,
    horizonte_semanas: int = 10,
) -> pd.DataFrame:
    """Rejilla completa independiente de R09 y enriquecida con información as-of."""

    if not 1 <= horizonte_semanas <= 10:
        raise ValueError("FenologicoComponentes_v1 admite horizontes de 1 a 10 semanas")
    lotes = datos.lotes.copy()
    requeridas_lote = {"lote_id", "n_plantas"}
    if lotes.empty or requeridas_lote - set(lotes):
        raise ValueError("El modelo fenológico necesita dim.lote con lote_id y n_plantas")
    campania_defecto = campania_mas_reciente(datos)
    emisiones = normalizar_emisiones(emisiones, campania_defecto)
    if emisiones.empty:
        raise ValueError("No hay fechas de emisión para construir el panel fenológico")

    atributos = [
        c
        for c in (
            "lote_id",
            "empresa",
            "fundo",
            "modulo",
            "lote",
            "variedad",
            "area_ha",
            "n_plantas",
            "fecha_siembra",
        )
        if c in lotes
    ]
    lotes = lotes[atributos].drop_duplicates("lote_id")
    lotes["n_plantas"] = pd.to_numeric(lotes.n_plantas, errors="coerce")
    lotes = lotes[lotes.n_plantas.gt(0)].copy()

    # Evita convertir lotes sin ninguna señal de actividad en miles de ceros artificiales.
    # La actividad se resuelve por campaña: un lote que existe en C2026 no debe crear un
    # cero de C2023 solo porque comparte el mismo identificador físico.
    activos_campania: dict[str, set] = {}
    for tabla in (datos.cosecha, datos.poda):
        if tabla.empty or not {"campania", "lote_id"} <= set(tabla):
            continue
        for campania, grupo in tabla.groupby(tabla.campania.astype(str)):
            activos_campania.setdefault(campania, set()).update(grupo.lote_id.dropna())
    partes = []
    for campania, emisiones_campania in emisiones.groupby("campania", sort=False):
        lotes_campania = lotes
        activos = activos_campania.get(str(campania), set())
        if activos:
            lotes_campania = lotes[lotes.lote_id.isin(activos)].copy()
        partes.append(emisiones_campania.merge(lotes_campania, how="cross"))
    base = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    horizontes = pd.DataFrame({"horizonte_semanas": range(1, horizonte_semanas + 1)})
    panel = base.merge(horizontes, how="cross")
    # La operación compara y agenda por semana agronómica (lunes), no por el día de
    # ejecución. Una emisión del jueves 20/08 debe proyectar la semana del lunes 24/08;
    # conservar el jueves generaría universos artificialmente distintos frente a R09.
    panel["fecha_objetivo"] = lunes_semana(panel.fecha_emision) + pd.to_timedelta(
        panel.horizonte_semanas * 7, unit="D"
    )
    panel["calendario_fuente"] = "rejilla_lotes_independiente_de_R09"
    panel["banda_horizonte"] = panel.horizonte_semanas.map(banda_horizonte)
    panel["plantas"] = panel.n_plantas
    semana = panel.fecha_objetivo.dt.isocalendar().week.astype(float)
    panel["semana_objetivo_sin"] = np.sin(2 * np.pi * semana / 52.18)
    panel["semana_objetivo_cos"] = np.cos(2 * np.pi * semana / 52.18)

    reales = cosecha_real_semanal(datos)
    if reales.empty:
        raise ValueError("No hay cosecha real con la que entrenar FenologicoComponentes_v1")
    claves = ["campania", "lote_id", "fecha_objetivo"]
    panel = panel.merge(reales, on=claves, how="left", validate="m:1")
    ultima_real = pd.to_datetime(reales.fecha_objetivo).max()
    resuelta = panel.fecha_objetivo <= ultima_real
    panel.loc[resuelta, "real_kg"] = panel.loc[resuelta, "real_kg"].fillna(0.0)
    panel["ocurre_cosecha"] = np.where(
        panel.real_kg.notna(), panel.real_kg.gt(0).astype(float), np.nan
    )

    panel = enriquecer_asof(panel, datos)
    historico = reales.rename(columns={"fecha_objetivo": "fecha_real"})
    columnas_hist = [
        "frutos_reales_por_planta_catalogo",
        "peso_real_g",
        "real_kg",
        "pasada_real",
    ]
    panel = ultimo_disponible(
        panel,
        historico,
        columnas_hist,
        fecha_observacion="fecha_real",
        fecha_corte="fecha_emision",
    )
    panel = panel.rename(
        columns={
            "frutos_reales_por_planta_catalogo_y": "frutos_por_planta_ultimo_asof",
            "peso_real_g_y": "peso_real_g_ultimo_asof",
            "real_kg_y": "kg_ultimo_asof",
            "pasada_real_y": "pasada_ultimo_asof",
            "fecha_real_observada": "fecha_ultima_cosecha",
            "frutos_reales_por_planta_catalogo_x": "frutos_reales_por_planta_catalogo",
            "peso_real_g_x": "peso_real_g",
            "real_kg_x": "real_kg",
            "pasada_real_x": "pasada_real",
        }
    )
    if "fecha_ultima_cosecha" in panel:
        panel["semanas_desde_ultima_cosecha"] = (
            panel.fecha_emision - pd.to_datetime(panel.fecha_ultima_cosecha)
        ).dt.days / 7
    for columna in (
        "frutos_por_planta_ultimo_asof",
        "peso_real_g_ultimo_asof",
        "kg_ultimo_asof",
        "pasada_ultimo_asof",
        "semanas_desde_ultima_cosecha",
    ):
        if columna not in panel:
            panel[columna] = np.nan
    panel = agregar_historial_asof(panel, reales)
    return panel


def auditar_panel_fenologico(
    panel: pd.DataFrame,
    *,
    n_emisiones: int,
    n_lotes: int,
    horizonte_semanas: int,
    filas_esperadas: int | None = None,
) -> pd.DataFrame:
    """Controles explícitos de grano, conteo, fuga y ausencia de predictores R09."""

    claves = ["campania", "fecha_emision", "lote_id", "fecha_objetivo"]
    duplicados = int(panel.duplicated(claves).sum())
    esperado = (
        int(filas_esperadas)
        if filas_esperadas is not None
        else n_emisiones * n_lotes * horizonte_semanas
    )
    fugas = detectar_fuga(panel)
    prohibidas = sorted(
        set(panel) & {"frutos_por_planta_r09", "peso_baya_r09", "kg_r09", "p50_kg_r09"}
    )
    filas = [
        {
            "regla": "fenologico_grano_unico",
            "estado": "ok" if duplicados == 0 else "error",
            "observados": len(panel),
            "afectados": duplicados,
            "detalle": "campaña × emisión × lote × semana objetivo",
        },
        {
            "regla": "fenologico_conteo_rejilla",
            "estado": "ok" if len(panel) == esperado else "error",
            "observados": len(panel),
            "afectados": abs(len(panel) - esperado),
            "detalle": f"esperado={esperado}; emisiones={n_emisiones}; lotes={n_lotes}",
        },
        {
            "regla": "fenologico_sin_predictores_r09",
            "estado": "ok" if not prohibidas else "error",
            "observados": len(panel.columns),
            "afectados": len(prohibidas),
            "detalle": ", ".join(prohibidas) or "ninguna salida R09 presente",
        },
        {
            "regla": "fenologico_sin_fuga_fechada",
            "estado": "ok" if fugas.empty else "error",
            "observados": len(panel),
            "afectados": int(fugas.afectados.sum()) if not fugas.empty else 0,
            "detalle": fugas.to_dict("records") if not fugas.empty else "as-of válido",
        },
    ]
    return pd.DataFrame(filas)


__all__ = [
    "agregar_historial_asof",
    "auditar_panel_fenologico",
    "campania_mas_reciente",
    "construir_panel_fenologico",
    "cosecha_real_semanal",
    "emisiones_historial",
    "normalizar_emisiones",
]
