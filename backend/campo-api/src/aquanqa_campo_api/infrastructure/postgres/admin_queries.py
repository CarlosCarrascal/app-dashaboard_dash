"""SQL de lectura para el panel administrativo.

Las consultas están separadas del adaptador para que el contrato administrativo no termine
mezclado con la persistencia de la app móvil. No se interpolan filtros recibidos del cliente;
solo se inserta el ``ORDER BY`` elegido desde una lista blanca.
"""

from __future__ import annotations

EVALUATIONS_CTE = """
WITH evaluaciones AS (
    SELECT
        'ev_estados'::text AS source_table,
        x.estados_id::bigint AS source_id,
        'estadios'::text AS module_key,
        NULL::text AS tipo,
        'core'::text AS origen,
        x.fecha,
        (x.fecha::timestamp + COALESCE(x.hora, time '00:00'))
            AT TIME ZONE 'America/Lima' AS captured_at,
        x.lote_id,
        emp.empresa_id,
        f.fundo_id,
        mo.modulo_id,
        x.evaluador_id,
        emp.nombre AS empresa,
        f.codigo AS fundo,
        mo.codigo AS modulo,
        l.codigo AS lote,
        v.nombre AS variedad,
        btrim(concat_ws(' ', ev.nombres, ev.apellidos)) AS evaluador,
        COALESCE(ev.dni, '') AS evaluador_dni,
        jsonb_build_object(
            'e1', x.e1, 'e2', x.e2, 'e3', x.e3, 'e4', x.e4, 'e5', x.e5,
            'total', x.total, 'total_origen', x.total_origen,
            'cortina', x.cortina, 'hilera', x.hilera, 'planta', x.planta,
            'item', x.item, 'hora', x.hora
        ) AS detalle
    FROM core.ev_estados x
    JOIN core.m_lote l ON l.lote_id = x.lote_id
    JOIN core.m_modulo mo ON mo.modulo_id = l.modulo_id
    JOIN core.m_fundo f ON f.fundo_id = mo.fundo_id
    JOIN core.m_empresa emp ON emp.empresa_id = f.empresa_id
    LEFT JOIN core.m_variedad v ON v.variedad_id = l.variedad_id
    LEFT JOIN core.m_evaluador ev ON ev.evaluador_id = x.evaluador_id

    UNION ALL

    SELECT
        'ev_flores', x.flores_id::bigint, 'flores', NULL::text, 'core', x.fecha,
        (x.fecha::timestamp + COALESCE(x.hora, time '00:00'))
            AT TIME ZONE 'America/Lima',
        x.lote_id, emp.empresa_id, f.fundo_id, mo.modulo_id, x.evaluador_id,
        emp.nombre, f.codigo, mo.codigo, l.codigo, v.nombre,
        btrim(concat_ws(' ', ev.nombres, ev.apellidos)), COALESCE(ev.dni, ''),
        jsonb_build_object(
            'n_flores', x.n_flores, 'cuajo', x.cuajo,
            'yemas_abiertas', x.yemas_abiertas, 'yemas_por_abrir', x.yemas_por_abrir,
            'brotes_tiernos', x.brotes_tiernos, 'yemas_muertas', x.yemas_muertas,
            'cortina', x.cortina, 'hilera', x.hilera, 'planta', x.planta,
            'item', x.item, 'hora', x.hora
        )
    FROM core.ev_flores x
    JOIN core.m_lote l ON l.lote_id = x.lote_id
    JOIN core.m_modulo mo ON mo.modulo_id = l.modulo_id
    JOIN core.m_fundo f ON f.fundo_id = mo.fundo_id
    JOIN core.m_empresa emp ON emp.empresa_id = f.empresa_id
    LEFT JOIN core.m_variedad v ON v.variedad_id = l.variedad_id
    LEFT JOIN core.m_evaluador ev ON ev.evaluador_id = x.evaluador_id

    UNION ALL

    SELECT
        'ev_brotes', x.brotes_id::bigint, 'brotes', NULL::text, 'core', x.fecha,
        (x.fecha::timestamp + COALESCE(x.hora, time '00:00'))
            AT TIME ZONE 'America/Lima',
        x.lote_id, emp.empresa_id, f.fundo_id, mo.modulo_id, x.evaluador_id,
        emp.nombre, f.codigo, mo.codigo, l.codigo, v.nombre,
        btrim(concat_ws(' ', ev.nombres, ev.apellidos)), COALESCE(ev.dni, ''),
        jsonb_build_object(
            'piso', x.piso, 'brotes', x.brotes, 'des1', x.des1,
            'des2', x.des2, 'des3', x.des3,
            'cortina', x.cortina, 'hilera', x.hilera, 'planta', x.planta,
            'hora', x.hora
        )
    FROM core.ev_brotes x
    JOIN core.m_lote l ON l.lote_id = x.lote_id
    JOIN core.m_modulo mo ON mo.modulo_id = l.modulo_id
    JOIN core.m_fundo f ON f.fundo_id = mo.fundo_id
    JOIN core.m_empresa emp ON emp.empresa_id = f.empresa_id
    LEFT JOIN core.m_variedad v ON v.variedad_id = l.variedad_id
    LEFT JOIN core.m_evaluador ev ON ev.evaluador_id = x.evaluador_id

    UNION ALL

    SELECT
        'ev_baya_medicion', min(x.baya_medicion_id)::bigint,
        'baya', 'crecimiento', 'access', x.fecha,
        (x.fecha::timestamp) AT TIME ZONE 'America/Lima',
        x.lote_id, emp.empresa_id, f.fundo_id, mo.modulo_id, NULL::smallint,
        emp.nombre, f.codigo, mo.codigo, l.codigo, v.nombre,
        ''::text, ''::text,
        jsonb_build_object(
            'cantidad_muestras', count(*),
            'diametro_promedio', round(avg(x.diametro)::numeric, 2),
            'diametro_minimo', min(x.diametro),
            'diametro_maximo', max(x.diametro),
            'mediciones_sospechosas', count(*) FILTER (WHERE x.sospechoso),
            'cortina', x.cortina, 'hilera', x.hilera,
            'observaciones', jsonb_agg(jsonb_build_object(
                'source_id', x.baya_medicion_id,
                'numero_muestra', x.nro_muestra,
                'diametro_mm', x.diametro,
                'sospechoso', x.sospechoso
            ) ORDER BY x.nro_muestra, x.baya_medicion_id)
        )
    FROM core.ev_baya_medicion x
    JOIN core.m_lote l ON l.lote_id = x.lote_id
    JOIN core.m_modulo mo ON mo.modulo_id = l.modulo_id
    JOIN core.m_fundo f ON f.fundo_id = mo.fundo_id
    JOIN core.m_empresa emp ON emp.empresa_id = f.empresa_id
    LEFT JOIN core.m_variedad v ON v.variedad_id = l.variedad_id
    GROUP BY x.fecha, x.lote_id, x.cortina, x.hilera,
             emp.empresa_id, f.fundo_id, mo.modulo_id,
             emp.nombre, f.codigo, mo.codigo, l.codigo, v.nombre

    UNION ALL

    SELECT
        'ev_evaluacion_baya', x.evaluacion_baya_id,
        CASE WHEN x.tipo = 'peso' THEN 'pesos' ELSE 'baya' END,
        x.tipo, x.origen, x.fecha, x.creado_en,
        x.lote_id, emp.empresa_id, f.fundo_id, mo.modulo_id, x.evaluador_id,
        emp.nombre, f.codigo, mo.codigo, l.codigo, v.nombre,
        btrim(concat_ws(' ', ev.nombres, ev.apellidos)), COALESCE(ev.dni, ''),
        jsonb_build_object(
            'idempotency_key', x.idempotency_key,
            'source_snapshot_id', x.source_snapshot_id,
            'source_row_hash', x.source_row_hash,
            'observaciones', COALESCE((
                SELECT jsonb_agg(jsonb_build_object(
                    'numero_muestra', o.numero_muestra,
                    'numero_medicion', o.numero_medicion,
                    'estado_codigo', o.estado_codigo,
                    'diametro_mm', o.diametro_mm,
                    'peso_g', o.peso_g,
                    'deshoje', o.deshoje,
                    'valor_x', o.valor_x,
                    'observacion', o.observacion
                ) ORDER BY o.numero_muestra, o.numero_medicion)
                FROM core.ev_baya_observacion o
                WHERE o.evaluacion_baya_id = x.evaluacion_baya_id
            ), '[]'::jsonb)
        )
    FROM core.ev_evaluacion_baya x
    JOIN core.m_lote l ON l.lote_id = x.lote_id
    JOIN core.m_modulo mo ON mo.modulo_id = l.modulo_id
    JOIN core.m_fundo f ON f.fundo_id = mo.fundo_id
    JOIN core.m_empresa emp ON emp.empresa_id = f.empresa_id
    LEFT JOIN core.m_variedad v ON v.variedad_id = l.variedad_id
    LEFT JOIN core.m_evaluador ev ON ev.evaluador_id = x.evaluador_id

    UNION ALL

    SELECT
        'ev_evaluacion_ramas', x.evaluacion_ramas_id::bigint, 'ramas', NULL::text, 'core', x.fecha,
        x.creado_en, x.lote_id, emp.empresa_id, f.fundo_id, mo.modulo_id, x.evaluador_id,
        emp.nombre, f.codigo, mo.codigo, l.codigo, v.nombre,
        btrim(concat_ws(' ', ev.nombres, ev.apellidos)), COALESCE(ev.dni, ''),
        jsonb_build_object(
            'ramas_menor5', x.ramas_menor5, 'ramas_mayor5', x.ramas_mayor5,
            'mediciones', COALESCE((
                SELECT jsonb_agg(jsonb_build_object(
                    'nro_rama', r.nro_rama, 'diametro', r.diametro,
                    'sospechoso', r.sospechoso, 'id_origen', r.id_origen
                ) ORDER BY r.nro_rama, r.rama_medicion_id)
                FROM core.ev_rama_medicion r
                WHERE r.evaluacion_ramas_id = x.evaluacion_ramas_id
            ), '[]'::jsonb)
        )
    FROM core.ev_evaluacion_ramas x
    JOIN core.m_lote l ON l.lote_id = x.lote_id
    JOIN core.m_modulo mo ON mo.modulo_id = l.modulo_id
    JOIN core.m_fundo f ON f.fundo_id = mo.fundo_id
    JOIN core.m_empresa emp ON emp.empresa_id = f.empresa_id
    LEFT JOIN core.m_variedad v ON v.variedad_id = l.variedad_id
    LEFT JOIN core.m_evaluador ev ON ev.evaluador_id = x.evaluador_id
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
