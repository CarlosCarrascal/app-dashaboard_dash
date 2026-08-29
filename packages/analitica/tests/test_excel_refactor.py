from __future__ import annotations

import ast
from pathlib import Path

from analitica.servicios import excel_parameter_deltas as deltas
from analitica.servicios import extract_excel_parameter_transitions as transitions


def test_deltas_expone_responsabilidades_desde_modulos_internos() -> None:
    assert deltas.inventariar_libros.__module__.endswith("excel_parameter_deltas_io")
    assert deltas.leer_snapshot_libro.__module__.endswith("excel_parameter_deltas_io")
    assert deltas.calcular_delta_snapshot.__module__.endswith(
        "excel_parameter_deltas_calculation"
    )
    assert deltas.predecir_temporal.__module__.endswith("excel_parameter_deltas_calculation")
    assert deltas._json_default.__module__.endswith("excel_parameter_deltas_serialization")


def test_transiciones_expone_responsabilidades_desde_modulos_internos() -> None:
    assert transitions._read_snapshot.__module__.endswith(
        "extract_excel_parameter_transitions_io"
    )
    assert transitions._prepare_parameters.__module__.endswith(
        "extract_excel_parameter_transitions_io"
    )
    assert transitions._transition_frame.__module__.endswith(
        "extract_excel_parameter_transitions_calculation"
    )
    assert transitions._parse_week_spec.__module__.endswith(
        "extract_excel_parameter_transitions_serialization"
    )
    assert transitions._json_value.__module__.endswith(
        "extract_excel_parameter_transitions_serialization"
    )


def test_drivers_opcionales_solo_se_importan_dentro_de_las_operaciones_de_io() -> None:
    service_paths = (
        Path(deltas.__file__),
        Path(transitions.__file__),
    )
    io_paths = (
        Path(deltas.__file__).with_name("excel_parameter_deltas_io.py"),
        Path(transitions.__file__).with_name("extract_excel_parameter_transitions_io.py"),
    )
    for path in (*service_paths, *io_paths):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        top_level_names = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "python_calamine" not in top_level_names
        assert "pyodbc" not in top_level_names
