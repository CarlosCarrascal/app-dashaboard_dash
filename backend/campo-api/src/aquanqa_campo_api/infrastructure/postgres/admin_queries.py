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
   x.tipo,x.origen,x.fecha,
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
