"""Interfaz de línea de comandos del ETL.

Se invoca a través del orquestador del monorepo:

    npm run extract              todas las tablas
    npm run extract -- --solo e01_ramas h05_clima
    npm run load
    node scripts/run.mjs py extract --solo m_lotes_maestro
"""

from __future__ import annotations

import argparse
import sys

from aquanqa_etl.config import cargar_config


def _titulo(texto: str) -> None:
    print(f"\n\033[1m{texto}\033[0m")


def _cmd_extract(args: argparse.Namespace) -> int:
    from aquanqa_etl.extract import extraer_access, extraer_maestro_lotes, extraer_tareo

    config = cargar_config()
    solo = set(args.solo) if args.solo else None

    resultados = []
    _titulo("Maestro y orígenes externos")
    if solo is None or "m_lotes_maestro" in solo:
        resultados.append(extraer_maestro_lotes(config))
    if solo is None or "tareo" in solo:
        tareo = extraer_tareo(config)
        if tareo:
            resultados.append(tareo)

    tablas_access = solo - {"m_lotes_maestro", "tareo"} if solo else None
    if tablas_access is None or tablas_access:
        _titulo("Base Access (solo lectura)")
        resultados.extend(extraer_access(config, solo=tablas_access))

    desviadas = [r for r in resultados if not r.ok]
    total = sum(r.filas for r in resultados)
    print()
    print(f"Extraídas {len(resultados)} tablas · {total:,} filas · en {config.dir_extraccion}")
    if desviadas:
        print("\n\033[33mHay desviaciones respecto a la auditoría:\033[0m")
        for r in desviadas:
            print(f"  {r.tabla}: {r.filas:,} frente a {r.esperadas:,} ({r.desviacion:+d})")
        print("  Repite la extracción de esas tablas antes de cargar.")
        return 1
    print("Siguiente paso:  npm run load")
    return 0


def _cmd_load(args: argparse.Namespace) -> int:
    from aquanqa_etl.load import cargar_raw, resumen_carga

    config = cargar_config()
    _titulo("Carga a raw")
    resultados = cargar_raw(config, solo=set(args.solo) if args.solo else None)
    if not resultados:
        print("\nNo se cargó nada: no hay CSV en el directorio de extracción.")
        print("Ejecuta primero:  npm run extract")
        return 1
    ok = resumen_carga(resultados)
    print("\nSiguiente paso:  npm run build" if ok else "\nCorrige las desviaciones y repite.")
    return 0 if ok else 1


def _cmd_catalogo(_: argparse.Namespace) -> int:
    from aquanqa_etl.catalogo import CATALOGO_ACCESS, DESCARTADAS, total_filas_esperadas

    _titulo("Catálogo de migración")
    print(f"{'ORIGEN':<26}{'DESTINO':<26}{'COLS':>5}{'FILAS':>10}")
    for t in CATALOGO_ACCESS:
        esperadas = f"{t.filas_esperadas:,}" if t.filas_esperadas else "-"
        print(f"{t.origen:<26}raw.{t.destino:<22}{len(t.columnas):>5}{esperadas:>10}")
    print(f"\n{len(CATALOGO_ACCESS)} tablas · {total_filas_esperadas():,} filas esperadas")

    _titulo("No se migran")
    for objeto, motivo in DESCARTADAS.items():
        print(f"  {objeto}\n      {motivo}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aquanqa-etl",
        description="Extracción y carga de BD_AQUANQA_26 hacia PostgreSQL.",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p_extract = sub.add_parser("extract", help="extrae los orígenes a CSV (solo lectura)")
    p_extract.add_argument(
        "--solo", nargs="+", metavar="TABLA", help="nombres de destino a extraer"
    )
    p_extract.set_defaults(func=_cmd_extract)

    p_load = sub.add_parser("load", help="carga los CSV al esquema raw")
    p_load.add_argument("--solo", nargs="+", metavar="TABLA", help="tablas a cargar")
    p_load.set_defaults(func=_cmd_load)

    sub.add_parser("catalogo", help="muestra qué se migra y qué no").set_defaults(
        func=_cmd_catalogo
    )

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"\n\033[31m✗ {exc}\033[0m", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
