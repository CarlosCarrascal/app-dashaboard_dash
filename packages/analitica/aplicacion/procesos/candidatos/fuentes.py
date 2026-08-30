"""Lecturas SQL de emisiones y baselines congelados."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from ....infraestructura.postgres import conexion_postgres
from .contratos import ContratoBaselines


def seleccionar_emisiones_micro_desde_fuente(
    emisiones: pd.DataFrame,
    cosecha: pd.DataFrame,
    campania: str,
    cuantiles: tuple[float, ...] = (0.2, 0.5, 0.8),
    cerrado_hasta: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Elige emisiones deterministas por fase de volumen, no una muestra aleatoria."""

    e = emisiones.copy()
    e["fecha_emision"] = pd.to_datetime(e["fecha_emision"], errors="coerce").dt.normalize()
    e = e[e.campania.astype(str).eq(str(campania))].dropna(subset=["fecha_emision"])
    e = e.sort_values("fecha_emision").drop_duplicates(["campania", "fecha_emision"])
    if e.empty:
        return e
    h = cosecha.copy()
    h = h[h.campania.astype(str).eq(str(campania))]
    h["fecha"] = pd.to_datetime(h["fecha"], errors="coerce").dt.normalize()
    h["kg"] = pd.to_numeric(h.get("kg"), errors="coerce").fillna(0.0)
    watermark_fuente = h.fecha.max()
    watermark = (
        min(pd.Timestamp(cerrado_hasta).normalize(), watermark_fuente)
        if cerrado_hasta is not None and pd.notna(watermark_fuente)
        else watermark_fuente
    )
    volumenes: list[dict[str, Any]] = []
    for fecha in e.fecha_emision:
        inicio = pd.Timestamp(fecha) + pd.to_timedelta(7, unit="D")
        fin = inicio + pd.to_timedelta(6, unit="D")
        cerrado = pd.notna(watermark) and fin <= watermark
        volumen = float(h.loc[h.fecha.between(inicio, fin), "kg"].sum()) if cerrado else np.nan
        volumenes.append({"fecha_emision": fecha, "volumen_h1": volumen, "cerrado": cerrado})
    v = pd.DataFrame(volumenes)
    v = v[v.cerrado & v.volumen_h1.notna()].sort_values("fecha_emision")
    if v.empty:
        return e.iloc[0:0].copy()
    total = float(v.volumen_h1.clip(lower=0).sum())
    if total <= 0:
        posiciones = np.linspace(0, len(v) - 1, min(len(cuantiles), len(v))).round().astype(int)
        fechas = v.iloc[posiciones].fecha_emision.tolist()
    else:
        acumulado = v.volumen_h1.clip(lower=0).cumsum() / total
        fechas = []
        for cuantil in cuantiles:
            distancia = (acumulado - cuantil).abs()
            fechas.append(v.loc[distancia.idxmin(), "fecha_emision"])
    seleccion = e[e.fecha_emision.isin(list(dict.fromkeys(fechas)))].copy()
    return seleccion.sort_values("fecha_emision").reset_index(drop=True)


def cargar_contrato_baselines(
    dsn: str,
    referencias: Mapping[str, int],
    campania: str,
) -> ContratoBaselines:
    """Resuelve referencias solo desde releases activas y aprobadas.

    Esto impide que el CLI apunte accidentalmente a una corrida experimental que tenga
    el mismo nombre de modelo. Todas las series deben compartir un único contrato.
    """

    pares = sorted((str(modelo), int(run_id)) for modelo, run_id in referencias.items())
    encontrados: list[dict[str, Any]] = []
    consulta = """
        SELECT l.modelo, l.run_id, l.source_hash, l.evaluation_contract_id,
               c.campania, c.cerrado_hasta, c.keyset_sha256,
               c.closed_calendar_sha256
        FROM analytics.model_series_release l
        JOIN analytics.evaluation_contract c
          ON c.evaluation_contract_id = l.evaluation_contract_id
        WHERE l.campania = %s
          AND l.modelo = %s
          AND l.run_id = %s
          AND l.uso IN ('historico', 'referencia', 'screening')
          AND l.activo
          AND l.estado = 'approved'
          AND l.estado_evaluacion = 'passed'
          AND c.estado = 'approved'
    """
    with conexion_postgres(dsn) as conexion, conexion.cursor() as cursor:
        for modelo, run_id in pares:
            cursor.execute(consulta, (campania, modelo, run_id))
            columnas = [descripcion.name for descripcion in cursor.description]
            filas = cursor.fetchall()
            encontrados.extend(dict(zip(columnas, fila, strict=True)) for fila in filas)
    if len(encontrados) != len(pares):
        recibidos = sorted((str(f["modelo"]), int(f["run_id"])) for f in encontrados)
        raise ValueError(
            "Los baselines deben ser releases activas, aprobadas y certificadas; "
            f"solicitados={pares}, encontrados={recibidos}."
        )
    contratos = {int(f["evaluation_contract_id"]) for f in encontrados}
    if len(contratos) != 1:
        raise ValueError(
            f"Los baselines no comparten un único evaluation_contract_id: {sorted(contratos)}."
        )
    primera = encontrados[0]
    return ContratoBaselines(
        evaluation_contract_id=int(primera["evaluation_contract_id"]),
        campania=str(primera["campania"]),
        cerrado_hasta=pd.Timestamp(primera["cerrado_hasta"]).normalize(),
        keyset_sha256=str(primera["keyset_sha256"]),
        closed_calendar_sha256=str(primera["closed_calendar_sha256"]),
        run_ids={str(f["modelo"]): int(f["run_id"]) for f in encontrados},
        source_hashes={str(f["modelo"]): str(f["source_hash"]) for f in encontrados},
    )


def cargar_baselines_por_run(
    dsn: str,
    referencias: Mapping[str, int],
    campania: str,
    *,
    horizontes: tuple[int, ...] | None = None,
    cerrado_hasta: str | pd.Timestamp | None = None,
    fechas_emision: pd.Series | list[Any] | tuple[Any, ...] | None = None,
) -> dict[str, pd.DataFrame]:
    """Carga solo el segmento necesario de baselines inmutables.

    Los filtros reducen el coste del micro-replay sin cambiar el contrato: la
    corrida y la release siguen siendo las fuentes congeladas y nunca se
    reconstruyen dentro del runner candidato.
    """

    columnas = """
        modelo, version_modelo, campania, lote_id, fecha_emision, fecha_objetivo,
        horizonte_semanas, p50_kg, real_kg
    """
    salida: dict[str, pd.DataFrame] = {}
    emisiones = None
    if fechas_emision is not None:
        emisiones = sorted(
            {pd.Timestamp(fecha).date() for fecha in list(fechas_emision) if pd.notna(fecha)}
        )
    with conexion_postgres(dsn) as conexion:
        for modelo, run_id in sorted(referencias.items()):
            condiciones = ["run_id = %s", "campania = %s", "modelo = %s"]
            parametros: list[Any] = [int(run_id), campania, modelo]
            if horizontes:
                condiciones.append("horizonte_semanas = ANY(%s::smallint[])")
                parametros.append([int(h) for h in horizontes])
            if cerrado_hasta is not None:
                condiciones.append("fecha_objetivo::date + 6 <= %s::date")
                parametros.append(pd.Timestamp(cerrado_hasta).date())
            if emisiones:
                condiciones.append("fecha_emision::date = ANY(%s::date[])")
                parametros.append(emisiones)
            consulta = f"""
                SELECT {columnas}
                FROM analytics.prediction
                WHERE {" AND ".join(condiciones)}
            """
            with conexion.cursor() as cursor:
                cursor.execute(consulta, parametros)
                nombres = [descripcion.name for descripcion in cursor.description]
                salida[modelo] = pd.DataFrame(cursor.fetchall(), columns=nombres)
    return salida


__all__ = [
    "cargar_baselines_por_run",
    "cargar_contrato_baselines",
    "seleccionar_emisiones_micro_desde_fuente",
]
