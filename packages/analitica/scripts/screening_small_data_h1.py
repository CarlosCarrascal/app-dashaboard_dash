"""Fachada CLI compatible para el screening honesto de ML pequeño H1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from analitica.servicios import small_data_h1 as _servicio

# Alias históricos: la implementación única vive en el servicio.
CAMPANIA_DEFAULT = _servicio.CAMPANIA_DEFAULT
FEATURE_SETS = _servicio.FEATURE_SETS
FUNDOS = _servicio.FUNDOS
RUN_ID_DEFAULT = _servicio.RUN_ID_DEFAULT
SEMANA_MAX_SELECCION = _servicio.SEMANA_MAX_SELECCION
SEMANAS_HOLDOUT = _servicio.SEMANAS_HOLDOUT
ULTIMO_CIERRE_DEFAULT = _servicio.ULTIMO_CIERRE_DEFAULT
Configuracion = _servicio.Configuracion
_ajustar_modelo = _servicio._ajustar_modelo
_cargar_universo_lote = _servicio._cargar_universo_lote
_json_default = _servicio._json_default
_metricas = _servicio._metricas
_resumen_periodo = _servicio._resumen_periodo
_wins = _servicio._wins
aplicar_candidato_a_lotes = _servicio.aplicar_candidato_a_lotes
cargar_universo_lote = _servicio.cargar_universo_lote
construir_panel_fundo = _servicio.construir_panel_fundo
configuraciones = _servicio.configuraciones
ejecutar = _servicio.ejecutar
normalizar_fundo = _servicio.normalizar_fundo
predecir_rolling = _servicio.predecir_rolling
seleccionar_configuracion = _servicio.seleccionar_configuracion


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=int, default=RUN_ID_DEFAULT)
    parser.add_argument("--campania", default=CAMPANIA_DEFAULT)
    parser.add_argument("--ultimo-cierre", default=str(ULTIMO_CIERRE_DEFAULT.date()))
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    resultado = ejecutar(
        run_id=args.run_id,
        campania=args.campania,
        ultimo_cierre=pd.Timestamp(args.ultimo_cierre),
    )
    texto = json.dumps(resultado, ensure_ascii=False, indent=2, default=_json_default)
    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(texto, encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
