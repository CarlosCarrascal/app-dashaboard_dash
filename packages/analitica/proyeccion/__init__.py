"""Pronóstico temporal, evidencia y gobierno de modelos de Aqu Anqa."""

from importlib import import_module

_LAZY_ATTRS = {
    "DatosProyeccion": (".dominio.contratos", "DatosProyeccion"),
    "FuenteInfo": (".dominio.contratos", "FuenteInfo"),
    "ResultadoTorneo": (".dominio.contratos", "ResultadoTorneo"),
    "ProjectionConfig": (".aplicacion.procesos.engine", "ProjectionConfig"),
    "ProjectionNotReady": (".aplicacion.procesos.engine", "ProjectionNotReady"),
    "ProjectionScenario": (".aplicacion.procesos.engine", "ProjectionScenario"),
    "proyectar_desde_corte": (".aplicacion.procesos.engine", "proyectar_desde_corte"),
    "replay_historico_ciego": (".aplicacion.procesos.engine", "replay_historico_ciego"),
    "AdaptadorOpenMeteo": (".infraestructura.clima", "AdaptadorOpenMeteo"),
    "PronosticoClima": (".infraestructura.clima", "PronosticoClima"),
    "resolver_horizonte_climatico": (".infraestructura.clima", "resolver_horizonte_climatico"),
    "NOMBRE_MODELO_HIBRIDO": (".dominio.modelos.hibrido", "NOMBRE_MODELO"),
    "backtest_hibrido_v1": (".dominio.modelos.hibrido", "backtest_hibrido_v1"),
    "backtest_macro_legacy_v1": (".dominio.modelos.hibrido", "backtest_macro_legacy_v1"),
    "construir_curva_historica": (".dominio.modelos.hibrido", "construir_curva_historica"),
    "proyectar_hibrido_v1": (".dominio.modelos.hibrido", "proyectar_hibrido_v1"),
    "NOMBRE_MODELO_PARAMETROS_ASOF": (".aplicacion.parametros", "NOMBRE_MODELO"),
    "VERSION_MODELO_PARAMETROS_ASOF": (".aplicacion.parametros", "VERSION_MODELO"),
    "ConfiguracionParametrosAsOf": (".aplicacion.parametros", "ConfiguracionParametrosAsOf"),
    "aprender_desplazamiento": (".aplicacion.parametros", "aprender_desplazamiento"),
    "backtest_hibrido_parametros_asof": (
        ".aplicacion.parametros",
        "backtest_hibrido_parametros_asof",
    ),
    "construir_snapshot_parametros": (".aplicacion.parametros", "construir_snapshot_parametros"),
    "ejecutar_emision_parametros_asof": (
        ".aplicacion.parametros",
        "ejecutar_emision_parametros_asof",
    ),
    "normalizar_parametros_excel": (".aplicacion.parametros", "normalizar_parametros_excel"),
    "seleccionar_gdd_config": (".aplicacion.parametros", "seleccionar_gdd_config"),
    "seleccionar_peso_macro": (".aplicacion.parametros", "seleccionar_peso_macro"),
    "sha256_archivo": (".dominio.compartido", "sha256_archivo"),
    "cargar_parametros_historicos": (
        ".aplicacion.parametros.excel",
        "cargar_parametros_historicos",
    ),
    "cargar_parametros_libro": (".aplicacion.parametros.excel", "cargar_parametros_libro"),
    "seleccionar_libros_parametros": (
        ".aplicacion.parametros.excel",
        "seleccionar_libros_parametros",
    ),
    "EscenarioFenologico": (".dominio.modelos.fenologico", "EscenarioFenologico"),
    "ResultadoFenologico": (".dominio.modelos.fenologico", "ResultadoFenologico"),
    "aplicar_escenario_fenologico": (".dominio.modelos.fenologico", "aplicar_escenario_fenologico"),
    "backtest_fenologico_v1": (".dominio.modelos.fenologico", "backtest_fenologico_v1"),
    "proyectar_fenologico_v1": (".dominio.modelos.fenologico", "proyectar_fenologico_v1"),
    "metricas_pronostico": (".dominio.evaluacion.metricas", "metricas_pronostico"),
    "OccurrenceConfig": (".dominio.modelos.ocurrencia", "OccurrenceConfig"),
    "estimar_ocurrencia": (".dominio.modelos.ocurrencia", "estimar_ocurrencia"),
    "LoteParametrosProyeccion": (
        ".aplicacion.procesos.motor_proyeccion_semanal",
        "LoteParametrosProyeccion",
    ),
    "RegistroBDProy": (".aplicacion.procesos.motor_proyeccion_semanal", "RegistroBDProy"),
    "ajustar_dia_habil": (".aplicacion.procesos.motor_proyeccion_semanal", "ajustar_dia_habil"),
    "calcular_fechas_reingreso": (
        ".aplicacion.procesos.motor_proyeccion_semanal",
        "calcular_fechas_reingreso",
    ),
    "extraer_fechas_pasadas": (
        ".aplicacion.procesos.motor_proyeccion_semanal",
        "extraer_fechas_pasadas",
    ),
    "ejecutar_proyeccion_semanal_dataframe": (
        ".aplicacion.procesos.motor_proyeccion_semanal",
        "ejecutar_proyeccion_semanal_dataframe",
    ),
    "generar_matriz_resumen_pdi": (
        ".aplicacion.procesos.motor_proyeccion_semanal",
        "generar_matriz_resumen_pdi",
    ),
    "norm_cdf": (".aplicacion.procesos.motor_proyeccion_semanal", "norm_cdf"),
    "proyectar_lote_pasadas": (
        ".aplicacion.procesos.motor_proyeccion_semanal",
        "proyectar_lote_pasadas",
    ),
    "semana_iso_21": (".aplicacion.procesos.motor_proyeccion_semanal", "semana_iso_21"),
    "ResultadoValidacionOperativa": (".aplicacion.operativo", "ResultadoValidacionOperativa"),
    "validar_libro_operativo": (".aplicacion.operativo", "validar_libro_operativo"),
    "validar_libros_semana": (".aplicacion.operativo", "validar_libros_semana"),
    "banda_horizonte": (".dominio.versiones", "banda_horizonte"),
    "parsear_version": (".dominio.versiones", "parsear_version"),
    "construir_backtest_r09": (".aplicacion.procesos.backtest", "construir_backtest_r09"),
    "seleccionar_versiones_oficiales": (
        ".aplicacion.procesos.backtest",
        "seleccionar_versiones_oficiales",
    ),
    "LIBROS_OPERATIVOS": (".aplicacion.operativo", "LIBROS_OPERATIVOS"),
    "MODELO_OPERATIVO_ACTUAL": (".aplicacion.operativo", "MODELO_OPERATIVO_ACTUAL"),
    "construir_modelo_operativo_excel": (
        ".aplicacion.operativo",
        "construir_modelo_operativo_excel",
    ),
    "datos_proyeccion_operativo": (".aplicacion.operativo", "datos_proyeccion_operativo"),
    "seleccionar_libros_operativos": (".aplicacion.operativo", "seleccionar_libros_operativos"),
}


def __getattr__(name: str):
    try:
        modulo, atributo = _LAZY_ATTRS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    ruta = f"analitica{modulo}" if modulo.startswith(".") else modulo
    valor = getattr(import_module(ruta), atributo)
    globals()[name] = valor
    return valor


def __dir__():
    return sorted(set(globals()) | set(__all__) | set(_LAZY_ATTRS))


__all__ = [
    "DatosProyeccion",
    "FuenteInfo",
    "ResultadoTorneo",
    "ProjectionConfig",
    "ProjectionNotReady",
    "ProjectionScenario",
    "proyectar_desde_corte",
    "replay_historico_ciego",
    "NOMBRE_MODELO_HIBRIDO",
    "backtest_hibrido_v1",
    "backtest_macro_legacy_v1",
    "construir_curva_historica",
    "proyectar_hibrido_v1",
    "NOMBRE_MODELO_PARAMETROS_ASOF",
    "VERSION_MODELO_PARAMETROS_ASOF",
    "ConfiguracionParametrosAsOf",
    "backtest_hibrido_parametros_asof",
    "ejecutar_emision_parametros_asof",
    "construir_snapshot_parametros",
    "normalizar_parametros_excel",
    "seleccionar_peso_macro",
    "seleccionar_gdd_config",
    "aprender_desplazamiento",
    "sha256_archivo",
    "seleccionar_libros_parametros",
    "cargar_parametros_libro",
    "cargar_parametros_historicos",
    "OccurrenceConfig",
    "EscenarioFenologico",
    "ResultadoFenologico",
    "aplicar_escenario_fenologico",
    "AdaptadorOpenMeteo",
    "PronosticoClima",
    "resolver_horizonte_climatico",
    "backtest_fenologico_v1",
    "proyectar_fenologico_v1",
    "estimar_ocurrencia",
    "banda_horizonte",
    "construir_backtest_r09",
    "metricas_pronostico",
    "parsear_version",
    "seleccionar_versiones_oficiales",
    "LoteParametrosProyeccion",
    "RegistroBDProy",
    "norm_cdf",
    "semana_iso_21",
    "ajustar_dia_habil",
    "calcular_fechas_reingreso",
    "extraer_fechas_pasadas",
    "proyectar_lote_pasadas",
    "ejecutar_proyeccion_semanal_dataframe",
    "generar_matriz_resumen_pdi",
    "ResultadoValidacionOperativa",
    "validar_libro_operativo",
    "validar_libros_semana",
    "LIBROS_OPERATIVOS",
    "MODELO_OPERATIVO_ACTUAL",
    "construir_modelo_operativo_excel",
    "datos_proyeccion_operativo",
    "seleccionar_libros_operativos",
]
