"""Adaptador CLI y fachada histórica del screening cross-campaign h1.

La implementación de negocio vive en :mod:`analitica.servicios.cross_campaign`.
Este módulo conserva el comando y los nombres históricos para consumidores
existentes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.servicios import cross_campaign as _cross_campaign

# Fachada compatible: no hay una segunda implementación ejecutable aquí.
R09_ACCESS_DEFAULT = _cross_campaign.R09_ACCESS_DEFAULT
MACRO_RUN_ID = _cross_campaign.MACRO_RUN_ID
CAMPAIGNAS = _cross_campaign.CAMPAIGNAS
FUNDOS = _cross_campaign.FUNDOS
SEMANA_DESARROLLO_C2026 = _cross_campaign.SEMANA_DESARROLLO_C2026
SEMANAS_HOLDOUT_C2026 = _cross_campaign.SEMANAS_HOLDOUT_C2026
CIERRE_CERTIFICADO_C2026 = _cross_campaign.CIERRE_CERTIFICADO_C2026
REAL_ACCESS_DEFAULT = _cross_campaign.REAL_ACCESS_DEFAULT
FEATURE_SETS = _cross_campaign.FEATURE_SETS

Configuracion = _cross_campaign.Configuracion
_mapear_fundo_h01 = _cross_campaign._mapear_fundo_h01
sha256_archivo = _cross_campaign.sha256_archivo
leer_macro_h1 = _cross_campaign.leer_macro_h1
leer_reales_access = _cross_campaign.leer_reales_access
construir_panel = _cross_campaign.construir_panel
construir_features_asof = _cross_campaign.construir_features_asof
configuraciones = _cross_campaign.configuraciones
_columnas_modelo = _cross_campaign._columnas_modelo
_matriz = _cross_campaign._matriz
mascara_entrenamiento = _cross_campaign.mascara_entrenamiento
_predecir_bayes = _cross_campaign._predecir_bayes
predecir_rolling = _cross_campaign.predecir_rolling
_metricas = _cross_campaign._metricas
bootstrap_pareado = _cross_campaign.bootstrap_pareado
_por_fundo = _cross_campaign._por_fundo
_bootstrap_por_fundo = _cross_campaign._bootstrap_por_fundo
_resumen_periodo = _cross_campaign._resumen_periodo
mascara_seleccion = _cross_campaign.mascara_seleccion
seleccionar_configuracion = _cross_campaign.seleccionar_configuracion
_keyset_sha256 = _cross_campaign._keyset_sha256
ejecutar = _cross_campaign.ejecutar
_json_default = _cross_campaign._json_default
escribir_json = _cross_campaign.escribir_json

# Utilidades R09 ya centralizadas anteriormente; se conservan por identidad.
normalizar_fundo = _cross_campaign.normalizar_fundo
_conexion_access = _cross_campaign._conexion_access
_columna_campania = _cross_campaign._columna_campania
leer_r09_access = _cross_campaign.leer_r09_access
preparar_r09_crudo = _cross_campaign.preparar_r09_crudo

__all__ = [
    "CAMPAIGNAS",
    "CIERRE_CERTIFICADO_C2026",
    "FEATURE_SETS",
    "FUNDOS",
    "MACRO_RUN_ID",
    "REAL_ACCESS_DEFAULT",
    "R09_ACCESS_DEFAULT",
    "SEMANA_DESARROLLO_C2026",
    "SEMANAS_HOLDOUT_C2026",
    "Configuracion",
    "bootstrap_pareado",
    "construir_features_asof",
    "construir_panel",
    "configuraciones",
    "ejecutar",
    "escribir_json",
    "leer_macro_h1",
    "leer_reales_access",
    "leer_r09_access",
    "mascara_entrenamiento",
    "mascara_seleccion",
    "normalizar_fundo",
    "predecir_rolling",
    "preparar_r09_crudo",
    "seleccionar_configuracion",
    "sha256_archivo",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-access", type=Path, default=REAL_ACCESS_DEFAULT)
    parser.add_argument("--r09-access", type=Path, default=R09_ACCESS_DEFAULT)
    parser.add_argument("--run-id", type=int, default=MACRO_RUN_ID)
    parser.add_argument("--salida", type=Path)
    parser.add_argument("--detalle", type=Path)
    args = parser.parse_args()
    resultado, detalle = ejecutar(
        real_access=args.real_access, r09_access=args.r09_access, run_id=args.run_id
    )
    if args.salida:
        escribir_json(resultado, args.salida)
    if args.detalle:
        args.detalle.parent.mkdir(parents=True, exist_ok=True)
        detalle.to_parquet(args.detalle, index=False)
    print(
        json.dumps(
            {
                "configuracion_id": resultado["configuracion_id"],
                "metricas": resultado["metricas"],
                "veredicto_holdout": resultado["veredicto_holdout"],
            },
            ensure_ascii=False,
            indent=2,
            default=_json_default,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
