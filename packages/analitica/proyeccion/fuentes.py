"""Lectura versionada de las fuentes analíticas.

PostgreSQL es la fuente contractual. El modo ``auto`` permite trabajar sin servidor, pero
el fallback a Excel queda siempre marcado en :class:`FuenteInfo`; nunca es silencioso.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from analitica import settings

from ..servicios.infraestructura.postgres import conexion_postgres
from .contratos import DatosProyeccion, FuenteInfo

SQL = {
    "forecast_campania": """
        SELECT version, empresa_norm, fundo_norm, modulo, turno, campania,
               anio, semana, kg_exp, kg_des, kg_con, frutos_exp,
               c12, c14, c16, c18, c19, c20, c22, c24, c26
        FROM stg.v_r08_forecast
    """,
    "forecast": """
        SELECT r.lote_id, r.motivo, r.version, r.campania, r.pasada,
               r.area_ha::double precision AS area_ha, r.fecha_cos_ant,
               r.fecha_cos, r.semana,
               r.frutos_por_planta, r.peso_baya, r.frutos_total,
               r.rendimiento, r.kg, r.dr,
               d.empresa, d.fundo, d.modulo, d.lote, d.variedad,
               d.n_plantas::double precision AS plantas_maestro
        FROM stg.v_r09_forecast r
        LEFT JOIN dim.lote d USING (lote_id)
        WHERE r.lote_id IS NOT NULL AND r.fecha_cos IS NOT NULL
    """,
    "cosecha": """
        SELECT h.lote_id, h.motivo, h.campania, h.fecha, h.turno,
               h.n_plantas::double precision AS plantas_cosechadas,
               h.semana, h.kg, h.pana, h.peso_baya,
               d.empresa, d.fundo, d.modulo, d.lote, d.variedad,
               d.area_ha::double precision AS area_ha,
               d.n_plantas::double precision AS plantas_maestro
        FROM stg.v_h01_cosecha h
        LEFT JOIN dim.lote d USING (lote_id)
        WHERE h.lote_id IS NOT NULL AND h.fecha IS NOT NULL
    """,
    "flores": """
        SELECT e.lote_id, e.fecha, e.cortina, e.hilera, e.planta,
               e.n_flores, e.cuajo, e.yemas_abiertas, e.yemas_por_abrir,
               d.empresa, d.fundo, d.modulo, d.lote
        FROM stg.v_e02_flores e LEFT JOIN dim.lote d USING (lote_id)
        WHERE e.lote_id IS NOT NULL AND e.fecha IS NOT NULL
    """,
    "estados": """
        SELECT e.lote_id, e.fecha, e.cortina, e.hilera, e.planta,
               e.e1, e.e2, e.e3, e.e4, e.e5,
               d.empresa, d.fundo, d.modulo, d.lote
        FROM stg.v_e03_estados e LEFT JOIN dim.lote d USING (lote_id)
        WHERE e.lote_id IS NOT NULL AND e.fecha IS NOT NULL
    """,
    "bayas": """
        SELECT e.lote_id, e.fecha, e.cortina, e.hilera, e.diametro, e.nro_muestra,
               d.empresa, d.fundo, d.modulo, d.lote
        FROM stg.v_e05_bayas e LEFT JOIN dim.lote d USING (lote_id)
        WHERE e.lote_id IS NOT NULL AND e.fecha IS NOT NULL
    """,
    # Brotes y ramas se levantan en campo desde el inicio y hasta ahora no entraban a
    # ningún análisis. Son las dos primeras señales del ciclo, anteriores a la floración:
    # sin ellas la cadena poda → brote → yema → flor → cuajado → fruto empieza por la mitad.
    "brotes": """
        SELECT e.lote_id, e.fecha, e.piso, e.cortina, e.hilera, e.planta,
               e.brotes, e.des1, e.des2, e.des3,
               d.empresa, d.fundo, d.modulo, d.lote
        FROM stg.v_e04_brotes e LEFT JOIN dim.lote d USING (lote_id)
        WHERE e.lote_id IS NOT NULL AND e.fecha IS NOT NULL
    """,
    "ramas": """
        SELECT e.lote_id, e.fecha, e.cortina, e.hilera, e.planta,
               e.ramas_menor5, e.ramas_mayor5, e.nro_rama, e.diametro,
               d.empresa, d.fundo, d.modulo, d.lote
        FROM stg.v_e01_ramas e LEFT JOIN dim.lote d USING (lote_id)
        WHERE e.lote_id IS NOT NULL AND e.fecha IS NOT NULL
    """,
    # Packing: la medición más precisa del tamaño de fruto que existe en la operación.
    # Frente al censo de bayas de campo —2 fechas y 36 lotes— acá hay tres campañas de
    # calibre medido en línea, con acidez y defectos.
    #
    # Dos límites que condicionan su uso y que hay que tener presentes: el grano es
    # **módulo**, no lote, y cubre 15 de los 26 módulos. Por eso alimenta un bloque propio
    # de análisis en vez de mezclarse con el panel de lote.
    "packing": """
        SELECT p.modulo, p.fecha_cosecha, p.semana, p.anio, p.variedad,
               p.calibre, p.calibre_mm, p.clase, p.mercado, p.defecto, p.acidez,
               p.peso_kg, p.recuento
        FROM stg.v_h02_packing p
        WHERE p.fecha_cosecha IS NOT NULL AND p.modulo IS NOT NULL
    """,
    "poda": """
        SELECT p.lote_id, p.campania, p.fecha_inicio, p.fecha_siembra,
               p.area_ha::double precision AS area_ha, p.variedad,
               d.empresa, d.fundo, d.modulo, d.lote
        FROM stg.v_m_poda p LEFT JOIN dim.lote d USING (lote_id)
        WHERE p.lote_id IS NOT NULL AND p.fecha_inicio IS NOT NULL
    """,
    "clima": """
        SELECT fecha_hora, temp, temp_alta, temp_baja, humedad, punto_rocio,
               vel_viento, lluvia, rad_sol, ener_solar, et_mm,
               dg_calentamiento, dg_enfriamiento
        FROM stg.v_h05_clima WHERE fecha_hora IS NOT NULL
    """,
    "riego": """
        SELECT r.fecha, r.modulo_id, r.turno_local, r.area_ha, r.agua_m3,
               r.lamina_mm, r.reposicion_pct, r.estimado,
               d.empresa, d.fundo, d.modulo
        FROM stg.v_riego_diario r LEFT JOIN dim.modulo d USING (modulo_id)
        WHERE r.fecha IS NOT NULL
    """,
    "lotes": """
        SELECT lote_id, empresa, fundo, modulo, lote, variedad,
               area_ha::double precision AS area_ha,
               n_plantas::double precision AS n_plantas, fecha_siembra,
               clave_negocio
        FROM dim.lote WHERE NOT es_sentinel AND NOT es_ficticio
    """,
}


@contextmanager
def _conexion(dsn: str):
    """Fachada privada histórica hacia el adaptador PostgreSQL compartido."""
    with conexion_postgres(dsn) as conexion:
        yield conexion


def _leer_sql(conexion, consulta: str) -> pd.DataFrame:
    # pandas aún advierte con conexiones DBAPI no-SQLAlchemy, pero psycopg implementa el
    # contrato necesario y evita una dependencia adicional solo para siete lecturas.
    with conexion.cursor() as cursor:
        cursor.execute(consulta)
        columnas = [descripcion.name for descripcion in cursor.description]
        return pd.DataFrame(cursor.fetchall(), columns=columnas)


def _source_snapshot_access(conexion) -> tuple[int | None, tuple[str, ...]]:
    """Obtiene el único snapshot Access que puede representar la foto cargada.

    Si hay varias campañas o la base todavía no conoce el control de snapshots, no se
    inventa una correspondencia: la corrida queda trazable por su firma, pero el vínculo
    físico se declara no verificable para la UI.
    """
    try:
        tabla = _leer_sql(
            conexion,
            """
            SELECT source_snapshot_id
            FROM raw.v_ultimo_snapshot_fuente
            WHERE tipo = 'access'
            ORDER BY extraido_en DESC, source_snapshot_id DESC
            """,
        )
    except Exception as exc:
        return None, (
            "No se pudo vincular la corrida con el snapshot Access "
            f"({type(exc).__name__}); el estado físico queda no verificable.",
        )
    if len(tabla) != 1:
        return None, (
            "El origen tiene cero o varios snapshots Access; no se puede atribuir la corrida "
            "a uno solo.",
        )
    try:
        return int(tabla.iloc[0].source_snapshot_id), ()
    except (TypeError, ValueError):
        return None, ("El identificador del snapshot Access no es válido; queda no verificable.",)


def _huella_tabla(datos: pd.DataFrame) -> str:
    """Hash determinista del multiconjunto de filas, independiente del orden de lectura."""
    if datos.empty:
        return hashlib.sha256(b"").hexdigest()
    columnas = sorted(datos.columns)
    hashes = pd.util.hash_pandas_object(datos[columnas], index=False).to_numpy(np.uint64)
    hashes.sort()
    digest = hashlib.sha256()
    digest.update("\x1f".join(columnas).encode())
    digest.update("\x1f".join(str(datos[c].dtype) for c in columnas).encode())
    digest.update(hashes.tobytes())
    return digest.hexdigest()


def _firma(nombre: str, tablas: dict[str, pd.DataFrame], corte: datetime | None) -> str:
    resumen: dict[str, object] = {"fuente": nombre, "corte": corte.isoformat() if corte else None}
    for tabla, datos in sorted(tablas.items()):
        resumen[tabla] = {
            "filas": int(len(datos)),
            "columnas": list(datos.columns),
            "sha256_contenido": _huella_tabla(datos),
        }
    serializado = json.dumps(resumen, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(serializado).hexdigest()


# Columna de fecha de cada tabla. Fija el corte de datos y permite aplicar un as-of.
COLUMNA_FECHA = {
    "forecast": "fecha_cos",
    "cosecha": "fecha",
    "flores": "fecha",
    "estados": "fecha",
    "bayas": "fecha",
    "brotes": "fecha",
    "ramas": "fecha",
    "packing": "fecha_cosecha",
    "clima": "fecha_hora",
    "riego": "fecha",
}


def _aplicar_asof(tablas: dict[str, pd.DataFrame], corte) -> dict[str, pd.DataFrame]:
    """Deja fuera todo lo posterior al corte, tabla por tabla.

    Sin esto, «corte de datos» era solo la fecha máxima encontrada: describía hasta dónde
    llegaban los datos, no hasta dónde se había decidido mirar. Con un corte explícito, dos
    corridas de fechas distintas sobre la misma base dejan de ser comparables por accidente.
    """
    if corte is None:
        return tablas
    limite = pd.Timestamp(corte)
    salida = {}
    for nombre, tabla in tablas.items():
        columna = COLUMNA_FECHA.get(nombre)
        if not columna or tabla.empty or columna not in tabla:
            salida[nombre] = tabla
            continue
        fechas = pd.to_datetime(tabla[columna], errors="coerce")
        ref = limite.tz_localize(None) if fechas.dt.tz is None else limite
        if fechas.dt.tz is not None and ref.tz is None:
            ref = ref.tz_localize(fechas.dt.tz)
        salida[nombre] = tabla[fechas.isna() | (fechas <= ref)].reset_index(drop=True)
    return salida


def cargar_postgres(dsn: str | None = None, corte_asof=None) -> DatosProyeccion:
    """Lee las tablas del contrato, opcionalmente recortadas a una fecha.

    `corte_asof` responde «¿qué se sabía el día X?». Sin él se toma todo lo que haya, que
    es lo correcto para un análisis retrospectivo pero puede incluir fechas posteriores a
    la ejecución si la base trae datos cargados por adelantado. Ese caso se detecta y se
    declara en las advertencias, en vez de pasar inadvertido.
    """
    dsn = dsn or settings.postgres_dsn()
    if not dsn:
        raise RuntimeError("No existe ANALYTICS_DATABASE_URL ni configuración PG utilizable.")
    with _conexion(dsn) as conexion:
        tablas = {nombre: _leer_sql(conexion, consulta) for nombre, consulta in SQL.items()}
        source_snapshot_id, advertencias_snapshot = _source_snapshot_access(conexion)

    corte_asof = pd.Timestamp(corte_asof) if corte_asof is not None else None
    tablas = _aplicar_asof(tablas, corte_asof)

    fechas = []
    for nombre, columna in COLUMNA_FECHA.items():
        if nombre in tablas and columna in tablas[nombre] and not tablas[nombre].empty:
            fechas.append(pd.to_datetime(tablas[nombre][columna], errors="coerce").max())
    corte_pd = max((f for f in fechas if pd.notna(f)), default=None)
    corte = corte_pd.to_pydatetime().replace(tzinfo=UTC) if corte_pd is not None else None

    advertencias: tuple[str, ...] = advertencias_snapshot
    if corte_asof is not None:
        advertencias += (f"Corte as-of aplicado: solo datos hasta {corte_asof:%d/%m/%Y}.",)
    elif corte is not None:
        ahora = datetime.now(UTC)
        if corte > ahora:
            dias = (corte - ahora).days
            advertencias += (
                f"Los datos llegan hasta el {corte:%d/%m/%Y}, {dias} días por delante de "
                "esta ejecución. El análisis es retrospectivo sobre un histórico completo, "
                "no una foto de lo que se sabía hoy.",
            )
    info = FuenteInfo(
        nombre="postgres",
        firma=_firma("postgres", tablas, corte),
        corte=corte,
        advertencias=advertencias,
        conteos={nombre: len(tabla) for nombre, tabla in tablas.items()},
        source_snapshot_id=source_snapshot_id,
    )
    return DatosProyeccion(fuente=info, **tablas)


def _hoja_por_nombre(libro: pd.ExcelFile, candidatos: tuple[str, ...]) -> str | None:
    normalizadas = {str(nombre).casefold().replace(" ", ""): nombre for nombre in libro.sheet_names}
    for candidato in candidatos:
        encontrado = normalizadas.get(candidato.casefold().replace(" ", ""))
        if encontrado:
            return encontrado
    return None


def cargar_excel(ruta: Path | None = None) -> DatosProyeccion:
    """Fallback local explícito.

    El libro histórico no contiene las versiones R09; por eso habilita relaciones y
    revisión de cosecha, pero bloquea un backtest oficial y lo deja indicado en la fuente.
    """
    ruta = Path(ruta or settings.XLSX_REPO)
    if not ruta.is_file():
        raise FileNotFoundError(ruta)
    libro = pd.ExcelFile(ruta)
    hoja = _hoja_por_nombre(libro, ("Kg Reales", "HistoricosVolumen"))
    cosecha = pd.read_excel(libro, sheet_name=hoja) if hoja else pd.DataFrame()
    tablas = {
        "forecast": pd.DataFrame(),
        "forecast_campania": pd.DataFrame(),
        "cosecha": cosecha,
        "flores": pd.DataFrame(),
        "estados": pd.DataFrame(),
        "bayas": pd.DataFrame(),
        "brotes": pd.DataFrame(),
        "ramas": pd.DataFrame(),
        "packing": pd.DataFrame(),
        "poda": pd.DataFrame(),
        "clima": pd.DataFrame(),
        "riego": pd.DataFrame(),
        "lotes": pd.DataFrame(),
    }
    corte_archivo = datetime.fromtimestamp(ruta.stat().st_mtime, tz=UTC)
    advertencias = (
        "FALLBACK_EXCEL_ACTIVO: PostgreSQL no estuvo disponible o se solicitó Excel.",
        "El Excel no conserva el historial versionado R09; no puede publicar backtesting oficial.",
    )
    info = FuenteInfo(
        nombre="excel",
        firma=_firma("excel", tablas, corte_archivo),
        corte=corte_archivo,
        fallback=True,
        advertencias=advertencias,
        conteos={nombre: len(tabla) for nombre, tabla in tablas.items()},
    )
    return DatosProyeccion(fuente=info, **tablas)


def cargar_datos(origen: str | None = None, corte_asof=None) -> DatosProyeccion:
    origen = (origen or settings.ANALYTICS_SOURCE).lower()
    if origen == "postgres":
        return cargar_postgres(corte_asof=corte_asof)
    if origen == "excel":
        return cargar_excel()
    if origen != "auto":
        raise ValueError("AQUANQA_ANALYTICS_SOURCE debe ser postgres, excel o auto.")
    try:
        return cargar_postgres(corte_asof=corte_asof)
    except Exception as exc:
        datos = cargar_excel()
        aviso = f"PostgreSQL falló ({type(exc).__name__}); se activó fallback visible."
        datos.fuente = FuenteInfo(
            **{**datos.fuente.__dict__, "advertencias": (aviso, *datos.fuente.advertencias)}
        )
        return datos
