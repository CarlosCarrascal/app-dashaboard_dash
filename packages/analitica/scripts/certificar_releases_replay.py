"""Fachada CLI compatible para certificar releases de replay.

La lógica reusable vive en :mod:`analitica.servicios.certificar_releases_replay`.
Este módulo conserva aliases públicos/privados, firmas, CLI y serialización histórica.
"""

from __future__ import annotations

from analitica.servicios import certificar_releases_replay as _servicio

# Aliases históricos: la implementación única vive en el servicio.
Any = _servicio.Any
Certificacion = _servicio.Certificacion
CERTIFICACIONES = _servicio.CERTIFICACIONES
Iterable = _servicio.Iterable
RELEASE_OPERATIVA = _servicio.RELEASE_OPERATIVA
RUNS_RECHAZADOS = _servicio.RUNS_RECHAZADOS
Serie = _servicio.Serie
_filas = _servicio._filas
_registrar_contrato = _servicio._registrar_contrato
_registrar_rechazos = _servicio._registrar_rechazos
_registrar_release_operativa = _servicio._registrar_release_operativa
_registrar_releases = _servicio._registrar_releases
_sha256 = _servicio._sha256
_snapshot = _servicio._snapshot
_universo = _servicio._universo
argparse = _servicio.argparse
date = _servicio.date
dataclass = _servicio.dataclass
hashlib = _servicio.hashlib
json = _servicio.json
settings = _servicio.settings
timedelta = _servicio.timedelta
ejecutar = _servicio.ejecutar


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Registra contratos y releases")
    args = parser.parse_args()
    print(json.dumps(ejecutar(args.apply), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
