"""Fachada CLI compatible para persistir el nowcast de cierre semanal.

La lógica reusable vive en :mod:`analitica.servicios.persistir_nowcast_cierre_adaptativo`.
Este módulo conserva los aliases históricos y la frontera CLI.
"""

from __future__ import annotations

import argparse
import json

from analitica.servicios import persistir_nowcast_cierre_adaptativo as _servicio

# Aliases históricos: la implementación única vive en el servicio.
Any = _servicio.Any
CAMPAIGN = _servicio.CAMPAIGN
FUNDOS = _servicio.FUNDOS
MACRO_RUN_HISTORY = _servicio.MACRO_RUN_HISTORY
MACRO_RUN_S34 = _servicio.MACRO_RUN_S34
MODELO = _servicio.MODELO
R09_ACCESS_DEFAULT = _servicio.R09_ACCESS_DEFAULT
REAL_ACCESS_DEFAULT = _servicio.REAL_ACCESS_DEFAULT
ROOT = _servicio.ROOT
ARTEFACTO_DEFAULT = _servicio.ARTEFACTO_DEFAULT
VERSION = _servicio.VERSION

Path = _servicio.Path
date = _servicio.date
hashlib = _servicio.hashlib
np = _servicio.np
pd = _servicio.pd
psycopg = _servicio.psycopg
settings = _servicio.settings
RepositorioAnalytics = _servicio.RepositorioAnalytics
calcular_nowcast_cierre_adaptativo = _servicio.calcular_nowcast_cierre_adaptativo
leer_diario = _servicio.leer_diario
normalizar_fundo_r09 = _servicio.normalizar_fundo_r09
leer_macro_h1 = _servicio.leer_macro_h1
leer_reales_r09_fundo = _servicio.leer_reales_r09_fundo

_sha256_archivo = _servicio._sha256_archivo
_json_hash = _servicio._json_hash
_records_hash = _servicio._records_hash
_normalizar_detalle_artifact = _servicio._normalizar_detalle_artifact
_append_latest_closed_week = _servicio._append_latest_closed_week
_metric = _servicio._metric
_bootstrap = _servicio._bootstrap
build_candidate = _servicio.build_candidate
_publication_rows = _servicio._publication_rows
_baseline_release_hashes = _servicio._baseline_release_hashes
persist = _servicio.persist


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=ARTEFACTO_DEFAULT)
    parser.add_argument("--real-access", type=Path, default=REAL_ACCESS_DEFAULT)
    parser.add_argument("--r09-access", type=Path, default=R09_ACCESS_DEFAULT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / ".tmp" / "persistir_nowcast_cierre_adaptativo.json",
    )
    args = parser.parse_args(argv)
    output, metrics = build_candidate(
        artifact=args.artifact,
        real_access=args.real_access,
        r09_access=args.r09_access,
    )
    report = persist(
        output,
        metrics,
        artifact=args.artifact,
        real_access=args.real_access,
        r09_access=args.r09_access,
        apply=args.apply,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str, allow_nan=False),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
