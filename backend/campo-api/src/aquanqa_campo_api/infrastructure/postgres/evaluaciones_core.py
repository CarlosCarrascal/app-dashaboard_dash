"""Único destino de escritura móvil: cabecera canónica y detalle por módulo."""

from psycopg import sql

MODULE_TYPES = {"baya": "desarrollo", "pesos": "peso"}


def write_details(cursor, normalized, evaluation_id, *, replace=False):
    data = normalized.data
    module = normalized.module_key
    kind = MODULE_TYPES.get(module, module)
    if replace:
        tables = {
            "estadios": ["ev_estadios"],
            "flores": ["ev_conteo_flores"],
            "brotes": ["ev_conteo_brotes"],
            "ramas": ["ev_rama_observacion", "ev_conteo_ramas"],
            "baya": ["ev_fruto_observacion"],
            "pesos": ["ev_fruto_observacion"],
        }[module]
        for table in tables:
            cursor.execute(
                sql.SQL("DELETE FROM core.{} WHERE evaluacion_id=%s").format(sql.Identifier(table)),
                (evaluation_id,),
            )
    if module in {"estadios", "flores", "brotes", "ramas"}:
        table, fields = {
            "estadios": (
                "ev_estadios",
                {
                    **{f"e{i}": data.get(f"e{i}") for i in range(1, 6)},
                    "total_origen": data.get("total_origen"),
                    "item_origen": data.get("item"),
                },
            ),
            "flores": (
                "ev_conteo_flores",
                {
                    **{
                        key: data.get(key)
                        for key in (
                            "n_flores",
                            "cuajo",
                            "yemas_abiertas",
                            "yemas_por_abrir",
                            "yemas_muertas",
                            "brotes_tiernos",
                        )
                    },
                    "item_origen": data.get("item"),
                },
            ),
            "brotes": (
                "ev_conteo_brotes",
                {
                    "piso": data.get("piso"),
                    "brotes": data.get("brotes"),
                    **{f"des{i}_origen": data.get(f"des{i}") for i in range(1, 4)},
                },
            ),
            "ramas": (
                "ev_conteo_ramas",
                {key: data.get(key) for key in ("ramas_menor5", "ramas_mayor5")},
            ),
        }[module]
        fields = {"evaluacion_id": evaluation_id, **fields}
        cursor.execute(
            sql.SQL("INSERT INTO core.{} ({}) VALUES ({})").format(
                sql.Identifier(table),
                sql.SQL(",").join(map(sql.Identifier, fields)),
                sql.SQL(",").join(sql.Placeholder() for _ in fields),
            ),
            tuple(fields.values()),
        )
    if module == "ramas":
        cursor.executemany(
            """
            INSERT INTO core.ev_rama_observacion
                (evaluacion_id,numero_rama,numero_medicion,diametro_mm,id_origen)
            VALUES (%s,%s,1,%s,%s)
        """,
            [
                (evaluation_id, row["nro_rama"], row["diametro"], str(normalized.source.client_id))
                for row in data["mediciones"]
            ],
        )
    elif module in {"baya", "pesos"}:
        cursor.executemany(
            """
            INSERT INTO core.ev_fruto_observacion
                (evaluacion_id,tipo,numero_muestra,numero_medicion,estado_codigo,diametro_mm,peso_g)
            VALUES (%s,%s,%s,1,%s,%s,%s)
        """,
            [
                (
                    evaluation_id,
                    kind,
                    row["numero_muestra"],
                    row.get("estado_codigo"),
                    row.get("diametro_mm"),
                    row.get("peso_g"),
                )
                for row in data["observaciones"]
            ],
        )


def persist(cursor, normalized, lote_id, evaluador_id):
    source = normalized.source
    cursor.execute(
        """
        INSERT INTO core.ev_evaluacion
            (tipo,grano,fecha,hora,captured_at,lote_id,cortina,hilera,planta,evaluador_id,origen)
        VALUES (%s,'captura',%s,%s,%s,%s,%s,%s,%s,%s,'mobile')
        RETURNING evaluacion_id
    """,
        (
            MODULE_TYPES.get(source.module_key, source.module_key),
            source.fecha,
            normalized.data.get("hora"),
            source.captured_at,
            lote_id,
            source.cortina,
            source.hilera,
            source.planta,
            evaluador_id,
        ),
    )
    evaluation_id = cursor.fetchone()["evaluacion_id"]
    write_details(cursor, normalized, evaluation_id)
    return "ev_evaluacion", evaluation_id, False


def update_resource(cursor, normalized, *, lote_id, evaluator_id, resource_id, **_):
    source = normalized.source
    cursor.execute(
        """
        UPDATE core.ev_evaluacion SET lote_id=%s,cortina=%s,hilera=%s,planta=%s,
            revision=revision+1,actualizado_en=now()
        WHERE evaluacion_id=%s AND origen='mobile' AND tipo=%s AND evaluador_id=%s
            AND estado_registro='vigente'
        RETURNING evaluacion_id
    """,
        (
            lote_id,
            source.cortina,
            source.hilera,
            source.planta,
            resource_id,
            MODULE_TYPES.get(source.module_key, source.module_key),
            evaluator_id,
        ),
    )
    if cursor.fetchone() is None:
        from ...modules.evaluaciones.repository import EvaluationConflictError

        raise EvaluationConflictError("la captura no pertenece al módulo/evaluador vigente")
    write_details(cursor, normalized, resource_id, replace=True)
