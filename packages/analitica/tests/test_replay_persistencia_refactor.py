"""Contratos locales de la extracción de certificación y persistencia."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from analitica.aplicacion.procesos.candidatos import json_reproducible
from analitica.aplicacion.servicios import certificar_releases_replay as cert
from analitica.aplicacion.servicios import persistir_hibrido_parametros_asof as hpa
from analitica.interfaces.scripts import certificar_releases_replay as cert_fachada
from analitica.interfaces.scripts import persistir_hibrido_parametros_asof as hpa_fachada


def _secciones(ruta: Path) -> list[str]:
    fuente = ruta.read_text(encoding="utf-8")
    return [
        marca
        for marca in (
            "# Contratos",
            "# Serialización",
            "# Consultas",
            "# Certificación",
        )
        if marca in fuente
    ]


def test_las_fronteras_fisicas_y_las_fachadas_se_conservan() -> None:
    for modulo in (cert, hpa):
        arbol = ast.parse(Path(modulo.__file__).read_text(encoding="utf-8"))
        imports_scripts = [
            nodo
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.ImportFrom)
            and nodo.module
            and nodo.module.startswith("analitica.interfaces.scripts")
        ]
        assert not imports_scripts

    assert _secciones(Path(cert.__file__)) == [
        "# Contratos",
        "# Serialización",
        "# Consultas",
        "# Certificación",
    ]
    assert _secciones(Path(hpa.__file__)) == [
        "# Contratos",
        "# Serialización",
        "# Consultas",
        "# Certificación",
    ]
    assert cert_fachada.ejecutar is cert.ejecutar
    assert hpa_fachada.ejecutar is hpa.ejecutar
    assert inspect.signature(cert_fachada.ejecutar) == inspect.signature(cert.ejecutar)
    assert inspect.signature(hpa_fachada.ejecutar) == inspect.signature(hpa.ejecutar)


def test_certificacion_separa_lectura_de_validacion(monkeypatch: pytest.MonkeyPatch) -> None:
    certificacion = cert.CERTIFICACIONES[0]
    llamadas: list[tuple[str, tuple[object, ...]]] = []
    resultado = {"keyset_sha256": "keyset-local"}

    def filas_falsas(_cursor, consulta: str, parametros) -> list[tuple[object, ...]]:
        llamadas.append((consulta, tuple(parametros)))
        return [(1,)]

    monkeypatch.setattr(cert, "_filas", filas_falsas)
    monkeypatch.setattr(cert, "_certificar_universo", lambda contrato, filas: resultado)

    assert cert._universo(object(), certificacion) is resultado
    assert len(llamadas) == len(certificacion.series)
    assert all("FROM analytics.prediction" in consulta for consulta, _ in llamadas)
    assert all(parametros[4] == list(certificacion.horizontes) for _, parametros in llamadas)


def test_serializacion_de_firmas_es_reproducible() -> None:
    valor = {"b": [2, 1], "a": "valor"}
    esperado = hashlib.sha256(json_reproducible(valor).encode("utf-8")).hexdigest()

    assert hpa._hash_json(valor) == esperado
    assert json.loads(hpa._serializar_json(valor)) == valor


def test_persistencia_extraida_conserva_orden_y_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    eventos: list[tuple[object, ...]] = []

    class RepositorioFalso:
        def __init__(self, dsn: str) -> None:
            eventos.append(("init", dsn))

        def snapshot(self, _datos) -> int:
            eventos.append(("snapshot",))
            return 41

        def crear_run(self, snapshot_id: int, tipo: str, configuracion: dict) -> int:
            eventos.append(("crear_run", snapshot_id, tipo, configuracion))
            return 901

        def guardar_predicciones(self, run_id: int, _tabla: pd.DataFrame) -> None:
            eventos.append(("guardar_predicciones", run_id))

        def guardar_metricas(self, run_id: int, _tabla: pd.DataFrame) -> None:
            eventos.append(("guardar_metricas", run_id))
            raise RuntimeError("fallo sintetico")

        def finalizar_run(self, *args: object) -> None:
            eventos.append(("finalizar_run", *args))

    monkeypatch.setattr(hpa, "RepositorioAnalytics", RepositorioFalso)
    monkeypatch.setattr(
        hpa,
        "metricas_pronostico",
        lambda _tabla: pd.DataFrame([{"modelo": hpa.NOMBRE_MODELO, "n": 1}]),
    )
    solicitud = hpa.SolicitudEjecucion(
        campania="C2026",
        referencias={hpa.MODELO_MACRO: 76},
        hashes_esperados=None,
        expected_keyset_hash=None,
        horizonte=10,
        max_cortes=0,
        excel_root=None,
        preflight_only=False,
        dry_run=False,
        cache_dir=None,
    )
    contrato = SimpleNamespace(
        evaluation_contract_id=42,
        keyset_sha256="keyset",
        closed_calendar_sha256="calendar",
    )

    with pytest.raises(RuntimeError, match="fallo sintetico"):
        hpa._persistir_candidato(
            "dsn-sintetico",
            SimpleNamespace(),
            pd.DataFrame({"modelo": [hpa.NOMBRE_MODELO]}),
            pd.DataFrame(),
            pd.DataFrame(),
            {"baseline_hashes": {"MacroLegacy_v1": "hash"}},
            contrato,
            solicitud,
        )

    assert [evento[0] for evento in eventos] == [
        "init",
        "snapshot",
        "crear_run",
        "guardar_predicciones",
        "guardar_metricas",
        "finalizar_run",
    ]
    assert eventos[-1] == ("finalizar_run", 901, "failed", "fallo sintetico")
