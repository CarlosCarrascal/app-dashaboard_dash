"""Micro-replay prospectivo de deltas de parámetros ProySemanal.

No persiste ni publica. Para una emisión Sxx parte de los libros Sxx-1,
aprende cambios de parámetros usando únicamente transiciones cuyo destino es
anterior a Sxx y ejecuta el motor matemático con esos parámetros estimados.

El Excel Sxx nunca se usa para construir la predicción; queda reservado para
el benchmark asistido. Esto separa el conocimiento humano contemporáneo de un
candidato realmente automático.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analitica.proyeccion.candidatos import escribir_json_reproducible
from analitica.servicios import parameter_delta_replay as _servicio

# Aliases públicos y privados históricos. La implementación de negocio vive en
# el servicio específico para que esta fachada solo conserve el contrato CLI.
ACCESS_DEFAULT = _servicio.ACCESS_DEFAULT
PARAMETROS_CALENDARIO = _servicio.PARAMETROS_CALENDARIO
PARAMETROS_CURVA = _servicio.PARAMETROS_CURVA
ROOT_DEFAULT = _servicio.ROOT_DEFAULT
TRANSITIONS_DEFAULT = _servicio.TRANSITIONS_DEFAULT
CandidateParamDelta = _servicio.CandidateParamDelta
np = _servicio.np
pd = _servicio.pd

_conexion_access = _servicio._conexion_access
_columna_campania = _servicio._columna_campania
_libros_semana = _servicio._libros_semana
_normalizar_clave = _servicio._normalizar_clave
_columna = _servicio._columna
_preparar_lote = _servicio._preparar_lote
_aplicar_modelo = _servicio._aplicar_modelo
_proyectar_emision_detallada = _servicio._proyectar_emision_detallada
_proyectar_emision = _servicio._proyectar_emision
_metricas = _servicio._metricas
ejecutar = _servicio.ejecutar

conexion_access = _servicio.conexion_access
columna_campania = _servicio.columna_campania
libros_semana = _servicio.libros_semana
normalizar_clave = _servicio.normalizar_clave
columna = _servicio.columna
preparar_lote = _servicio.preparar_lote
aplicar_modelo = _servicio.aplicar_modelo
proyectar_emision_detallada = _servicio.proyectar_emision_detallada
proyectar_emision = _servicio.proyectar_emision
cargar_reales_y_r09 = _servicio.cargar_reales_y_r09
ejecutar_proyeccion_semanal_dataframe = _servicio.ejecutar_proyeccion_semanal_dataframe
seleccionar_libros_parametros = _servicio.seleccionar_libros_parametros
leer_libro_operativo = _servicio.leer_libro_operativo


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--transitions", type=Path, default=TRANSITIONS_DEFAULT)
    parser.add_argument("--access", type=Path, default=ACCESS_DEFAULT)
    parser.add_argument("--campania", default="C2026")
    parser.add_argument("--emisiones", nargs="*", type=int, default=[28, 29, 32, 33])
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args()
    resultado = ejecutar(
        root=args.root,
        transitions=args.transitions,
        access=args.access,
        campania=args.campania,
        emisiones=tuple(args.emisiones),
    )
    if args.salida:
        escribir_json_reproducible(resultado, args.salida)
    print(json.dumps(resultado["ranking"][:10], ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
