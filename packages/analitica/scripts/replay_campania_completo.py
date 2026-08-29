"""Construye y persiste un replay as-of completo para una campaña cerrada.

El replay histórico de R09 no puede cubrir una campaña completa cuando Access solo
conserva unas pocas emisiones. Este script crea emisiones técnicas semanales, una
semana antes de cada cierre real, y vuelve a ejecutar MacroLegacy + OcurrenciaOnline
sin leer ningún dato posterior al corte. Esas emisiones son un instrumento de
validación, no una reconstrucción ficticia de lo que el agrónomo publicó.

La corrida final conserva los modelos de las campañas que ya estaban en la última
corrida exitosa y reemplaza únicamente la campaña solicitada por el replay completo.
"""

from __future__ import annotations

import json

from analitica.servicios import replay_campania_completo as _servicio

# Aliases históricos: la implementación única vive en el servicio.
argparse = _servicio.argparse
np = _servicio.np
pd = _servicio.pd
settings = _servicio.settings
RepositorioAnalytics = _servicio.RepositorioAnalytics
cargar_datos = _servicio.cargar_datos
backtest_macro_legacy_v1 = _servicio.backtest_macro_legacy_v1
MODELO_V1 = _servicio.MODELO_V1
VERSION_V1 = _servicio.VERSION_V1
ejecutar_replay_hibrido_ocurrencia = _servicio.ejecutar_replay_hibrido_ocurrencia
MODELO_V2 = _servicio.MODELO_V2
VERSION_V2 = _servicio.VERSION_V2
ejecutar_replay_hibrido_ocurrencia_v2 = _servicio.ejecutar_replay_hibrido_ocurrencia_v2
metricas_cobertura_operacional = _servicio.metricas_cobertura_operacional
metricas_pronostico = _servicio.metricas_pronostico
emisiones_completas = _servicio.emisiones_completas
normalizar_modelo = _servicio.normalizar_modelo
semanas_cerradas = _servicio.semanas_cerradas
MODELO_R09 = _servicio.MODELO_R09
MODELO_MACRO = _servicio.MODELO_MACRO
MODELO_NAIVE = _servicio.MODELO_NAIVE
SNAPSHOT_ID = _servicio.SNAPSHOT_ID
RUN_ORIGEN = _servicio.RUN_ORIGEN
CLAVES = _servicio.CLAVES

argumentos = _servicio.argumentos
_marcar_macro = _servicio._marcar_macro
_expandir_v1 = _servicio._expandir_v1
_naive = _servicio._naive
_metricas = _servicio._metricas
_leer_anterior = _servicio._leer_anterior
construir = _servicio.construir
persistir = _servicio.persistir
_semanas_cerradas = _servicio._semanas_cerradas
_emisiones_completas = _servicio._emisiones_completas
_normalizar_modelo = _servicio._normalizar_modelo


def main() -> None:
    print(json.dumps(persistir(argumentos()), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
