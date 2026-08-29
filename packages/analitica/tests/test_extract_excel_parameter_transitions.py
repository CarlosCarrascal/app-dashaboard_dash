from __future__ import annotations

import ast
import inspect
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analitica.scripts import extract_excel_parameter_transitions as facade
from analitica.servicios import extract_excel_parameter_transitions as service

COMPATIBLE_NAMES = (
    "WorkbookSnapshot",
    "_canonical_text",
    "_clean_identifier",
    "_unique_headers",
    "_find_header_index",
    "_table_from_rows",
    "_column_lookup",
    "_required_column",
    "_optional_series",
    "_assert_unique_keys",
    "_prepare_parameters",
    "_prepare_panel",
    "_read_snapshot",
    "_difference_days",
    "_numeric_changed",
    "_date_changed",
    "_safe_log_ratio",
    "_asof_status",
    "_transition_frame",
    "_parse_week_spec",
    "_parse_emission_date_entries",
    "_load_emission_dates",
    "_sha256",
    "_json_value",
    "_validate_output_directory",
    "extract_transitions",
    "write_outputs",
)


@pytest.mark.parametrize("name", COMPATIBLE_NAMES)
def test_fachada_conserva_identidad_y_firma_de_aliases(name: str) -> None:
    facade_value = getattr(facade, name)
    service_value = getattr(service, name)
    assert facade_value is service_value
    assert inspect.signature(facade_value) == inspect.signature(service_value)


def test_fachada_conserva_constantes_y_dependencias_historicas() -> None:
    for name in (
        "PACKAGES_ROOT",
        "PARAMETROS_NOMBRADOS",
        "DEFAULT_SOURCE",
        "ALLOWED_OUTPUT_ROOT",
        "DEFAULT_PREFIX",
        "EPSILON",
        "KEY_COLUMNS",
        "normalizar_parametros_excel",
        "seleccionar_libros_parametros",
        "np",
        "pd",
    ):
        assert getattr(facade, name) is getattr(service, name)


def _snapshot(week: int, path: Path, shift: float) -> service.WorkbookSnapshot:
    row: dict[str, object] = {
        "modulo": "M-01",
        "lote": "L-01",
        "turno": "D",
        "caida": 1.0 + shift,
        "finicio": pd.Timestamp("2026-01-01") + pd.Timedelta(value=int(shift), unit="D"),
        "fepas1": pd.Timestamp("2026-01-20") + pd.Timedelta(value=int(shift), unit="D"),
        "fepas2": pd.Timestamp("2026-02-01") + pd.Timedelta(value=int(shift), unit="D"),
        "parametros_presente": True,
        "panel_presente": True,
    }
    row.update(
        {
            parameter: float(index) + shift
            for index, parameter in enumerate(service.PARAMETROS_NOMBRADOS, start=1)
        }
    )
    return service.WorkbookSnapshot(
        semana=week,
        fundo="Arena",
        path=path,
        sha256=f"sha-{week}",
        frame=pd.DataFrame([row]),
        fepas_indices=(1, 2),
    )


def test_transicion_fachada_y_servicio_es_paritaria_y_asof_estricta(tmp_path: Path) -> None:
    fechas = {
        24: pd.Timestamp("2026-06-08"),
        25: pd.Timestamp("2026-06-15"),
    }
    facade_result = facade._transition_frame(
        _snapshot(24, tmp_path / "anterior.xlsm", 0.0),
        _snapshot(25, tmp_path / "actual.xlsm", 1.0),
        campaign="C2026",
        emission_dates=fechas,
    )
    service_result = service._transition_frame(
        _snapshot(24, tmp_path / "anterior.xlsm", 0.0),
        _snapshot(25, tmp_path / "actual.xlsm", 1.0),
        campaign="C2026",
        emission_dates=fechas,
    )

    facade_frame, facade_report = facade_result
    service_frame, service_report = service_result
    pd.testing.assert_frame_equal(facade_frame, service_frame)
    assert facade_report == service_report
    assert facade_frame.transicion_canonicamente_consecutiva.dtype == bool
    assert facade_frame.transicion_asof_estricta.dtype == bool
    assert pd.api.types.is_bool_dtype(facade_frame.fila_asof_utilizable)
    assert facade_frame.loc[0, "motivo_asof"] == "estricto"
    assert bool(facade_frame.loc[0, "fila_asof_utilizable"])
    assert facade_frame.loc[0, "delta_X1"] == 1.0
    assert facade_frame.loc[0, "n_fepas_cambiadas"] == 2


def test_cli_conserva_argumentos_micro_fechas_prefijo_y_serializacion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source_root = tmp_path / "proyecciones"
    output_dir = tmp_path / "salida"
    calls: dict[str, object] = {}
    report = {
        "coverage": {
            "transition_rows": 3,
            "comparable_lot_coverage": 0.5,
            "strict_asof_usable_rows": 2,
        },
        "selection": {
            "canonical_pairs": 1,
            "workbooks_read": 2,
        },
    }

    def fake_extract(
        source: Path,
        *,
        weeks: list[int],
        campaign: str,
        emission_dates: dict[int, pd.Timestamp],
    ) -> tuple[pd.DataFrame, dict[str, object]]:
        calls["extract"] = (source, weeks, campaign, emission_dates)
        return pd.DataFrame(), report

    def fake_write(
        transitions: pd.DataFrame,
        received_report: dict[str, object],
        *,
        output_directory: Path,
        prefix: str,
    ) -> tuple[Path, Path, dict[str, object]]:
        calls["write"] = (transitions, received_report, output_directory, prefix)
        return output_dir / "result.parquet", output_dir / "result.json", report

    monkeypatch.setattr(facade, "extract_transitions", fake_extract)
    monkeypatch.setattr(facade, "write_outputs", fake_write)

    assert (
        facade.main(
            [
                "--source-root",
                str(source_root),
                "--output-dir",
                str(output_dir),
                "--campaign",
                "C2027",
                "--micro",
                "--emission-date",
                "S31=2026-07-29",
            ]
        )
        == 0
    )

    assert calls["extract"] == (
        source_root,
        [31, 32, 33, 34, 35],
        "C2027",
        {31: pd.Timestamp("2026-07-29")},
    )
    assert calls["write"][2:] == (output_dir, "excel_parameter_transitions_micro")
    assert json.loads(capsys.readouterr().out) == {
        "canonical_pairs": 1,
        "comparable_lot_coverage": 0.5,
        "json": str(output_dir / "result.json"),
        "parquet": str(output_dir / "result.parquet"),
        "rows": 3,
        "strict_asof_usable_rows": 2,
        "workbooks_read": 2,
    }


def test_write_outputs_conserva_ruta_segura_y_serializacion_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "ALLOWED_OUTPUT_ROOT", tmp_path)
    transitions = pd.DataFrame({"modulo": ["M-01"], "valor": [np.int64(4)]})
    report = {
        "fecha": date(2026, 7, 29),
        "ruta": tmp_path / "origen.xlsm",
        "entero": np.int64(4),
        "ausente": pd.NA,
        "invalido": float("nan"),
    }

    parquet_path, json_path, final_report = facade.write_outputs(
        transitions,
        report,
        output_directory=tmp_path / "artefactos",
        prefix="transiciones/prueba",
    )

    assert parquet_path == tmp_path / "artefactos" / "transiciones_prueba.parquet"
    assert json_path == tmp_path / "artefactos" / "transiciones_prueba.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["fecha"] == "2026-07-29"
    assert payload["ruta"] == str(tmp_path / "origen.xlsm")
    assert payload["entero"] == 4
    assert payload["ausente"] is None
    assert payload["invalido"] is None
    assert final_report["outputs"]["parquet"] == str(parquet_path)
    assert parquet_path.is_file()


def test_ast_deja_la_fachada_como_compuerta_cli_y_el_servicio_sin_scripts() -> None:
    facade_tree = ast.parse(Path(facade.__file__).read_text(encoding="utf-8"))
    definitions = [
        node.name
        for node in facade_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assert definitions == ["build_parser", "main"]
    assert not [
        node
        for node in ast.walk(facade_tree)
        if isinstance(node, (ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith))
    ]

    service_tree = ast.parse(Path(service.__file__).read_text(encoding="utf-8"))
    assert not [
        node
        for node in ast.walk(service_tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("analitica.scripts.")
    ]
    top_level_imports = [
        alias.name
        for node in service_tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    ] + [
        node.module
        for node in service_tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    ]
    assert "pyodbc" not in top_level_imports
    assert "python_calamine" not in top_level_imports
