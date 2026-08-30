"""Fachada CLI compatible para visualizar tablas comparativas de proyecciones."""

from analitica.aplicacion.servicios import ver_comparaciones as _servicio

# Aliases históricos: la implementación única vive en el servicio.
ACCDB_PATH = _servicio.ACCDB_PATH
PROY_FOLDER = _servicio.PROY_FOLDER
argparse = _servicio.argparse
os = _servicio.os
pd = _servicio.pd
postgres_dsn = _servicio.postgres_dsn
psycopg = _servicio.psycopg
sys = _servicio.sys
tabla_matriz_six = _servicio.tabla_matriz_six
tabla_real_vs_modelos = _servicio.tabla_real_vs_modelos
tabla_replicacion = _servicio.tabla_replicacion
tabla_versiones_access = _servicio.tabla_versiones_access


def main():
    parser = argparse.ArgumentParser(
        description="Visualizador CLI de tablas comparativas de Aqu Anqa"
    )
    parser.add_argument(
        "--vista",
        choices=["real", "six", "semana33", "semana32", "versiones", "todas"],
        default="todas",
        help="Tipo de tabla a visualizar (real, six, semana33, semana32, versiones, todas)",
    )

    args = parser.parse_args()

    if args.vista in ["real", "todas"]:
        tabla_real_vs_modelos()
        print()

    if args.vista in ["semana33", "todas"]:
        tabla_replicacion(33)
        print()

    if args.vista in ["semana32", "todas"]:
        tabla_replicacion(32)
        print()

    if args.vista in ["six", "todas"]:
        tabla_matriz_six()
        print()

    if args.vista in ["versiones", "todas"]:
        tabla_versiones_access()


if __name__ == "__main__":
    main()
