from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from analitica.scripts import screening_excel_assisted as facade
from analitica.servicios import excel_assisted as service

NOMBRES_COMPATIBLES = (
    "_conexion_access",
    "_columna_campania",
    "cargar_reales_y_r09",
    "fecha_lunes_iso",
    "construir_modelo_operativo_excel",
    "ejecutar",
)


@pytest.mark.parametrize("nombre", NOMBRES_COMPATIBLES)
def test_fachada_conserva_identidad_y_firma_historica(nombre: str) -> None:
    assert getattr(facade, nombre) is getattr(service, nombre)
    assert inspect.signature(getattr(facade, nombre)) == inspect.signature(getattr(service, nombre))


def test_fachada_conserva_constantes_imports_y_serializador_historicos() -> None:
    for nombre in (
        "ROOT_DEFAULT",
        "ACCESS_DEFAULT",
        "SEMANAS_LIMPIAS",
        "np",
        "pd",
        "escribir_json_reproducible",
    ):
        assert getattr(facade, nombre) is getattr(service, nombre)


def test_ejecutar_preserva_comparacion_y_omisiones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raiz = tmp_path / "proyecciones"
    (raiz / "ProyeccionSemanal_24").mkdir(parents=True)
    access = tmp_path / "datos.accdb"
    reales = pd.DataFrame({"semana": [25], "real_kg": [100.0]})
    r09 = pd.DataFrame({"version": ["s24"], "semana": [25], "r09_kg": [90.0]})

    def fake_cargar(_access: Path, _campania: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        return reales, r09

    def fake_construir(
        carpeta: Path,
        *,
        campania: str,
        fecha_emision: pd.Timestamp,
        version_fuente: str,
        fuente_parametros: str,
    ) -> tuple[pd.DataFrame, object, dict[str, object]]:
        assert carpeta == raiz / "ProyeccionSemanal_24"
        assert campania == "C2026"
        assert fecha_emision == service.fecha_lunes_iso(2026, 24)
        assert version_fuente == "ProySemanal_24"
        assert fuente_parametros == "excel"
        predicciones = pd.DataFrame(
            {"fecha_objetivo": [pd.Timestamp("2026-06-15")], "p50_kg": [101.0]}
        )
        return predicciones, object(), {"manifest": [{"sha256": "abc123"}]}

    monkeypatch.setattr(service, "cargar_reales_y_r09", fake_cargar)
    monkeypatch.setattr(service, "construir_modelo_operativo_excel", fake_construir)

    resultado = service.ejecutar(
        raiz,
        access,
        campania="C2026",
        semanas=(24, 25),
    )

    assert resultado == {
        "schema": "screening-excel-assisted-v1",
        "descripcion": "Techo asistido; no es un modelo automatico ni publicable.",
        "campania": "C2026",
        "access": str(access),
        "root": str(raiz),
        "semanas_solicitadas": [24, 25],
        "comparacion": [
            {
                "campania": "C2026",
                "semana_emision": 24,
                "fecha_emision": "2026-06-08",
                "semana_objetivo": 25,
                "real_kg": 100.0,
                "excel_asistido_kg": 101.0,
                "r09_kg": 90.0,
                "n_libros": 1,
                "hashes": ["abc123"],
                "error_abs_excel": 1.0,
                "error_abs_r09": 10.0,
            }
        ],
        "metricas": {
            "ExcelAsistido": {
                "wape": 0.01,
                "sesgo": 0.01,
                "mae_kg": 1.0,
                "n_semanas": 1,
                "volumen_real_kg": 100.0,
                "semanas_ganadas_r09": 1.0,
            },
            "R09": {
                "wape": 0.1,
                "sesgo": -0.1,
                "mae_kg": 10.0,
                "n_semanas": 1,
                "volumen_real_kg": 100.0,
            },
            "universo": {
                "n_semanas": 1,
                "volumen_real_kg": 100.0,
                "denominador_wape": 100.0,
            },
        },
        "omitidas": [{"semana_emision": 25, "motivo": "carpeta_ausente"}],
        "publicable": False,
    }


def test_fachada_cli_conserva_argumentos_salida_y_serializacion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    salida = tmp_path / "resultado" / "screening.json"
    raiz = tmp_path / "proyecciones"
    access = tmp_path / "datos.accdb"
    resultado = {
        "metricas": {"ExcelAsistido": {"n_semanas": 1}},
        "omitidas": [{"semana_emision": 24}],
        "detalle": [{"valor": 3}],
    }
    llamadas: list[tuple[Path, Path, str, tuple[int, ...]]] = []

    def fake_ejecutar(
        root: Path,
        access: Path,
        *,
        campania: str,
        semanas: tuple[int, ...],
    ) -> dict[str, object]:
        llamadas.append((root, access, campania, semanas))
        return resultado

    monkeypatch.setattr(facade, "ejecutar", fake_ejecutar)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "screening_excel_assisted",
            "--root",
            str(raiz),
            "--access",
            str(access),
            "--campania",
            "C2027",
            "--semanas",
            "28",
            "31",
            "--salida",
            str(salida),
        ],
    )

    assert facade.main() == 0
    assert llamadas == [(raiz, access, "C2027", (28, 31))]
    assert json.loads(salida.read_text(encoding="utf-8")) == resultado
    salida_consola = capsys.readouterr().out
    assert '"n_semanas": 1' in salida_consola
    assert '"semana_emision": 24' in salida_consola


def test_fachada_es_compuerta_cli_y_servicio_no_depende_de_scripts() -> None:
    ruta_fachada = Path(facade.__file__)
    arbol_fachada = ast.parse(ruta_fachada.read_text(encoding="utf-8"), filename=str(ruta_fachada))
    definiciones = [
        nodo.name
        for nodo in arbol_fachada.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assert definiciones == ["main"]
    assert not [
        nodo
        for nodo in ast.walk(arbol_fachada)
        if isinstance(nodo, (ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith))
    ]

    ruta_servicio = Path(service.__file__)
    arbol_servicio = ast.parse(
        ruta_servicio.read_text(encoding="utf-8"), filename=str(ruta_servicio)
    )
    assert not [
        nodo
        for nodo in ast.walk(arbol_servicio)
        if isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.scripts.")
    ]
