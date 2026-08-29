"""Interfaz de línea de comandos del ETL.

Se invoca a través del orquestador del monorepo:

    npm run extract              todas las tablas
    npm run extract -- --solo e01_ramas h05_clima
    npm run load
    node scripts/run.mjs py extract --solo m_lotes_maestro
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from aquanqa_etl.config import cargar_config, raiz_repo
from aquanqa_etl.extract.access import MANIFIESTO_ACCESS


def _titulo(texto: str) -> None:
    print(f"\n\033[1m{texto}\033[0m")


def _resolver_snapshot_dir(config, manifest: str | None = None) -> Path:
    """Resuelve un snapshot explícito o el último snapshot Access completo."""
    if manifest:
        ruta = Path(manifest).expanduser()
        if not ruta.is_absolute():
            ruta = raiz_repo() / ruta
        ruta = ruta.resolve()
        if not ruta.is_file():
            raise FileNotFoundError(f"No existe el manifiesto indicado: {ruta}")
        return ruta.parent
    if (config.dir_extraccion / MANIFIESTO_ACCESS).is_file():
        return config.dir_extraccion
    raiz = config.dir_extraccion / "snapshots" / config.access_campania
    candidatos = []
    for ruta in raiz.glob(f"*/{MANIFIESTO_ACCESS}"):
        try:
            contenido = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if contenido.get("snapshot_completo") is True:
            candidatos.append(ruta)
    if candidatos:
        return max(candidatos, key=lambda ruta: ruta.parent.name).parent
    return config.dir_extraccion


def _cmd_extract(args: argparse.Namespace) -> int:
    from aquanqa_etl.catalogo import CATALOGO_ACCESS
    from aquanqa_etl.extract import extraer_access, extraer_maestro_lotes, extraer_tareo

    config = cargar_config().para_campania(args.campania)
    if args.access_path:
        access_path = Path(args.access_path).expanduser()
        if not access_path.is_absolute():
            access_path = raiz_repo() / access_path
        config = replace(config, access_db=access_path.resolve())
    if args.source_version:
        config = replace(config, access_version_fuente=args.source_version)
    if args.output:
        output_path = Path(args.output).expanduser()
        if not output_path.is_absolute():
            output_path = raiz_repo() / output_path
        config = replace(config, dir_extraccion=output_path.resolve())
    solo = set(args.solo) if args.solo else None

    resultados = []
    tablas_access = solo - {"m_lotes_maestro", "tareo"} if solo else None
    if tablas_access is None or tablas_access:
        _titulo("Base Access (solo lectura)")
        resultados.extend(extraer_access(config, solo=tablas_access))

    _titulo("Orígenes externos opcionales")
    if solo is None or "m_lotes_maestro" in solo:
        if config.maestro_lotes.is_file():
            resultados.append(extraer_maestro_lotes(config))
        else:
            print(f"  maestro no disponible: {config.maestro_lotes} · se deja para otra etapa")
    if solo is None or "tareo" in solo:
        tareo = extraer_tareo(config)
        if tareo:
            resultados.append(tareo)

    desviadas = [r for r in resultados if not r.ok]
    total = sum(r.filas for r in resultados)
    print()
    print(f"Extraídas {len(resultados)} tablas · {total:,} filas · en {config.dir_extraccion}")
    if desviadas:
        print("\n\033[33mHay desviaciones respecto a la auditoría:\033[0m")
        for r in desviadas:
            print(f"  {r.tabla}: {r.filas:,} frente a {r.esperadas:,} ({r.desviacion:+d})")
        if args.allow_row_drift or not args.strict_baseline:
            print(
                "  Variación conservada como advertencia; los conteos y la huella quedan auditados."
            )
        else:
            print(
                "  Repite la extracción o usa --allow-row-drift si es crecimiento operativo "
                "esperado."
            )
            return 1
    access_origenes = {t.origen for t in CATALOGO_ACCESS}
    snapshots = {r.ruta_csv.parent for r in resultados if r.tabla in access_origenes}
    if snapshots:
        print(f"Snapshot Access listo: {next(iter(snapshots))}")
    print("Siguiente paso:  npm run load")
    return 0


def _cmd_catalogo_access(args: argparse.Namespace) -> int:
    from aquanqa_etl.extract import catalogar_access

    config = cargar_config().para_campania(args.campania)
    if args.access_path:
        access_path = Path(args.access_path).expanduser()
        if not access_path.is_absolute():
            access_path = raiz_repo() / access_path
        config = replace(config, access_db=access_path.resolve())
    if args.source_version:
        config = replace(config, access_version_fuente=args.source_version)
    if args.output:
        output_path = Path(args.output).expanduser()
        if not output_path.is_absolute():
            output_path = raiz_repo() / output_path
        config = replace(config, dir_extraccion=output_path.resolve())

    _titulo("Catálogo técnico Access (solo lectura)")
    catalogar_access(config, require_dao=args.require_dao)
    return 0


def _cmd_load(args: argparse.Namespace) -> int:
    from aquanqa_etl.load import cargar_raw, resumen_carga

    config = cargar_config()
    if args.database:
        config = replace(config, pg_database=args.database)
    config = replace(config, dir_extraccion=_resolver_snapshot_dir(config, args.manifest))
    _titulo("Carga a raw")
    resultados = cargar_raw(config, solo=set(args.solo) if args.solo else None)
    if not resultados:
        if (config.dir_extraccion / MANIFIESTO_ACCESS).is_file():
            print("\nSnapshot ya cargado o sin filas nuevas: no se insertaron duplicados.")
            return 0
        print("\nNo se cargó nada: no hay CSV en el directorio de extracción.")
        print("Ejecuta primero:  npm run extract")
        return 1
    ok = resumen_carga(resultados, strict_baseline=args.strict_baseline)
    if not ok and args.allow_row_drift:
        print("\nVariación aceptada explícitamente; la carga ya quedó auditada en raw.")
        ok = True
    print("\nSiguiente paso:  npm run build" if ok else "\nCorrige las desviaciones y repite.")
    return 0 if ok else 1


def _cmd_snapshot(args: argparse.Namespace) -> int:
    from aquanqa_etl.snapshots import promover_snapshot, rollback_snapshot, validar_snapshot

    config = cargar_config()
    if args.database:
        config = replace(config, pg_database=args.database)
    if args.accion == "validate":
        problemas = validar_snapshot(
            config,
            snapshot_id=args.snapshot_id,
            tipo=args.tipo,
            campania=args.campania,
        )
        if problemas:
            for problema in problemas:
                print(f"✗ {problema}")
            return 1
        print("OK Snapshot válido para promoción")
        return 0
    if args.accion == "promote":
        snapshot_id = promover_snapshot(
            config,
            snapshot_id=args.snapshot_id,
            tipo=args.tipo,
            campania=args.campania,
            autorizado_por=args.usuario,
            motivo=args.motivo,
        )
        print(f"OK Snapshot {snapshot_id} publicado en {config.pg_database}")
        return 0
    snapshot_id = rollback_snapshot(
        config,
        snapshot_id=args.snapshot_id,
        tipo=args.tipo,
        campania=args.campania,
        autorizado_por=args.usuario,
        motivo=args.motivo,
    )
    print(f"OK Rollback registrado; snapshot vigente: {snapshot_id or 'ninguno'}")
    return 0


def _cmd_refresh(args: argparse.Namespace) -> int:
    from aquanqa_etl.orquestador import (
        construir_plan,
        ejecutar_refresco,
        formatear_plan,
        plan_a_dict,
    )

    config = cargar_config()
    if args.database:
        config = replace(config, pg_database=args.database)

    if args.accion == "plan":
        plan = construir_plan(
            config,
            snapshot_id=args.snapshot_id,
            campania=args.campania,
        )
        contenido = json.dumps(plan_a_dict(plan), ensure_ascii=False, indent=2)
        if args.output:
            ruta = Path(args.output).expanduser()
            if not ruta.is_absolute():
                ruta = raiz_repo() / ruta
            ruta = ruta.resolve()
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(contenido + "\n", encoding="utf-8")
            print(f"Plan guardado: {ruta}")
        print(contenido if args.json else formatear_plan(plan))
        return 0

    plan = ejecutar_refresco(
        config,
        snapshot_id=args.snapshot_id,
        campania=args.campania,
        access_path=args.access_path,
        source_version=args.source_version,
        output=args.output,
        strict_baseline=args.strict_baseline,
        promover=args.promote,
        ejecutar_core=args.execute_core,
        permitir_reconstruccion_core=args.allow_full_core_rebuild,
        usuario=args.usuario,
        motivo=args.motivo,
    )
    if args.json:
        print(json.dumps(plan_a_dict(plan), ensure_ascii=False, indent=2))
    return 0


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


def _cmd_baseline(args: argparse.Namespace) -> int:
    from aquanqa_etl.baseline import registrar_baseline

    config = cargar_config()
    if args.database:
        config = replace(config, pg_database=args.database)
    registrar_baseline(config, args.output)
    return 0


def _cmd_modelo(args: argparse.Namespace) -> int:
    from aquanqa_etl.modelo import exportar_modelo, registrar_modelo, validar_modelo
    from aquanqa_etl.perfilado import mostrar_modelo

    if args.accion == "validate":
        validar_modelo()
        print("OK: catálogo semántico completo; 23 fuentes Access cubiertas exactamente")
        return 0
    if args.accion == "show":
        print(json.dumps(mostrar_modelo(), ensure_ascii=False, indent=2))
        return 0
    if args.accion == "export":
        ruta = Path(args.output or "docs/modelo/catalogo_semantico_access.json")
        if not ruta.is_absolute():
            ruta = raiz_repo() / ruta
        print(f"Catálogo semántico exportado: {exportar_modelo(ruta)}")
        return 0

    config = cargar_config()
    if args.database:
        config = replace(config, pg_database=args.database)
    resumen = registrar_modelo(config)
    print(
        "OK: modelo registrado en "
        f"{config.pg_database} · versión {resumen['modelo_version']} · "
        f"{resumen['tablas']} tablas · {resumen['bloques']} bloques · "
        f"{resumen['relaciones']} relaciones · hash {resumen['hash_modelo'][:16]}"
    )
    return 0


def _cmd_perfil(args: argparse.Namespace) -> int:
    from aquanqa_etl.perfilado import perfilar_snapshot

    config = cargar_config()
    if args.database:
        config = replace(config, pg_database=args.database)
    resumen = perfilar_snapshot(
        config,
        snapshot_id=args.snapshot_id,
        campania=args.campania,
        modelo_version=args.modelo_version,
        solo=set(args.solo) if args.solo else None,
    )
    print(
        "OK: perfilado guardado en raw · "
        f"snapshot {resumen['source_snapshot_id']} · "
        f"{resumen['tablas_perfiladas']} tablas · "
        f"{resumen['relaciones_evaluadas']} relaciones · "
        f"{resumen['tablas_con_alertas']} tablas con alertas"
    )
    if args.detalle:
        for perfil in resumen["perfiles"]:
            print(
                f"  {perfil['tabla_raw']:<28} {perfil['filas_raw']:>10,} filas · "
                f"{perfil['estado']}"
                + (f" · {perfil['detalle']}" if perfil["detalle"] else "")
            )
    return 0


def _cmd_relacion(args: argparse.Namespace) -> int:
    from aquanqa_etl.perfilado import aprobar_relacion

    if args.accion != "approve":
        raise ValueError("Acción de relación no soportada")
    config = cargar_config()
    if args.database:
        config = replace(config, pg_database=args.database)
    aprobar_relacion(
        config,
        args.codigo,
        snapshot_id=args.snapshot_id,
        usuario=args.usuario,
        motivo=args.motivo,
        modelo_version=args.modelo_version,
    )
    print(f"OK: relación {args.codigo} aprobada para snapshot {args.snapshot_id}")
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
    p_extract.add_argument(
        "--campania", choices=("C2025", "C2026"), help="copia Access autorizada a extraer"
    )
    p_extract.add_argument("--access-path", help="ruta explícita a la copia .accdb")
    p_extract.add_argument("--source-version", help="identificador de versión del archivo fuente")
    p_extract.add_argument("--output", help="raíz de salida de snapshots y CSV externos")
    p_extract.add_argument(
        "--strict-baseline",
        action="store_true",
        help="falla si los conteos difieren de la auditoría histórica",
    )
    p_extract.add_argument(
        "--allow-row-drift",
        action="store_true",
        help=(
            "Permite cargar una copia operativa con más o menos filas que la auditoría base; "
            "la desviación se informa y se conserva en el manifiesto."
        ),
    )
    p_extract.set_defaults(func=_cmd_extract)

    p_catalogo_access = sub.add_parser(
        "catalogo-access", help="inspecciona columnas, tipos, índices, claves y consultas Access"
    )
    p_catalogo_access.add_argument(
        "--campania", choices=("C2025", "C2026"), help="copia Access autorizada a inspeccionar"
    )
    p_catalogo_access.add_argument("--access-path", help="ruta explícita a la copia .accdb")
    p_catalogo_access.add_argument("--source-version", help="identificador informativo de versión")
    p_catalogo_access.add_argument("--output", help="raíz donde guardar el catálogo técnico")
    p_catalogo_access.add_argument(
        "--require-dao",
        action="store_true",
        help="falla si DAO no está disponible para leer relaciones y QueryDef.SQL",
    )
    p_catalogo_access.set_defaults(func=_cmd_catalogo_access)

    p_load = sub.add_parser("load", help="carga los CSV al esquema raw")
    p_load.add_argument("--solo", nargs="+", metavar="TABLA", help="tablas a cargar")
    p_load.add_argument("--manifest", help="manifiesto access_snapshot.json a cargar")
    p_load.add_argument("--database", help="base PostgreSQL destino; por defecto PGDATABASE")
    p_load.add_argument(
        "--mode",
        choices=("append-only",),
        default="append-only",
        help="modo de carga; append-only conserva todos los snapshots históricos",
    )
    p_load.add_argument(
        "--strict-baseline",
        action="store_true",
        help="falla si los conteos difieren de la auditoría histórica",
    )
    p_load.add_argument(
        "--allow-row-drift",
        action="store_true",
        help="Acepta crecimiento operativo frente al conteo base sin ocultar la desviación.",
    )
    p_load.set_defaults(func=_cmd_load)

    sub.add_parser("catalogo", help="muestra qué se migra y qué no").set_defaults(
        func=_cmd_catalogo
    )

    p_baseline = sub.add_parser(
        "baseline", help="registra conteos exactos de una BD PostgreSQL sin modificarla"
    )
    p_baseline.add_argument("--database", help="base PostgreSQL a registrar")
    p_baseline.add_argument("--output", help="JSON de salida para la línea base")
    p_baseline.set_defaults(func=_cmd_baseline)

    p_modelo = sub.add_parser(
        "modelo", help="valida, exporta o registra el catálogo semántico de Access"
    )
    p_modelo.add_argument(
        "accion", choices=("validate", "show", "export", "register"),
        help="operación del catálogo; register solo escribe metadata en aquanqa_migracion",
    )
    p_modelo.add_argument("--database", help="base destino para register")
    p_modelo.add_argument("--output", help="ruta destino para export")
    p_modelo.set_defaults(func=_cmd_modelo)

    p_perfil = sub.add_parser(
        "perfil", help="perfila tablas y relaciones de un snapshot Access en raw"
    )
    p_perfil.add_argument("--snapshot-id", type=int, help="snapshot Access a perfilar")
    p_perfil.add_argument("--campania", help="campaña para resolver el snapshot más reciente")
    p_perfil.add_argument("--modelo-version", help="versión semántica explícita")
    p_perfil.add_argument("--database", help="base destino; debe ser aquanqa_migracion")
    p_perfil.add_argument("--solo", nargs="+", metavar="TABLA", help="fuentes raw concretas")
    p_perfil.add_argument("--detalle", action="store_true", help="muestra cada perfil")
    p_perfil.set_defaults(func=_cmd_perfil)

    p_relacion = sub.add_parser("relacion", help="gobierna relaciones candidatas")
    relacion_sub = p_relacion.add_subparsers(dest="accion", required=True)
    p_aprobar = relacion_sub.add_parser("approve", help="aprueba una relación con evidencia válida")
    p_aprobar.add_argument("--codigo", required=True, help="código de relación del catálogo")
    p_aprobar.add_argument("--snapshot-id", required=True, type=int)
    p_aprobar.add_argument("--modelo-version")
    p_aprobar.add_argument("--database", help="base destino; debe ser aquanqa_migracion")
    p_aprobar.add_argument("--usuario", required=True)
    p_aprobar.add_argument("--motivo", required=True)
    p_aprobar.set_defaults(func=_cmd_relacion)

    p_snapshot = sub.add_parser("snapshot", help="validar, publicar o revertir snapshots")
    snapshot_sub = p_snapshot.add_subparsers(dest="accion", required=True)
    for accion in ("validate", "promote", "rollback"):
        p = snapshot_sub.add_parser(accion)
        p.add_argument(
            "--snapshot-id", "--to-snapshot", dest="snapshot_id", type=int,
            help="identificador en raw.source_snapshot (alias operativo: --to-snapshot)",
        )
        p.add_argument("--tipo", default="access")
        p.add_argument("--campania", default=None)
        p.add_argument("--database", help="base PostgreSQL destino; por defecto PGDATABASE")
        p.add_argument("--usuario", default="etl")
        p.add_argument("--motivo", default=None)
        p.set_defaults(func=_cmd_snapshot)

    p_refresh = sub.add_parser(
        "refresh",
        help="planifica y ejecuta un refresco Access controlado por snapshot y bloques",
    )
    refresh_sub = p_refresh.add_subparsers(dest="accion", required=True)

    p_refresh_plan = refresh_sub.add_parser(
        "plan",
        help="compara un snapshot raw contra el publicado sin modificar PostgreSQL",
    )
    p_refresh_plan.add_argument("--snapshot-id", type=int, help="snapshot Access ya cargado")
    p_refresh_plan.add_argument("--campania", default=None, help="campaña del snapshot")
    p_refresh_plan.add_argument(
        "--database",
        default=None,
        help="base destino; debe ser aquanqa_migracion",
    )
    p_refresh_plan.add_argument("--output", help="JSON donde guardar el plan")
    p_refresh_plan.add_argument("--json", action="store_true", help="imprime el plan como JSON")
    p_refresh_plan.set_defaults(func=_cmd_refresh)

    p_refresh_run = refresh_sub.add_parser(
        "run",
        help="extrae/carga Access, valida y ejecuta el refresco autorizado",
    )
    p_refresh_run.add_argument("--snapshot-id", type=int, help="usa un snapshot raw ya cargado")
    p_refresh_run.add_argument("--campania", default=None, help="campaña de Access")
    p_refresh_run.add_argument("--access-path", help="ruta explícita a la copia .accdb")
    p_refresh_run.add_argument("--source-version", help="identificador de versión del archivo")
    p_refresh_run.add_argument("--output", help="raíz para snapshots y CSV extraídos")
    p_refresh_run.add_argument(
        "--database",
        default=None,
        help="base destino; debe ser aquanqa_migracion",
    )
    p_refresh_run.add_argument(
        "--strict-baseline",
        action="store_true",
        help="falla si las filas difieren del baseline histórico",
    )
    p_refresh_run.add_argument(
        "--promote",
        action="store_true",
        help="publica el snapshot solo después de superar la validación",
    )
    p_refresh_run.add_argument(
        "--execute-core",
        action="store_true",
        help="ejecuta el cierre core calculado por el plan",
    )
    p_refresh_run.add_argument(
        "--allow-full-core-rebuild",
        action="store_true",
        help="autoriza reconstruir todo core cuando el core vigente ya tiene datos",
    )
    p_refresh_run.add_argument("--usuario", default="etl")
    p_refresh_run.add_argument("--motivo", default=None)
    p_refresh_run.add_argument(
        "--json", action="store_true", help="imprime el plan final como JSON"
    )
    p_refresh_run.set_defaults(func=_cmd_refresh)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (FileNotFoundError, RuntimeError, ValueError, KeyError) as exc:
        print(f"\n\033[31m✗ {exc}\033[0m", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
