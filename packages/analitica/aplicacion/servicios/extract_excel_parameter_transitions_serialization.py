"""Parsing de argumentos y escritura auditable de transiciones Excel."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_ALLOWED_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / ".tmp"


def _parse_week_spec(specification: str | None) -> list[int]:
    if not specification:
        return list(range(1, 36))
    weeks: set[int] = set()
    for token in specification.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start, end = int(start_text), int(end_text)
            if end < start:
                raise ValueError(f"Rango de semanas inválido: {token}")
            weeks.update(range(start, end + 1))
        else:
            weeks.add(int(token))
    invalid = sorted(week for week in weeks if week < 1 or week > 53)
    if invalid:
        raise ValueError(f"Semanas fuera de rango: {invalid}")
    return sorted(weeks)


def _parse_emission_date_entries(entries: Iterable[str]) -> dict[int, pd.Timestamp]:
    result: dict[int, pd.Timestamp] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(f"Fecha de emisión inválida: {entry!r}; use S31=2026-07-29")
        week_text, date_text = entry.split("=", 1)
        match = re.fullmatch(r"S?0*(\d+)", week_text.strip(), re.I)
        if not match:
            raise ValueError(f"Semana de emisión inválida: {week_text!r}")
        parsed = pd.to_datetime(date_text.strip(), errors="coerce")
        if pd.isna(parsed):
            raise ValueError(f"Fecha de emisión inválida: {date_text!r}")
        result[int(match.group(1))] = pd.Timestamp(parsed).normalize()
    return result


def _load_emission_dates(
    json_path: Path | None,
    inline_entries: Iterable[str],
) -> dict[int, pd.Timestamp]:
    dates: dict[int, pd.Timestamp] = {}
    if json_path is not None:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("fechas_emision"), dict):
            payload = payload["fechas_emision"]
        if not isinstance(payload, dict):
            raise ValueError("El JSON de fechas debe ser un objeto semana -> fecha")
        dates.update(
            _parse_emission_date_entries(f"{key}={value}" for key, value in payload.items())
        )
    dates.update(_parse_emission_date_entries(inline_entries))
    return dates


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_value(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return value


def validate_output_directory(path: Path, *, allowed_root: Path) -> Path:
    allowed = allowed_root.resolve()
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError as exc:
        raise ValueError(f"La salida debe permanecer dentro de {allowed}") from exc
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def write_outputs(
    transitions: pd.DataFrame,
    report: dict[str, object],
    *,
    output_directory: Path,
    prefix: str,
    allowed_root: Path,
) -> tuple[Path, Path, dict[str, object]]:
    """Escribe únicamente artefactos locales candidate-only."""

    output_directory = validate_output_directory(output_directory, allowed_root=allowed_root)
    safe_prefix = re.sub(r"[^A-Za-z0-9_.-]+", "_", prefix).strip("._")
    if not safe_prefix:
        raise ValueError("El prefijo de salida no puede quedar vacío")
    parquet_path = output_directory / f"{safe_prefix}.parquet"
    json_path = output_directory / f"{safe_prefix}.json"
    transitions.to_parquet(parquet_path, index=False, compression="zstd")
    report_with_outputs = {
        **report,
        "outputs": {
            "parquet": str(parquet_path),
            "parquet_sha256": _sha256(parquet_path),
            "json": str(json_path),
        },
    }
    json_path.write_text(
        json.dumps(_json_value(report_with_outputs), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return parquet_path, json_path, report_with_outputs


__all__ = [
    "DEFAULT_ALLOWED_OUTPUT_ROOT",
    "_json_value",
    "_load_emission_dates",
    "_parse_emission_date_entries",
    "_parse_week_spec",
    "_sha256",
    "validate_output_directory",
    "write_outputs",
]
