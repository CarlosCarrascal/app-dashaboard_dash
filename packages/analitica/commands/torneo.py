"""Comandos del torneo de modelos: backtest, train, project y export."""

from __future__ import annotations

import pandas as pd

from .common import _parsear_horizontes, _registrar_inicio, _repositorio, _salida


def _torneo(args, tipo: str):
    from ..proyeccion.asof import enriquecer_asof
    from ..proyeccion.backtest import construir_backtest
    from ..proyeccion.calidad import (
        controles_componentes,
        controles_fuente,
        controles_panel_asof,
        controles_predicciones,
        controles_reconciliacion,
    )
    from ..proyeccion.clima_futuro import AdaptadorOpenMeteo
    from ..proyeccion.engine import ProjectionConfig, ProjectionScenario, proyectar_desde_corte
    from ..proyeccion.exportacion import exportar_paquete
    from ..proyeccion.fenologico_v1 import construir_panel_fenologico, proyectar_fenologico_v1
    from ..proyeccion.fuentes import cargar_datos
    from ..proyeccion.gobernanza import (
        log_metricas_mlflow,
        registrar_modelos_mlflow,
        tracking_mlflow,
    )
    from ..proyeccion.hibrido_legacy import proyectar_hibrido_v1
    from ..proyeccion.interpretabilidad import paquete_interpretabilidad_xgboost
    from ..proyeccion.metricas import metricas_pareadas_modelos
    from ..proyeccion.modelos import entrenar_challengers_finales
    from ..proyeccion.monitoreo import monitorear_llegada_reales
    from ..proyeccion.reconciliacion import bottom_up
    from ..proyeccion.torneo import ejecutar_torneo

    datos = cargar_datos(args.source, corte_asof=getattr(args, "corte_asof", None))
    config = {
        "source": args.source,
        "incluir_ml": not args.skip_ml,
        "incluir_statsforecast": not args.skip_stats,
        "incluir_componentes": not getattr(args, "skip_componentes", False),
        "incluir_fenologico_v1": not getattr(args, "skip_fenologico_v1", False),
        "incluir_macro_legacy": not getattr(args, "skip_macro_legacy", False),
        "incluir_hibrido_legacy": not getattr(args, "skip_hibrido_legacy", False),
        "fenologico_usar_mixedlm": getattr(args, "fenologico_mixedlm", False),
        "incluir_explicaciones": not args.skip_explain,
        "modelo_proyeccion": getattr(args, "modelo_proyeccion", "campeon"),
        "horizonte_semanas": getattr(args, "horizonte_semanas", None),
        "calendario_proyeccion": getattr(args, "calendario_proyeccion", None),
        "fecha_emision": getattr(args, "fecha_emision", None),
        "fenologico_max_cortes": getattr(args, "fenologico_max_cortes", 8),
        "escenario": {
            "frutos_pct": getattr(args, "escenario_frutos_pct", 0.0),
            "peso_pct": getattr(args, "escenario_peso_pct", 0.0),
            "plantas_pct": getattr(args, "escenario_plantas_pct", 0.0),
            "desplazamiento_semanas": getattr(args, "desplazamiento_semanas", 0),
        },
        "clima_futuro": {
            "proveedor": "open_meteo"
            if getattr(args, "open_meteo_lat", None) is not None
            else None,
            "latitud": getattr(args, "open_meteo_lat", None),
            "longitud": getattr(args, "open_meteo_lon", None),
        },
    }
    config["publicacion"] = (
        "experimental"
        if tipo == "project"
        and (
            getattr(args, "modelo_proyeccion", "campeon") == "Componentes_identidad"
            or getattr(args, "modelo_proyeccion", "campeon") == "FenologicoComponentes_v1"
            or getattr(args, "modelo_proyeccion", "campeon") == "HibridoLegacyResidual_v1"
            or any(
                float(getattr(args, nombre, 0.0) or 0.0) != 0
                for nombre in (
                    "escenario_frutos_pct",
                    "escenario_peso_pct",
                    "escenario_plantas_pct",
                )
            )
            or int(getattr(args, "desplazamiento_semanas", 0) or 0) != 0
        )
        else "oficial"
    )
    repo = _repositorio(args.no_persist)
    run_id = snapshot_id = None
    with tracking_mlflow(tipo, datos.fuente, config) as mlflow_id:
        try:
            snapshot_id, run_id = _registrar_inicio(repo, datos, tipo, config, mlflow_id)
            latitud = getattr(args, "open_meteo_lat", None)
            longitud = getattr(args, "open_meteo_lon", None)
            if (latitud is None) != (longitud is None):
                raise ValueError("Open-Meteo requiere latitud y longitud juntas")
            if tipo == "project" and latitud is not None:
                pronostico_clima = AdaptadorOpenMeteo().obtener(
                    latitud=float(latitud),
                    longitud=float(longitud),
                )
                if repo is not None and run_id is not None:
                    repo.guardar_pronostico_clima(run_id, pronostico_clima)
            backtest = construir_backtest(datos.forecast, datos.cosecha)
            # El enriquecimiento as-of se calcula y audita aunque R09 continúe como campeón.
            objetivos = backtest[backtest.modelo == "R09_publicado"].drop_duplicates(
                ["campania", "lote_id", "fecha_emision", "fecha_objetivo"]
            )
            asof = enriquecer_asof(objetivos, datos)
            calidad_asof = controles_panel_asof(asof)
            resultado = ejecutar_torneo(
                backtest,
                datos.cosecha,
                incluir_ml=not args.skip_ml,
                incluir_statsforecast=not args.skip_stats,
                incluir_componentes=not getattr(args, "skip_componentes", False),
                incluir_fenologico_v1=not (
                    getattr(args, "skip_fenologico_v1", False)
                    or (
                        tipo == "project"
                        and getattr(args, "modelo_proyeccion", "campeon")
                        in {"FenologicoComponentes_v1", "HibridoLegacyResidual_v1"}
                    )
                ),
                incluir_macro_legacy=not getattr(args, "skip_macro_legacy", False),
                incluir_hibrido_legacy=not getattr(args, "skip_hibrido_legacy", False),
                # MixedLM queda disponible como diagnóstico explícito; el replay operativo
                # usa por defecto la ruta temporal más rápida y estable.
                fenologico_usar_mixedlm=getattr(args, "fenologico_mixedlm", False),
                # El panel as-of es la entrada de censos fenológicos y clima acumulado.
                panel_asof=asof,
                datos=datos,
                # La proyección directa no repite el rolling-origin antes de emitir.
                diagnostico_montecarlo=getattr(args, "diagnostico_montecarlo", False),
                sin_fuga=not (calidad_asof.estado == "error").any(),
                reproducible=True,
                fenologico_max_cortes=int(getattr(args, "fenologico_max_cortes", 8) or 8),
                horizonte_semanas=int(getattr(args, "horizonte_semanas", 10) or 10),
            )
            if tipo in {"project", "train", "export"} and repo is not None:
                decisiones_backtest = repo.decisiones_vigentes()
                if not decisiones_backtest.empty:
                    resultado.decisiones = decisiones_backtest
            registro_mlflow = {"estado": "no_aplica", "modelos": []}
            explicaciones = {}
            if tipo == "train" and not args.skip_ml:
                modelos_finales = entrenar_challengers_finales(backtest)
                registro_mlflow = registrar_modelos_mlflow(modelos_finales, resultado.decisiones)
                if not args.skip_explain:
                    explicaciones = paquete_interpretabilidad_xgboost(backtest)
            publicables = resultado.predicciones
            calidad_jerarquia = pd.DataFrame()
            calidad_fenologico = pd.DataFrame()
            if tipo == "project":
                modelo_solicitado = getattr(args, "modelo_proyeccion", "campeon")
                if modelo_solicitado == "FenologicoComponentes_v1":
                    nuevo = proyectar_fenologico_v1(
                        datos,
                        fecha_emision=getattr(args, "fecha_emision", None),
                        horizonte_semanas=int(getattr(args, "horizonte_semanas", 10) or 10),
                    )
                    publicables = nuevo.predicciones
                    resultado.evidencia_features = nuevo.evidencia_features
                    resultado.advertencias.extend(nuevo.advertencias)
                    calidad_fenologico = nuevo.auditoria
                elif modelo_solicitado == "HibridoLegacyResidual_v1":
                    fecha_hibrido = pd.Timestamp(
                        getattr(args, "fecha_emision", None) or backtest.fecha_emision.max()
                    ).normalize()
                    campania_hibrido = str(
                        backtest.loc[
                            backtest.fecha_emision.eq(backtest.fecha_emision.max()), "campania"
                        ].iloc[0]
                    )
                    fechas_previas = backtest[
                        (backtest.campania.astype(str) == campania_hibrido)
                        & (pd.to_datetime(backtest.fecha_emision) <= fecha_hibrido)
                    ][["campania", "fecha_emision"]].drop_duplicates()
                    emisiones_hibrido = pd.concat(
                        [
                            fechas_previas,
                            pd.DataFrame(
                                {
                                    "campania": [campania_hibrido],
                                    "fecha_emision": [fecha_hibrido],
                                }
                            ),
                        ],
                        ignore_index=True,
                    ).drop_duplicates(["campania", "fecha_emision"])
                    panel_hibrido = construir_panel_fenologico(
                        datos,
                        emisiones_hibrido,
                        horizonte_semanas=int(getattr(args, "horizonte_semanas", 10) or 10),
                    )
                    publicables = proyectar_hibrido_v1(
                        panel_hibrido,
                        datos,
                        fecha_hibrido,
                    )
                elif modelo_solicitado in {"Componentes_identidad", "R09_publicado"}:
                    horizontes = _parsear_horizontes(getattr(args, "horizontes", None))
                    escenario = ProjectionScenario(
                        nombre=getattr(args, "nombre_escenario", "base"),
                        frutos_pct=float(getattr(args, "escenario_frutos_pct", 0.0)),
                        peso_pct=float(getattr(args, "escenario_peso_pct", 0.0)),
                        plantas_pct=float(getattr(args, "escenario_plantas_pct", 0.0)),
                        desplazamiento_semanas=int(getattr(args, "desplazamiento_semanas", 0)),
                    )
                    configuracion = ProjectionConfig(
                        fecha_emision=getattr(args, "fecha_emision", None),
                        horizonte_semanas=int(getattr(args, "horizonte_semanas", 10) or 10),
                        modelo=modelo_solicitado,
                        calendario=getattr(args, "calendario_proyeccion", "ocurrencia"),
                        horizontes=horizontes,
                        escenario=escenario,
                    )
                    publicables = proyectar_desde_corte(
                        backtest, datos=datos, panel_asof=asof, config=configuracion
                    )
                else:
                    ultima = resultado.predicciones.fecha_emision.max()
                    actuales = resultado.predicciones[
                        resultado.predicciones.fecha_emision == ultima
                    ]
                    elegidas = [
                        actuales[
                            (actuales.banda_horizonte == d.banda_horizonte)
                            & (actuales.modelo == d.campeon)
                        ]
                        for d in resultado.decisiones.itertuples(index=False)
                    ]
                    publicables = (
                        pd.concat(elegidas, ignore_index=True) if elegidas else pd.DataFrame()
                    )
                if not publicables.empty:
                    calidad_jerarquia = controles_reconciliacion(bottom_up(publicables))
            calidad = pd.concat(
                [
                    controles_fuente(datos),
                    calidad_asof,
                    controles_predicciones(publicables),
                    # Se audita todo el torneo y no solo lo publicable.
                    controles_componentes(resultado.predicciones),
                    calidad_jerarquia,
                    calidad_fenologico,
                    monitorear_llegada_reales(resultado.predicciones, asof),
                ],
                ignore_index=True,
            )
            metricas_comparacion = pd.DataFrame()
            if tipo == "backtest":
                comparadores = [
                    "MacroLegacy_v1",
                    "HibridoLegacyResidual_v1",
                    "FenologicoComponentes_v1",
                ]
                partes_comparacion = []
                for modelo in comparadores:
                    parte = metricas_pareadas_modelos(
                        resultado.predicciones,
                        modelo_base="R09_publicado",
                        modelo_candidato=modelo,
                    )
                    if not parte.empty:
                        partes_comparacion.append(parte)
                if partes_comparacion:
                    metricas_comparacion = pd.concat(
                        partes_comparacion, ignore_index=True, sort=False
                    )
            zip_ruta, firma = exportar_paquete(
                tipo,
                datos,
                predicciones=publicables,
                metricas=resultado.metricas,
                decisiones=resultado.decisiones,
                calidad=calidad,
                evidencia_features=resultado.evidencia_features,
                registro_mlflow=registro_mlflow,
                explicaciones=explicaciones,
            )
            log_metricas_mlflow(resultado.metricas)
            if repo:
                repo.guardar_predicciones(run_id, publicables)
                repo.guardar_metricas(run_id, resultado.metricas)
                repo.guardar_metricas_comparacion(run_id, metricas_comparacion)
                repo.guardar_evidencia_features(run_id, resultado.evidencia_features)
                repo.guardar_calidad(snapshot_id, run_id, calidad)
                repo.guardar_artifacto(run_id, "audit_zip", zip_ruta, firma)
                repo.finalizar_run(run_id)
                # La decisión vigente se cambia al final; si falla una persistencia,
                # permanece visible la última decisión exitosa.
                if tipo == "backtest":
                    repo.guardar_decisiones(run_id, resultado.decisiones)
            try:
                import mlflow

                if mlflow.active_run():
                    mlflow.log_artifact(str(zip_ruta), artifact_path="audit")
            except ImportError:
                pass
            if tipo == "project":
                # project devuelve exactamente las filas que escribió como proyección vigente.
                resultado.predicciones = publicables
            return datos, resultado, run_id, zip_ruta
        except (Exception, KeyboardInterrupt) as exc:
            if repo and run_id:
                repo.finalizar_run(run_id, "failed", str(exc))
            raise


def ejecutar_backtest(args) -> int:
    datos, resultado, run_id, zip_ruta = _torneo(args, "backtest")
    _salida(
        run_id=run_id,
        fuente=datos.fuente.nombre,
        predicciones=len(resultado.predicciones),
        modelos=sorted(resultado.predicciones.modelo.unique()),
        decisiones=resultado.decisiones.to_dict("records"),
        advertencias=resultado.advertencias,
        artefacto=zip_ruta,
    )
    return 0


def ejecutar_train(args) -> int:
    datos, resultado, run_id, zip_ruta = _torneo(args, "train")
    _salida(
        run_id=run_id,
        fuente=datos.fuente.nombre,
        decisiones=resultado.decisiones.to_dict("records"),
        artefacto=zip_ruta,
    )
    return 0


def ejecutar_project(args) -> int:
    from ..proyeccion.calidad import controles_reconciliacion
    from ..proyeccion.reconciliacion import bottom_up

    datos, resultado, run_id, zip_ruta = _torneo(args, "project")
    proyeccion = resultado.predicciones.copy()
    jerarquia = bottom_up(proyeccion) if not proyeccion.empty else pd.DataFrame()
    calidad_jerarquia = (
        controles_reconciliacion(jerarquia) if not jerarquia.empty else pd.DataFrame()
    )
    _salida(
        run_id=run_id,
        fecha_emision=(proyeccion.fecha_emision.max() if not proyeccion.empty else None),
        lotes=len(proyeccion),
        reconciliacion=calidad_jerarquia.to_dict("records"),
        artefacto=zip_ruta,
    )
    return 0


def ejecutar_export(args) -> int:
    # Export mínimo reproducible del campeón R09, sin reentrenar challengers costosos.
    args.skip_ml = True
    args.skip_stats = True
    args.skip_componentes = True
    datos, resultado, run_id, zip_ruta = _torneo(args, "export")
    _salida(
        run_id=run_id,
        fuente=datos.fuente.nombre,
        artefacto=zip_ruta,
        nota="Export regenerado desde el snapshot actual.",
    )
    return 0
