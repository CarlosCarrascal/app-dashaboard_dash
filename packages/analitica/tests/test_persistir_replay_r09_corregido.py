from __future__ import annotations

import ast
import inspect
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from analitica.aplicacion.servicios import persistir_replay_r09_corregido as service
from analitica.interfaces.scripts import persistir_replay_r09_corregido as facade

SCRIPT = facade.__file__


def _real_sintetico() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "campania": "C2026",
                "lote_id": 101,
                "fecha_objetivo": pd.Timestamp("2026-01-05"),
                "empresa": "Aqu Anqa",
                "fundo": "Arena",
                "modulo": "M01",
                "lote": "L101",
                "real_kg": 100.0,
            },
            {
                "campania": "C2026",
                "lote_id": 102,
                "fecha_objetivo": pd.Timestamp("2026-01-05"),
                "empresa": "Aqu Anqa",
                "fundo": "Arena",
                "modulo": "M01",
                "lote": "L102",
                "real_kg": 60.0,
            },
        ]
    )


def _emitido_sintetico() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "modelo": service.MODELO_R09,
                "version_modelo": "R09_publicado_vintage_v1",
                "version_fuente": "S03",
                "campania": "C2026",
                "empresa": "Aqu Anqa",
                "fundo": "Arena",
                "modulo": "M01",
                "lote": "L101",
                "lote_id": 101,
                "fecha_emision": pd.Timestamp("2025-12-29"),
                "fecha_objetivo": pd.Timestamp("2026-01-05"),
                "horizonte_semanas": 1,
                "banda_horizonte": "operativo",
                "p50_kg": 80.0,
                "real_kg": 100.0,
                "origen_emision": pd.Timestamp("2025-12-29"),
            }
        ]
    )


def _base_sintetica() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "modelo": "MacroLegacy_v1",
                "version_modelo": "macro-v1",
                "campania": "C2026",
                "empresa": "Aqu Anqa",
                "fundo": "Arena",
                "modulo": "M01",
                "lote": "L101",
                "lote_id": 101,
                "fecha_emision": pd.Timestamp("2025-12-29"),
                "fecha_objetivo": pd.Timestamp("2026-01-05"),
                "horizonte_semanas": 1,
                "banda_horizonte": "operativo",
                "version_fuente": "macro-source",
                "p10_kg": 70.0,
                "p50_kg": 90.0,
                "p90_kg": 110.0,
                "real_kg": 100.0,
                "plantas": 10.0,
                "frutos_por_planta": 5.0,
                "peso_baya_g": 2.0,
                "confianza": "media",
                "componentes": {},
                "origen_emision": pd.Timestamp("2025-12-29"),
                "tipo_prediccion": "replay",
                "es_replay_ciego": True,
                "es_curva_stitched": True,
                "estado_evaluacion": "evaluada",
            }
        ]
    )


def test_fachada_conserva_aliases_firmas_y_es_delgada() -> None:
    aliases = (
        "argparse",
        "np",
        "pd",
        "settings",
        "RepositorioAnalytics",
        "metricas_cobertura_operacional",
        "metricas_pronostico",
        "MODELO_R09",
        "CONFIG_FUENTE",
        "_parsear_argumentos",
        "_leer_base",
        "_leer_r09_emitido",
        "_leer_real_universo",
        "_preparar_r09",
        "_metricas",
        "persistir",
    )
    for nombre in aliases:
        assert getattr(facade, nombre) is getattr(service, nombre), nombre
        if callable(getattr(facade, nombre)):
            assert inspect.signature(getattr(facade, nombre)) == inspect.signature(
                getattr(service, nombre)
            ), nombre

    assert not inspect.signature(facade.main).parameters
    with open(SCRIPT, encoding="utf-8") as archivo:
        arbol = ast.parse(archivo.read(), filename=SCRIPT)
    definiciones = [
        nodo.name
        for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assert definiciones == ["main"]
    assert not any(
        isinstance(nodo, (ast.For, ast.While, ast.Try, ast.With)) for nodo in ast.walk(arbol)
    )


def test_consultas_historicas_conservan_fuentes_filtros_y_contratos(monkeypatch) -> None:
    llamadas: list[tuple[str, object, object]] = []
    base_meta = pd.DataFrame([{"run_id": 71, "snapshot_id": 40}])
    base = _base_sintetica()

    def read_sql(query, conexion, params=None):
        llamadas.append((query, conexion, params))
        if len(llamadas) == 1:
            return base_meta
        return base

    monkeypatch.setattr(service.pd, "read_sql_query", read_sql)
    resultado = service._leer_base("conexion")
    assert resultado[:2] == (71, 40)
    assert llamadas[0][1:] == ("conexion", (service.CONFIG_FUENTE,))
    assert "tipo = 'backtest'" in llamadas[0][0]
    assert "HibridoOcurrenciaOnline_v2" in llamadas[0][0]
    assert "COALESCE(configuracion->>'r09_vintage_source', '') <> %s" in llamadas[0][0]
    assert "ORDER BY fin DESC NULLS LAST, run_id DESC" in llamadas[0][0]
    assert "FROM analytics.prediction" in llamadas[1][0]
    assert "WHERE run_id = %s AND modelo <> %s" in llamadas[1][0]
    assert llamadas[1][2] == (71, service.MODELO_R09)
    assert list(resultado[2].columns) == list(base.columns)

    consultas: list[str] = []

    def capture_sql(query, *_args, **_kwargs):
        consultas.append(query)
        return pd.DataFrame()

    monkeypatch.setattr(service.pd, "read_sql_query", capture_sql)
    service._leer_r09_emitido("conexion")
    service._leer_real_universo("conexion")
    assert "WITH versiones AS" in consultas[0]
    assert "r.version ~* '^S0*[0-9]+$'" in consultas[0]
    assert "WHERE r.numero_version <= r.semana" in consultas[0]
    assert "SELECT DISTINCT ON (modelo, campania, lote_id, fecha_objetivo)" in consultas[0]
    assert "horizonte_semanas ASC, fecha_emision DESC" in consultas[0]
    assert "SUM(h.kg)::double precision AS real_kg" in consultas[1]
    assert "GROUP BY h.campania, h.lote_id, date_trunc('week', h.fecha)::date" in consultas[1]


def test_reconstruccion_sintetica_conserva_universo_fechas_horizonte_y_columnas() -> None:
    real = _real_sintetico()
    emitido = _emitido_sintetico()

    desde_fachada = facade._preparar_r09(real, emitido)
    desde_servicio = service._preparar_r09(real, emitido)
    pd.testing.assert_frame_equal(desde_fachada, desde_servicio)

    columnas = [
        "modelo",
        "version_modelo",
        "campania",
        "empresa",
        "fundo",
        "modulo",
        "lote",
        "lote_id",
        "fecha_emision",
        "fecha_objetivo",
        "horizonte_semanas",
        "banda_horizonte",
        "version_fuente",
        "p10_kg",
        "p50_kg",
        "p90_kg",
        "real_kg",
        "plantas",
        "frutos_por_planta",
        "peso_baya_g",
        "confianza",
        "componentes",
        "origen_emision",
        "tipo_prediccion",
        "es_replay_ciego",
        "es_curva_stitched",
        "estado_evaluacion",
    ]
    assert list(desde_servicio.columns) == columnas
    assert len(desde_servicio) == 2
    assert desde_servicio.modelo.eq(service.MODELO_R09).all()
    emitida = desde_servicio.loc[desde_servicio.lote_id.eq(101)].iloc[0]
    ausente = desde_servicio.loc[desde_servicio.lote_id.eq(102)].iloc[0]
    assert emitida.p50_kg == 80.0
    assert emitida.version_fuente == "S03"
    assert ausente.p50_kg == 0.0
    assert ausente.version_fuente == "SIN_EMISION_R09"
    assert ausente.fecha_emision == pd.Timestamp("2025-12-29")
    assert ausente.origen_emision == ausente.fecha_emision
    assert ausente.horizonte_semanas == 0
    assert ausente.banda_horizonte == "operativo"
    assert ausente.componentes == {
        "referencia_publicada": True,
        "emitio_prediccion": False,
        "fuente_r09": service.CONFIG_FUENTE,
        "politica_variantes": "Sxx estándar; variantes excluidas",
        "ausencia_evaluada_como_cero": True,
    }


def test_reutilizacion_no_instancia_repositorio_ni_escribe(monkeypatch) -> None:
    eventos: list[tuple[object, ...]] = []

    class ConexionFalsa:
        def __enter__(self):
            eventos.append(("enter",))
            return self

        def __exit__(self, *_args):
            eventos.append(("exit",))

    def connect(dsn):
        eventos.append(("connect", dsn))
        return ConexionFalsa()

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))
    monkeypatch.setattr(service.settings, "postgres_dsn", lambda: "dsn-sintetico")
    monkeypatch.setattr(
        service.pd,
        "read_sql_query",
        lambda query, *_args, **_kwargs: pd.DataFrame([{"run_id": 902, "snapshot_id": 40}]),
    )

    class RepositorioProhibido:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("la reutilización no debe crear repositorio ni escribir")

    monkeypatch.setattr(service, "RepositorioAnalytics", RepositorioProhibido)
    assert service.persistir() == {"run_id": 902, "reused": True}
    assert eventos == [("connect", "dsn-sintetico"), ("enter",), ("exit",)]


def test_persistencia_sintetica_conserva_orden_configuracion_y_salida(monkeypatch) -> None:
    eventos: list[tuple[object, ...]] = []
    base_meta = pd.DataFrame([{"run_id": 71, "snapshot_id": 40}])
    base = _base_sintetica()
    real = _real_sintetico()
    emitido = _emitido_sintetico()

    class ConexionFalsa:
        def __enter__(self):
            eventos.append(("enter",))
            return self

        def __exit__(self, *_args):
            eventos.append(("exit",))

    def connect(dsn):
        eventos.append(("connect", dsn))
        return ConexionFalsa()

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))
    monkeypatch.setattr(service.settings, "postgres_dsn", lambda: "dsn-sintetico")

    def read_sql(query, *_args, **_kwargs):
        if "configuracion->>'r09_vintage_source' = %s" in query:
            return pd.DataFrame()
        if "COALESCE(configuracion->>'r09_vintage_source', '') <> %s" in query:
            return base_meta
        if "FROM analytics.prediction" in query:
            return base
        if "WITH versiones AS" in query:
            return emitido
        return real

    monkeypatch.setattr(service.pd, "read_sql_query", read_sql)
    monkeypatch.setattr(
        service, "_metricas", lambda _tabla: pd.DataFrame({"modelo": ["R09_publicado"]})
    )

    class RepositorioFalso:
        def __init__(self, dsn):
            eventos.append(("init", dsn))

        def crear_run(self, *args):
            eventos.append(("crear_run", *args))
            return 903

        def guardar_predicciones(self, *args):
            eventos.append(("guardar_predicciones", *args))

        def guardar_metricas(self, *args):
            eventos.append(("guardar_metricas", *args))

        def finalizar_run(self, *args):
            eventos.append(("finalizar_run", *args))

    monkeypatch.setattr(service, "RepositorioAnalytics", RepositorioFalso)
    resultado = service.persistir()

    assert resultado == {
        "run_id": 903,
        "base_run": 71,
        "filas": 3,
        "r09_filas": 2,
        "r09_emitidas": 1,
        "r09_sin_emision": 1,
        "campanias": ["C2026"],
    }
    assert [evento[0] for evento in eventos] == [
        "connect",
        "enter",
        "exit",
        "init",
        "crear_run",
        "guardar_predicciones",
        "guardar_metricas",
        "finalizar_run",
    ]
    configuracion = eventos[4][3]
    assert configuracion == {
        "base_run": 71,
        "r09": "referencia_publicada_no_algoritmo",
        "r09_vintage_source": service.CONFIG_FUENTE,
        "r09_variant_policy": "Sxx estándar; variantes excluidas",
        "r09_missing_policy": "SIN_EMISION_R09 explícito; p50=0 solo para WAPE operacional",
        "universo": "cosecha_real_completa_por_campania",
        "correccion": "reconstruccion_r09_sin_reentrenar_modelos",
    }
    assert eventos[-1] == ("finalizar_run", 903, "succeeded")


def test_fachada_preserva_formato_historico_de_reutilizacion(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["persistir_replay_r09_corregido"])
    monkeypatch.setattr(facade, "persistir", lambda: {"run_id": 904, "reused": True})

    facade.main()

    assert capsys.readouterr().out == '{"run_id": 904, "reused": true}\n'


@pytest.mark.parametrize("modulo", [facade, service])
def test_modulos_no_importan_psycopg_al_importarse(modulo) -> None:
    assert "psycopg" not in modulo.__dict__
