"""SQL de lectura para el panel administrativo.

Las consultas están separadas del adaptador para que el contrato administrativo no termine
mezclado con la persistencia de la app móvil. No se interpolan filtros recibidos del cliente;
solo se inserta el ``ORDER BY`` elegido desde una lista blanca.
"""

from __future__ import annotations

EVALUATIONS_CTE = """
WITH evaluaciones AS (
 SELECT 'ev_evaluacion'::text source_table,x.evaluacion_id source_id,
   CASE x.tipo WHEN 'desarrollo' THEN 'baya' WHEN 'peso' THEN 'pesos' ELSE x.tipo END module_key,
   x.tipo,x.origen,x.fecha,x.grano,
   COALESCE(x.captured_at,(x.fecha::timestamp+COALESCE(x.hora,time '00:00'))
       AT TIME ZONE 'America/Lima') captured_at,
   x.lote_id,emp.empresa_id,f.fundo_id,mo.modulo_id,x.evaluador_id,
   emp.nombre empresa,f.codigo fundo,mo.codigo modulo,l.codigo lote,v.nombre variedad,
   btrim(concat_ws(' ',ev.nombres,ev.apellidos)) evaluador,COALESCE(ev.dni,'') evaluador_dni,
   jsonb_build_object('cortina',x.cortina,'hilera',x.hilera,'planta',x.planta,
      'hora',x.hora,'grano',x.grano,'publicacion_id',x.publicacion_id,'revision',x.revision)
   || CASE x.tipo
     WHEN 'estadios' THEN (to_jsonb(s)-'tipo'-'evaluacion_id') ||
       jsonb_build_object('total',s.total_calculado,'item',s.item_origen)
     WHEN 'flores' THEN (to_jsonb(c)-'tipo'-'evaluacion_id') ||
       jsonb_build_object('item',c.item_origen)
     WHEN 'brotes' THEN (to_jsonb(b)-'tipo'-'evaluacion_id') ||
       jsonb_build_object('des1',b.des1_origen,'des2',b.des2_origen,'des3',b.des3_origen)
     WHEN 'ramas' THEN (to_jsonb(r)-'tipo'-'evaluacion_id') ||
       jsonb_build_object('mediciones',COALESCE((SELECT jsonb_agg(
         jsonb_build_object('nro_rama',o.numero_rama,'numero_medicion',o.numero_medicion,
          'diametro',o.diametro_mm,'sospechoso',o.sospechoso,'id_origen',o.id_origen)
         ORDER BY o.numero_rama,o.numero_medicion)
         FROM core.ev_rama_observacion o WHERE o.evaluacion_id=x.evaluacion_id),'[]'::jsonb))
     ELSE (SELECT jsonb_build_object(
         'cantidad_muestras',count(*),'diametro_promedio',avg(o.diametro_mm),
         'diametro_minimo',min(o.diametro_mm),'diametro_maximo',max(o.diametro_mm),
         'observaciones',COALESCE(jsonb_agg(to_jsonb(o)-'evaluacion_id'-'tipo'
            ORDER BY o.numero_muestra,o.numero_medicion),'[]'::jsonb))
         FROM core.ev_fruto_observacion o WHERE o.evaluacion_id=x.evaluacion_id)
   END detalle
 FROM core.ev_evaluacion x
 JOIN core.m_lote l ON l.lote_id=x.lote_id
 JOIN core.m_modulo mo ON mo.modulo_id=l.modulo_id
 JOIN core.m_fundo f ON f.fundo_id=mo.fundo_id
 JOIN core.m_empresa emp ON emp.empresa_id=f.empresa_id
 LEFT JOIN core.m_variedad v ON v.variedad_id=l.variedad_id
 LEFT JOIN core.m_evaluador ev ON ev.evaluador_id=x.evaluador_id
 LEFT JOIN core.ev_estadios s ON s.evaluacion_id=x.evaluacion_id
 LEFT JOIN core.ev_conteo_flores c ON c.evaluacion_id=x.evaluacion_id
 LEFT JOIN core.ev_conteo_brotes b ON b.evaluacion_id=x.evaluacion_id
 LEFT JOIN core.ev_conteo_ramas r ON r.evaluacion_id=x.evaluacion_id
 WHERE x.estado_registro='vigente'
)
"""

EVALUATION_ORDER = {
    "captured_at": "captured_at",
    "fecha": "fecha",
    "module_key": "module_key",
    "empresa": "empresa",
    "fundo": "fundo",
    "modulo": "modulo",
    "lote": "lote",
    "evaluador": "evaluador",
}


def analytics_cte(module_key: str, *, prepare_territory: bool = False) -> str:
    """Project only measurements used by analytics, never capture/audit payloads.

    Retain the same joins and scope columns as records so filtering is identical.
    Field lists are internal constants, never SQL supplied by the caller.
    """
    fields = {
        "estadios": ("s", ("e1", "e2", "e3", "e4", "e5")),
        "flores": ("c", ("n_flores", "cuajo", "yemas_abiertas", "yemas_por_abrir", "yemas_muertas", "brotes_tiernos")),
        "brotes": ("b", ("piso", "brotes")),
    }
    if module_key in fields:
        alias, names = fields[module_key]
        detail = "jsonb_build_object(" + ",".join(f"'{name}',{alias}.{name}" for name in names) + ")"
    elif module_key == "ramas":
        detail = """jsonb_build_object('ramas_menor5',r.ramas_menor5,'ramas_mayor5',r.ramas_mayor5,
          'mediciones',COALESCE((SELECT jsonb_agg(jsonb_build_object(
            'nro_rama',o.numero_rama,'numero_medicion',o.numero_medicion,
            'diametro',o.diametro_mm,'sospechoso',o.sospechoso)
            ORDER BY o.numero_rama,o.numero_medicion)
            FROM core.ev_rama_observacion o WHERE o.evaluacion_id=x.evaluacion_id),'[]'::jsonb))"""
    elif module_key in ("baya", "pesos"):
        detail = """jsonb_build_object('observaciones',COALESCE((SELECT jsonb_agg(jsonb_build_object(
            'numero_muestra',o.numero_muestra,'numero_medicion',o.numero_medicion,
            'diametro_mm',o.diametro_mm,'peso_g',o.peso_g,'estado_codigo',o.estado_codigo)
            ORDER BY o.numero_muestra,o.numero_medicion)
            FROM core.ev_fruto_observacion o WHERE o.evaluacion_id=x.evaluacion_id),'[]'::jsonb))"""
    else:
        raise ValueError("Familia analítica desconocida")
    before, _, rest = EVALUATIONS_CTE.partition("   jsonb_build_object('cortina'")
    _, _, after = rest.partition("   END detalle")
    # A family is already mandatory here. Filter the stored type directly so
    # PostgreSQL can use its type/date index instead of evaluating CASE across
    # every evaluation. The outer module_key filter and scope still apply.
    stored_type = {'baya': 'desarrollo', 'pesos': 'peso'}.get(module_key, module_key)
    after = after.replace("WHERE x.estado_registro='vigente'",
                          f"WHERE x.estado_registro='vigente' AND x.tipo='{stored_type}'", 1)
    query = before + "   " + detail + " detalle" + after
    # Materializing the small territory lookup helps these count families.
    # Flowers and fruit series need predicate pushdown through their joins.
    if not prepare_territory or module_key not in ('estadios', 'ramas', 'brotes'):
        return query
    territory_joins = """JOIN core.m_lote l ON l.lote_id=x.lote_id
 JOIN core.m_modulo mo ON mo.modulo_id=l.modulo_id
 JOIN core.m_fundo f ON f.fundo_id=mo.fundo_id
 JOIN core.m_empresa emp ON emp.empresa_id=f.empresa_id"""
    query = query.replace(territory_joins, 'JOIN analytical_territory t ON t.lote_id=x.lote_id')
    for original, replacement in {
        'emp.empresa_id':'t.empresa_id', 'f.fundo_id':'t.fundo_id',
        'mo.modulo_id':'t.modulo_id', 'emp.nombre':'t.empresa',
        'f.codigo':'t.fundo', 'mo.codigo':'t.modulo', 'l.codigo':'t.lote',
        'l.variedad_id':'t.variedad_id',
    }.items():
        query = query.replace(original, replacement)
    territory = """WITH analytical_territory AS MATERIALIZED (
      SELECT l.lote_id,l.variedad_id,mo.modulo_id,f.fundo_id,emp.empresa_id,
        l.codigo lote,mo.codigo modulo,f.codigo fundo,emp.nombre empresa
      FROM core.m_lote l JOIN core.m_modulo mo ON mo.modulo_id=l.modulo_id
      JOIN core.m_fundo f ON f.fundo_id=mo.fundo_id
      JOIN core.m_empresa emp ON emp.empresa_id=f.empresa_id
    ), evaluaciones AS ("""
    return query.replace('WITH evaluaciones AS (',territory,1)


ANALYTICS_FIELDS = {
    "estadios": ("e1", "e2", "e3", "e4", "e5"),
    "flores": ("n_flores", "cuajo", "yemas_abiertas", "yemas_por_abrir", "yemas_muertas", "brotes_tiernos"),
    "brotes": ("piso", "brotes"),
    "ramas": ("ramas_menor5", "ramas_mayor5", "mediciones"),
    "baya": ("observaciones",),
    "pesos": ("observaciones",),
}


SAMPLE_FIELDS = {
    "mediciones": ("nro_rama", "numero_medicion", "diametro", "sospechoso"),
    "observaciones": ("numero_muestra", "numero_medicion", "diametro_mm", "peso_g", "estado_codigo"),
}


def analytics_rows_sql(cte: str, where: str, module_key: str, *, daily: bool = False) -> str:
    # One scope label per lot/date, positional measurements on the database wire.
    # The HTTP contract and the full-population calculations remain unchanged.
    alias = {'estadios': 's', 'flores': 'c', 'brotes': 'b', 'ramas': 'r'}.get(module_key)
    columns = []
    for field in ANALYTICS_FIELDS[module_key]:
        if field in SAMPLE_FIELDS:
            if field == 'mediciones':
                table = 'core.ev_rama_observacion'
                cells = 'o.numero_rama,o.numero_medicion,o.diametro_mm,o.sospechoso'
                order = 'o.numero_rama,o.numero_medicion'
            else:
                table = 'core.ev_fruto_observacion'
                cells = 'o.numero_muestra,o.numero_medicion,o.diametro_mm,o.peso_g,o.estado_codigo'
                order = 'o.numero_muestra,o.numero_medicion'
            packed_columns = []
            for cell in cells.split(','):
                array = f'jsonb_agg({cell} ORDER BY {order})'
                uniform = f'count(DISTINCT {cell}) <= 1 AND (count({cell})=0 OR count({cell})=count(*))'
                packed_columns.append(f'CASE WHEN {uniform} THEN ({array}->0) ELSE {array} END')
            # Constant sample columns travel once per evaluation. Nonuniform
            # columns retain their ordered values, including explicit nulls.
            expression = (f"(SELECT jsonb_build_object('columns',jsonb_build_array(count(*),"
                          f"{','.join(packed_columns)})) FROM {table} o WHERE o.evaluacion_id=x.evaluacion_id)")
        else:
            expression = f'{alias}.{field}'
        columns.append(f'{expression} AS measure_{field}')
    # Keep detalle for search/state filters, but read measurements straight from
    # typed columns. PostgreSQL can omit the unused JSON object projection.
    cte = cte.replace(' detalle', ' detalle,' + ','.join(columns), 1)
    values = ','.join(f'measure_{field}' for field in ANALYTICS_FIELDS[module_key])
    scope = 'fecha,NULL::bigint lote_id,NULL::text fundo,NULL::text modulo,NULL::text lote' if daily else 'fecha,lote_id,fundo,modulo,lote'
    group = 'fecha' if daily else 'fecha,lote_id,fundo,modulo,lote'
    order = 'lote_id,source_id' if daily else 'source_id'
    return f"""{cte}
      SELECT {scope},
        jsonb_agg(jsonb_build_array(source_id,{values}) ORDER BY {order}) measurements
      FROM evaluaciones WHERE {where}
      GROUP BY {group} ORDER BY fecha{'' if daily else ',lote_id'}"""



def snapshot_rows_sql(cte: str, where: str, module_key: str, *, series_metric: str | None = None, with_state: bool = False) -> str:
    original_cte = cte
    selected = f"({where}) AND grano=(SELECT grano FROM chosen) AND fecha=(SELECT fecha FROM chosen)"
    packed = analytics_rows_sql(cte,selected,module_key)
    cte, separator, body = packed.partition('      SELECT fecha,lote_id,fundo,modulo,lote,')
    if not separator:
        raise ValueError('Proyección de snapshot inválida')
    # Multiple references must not force materialization of every nested sample.
    cte = cte.replace('evaluaciones AS (','evaluaciones AS NOT MATERIALIZED (',1)
    sql = f"""{cte}, available AS MATERIALIZED (
      SELECT grano,max(fecha) fecha,count(*) n FROM evaluaciones WHERE {where} GROUP BY grano
    ), chosen AS (
      SELECT grano,fecha FROM available WHERE grano=COALESCE(%s::text,
        (SELECT grano FROM available WHERE grano IS NOT NULL ORDER BY n DESC,grano LIMIT 1))
    ), packed AS ({separator}{body})
    SELECT (SELECT jsonb_agg(to_jsonb(a) ORDER BY n DESC,grano) FROM available a) available,
           (SELECT jsonb_agg(to_jsonb(p) ORDER BY fecha,lote_id) FROM packed p) groups"""
    if series_metric is not None:
        history_where = (f"({where}) AND grano=(SELECT grano FROM chosen) "
                         "AND fecha >= COALESCE(%s::date,(SELECT fecha FROM chosen)-29) "
                         "AND fecha <= (SELECT fecha FROM chosen)")
        history = (stage_trend_sql(original_cte, history_where) if module_key == 'estadios' else
                   series_trend_sql(original_cte, history_where, module_key, series_metric, with_state))
        sql += f", (SELECT jsonb_agg(to_jsonb(t) ORDER BY fecha) FROM ({history}) t) trend"
    return sql


def series_trend_sql(cte: str, where: str, module_key: str, metric: str, with_state: bool = False) -> str:
    if module_key == 'flores':
        if metric not in ANALYTICS_FIELDS['flores']:
            raise ValueError('Indicador desconocido')
        cte = cte.replace(' detalle', f' detalle,c.{metric} AS series_value', 1)
    elif module_key == 'brotes':
        cte = cte.replace(' detalle', ' detalle,b.brotes AS series_value', 1)
    simple = module_key in ('flores', 'brotes')
    if simple:
        valid = "value >= 0 AND value < 'Infinity'::double precision"
        # Counts and quantiles share the same evaluation unit. One aggregation
        # preserves empty metrics without materializing and joining daily tables.
        return f"""{cte}, values_by_evaluation AS (
          SELECT fecha,series_value::double precision value FROM evaluaciones WHERE {where}
        ) SELECT fecha,count(*) evaluations,0::bigint observations,0::bigint excluded,
          count(*) FILTER (WHERE {valid}) n,
          percentile_cont(ARRAY[0.25,0.5,0.75]) WITHIN GROUP (ORDER BY value)
            FILTER (WHERE {valid}) quantiles
          FROM values_by_evaluation GROUP BY fecha ORDER BY fecha"""
    else:
        filtered = f'SELECT source_id,fecha FROM evaluaciones WHERE {where}'
        if module_key == 'ramas':
            table, ordinal = 'core.ev_rama_observacion', 'numero_rama'
            conflict = 'COALESCE(o.sospechoso,FALSE) OR '
            state = 'NULL::text'
        elif module_key in ('baya', 'pesos'):
            table, ordinal = 'core.ev_fruto_observacion', 'numero_muestra'
            conflict, state = '', 'o.estado_codigo'
        else:
            raise ValueError('Familia desconocida')
        value = 'peso_g' if module_key == 'pesos' else 'diametro_mm'
        # Count duplicate ordinals before filtering states, as in aggregate().
        candidates = f"""SELECT * FROM (
          SELECT f.fecha,o.{value}::double precision value,{state} state,
            ({conflict}COALESCE(o.numero_medicion,1)>1 OR (o.{ordinal} IS NOT NULL AND
             count(*) OVER (PARTITION BY f.source_id,o.{ordinal})>1)) conflict
          FROM filtered f JOIN {table} o ON o.evaluacion_id=f.source_id
        ) samples {"WHERE state = %s" if with_state else ''}"""
        observed = 'count(*)'
        valid = "NOT conflict AND value > 0 AND value < 'Infinity'::double precision"
    return f"""{cte}, filtered AS MATERIALIZED ({filtered}),
      days AS (SELECT fecha,count(*) evaluations FROM filtered GROUP BY fecha),
      candidates AS MATERIALIZED ({candidates}),
      stats AS (SELECT fecha,{observed} observations,count(*) FILTER (WHERE conflict) excluded,
        count(*) FILTER (WHERE {valid}) n,
        percentile_cont(ARRAY[0.25,0.5,0.75]) WITHIN GROUP (ORDER BY value)
          FILTER (WHERE {valid}) quantiles
        FROM candidates GROUP BY fecha)
      SELECT d.fecha,d.evaluations,COALESCE(s.observations,0) observations,
        COALESCE(s.excluded,0) excluded,COALESCE(s.n,0) n,s.quantiles
      FROM days d LEFT JOIN stats s USING(fecha) ORDER BY d.fecha"""


def stage_trend_sql(cte: str, where: str, *, analytical: bool = False) -> str:
    # Counts originate in typed numeric stage columns. Validate all five together,
    # exactly as aggregate() does, before contributing any stage to the denominator.
    raw_columns = ",".join(f"s.e{i} AS stage_e{i}" for i in range(1, 6))
    cte = cte.replace(" detalle", f" detalle,{raw_columns}", 1)
    columns = ",".join(f"stage_e{i}::double precision AS e{i}" for i in range(1, 6))
    valid = " AND ".join(f"e{i} >= 0 AND e{i} < 'Infinity'::double precision" for i in range(1, 6))
    sums = ",".join(f"sum(e{i}) FILTER (WHERE complete) AS e{i}" for i in range(1, 6))
    scope = 'fecha,lote_id,fundo,modulo,lote' if analytical else 'fecha'
    result_scope = ("fecha,lote_id,grouping(lote_id,fecha) bucket_kind,"
                    "max(fundo) fundo,max(modulo) modulo,max(lote) lote") if analytical else 'fecha'
    grouping = 'GROUPING SETS ((),(lote_id),(fecha))' if analytical else 'fecha'
    return f"""{cte}, stage_values AS (
      SELECT {scope},{columns} FROM evaluaciones WHERE {where}
    ), stage_validity AS MATERIALIZED (
      SELECT *,COALESCE(({valid}),FALSE) complete FROM stage_values
    ) SELECT {result_scope},count(*) evaluations,count(*) FILTER (WHERE complete) complete,{sums}
      FROM stage_validity GROUP BY {grouping} ORDER BY fecha"""


def unpack_analytics_rows(groups: list[dict], module_key: str) -> list[dict]:
    fields = ANALYTICS_FIELDS[module_key]
    rows = []
    for group in groups:
        for values in group["measurements"]:
            detail = dict(zip(fields, values[1:], strict=True))
            for field, names in SAMPLE_FIELDS.items():
                if field in detail:
                    packed = detail[field]
                    if isinstance(packed, dict) and 'columns' in packed:
                        count, *columns = packed['columns']
                        detail[field] = [dict(zip(names, (column[i] if isinstance(column, list) else column
                            for column in columns), strict=True)) for i in range(count)]
                    else:
                        detail[field] = [dict(zip(names, sample, strict=True)) if isinstance(sample, list) else sample
                                         for sample in packed or []]
            rows.append({"source_id": values[0], "fecha": group["fecha"], "lote_id": group["lote_id"],
                         "fundo": group["fundo"], "modulo": group["modulo"], "lote": group["lote"],
                         "detalle": detail})
    return rows


MASTER_DEFINITIONS = {
    "empresas": {
        "select": "empresa_id, nombre, activo, es_sentinel, creado_en",
        "from": "core.m_empresa",
        "search": "concat_ws(' ', nombre)",
        "where": "NOT es_sentinel",
        "order": "nombre, empresa_id",
    },
    "fundos": {
        "select": (
            "f.fundo_id, f.empresa_id, e.nombre AS empresa, f.codigo, "
            "f.alias_operativo, f.activo, f.es_sentinel, f.creado_en"
        ),
        "from": "core.m_fundo f JOIN core.m_empresa e ON e.empresa_id = f.empresa_id",
        "search": "concat_ws(' ', e.nombre, f.codigo, f.alias_operativo)",
        "where": "NOT f.es_sentinel AND NOT e.es_sentinel",
        "order": "e.nombre, f.codigo, f.fundo_id",
    },
    "modulos": {
        "select": (
            "m.modulo_id, m.fundo_id, f.empresa_id, e.nombre AS empresa, "
            "f.codigo AS fundo, m.codigo, m.activo, m.es_sentinel"
        ),
        "from": (
            "core.m_modulo m JOIN core.m_fundo f ON f.fundo_id = m.fundo_id "
            "JOIN core.m_empresa e ON e.empresa_id = f.empresa_id"
        ),
        "search": "concat_ws(' ', e.nombre, f.codigo, m.codigo)",
        "where": "NOT m.es_sentinel AND NOT f.es_sentinel AND NOT e.es_sentinel",
        "order": "e.nombre, f.codigo, m.codigo, m.modulo_id",
    },
    "lotes": {
        "select": (
            "l.lote_id, l.modulo_id, m.fundo_id, f.empresa_id, e.nombre AS empresa, "
            "f.codigo AS fundo, m.codigo AS modulo, l.codigo, l.turno_id, "
            "t.codigo AS turno, l.variedad_id, v.nombre AS variedad, "
            "l.area_ha, l.n_plantas, l.fecha_siembra, "
            "l.maceta, l.tipo_fibra, l.key_map, l.es_ficticio, l.es_sentinel, "
            "l.origen"
        ),
        "from": (
            "core.m_lote l JOIN core.m_modulo m ON m.modulo_id = l.modulo_id "
            "JOIN core.m_fundo f ON f.fundo_id = m.fundo_id "
            "JOIN core.m_empresa e ON e.empresa_id = f.empresa_id "
            "JOIN core.m_turno t ON t.turno_id = l.turno_id "
            "JOIN core.m_variedad v ON v.variedad_id = l.variedad_id"
        ),
        "search": "concat_ws(' ', e.nombre, f.codigo, m.codigo, l.codigo, t.codigo, v.nombre)",
        "where": (
            "NOT l.es_sentinel AND NOT l.es_ficticio AND NOT m.es_sentinel "
            "AND NOT f.es_sentinel AND NOT e.es_sentinel"
        ),
        "order": "e.nombre, f.codigo, m.codigo, l.codigo, l.lote_id",
    },
    "evaluadores": {
        "select": (
            "evaluador_id, dni, nombres, apellidos, codigo, zona, celular, "
            "inicio_labores, nacimiento, activo, en_maestro, creado_en"
        ),
        "from": "core.m_evaluador",
        "search": "concat_ws(' ', dni, nombres, apellidos, codigo, zona)",
        "where": "true",
        "order": "apellidos, nombres, evaluador_id",
    },
    "campanias": {
        "select": "campania_id, codigo, fecha_inicio, fecha_fin, origen_fechas",
        "from": "core.t_campania",
        "search": "concat_ws(' ', codigo, origen_fechas)",
        "where": "true",
        "order": "fecha_inicio DESC NULLS LAST, campania_id DESC",
    },
    "variedades": {
        "select": "variedad_id, nombre, es_sentinel",
        "from": "core.m_variedad",
        "search": "concat_ws(' ', nombre)",
        "where": "NOT es_sentinel",
        "order": "nombre, variedad_id",
    },
    "turnos": {
        "select": "turno_id, codigo, es_sentinel",
        "from": "core.m_turno",
        "search": "concat_ws(' ', codigo)",
        "where": "NOT es_sentinel",
        "order": "codigo, turno_id",
    },
    "muestreo": {
        "select": (
            "s.muestra_id, s.lote_id, e.nombre AS empresa, f.codigo AS fundo, "
            "m.codigo AS modulo, l.codigo AS lote, s.evaluacion, s.cortina, "
            "s.hilera, s.planta, s.muestras"
        ),
        "from": (
            "core.cfg_muestra_requerida s JOIN core.m_lote l "
            "ON l.lote_id = s.lote_id JOIN core.m_modulo m "
            "ON m.modulo_id = l.modulo_id JOIN core.m_fundo f "
            "ON f.fundo_id = m.fundo_id JOIN core.m_empresa e "
            "ON e.empresa_id = f.empresa_id"
        ),
        "search": "concat_ws(' ', e.nombre, f.codigo, m.codigo, l.codigo, s.evaluacion)",
        "where": "NOT l.es_sentinel AND NOT l.es_ficticio",
        "order": "e.nombre, f.codigo, m.codigo, l.codigo, s.evaluacion, s.muestra_id",
    },
}
