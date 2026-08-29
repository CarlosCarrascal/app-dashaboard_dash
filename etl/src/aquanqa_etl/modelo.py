"""Catálogo semántico y grafo de dependencias de la migración Access.

El catálogo físico de Access vive en cada snapshot (`raw.access_schema_catalog`). Este módulo
contiene la decisión semántica versionada: qué significa una fuente, cuál es su grano, qué
destinos son candidatos y qué relaciones todavía necesitan evidencia. No se infieren relaciones
por el prefijo del nombre y no se crean tablas de ``core`` a partir de este registro.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from aquanqa_etl.catalogo import CATALOGO_ACCESS
from aquanqa_etl.config import Config

MODELO_VERSION = "access-c2026-2026-08-28.v2"
"""Contrato semántico completo con destinos core prefijados semánticamente."""


@dataclass(frozen=True, slots=True)
class TablaModelo:
    tabla_raw: str
    bloque: str
    dominio: str
    rol: str
    grano: str
    decision: str
    stg_objetos: tuple[str, ...] = ()
    core_objetos: tuple[str, ...] = ()
    depende_de: tuple[str, ...] = ()
    claves_candidatas: tuple[tuple[str, ...], ...] = ()
    evidencia: tuple[str, ...] = ()
    notas: str = ""
    fuente_maestra: bool = False


@dataclass(frozen=True, slots=True)
class BloqueModelo:
    codigo: str
    orden: int
    nombre: str
    tablas_raw: tuple[str, ...]
    prerequisitos: tuple[str, ...] = ()
    cargable: bool = True
    notas: str = ""


@dataclass(frozen=True, slots=True)
class RelacionModelo:
    codigo: str
    padre_raw: str
    hijo_raw: str
    columnas_padre: tuple[str, ...]
    columnas_hijo: tuple[str, ...]
    cardinalidad_esperada: str
    metodo: str
    evidencia: tuple[str, ...] = ()
    estado: str = "candidata"
    notas: str = ""


def _tabla(
    tabla_raw: str,
    bloque: str,
    dominio: str,
    rol: str,
    grano: str,
    decision: str,
    *,
    stg: tuple[str, ...] = (),
    core: tuple[str, ...] = (),
    depende_de: tuple[str, ...] = (),
    claves: tuple[tuple[str, ...], ...] = (),
    evidencia: tuple[str, ...] = (),
    notas: str = "",
    fuente_maestra: bool = False,
) -> TablaModelo:
    return TablaModelo(
        tabla_raw=tabla_raw,
        bloque=bloque,
        dominio=dominio,
        rol=rol,
        grano=grano,
        decision=decision,
        stg_objetos=stg,
        core_objetos=core,
        depende_de=depende_de,
        claves_candidatas=claves,
        evidencia=evidencia,
        notas=notas,
        fuente_maestra=fuente_maestra,
    )


_EVIDENCIA_BASE = (
    "docs/historico-access/evidencia/02_esquema_tablas.txt",
    "docs/historico-access/evidencia/05_linaje_dependencias.txt",
)


TABLAS_MODELO: tuple[TablaModelo, ...] = (
    _tabla(
        "m_lotes",
        "B01_IDENTIDAD",
        "identidad",
        "maestro",
        "una fila por empresa/fundo físico, módulo, turno y lote",
        "core",
        stg=("stg.maestro_lote",),
        core=(
            "core.m_empresa",
            "core.m_fundo",
            "core.m_modulo",
            "core.m_turno",
            "core.m_variedad",
            "core.m_lote",
            "core.m_fundo_alias",
            "core.m_variedad_alias",
        ),
        claves=(("fundo_ppto", "modulo", "lote"), ("fundo", "modulo", "lote")),
        evidencia=(
            "docs/adr/0012-maestro-lotes-access-principal.md",
            "docs/seguimiento/18_diseccion_access_y_contrato_app_2026-08-27.md",
        ),
        notas=(
            "Access es el maestro primario. Fundo y FundoPPto tienen "
            "vocabularios distintos; no se unen por alias sin resolver."
        ),
        fuente_maestra=True,
    ),
    _tabla(
        "m_evaluadores",
        "B02_CONTEXTO",
        "identidad",
        "maestro",
        "una fila por DNI de evaluador",
        "core",
        stg=("stg.m_evaluadores",),
        core=("core.m_evaluador",),
        claves=(("dni",),),
        evidencia=_EVIDENCIA_BASE,
        notas="El DNI es la clave de identidad; Cod es un atributo, no la clave.",
    ),
    _tabla(
        "m_time",
        "B02_CONTEXTO",
        "tiempo",
        "referencia",
        "una fila por fecha de calendario con semana de evaluación",
        "core",
        stg=("stg.m_time",),
        core=("core.t_campania", "core.t_calendario", "core.t_semana_evaluacion"),
        claves=(("fecha",),),
        evidencia=_EVIDENCIA_BASE,
        notas="La campaña no se deriva solo por fecha porque las campañas pueden solaparse.",
    ),
    _tabla(
        "m_n_muestra",
        "B02_CONTEXTO",
        "calidad_muestreo",
        "referencia",
        "una fila por evaluación y ubicación, con dos granos observados",
        "core",
        stg=("stg.m_n_muestra",),
        core=("core.cfg_muestra_requerida",),
        depende_de=("m_lotes",),
        claves=(("evaluacion", "fundo", "modulo", "lote", "cortina", "hilera", "planta"),),
        evidencia=_EVIDENCIA_BASE,
        notas=(
            "La nulidad de cortina/hilera/planta puede ser parte del grano de lote; "
            "no se fuerza una única clave."
        ),
    ),
    _tabla(
        "m_poda",
        "B02_CONTEXTO",
        "fenologia",
        "evento_maestro",
        "una fila por campaña y lote podado",
        "core",
        stg=("stg.m_poda",),
        core=("core.evt_poda",),
        depende_de=("m_lotes", "m_time"),
        claves=(("campania", "fundo", "modulo", "lote"),),
        evidencia=_EVIDENCIA_BASE,
        notas="La poda es el origen del tiempo agronómico y de la campaña por lote.",
    ),
    _tabla(
        "m_equivalencia_elifab",
        "B02_CONTEXTO",
        "packing",
        "referencia",
        "una fila por productor de packing y empresa equivalente",
        "core",
        core=("core.m_productor_equivalencia",),
        claves=(("productor",),),
        evidencia=_EVIDENCIA_BASE,
        notas="Se conserva como vocabulario auxiliar; no se mezcla con el maestro de lotes.",
    ),
    _tabla(
        "e01_ramas",
        "B03_FENOLOGIA",
        "fenologia",
        "medicion",
        "una fila por rama medida, dentro de planta, ubicación y fecha",
        "core",
        stg=("stg.e01_ramas",),
        core=("core.ev_evaluacion_ramas", "core.ev_rama_medicion"),
        depende_de=("m_lotes", "m_evaluadores", "m_time"),
        claves=(("fecha", "fundo", "modulo", "lote", "cortina", "hilera", "planta", "num_ramas"),),
        evidencia=_EVIDENCIA_BASE,
        notas="La fuente combina cabecera de planta y detalle de rama; el destino se separa.",
    ),
    _tabla(
        "e02_conteo_flores",
        "B03_FENOLOGIA",
        "fenologia",
        "medicion",
        "una fila por planta, ubicación, fecha y posible item",
        "core",
        stg=("stg.e02_flores",),
        core=("core.ev_flores",),
        depende_de=("m_lotes", "m_evaluadores", "m_time"),
        claves=(("fecha", "fundo", "modulo", "lote", "cortina", "hilera", "planta", "item"),),
        evidencia=_EVIDENCIA_BASE,
        notas=(
            "No se fuerza unicidad si los valores reales no la soportan; "
            "los conflictos van a qua."
        ),
    ),
    _tabla(
        "e03_conteo_estados",
        "B03_FENOLOGIA",
        "fenologia",
        "medicion",
        "una fila por item, planta, ubicación y fecha",
        "core",
        stg=("stg.e03_estados",),
        core=("core.ev_estados",),
        depende_de=("m_lotes", "m_evaluadores", "m_time"),
        claves=(("item", "fecha", "fundo", "modulo", "lote", "cortina", "hilera", "planta"),),
        evidencia=_EVIDENCIA_BASE,
        notas="E1..E5 y Total son medidas; no forman parte de la identidad.",
    ),
    _tabla(
        "e04_brotes",
        "B03_FENOLOGIA",
        "fenologia",
        "medicion",
        "una fila por piso, planta, ubicación y fecha",
        "core",
        stg=("stg.e04_brotes",),
        core=("core.ev_brotes",),
        depende_de=("m_lotes", "m_evaluadores", "m_time"),
        claves=(("fecha", "piso", "fundo", "modulo", "lote", "cortina", "hilera", "planta"),),
        evidencia=_EVIDENCIA_BASE,
        notas="La fecha debe integrar la identidad; la PK de Access histórica la omitía.",
    ),
    _tabla(
        "e05_diametros_bayas",
        "B03_FENOLOGIA",
        "fenologia",
        "medicion",
        "una fila por baya medida, hilera y fecha",
        "core",
        stg=("stg.e05_bayas",),
        core=("core.ev_baya_medicion",),
        depende_de=("m_lotes", "m_time"),
        claves=(("fecha", "modulo", "lote", "cortina", "hilera", "diametro"),),
        evidencia=_EVIDENCIA_BASE,
        notas=(
            "Access no trae identificador de baya; nro_muestra se asigna en staging "
            "y queda documentado."
        ),
    ),
    _tabla(
        "e05_seguimiento",
        "B03_FENOLOGIA",
        "fenologia",
        "medicion_detalle",
        "una fila por planta y fecha con hasta 25 pares diámetro/estado",
        "core",
        stg=("stg.e05_seguimiento",),
        core=("core.ev_evaluacion_baya", "core.ev_baya_observacion"),
        depende_de=("m_lotes", "m_evaluadores", "m_time"),
        claves=(
            ("id_origen", "numero_muestra"),
            (
                "fecha",
                "fundo",
                "modulo",
                "lote",
                "cortina",
                "hilera",
                "planta",
                "numero_muestra",
            ),
        ),
        evidencia=_EVIDENCIA_BASE,
        notas="El formato ancho se conserva en raw y se desancha únicamente en staging.",
    ),
    _tabla(
        "h00_volumen_campo",
        "B04_OPERACION",
        "cosecha",
        "hecho",
        "una fila por campaña, fecha, fundo, variedad, módulo y lote",
        "core",
        stg=("stg.h00_cosecha",),
        core=("core.op_cosecha",),
        depende_de=("m_lotes", "m_time"),
        claves=(("campania", "fecha", "fundo", "variedad", "modulo", "lote"),),
        evidencia=_EVIDENCIA_BASE,
        notas="Se concilia con H01 antes de publicar cosecha.",
    ),
    _tabla(
        "h01_prod_historica",
        "B04_OPERACION",
        "cosecha",
        "hecho",
        "una fila por campaña, fecha, fundo, módulo, turno y lote",
        "core",
        stg=("stg.h01_cosecha",),
        core=("core.op_cosecha",),
        depende_de=("m_lotes", "m_time"),
        claves=(("campania", "fecha", "fundo", "modulo", "turno", "lote"),),
        evidencia=_EVIDENCIA_BASE,
        notas=(
            "Alimenta la misma entidad de cosecha que H00; no se duplica como tabla "
            "paralela sin conciliación."
        ),
    ),
    _tabla(
        "h02_bd_elifab",
        "B04_OPERACION",
        "packing",
        "hecho",
        "una fila por registro de clasificación y proceso de packing",
        "core",
        stg=("stg.h02_packing",),
        core=("core.op_packing",),
        depende_de=("m_equivalencia_elifab", "m_time"),
        claves=(("fecha_cosecha", "fecha_proceso", "modulo", "turno", "clases", "calibre"),),
        evidencia=_EVIDENCIA_BASE,
        notas="Lote es una nota del proceso; no se fuerza como lote de campo.",
    ),
    _tabla(
        "h05_clima",
        "B04_OPERACION",
        "clima",
        "observacion",
        "una fila por timestamp de estación y variables meteorológicas",
        "core",
        stg=("stg.h05_clima",),
        core=("core.op_clima",),
        depende_de=("m_time",),
        claves=(("fecha",),),
        evidencia=_EVIDENCIA_BASE,
        notas="La duplicación por recarga se deduplica con evidencia en qua; no se elimina de raw.",
    ),
    _tabla(
        "r08_forecast_campania",
        "B05_PRONOSTICO",
        "forecast",
        "hecho_versionado",
        "una fila por versión, campaña, módulo, turno y semana",
        "core",
        stg=("stg.r08_forecast",),
        core=("core.op_forecast_campania",),
        depende_de=("m_lotes", "m_time"),
        claves=(("version", "campania", "fundo_ppto", "modulo", "turno", "anio", "semana"),),
        evidencia=_EVIDENCIA_BASE,
        notas=(
            "Todas las versiones permanecen en raw; core publicará la versión "
            "operativa aprobada."
        ),
    ),
    _tabla(
        "r09_forecast_semanal",
        "B05_PRONOSTICO",
        "forecast",
        "hecho_versionado",
        "una fila por versión, campaña, lote y semana",
        "core",
        stg=("stg.r09_forecast",),
        core=("core.op_forecast_semanal",),
        depende_de=("m_lotes", "m_time"),
        claves=(("version", "campania", "modulo", "turno", "lote", "sem"),),
        evidencia=_EVIDENCIA_BASE,
        notas="Versiones S27, S27_v2 y S27_v3 no se deben sumar; se conservan como iteraciones.",
    ),
    _tabla(
        "h01_detalle_cosecha",
        "B06_PENDIENTES",
        "cosecha",
        "detalle_auxiliar",
        "pendiente de confirmar: detalle operativo de cosecha",
        "raw_only",
        depende_de=("m_lotes",),
        evidencia=_EVIDENCIA_BASE,
        notas="Se conserva íntegra en raw hasta definir grano, clave y conciliación con H00/H01.",
    ),
    _tabla(
        "m_presupuesto_mo",
        "B06_PENDIENTES",
        "planificacion",
        "referencia_auxiliar",
        "pendiente de confirmar: presupuesto semanal por evaluación",
        "raw_only",
        depende_de=("m_time",),
        evidencia=_EVIDENCIA_BASE,
        notas="No se inventa una entidad core mientras no exista contrato de negocio.",
    ),
    _tabla(
        "r08_forecast_campania_24",
        "B06_PENDIENTES",
        "forecast",
        "historico_auxiliar",
        "pendiente de confirmar: variante histórica de forecast de campaña",
        "raw_only",
        evidencia=_EVIDENCIA_BASE,
        notas="Se compara contra R08 actual antes de decidir integración por campaña o snapshot.",
    ),
    _tabla(
        "r08_forecast_campania_25",
        "B06_PENDIENTES",
        "forecast",
        "historico_auxiliar",
        "pendiente de confirmar: variante histórica de forecast de campaña",
        "raw_only",
        evidencia=_EVIDENCIA_BASE,
        notas="La diferencia de columnas impide asumir equivalencia 1:1.",
    ),
    _tabla(
        "r09_forecast_semanal_25",
        "B06_PENDIENTES",
        "forecast",
        "historico_auxiliar",
        "pendiente de confirmar: variante histórica de forecast semanal",
        "raw_only",
        evidencia=_EVIDENCIA_BASE,
        notas="Se conserva en raw hasta definir la relación entre versiones históricas y campaña.",
    ),
)


BLOQUES_MODELO: tuple[BloqueModelo, ...] = (
    BloqueModelo(
        "B01_IDENTIDAD",
        1,
        "Identidad y maestro de lotes",
        ("m_lotes",),
        notas="Access M_Lotes es la fuente primaria; Excel solo se compara.",
    ),
    BloqueModelo(
        "B02_CONTEXTO",
        2,
        "Tiempo, evaluadores, poda y muestreo",
        ("m_evaluadores", "m_time", "m_n_muestra", "m_poda", "m_equivalencia_elifab"),
        prerequisitos=("B01_IDENTIDAD",),
    ),
    BloqueModelo(
        "B03_FENOLOGIA",
        3,
        "Evaluaciones E01–E05",
        (
            "e01_ramas",
            "e02_conteo_flores",
            "e03_conteo_estados",
            "e04_brotes",
            "e05_diametros_bayas",
            "e05_seguimiento",
        ),
        prerequisitos=("B01_IDENTIDAD", "B02_CONTEXTO"),
    ),
    BloqueModelo(
        "B04_OPERACION",
        4,
        "Cosecha, packing y clima",
        ("h00_volumen_campo", "h01_prod_historica", "h02_bd_elifab", "h05_clima"),
        prerequisitos=("B01_IDENTIDAD", "B02_CONTEXTO"),
    ),
    BloqueModelo(
        "B05_PRONOSTICO",
        5,
        "Forecast R08 y R09 vigente",
        ("r08_forecast_campania", "r09_forecast_semanal"),
        prerequisitos=("B01_IDENTIDAD", "B02_CONTEXTO"),
    ),
    BloqueModelo(
        "B06_PENDIENTES",
        6,
        "Fuentes conservadas en raw hasta decisión",
        (
            "h01_detalle_cosecha",
            "m_presupuesto_mo",
            "r08_forecast_campania_24",
            "r08_forecast_campania_25",
            "r09_forecast_semanal_25",
        ),
        prerequisitos=(),
        cargable=False,
        notas="raw_only no es una pérdida: significa fuente preservada sin destino core aprobado.",
    ),
)


def _rel(
    codigo: str,
    padre: str,
    hijo: str,
    columnas_padre: tuple[str, ...],
    columnas_hijo: tuple[str, ...],
    cardinalidad: str,
    metodo: str,
    *,
    notas: str = "",
) -> RelacionModelo:
    return RelacionModelo(
        codigo=codigo,
        padre_raw=padre,
        hijo_raw=hijo,
        columnas_padre=columnas_padre,
        columnas_hijo=columnas_hijo,
        cardinalidad_esperada=cardinalidad,
        metodo=metodo,
        evidencia=_EVIDENCIA_BASE,
        notas=notas,
    )


RELACIONES_MODELO: tuple[RelacionModelo, ...] = (
    _rel(
        "REL_EVAL_E01",
        "m_evaluadores",
        "e01_ramas",
        ("dni",),
        ("evaluador",),
        "1:N",
        "directa_trim",
    ),
    _rel(
        "REL_EVAL_E02",
        "m_evaluadores",
        "e02_conteo_flores",
        ("dni",),
        ("evaluador",),
        "1:N",
        "directa_trim",
    ),
    _rel(
        "REL_EVAL_E03",
        "m_evaluadores",
        "e03_conteo_estados",
        ("dni",),
        ("evaluador",),
        "1:N",
        "directa_trim",
    ),
    _rel(
        "REL_EVAL_E04",
        "m_evaluadores",
        "e04_brotes",
        ("dni",),
        ("evaluador",),
        "1:N",
        "directa_trim",
    ),
    _rel(
        "REL_EVAL_E05",
        "m_evaluadores",
        "e05_seguimiento",
        ("dni",),
        ("evaluador",),
        "1:N",
        "directa_trim",
    ),
    _rel(
        "REL_TIME_E01", "m_time", "e01_ramas", ("fecha",), ("fecha",), "1:N", "directa_fecha"
    ),
    _rel(
        "REL_TIME_E02",
        "m_time",
        "e02_conteo_flores",
        ("fecha",),
        ("fecha",),
        "1:N",
        "directa_fecha",
    ),
    _rel(
        "REL_TIME_E03",
        "m_time",
        "e03_conteo_estados",
        ("fecha",),
        ("fecha",),
        "1:N",
        "directa_fecha",
    ),
    _rel(
        "REL_TIME_E04", "m_time", "e04_brotes", ("fecha",), ("fecha",), "1:N", "directa_fecha"
    ),
    _rel(
        "REL_TIME_E05", "m_time", "e05_seguimiento", ("fecha",), ("fecha",), "1:N", "directa_fecha"
    ),
    _rel(
        "REL_TIME_H00",
        "m_time",
        "h00_volumen_campo",
        ("fecha",),
        ("fecha",),
        "1:N",
        "directa_fecha",
    ),
    _rel(
        "REL_TIME_H01",
        "m_time",
        "h01_prod_historica",
        ("fecha",),
        ("fecha",),
        "1:N",
        "directa_fecha",
    ),
    _rel(
        "REL_TIME_H05", "m_time", "h05_clima", ("fecha",), ("fecha",), "1:N", "directa_timestamp"
    ),
    _rel(
        "REL_LOTES_E01",
        "m_lotes",
        "e01_ramas",
        ("fundo_ppto", "modulo", "lote"),
        ("fundo", "modulo", "lote"),
        "1:N",
        "normalizacion_ubicacion",
        notas=(
            "Los vocabularios de fundo no son equivalentes sin mapa de identidad."
        ),
    ),
    _rel(
        "REL_LOTES_E02",
        "m_lotes",
        "e02_conteo_flores",
        ("fundo_ppto", "modulo", "lote"),
        ("fundo", "modulo", "lote"),
        "1:N",
        "normalizacion_ubicacion",
    ),
    _rel(
        "REL_LOTES_E03",
        "m_lotes",
        "e03_conteo_estados",
        ("fundo_ppto", "modulo", "lote"),
        ("fundo", "modulo", "lote"),
        "1:N",
        "normalizacion_ubicacion",
    ),
    _rel(
        "REL_LOTES_E04",
        "m_lotes",
        "e04_brotes",
        ("fundo_ppto", "modulo", "lote"),
        ("fundo", "modulo", "lote"),
        "1:N",
        "normalizacion_ubicacion",
    ),
    _rel(
        "REL_LOTES_E05",
        "m_lotes",
        "e05_seguimiento",
        ("fundo_ppto", "modulo", "lote"),
        ("fundo", "modulo", "lote"),
        "1:N",
        "normalizacion_ubicacion",
    ),
    _rel(
        "REL_LOTES_H00",
        "m_lotes",
        "h00_volumen_campo",
        ("fundo_ppto", "modulo", "lote"),
        ("fundo", "modulo", "lote"),
        "1:N",
        "normalizacion_ubicacion",
    ),
    _rel(
        "REL_LOTES_H01",
        "m_lotes",
        "h01_prod_historica",
        ("fundo_ppto", "modulo", "lote"),
        ("fundo", "modulo", "lote"),
        "1:N",
        "normalizacion_ubicacion",
    ),
    _rel(
        "REL_LOTES_PODA",
        "m_lotes",
        "m_poda",
        ("fundo_ppto", "modulo", "lote"),
        ("fundo", "modulo", "lote"),
        "1:N",
        "normalizacion_ubicacion",
    ),
    _rel(
        "REL_LOTES_MUESTRA",
        "m_lotes",
        "m_n_muestra",
        ("fundo_ppto", "modulo", "lote"),
        ("fundo", "modulo", "lote"),
        "1:N",
        "normalizacion_ubicacion",
    ),
    _rel(
        "REL_LOTES_R09",
        "m_lotes",
        "r09_forecast_semanal",
        ("fundo_ppto", "modulo", "lote"),
        ("fundo", "modulo", "lote"),
        "1:N",
        "normalizacion_ubicacion",
    ),
    _rel(
        "REL_EQUIV_H02",
        "m_equivalencia_elifab",
        "h02_bd_elifab",
        ("productor",),
        ("productor",),
        "1:N",
        "directa_trim",
    ),
)


def _registro(valor: Any) -> Any:
    if isinstance(valor, tuple):
        return [_registro(item) for item in valor]
    if isinstance(valor, dict):
        return {key: _registro(item) for key, item in valor.items()}
    return valor


def payload_modelo(modelo_version: str = MODELO_VERSION) -> dict[str, Any]:
    return {
        "modelo_version": modelo_version,
        "tablas": [_registro(asdict(tabla)) for tabla in TABLAS_MODELO],
        "bloques": [_registro(asdict(bloque)) for bloque in BLOQUES_MODELO],
        "relaciones": [_registro(asdict(relacion)) for relacion in RELACIONES_MODELO],
    }


def hash_modelo(modelo_version: str = MODELO_VERSION) -> str:
    contenido = json.dumps(
        payload_modelo(modelo_version), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(contenido).hexdigest()


def validar_modelo() -> None:
    """Falla temprano si el contrato semántico no cubre exactamente las fuentes Access."""
    fuentes = {tabla.destino for tabla in CATALOGO_ACCESS}
    modelo = {tabla.tabla_raw for tabla in TABLAS_MODELO}
    if fuentes != modelo:
        raise ValueError(
            "El modelo semántico no cubre exactamente CATALOGO_ACCESS: "
            f"faltan={sorted(fuentes - modelo)}, sobran={sorted(modelo - fuentes)}"
        )
    bloques = {bloque.codigo for bloque in BLOQUES_MODELO}
    if len(bloques) != len(BLOQUES_MODELO):
        raise ValueError("Hay códigos de bloque repetidos en el modelo semántico.")
    apariciones: list[str] = [tabla for bloque in BLOQUES_MODELO for tabla in bloque.tablas_raw]
    if set(apariciones) != fuentes or len(apariciones) != len(set(apariciones)):
        raise ValueError("Cada fuente Access debe pertenecer a un único bloque semántico.")
    for tabla in TABLAS_MODELO:
        if tabla.bloque not in bloques:
            raise ValueError(f"{tabla.tabla_raw} apunta a un bloque inexistente: {tabla.bloque}")
        if tabla.decision not in {"core", "raw_only"}:
            raise ValueError(f"Decisión inválida para {tabla.tabla_raw}: {tabla.decision}")
        if tabla.decision == "raw_only" and tabla.core_objetos:
            raise ValueError(f"{tabla.tabla_raw} es raw_only pero declara destinos core.")
    for relacion in RELACIONES_MODELO:
        if relacion.padre_raw not in fuentes or relacion.hijo_raw not in fuentes:
            raise ValueError(f"Relación {relacion.codigo} referencia una fuente inexistente.")
        if len(relacion.columnas_padre) != len(relacion.columnas_hijo):
            raise ValueError(f"Relación {relacion.codigo} tiene columnas desparejas.")
        if relacion.estado not in {"candidata", "aprobada", "rechazada", "bloqueada"}:
            raise ValueError(f"Estado de relación inválido: {relacion.estado}")


def tabla_modelo(tabla_raw: str) -> TablaModelo:
    validar_modelo()
    for tabla in TABLAS_MODELO:
        if tabla.tabla_raw == tabla_raw:
            return tabla
    raise KeyError(tabla_raw)


def bloque_modelo(codigo: str) -> BloqueModelo:
    for bloque in BLOQUES_MODELO:
        if bloque.codigo == codigo:
            return bloque
    raise KeyError(codigo)


def exportar_modelo(ruta: Path, modelo_version: str = MODELO_VERSION) -> Path:
    validar_modelo()
    ruta = ruta.expanduser().resolve()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(
            {**payload_modelo(modelo_version), "hash_modelo": hash_modelo(modelo_version)},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return ruta


def registrar_modelo(config: Config, modelo_version: str = MODELO_VERSION) -> dict[str, Any]:
    """Registra el contrato en raw sin cargar ni modificar datos de negocio."""
    validar_modelo()
    if config.pg_database != "aquanqa_migracion":
        raise RuntimeError(
            "El catálogo semántico solo puede registrarse en aquanqa_migracion; "
            f"base recibida: {config.pg_database}."
        )

    import psycopg

    modelo_hash = hash_modelo(modelo_version)
    with psycopg.connect(config.dsn, autocommit=False) as conexion:
        with conexion.cursor() as cur:
            cur.execute(
                """
                SELECT hash_modelo
                FROM raw.migracion_modelo_version
                WHERE modelo_version = %s
                """,
                (modelo_version,),
            )
            existente = cur.fetchone()
            if existente and str(existente[0]) != modelo_hash:
                raise RuntimeError(
                    f"La versión de modelo {modelo_version} ya existe con otro hash; "
                    "cree una nueva versión para preservar trazabilidad."
                )
            cur.execute(
                """
                UPDATE raw.migracion_modelo_version
                   SET vigente = false, actualizado_en = now()
                 WHERE vigente AND modelo_version <> %s
                """,
                (modelo_version,),
            )
            cur.execute(
                """
                INSERT INTO raw.migracion_modelo_version
                    (
                        modelo_version, hash_modelo, estado, vigente, descripcion,
                        contrato, aprobado_en
                    )
                VALUES (%s, %s, 'aprobado', true, %s, %s::jsonb, now())
                ON CONFLICT (modelo_version) DO UPDATE SET
                    estado = 'aprobado',
                    vigente = true,
                    descripcion = EXCLUDED.descripcion,
                    contrato = EXCLUDED.contrato,
                    aprobado_en = coalesce(raw.migracion_modelo_version.aprobado_en, now()),
                    actualizado_en = now()
                """,
                (
                    modelo_version,
                    modelo_hash,
                    "Contrato semántico completo Access → raw/stg/core por bloques.",
                    json.dumps(payload_modelo(modelo_version), ensure_ascii=False),
                ),
            )
            for bloque in BLOQUES_MODELO:
                cur.execute(
                    """
                    INSERT INTO raw.migracion_modelo_bloque
                        (modelo_version, bloque, orden, nombre, tablas_raw,
                         prerequisitos, cargable, notas)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (modelo_version, bloque) DO UPDATE SET
                        orden = EXCLUDED.orden,
                        nombre = EXCLUDED.nombre,
                        tablas_raw = EXCLUDED.tablas_raw,
                        prerequisitos = EXCLUDED.prerequisitos,
                        cargable = EXCLUDED.cargable,
                        notas = EXCLUDED.notas,
                        actualizado_en = now()
                    """,
                    (
                        modelo_version,
                        bloque.codigo,
                        bloque.orden,
                        bloque.nombre,
                        list(bloque.tablas_raw),
                        list(bloque.prerequisitos),
                        bloque.cargable,
                        bloque.notas,
                    ),
                )
            for tabla in TABLAS_MODELO:
                cur.execute(
                    """
                    INSERT INTO raw.migracion_modelo_tabla
                        (modelo_version, tabla_raw, bloque, dominio, rol, grano,
                         decision, stg_objetos, core_objetos, depende_de,
                         claves_candidatas, evidencia, notas, fuente_maestra, estado)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s::jsonb, %s, %s, %s, 'aprobado')
                    ON CONFLICT (modelo_version, tabla_raw) DO UPDATE SET
                        bloque = EXCLUDED.bloque,
                        dominio = EXCLUDED.dominio,
                        rol = EXCLUDED.rol,
                        grano = EXCLUDED.grano,
                        decision = EXCLUDED.decision,
                        stg_objetos = EXCLUDED.stg_objetos,
                        core_objetos = EXCLUDED.core_objetos,
                        depende_de = EXCLUDED.depende_de,
                        claves_candidatas = EXCLUDED.claves_candidatas,
                        evidencia = EXCLUDED.evidencia,
                        notas = EXCLUDED.notas,
                        fuente_maestra = EXCLUDED.fuente_maestra,
                        estado = 'aprobado',
                        actualizado_en = now()
                    """,
                    (
                        modelo_version,
                        tabla.tabla_raw,
                        tabla.bloque,
                        tabla.dominio,
                        tabla.rol,
                        tabla.grano,
                        tabla.decision,
                        list(tabla.stg_objetos),
                        list(tabla.core_objetos),
                        list(tabla.depende_de),
                        json.dumps(
                            [list(clave) for clave in tabla.claves_candidatas], ensure_ascii=False
                        ),
                        list(tabla.evidencia),
                        tabla.notas,
                        tabla.fuente_maestra,
                    ),
                )
            for relacion in RELACIONES_MODELO:
                cur.execute(
                    """
                    INSERT INTO raw.migracion_modelo_relacion
                        (modelo_version, codigo, padre_raw, hijo_raw,
                         columnas_padre, columnas_hijo, cardinalidad_esperada,
                         metodo, evidencia, estado, notas)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (modelo_version, codigo) DO UPDATE SET
                        padre_raw = EXCLUDED.padre_raw,
                        hijo_raw = EXCLUDED.hijo_raw,
                        columnas_padre = EXCLUDED.columnas_padre,
                        columnas_hijo = EXCLUDED.columnas_hijo,
                        cardinalidad_esperada = EXCLUDED.cardinalidad_esperada,
                        metodo = EXCLUDED.metodo,
                        evidencia = EXCLUDED.evidencia,
                        estado = CASE
                            WHEN raw.migracion_modelo_relacion.estado = 'aprobada'
                            THEN raw.migracion_modelo_relacion.estado
                            ELSE EXCLUDED.estado
                        END,
                        notas = EXCLUDED.notas,
                        actualizado_en = now()
                    """,
                    (
                        modelo_version,
                        relacion.codigo,
                        relacion.padre_raw,
                        relacion.hijo_raw,
                        list(relacion.columnas_padre),
                        list(relacion.columnas_hijo),
                        relacion.cardinalidad_esperada,
                        relacion.metodo,
                        list(relacion.evidencia),
                        relacion.estado,
                        relacion.notas,
                    ),
                )
            # El run ya abierto antes de registrar el contrato queda enlazado al modelo exacto.
            cur.execute(
                """
                UPDATE raw.migracion_run
                   SET modelo_version = %s
                 WHERE modelo_version IS NULL
                   AND source_snapshot_id IN (
                       SELECT source_snapshot_id
                       FROM raw.source_snapshot
                       WHERE tipo = 'access'
                   )
                """,
                (modelo_version,),
            )
            # migracion_tabla está protegida por un trigger para que sus estados
            # solo cambien mediante el procedimiento de gobierno. Aquí no se
            # cambia el estado ni los conteos: únicamente se enlaza cada fila
            # histórica al contrato semántico recién registrado. Se habilita la
            # misma bandera transaccional que usan las rutinas oficiales.
            cur.execute("SELECT set_config('raw.migracion_control', 'on', true)")
            cur.execute(
                """
                UPDATE raw.migracion_tabla mt
                   SET modelo_version = m.modelo_version,
                       bloque = m.bloque,
                       decision_modelo = m.decision
                  FROM raw.migracion_modelo_tabla m
                 WHERE m.modelo_version = %s
                   AND mt.tabla_raw = m.tabla_raw
                   AND mt.modelo_version IS NULL
                """,
                (modelo_version,),
            )
        conexion.commit()
    return {
        "modelo_version": modelo_version,
        "hash_modelo": modelo_hash,
        "tablas": len(TABLAS_MODELO),
        "bloques": len(BLOQUES_MODELO),
        "relaciones": len(RELACIONES_MODELO),
    }


__all__ = [
    "BLOQUES_MODELO",
    "MODELO_VERSION",
    "RELACIONES_MODELO",
    "TABLAS_MODELO",
    "BloqueModelo",
    "RelacionModelo",
    "TablaModelo",
    "bloque_modelo",
    "exportar_modelo",
    "hash_modelo",
    "payload_modelo",
    "registrar_modelo",
    "tabla_modelo",
    "validar_modelo",
]
