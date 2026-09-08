"""Historial canónico; los prefijos m1..m7 siguen siendo contrato móvil, no columnas."""

HISTORY_SQL = """
WITH page AS (
 SELECT x.*, CASE x.tipo WHEN 'desarrollo' THEN 'baya' WHEN 'peso' THEN 'pesos'
                 ELSE x.tipo END AS module_key
 FROM core.ev_evaluacion x
 WHERE x.estado_registro='vigente' AND x.evaluador_id=%s
   AND (%s::text IS NULL OR CASE x.tipo WHEN 'desarrollo' THEN 'baya'
        WHEN 'peso' THEN 'pesos' ELSE x.tipo END=%s)
 ORDER BY COALESCE(x.captured_at,(x.fecha::timestamp+COALESCE(x.hora,time '00:00'))
          AT TIME ZONE 'America/Lima') DESC, x.evaluacion_id DESC
 LIMIT %s OFFSET %s
)
SELECT 'ev_evaluacion' AS source_table,x.evaluacion_id AS source_id,i.client_id,
 x.module_key,x.fecha,COALESCE(x.captured_at,
    (x.fecha::timestamp+COALESCE(x.hora,time '00:00')) AT TIME ZONE 'America/Lima') captured_at,
 x.evaluador_id,COALESCE(ev.dni,'') evaluador_dni,
 btrim(concat_ws(' ',ev.nombres,ev.apellidos)) evaluador,
 x.lote_id,COALESCE(f.codigo,'') fundo,COALESCE(m.codigo,'') modulo,
 COALESCE(l.codigo,'') lote,x.cortina,x.hilera,x.planta,
 (CASE x.tipo
 WHEN 'estadios' THEN jsonb_build_object('m1_e1',s.e1,'m1_e2',s.e2,'m1_e3',s.e3,
   'm1_e4',s.e4,'m1_e5',s.e5,'m1_total',COALESCE(s.total_origen,s.total_calculado))
 WHEN 'flores' THEN jsonb_build_object('m2_flores',c.n_flores,'m2_cuajos',c.cuajo,
   'm2_yp',c.yemas_por_abrir,'m2_ya',c.yemas_abiertas,'m2_ymuerta',c.yemas_muertas,
   'm2_brotes_tiernos',c.brotes_tiernos)
 WHEN 'brotes' THEN jsonb_build_object('m6_piso',b.piso,'m6_brotes',b.brotes,
   'm6_des1',b.des1_origen,'m6_des2',b.des2_origen,'m6_des3',b.des3_origen)
 WHEN 'ramas' THEN jsonb_build_object('m7_ram_lt5',r.ramas_menor5,'m7_ram_gt5',r.ramas_mayor5,
   'mediciones',COALESCE((SELECT jsonb_agg(jsonb_build_object(
       'numero_rama',o.numero_rama,'numero_medicion',o.numero_medicion,'diametro_mm',o.diametro_mm)
       ORDER BY o.numero_rama,o.numero_medicion)
       FROM core.ev_rama_observacion o WHERE o.evaluacion_id=x.evaluacion_id),'[]'::jsonb))
   || COALESCE((SELECT jsonb_object_agg('m7_diam'||CASE WHEN o.numero_rama<10 THEN '0' ELSE '' END
       ||o.numero_rama::text,to_jsonb(o.diametro_mm)) FROM core.ev_rama_observacion o
       WHERE o.evaluacion_id=x.evaluacion_id AND o.numero_medicion=1),'{}'::jsonb)
 ELSE jsonb_build_object('muestras',COALESCE((SELECT jsonb_agg(jsonb_build_object(
       'numero_muestra',o.numero_muestra,'numero_medicion',o.numero_medicion,
       'estado_codigo',o.estado_codigo,'diametro_mm',o.diametro_mm,'peso_g',o.peso_g,
       'deshoje',o.deshoje,'valor_x',o.valor_x,'observacion',o.observacion)
       ORDER BY o.numero_muestra,o.numero_medicion)
       FROM core.ev_fruto_observacion o WHERE o.evaluacion_id=x.evaluacion_id),'[]'::jsonb))
   || COALESCE((SELECT jsonb_object_agg(metric.k||CASE WHEN o.numero_muestra<10 THEN '0' ELSE '' END
       ||o.numero_muestra::text,metric.v)
       FROM core.ev_fruto_observacion o
       CROSS JOIN LATERAL (VALUES
          (CASE WHEN x.tipo='peso' THEN 'm5_diam' ELSE 'm4_diam' END,to_jsonb(o.diametro_mm)),
          ('m4_est',to_jsonb(o.estado_codigo)),('m5_peso',to_jsonb(o.peso_g))) metric(k,v)
       WHERE o.evaluacion_id=x.evaluacion_id AND o.numero_medicion=1 AND metric.v IS NOT NULL),
       '{}'::jsonb)
 END) - CASE WHEN x.origen='mobile' THEN 'muestras' ELSE '__sin_exclusion__' END AS valores
FROM page x
JOIN core.m_lote l ON l.lote_id=x.lote_id
JOIN core.m_evaluador ev ON ev.evaluador_id=x.evaluador_id
LEFT JOIN core.m_modulo m ON m.modulo_id=l.modulo_id
LEFT JOIN core.m_fundo f ON f.fundo_id=m.fundo_id
LEFT JOIN core.ev_estadios s ON s.evaluacion_id=x.evaluacion_id
LEFT JOIN core.ev_conteo_flores c ON c.evaluacion_id=x.evaluacion_id
LEFT JOIN core.ev_conteo_brotes b ON b.evaluacion_id=x.evaluacion_id
LEFT JOIN core.ev_conteo_ramas r ON r.evaluacion_id=x.evaluacion_id
LEFT JOIN core.api_evaluacion_ingesta i ON i.resource_table='ev_evaluacion'
 AND i.resource_id=x.evaluacion_id AND i.status='accepted'
ORDER BY captured_at DESC,x.evaluacion_id DESC
"""
