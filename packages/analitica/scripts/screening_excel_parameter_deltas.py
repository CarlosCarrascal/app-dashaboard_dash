"""Fachada CLI compatible para el screening de deltas expertos Excel.

La lógica de negocio vive en :mod:`analitica.servicios.excel_parameter_deltas`.
Este módulo conserva los nombres históricos, las firmas públicas y privadas,
los argumentos de línea de comandos, la serialización y las rutas de salida.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.servicios import excel_parameter_deltas as _servicio

# Compatibilidad de nombres históricos: las dependencias y todos los símbolos
# del script anterior apuntan a la implementación única del servicio.
hashlib = _servicio.hashlib
re = _servicio.re
Iterable = _servicio.Iterable
Mapping = _servicio.Mapping
asdict = _servicio.asdict
dataclass = _servicio.dataclass
np = _servicio.np
pd = _servicio.pd
Ridge = _servicio.Ridge
StandardScaler = _servicio.StandardScaler
cargar_universo_lote = _servicio.cargar_universo_lote

ROOT_DEFAULT = _servicio.ROOT_DEFAULT
RUN_ID_DEFAULT = _servicio.RUN_ID_DEFAULT
CAMPANIA_DEFAULT = _servicio.CAMPANIA_DEFAULT
SEMANAS = _servicio.SEMANAS
SEMANA_MAX_DESARROLLO = _servicio.SEMANA_MAX_DESARROLLO
SEMANAS_HOLDOUT = _servicio.SEMANAS_HOLDOUT
FUNDOS = _servicio.FUNDOS
ALIASES_FUNDO = _servicio.ALIASES_FUNDO
TOKENS_VARIANTE = _servicio.TOKENS_VARIANTE
PARAMETROS = _servicio.PARAMETROS
FEATURE_SETS = _servicio.FEATURE_SETS
FEATURES_CRUDAS = _servicio.FEATURES_CRUDAS

Configuracion = _servicio.Configuracion
_normalizar_texto = _servicio._normalizar_texto
_es_variante = _servicio._es_variante
sha256_archivo = _servicio.sha256_archivo
inventariar_libros = _servicio.inventariar_libros
_tabla_hoja = _servicio._tabla_hoja
_columna = _servicio._columna
_clave_lote = _servicio._clave_lote
leer_snapshot_libro = _servicio.leer_snapshot_libro
cargar_snapshots = _servicio.cargar_snapshots
_mediana_finita = _servicio._mediana_finita
calcular_delta_snapshot = _servicio.calcular_delta_snapshot
construir_deltas = _servicio.construir_deltas
aplicar_shrinkage_features = _servicio.aplicar_shrinkage_features
construir_contrato = _servicio.construir_contrato
_ajustar_predecir = _servicio._ajustar_predecir
predecir_temporal = _servicio.predecir_temporal
configuraciones = _servicio.configuraciones
_metricas = _servicio._metricas
_evaluar_periodo = _servicio._evaluar_periodo
seleccionar_configuracion = _servicio.seleccionar_configuracion
_keyset = _servicio._keyset
ejecutar = _servicio.ejecutar
_json_default = _servicio._json_default


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--run-id", type=int, default=RUN_ID_DEFAULT)
    parser.add_argument("--campania", default=CAMPANIA_DEFAULT)
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    resultado = ejecutar(root=args.root, run_id=args.run_id, campania=args.campania)
    texto = json.dumps(resultado, ensure_ascii=False, indent=2, default=_json_default)
    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(texto, encoding="utf-8")
    print(
        json.dumps(
            {
                "configuracion_ganadora": resultado["configuracion_ganadora"],
                "trazabilidad": resultado["trazabilidad"],
                "contrato": resultado["evaluation_contract"],
                "desarrollo": resultado["desarrollo"]["empresa"],
                "holdout": resultado["holdout"]["empresa"],
                "veredicto": resultado["veredicto"],
            },
            ensure_ascii=False,
            indent=2,
            default=_json_default,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
