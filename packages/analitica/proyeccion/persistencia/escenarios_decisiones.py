"""Persistencia de escenarios de proyección y decisiones de promoción."""

from __future__ import annotations

import pandas as pd

from ..compartido import limpiar_valor as _limpio
from ..compartido import serializar_json as _json


class EscenariosDecisionesMixin:
    """Operaciones de revisión de escenarios y decisiones vigentes."""

    def guardar_escenario(
        self,
        *,
        nombre: str,
        modo_decision: str,
        run_base_id: int | None,
        parametros: dict,
        advertencias: list[str] | None = None,
        actor: str | None = None,
    ) -> int:
        if modo_decision not in {"plan_semanal", "poda_campania"}:
            raise ValueError("modo_decision inválido")
        with self.conexion() as con, con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO analytics.projection_scenario
                    (nombre, modo_decision, run_base_id, parametros, advertencias, creado_por)
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s)
                RETURNING scenario_id
                """,
                (
                    nombre.strip() or "escenario sin nombre",
                    modo_decision,
                    run_base_id,
                    _json(parametros),
                    _json(advertencias or []),
                    actor,
                ),
            )
            return int(cur.fetchone()[0])

    def cambiar_estado_escenario(
        self,
        scenario_id: int,
        estado_nuevo: str,
        *,
        comentario: str | None = None,
        actor: str | None = None,
    ) -> None:
        transiciones = {
            "guardado": {"en_revision"},
            "en_revision": {"aprobado", "guardado"},
            "aprobado": {"publicado", "en_revision"},
            "publicado": {"reemplazado"},
            "reemplazado": set(),
        }
        with self.conexion() as con, con.cursor() as cur:
            cur.execute(
                "SELECT estado, parametros FROM analytics.projection_scenario WHERE scenario_id=%s",
                (scenario_id,),
            )
            fila = cur.fetchone()
            if not fila:
                raise ValueError(f"Escenario inexistente: {scenario_id}")
            anterior, parametros = fila
            if estado_nuevo not in transiciones.get(anterior, set()):
                raise ValueError(f"Transición no permitida: {anterior} → {estado_nuevo}")
            if estado_nuevo == "publicado":
                modelo = (parametros or {}).get("modelo")
                if modelo and modelo != "R09_publicado":
                    cur.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM analytics.model_decision
                            WHERE vigente AND resultado='promover' AND challenger=%s
                        )
                        """,
                        (modelo,),
                    )
                    if not cur.fetchone()[0]:
                        raise ValueError(
                            "Publicación bloqueada: el challenger no tiene decisión de promoción."
                        )
            cur.execute(
                """
                UPDATE analytics.projection_scenario
                SET estado=%s, actualizado_en=now()
                WHERE scenario_id=%s
                """,
                (estado_nuevo, scenario_id),
            )
            cur.execute(
                """
                INSERT INTO analytics.projection_scenario_review
                    (scenario_id, estado_anterior, estado_nuevo, comentario, actor)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (scenario_id, anterior, estado_nuevo, comentario, actor),
            )

    def guardar_decisiones(self, run_id: int, decisiones: pd.DataFrame):
        if decisiones.empty:
            return
        with self.conexion() as con, con.cursor() as cur:
            for fila in decisiones.itertuples(index=False):
                s = pd.Series(fila._asdict())
                cur.execute(
                    "UPDATE analytics.model_decision SET vigente=false "
                    "WHERE banda_horizonte=%s AND vigente",
                    (s.banda_horizonte,),
                )
                excluidas = {
                    "banda_horizonte",
                    "campeon",
                    "challenger",
                    "resultado",
                    "justificacion",
                    "checks",
                }
                metricas = {
                    k: _limpio(v) for k, v in s.items() if k not in excluidas and not pd.isna(v)
                }
                cur.execute(
                    """
                    INSERT INTO analytics.model_decision
                        (run_id, banda_horizonte, campeon, challenger, resultado, regla,
                         metricas, justificacion, decidido_por)
                    VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,'pipeline')
                """,
                    (
                        run_id,
                        s.banda_horizonte,
                        s.campeon,
                        _limpio(s.challenger),
                        s.resultado,
                        _json(
                            {
                                "criterios": "REGLA_PROMOCION",
                                "checks": _limpio(s.get("checks")),
                            }
                        ),
                        _json(metricas),
                        s.justificacion,
                    ),
                )

    def decisiones_vigentes(self) -> pd.DataFrame:
        """Decisiones del último backtest; project las consume pero no las reescribe."""
        with self.conexion() as con, con.cursor() as cur:
            cur.execute(
                """
                SELECT banda_horizonte, campeon, challenger, resultado,
                       justificacion, regla, metricas
                FROM analytics.model_decision
                WHERE vigente
                ORDER BY banda_horizonte
                """
            )
            columnas = [descripcion.name for descripcion in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=columnas)
