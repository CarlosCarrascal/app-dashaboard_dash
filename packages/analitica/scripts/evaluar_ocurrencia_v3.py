"""Evalúa OcurrenciaOnline v3 contra las versiones actuales sin persistir."""

from __future__ import annotations

import argparse
import json

from analitica.servicios import evaluacion_ocurrencia_v3 as _evaluacion

# Fachada compatible: la lógica reusable vive en el servicio único.
cargar_datos = _evaluacion.cargar_datos
backtest_macro_legacy_v1 = _evaluacion.backtest_macro_legacy_v1
ejecutar_replay_hibrido_ocurrencia = _evaluacion.ejecutar_replay_hibrido_ocurrencia
ejecutar_replay_hibrido_ocurrencia_v2 = _evaluacion.ejecutar_replay_hibrido_ocurrencia_v2
ejecutar_replay_hibrido_ocurrencia_v3 = _evaluacion.ejecutar_replay_hibrido_ocurrencia_v3
emisiones_completas = _evaluacion.emisiones_completas
metricas_pronostico = _evaluacion.metricas_pronostico
normalizar_modelo = _evaluacion.normalizar_modelo
_emisiones_completas = _evaluacion._emisiones_completas
_normalizar_modelo = _evaluacion._normalizar_modelo
_metricas = _evaluacion._metricas
metricas = _evaluacion.metricas
evaluar = _evaluacion.evaluar
evaluar_ocurrencia_v3 = _evaluacion.evaluar_ocurrencia_v3
ejecutar = _evaluacion.ejecutar


def main() -> None:
    # La ayuda debe ser segura: la ejecución real consulta PostgreSQL y solo debe ocurrir
    # después de que argparse haya atendido ``--help``. Se conservan argumentos históricos
    # desconocidos para no romper invocaciones existentes.
    argparse.ArgumentParser(description=__doc__).parse_known_args()
    datos = cargar_datos("postgres")
    salidas = evaluar(datos, campania="C2026")
    print(json.dumps(salidas, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
