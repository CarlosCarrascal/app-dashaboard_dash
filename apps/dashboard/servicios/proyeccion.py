"""Lectura PostgreSQL mínima para la mesa de Proyección.

La página operativa no debe esperar a que se carguen relaciones, SHAP ni artefactos de
otros módulos. Este servicio trae únicamente la corrida vigente, cosecha real, referencia
R09 y replay histórico. Ningún callback abre Excel ni ejecuta el motor.
"""

from __future__ import annotations

import re
import time
from functools import lru_cache

import pandas as pd

from analitica import settings

from .consultas import consulta as _consulta
from .consultas import consulta_si_existe as _consulta_si_existe
from .reporting import (
    cosecha_real_operativa,
    hibrido_v2,
    lotes,
    r09_referencia,
)

TTL_CACHE_SEGUNDOS = 300

# Regla única para operación y replay: solo ``Sxx`` base es una emisión oficial.
# Sufijos como ``_v2``, ``_v3``, ``EDI`` u ``oli`` quedan fuera hasta que una
# promoción explícita los convierta en una release aprobada. De este modo analytics
# y stg no aplican criterios distintos a la misma referencia.
R09_PATRON_VERSION_CANONICA_SQL = r"^[Ss]0*([0-9]+)$"
R09_REGLA_VARIANTES = "Solo versiones base Sxx; variantes y copias requieren promoción explícita."
RELACION_RELEASE = "analytics.model_series_release"
RELACION_CONTRATO = "analytics.evaluation_contract"


def _relacion_existe(conexion, relacion: str) -> bool:
    with conexion.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", (relacion,))
        return cursor.fetchone()[0] is not None


def _certificacion_disponible(conexion) -> bool:
    return _relacion_existe(conexion, RELACION_RELEASE) and _relacion_existe(
        conexion, RELACION_CONTRATO
    )


def es_version_r09_canonica(version: object) -> bool:
    """Replica en Python la regla aplicada por las consultas PostgreSQL de R09."""

    return bool(re.fullmatch(R09_PATRON_VERSION_CANONICA_SQL, str(version or "")))


def _validar_un_contrato_por_campania(releases: pd.DataFrame) -> None:
    """Impide combinar denominadores certificados distintos en una misma campaña."""

    if releases.empty:
        return
    requeridas = {"campania", "evaluation_contract_id"}
    if not requeridas.issubset(releases.columns):
        raise ValueError("Las releases no informan su contrato de evaluación")
    contratos = (
        releases.dropna(subset=["evaluation_contract_id"])
        .groupby("campania", dropna=False)["evaluation_contract_id"]
        .nunique()
    )
    mezcladas = contratos[contratos.ne(1)]
    if not mezcladas.empty:
        detalle = ", ".join(f"{campania}: {int(n)}" for campania, n in mezcladas.items())
        raise ValueError(f"Releases con contratos incompatibles ({detalle})")


def _vacio() -> dict[str, object]:
    return {
        "error": None,
        "runs": pd.DataFrame(),
        "proyeccion": pd.DataFrame(),
        "proyeccion_experimental": pd.DataFrame(),
        "hibrido_v2": pd.DataFrame(),
        "cosecha_real": pd.DataFrame(),
        "lotes": pd.DataFrame(),
        "replay": pd.DataFrame(),
        "replay_detalle": pd.DataFrame(),
        "nowcast_cierre": pd.DataFrame(),
    }


@lru_cache(maxsize=2)
def _cache_proyeccion(minuto: int) -> dict[str, object]:
    del minuto
    resultado = _vacio()
    dsn = settings.postgres_dsn()
    if not dsn:
        resultado["error"] = "PostgreSQL no está configurado."
        return resultado
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=3) as conexion:
            resultado["runs"] = _consulta(
                conexion,
                """
                SELECT r.run_id, r.tipo, r.estado, r.inicio, r.fin, r.codigo_commit,
                       r.mlflow_run_id, s.snapshot_id, s.fuente,
                       s.firma AS firma_snapshot, s.corte_datos
                FROM analytics.forecast_run r
                JOIN analytics.dataset_snapshot s USING (snapshot_id)
                WHERE r.estado IN ('succeeded', 'published')
                ORDER BY r.run_id DESC LIMIT 10
                """,
            )
            resultado["proyeccion_experimental"] = _consulta_si_existe(
                conexion,
                "reporting.proyeccion_operativa_detalle",
                """
                SELECT run_id, modelo, version_fuente, campania, empresa, fundo, modulo,
                       lote, fundo_fuente, lote_id, fecha_emision, fecha_objetivo,
                       horizonte_semanas, banda_horizonte, p10_kg, p50_kg, p90_kg,
                       real_kg, plantas, frutos_por_planta, peso_baya_g, componentes,
                       confianza, snapshot_id, generado_en, configuracion,
                       turno, variedad, area_ha, n_plantas
                FROM reporting.proyeccion_operativa_detalle
                ORDER BY fecha_objetivo, fundo, modulo, lote_id
                """,
            )
            # El híbrido v2 se muestra como comparación del plan, usando su corrida
            # normal completa. No se crea una corrida especial por horizonte: el horizonte
            # se recorta en la vista con la misma regla de seis semanas que la Macro.
            resultado["hibrido_v2"] = hibrido_v2(conexion)
            # R09 es una referencia publicada, no un modelo. La curva operativa usa
            # la última emisión oficial disponible para cada semana objetivo: S34
            # para la semana 34, S35 para las semanas 35-40, etc. Así no se borra una
            # emisión histórica al cargar la siguiente. El replay ciego continúa
            # usando analytics.prediction y sus reglas temporales estrictas.
            resultado["proyeccion"] = r09_referencia(conexion)
            resultado["cosecha_real"] = cosecha_real_operativa(conexion)
            resultado["lotes"] = lotes(conexion)
            resultado["nowcast_cierre"] = _consulta_si_existe(
                conexion,
                "reporting.nowcast_cierre_semanal",
                """
                SELECT run_id, modelo, version_modelo, campania,
                       semana_inicio, semana_cierre, fecha_corte, fecha_emision,
                       fundo, kg_lun_mar, p50_kg, real_kg, macro_kg,
                       r09_presemana_kg, r09_misma_semana_kg,
                       estado_evaluacion, componentes, uso, release_id,
                       evaluation_contract_id, generado_en, ape, sesgo_pct
                FROM reporting.nowcast_cierre_semanal
                ORDER BY semana_inicio, fundo
                """,
            )
    except Exception as exc:
        resultado["error"] = f"Proyección no disponible: {type(exc).__name__}: {exc}"
    return resultado


def estado_proyeccion() -> dict[str, object]:
    """Snapshot operativo compartido durante cinco minutos.

    La corrida cambia al persistir una nueva emisión, no con cada interacción del
    agrónomo. Un TTL de cinco minutos evita releer PostgreSQL al seleccionar varios
    fundos seguidos sin convertir el caché en una fuente de datos permanente.
    """
    return _cache_proyeccion(int(time.time() // TTL_CACHE_SEGUNDOS))


@lru_cache(maxsize=2)
def _cache_replay(minuto: int) -> dict[str, object]:
    del minuto
    resultado = {
        "error": None,
        "replay": pd.DataFrame(),
        "replay_detalle": pd.DataFrame(),
        "real_detalle": pd.DataFrame(),
        "certificacion": {
            "estado": "no_certificado",
            "detalle": "No se encontró una release histórica aprobada con contrato de evaluación.",
            "regla_r09": R09_REGLA_VARIANTES,
        },
    }
    dsn = settings.postgres_dsn()
    if not dsn:
        resultado["error"] = "PostgreSQL no está configurado."
        return resultado
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=3) as conexion:
            if not _certificacion_disponible(conexion):
                resultado["error"] = (
                    "Replay no certificado: la base no expone releases aprobadas "
                    "y contratos de evaluación. No se usó la última corrida como reemplazo."
                )
                return resultado

            releases = _consulta(
                conexion,
                """
                SELECT r.campania, r.modelo, r.version_modelo, r.run_id,
                       r.evaluation_contract_id, r.uso, r.source_hash
                FROM analytics.model_series_release r
                JOIN analytics.evaluation_contract c
                  ON c.evaluation_contract_id = r.evaluation_contract_id
                WHERE r.estado = 'approved' AND r.activo
                  AND r.uso IN ('historico', 'referencia')
                  AND c.estado = 'approved'
                  -- El cierre del miércoles tiene otro contrato temporal y se
                  -- presenta en su propia pestaña; no debe contaminar el replay
                  -- comparable de plan semanal.
                  AND r.modelo <> 'NowcastCierreSemanal_v1'
                ORDER BY r.campania, r.modelo
                """,
            )
            if releases.empty:
                resultado["error"] = (
                    "Replay no certificado: no existe ninguna release histórica aprobada."
                )
                return resultado

            _validar_un_contrato_por_campania(releases)

            resultado["certificacion"] = {
                "estado": "certificado",
                "releases": releases.to_dict("records"),
                "regla_r09": R09_REGLA_VARIANTES,
            }

            # Predicciones analíticas: una release fija el run de cada modelo. La
            # emisión se elige a nivel modelo-campaña-semana y luego se conservan
            # todos los lotes de ese vintage; nunca se elige el horizonte por lote.
            modelos_detalle = _consulta_si_existe(
                conexion,
                "analytics.prediction",
                """
                WITH releases AS (
                    SELECT r.campania, r.modelo, r.version_modelo, r.run_id,
                           r.evaluation_contract_id, c.semanas_cerradas
                    FROM analytics.model_series_release r
                    JOIN analytics.evaluation_contract c
                      ON c.evaluation_contract_id = r.evaluation_contract_id
                    WHERE r.estado = 'approved' AND r.activo
                      AND r.uso IN ('historico', 'referencia')
                      AND c.estado = 'approved'
                      AND r.modelo <> 'NowcastCierreSemanal_v1'
                )
                SELECT p.run_id, p.modelo, p.version_modelo, p.version_fuente,
                       p.campania, p.empresa, p.fundo, p.modulo, p.lote, p.lote_id,
                       p.fecha_emision,
                       date_trunc('week', p.fecha_objetivo)::date AS fecha_objetivo,
                       p.horizonte_semanas, p.banda_horizonte, p.p50_kg,
                       COALESCE(p.origen_emision, p.fecha_emision) AS origen_emision,
                       COALESCE((p.componentes->>'emitio_prediccion')::boolean, true)
                           AS emitio_prediccion,
                       r.evaluation_contract_id, p.real_kg
                FROM analytics.prediction p
                JOIN releases r
                  ON r.run_id = p.run_id
                 AND r.modelo = p.modelo
                 AND r.campania = p.campania
                 AND r.version_modelo = COALESCE(p.version_modelo, 'sin_version')
                WHERE p.lote_id IS NOT NULL
                  AND p.real_kg IS NOT NULL
                  AND COALESCE(p.origen_emision, p.fecha_emision)
                      < date_trunc('week', p.fecha_objetivo)::date
                  AND p.horizonte_semanas >= 1
                  AND r.semanas_cerradas
                      ? to_char(
                          date_trunc('week', p.fecha_objetivo)::date,
                          'YYYY-MM-DD'
                        )
                ORDER BY p.campania, p.modelo, p.fecha_objetivo, p.lote_id
                """,
            )

            # R09 histórico se consume desde la serie congelada de la release.
            # Volver a reconstruirlo desde Access en cada carga sería lento y abriría
            # una segunda interpretación de la misma referencia publicada.
            resultado["replay_detalle"] = modelos_detalle

            # El real del replay pertenece al contrato certificado, no al último
            # contenido mutable de H01. Todos los modelos activos comparten keyset y
            # denominador; tomar una sola copia evita ampliar accidentalmente C2025 o
            # incluir la semana parcial 17–23/08 de C2026.
            if not modelos_detalle.empty:
                columnas_real = [
                    "evaluation_contract_id",
                    "campania",
                    "fecha_objetivo",
                    "lote_id",
                    "empresa",
                    "fundo",
                    "modulo",
                    "lote",
                    "real_kg",
                ]
                resultado["real_detalle"] = (
                    modelos_detalle[columnas_real]
                    .drop_duplicates(
                        [
                            "evaluation_contract_id",
                            "campania",
                            "fecha_objetivo",
                            "lote_id",
                        ]
                    )
                    .reset_index(drop=True)
                )

            if not resultado["replay_detalle"].empty:
                detalle = resultado["replay_detalle"].copy()
                detalle["fecha_objetivo"] = pd.to_datetime(
                    detalle["fecha_objetivo"], errors="coerce"
                )
                resultado["replay"] = (
                    detalle.groupby(
                        [
                            "run_id",
                            "modelo",
                            "fecha_emision",
                            "fecha_objetivo",
                            "horizonte_semanas",
                            "banda_horizonte",
                        ],
                        as_index=False,
                        dropna=False,
                    )
                    .agg(
                        # La release certificada ya garantiza una sola versión por
                        # semana objetivo. ``first`` evita comparar objetos JSON/dict
                        # cuando una fuente conserva metadatos estructurados.
                        version_fuente=("version_fuente", "first"),
                        p50_kg=("p50_kg", "sum"),
                        real_kg=("real_kg", "sum"),
                        n_lotes=("lote_id", "nunique"),
                    )
                    .sort_values(["fecha_emision", "fecha_objetivo", "modelo"])
                )
    except Exception as exc:
        resultado["error"] = f"Replay no disponible: {type(exc).__name__}: {exc}"
    return resultado


def estado_replay_proyeccion() -> dict[str, object]:
    """Replay histórico cargado solo al abrir su pestaña."""
    return _cache_replay(int(time.time() // TTL_CACHE_SEGUNDOS))


def limpiar_cache_proyeccion() -> None:
    _cache_proyeccion.cache_clear()
    _cache_replay.cache_clear()
