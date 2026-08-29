"""Fachada CLI compatible del screening honesto de clima y fenología."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.servicios import fenologia_honest as _fenologia_honest

# Alias históricos: la implementación única vive en el servicio.
CAMPANIA = _fenologia_honest.CAMPANIA
RUN_ID = _fenologia_honest.RUN_ID
SEMANA_INICIAL = _fenologia_honest.SEMANA_INICIAL
SEMANA_DESARROLLO_FINAL = _fenologia_honest.SEMANA_DESARROLLO_FINAL
SEMANAS_HOLDOUT = _fenologia_honest.SEMANAS_HOLDOUT
HORIZONTES = _fenologia_honest.HORIZONTES
CIERRE_CERTIFICADO = _fenologia_honest.CIERRE_CERTIFICADO
TBASES = _fenologia_honest.TBASES
VENTANAS = _fenologia_honest.VENTANAS
FUNDOS = _fenologia_honest.FUNDOS
RUNS_EXTERNOS = _fenologia_honest.RUNS_EXTERNOS
MAPEO_FUNDO = _fenologia_honest.MAPEO_FUNDO
SQL_MACRO = _fenologia_honest.SQL_MACRO
SQL_CLIMA = _fenologia_honest.SQL_CLIMA
SQL_ESTADOS = _fenologia_honest.SQL_ESTADOS
SQL_FLORES = _fenologia_honest.SQL_FLORES

Configuracion = _fenologia_honest.Configuracion
_normalizar_fundo = _fenologia_honest._normalizar_fundo
_leer_dataframe = _fenologia_honest._leer_dataframe
leer_fuentes = _fenologia_honest.leer_fuentes
preparar_macro = _fenologia_honest.preparar_macro
preparar_clima = _fenologia_honest.preparar_clima
construir_clima_asof = _fenologia_honest.construir_clima_asof
_preparar_estados = _fenologia_honest._preparar_estados
_preparar_flores = _fenologia_honest._preparar_flores
construir_fenologia_asof = _fenologia_honest.construir_fenologia_asof
agregar_curvas_fundo = _fenologia_honest.agregar_curvas_fundo
redistribuir_curva = _fenologia_honest.redistribuir_curva
_columna_clima = _fenologia_honest._columna_clima
_escalar_entrenamiento = _fenologia_honest._escalar_entrenamiento
construir_panel_features = _fenologia_honest.construir_panel_features
calcular_desplazamientos = _fenologia_honest.calcular_desplazamientos
aplicar_desplazamientos = _fenologia_honest.aplicar_desplazamientos
_filtro_scope = _fenologia_honest._filtro_scope
metricas = _fenologia_honest.metricas
metricas_por_fundo = _fenologia_honest.metricas_por_fundo
_configuraciones = _fenologia_honest._configuraciones
_resumen_config = _fenologia_honest._resumen_config
seleccionar_configuracion = _fenologia_honest.seleccionar_configuracion
evaluar_gates = _fenologia_honest.evaluar_gates
_cobertura_fuentes = _fenologia_honest._cobertura_fuentes
_evaluar_externa = _fenologia_honest._evaluar_externa
evaluar = _fenologia_honest.evaluar
_json_limpio = _fenologia_honest._json_limpio
sha256_dataframe = _fenologia_honest.sha256_dataframe

__all__ = [
    "CAMPANIA",
    "CIERRE_CERTIFICADO",
    "Configuracion",
    "FUNDOS",
    "HORIZONTES",
    "RUN_ID",
    "RUNS_EXTERNOS",
    "SEMANA_DESARROLLO_FINAL",
    "SEMANA_INICIAL",
    "SEMANAS_HOLDOUT",
    "SQL_CLIMA",
    "SQL_ESTADOS",
    "SQL_FLORES",
    "SQL_MACRO",
    "TBASES",
    "VENTANAS",
    "agregar_curvas_fundo",
    "aplicar_desplazamientos",
    "calcular_desplazamientos",
    "construir_clima_asof",
    "construir_fenologia_asof",
    "construir_panel_features",
    "evaluar",
    "evaluar_gates",
    "leer_fuentes",
    "metricas",
    "metricas_por_fundo",
    "preparar_clima",
    "preparar_macro",
    "redistribuir_curva",
    "seleccionar_configuracion",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--salida",
        type=Path,
        default=Path(".tmp/screening_gdd_fenologia_honest.json"),
    )
    parser.add_argument("--sin-externas", action="store_true")
    args = parser.parse_args()
    macro, clima, estados, flores = leer_fuentes()
    resultado = evaluar(
        macro,
        clima,
        estados,
        flores,
        evaluar_externas=not args.sin_externas,
    )
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(
        json.dumps(_json_limpio(resultado), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    decision = resultado["decision"]
    print(json.dumps(decision, ensure_ascii=False, sort_keys=True))
    print(str(args.salida.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
