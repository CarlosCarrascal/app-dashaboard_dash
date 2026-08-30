"""Comandos operativos basados en los libros ProySemanal."""

from __future__ import annotations

import pandas as pd

from .common import _raiz_operativa, _salida


def ejecutar_validar_operativo(args) -> int:
    """Valida los libros actuales y bloquea el éxito si las fuentes no están alineadas."""

    raiz = _raiz_operativa(args)
    from ..proyeccion.operativo import seleccionar_libros_operativos, validar_libro_operativo
    from ..proyeccion.persistencia import RepositorioAnalytics

    libros = seleccionar_libros_operativos(raiz, args.version_fuente)
    filas = []
    for nombre, fundo in libros:
        ruta = raiz / nombre
        if not ruta.is_file():
            filas.append(
                {
                    "archivo": str(ruta),
                    "modelo": "ModeloOperativoActual_v1",
                    "estado": "no_evaluable",
                    "sha256": "",
                    "filas_fuente": 0,
                    "filas_motor": 0,
                    "diferencias_filas": 0,
                    "max_diferencia": {},
                    "advertencias": ["No se encontró el libro operativo"],
                    "metadatos": {"fundo": fundo},
                }
            )
            continue
        resultado = validar_libro_operativo(ruta, fundo_nombre=fundo)
        filas.append(
            {
                "archivo": resultado.archivo,
                "modelo": resultado.modelo,
                "estado": resultado.estado,
                "sha256": resultado.sha256,
                "filas_fuente": resultado.filas_fuente,
                "filas_motor": resultado.filas_motor,
                "diferencias_filas": resultado.diferencias_filas,
                "max_diferencia": resultado.max_diferencia,
                "advertencias": resultado.advertencias,
                "metadatos": resultado.metadatos,
            }
        )
    reporte = pd.DataFrame(filas)
    if args.persist:
        repo = RepositorioAnalytics()
        repo.guardar_validacion_operativa(reporte)
    _salida(
        modelo="ModeloOperativoActual_v1",
        estado="validado" if (reporte.estado == "validado").all() else "bloqueado",
        libros=reporte.to_dict("records"),
        persistido=bool(args.persist),
    )
    return 0 if (reporte.estado == "validado").all() else 2


def ejecutar_project_operativo(args) -> int:
    """Persiste una emisión de ProySemanal sin ejecutar el torneo ML.

    Es la ruta operativa: Panel + Parametros → motor Python → analytics.prediction.
    R09 no se sobrescribe; la corrida queda experimental hasta que el replay histórico
    demuestre una mejora y se promueva explícitamente.
    """

    from ..proyeccion.exportacion import exportar_paquete
    from ..proyeccion.operativo import (
        MODELO_OPERATIVO_ACTUAL,
        construir_modelo_operativo_excel,
        datos_proyeccion_operativo,
    )
    from ..proyeccion.persistencia import RepositorioAnalytics, tracking_mlflow

    raiz = _raiz_operativa(args)
    predicciones, fuente, detalles = construir_modelo_operativo_excel(
        raiz,
        campania=args.campania,
        fecha_emision=args.fecha_emision,
        version_fuente=args.version_fuente,
        fuente_parametros=args.fuente_parametros,
    )
    repo = None if args.no_persist else RepositorioAnalytics()
    datos = datos_proyeccion_operativo(fuente)
    config = {
        "modelo_proyeccion": MODELO_OPERATIVO_ACTUAL,
        "version_modelo": "v1-auto" if args.fuente_parametros == "postgres_auto" else "v1",
        "campania": args.campania,
        "fecha_emision": str(args.fecha_emision),
        "version_fuente": args.version_fuente,
        "fuente_parametros": args.fuente_parametros,
        "publicacion": "experimental",
        "fuente": detalles,
        "validacion_operativa": {
            "estado": "operativo_reproducible",
            "nota": (
                "Panel aporta el calendario; X/O/N/A/B se calibran automáticamente desde "
                "PostgreSQL."
                if args.fuente_parametros == "postgres_auto"
                else "Panel + Parametros ejecutados por el motor Python; BDProy queda como "
                "compatibilidad."
            ),
        },
    }
    run_id = snapshot_id = None
    with tracking_mlflow("project", fuente, config) as mlflow_id:
        try:
            if repo is not None:
                snapshot_id = repo.snapshot(datos)
                run_id = repo.crear_run(snapshot_id, "project", config, mlflow_id)
                identidad = repo.resolver_lote_ids(predicciones)
                predicciones = predicciones.merge(
                    identidad,
                    on=["fundo", "modulo", "turno", "lote"],
                    how="left",
                    validate="many_to_one",
                )
                faltantes = int(predicciones["lote_id"].isna().sum())
                if faltantes:
                    raise RuntimeError(
                        f"No se resolvieron {faltantes} filas contra dim.lote; "
                        "la corrida no se persistirá para evitar mezclar lotes."
                    )
            calidad = pd.DataFrame(
                [
                    {
                        "regla": "modelo_operativo_ejecutado",
                        "estado": "ok",
                        "observados": len(predicciones),
                        "afectados": 0,
                        "detalle": {
                            "modelo": MODELO_OPERATIVO_ACTUAL,
                            "libros": detalles["manifest"],
                        },
                    },
                    {
                        "regla": "intervalos_operativos",
                        "estado": "warning",
                        "observados": len(predicciones),
                        "afectados": len(predicciones),
                        "detalle": {
                            "mensaje": "P10/P90 aún no calibrados; la salida es determinista."
                        },
                    },
                ]
            )
            zip_ruta, firma = exportar_paquete(
                "project-operational",
                datos,
                predicciones=predicciones,
                calidad=calidad,
            )
            if repo is not None:
                repo.guardar_predicciones(run_id, predicciones)
                repo.guardar_calidad(snapshot_id, run_id, calidad)
                repo.guardar_artifacto(run_id, "audit_zip", zip_ruta, firma)
                repo.finalizar_run(run_id)
            _salida(
                run_id=run_id,
                snapshot=fuente.firma,
                modelo=MODELO_OPERATIVO_ACTUAL,
                estado="succeeded" if repo is not None else "calculated",
                publicacion="experimental",
                filas=len(predicciones),
                lotes=int(
                    predicciones[["fundo", "modulo", "lote"]]
                    .drop_duplicates()
                    .shape[0]
                ),
                artefacto=zip_ruta,
                advertencias=list(fuente.advertencias),
            )
            return 0
        except (Exception, KeyboardInterrupt) as exc:
            if repo is not None and run_id is not None:
                repo.finalizar_run(run_id, "failed", str(exc))
            raise
