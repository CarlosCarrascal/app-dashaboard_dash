from __future__ import annotations

import ast
import inspect
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from analitica.aplicacion.servicios import certificar_releases_replay as servicio
from analitica.aplicacion.servicios import certificar_releases_replay_certificacion as certificacion
from analitica.aplicacion.servicios import certificar_releases_replay_lectura as lectura
from analitica.aplicacion.servicios import certificar_releases_replay_persistencia as persistencia
from analitica.aplicacion.servicios import certificar_releases_replay_serializacion as serializacion
from analitica.interfaces.scripts import certificar_releases_replay as fachada

SCRIPT = Path(fachada.__file__)


def test_fachada_conserva_aliases_y_firmas_historicas() -> None:
    nombres = (
        "Any",
        "Certificacion",
        "CERTIFICACIONES",
        "Iterable",
        "RELEASE_OPERATIVA",
        "RUNS_RECHAZADOS",
        "Serie",
        "_filas",
        "_registrar_contrato",
        "_registrar_rechazos",
        "_registrar_release_operativa",
        "_registrar_releases",
        "_sha256",
        "_snapshot",
        "_universo",
        "ejecutar",
    )
    for nombre in nombres:
        alias = getattr(fachada, nombre)
        implementacion = getattr(servicio, nombre)
        assert alias is implementacion, nombre
        if callable(alias):
            assert inspect.signature(alias) == inspect.signature(implementacion)

    for nombre in (
        "argparse",
        "date",
        "dataclass",
        "hashlib",
        "json",
        "settings",
        "timedelta",
    ):
        assert getattr(fachada, nombre) is getattr(servicio, nombre)


def test_fachada_es_delgada_y_psycopg_sigue_lazy() -> None:
    arbol = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    assert [
        nodo.name
        for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ] == ["main"]
    assert not any(
        isinstance(nodo, (ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith))
        for nodo in ast.walk(arbol)
    )
    assert "psycopg" not in servicio.__dict__


def test_fachada_de_servicio_reexporta_las_fronteras_especializadas() -> None:
    assert servicio._sha256 is serializacion._sha256
    assert servicio._filas is lectura._filas
    assert servicio._snapshot is lectura._snapshot
    assert servicio._certificar_universo is certificacion._certificar_universo
    assert servicio._registrar_contrato is persistencia._registrar_contrato
    assert servicio._registrar_releases is persistencia._registrar_releases
    assert servicio._registrar_rechazos is persistencia._registrar_rechazos
    assert servicio._registrar_release_operativa is persistencia._registrar_release_operativa
    assert servicio._SQL_UNIVERSO == lectura._SQL_UNIVERSO
    assert servicio._SQL_OPERATIVA_PREDICCIONES == lectura._SQL_OPERATIVA_PREDICCIONES
    assert servicio._SQL_SNAPSHOT == lectura._SQL_SNAPSHOT
    assert servicio._SQL_SERIES_RECHAZADAS == lectura._SQL_SERIES_RECHAZADAS


def test_modulos_internos_no_importan_la_ruta_historica() -> None:
    for modulo in (certificacion, lectura, persistencia, serializacion):
        arbol = ast.parse(Path(modulo.__file__).read_text(encoding="utf-8"))
        assert not any(
            isinstance(nodo, ast.ImportFrom)
            and nodo.module
            and nodo.module.startswith("analitica.interfaces.scripts")
            for nodo in ast.walk(arbol)
        )


def test_universo_conserva_la_inyeccion_historica_de_lectura(monkeypatch) -> None:
    certificacion_actual = servicio.CERTIFICACIONES[0]
    llamadas: list[tuple[str, tuple[object, ...]]] = []
    resultado = {"keyset_sha256": "keyset-local"}

    def filas_falsas(_cursor, consulta: str, parametros) -> list[tuple[object, ...]]:
        llamadas.append((consulta, tuple(parametros)))
        return [(1,)]

    monkeypatch.setattr(servicio, "_filas", filas_falsas)
    monkeypatch.setattr(servicio, "_certificar_universo", lambda contrato, filas: resultado)

    assert servicio._universo(object(), certificacion_actual) is resultado
    assert len(llamadas) == len(certificacion_actual.series)
    assert all("FROM analytics.prediction" in consulta for consulta, _ in llamadas)
    assert all(parametros[4] == list(certificacion_actual.horizontes) for _, parametros in llamadas)


class _CursorFalso:
    def __init__(self, conexion: _ConexionFalsa) -> None:
        self.conexion = conexion
        self.ultima_consulta = ""
        self.ultimos_parametros: tuple[object, ...] = ()

    def __enter__(self) -> _CursorFalso:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, consulta: str, parametros: tuple[object, ...]) -> None:
        self.ultima_consulta = " ".join(consulta.split())
        self.ultimos_parametros = tuple(parametros)
        etiqueta = self._etiqueta_escritura()
        if etiqueta is not None:
            self.conexion.pendientes.append(etiqueta)

    def fetchone(self) -> tuple[int]:
        if self.ultima_consulta.startswith("SELECT snapshot_id"):
            return (int(self.ultimos_parametros[0]) + 1000,)
        if "RETURNING evaluation_contract_id" in self.ultima_consulta:
            self.conexion.siguiente_contrato += 1
            return (self.conexion.siguiente_contrato,)
        raise AssertionError(f"fetchone inesperado: {self.ultima_consulta}")

    def fetchall(self) -> list[tuple[object, ...]]:
        if "prediction_id" in self.ultima_consulta:
            return [
                (
                    1,
                    date(2026, 8, 20),
                    date(2026, 8, 24),
                    1,
                    "fuente",
                    10.0,
                    9.0,
                    11.0,
                    2.0,
                    3.0,
                    4.0,
                    "{}",
                )
            ]
        if self.ultima_consulta.startswith("SELECT DISTINCT campania"):
            run_id = self.ultimos_parametros[0]
            return [("C2026", f"Experimental_{run_id}", "v1")]
        raise AssertionError(f"fetchall inesperado: {self.ultima_consulta}")

    def _etiqueta_escritura(self) -> str | None:
        consulta = self.ultima_consulta
        if consulta.startswith("UPDATE"):
            return "operativa_withdraw" if "uso='operativo'" in consulta else "withdraw"
        if not consulta.startswith("INSERT"):
            return None
        if "INTO analytics.evaluation_contract" in consulta:
            return "rejected_contract" if "'rejected'" in consulta else "contract"
        if "'operativo', 'approved'" in consulta:
            return "operativa_release"
        if "'historico','rejected'" in consulta:
            return "rejected_release"
        if "INTO analytics.model_series_release" in consulta:
            return "release"
        raise AssertionError(f"INSERT inesperado: {consulta}")


class _ConexionFalsa:
    def __init__(self) -> None:
        self.pendientes: list[str] = []
        self.persistidos: list[str] = []
        self.revertidos: list[str] = []
        self.siguiente_contrato = 2000
        self.commits = 0
        self.rollbacks = 0
        self.cursor_falso = _CursorFalso(self)

    def __enter__(self) -> _ConexionFalsa:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> _CursorFalso:
        return self.cursor_falso

    def commit(self) -> None:
        self.commits += 1
        self.persistidos.extend(self.pendientes)
        self.pendientes.clear()

    def rollback(self) -> None:
        self.rollbacks += 1
        self.revertidos.extend(self.pendientes)
        self.pendientes.clear()


def _universo_falso(_cursor: object, cert: servicio.Certificacion) -> dict[str, object]:
    return {
        "fecha_inicio": date(2026, 8, 3),
        "fecha_fin": date(2026, 8, 10),
        "cerrado_hasta": date(2026, 8, 16),
        "semanas": [date(2026, 8, 3), date(2026, 8, 10)],
        "emisiones": [date(2026, 7, 27)],
        "keyset_sha256": f"keyset-{cert.run_id}",
        "closed_calendar_sha256": f"calendar-{cert.run_id}",
        "volumen_real_kg": 10.0,
        "n_unidades": 1,
        "n_emisiones": 1,
        "predicciones_sha256": {
            serie.modelo: f"prediction-{cert.run_id}-{serie.modelo}"
            for serie in cert.series
        },
    }


def _preparar_dobles(monkeypatch) -> _ConexionFalsa:
    conexion = _ConexionFalsa()
    monkeypatch.setattr(servicio.settings, "postgres_dsn", lambda: "postgresql://falso")
    monkeypatch.setattr(servicio, "_universo", _universo_falso)
    monkeypatch.setitem(
        sys.modules,
        "psycopg",
        SimpleNamespace(connect=lambda dsn: _conexion_para_dsn(dsn, conexion)),
    )
    return conexion


def _conexion_para_dsn(dsn: str, conexion: _ConexionFalsa) -> _ConexionFalsa:
    assert dsn == "postgresql://falso"
    return conexion


def test_dry_run_revierte_la_validacion_y_no_persiste_escrituras(monkeypatch) -> None:
    conexion = _preparar_dobles(monkeypatch)

    resultado = servicio.ejecutar(False)

    assert len(resultado) == len(servicio.CERTIFICACIONES) + 1
    assert conexion.commits == 0
    assert conexion.rollbacks == 1
    assert conexion.persistidos == []
    assert conexion.pendientes == []
    assert conexion.revertidos == ["operativa_withdraw", "operativa_release"]


def test_apply_conserva_el_orden_de_efectos_y_hace_un_commit(monkeypatch) -> None:
    conexion = _preparar_dobles(monkeypatch)

    servicio.ejecutar(True)

    esperado = []
    for cert in servicio.CERTIFICACIONES:
        esperado.append("contract")
        for _serie in cert.series:
            esperado.extend(("withdraw", "release"))
    esperado.extend(("operativa_withdraw", "operativa_release"))
    for _run_id in servicio.RUNS_RECHAZADOS:
        esperado.extend(("rejected_contract", "rejected_release"))

    assert conexion.persistidos == esperado
    assert conexion.commits == 1
    assert conexion.rollbacks == 0
    assert conexion.pendientes == []
