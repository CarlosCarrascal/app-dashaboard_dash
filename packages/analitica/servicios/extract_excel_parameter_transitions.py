"""Fachada compatible para extraer transiciones canónicas de parámetros Excel.

Las responsabilidades internas están separadas en módulos de normalización, I/O,
cálculo y serialización. Este módulo conserva la API histórica del servicio,
incluidos aliases privados utilizados por la fachada CLI.
"""

from __future__ import annotations

import hashlib  # noqa: F401 - alias histórico consumido por la fachada CLI
import json  # noqa: F401 - alias histórico
import math  # noqa: F401 - alias histórico consumido por la fachada CLI
import re  # noqa: F401 - alias histórico consumido por la fachada CLI
import sys
import unicodedata  # noqa: F401 - alias histórico consumido por la fachada CLI
from collections.abc import Iterable, Mapping, Sequence  # noqa: F401
from dataclasses import dataclass  # noqa: F401
from datetime import date, datetime  # noqa: F401
from pathlib import Path
from typing import Any  # noqa: F401

import numpy as np  # noqa: F401
import pandas as pd  # noqa: F401

PACKAGES_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))

from . import extract_excel_parameter_transitions_calculation as _calculation  # noqa: E402
from . import extract_excel_parameter_transitions_io as _io  # noqa: E402
from . import extract_excel_parameter_transitions_normalization as _normalization  # noqa: E402
from . import extract_excel_parameter_transitions_serialization as _serialization  # noqa: E402

_asof_status = _calculation._asof_status
_date_changed = _calculation._date_changed
_difference_days = _calculation._difference_days
_extract_transitions = _calculation._extract_transitions
_numeric_changed = _calculation._numeric_changed
_safe_log_ratio = _calculation._safe_log_ratio
_transition_frame = _calculation._transition_frame
WorkbookSnapshot = _io.WorkbookSnapshot
_find_header_index = _io._find_header_index
_prepare_panel = _io._prepare_panel
_prepare_parameters = _io._prepare_parameters
_read_snapshot = _io._read_snapshot
_table_from_rows = _io._table_from_rows
KEY_COLUMNS = _normalization.KEY_COLUMNS
PARAMETROS_NOMBRADOS = _normalization.PARAMETROS_NOMBRADOS
_assert_unique_keys = _normalization._assert_unique_keys
_canonical_text = _normalization._canonical_text
_clean_identifier = _normalization._clean_identifier
_column_lookup = _normalization._column_lookup
_optional_series = _normalization._optional_series
_required_column = _normalization._required_column
_unique_headers = _normalization._unique_headers
normalizar_parametros_excel = _normalization.normalizar_parametros_excel
seleccionar_libros_parametros = _normalization.seleccionar_libros_parametros
_json_value = _serialization._json_value
_load_emission_dates = _serialization._load_emission_dates
_parse_emission_date_entries = _serialization._parse_emission_date_entries
_parse_week_spec = _serialization._parse_week_spec
_sha256 = _serialization._sha256
validate_output_directory = _serialization.validate_output_directory
_write_outputs = _serialization.write_outputs

DEFAULT_SOURCE = Path(r"C:\Users\CCARRASCAL\Downloads\Proyecciones")
ALLOWED_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / ".tmp"
DEFAULT_PREFIX = "excel_parameter_transitions"
EPSILON = 1e-12


def extract_transitions(
    source_root: Path,
    *,
    weeks: Sequence[int],
    campaign: str,
    emission_dates: Mapping[int, pd.Timestamp] | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Construye el dataset candidate-only en memoria."""

    return _extract_transitions(
        source_root,
        weeks=weeks,
        campaign=campaign,
        emission_dates=emission_dates,
        selector=seleccionar_libros_parametros,
        reader=_read_snapshot,
    )


def _validate_output_directory(path: Path) -> Path:
    return validate_output_directory(path, allowed_root=ALLOWED_OUTPUT_ROOT)


def write_outputs(
    transitions: pd.DataFrame,
    report: dict[str, object],
    *,
    output_directory: Path,
    prefix: str,
) -> tuple[Path, Path, dict[str, object]]:
    """Escribe únicamente artefactos locales candidate-only."""

    return _write_outputs(
        transitions,
        report,
        output_directory=output_directory,
        prefix=prefix,
        allowed_root=ALLOWED_OUTPUT_ROOT,
    )


__all__ = [
    "ALLOWED_OUTPUT_ROOT",
    "DEFAULT_PREFIX",
    "DEFAULT_SOURCE",
    "EPSILON",
    "KEY_COLUMNS",
    "PARAMETROS_NOMBRADOS",
    "WorkbookSnapshot",
    "extract_transitions",
    "normalizar_parametros_excel",
    "seleccionar_libros_parametros",
    "write_outputs",
]
