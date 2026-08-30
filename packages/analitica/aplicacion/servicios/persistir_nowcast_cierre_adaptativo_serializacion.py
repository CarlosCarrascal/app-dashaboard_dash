"""Serializacion, hashes y contratos de salida del nowcast de cierre."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd


def sha256_archivo(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def records_hash(
    table: pd.DataFrame, columns: list[str], *, hash_json: Callable[[Any], str]
) -> str:
    clean = table[columns].copy().sort_values(columns[:3], kind="stable")
    clean = clean.where(pd.notna(clean), None)
    return hash_json(clean.to_dict("records"))


def publication_rows(
    output: pd.DataFrame,
    *,
    modelo: str,
    version: str,
    campaign: str,
    fundos: tuple[str, ...],
) -> pd.DataFrame:
    component_columns = [
        "pace_kg",
        "share_estimado",
        "coef_macro",
        "coef_pace",
        "escala_adaptativa",
        "peso_ritmo_adaptativo",
        "n_entrenamiento",
        "fase_bajo_volumen",
        "retencion_correccion",
        "recon_alpha",
        "recon_share_macro",
        "recon_share_montue",
        "recon_total_empresa_kg",
        "estado_nowcast",
    ]
    rows: list[dict[str, Any]] = []
    for record in output.to_dict("records"):
        target = pd.Timestamp(record["fecha_objetivo"])
        rows.append(
            {
                "modelo": modelo,
                "version_modelo": version,
                "campania": campaign,
                "semana_inicio": target,
                "semana_cierre": target + pd.Timedelta(days=6),
                "fecha_corte": target + pd.Timedelta(days=1),
                "fecha_emision": target + pd.Timedelta(days=2),
                "fundo": record["fundo_operativo"],
                "kg_lun_mar": record["montue_kg"],
                "p50_kg": record["candidate_kg"],
                "real_kg": record["real_kg"],
                "macro_kg": record["macro_kg"],
                "r09_presemana_kg": record.get("r09_presemana_kg"),
                "r09_misma_semana_kg": record.get("r09_misma_semana_kg"),
                "estado_evaluacion": "evaluado",
                "componentes": {
                    key: (None if pd.isna(record.get(key)) else record.get(key))
                    for key in component_columns
                }
                | {
                    "producto": "nowcast_cierre_semana",
                    "informacion_maxima": "martes",
                    "r09_usado_como_predictor": False,
                    "macro_fecha_emision": (target - pd.Timedelta(days=7)).date().isoformat(),
                },
            }
        )
    fund_rows = pd.DataFrame(rows)
    company = fund_rows.groupby(
        [
            "modelo",
            "version_modelo",
            "campania",
            "semana_inicio",
            "semana_cierre",
            "fecha_corte",
            "fecha_emision",
            "estado_evaluacion",
        ],
        as_index=False,
    ).agg(
        kg_lun_mar=("kg_lun_mar", "sum"),
        p50_kg=("p50_kg", "sum"),
        real_kg=("real_kg", "sum"),
        macro_kg=("macro_kg", "sum"),
        r09_presemana_kg=("r09_presemana_kg", lambda x: x.sum(min_count=1)),
        r09_misma_semana_kg=("r09_misma_semana_kg", lambda x: x.sum(min_count=1)),
    )
    company["fundo"] = "Empresa"
    company["componentes"] = [
        {
            "producto": "nowcast_cierre_semana",
            "nivel": "empresa_reconciliada",
            "fondos": list(fundos),
            "r09_usado_como_predictor": False,
        }
        for _ in range(len(company))
    ]
    columns = list(fund_rows.columns)
    return pd.concat([fund_rows, company.reindex(columns=columns)], ignore_index=True)


def serialize_report(
    output: pd.DataFrame,
    metrics: dict[str, Any],
    *,
    artifact: Path,
    real_access: Path,
    r09_access: Path,
    apply: bool,
    modelo: str,
    version: str,
    campaign: str,
    macro_run_history: int,
    macro_run_s34: int,
    publication_rows: Callable[..., pd.DataFrame],
    sha256_archivo: Callable[[Path], str],
    records_hash: Callable[..., str],
    json_hash: Callable[[Any], str],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows = publication_rows(output)
    source_info = {
        "artifact": str(artifact),
        "artifact_sha256": sha256_archivo(artifact),
        "real_access": str(real_access),
        "real_access_sha256": sha256_archivo(real_access),
        "r09_access": str(r09_access),
        "r09_access_sha256": sha256_archivo(r09_access),
        "macro_runs": {"history": macro_run_history, "S34": macro_run_s34},
        "configuration_id": metrics["configuration_id"],
    }
    prediction_hash = records_hash(
        rows,
        ["campania", "semana_inicio", "fundo", "p50_kg", "real_kg", "kg_lun_mar"],
    )
    source_hash = json_hash(source_info | {"prediction_hash": prediction_hash})
    report: dict[str, Any] = {
        "schema": "nowcast-close-release-v1",
        "modelo": modelo,
        "version_modelo": version,
        "campania": campaign,
        "candidate_only": True,
        "published_as_forecast": False,
        "source": source_info,
        "source_hash": source_hash,
        "predictions_sha256": prediction_hash,
        "metrics": metrics,
        "rows": int(len(rows)),
        "weeks": int(output.fecha_objetivo.nunique()),
        "apply": bool(apply),
    }
    if not apply:
        report["status"] = "dry_run_passed"
    return rows, {
        "report": report,
        "source_hash": source_hash,
        "prediction_hash": prediction_hash,
    }


__all__ = [
    "json_hash",
    "publication_rows",
    "records_hash",
    "serialize_report",
    "sha256_archivo",
]
