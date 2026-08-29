from __future__ import annotations

import dash
from dash import html

from components import ui
from pages.analitica._comun import (
    datos,
    estado_fuente,
    panel_fuentes,
    panel_glosario,
    tabla,
)

dash.register_page(
    __name__,
    path="/analitica/trazabilidad",
    name="Trazabilidad",
    order=7,
    grupo="Plataforma analítica",
)


def _resumen_calidad(calidad) -> html.Div:
    """Veredicto de los controles antes de la tabla: primero si algo falló, después el detalle."""
    if calidad is None or calidad.empty:
        return ui.semaforo("aviso", "Esta ejecución no dejó registro de controles.")
    conteo = calidad.estado.value_counts().to_dict() if "estado" in calidad else {}
    errores = int(conteo.get("error", 0))
    avisos = int(conteo.get("warning", 0))
    total = len(calidad)
    if errores:
        return ui.semaforo(
            "error",
            f"**{errores} de {total} controles encontraron un problema serio.** Los números "
            "de esta corrida no deberían usarse para decidir hasta revisarlos.",
        )
    if avisos:
        return ui.semaforo(
            "aviso",
            f"**{total} controles ejecutados: ninguno falló, {avisos} dejaron una "
            "advertencia.** Una advertencia no invalida la corrida; señala algo que conviene "
            "mirar, como datos incompletos en una parte del período.",
        )
    return ui.semaforo("ok", f"**Los {total} controles automáticos pasaron sin observaciones.**")


def layout():
    estado = datos()
    return html.Div(
        className="space-y-4",
        children=[
            ui.encabezado_pagina(
                "De dónde salió cada número",
                "Qué datos se usaron, cuándo se ejecutó el cálculo, con qué versión del "
                "código y qué controles se pasaron. Sirve para poder repetir exactamente el "
                "mismo resultado meses después.",
            ),
            estado_fuente(estado),
            ui.panel(
                "1 · Con qué datos se hizo el análisis",
                panel_fuentes(estado),
                ayuda="Fuentes reales de la corrida vigente, con sus conteos y su corte.",
            ),
            ui.panel(
                "2 · Ejecuciones registradas",
                tabla(
                    estado["runs"],
                    [
                        "run_id",
                        "tipo",
                        "estado",
                        "fuente",
                        "corte_datos",
                        "inicio",
                        "fin",
                        "firma_snapshot",
                        "codigo_commit",
                        "mlflow_run_id",
                    ],
                    limite=20,
                    vacio="Todavía no se ha ejecutado ningún análisis.",
                    como_leer=(
                        "Cada fila es una ejecución completa del análisis. **Datos hasta** "
                        "marca el corte: nada posterior a esa fecha entró en el cálculo, ni "
                        "siquiera si ya estaba cargado en la base.\n\n"
                        "La **huella de los datos** es la pieza que hace reproducible todo lo "
                        "demás. Dos ejecuciones con la misma huella partieron exactamente del "
                        "mismo material; si la huella cambia, los números pueden cambiar "
                        "aunque el código sea idéntico.\n\n"
                        "La **versión del código** cierra el círculo: con la huella y esa "
                        "versión se puede volver a producir el mismo resultado."
                    ),
                ),
                ayuda="Historial de ejecuciones con su corte de datos y su versión de código.",
            ),
            ui.panel(
                "3 · Controles automáticos",
                _resumen_calidad(estado["calidad"]),
                tabla(
                    estado["calidad"],
                    ["regla", "estado", "observados", "afectados", "detalle"],
                    limite=40,
                    vacio="Esta ejecución no dejó registro de controles.",
                    como_leer=(
                        "Cada control revisa una condición concreta antes de dar los "
                        "resultados por buenos: que el escenario bajo no supere al alto, que "
                        "no se haya colado información posterior a la fecha de emisión, que "
                        "los totales por fundo cuadren con la suma de sus lotes.\n\n"
                        "**Casos revisados** es cuántas filas miró el control y **casos con "
                        "problema** cuántas no cumplieron. Un control con cero casos con "
                        "problema es la situación normal, no una casualidad."
                    ),
                ),
                ayuda="Verificaciones que se ejecutan sobre los datos y los resultados.",
            ),
            ui.panel(
                "4 · Auditoría de ensamblaje del panel",
                tabla(
                    estado["ensamblaje"],
                    [
                        "paso",
                        "unidad_salida",
                        "tipo_union",
                        "validacion_union",
                        "filas_izquierda",
                        "filas_salida",
                        "filas_emparejadas",
                        "filas_solo_izquierda",
                        "filas_solo_derecha",
                        "filas_salida_duplicadas",
                        "factor_expansion",
                        "estado",
                        "detalle",
                    ],
                    limite=40,
                    vacio="La corrida vigente no dejó auditoría de ensamblaje.",
                    como_leer=(
                        "Cada fila representa un paso de integración. **Filas antes/después** "
                        "permite detectar expansión; **validación** indica la cardinalidad "
                        "permitida; y **filas duplicadas** debe ser cero. Las claves sin pareja "
                        "son cobertura faltante, no duplicación automática."
                    ),
                ),
                ayuda="Demuestra que las tablas se unieron sin inflar la unidad lote-semana.",
            ),
            ui.panel(
                "5 · Paquetes descargables de auditoría",
                tabla(
                    estado["artefactos"],
                    [
                        "run_id",
                        "tipo",
                        "artefacto",
                        "release_aprobada",
                        "creado_en",
                        "bytes",
                        "sha256",
                        "uri",
                    ],
                    limite=20,
                    vacio="Todavía no se ha generado ningún paquete de auditoría.",
                ),
                ui.parrafo(
                    "Cada ejecución deja un archivo comprimido que se sostiene solo: incluye "
                    "los datos de partida y su huella, las referencias científicas usadas, la "
                    "ficha del modelo, los parámetros, las métricas, las predicciones y el "
                    "detalle del entorno donde se calculó. La **huella del archivo** permite "
                    "comprobar que nadie lo modificó después de generarlo."
                ),
                ayuda="Archivos que permiten auditar una corrida sin acceso a la base.",
            ),
            panel_glosario(
                [
                    "run_id",
                    "tipo",
                    "firma_snapshot",
                    "corte_datos",
                    "codigo_commit",
                    "regla",
                    "sha256",
                ]
            ),
        ],
    )
