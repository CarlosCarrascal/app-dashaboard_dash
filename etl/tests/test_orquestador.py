from aquanqa_etl.orquestador import (
    ContratoBloque,
    ContratoTabla,
    DeltaTabla,
    calcular_plan,
    huella_esquema_canonica,
)


def _contratos():
    tablas = (
        ContratoTabla("m_lotes", "B01_IDENTIDAD", "core"),
        ContratoTabla("m_evaluadores", "B02_CONTEXTO", "core"),
        ContratoTabla("e03_conteo_estados", "B03_FENOLOGIA", "core"),
        ContratoTabla("h00_volumen_campo", "B04_OPERACION", "core"),
        ContratoTabla("r08_forecast_campania", "B05_PRONOSTICO", "core"),
        ContratoTabla("h01_detalle_cosecha", "B06_PENDIENTES", "raw_only"),
    )
    bloques = (
        ContratoBloque("B01_IDENTIDAD", 1, ("m_lotes",), ()),
        ContratoBloque("B02_CONTEXTO", 2, ("m_evaluadores",), ("B01_IDENTIDAD",)),
        ContratoBloque(
            "B03_FENOLOGIA", 3, ("e03_conteo_estados",), ("B01_IDENTIDAD", "B02_CONTEXTO")
        ),
        ContratoBloque(
            "B04_OPERACION", 4, ("h00_volumen_campo",), ("B01_IDENTIDAD", "B02_CONTEXTO")
        ),
        ContratoBloque(
            "B05_PRONOSTICO", 5, ("r08_forecast_campania",), ("B01_IDENTIDAD", "B02_CONTEXTO")
        ),
        ContratoBloque("B06_PENDIENTES", 6, ("h01_detalle_cosecha",), (), False),
    )
    return tablas, bloques


def _deltas(**cambios):
    return {
        tabla: DeltaTabla(
            tabla,
            filas_anteriores=10,
            filas_actuales=10 + filas_nuevas,
            filas_nuevas=filas_nuevas,
        )
        for tabla, filas_nuevas in cambios.items()
    }


def _plan(cambios, *, anterior=1, objetivo=2, core_poblado=False, hashes=None):
    tablas, bloques = _contratos()
    hashes = hashes or {tabla.tabla_raw: "same" for tabla in tablas}
    deltas = {
        tabla.tabla_raw: DeltaTabla(tabla.tabla_raw, filas_anteriores=10, filas_actuales=10)
        for tabla in tablas
    }
    deltas.update(_deltas(**cambios))
    return calcular_plan(
        snapshot_objetivo_id=objetivo,
        snapshot_objetivo_estado="cargado",
        campania="C2026",
        modelo_version="modelo-test",
        snapshot_anterior_id=anterior,
        deltas=deltas,
        schema_hashes_objetivo=hashes,
        schema_hashes_anterior={tabla.tabla_raw: "same" for tabla in tablas},
        tablas_modelo=tablas,
        bloques_modelo=bloques,
        core_poblado=core_poblado,
    )


def test_cambio_operativo_calcula_prerequisitos_sin_arrastrar_hermanos():
    plan = _plan({"h00_volumen_campo": 2})

    assert plan.bloques_directos == ("B04_OPERACION",)
    assert plan.bloques_requeridos == ("B01_IDENTIDAD", "B02_CONTEXTO", "B04_OPERACION")
    assert plan.bloques_ejecucion == plan.bloques_requeridos
    assert "B03_FENOLOGIA" not in plan.bloques_requeridos
    assert "B05_PRONOSTICO" not in plan.bloques_requeridos


def test_cambio_en_maestro_invalida_todas_las_ramas():
    plan = _plan({"m_lotes": 1})

    assert plan.bloques_directos == ("B01_IDENTIDAD",)
    assert plan.bloques_requeridos == (
        "B01_IDENTIDAD",
        "B02_CONTEXTO",
        "B03_FENOLOGIA",
        "B04_OPERACION",
        "B05_PRONOSTICO",
    )


def test_core_poblado_fuerza_reconstruccion_completa_protegida():
    plan = _plan({"e03_conteo_estados": 1}, core_poblado=True)

    assert plan.estado == "requiere_reconstruccion_core"
    assert plan.requiere_reconstruccion_completa
    assert plan.bloques_ejecucion == (
        "B01_IDENTIDAD",
        "B02_CONTEXTO",
        "B03_FENOLOGIA",
        "B04_OPERACION",
        "B05_PRONOSTICO",
    )


def test_cambio_raw_only_no_dispara_core():
    plan = _plan({"h01_detalle_cosecha": 3}, core_poblado=True)

    assert plan.estado == "raw_only"
    assert plan.tablas_raw_only_cambiadas == ("h01_detalle_cosecha",)
    assert plan.bloques_directos == ()
    assert plan.bloques_ejecucion == ()


def test_cambio_de_esquema_se_detecta_sin_cambio_de_filas():
    hashes = {tabla.tabla_raw: "same" for tabla in _contratos()[0]}
    hashes["m_evaluadores"] = "nuevo-schema"
    plan = _plan({}, hashes=hashes)

    assert plan.tablas_cambiadas == ("m_evaluadores",)
    assert plan.tablas_schema_cambiado == ("m_evaluadores",)
    assert plan.bloques_directos == ("B02_CONTEXTO",)


def test_mismo_snapshot_es_no_op_aunque_el_delta_historico_tenga_filas():
    plan = _plan({"m_lotes": 20}, anterior=1, objetivo=1, core_poblado=True)

    assert plan.estado == "sin_cambios"
    assert plan.tablas_cambiadas == ()
    assert plan.bloques_ejecucion == ()


def test_hash_canonico_no_confunde_metadata_odbc_con_dao():
    odbc = [
        {
            "nombre": "Fundo",
            "tipo": "VARCHAR",
            "tipo_codigo": -9,
            "tamano": 50,
            "posicion": 1,
            "nullable": 1,
            "radix": None,
        },
        {
            "nombre": "Area",
            "tipo": "REAL",
            "tipo_codigo": 7,
            "tamano": 24,
            "posicion": 2,
        },
    ]
    dao = [
        {
            "nombre": "Fundo",
            "tipo": "10",
            "tamano": 50,
            "posicion": "0",
            "requerido": False,
            "atributos": 2,
        },
        {
            "nombre": "Area",
            "tipo": "6",
            "tamano": 4,
            "posicion": "1",
            "requerido": False,
        },
    ]

    assert huella_esquema_canonica(odbc) == huella_esquema_canonica(dao)
