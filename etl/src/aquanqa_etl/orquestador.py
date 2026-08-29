"""Orquestador controlado de refrescos Access -> raw -> stg -> core.

Este módulo concentra la decisión que antes quedaba repartida entre comandos manuales:

* identifica el snapshot Access cargado y el snapshot vigente anterior;
* compara filas y estructura por tabla;
* calcula el cierre de dependencias del modelo semántico;
* distingue fuentes ``core`` de fuentes ``raw_only``;
* no publica un snapshot que todavía no tenga una ruta segura para core;
* ejecuta la reconstrucción física actual únicamente con autorización explícita, backup,
  transacción única y rollback de la publicación si algún bloque falla.

La base ``aquanqa`` nunca es un destino válido para este flujo. La aplicación móvil y el
panel administrativo quedan fuera de este módulo: ambos podrán consumir la base cuando el
contrato core esté publicado, pero no intervienen en la migración.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from aquanqa_etl.baseline import registrar_baseline
from aquanqa_etl.config import Config, raiz_repo

TARGET_DATABASE = "aquanqa_migracion"
DEFAULT_CAMPANIA = "C2026"

# El orden es deliberado. Los archivos ya contienen sus guards, el registro de run y el
# registro de linaje; el orquestador solo decide cuándo se permite ejecutarlos.
BLOCK_SCRIPTS: dict[str, str] = {
    "B01_IDENTIDAD": "db/tools/migrar_maestro_lotes.sql",
    "B02_CONTEXTO": "db/tools/migrar_b02_contexto.sql",
    "B03_FENOLOGIA": "db/tools/migrar_b03_fenologia.sql",
    "B04_OPERACION": "db/tools/migrar_b04_operacion.sql",
    "B05_PRONOSTICO": "db/tools/migrar_b05_pronostico.sql",
}
RAW_ONLY_SCRIPT = "db/tools/cerrar_b06_raw_only.sql"
PREFLIGHT_SCRIPT = "db/tools/preflight_migracion.sql"
AUDIT_SCRIPT = "db/tools/auditoria_final_migracion.sql"


@dataclass(frozen=True, slots=True)
class DeltaTabla:
    """Delta persistido en ``raw.source_table_delta`` para una tabla."""

    tabla_raw: str
    filas_anteriores: int = 0
    filas_actuales: int = 0
    filas_nuevas: int = 0
    filas_eliminadas: int = 0
    filas_modificadas: int = 0

    @property
    def hay_cambio(self) -> bool:
        return any(
            (
                self.filas_nuevas,
                self.filas_eliminadas,
                self.filas_modificadas,
            )
        )


@dataclass(frozen=True, slots=True)
class ContratoTabla:
    """Parte del modelo vigente necesaria para planificar un refresco."""

    tabla_raw: str
    bloque: str | None
    decision: str


@dataclass(frozen=True, slots=True)
class ContratoBloque:
    """Bloque y sus prerequisitos tomados de la versión de modelo aprobada."""

    codigo: str
    orden: int
    tablas_raw: tuple[str, ...]
    prerequisitos: tuple[str, ...]
    cargable: bool = True


@dataclass(frozen=True, slots=True)
class CambioTabla:
    tabla_raw: str
    bloque: str | None
    decision: str | None
    filas_anteriores: int
    filas_actuales: int
    filas_nuevas: int
    filas_eliminadas: int
    filas_modificadas: int
    cambio_esquema: bool
    cambio: bool
    motivo: str


@dataclass(frozen=True, slots=True)
class PlanRefresco:
    """Resultado reproducible de la comparación de un snapshot contra el vigente."""

    snapshot_objetivo_id: int
    snapshot_objetivo_estado: str
    snapshot_anterior_id: int | None
    campania: str
    modelo_version: str
    estado: str
    modo_ejecucion: str
    core_poblado: bool
    tablas_cambiadas: tuple[str, ...]
    tablas_raw_only_cambiadas: tuple[str, ...]
    tablas_schema_cambiado: tuple[str, ...]
    bloques_directos: tuple[str, ...]
    bloques_requeridos: tuple[str, ...]
    bloques_ejecucion: tuple[str, ...]
    deltas_faltantes: tuple[str, ...]
    razones: tuple[str, ...]
    detalle_tablas: tuple[CambioTabla, ...]

    @property
    def requiere_core(self) -> bool:
        return bool(self.bloques_directos)

    @property
    def requiere_reconstruccion_completa(self) -> bool:
        return self.modo_ejecucion == "reconstruccion_core_completa"


def _orden_bloques(bloques: Sequence[ContratoBloque]) -> list[ContratoBloque]:
    return sorted(bloques, key=lambda bloque: (bloque.orden, bloque.codigo))


def _cierre_bloques(
    bloques: Sequence[ContratoBloque], directos: set[str]
) -> tuple[str, ...]:
    """Calcula prerequisitos y descendientes afectados, conservando el orden técnico.

    Los descendientes se expanden desde los bloques que cambiaron directamente, no desde
    los prerequisitos que se vuelve necesario repetir. Así, un cambio en B04 no dispara B03
    o B05, mientras que un cambio en B01 sí invalida todas sus ramas descendientes.
    """
    por_codigo = {bloque.codigo: bloque for bloque in bloques}
    directos_validos = {codigo for codigo in directos if codigo in por_codigo}
    seleccionados = set(directos_validos)

    pendientes = list(directos_validos)
    while pendientes:
        codigo = pendientes.pop()
        for prerequisito in por_codigo[codigo].prerequisitos:
            if prerequisito in por_codigo and prerequisito not in seleccionados:
                seleccionados.add(prerequisito)
                pendientes.append(prerequisito)

    descendientes = set(directos_validos)
    cambio = True
    while cambio:
        cambio = False
        for bloque in bloques:
            if bloque.codigo in descendientes:
                continue
            if any(prerequisito in descendientes for prerequisito in bloque.prerequisitos):
                descendientes.add(bloque.codigo)
                cambio = True
    seleccionados.update(descendientes)
    return tuple(
        bloque.codigo
        for bloque in _orden_bloques(bloques)
        if bloque.codigo in seleccionados
    )


def calcular_plan(
    *,
    snapshot_objetivo_id: int,
    snapshot_objetivo_estado: str,
    campania: str,
    modelo_version: str,
    snapshot_anterior_id: int | None,
    deltas: Mapping[str, DeltaTabla],
    schema_hashes_objetivo: Mapping[str, str | None],
    schema_hashes_anterior: Mapping[str, str | None],
    tablas_modelo: Sequence[ContratoTabla],
    bloques_modelo: Sequence[ContratoBloque],
    core_poblado: bool,
) -> PlanRefresco:
    """Construye un plan sin hacer I/O.

    El cierre de dependencias se calcula siempre. Cuando ya existe core publicado, los
    scripts físicos actuales no permiten reconstruir solo una rama sin limpiar objetos
    dependientes; en ese caso ``bloques_requeridos`` sigue mostrando el mínimo semántico,
    pero ``bloques_ejecucion`` contiene todos los bloques cargables y el modo exige una
    reconstrucción completa protegida.
    """
    bloques_por_codigo = {bloque.codigo: bloque for bloque in bloques_modelo}
    tablas_ordenadas = sorted(tablas_modelo, key=lambda tabla: tabla.tabla_raw)
    cambios: list[CambioTabla] = []
    faltantes: list[str] = []

    mismo_snapshot = snapshot_anterior_id == snapshot_objetivo_id
    for contrato in tablas_ordenadas:
        delta = deltas.get(contrato.tabla_raw)
        if delta is None:
            faltantes.append(contrato.tabla_raw)
            delta = DeltaTabla(contrato.tabla_raw)
        hash_objetivo = schema_hashes_objetivo.get(contrato.tabla_raw)
        hash_anterior = schema_hashes_anterior.get(contrato.tabla_raw)
        cambio_esquema = (
            not mismo_snapshot
            and hash_objetivo != hash_anterior
            and (hash_objetivo is not None or hash_anterior is not None)
        )
        cambio_filas = False if mismo_snapshot else delta.hay_cambio
        cambio = cambio_filas or cambio_esquema
        motivos: list[str] = []
        if cambio_filas:
            motivos.append("filas")
        if cambio_esquema:
            motivos.append("esquema")
        cambios.append(
            CambioTabla(
                tabla_raw=contrato.tabla_raw,
                bloque=contrato.bloque,
                decision=contrato.decision,
                filas_anteriores=delta.filas_anteriores,
                filas_actuales=delta.filas_actuales,
                filas_nuevas=delta.filas_nuevas,
                filas_eliminadas=delta.filas_eliminadas,
                filas_modificadas=delta.filas_modificadas,
                cambio_esquema=cambio_esquema,
                cambio=cambio,
                motivo=" + ".join(motivos) if motivos else "sin cambio",
            )
        )

    cambios_reales = [cambio for cambio in cambios if cambio.cambio]
    tablas_cambiadas = tuple(cambio.tabla_raw for cambio in cambios_reales)
    tablas_schema = tuple(cambio.tabla_raw for cambio in cambios_reales if cambio.cambio_esquema)
    tablas_raw_only = tuple(
        cambio.tabla_raw
        for cambio in cambios_reales
        if cambio.decision == "raw_only"
    )
    tablas_sin_bloque = tuple(
        cambio.tabla_raw
        for cambio in cambios_reales
        if cambio.bloque is None or cambio.bloque not in bloques_por_codigo
    )

    directos = {
        cambio.bloque
        for cambio in cambios_reales
        if cambio.decision == "core"
        and cambio.bloque is not None
        and cambio.bloque in bloques_por_codigo
        and bloques_por_codigo[cambio.bloque].cargable
    }
    directos = {codigo for codigo in directos if codigo}
    requeridos = _cierre_bloques(bloques_modelo, directos)
    cargables = tuple(
        bloque.codigo for bloque in _orden_bloques(bloques_modelo) if bloque.cargable
    )

    razones: list[str] = []
    if mismo_snapshot:
        razones.append(
            "El snapshot objetivo ya es el snapshot Access publicado; se trata de un no-op."
        )
    if faltantes:
        razones.append(
            "Faltan deltas por tabla; no se puede demostrar un check-to-check completo: "
            + ", ".join(faltantes)
        )
    if tablas_sin_bloque:
        razones.append(
            "Hay tablas modificadas fuera del modelo vigente: " + ", ".join(tablas_sin_bloque)
        )
    if directos:
        razones.append(
            "Cambios core directos en: " + ", ".join(sorted(directos))
        )
    if tablas_raw_only:
        razones.append(
            "Cambios raw_only conservados sin promoción a core: "
            + ", ".join(tablas_raw_only)
        )

    if faltantes or tablas_sin_bloque:
        estado = "bloqueado_incompleto"
        modo = "detenido"
        ejecucion: tuple[str, ...] = ()
    elif not cambios_reales:
        estado = "sin_cambios"
        modo = "no_op"
        ejecucion = ()
    elif directos and core_poblado:
        estado = "requiere_reconstruccion_core"
        modo = "reconstruccion_core_completa"
        ejecucion = cargables
        razones.append(
            "El core vigente tiene datos y los scripts físicos reconstruyen tablas con "
            "TRUNCATE/DELETE; se ejecutarán todos los bloques core dentro de una transacción."
        )
    elif directos:
        estado = "listo_para_bloques"
        modo = "bloques_dependientes"
        ejecucion = requeridos
        razones.append(
            "El core no tiene una ejecución publicada previa; se puede construir el "
            "cierre requerido."
        )
    else:
        estado = "raw_only"
        modo = "solo_raw"
        ejecucion = ()

    return PlanRefresco(
        snapshot_objetivo_id=int(snapshot_objetivo_id),
        snapshot_objetivo_estado=str(snapshot_objetivo_estado),
        snapshot_anterior_id=(
            int(snapshot_anterior_id) if snapshot_anterior_id is not None else None
        ),
        campania=str(campania),
        modelo_version=str(modelo_version),
        estado=estado,
        modo_ejecucion=modo,
        core_poblado=bool(core_poblado),
        tablas_cambiadas=tablas_cambiadas,
        tablas_raw_only_cambiadas=tablas_raw_only,
        tablas_schema_cambiado=tablas_schema,
        bloques_directos=tuple(
            bloque.codigo for bloque in _orden_bloques(bloques_modelo) if bloque.codigo in directos
        ),
        bloques_requeridos=requeridos,
        bloques_ejecucion=ejecucion,
        deltas_faltantes=tuple(faltantes),
        razones=tuple(razones),
        detalle_tablas=tuple(cambios),
    )


def plan_a_dict(plan: PlanRefresco) -> dict[str, Any]:
    """Serializa el plan sin perder los detalles por tabla."""
    return asdict(plan)


def formatear_plan(plan: PlanRefresco) -> str:
    """Devuelve una salida humana breve y auditable para consola."""
    lineas = [
        "Plan de refresco Access",
        f"  snapshot objetivo : {plan.snapshot_objetivo_id} ({plan.snapshot_objetivo_estado})",
        f"  snapshot anterior : {plan.snapshot_anterior_id or 'ninguno'}",
        f"  campaña           : {plan.campania}",
        f"  modelo            : {plan.modelo_version}",
        f"  estado            : {plan.estado}",
        f"  modo              : {plan.modo_ejecucion}",
        f"  tablas cambiadas  : {len(plan.tablas_cambiadas)}",
        f"  bloques directos  : {', '.join(plan.bloques_directos) or 'ninguno'}",
        f"  cierre requerido  : {', '.join(plan.bloques_requeridos) or 'ninguno'}",
        f"  ejecución prevista: {', '.join(plan.bloques_ejecucion) or 'ninguna'}",
    ]
    if plan.tablas_cambiadas:
        lineas.append("  detalle de cambios:")
        for cambio in plan.detalle_tablas:
            if cambio.cambio:
                lineas.append(
                    f"    - {cambio.tabla_raw}: {cambio.motivo}; "
                    f"+{cambio.filas_nuevas}/-{cambio.filas_eliminadas}/"
                    f"~{cambio.filas_modificadas} filas"
                )
    if plan.razones:
        lineas.append("  decisiones:")
        lineas.extend(f"    - {razon}" for razon in plan.razones)
    return "\n".join(lineas)


def _exigir_base_objetivo(config: Config) -> None:
    if config.pg_database != TARGET_DATABASE:
        raise RuntimeError(
            "El orquestador solo puede escribir en aquanqa_migracion; "
            f"la base recibida es {config.pg_database!r}. La base aquanqa del dashboard "
            "queda intacta."
        )
    import psycopg

    with psycopg.connect(config.dsn) as conexion, conexion.cursor() as cur:
        cur.execute("SELECT current_database()")
        actual = str(cur.fetchone()[0])
    if actual != TARGET_DATABASE:
        raise RuntimeError(
            f"Conexión insegura: PostgreSQL devolvió {actual!r}; se exige {TARGET_DATABASE!r}."
        )


def _fila_snapshot(cur, snapshot_id: int | None, campania: str) -> tuple[Any, ...] | None:
    if snapshot_id is None:
        cur.execute(
            """
            SELECT source_snapshot_id, campania, estado
            FROM raw.source_snapshot
            WHERE tipo = 'access' AND campania = %s
            ORDER BY extraido_en DESC, source_snapshot_id DESC
            LIMIT 1
            """,
            (campania,),
        )
    else:
        cur.execute(
            """
            SELECT source_snapshot_id, campania, estado
            FROM raw.source_snapshot
            WHERE source_snapshot_id = %s
            """,
            (snapshot_id,),
        )
    return cur.fetchone()


def _modelo_desde_bd(cur) -> tuple[str, tuple[ContratoTabla, ...], tuple[ContratoBloque, ...]]:
    cur.execute("SELECT raw.fn_modelo_version_vigente()")
    modelo_version = str(cur.fetchone()[0])
    cur.execute(
        """
        SELECT bloque, orden, tablas_raw, prerequisitos, cargable
        FROM raw.migracion_modelo_bloque
        WHERE modelo_version = %s
        ORDER BY orden, bloque
        """,
        (modelo_version,),
    )
    bloques = tuple(
        ContratoBloque(
            codigo=str(fila[0]),
            orden=int(fila[1]),
            tablas_raw=tuple(fila[2] or ()),
            prerequisitos=tuple(fila[3] or ()),
            cargable=bool(fila[4]),
        )
        for fila in cur.fetchall()
    )
    cur.execute(
        """
        SELECT tabla_raw, bloque, decision
        FROM raw.migracion_modelo_tabla
        WHERE modelo_version = %s
        ORDER BY tabla_raw
        """,
        (modelo_version,),
    )
    tablas = tuple(
        ContratoTabla(str(fila[0]), str(fila[1]) if fila[1] is not None else None, str(fila[2]))
        for fila in cur.fetchall()
    )
    if not bloques or not tablas:
        raise RuntimeError(
            f"El modelo vigente {modelo_version!r} no tiene bloques y tablas registradas."
        )
    return modelo_version, tablas, bloques


def construir_plan(
    config: Config,
    *,
    snapshot_id: int | None = None,
    campania: str | None = None,
) -> PlanRefresco:
    """Lee PostgreSQL y construye el plan para un snapshot ya cargado."""
    _exigir_base_objetivo(config)
    import psycopg

    campania_real = (campania or config.access_campania or DEFAULT_CAMPANIA).upper()
    with psycopg.connect(config.dsn) as conexion, conexion.cursor() as cur:
        fila = _fila_snapshot(cur, snapshot_id, campania_real)
        if not fila:
            raise RuntimeError(
                f"No existe snapshot Access para campaña {campania_real!r}"
                + (f" con id {snapshot_id}." if snapshot_id is not None else ".")
            )
        objetivo_id, campania_objetivo, estado_objetivo = fila
        if str(campania_objetivo).upper() != campania_real:
            raise RuntimeError(
                f"El snapshot {objetivo_id} pertenece a {campania_objetivo!r}, "
                f"no a {campania_real!r}."
            )

        cur.execute(
            """
            SELECT source_snapshot_id
            FROM raw.v_snapshot_publicado
            WHERE tipo = 'access' AND campania = %s
            """,
            (campania_real,),
        )
        fila_anterior = cur.fetchone()
        anterior_id = (
            int(fila_anterior[0])
            if fila_anterior and fila_anterior[0] is not None
            else None
        )

        modelo_version, tablas_modelo, bloques_modelo = _modelo_desde_bd(cur)
        cur.execute(
            """
            SELECT tabla_destino, filas_anteriores, filas_actuales,
                   filas_nuevas, filas_eliminadas, filas_modificadas
            FROM raw.source_table_delta
            WHERE source_snapshot_id = %s
            """,
            (objetivo_id,),
        )
        deltas = {
            str(fila[0]): DeltaTabla(
                tabla_raw=str(fila[0]),
                filas_anteriores=int(fila[1]),
                filas_actuales=int(fila[2]),
                filas_nuevas=int(fila[3]),
                filas_eliminadas=int(fila[4]),
                filas_modificadas=int(fila[5]),
            )
            for fila in cur.fetchall()
        }
        cur.execute(
            """
            SELECT tabla_destino, schema_hash
            FROM raw.source_table_snapshot
            WHERE source_snapshot_id = %s
            """,
            (objetivo_id,),
        )
        hashes_objetivo = {str(fila[0]): fila[1] for fila in cur.fetchall()}
        hashes_anterior: dict[str, str | None] = {}
        if anterior_id is not None:
            cur.execute(
                """
                SELECT tabla_destino, schema_hash
                FROM raw.source_table_snapshot
                WHERE source_snapshot_id = %s
                """,
                (anterior_id,),
            )
            hashes_anterior = {str(fila[0]): fila[1] for fila in cur.fetchall()}

        core_poblado = False
        if anterior_id is not None:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM raw.migracion_tabla mt
                    JOIN raw.migracion_run mr USING (migracion_run_id)
                    WHERE mr.source_snapshot_id = %s
                      AND mr.capa_destino = 'core'
                      AND mt.estado IN ('migrada', 'migrada_con_observaciones')
                )
                """,
                (anterior_id,),
            )
            core_poblado = bool(cur.fetchone()[0])

    return calcular_plan(
        snapshot_objetivo_id=int(objetivo_id),
        snapshot_objetivo_estado=str(estado_objetivo),
        campania=campania_real,
        modelo_version=modelo_version,
        snapshot_anterior_id=anterior_id,
        deltas=deltas,
        schema_hashes_objetivo=hashes_objetivo,
        schema_hashes_anterior=hashes_anterior,
        tablas_modelo=tablas_modelo,
        bloques_modelo=bloques_modelo,
        core_poblado=core_poblado,
    )


def _resolver_executable(nombre: str, variables: Iterable[str], versiones: Iterable[str]) -> str:
    for variable in variables:
        valor = os.environ.get(variable)
        if valor and Path(valor).is_file():
            return str(Path(valor).resolve())
    encontrado = shutil.which(nombre)
    if encontrado:
        return encontrado
    for version in versiones:
        candidato = Path(f"C:/Program Files/PostgreSQL/{version}/bin/{nombre}.exe")
        if candidato.is_file():
            return str(candidato)
    raise RuntimeError(
        f"No encuentro {nombre}. Define {next(iter(variables), nombre.upper() + '_EXE')} "
        "en .env o instala PostgreSQL."
    )


def _entorno_postgres(config: Config) -> dict[str, str]:
    entorno = os.environ.copy()
    entorno["PGCLIENTENCODING"] = "UTF8"
    if config.pg_password:
        entorno["PGPASSWORD"] = config.pg_password
    return entorno


def _ejecutar_psql(
    config: Config,
    archivos: Sequence[Path],
    *,
    transaccion_unica: bool,
) -> None:
    psql = _resolver_executable("psql", ("PSQL_EXE",), ("18", "17", "16", "15"))
    comandos = [
        psql,
        "--no-psqlrc",
        "-v",
        "ON_ERROR_STOP=1",
        "--pset",
        "pager=off",
        "--host",
        config.pg_host,
        "--port",
        str(config.pg_port),
        "--username",
        config.pg_user,
        "--dbname",
        config.pg_database,
    ]
    if transaccion_unica:
        comandos.append("--single-transaction")
    for archivo in archivos:
        comandos.extend(("--file", str(archivo)))
    resultado = subprocess.run(
        comandos,
        cwd=raiz_repo(),
        env=_entorno_postgres(config),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    salida = "\n".join(parte for parte in (resultado.stdout, resultado.stderr) if parte)
    if salida.strip():
        print(salida.rstrip())
    if resultado.returncode != 0:
        nombres = ", ".join(archivo.name for archivo in archivos)
        raise RuntimeError(
            f"psql falló al ejecutar [{nombres}] (código {resultado.returncode})."
        )


def _crear_guardas(config: Config) -> tuple[Path, Path]:
    """Crea backup físico y baseline antes de reconstruir core."""
    pg_dump = _resolver_executable(
        "pg_dump", ("PGDUMP_EXE", "PG_DUMP_EXE"), ("18", "17", "16", "15")
    )
    marca = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    directorio = raiz_repo() / "data" / "salida" / "guardas"
    directorio.mkdir(parents=True, exist_ok=True)
    dump = (directorio / f"{TARGET_DATABASE}_refresh_{marca}.dump").resolve()
    baseline = (directorio / f"{TARGET_DATABASE}_refresh_{marca}.baseline.json").resolve()
    comandos = [
        pg_dump,
        "--format=custom",
        "--file",
        str(dump),
        "--host",
        config.pg_host,
        "--port",
        str(config.pg_port),
        "--username",
        config.pg_user,
        "--dbname",
        config.pg_database,
        "--no-owner",
        "--no-privileges",
    ]
    resultado = subprocess.run(
        comandos,
        cwd=raiz_repo(),
        env=_entorno_postgres(config),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if resultado.stdout.strip():
        print(resultado.stdout.rstrip())
    if resultado.returncode != 0:
        if dump.exists():
            dump.unlink()
        detalle = resultado.stderr.strip() or "sin detalle de pg_dump"
        raise RuntimeError(f"No se pudo crear el backup {dump}: {detalle}")
    registrar_baseline(config, baseline)
    print(f"Backup core/raw: {dump}")
    print(f"Baseline: {baseline}")
    return dump, baseline


def _ruta_script(relativa: str) -> Path:
    ruta = (raiz_repo() / relativa).resolve()
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el script del orquestador: {ruta}")
    return ruta


def _ejecutar_core(plan: PlanRefresco, config: Config) -> bool:
    if plan.campania != DEFAULT_CAMPANIA:
        raise RuntimeError(
            "Los scripts de bloques actuales están parametrizados para C2026; "
            f"no se ejecuta core para {plan.campania}."
        )
    archivos = [_ruta_script(BLOCK_SCRIPTS[codigo]) for codigo in plan.bloques_ejecucion]
    archivos.append(_ruta_script(RAW_ONLY_SCRIPT))
    auditoria_final = set(BLOCK_SCRIPTS).issubset(plan.bloques_ejecucion)
    if auditoria_final:
        archivos.append(_ruta_script(AUDIT_SCRIPT))
    _ejecutar_psql(config, archivos, transaccion_unica=True)
    return auditoria_final


def _verificar_bloques_publicados(plan: PlanRefresco, config: Config) -> None:
    """Cierra el check-to-check mínimo cuando el plan fue deliberadamente parcial."""
    import psycopg

    esperados = set(plan.bloques_ejecucion)
    with psycopg.connect(config.dsn) as conexion, conexion.cursor() as cur:
        cur.execute(
            """
            SELECT bloque, estado
            FROM raw.migracion_bloque_ejecucion
            WHERE modelo_version = %s
              AND source_snapshot_id = %s
              AND bloque = ANY(%s)
            """,
            (plan.modelo_version, plan.snapshot_objetivo_id, list(esperados)),
        )
        estados = {str(fila[0]): str(fila[1]) for fila in cur.fetchall()}
    faltantes = sorted(codigo for codigo in esperados if estados.get(codigo) != "publicado")
    if faltantes:
        detalle = ", ".join(
            f"{codigo}={estados.get(codigo, 'sin registro')}" for codigo in faltantes
        )
        raise RuntimeError(f"El check-to-check de los bloques no cerró correctamente: {detalle}.")


def _resolver_snapshot_cargado(
    config: Config,
    *,
    campania: str,
    access_path: str | Path | None,
    source_version: str | None,
    output: str | Path | None,
    strict_baseline: bool,
    registrar=print,
) -> int:
    """Extrae solo Access, carga raw append-only y devuelve el id por SHA."""
    from dataclasses import replace

    from aquanqa_etl.catalogo import CATALOGO_ACCESS
    from aquanqa_etl.extract import extraer_access
    from aquanqa_etl.extract.access import MANIFIESTO_ACCESS
    from aquanqa_etl.load import cargar_raw, resumen_carga

    config_fuente = config.para_campania(campania)
    if access_path:
        ruta_access = Path(access_path).expanduser()
        if not ruta_access.is_absolute():
            ruta_access = raiz_repo() / ruta_access
        config_fuente = replace(config_fuente, access_db=ruta_access.resolve())
    if source_version:
        config_fuente = replace(config_fuente, access_version_fuente=source_version)
    if output:
        ruta_salida = Path(output).expanduser()
        if not ruta_salida.is_absolute():
            ruta_salida = raiz_repo() / ruta_salida
        config_fuente = replace(config_fuente, dir_extraccion=ruta_salida.resolve())

    destinos_access = {tabla.destino for tabla in CATALOGO_ACCESS}
    resultados = extraer_access(config_fuente, solo=destinos_access, registrar=registrar)
    snapshot_dirs = {resultado.ruta_csv.parent for resultado in resultados}
    if len(snapshot_dirs) != 1:
        raise RuntimeError(
            "La extracción Access no dejó exactamente un directorio de snapshot completo."
        )
    directorio_snapshot = next(iter(snapshot_dirs))
    config_carga = replace(config_fuente, dir_extraccion=directorio_snapshot)
    resultados_carga = cargar_raw(config_carga, solo=destinos_access, registrar=registrar)
    if resultados_carga:
        if not resumen_carga(
            resultados_carga,
            registrar=registrar,
            strict_baseline=strict_baseline,
        ):
            raise RuntimeError(
                "La carga raw quedó con desviaciones frente al baseline y se solicitó "
                "--strict-baseline. No se continúa a validación/promoción."
            )
    else:
        registrar("Snapshot Access ya cargado; no se insertaron filas duplicadas.")

    manifest_path = directorio_snapshot / MANIFIESTO_ACCESS
    if not manifest_path.is_file():
        raise RuntimeError(f"No existe el manifiesto del snapshot: {manifest_path}")
    manifiesto = json.loads(manifest_path.read_text(encoding="utf-8"))
    sha256 = str(manifiesto.get("sha256") or "").strip()
    if len(sha256) != 64:
        raise RuntimeError("El manifiesto Access no contiene una huella SHA-256 válida.")

    import psycopg

    with psycopg.connect(config_carga.dsn) as conexion, conexion.cursor() as cur:
        cur.execute(
            """
            SELECT source_snapshot_id
            FROM raw.source_snapshot
            WHERE tipo = 'access' AND campania = %s AND btrim(sha256) = %s
            ORDER BY source_snapshot_id DESC
            LIMIT 1
            """,
            (campania, sha256),
        )
        fila = cur.fetchone()
    if not fila:
        raise RuntimeError(f"La carga no registró el snapshot Access con SHA {sha256}.")
    return int(fila[0])


def ejecutar_refresco(
    config: Config,
    *,
    snapshot_id: int | None = None,
    campania: str | None = None,
    access_path: str | Path | None = None,
    source_version: str | None = None,
    output: str | Path | None = None,
    strict_baseline: bool = False,
    promover: bool = False,
    ejecutar_core: bool = False,
    permitir_reconstruccion_core: bool = False,
    usuario: str = "etl",
    motivo: str | None = None,
    registrar=print,
) -> PlanRefresco:
    """Ejecuta el tramo seguro del refresco y, opcionalmente, core protegido.

    ``promover`` no se hace automáticamente para cambios core. Para ejecutar una nueva
    versión completa se debe solicitar explícitamente ``promover=True``, ``ejecutar_core=True``
    y, cuando el core actual ya tiene datos, ``permitir_reconstruccion_core=True``.
    """
    from aquanqa_etl.snapshots import promover_snapshot, rollback_snapshot, validar_snapshot

    _exigir_base_objetivo(config)
    if snapshot_id is not None and access_path is not None:
        raise ValueError("Usa --snapshot-id o --access-path, no ambos.")
    campania_real = (campania or config.access_campania or DEFAULT_CAMPANIA).upper()

    if access_path is not None or snapshot_id is None:
        snapshot_id = _resolver_snapshot_cargado(
            config,
            campania=campania_real,
            access_path=access_path,
            source_version=source_version,
            output=output,
            strict_baseline=strict_baseline,
            registrar=registrar,
        )
    elif source_version or output:
        raise ValueError("--source-version/--output solo aplican cuando se extrae Access.")

    problemas = validar_snapshot(
        config,
        snapshot_id=snapshot_id,
        tipo="access",
        campania=campania_real,
    )
    if problemas:
        raise RuntimeError(
            "El snapshot no superó la validación; no se publica ni se ejecuta core:\n  "
            + "\n  ".join(problemas)
        )
    plan = construir_plan(config, snapshot_id=snapshot_id, campania=campania_real)
    registrar(formatear_plan(plan))

    if plan.estado == "sin_cambios":
        if promover or ejecutar_core:
            registrar("No-op: el snapshot ya está vigente; no se repite ningún bloque.")
        return plan
    if plan.estado == "bloqueado_incompleto":
        raise RuntimeError("El plan está incompleto; corrige los controles antes de continuar.")

    if plan.requiere_core:
        if not ejecutar_core:
            raise RuntimeError(
                "El snapshot quedó cargado y validado en raw, pero no se publica porque "
                "el cambio afecta core. Ejecuta con --promote --execute-core y, si el core "
                "ya está poblado, --allow-full-core-rebuild."
            )
        if not promover:
            raise RuntimeError(
                "--execute-core requiere --promote: la publicación y la reconstrucción deben "
                "formar una operación controlada."
            )
        if plan.requiere_reconstruccion_completa and not permitir_reconstruccion_core:
            raise RuntimeError(
                "El core actual está poblado y solo admite reconstrucción completa con los "
                "scripts vigentes. Añade --allow-full-core-rebuild después de revisar el plan."
            )
        _crear_guardas(config)
        anterior_id = plan.snapshot_anterior_id
        promover_snapshot(
            config,
            snapshot_id=plan.snapshot_objetivo_id,
            tipo="access",
            campania=campania_real,
            autorizado_por=usuario,
            motivo=motivo or "Refresco Access orquestado con reconstrucción core protegida.",
        )
        try:
            _ejecutar_psql(config, [_ruta_script(PREFLIGHT_SCRIPT)], transaccion_unica=False)
            auditoria_final = _ejecutar_core(plan, config)
            if not auditoria_final:
                _verificar_bloques_publicados(plan, config)
        except Exception as exc:
            if anterior_id is None:
                raise RuntimeError(
                    "Falló la construcción inicial de core y no existe snapshot anterior para "
                    f"rollback: {exc}"
                ) from exc
            try:
                rollback_snapshot(
                    config,
                    snapshot_id=anterior_id,
                    tipo="access",
                    campania=campania_real,
                    autorizado_por=usuario,
                    motivo=f"Rollback automático del refresco {plan.snapshot_objetivo_id}: {exc}",
                )
            except Exception as rollback_exc:
                raise RuntimeError(
                    "Falló el core y también falló el rollback automático. "
                    f"Error core: {exc}. Error rollback: {rollback_exc}."
                ) from exc
            raise RuntimeError(
                "Falló la reconstrucción core; la transacción se revirtió y el snapshot anterior "
                f"({anterior_id}) volvió a estar vigente: {exc}"
            ) from exc
        registrar(
            "OK: snapshot publicado y core actualizado. "
            + (
                "Auditoría final cerrada. "
                if set(BLOCK_SCRIPTS).issubset(plan.bloques_ejecucion)
                else "Check-to-check parcial cerrado para los bloques seleccionados. "
            )
            + f"Bloques: {', '.join(plan.bloques_ejecucion)}"
        )
        return plan

    # Un cambio exclusivamente raw_only no necesita tocar core. Se puede publicar sin alterar
    # los hechos ni los maestros previamente auditados.
    if promover:
        promover_snapshot(
            config,
            snapshot_id=plan.snapshot_objetivo_id,
            tipo="access",
            campania=campania_real,
            autorizado_por=usuario,
            motivo=motivo or "Refresco Access raw_only orquestado.",
        )
        registrar("OK: snapshot raw_only publicado; core no fue modificado.")
    else:
        registrar("Snapshot raw_only validado; queda sin publicar hasta recibir --promote.")
    return plan


__all__ = [
    "BLOCK_SCRIPTS",
    "CambioTabla",
    "ContratoBloque",
    "ContratoTabla",
    "DeltaTabla",
    "PlanRefresco",
    "calcular_plan",
    "construir_plan",
    "ejecutar_refresco",
    "formatear_plan",
    "plan_a_dict",
]
