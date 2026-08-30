"""Ejecución del análisis de relaciones y sus claims de evidencia."""

from __future__ import annotations

import pandas as pd

from .common import _registrar_inicio, _repositorio, _salida


def ejecutar_relaciones(args) -> int:
    from ..proyeccion.calidad import controles_ensamblaje, controles_fuente
    from ..proyeccion.exportacion import exportar_paquete
    from ..proyeccion.fuentes import cargar_datos
    from ..proyeccion.inferencia import evaluar_matriz_inferencial
    from ..proyeccion.persistencia import tracking_mlflow
    from ..proyeccion.relaciones_partes import (
        construir_panel_relaciones,
        evaluar_matriz_relaciones,
        evaluar_relaciones,
        generar_claims,
        panel_packing,
        relaciones_packing,
        resumen_matriz,
        sensibilidad_gdd,
    )

    datos = cargar_datos(args.source, corte_asof=getattr(args, "corte_asof", None))
    config = {"minimo_n": args.minimo_n, "source": args.source}
    repo = _repositorio(args.no_persist)
    run_id = snapshot_id = None
    with tracking_mlflow("relations", datos.fuente, config) as mlflow_id:
        try:
            snapshot_id, run_id = _registrar_inicio(repo, datos, "relations", config, mlflow_id)
            panel, auditoria_ensamblaje = construir_panel_relaciones(
                datos, devolver_auditoria=True
            )
            relaciones = evaluar_relaciones(panel, minimo_n=args.minimo_n)
            inferencia = evaluar_matriz_inferencial(panel)
            # La matriz exploratoria cruza todo con todo para descubrir relaciones que
            # nadie formuló de antemano. Un hallazgo de un barrido no vale lo mismo que
            # una hipótesis previa, aunque salga el mismo número.
            matriz = evaluar_matriz_relaciones(panel, minimo_n=args.minimo_n)
            resumen = resumen_matriz(matriz)
            # El packing usa módulo-semana, no lote-semana, y cubre 15 de los 26 módulos.
            packing = relaciones_packing(panel_packing(datos))
            sensibilidad = sensibilidad_gdd(panel)
            relaciones = pd.concat(
                [
                    relaciones,
                    sensibilidad.assign(
                        hipotesis_id="H1_SENSIBILIDAD_GDD",
                        hipotesis="Sensibilidad a temperatura base",
                    ),
                ],
                ignore_index=True,
                sort=False,
            )
            claims = generar_claims(
                relaciones[relaciones.hipotesis_id != "H1_SENSIBILIDAD_GDD"], inferencia
            )
            calidad = pd.concat(
                [
                    controles_fuente(datos),
                    controles_ensamblaje(auditoria_ensamblaje),
                ],
                ignore_index=True,
            )
            zip_ruta, firma = exportar_paquete(
                "relations",
                datos,
                relaciones=relaciones,
                inferencia=inferencia,
                claims=claims,
                calidad=calidad,
                matriz_relaciones=matriz,
                relaciones_packing=packing,
                auditoria_ensamblaje=auditoria_ensamblaje,
            )
            if repo:
                repo.guardar_claims(run_id, claims)
                repo.guardar_calidad(snapshot_id, run_id, calidad)
                repo.guardar_artifacto(run_id, "audit_zip", zip_ruta, firma)
                repo.finalizar_run(run_id)
            try:
                import mlflow

                if mlflow.active_run():
                    mlflow.log_artifact(str(zip_ruta), artifact_path="audit")
            except ImportError:
                pass
            _salida(
                run_id=run_id,
                snapshot=datos.fuente.firma,
                fuente=datos.fuente.nombre,
                relaciones=len(relaciones),
                inferencias=len(inferencia),
                claims=len(claims),
                auditoria_ensamblaje=len(auditoria_ensamblaje),
                matriz_exploratoria=resumen,
                packing={
                    "pruebas": len(packing),
                    "sobreviven": int(packing.sobrevive.sum()) if not packing.empty else 0,
                },
                artefacto=zip_ruta,
            )
            return 0
        except (Exception, KeyboardInterrupt) as exc:
            if repo and run_id:
                repo.finalizar_run(run_id, "failed", str(exc))
            raise
