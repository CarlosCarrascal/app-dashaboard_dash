"""Fachada CLI compatible para el screening de correctores por fundo-semana."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.proyeccion.candidatos import escribir_json_reproducible
from analitica.servicios import small_data_farm as _servicio

# Aliases históricos: la lógica única vive en el servicio.
RUNS_H1 = _servicio.RUNS_H1
CIERRES = _servicio.CIERRES
FUNDOS = _servicio.FUNDOS
Config = _servicio.Config
_fundo = _servicio._fundo
_numero = _servicio._numero
_features = _servicio._features
_clave_modelo = _servicio._clave_modelo
comparar_r09 = _servicio.comparar_r09
configuraciones = _servicio.configuraciones
construir_fundo_semana = _servicio.construir_fundo_semana
ejecutar = _servicio.ejecutar
leer_panel = _servicio.leer_panel
metricas_empresa = _servicio.metricas_empresa
predecir_rolling = _servicio.predecir_rolling


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    resultado = ejecutar()
    if args.salida:
        escribir_json_reproducible(resultado, args.salida)
    print(json.dumps(resultado["mejor"], ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
