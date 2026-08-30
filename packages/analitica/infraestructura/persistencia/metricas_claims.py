"""Persistencia de métricas, claims, evidencia de features y clima."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analitica.dominio.compartido import limpiar_valor as _limpio
from analitica.dominio.compartido import serializar_json as _json
from analitica.dominio.compartido import serializar_jsonb as _jsonb


class ClaimHistoryConflictError(RuntimeError):
    """Indica que una corrida intenta cambiar un claim histórico ya registrado."""


class MetricasClaimsMixin:
    """Operaciones de métricas y evidencia científica asociada."""

    def guardar_metricas(self, run_id: int, tabla: pd.DataFrame):
        dimensiones = ["campania", "fundo", "horizonte_semanas"]
        ids = ["modelo", "banda_horizonte", "n", *dimensiones]
        # `analytics.metric.valor` es `double precision`: solo las columnas numéricas son
        # métricas. Las descriptivas —de qué base de plantas se evaluó, qué familia ganó—
        # viajan como contexto en `atributos`, porque describen la métrica en vez de serlo.
        candidatas = [c for c in tabla if c not in {*ids, "volumen_real_kg"}]
        numericas = [c for c in candidatas if pd.api.types.is_numeric_dtype(tabla[c])]
        descriptivas = [c for c in candidatas if c not in numericas]
        filas = []
        for fila in tabla.itertuples(index=False):
            serie = pd.Series(fila._asdict())
            contexto = {"volumen_real_kg": _limpio(serie.get("volumen_real_kg"))}
            contexto.update({c: _limpio(serie.get(c)) for c in descriptivas})
            for metrica in numericas:
                filas.append(
                    (
                        run_id,
                        serie.modelo,
                        metrica,
                        _limpio(serie[metrica]),
                        int(serie.n),
                        _limpio(serie.get("campania")),
                        _limpio(serie.get("fundo")),
                        _limpio(serie.get("horizonte_semanas")),
                        _limpio(serie.get("banda_horizonte")),
                        _json(contexto),
                    )
                )
        with self.conexion() as con, con.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO analytics.metric
                    (run_id, modelo, metrica, valor, n, campania, fundo,
                     horizonte_semanas, banda_horizonte, atributos)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
                filas,
            )

    def guardar_parametros_legacy(self, run_id: int, tabla: pd.DataFrame) -> None:
        """Persiste el snapshot as-of de X/O/N/A/B usado por el challenger."""

        if tabla is None or tabla.empty:
            return
        columnas = [
            "campania",
            "fecha_emision",
            "lote_id",
            "fundo",
            "modulo",
            "variedad",
            "nivel_calibracion",
            "n_observaciones_asof",
            "fuente_parametros",
            "archivo_fuente",
            "sha256_fuente",
            "parametros_base_json",
            "correcciones_json",
            "parametros_finales_json",
            "gdd_base",
            "gdd_ventana",
            "fecha_corte",
        ]
        copia = tabla.copy()
        for columna in columnas:
            if columna not in copia:
                copia[columna] = None
        filas = []
        for fila in copia[columnas].itertuples(index=False, name=None):
            valores = list(fila)
            for indice in (11, 12, 13):
                valor = valores[indice]
                valores[indice] = _json(valor if isinstance(valor, (dict, list)) else {})
            valores.insert(0, run_id)
            valores[2] = _limpio(valores[2])
            valores[3] = _limpio(valores[3])
            valores[8] = int(_limpio(valores[8]) or 0)
            valores[17] = _limpio(valores[17])
            filas.append(tuple(_limpio(valor) for valor in valores))
        with self.conexion() as con, con.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO analytics.legacy_parameter_snapshot
                    (run_id, campania, fecha_emision, lote_id, fundo, modulo, variedad,
                     nivel_calibracion, n_observaciones_asof, fuente_parametros,
                     archivo_fuente, sha256_fuente, parametros_base_json, correcciones_json,
                     parametros_finales_json, gdd_base, gdd_ventana, fecha_corte)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s)
                ON CONFLICT (run_id, campania, fecha_emision, lote_id)
                DO UPDATE SET
                    fundo=EXCLUDED.fundo, modulo=EXCLUDED.modulo, variedad=EXCLUDED.variedad,
                    nivel_calibracion=EXCLUDED.nivel_calibracion,
                    n_observaciones_asof=EXCLUDED.n_observaciones_asof,
                    fuente_parametros=EXCLUDED.fuente_parametros,
                    archivo_fuente=EXCLUDED.archivo_fuente,
                    sha256_fuente=EXCLUDED.sha256_fuente,
                    parametros_base_json=EXCLUDED.parametros_base_json,
                    correcciones_json=EXCLUDED.correcciones_json,
                    parametros_finales_json=EXCLUDED.parametros_finales_json,
                    gdd_base=EXCLUDED.gdd_base, gdd_ventana=EXCLUDED.gdd_ventana,
                    fecha_corte=EXCLUDED.fecha_corte
                """,
                filas,
            )

    def guardar_metricas_comparacion(self, run_id: int, tabla: pd.DataFrame):
        if tabla.empty:
            return
        columnas = [
            "modelo_base",
            "modelo",
            "banda_horizonte",
            "n",
            "wape",
            "mase",
            "mae_kg",
            "sesgo_pct",
            "cobertura_80",
            "volumen_real_kg",
            "universo",
        ]
        filas = [
            (run_id, *[_limpio(fila.get(columna)) for columna in columnas])
            for fila in tabla.to_dict("records")
        ]
        with self.conexion() as con, con.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO analytics.model_comparison_metric
                    (run_id, modelo_base, modelo, banda_horizonte, n, wape, mase,
                     mae_kg, sesgo_pct, cobertura_80, volumen_real_kg, universo)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (run_id, modelo_base, modelo, banda_horizonte)
                DO UPDATE SET n = EXCLUDED.n, wape = EXCLUDED.wape,
                              mase = EXCLUDED.mase, mae_kg = EXCLUDED.mae_kg,
                              sesgo_pct = EXCLUDED.sesgo_pct,
                              cobertura_80 = EXCLUDED.cobertura_80,
                              volumen_real_kg = EXCLUDED.volumen_real_kg,
                              universo = EXCLUDED.universo
                """,
                filas,
            )

    def guardar_claims(self, run_id: int, claims: pd.DataFrame):
        if claims.empty:
            return
        columnas = [
            "claim_id",
            "hipotesis_id",
            "hipotesis",
            "clase_evidencia",
            "estado",
            "afirmacion",
            "estimacion",
            "intervalo_inferior",
            "intervalo_superior",
            "unidad",
            "n_efectivo",
            "alcance",
            "supuestos",
            "limitaciones",
            "referencias",
        ]
        json_defaults = {
            "alcance": {},
            "supuestos": [],
            "limitaciones": [],
            "referencias": [],
        }
        with self.conexion() as con, con.cursor() as cur:
            for fila in claims.itertuples(index=False):
                s = pd.Series(fila._asdict())
                valores = []
                for columna in columnas:
                    valor = s.get(columna)
                    if columna in json_defaults:
                        try:
                            es_nulo = pd.isna(valor)
                        except (TypeError, ValueError):
                            es_nulo = False
                        if isinstance(es_nulo, (bool, np.bool_)) and es_nulo:
                            valor = json_defaults[columna]
                        valores.append(_jsonb(valor))
                    else:
                        valores.append(_limpio(valor))
                if run_id is not None:
                    cur.execute(
                        """
                        INSERT INTO analytics.evidence_claim_history AS historial
                            (claim_id, run_id, hipotesis_id, hipotesis, clase_evidencia,
                             estado, afirmacion,
                             estimacion, intervalo_inferior, intervalo_superior, unidad, n_efectivo,
                             alcance, supuestos, limitaciones, referencias)
                        VALUES (
                            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                            %s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb
                        )
                        ON CONFLICT (claim_id, run_id) DO UPDATE SET
                            hipotesis_id=EXCLUDED.hipotesis_id,
                            hipotesis=EXCLUDED.hipotesis,
                            clase_evidencia=EXCLUDED.clase_evidencia,
                            estado=EXCLUDED.estado,
                            afirmacion=EXCLUDED.afirmacion,
                            estimacion=EXCLUDED.estimacion,
                            intervalo_inferior=EXCLUDED.intervalo_inferior,
                            intervalo_superior=EXCLUDED.intervalo_superior,
                            unidad=EXCLUDED.unidad,
                            n_efectivo=EXCLUDED.n_efectivo,
                            alcance=EXCLUDED.alcance,
                            supuestos=EXCLUDED.supuestos,
                            limitaciones=EXCLUDED.limitaciones,
                            referencias=EXCLUDED.referencias
                        WHERE historial.hipotesis_id IS NOT DISTINCT FROM EXCLUDED.hipotesis_id
                          AND historial.hipotesis IS NOT DISTINCT FROM EXCLUDED.hipotesis
                          AND historial.clase_evidencia IS NOT DISTINCT FROM
                              EXCLUDED.clase_evidencia
                          AND historial.estado IS NOT DISTINCT FROM EXCLUDED.estado
                          AND historial.afirmacion IS NOT DISTINCT FROM EXCLUDED.afirmacion
                          AND historial.estimacion IS NOT DISTINCT FROM EXCLUDED.estimacion
                          AND historial.intervalo_inferior IS NOT DISTINCT FROM
                              EXCLUDED.intervalo_inferior
                          AND historial.intervalo_superior IS NOT DISTINCT FROM
                              EXCLUDED.intervalo_superior
                          AND historial.unidad IS NOT DISTINCT FROM EXCLUDED.unidad
                          AND historial.n_efectivo IS NOT DISTINCT FROM EXCLUDED.n_efectivo
                          AND historial.alcance IS NOT DISTINCT FROM EXCLUDED.alcance
                          AND historial.supuestos IS NOT DISTINCT FROM EXCLUDED.supuestos
                          AND historial.limitaciones IS NOT DISTINCT FROM EXCLUDED.limitaciones
                          AND historial.referencias IS NOT DISTINCT FROM EXCLUDED.referencias
                    """,
                        (valores[0], run_id, *valores[1:]),
                    )
                    if cur.rowcount == 0:
                        raise ClaimHistoryConflictError(
                            "El claim histórico "
                            f"({valores[0]!r}, {run_id!r}) ya existe con contenido diferente."
                        )
                cur.execute(
                    """
                    INSERT INTO analytics.evidence_claim
                        (claim_id, run_id, hipotesis_id, hipotesis, clase_evidencia,
                         estado, afirmacion,
                         estimacion, intervalo_inferior, intervalo_superior, unidad, n_efectivo,
                         alcance, supuestos, limitaciones, referencias)
                    VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb
                    )
                    ON CONFLICT (claim_id) DO UPDATE SET
                        run_id=EXCLUDED.run_id, hipotesis_id=EXCLUDED.hipotesis_id,
                        clase_evidencia=EXCLUDED.clase_evidencia,
                        estado=EXCLUDED.estado, afirmacion=EXCLUDED.afirmacion,
                        estimacion=EXCLUDED.estimacion,
                        intervalo_inferior=EXCLUDED.intervalo_inferior,
                        intervalo_superior=EXCLUDED.intervalo_superior,
                        n_efectivo=EXCLUDED.n_efectivo,
                        alcance=EXCLUDED.alcance, supuestos=EXCLUDED.supuestos,
                        limitaciones=EXCLUDED.limitaciones, referencias=EXCLUDED.referencias,
                        actualizado_en=now()
                """,
                    (valores[0], run_id, *valores[1:]),
                )

    def guardar_evidencia_features(self, run_id: int, evidencia: pd.DataFrame):
        """Vincula cada feature usada con la evidencia recalculada en su fold temporal."""

        if evidencia is None or evidencia.empty:
            return
        columnas = [
            "modelo",
            "modelo_componente",
            "predictor",
            "objetivo",
            "rezago",
            "transformacion",
            "hipotesis_id",
            "hipotesis",
            "referencias",
            "metodo",
            "papel",
            "estado",
            "admitida",
            "cobertura",
            "n_efectivo",
            "estimacion",
            "p_value",
            "q_value",
            "placebo",
            "estabilidad_modulo",
            "fecha_emision",
            "limitacion",
        ]
        tabla = evidencia.copy()
        for columna in columnas:
            if columna not in tabla:
                tabla[columna] = None
        with self.conexion() as con, con.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (hipotesis_id) hipotesis_id, claim_id
                FROM analytics.evidence_claim
                WHERE hipotesis_id IS NOT NULL
                ORDER BY hipotesis_id, actualizado_en DESC
                """
            )
            claims = {hipotesis_id: claim_id for hipotesis_id, claim_id in cur.fetchall()}
            filas = [
                (
                    run_id,
                    *[
                        _json(serie.get(c) or []) if c == "referencias" else _limpio(serie.get(c))
                        for c in columnas
                    ],
                    claims.get(serie.get("hipotesis_id")),
                )
                for _, serie in tabla[columnas].iterrows()
            ]
            cur.executemany(
                """
                INSERT INTO analytics.model_feature_evidence
                    (run_id, modelo, modelo_componente, predictor, objetivo, rezago,
                     transformacion, hipotesis_id, hipotesis, referencias, metodo, papel, estado,
                     admitida, cobertura, n_efectivo, estimacion, p_value, q_value,
                     placebo, estabilidad_modulo, fecha_emision, limitacion, claim_id)
                VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                ON CONFLICT (run_id, modelo, predictor, objetivo, fecha_emision)
                DO UPDATE SET
                    modelo_componente=EXCLUDED.modelo_componente,
                    estado=EXCLUDED.estado, admitida=EXCLUDED.admitida,
                    referencias=EXCLUDED.referencias,
                    cobertura=EXCLUDED.cobertura, n_efectivo=EXCLUDED.n_efectivo,
                    estimacion=EXCLUDED.estimacion, p_value=EXCLUDED.p_value,
                    q_value=EXCLUDED.q_value, placebo=EXCLUDED.placebo,
                    estabilidad_modulo=EXCLUDED.estabilidad_modulo,
                    limitacion=EXCLUDED.limitacion, claim_id=EXCLUDED.claim_id
                """,
                filas,
            )

    def guardar_pronostico_clima(self, run_id: int, pronostico) -> int:
        """Persiste el payload completo para que el forecast climático también sea as-of."""

        with self.conexion() as con, con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO analytics.weather_forecast_snapshot
                    (run_id, proveedor, endpoint, latitud, longitud, emitido_en,
                     payload_sha256, payload)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (proveedor, latitud, longitud, emitido_en, payload_sha256)
                DO UPDATE SET run_id=EXCLUDED.run_id
                RETURNING weather_snapshot_id
                """,
                (
                    run_id,
                    pronostico.proveedor,
                    pronostico.endpoint,
                    pronostico.latitud,
                    pronostico.longitud,
                    pronostico.emitido_en,
                    pronostico.payload_sha256,
                    _json(pronostico.payload),
                ),
            )
            return int(cur.fetchone()[0])
