"""Orquestación del modelo operativo sobre libros Excel de campaña."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from ..contratos import FuenteInfo
from ..motor_proyeccion_semanal import ejecutar_proyeccion_semanal_dataframe
from ..parametros_automaticos import (
    calibrar_universo_operativo,
    reemplazar_parametros_excel_por_db,
)
from ..versiones import banda_horizonte
from .excel import (
    MODELO_OPERATIVO_ACTUAL,
    _fecha,
    _firma_manifest,
    leer_libro_operativo,
    seleccionar_libros_operativos,
    sha256_archivo,
)


def construir_modelo_operativo_excel(
    root: str | Path,
    *,
    campania: str,
    fecha_emision: str | date | datetime,
    version_fuente: str = "ProySemanal_33",
    configuracion: Iterable[tuple[str, str]] | None = None,
    promociones: dict[str, str] | None = None,
    fuente_parametros: str = "excel",
) -> tuple[pd.DataFrame, FuenteInfo, dict[str, object]]:
    """Ejecuta la corrida completa del calendario que contienen los cuatro libros.

    La fecha de emisión es obligatoria y externa al libro. Así una reconstrucción
    histórica no puede inventar silenciosamente una fecha distinta a la versión que
    se desea publicar.
    """
    root_path = Path(root).expanduser().resolve()
    emision = _fecha(fecha_emision)
    libros = (
        tuple(configuracion)
        if configuracion is not None
        else seleccionar_libros_operativos(root_path, version_fuente, promociones)
    )
    partes: list[pd.DataFrame] = []
    manifest: list[dict[str, object]] = []
    resumen: list[dict[str, object]] = []
    if fuente_parametros not in {"excel", "postgres_auto"}:
        raise ValueError("fuente_parametros debe ser 'excel' o 'postgres_auto'")
    universo_auto = {}
    objetivos_auto = pd.DataFrame()
    metadata_auto: dict[str, object] = {}
    if fuente_parametros == "postgres_auto":
        universo_auto, objetivos_auto, metadata_auto = calibrar_universo_operativo(
            campania,
            emision,
        )

    for nombre, fundo in libros:
        ruta = root_path / nombre
        if not ruta.is_file():
            raise FileNotFoundError(f"No se encontró el libro operativo: {ruta}")
        parametros, panel, bdproy = leer_libro_operativo(ruta)
        hash_libro = sha256_archivo(ruta)
        metadata_parametros: dict[str, object] = {
            "fundo_operativo": fundo,
            "filas": int(len(parametros)),
            "niveles_calibracion": {"excel": int(len(parametros))},
        }
        if fuente_parametros == "postgres_auto":
            parametros, metadata_parametros = reemplazar_parametros_excel_por_db(
                parametros,
                fundo_operativo=fundo,
                universo=universo_auto,
                objetivos=objetivos_auto,
            )
        motor = ejecutar_proyeccion_semanal_dataframe(
            df_parametros=parametros,
            df_panel=panel,
            campana=campania,
            fundo_nombre=fundo,
        )
        if motor.empty:
            raise ValueError(f"El motor no produjo filas para {ruta.name}")

        motor = motor.copy()
        motor["modelo"] = MODELO_OPERATIVO_ACTUAL
        motor["version_modelo"] = "v1-auto" if fuente_parametros == "postgres_auto" else "v1"
        motor["version_fuente"] = version_fuente
        motor["campania"] = campania
        motor["fecha_emision"] = emision
        motor["fecha_objetivo"] = pd.to_datetime(motor["FeCos"])
        delta_dias = (motor["fecha_objetivo"] - emision).dt.days
        motor["horizonte_semanas"] = (delta_dias.clip(lower=0) // 7).astype(int).clip(upper=52)
        motor["banda_horizonte"] = motor["horizonte_semanas"].map(banda_horizonte)
        motor["empresa"] = None
        motor["fundo"] = motor["FundoQ"]
        motor["modulo"] = motor["Modulo"].astype(str).str.strip()
        motor["turno"] = motor["Turno"].astype(str).str.strip()
        motor["lote"] = motor["Lote"].astype(str).str.strip()
        motor["plantas"] = motor["Frutototal"] / motor["Frtutos"].replace(0, pd.NA)
        motor["frutos_por_planta"] = motor["Frtutos"]
        motor["peso_baya_g"] = motor["Peso"]
        # El modelo operativo es determinista. No se inventa un margen hasta calibrar
        # residuos históricos de esta misma emisión y horizonte.
        motor["p10_kg"] = None
        motor["p50_kg"] = motor["Kg"].clip(lower=0)
        motor["p90_kg"] = None
        motor["real_kg"] = None
        motor["confianza"] = "media"
        motor["origen_emision"] = emision
        motor["tipo_prediccion"] = "operativa"
        motor["es_replay_ciego"] = False
        motor["es_curva_stitched"] = False
        motor["estado_evaluacion"] = "pendiente"
        bdproy_filas_referencia = int(len(bdproy))
        metadata_por_lote = {
            (str(row.get("Modulo", "")).strip(), str(row.get("Lote", "")).strip()): {
                "lote_id_db": row.get("LoteIdDB"),
                "fuente_parametros": row.get("FuenteParametros", "excel"),
                "nivel_calibracion": row.get("NivelCalibracion", "excel"),
                "panas_observadas": row.get("PanasObservadas"),
                "rmse_parametros": row.get("RmseParametros"),
                "fuente_poda": row.get("FuentePoda", "excel"),
            }
            for _, row in parametros.iterrows()
        }

        def componentes_fila(
            fila,
            fuente_libro=nombre,
            fuente_hash=hash_libro,
            fundo_operativo=fundo,
            bdproy_filas=bdproy_filas_referencia,
            metadata=metadata_por_lote,
        ):
            meta_parametro = metadata.get(
                (str(fila["Modulo"]).strip(), str(fila["Lote"]).strip()),
                {},
            )
            return {
                "formula": "frutos_por_planta × plantas × peso_baya_g / 1000",
                "modelo_base": MODELO_OPERATIVO_ACTUAL,
                "modelos_componentes": {
                    "frutos": "tres intervalos de distribución normal por lote",
                    "peso": "tres curvas exponenciales con promedio ponderado",
                },
                "pasada": fila["Paña"],
                "fecha_inicio": fila["Fechaini"],
                "fecha_objetivo": fila["FeCos"],
                "area_ha": fila["Area"],
                "fuente_libro": fuente_libro,
                "fuente_hash": fuente_hash,
                "fundo_operativo": fundo_operativo,
                "fundo_fuente": fila["FundoQ"],
                "bdproy_filas_referencia": bdproy_filas,
                "intervalos": "no_calibrados_en_esta_corrida",
                **meta_parametro,
            }

        motor["componentes"] = motor.apply(componentes_fila, axis=1)
        partes.append(motor)
        manifest.append(
            {
                "archivo": nombre,
                "ruta": str(ruta),
                "fundo": fundo,
                "sha256": hash_libro,
                "filas_parametros": int(len(parametros)),
                "filas_panel": int(len(panel)),
                "filas_motor": int(len(motor)),
                "filas_bdproy": int(len(bdproy)),
                "fuente_parametros": fuente_parametros,
                "calibracion_parametros": metadata_parametros,
                "columnas_fepas": sorted(
                    str(c) for c in panel.columns if str(c).casefold().startswith("fepas")
                ),
            }
        )
        resumen.append({"archivo": nombre, "filas": len(motor), "fundo": fundo})

    predicciones = pd.concat(partes, ignore_index=True)
    firma = _firma_manifest(manifest)
    conteos = {
        "libros": len(manifest),
        "parametros": sum(int(m["filas_parametros"]) for m in manifest),
        "panel": sum(int(m["filas_panel"]) for m in manifest),
        "predicciones": len(predicciones),
        "bdproy_referencia": sum(int(m["filas_bdproy"]) for m in manifest),
    }
    advertencias = (
        "BDProy se conserva como salida de compatibilidad; no se usa como predictor.",
        "Los intervalos P10/P90 aún no están calibrados para esta corrida operativa.",
        "La emisión se recibió explícitamente por parámetro y no se infirió del libro.",
        (
            "X/O/N/A/B se calibraron con cosecha PostgreSQL conocida hasta la emisión; "
            "Panel continúa aportando el calendario de pasadas."
            if fuente_parametros == "postgres_auto"
            else "X/O/N/A/B proceden de la hoja Parametros del libro operativo."
        ),
    )
    fuente = FuenteInfo(
        # El contrato SQL permite únicamente las familias de fuente ``postgres``,
        # ``excel`` y ``fixture``. El detalle operativo queda en el manifest.
        nombre="postgres" if fuente_parametros == "postgres_auto" else "excel",
        firma=firma,
        corte=emision.to_pydatetime(),
        fallback=False,
        advertencias=advertencias,
        conteos=conteos,
    )
    detalles = {
        "modelo": MODELO_OPERATIVO_ACTUAL,
        "version_fuente": version_fuente,
        "fecha_emision": emision.date().isoformat(),
        "campania": campania,
        "root": str(root_path),
        "manifest": manifest,
        "resumen": resumen,
        "fuente_parametros": fuente_parametros,
        "calibracion_automatica": metadata_auto,
    }
    return predicciones, fuente, detalles


__all__ = ["construir_modelo_operativo_excel"]
