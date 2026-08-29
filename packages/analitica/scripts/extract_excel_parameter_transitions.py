"""Fachada CLI compatible para extraer transiciones de parámetros Excel.

La implementación reusable vive en
:mod:`analitica.servicios.extract_excel_parameter_transitions`. Este módulo
conserva los aliases históricos, la CLI, sus argumentos, la serialización y
las rutas de salida.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

PACKAGES_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))

from analitica.servicios import extract_excel_parameter_transitions as _servicio  # noqa: E402

PACKAGES_ROOT = _servicio.PACKAGES_ROOT

# Compatibilidad de nombres históricos: los aliases, incluidos los privados,
# apuntan a la implementación única del servicio.
hashlib = _servicio.hashlib
math = _servicio.math
re = _servicio.re
unicodedata = _servicio.unicodedata
dataclass = _servicio.dataclass
date = _servicio.date
datetime = _servicio.datetime
Iterable = _servicio.Iterable
Mapping = _servicio.Mapping
Any = _servicio.Any
np = _servicio.np
pd = _servicio.pd

PARAMETROS_NOMBRADOS = _servicio.PARAMETROS_NOMBRADOS
normalizar_parametros_excel = _servicio.normalizar_parametros_excel
seleccionar_libros_parametros = _servicio.seleccionar_libros_parametros

DEFAULT_SOURCE = _servicio.DEFAULT_SOURCE
ALLOWED_OUTPUT_ROOT = _servicio.ALLOWED_OUTPUT_ROOT
DEFAULT_PREFIX = _servicio.DEFAULT_PREFIX
EPSILON = _servicio.EPSILON
KEY_COLUMNS = _servicio.KEY_COLUMNS

WorkbookSnapshot = _servicio.WorkbookSnapshot
_canonical_text = _servicio._canonical_text
_clean_identifier = _servicio._clean_identifier
_unique_headers = _servicio._unique_headers
_find_header_index = _servicio._find_header_index
_table_from_rows = _servicio._table_from_rows
_column_lookup = _servicio._column_lookup
_required_column = _servicio._required_column
_optional_series = _servicio._optional_series
_assert_unique_keys = _servicio._assert_unique_keys
_prepare_parameters = _servicio._prepare_parameters
_prepare_panel = _servicio._prepare_panel
_read_snapshot = _servicio._read_snapshot
_difference_days = _servicio._difference_days
_numeric_changed = _servicio._numeric_changed
_date_changed = _servicio._date_changed
_safe_log_ratio = _servicio._safe_log_ratio
_asof_status = _servicio._asof_status
_transition_frame = _servicio._transition_frame
_parse_week_spec = _servicio._parse_week_spec
_parse_emission_date_entries = _servicio._parse_emission_date_entries
_load_emission_dates = _servicio._load_emission_dates
_sha256 = _servicio._sha256
_json_value = _servicio._json_value
_validate_output_directory = _servicio._validate_output_directory
extract_transitions = _servicio.extract_transitions
write_outputs = _servicio.write_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extrae cambios canónicos Parametros/Panel sin leer forecast ni PostgreSQL."
    )
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=ALLOWED_OUTPUT_ROOT)
    parser.add_argument("--campaign", default="C2026")
    parser.add_argument(
        "--weeks",
        help="Semanas separadas por coma o rango, por ejemplo 24-29,31-35.",
    )
    parser.add_argument(
        "--micro",
        action="store_true",
        help="Usa S31-S35 si --weeks no fue especificado.",
    )
    parser.add_argument("--emission-dates-json", type=Path)
    parser.add_argument(
        "--emission-date",
        action="append",
        default=[],
        help="Fecha verificada repetible, por ejemplo S31=2026-07-29.",
    )
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    weeks = _parse_week_spec(args.weeks)
    if args.micro and args.weeks is None:
        weeks = list(range(31, 36))
    emission_dates = _load_emission_dates(args.emission_dates_json, args.emission_date)
    transitions, report = extract_transitions(
        args.source_root,
        weeks=weeks,
        campaign=str(args.campaign),
        emission_dates=emission_dates,
    )
    prefix = f"{args.prefix}_micro" if args.micro and args.prefix == DEFAULT_PREFIX else args.prefix
    parquet_path, json_path, final_report = write_outputs(
        transitions,
        report,
        output_directory=args.output_dir,
        prefix=prefix,
    )
    summary = {
        "parquet": str(parquet_path),
        "json": str(json_path),
        "rows": final_report["coverage"]["transition_rows"],
        "canonical_pairs": final_report["selection"]["canonical_pairs"],
        "workbooks_read": final_report["selection"]["workbooks_read"],
        "comparable_lot_coverage": final_report["coverage"]["comparable_lot_coverage"],
        "strict_asof_usable_rows": final_report["coverage"]["strict_asof_usable_rows"],
    }
    print(json.dumps(_json_value(summary), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
