"""Validación del universo común de series de replay."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .certificar_releases_replay_contratos import Certificacion
from .certificar_releases_replay_serializacion import _sha256


def _certificar_universo(
    cert: Certificacion,
    filas_por_modelo: dict[str, list[tuple[Any, ...]]],
) -> dict[str, Any]:
    keysets: dict[str, list[tuple[Any, ...]]] = {}
    hashes_prediccion: dict[str, str] = {}
    reales_por_clave: dict[tuple[Any, ...], float] = {}

    for serie in cert.series:
        filas = filas_por_modelo[serie.modelo]
        if not filas:
            raise ValueError(f"{cert.campania}/{serie.modelo}: serie vacía")
        claves = (
            [(fila[0], fila[1], fila[2]) for fila in filas]
            if cert.curva_stitched
            else [(fila[0], fila[1], fila[2], int(fila[5])) for fila in filas]
        )
        if len(claves) != len(set(claves)):
            raise ValueError(f"{cert.campania}/{serie.modelo}: claves duplicadas")
        if cert.curva_stitched:
            lote_semana = [(fila[0], fila[1]) for fila in filas]
            if len(lote_semana) != len(set(lote_semana)):
                raise ValueError(
                    f"{cert.campania}/{serie.modelo}: más de una emisión por lote-semana"
                )
            emisiones_por_semana: dict[Any, set[Any]] = {}
            for _, objetivo, emision, *_ in filas:
                emisiones_por_semana.setdefault(objetivo, set()).add(emision)
            incoherentes = {
                objetivo: emisiones
                for objetivo, emisiones in emisiones_por_semana.items()
                if len(emisiones) != 1
            }
            if incoherentes:
                raise ValueError(
                    f"{cert.campania}/{serie.modelo}: emisiones mezcladas por semana: "
                    f"{incoherentes}"
                )
        keysets[serie.modelo] = claves
        hashes_prediccion[serie.modelo] = _sha256(
            [
                (
                    int(fila[0]),
                    fila[1].isoformat(),
                    fila[2].isoformat(),
                    round(float(fila[3]), 6),
                    round(float(fila[4]), 6),
                    int(fila[5]),
                    str(fila[6]),
                    None if fila[7] is None else round(float(fila[7]), 6),
                    None if fila[8] is None else round(float(fila[8]), 6),
                    None if fila[9] is None else round(float(fila[9]), 6),
                    None if fila[10] is None else round(float(fila[10]), 6),
                    None if fila[11] is None else round(float(fila[11]), 6),
                    str(fila[12]),
                )
                for fila in filas
            ]
        )
        for fila in filas:
            clave = (
                (fila[0], fila[1], fila[2])
                if cert.curva_stitched
                else (fila[0], fila[1], fila[2], int(fila[5]))
            )
            real = round(float(fila[3]), 6)
            anterior = reales_por_clave.setdefault(clave, real)
            if anterior != real:
                raise ValueError(f"{cert.campania}: denominador real distinto en {clave}")

    referencia = next(iter(keysets.values()))
    for modelo, claves in keysets.items():
        if claves != referencia:
            faltan = len(set(referencia) - set(claves))
            sobran = len(set(claves) - set(referencia))
            raise ValueError(
                f"{cert.campania}/{modelo}: universo diferente (faltan={faltan}, sobran={sobran})"
            )

    semanas = sorted({clave[1] for clave in referencia})
    emisiones = sorted({clave[2] for clave in referencia})
    if cert.curva_stitched:
        keyset_payload = [
            (int(lote), objetivo.isoformat(), emision.isoformat())
            for lote, objetivo, emision in referencia
        ]
    else:
        keyset_payload = [
            (int(lote), objetivo.isoformat(), emision.isoformat(), int(horizonte))
            for lote, objetivo, emision, horizonte in referencia
        ]
    keyset_sha = _sha256(keyset_payload)
    calendario_sha = _sha256([semana.isoformat() for semana in semanas])
    return {
        "fecha_inicio": semanas[0],
        "fecha_fin": semanas[-1],
        "cerrado_hasta": semanas[-1] + timedelta(days=6),
        "semanas": semanas,
        "emisiones": emisiones,
        "keyset_sha256": keyset_sha,
        "closed_calendar_sha256": calendario_sha,
        "volumen_real_kg": sum(reales_por_clave.values()),
        "n_unidades": len(referencia),
        "n_emisiones": len(emisiones),
        "predicciones_sha256": hashes_prediccion,
    }


__all__ = ["_certificar_universo"]
