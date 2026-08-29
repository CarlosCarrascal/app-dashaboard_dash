"""Construcción del parser público de ``aquanqa-analytics``."""

from __future__ import annotations

import argparse

from .bhattacharya import ejecutar_bhattacharya
from .operational import ejecutar_project_operativo, ejecutar_validar_operativo
from .relations import ejecutar_relaciones
from .torneo import ejecutar_backtest, ejecutar_export, ejecutar_project, ejecutar_train


def construir_parser(handlers: dict[str, object] | None = None) -> argparse.ArgumentParser:
    handlers = handlers or {
        "ejecutar_relaciones": ejecutar_relaciones,
        "ejecutar_backtest": ejecutar_backtest,
        "ejecutar_train": ejecutar_train,
        "ejecutar_project": ejecutar_project,
        "ejecutar_export": ejecutar_export,
        "ejecutar_bhattacharya": ejecutar_bhattacharya,
        "ejecutar_validar_operativo": ejecutar_validar_operativo,
        "ejecutar_project_operativo": ejecutar_project_operativo,
    }
    raiz = argparse.ArgumentParser(prog="aquanqa-analytics")
    sub = raiz.add_subparsers(dest="comando", required=True)

    def comunes(p):
        p.add_argument("--source", choices=["auto", "postgres", "excel"], default="auto")
        p.add_argument(
            "--no-persist",
            action="store_true",
            help="Calcula y exporta sin escribir el esquema analytics.",
        )
        p.add_argument(
            "--corte-asof",
            default=None,
            metavar="AAAA-MM-DD",
            help=(
                "Descarta todo dato posterior a esa fecha, para responder «qué se sabía "
                "el día X». Sin él se usa el histórico completo, y si la base trae fechas "
                "por delante de hoy la corrida lo declara en sus advertencias."
            ),
        )

    relaciones = sub.add_parser("relations", help="Matriz de hipótesis y evidence claims")
    comunes(relaciones)
    relaciones.add_argument("--minimo-n", type=int, default=25)
    relaciones.set_defaults(func=handlers["ejecutar_relaciones"])

    for nombre, funcion in (
        ("backtest", handlers["ejecutar_backtest"]),
        ("train", handlers["ejecutar_train"]),
        ("project", handlers["ejecutar_project"]),
        ("export", handlers["ejecutar_export"]),
    ):
        p = sub.add_parser(nombre)
        comunes(p)
        p.add_argument("--skip-ml", action="store_true")
        p.add_argument("--skip-stats", action="store_true")
        p.add_argument("--skip-componentes", action="store_true")
        p.add_argument(
            "--skip-fenologico-v1",
            action="store_true",
            help="No ejecutar el replay FenologicoComponentes_v1.",
        )
        p.add_argument(
            "--skip-macro-legacy",
            action="store_true",
            help="No ejecutar la reconstrucción MacroLegacy_v1.",
        )
        p.add_argument(
            "--fenologico-mixedlm",
            action="store_true",
            help="Incluir MixedLM en el challenger fenológico; aumenta el tiempo del replay.",
        )
        p.add_argument(
            "--skip-hibrido-legacy",
            action="store_true",
            help="No ejecutar el replay del híbrido Legacy–ML.",
        )
        p.add_argument(
            "--diagnostico-montecarlo",
            action="store_true",
            help="Añade un intervalo alternativo propagando el error de cada componente. "
            "Es diagnóstico: los intervalos publicados siguen siendo los calibrados.",
        )
        p.add_argument("--skip-explain", action="store_true")
        if nombre == "backtest":
            p.add_argument(
                "--fenologico-max-cortes",
                type=int,
                default=8,
                help="Máximo de cortes rolling-origin del challenger fenológico.",
            )
        if nombre == "project":
            p.add_argument(
                "--modelo-proyeccion",
                choices=[
                    "campeon",
                    "R09_publicado",
                    "Componentes_identidad",
                    "FenologicoComponentes_v1",
                    "HibridoLegacyResidual_v1",
                ],
                default="campeon",
                help=(
                    "campeon conserva la decisión vigente; los modelos nuevos ejecutan su "
                    "propio replay as-of y no usan predicciones R09 como feature."
                ),
            )
            p.add_argument("--fecha-emision", default=None, metavar="AAAA-MM-DD")
            p.add_argument("--horizonte-semanas", type=int, default=10)
            p.add_argument(
                "--calendario-proyeccion",
                choices=["ocurrencia", "r09_publicado"],
                default="ocurrencia",
                help="Calendario estimado con ceros históricos o calendario publicado por R09.",
            )
            p.add_argument(
                "--horizontes",
                default=None,
                help="Lista opcional separada por comas, por ejemplo 1,2,6.",
            )
            p.add_argument("--nombre-escenario", default="base")
            p.add_argument("--escenario-frutos-pct", type=float, default=0.0)
            p.add_argument("--escenario-peso-pct", type=float, default=0.0)
            p.add_argument("--escenario-plantas-pct", type=float, default=0.0)
            p.add_argument("--desplazamiento-semanas", type=int, default=0)
            p.add_argument(
                "--open-meteo-lat",
                type=float,
                help="Latitud del punto operativo; habilita snapshot climático trazable.",
            )
            p.add_argument(
                "--open-meteo-lon",
                type=float,
                help="Longitud del punto operativo; debe acompañar --open-meteo-lat.",
            )
        p.set_defaults(func=funcion)

    bhat = sub.add_parser(
        "bhattacharya", help="Descomposición poblacional de 3 oleadas (Bhattacharya)"
    )
    bhat.add_argument("--lote", default=None, help="Código de lote opcional (ej. L224, L042)")
    bhat.add_argument("--campania", default="C2026", help="Código de campaña (C2026 por defecto)")
    bhat.add_argument("--excel", default=None, help="Ruta a archivo Excel de entrada opcional")
    bhat.add_argument(
        "--exportar-excel", default=None, help="Ruta para exportar el resultado en Excel"
    )
    bhat.set_defaults(func=handlers["ejecutar_bhattacharya"])

    validar = sub.add_parser(
        "validate-operational",
        help="Valida la paridad del modelo operativo contra los libros ProySemanal",
    )
    validar.add_argument(
        "--root",
        default=None,
        help="Carpeta que contiene los cuatro libros (o AQUANQA_OPERATIVO_ROOT en .env)",
    )
    validar.add_argument(
        "--persist",
        action="store_true",
        help="Persiste el reporte en analytics.operational_model_validation",
    )
    validar.add_argument("--version-fuente", default="ProySemanal_33")
    validar.set_defaults(func=handlers["ejecutar_validar_operativo"])

    operativo = sub.add_parser(
        "operational-project",
        help="Ejecuta y persiste el modelo ProySemanal actual desde los libros Excel",
    )
    operativo.add_argument(
        "--root",
        default=None,
        help="Carpeta que contiene los cuatro libros (o AQUANQA_OPERATIVO_ROOT en .env)",
    )
    operativo.add_argument("--campania", default="C2026")
    operativo.add_argument("--fecha-emision", required=True, metavar="AAAA-MM-DD")
    operativo.add_argument("--version-fuente", default="ProySemanal_33")
    operativo.add_argument(
        "--fuente-parametros",
        choices=("postgres_auto", "excel"),
        default="postgres_auto",
        help=(
            "Origen de X/O/N/A/B. Por defecto calibra automáticamente con PostgreSQL; "
            "'excel' conserva la réplica exacta para pruebas de paridad."
        ),
    )
    operativo.add_argument("--no-persist", action="store_true")
    operativo.set_defaults(func=handlers["ejecutar_project_operativo"])

    return raiz
