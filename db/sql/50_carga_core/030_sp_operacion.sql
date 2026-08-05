-- ============================================================================
-- 50_carga_core · 030 · Carga de cosecha, clima, packing y forecast
-- ============================================================================

CREATE OR REPLACE PROCEDURE core.sp_cargar_cosecha()
LANGUAGE plpgsql
AS $$
DECLARE
    v_n integer; v_basura integer;
BEGIN
    TRUNCATE core.cosecha RESTART IDENTITY CASCADE;
    TRUNCATE qua.reconciliacion_cosecha;

    -- Las filas de subtotal de Excel: todos los identificadores vacíos y un valor grande en
    -- KG. Nunca aparecían al segmentar, solo en el total general, y por eso el total no
    -- cuadraba con la suma de las partes (H-06).
    -- El motivo viene del mapa de identidad, no se etiqueta a bulto: SIN_IDENTIFICADORES son
    -- las filas de subtotal (sin lote ni fecha) y LOTE_INEXISTENTE las que sí traen lote pero
    -- no está en el maestro vigente. Distinguirlos es lo que hace la cuarentena accionable.
    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'H00_VolumenCampo', 'core.cosecha',
           coalesce(v.motivo, 'SIN_IDENTIFICADORES'),
           CASE WHEN coalesce(v.motivo, 'SIN_IDENTIFICADORES') = 'SIN_IDENTIFICADORES'
                THEN 'H-06' ELSE 'N-3' END,
           CASE WHEN coalesce(v.motivo, 'SIN_IDENTIFICADORES') = 'SIN_IDENTIFICADORES'
                THEN 'Fila de subtotal de Excel: ' || round(v.kg::numeric, 2)
                     || ' kg sin lote ni fecha.'
                ELSE 'Cosecha de un lote que no está en el maestro vigente: '
                     || round(v.kg::numeric, 2) || ' kg.' END,
           to_jsonb(v)
    FROM stg.h00_cosecha v WHERE v.lote_id IS NULL OR v.fecha IS NULL;

    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'H01_ProdHistorica', 'core.cosecha',
           coalesce(v.motivo, 'SIN_IDENTIFICADORES'),
           CASE WHEN coalesce(v.motivo, 'SIN_IDENTIFICADORES') = 'SIN_IDENTIFICADORES'
                THEN 'H-06' ELSE 'N-3' END,
           CASE WHEN coalesce(v.motivo, 'SIN_IDENTIFICADORES') = 'SIN_IDENTIFICADORES'
                THEN 'Fila de subtotal de Excel: ' || round(v.kg::numeric, 2)
                     || ' kg sin lote ni fecha.'
                ELSE 'Cosecha de un lote que no está en el maestro vigente: '
                     || round(v.kg::numeric, 2) || ' kg.' END,
           to_jsonb(v)
    FROM stg.h01_cosecha v WHERE v.lote_id IS NULL OR v.fecha IS NULL;

    SELECT count(*) INTO v_basura FROM qua.rechazos
     WHERE tabla_destino = 'core.cosecha' AND motivo = 'SIN_IDENTIFICADORES';

    WITH h00 AS (
        SELECT h.lote_id, h.fecha, c.campania_id,
               sum(h.kg)::numeric(12,4) AS kg,
               count(*)::smallint       AS registros,
               max(va.variedad_id)      AS variedad_id
        FROM stg.h00_cosecha h
        JOIN core.campania c ON c.codigo = h.campania
        LEFT JOIN core.variedad_alias va ON va.alias_norm = stg.fn_norm_texto(h.variedad)
        WHERE h.lote_id IS NOT NULL AND h.fecha IS NOT NULL
        GROUP BY h.lote_id, h.fecha, c.campania_id
    ), h01 AS (
        SELECT h.lote_id, h.fecha, c.campania_id,
               sum(h.kg)::numeric(12,4) AS kg,
               max(h.pana)      AS pana,
               max(h.peso_baya) AS peso_baya,
               max(h.n_plantas) AS n_plantas,
               max(h.semana)    AS semana
        FROM stg.h01_cosecha h
        JOIN core.campania c ON c.codigo = h.campania
        WHERE h.lote_id IS NOT NULL AND h.fecha IS NOT NULL
        GROUP BY h.lote_id, h.fecha, c.campania_id
    )
    INSERT INTO core.cosecha (lote_id, fecha, campania_id, variedad_id, kg, pana, peso_baya,
                              n_plantas, semana, en_h00, en_h01, kg_h01, registros_h00)
    SELECT coalesce(a.lote_id, b.lote_id),
           coalesce(a.fecha, b.fecha),
           coalesce(a.campania_id, b.campania_id),
           -- ADR-0005: las 4 filas que solo existen en H01 (que nunca tuvo columna de
           -- variedad) no tienen a.variedad_id — apuntan al centinela en vez de quedar NULL
           -- (N-15). No es un fallo de resolución: el dato no existe en el origen.
           coalesce(a.variedad_id, (SELECT variedad_id FROM core.variedad WHERE es_sentinel)),
           -- H00 es la referencia de kilos (decisión D-3): conserva los registros completos
           -- en C2023 y C2024, donde H01 tiene 187 filas menos.
           coalesce(a.kg, b.kg),
           b.pana, b.peso_baya, b.n_plantas, b.semana,
           a.lote_id IS NOT NULL,
           b.lote_id IS NOT NULL,
           b.kg,
           coalesce(a.registros, 0)
    FROM h00 a
    FULL OUTER JOIN h01 b
      ON b.lote_id = a.lote_id AND b.fecha = a.fecha AND b.campania_id = a.campania_id;

    GET DIAGNOSTICS v_n = ROW_COUNT;

    -- H00 repite su clave natural en 34 grupos (151 filas de exceso). Se suman los kilos,
    -- que es lo que preserva el total de control, y el caso queda anotado (N-9).
    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'H00_VolumenCampo', 'core.cosecha', 'CLAVE_NATURAL_REPETIDA', 'N-9',
           'El mismo lote, fecha y campaña aparece ' || n || ' veces; los kilos se suman.',
           jsonb_build_object('lote_id', lote_id, 'fecha', fecha, 'campania', campania,
                              'veces', n, 'kg_total', kg)
    FROM (
        SELECT lote_id, fecha, campania, count(*) AS n, sum(kg) AS kg
        FROM stg.h00_cosecha WHERE lote_id IS NOT NULL AND fecha IS NOT NULL
        GROUP BY 1,2,3 HAVING count(*) > 1
    ) d;

    -- Reconciliación por campaña: la diferencia entre H00 y H01 no se oculta al unificarlas.
    INSERT INTO qua.reconciliacion_cosecha
        (campania, filas_h00, filas_h01, kg_h00, kg_h01, filas_solo_h00, filas_solo_h01)
    SELECT c.codigo,
           count(*) FILTER (WHERE co.en_h00),
           count(*) FILTER (WHERE co.en_h01),
           coalesce(sum(co.kg) FILTER (WHERE co.en_h00), 0),
           coalesce(sum(co.kg_h01) FILTER (WHERE co.en_h01), 0),
           count(*) FILTER (WHERE co.en_h00 AND NOT co.en_h01),
           count(*) FILTER (WHERE co.en_h01 AND NOT co.en_h00)
    FROM core.cosecha co
    JOIN core.campania c ON c.campania_id = co.campania_id
    GROUP BY c.codigo;

    RAISE NOTICE 'Cosecha: % filas unificadas, % filas de subtotal apartadas', v_n, v_basura;
END;
$$;

COMMENT ON PROCEDURE core.sp_cargar_cosecha() IS
    'Unifica H00 y H01 en un solo hecho (H-07), con H00 como referencia de kilos y H01 '
    'aportando paña, peso y plantas. La diferencia entre ambas queda registrada en '
    'qua.reconciliacion_cosecha, no se disuelve.';

-- ── Clima ───────────────────────────────────────────────────────────────────

CREATE OR REPLACE PROCEDURE core.sp_cargar_clima()
LANGUAGE plpgsql
AS $$
DECLARE v_n integer; v_dup integer;
BEGIN
    TRUNCATE core.clima;

    -- Un timestamp identifica una medición: no puede haber dos temperaturas para el mismo
    -- instante en la misma estación, y la tabla no tiene columna de estación. Los duplicados
    -- son exactos, así que da igual cuál se conserve (H-08).
    INSERT INTO core.clima
    SELECT DISTINCT ON (fecha_hora) *
    FROM stg.h05_clima
    WHERE fecha_hora IS NOT NULL
    ORDER BY fecha_hora;

    GET DIAGNOSTICS v_n = ROW_COUNT;

    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'H05_Clima', 'core.clima', 'TIMESTAMP_DUPLICADO', 'H-08',
           'El mismo instante registrado ' || n || ' veces por una recarga.',
           jsonb_build_object('fecha_hora', fecha_hora, 'veces', n)
    FROM (
        SELECT fecha_hora, count(*) AS n FROM stg.h05_clima
        WHERE fecha_hora IS NOT NULL GROUP BY 1 HAVING count(*) > 1
    ) d;

    GET DIAGNOSTICS v_dup = ROW_COUNT;
    RAISE NOTICE 'Clima: % mediciones, % instantes duplicados apartados', v_n, v_dup;
END;
$$;

-- ── Packing ─────────────────────────────────────────────────────────────────

CREATE OR REPLACE PROCEDURE core.sp_cargar_packing()
LANGUAGE plpgsql
AS $$
DECLARE v_n integer; v_merc integer;
BEGIN
    TRUNCATE core.packing RESTART IDENTITY CASCADE;
    TRUNCATE core.calibre RESTART IDENTITY CASCADE;
    TRUNCATE core.productor_equivalencia;

    -- Calibre como dimensión ORDENADA: en el origen era texto y se ordenaba alfabéticamente,
    -- con "10" antes que "2" (H-10). Los valores que no son un calibre conviven en la misma
    -- columna y se marcan en lugar de descartarse.
    --
    -- Deduplicación por fn_norm_texto: en el origen "Descarte" y "DESCARTE" son la MISMA
    -- palabra con dos grafías (13.503 filas combinadas) y deben ser una sola fila. "Defectos"
    -- y "-" NO se fusionan con "Descarte": son palabras distintas y no hay evidencia de que
    -- sean sinónimos — fusionarlas sería asumir una regla de negocio que nadie confirmó
    -- (ver ADR-0003 "nunca adivina"). La grafía canónica es la más frecuente de cada grupo,
    -- para que el catálogo muestre la forma que de verdad predomina en el origen.
    INSERT INTO core.calibre (etiqueta, mm, orden, es_descarte)
    SELECT etiqueta, mm,
           (row_number() OVER (ORDER BY mm NULLS LAST, etiqueta))::smallint,
           mm IS NULL
    FROM (
        SELECT DISTINCT ON (stg.fn_norm_texto(calibre))
               calibre AS etiqueta, stg.fn_calibre_mm(calibre) AS mm
        FROM (
            SELECT calibre, count(*) AS n
            FROM stg.h02_packing
            WHERE calibre IS NOT NULL AND calibre <> ''
            GROUP BY calibre
        ) f
        ORDER BY stg.fn_norm_texto(calibre), n DESC
    ) c;

    INSERT INTO core.productor_equivalencia (productor_norm, productor, empresa_id, origen)
    SELECT DISTINCT ON (stg.fn_norm_texto(e.productor))
           stg.fn_norm_texto(e.productor), btrim(e.productor), em.empresa_id,
           'M_EquivalenciaElifab'
    FROM raw.m_equivalencia_elifab e
    LEFT JOIN core.empresa em
           ON stg.fn_norm_texto(em.nombre) = stg.fn_norm_texto(e.empresa)
    WHERE e.productor IS NOT NULL;

    INSERT INTO core.packing (
        modulo_id, empresa_id, variedad_id, calibre_id, fecha_cosecha, fecha_proceso,
        semana, anio, turno_packing, clase, mercado, mercado_valido, recuento, peso_kg,
        porcentaje, nota_packing, calibrador, acdt, acidez, defecto, programa,
        contenedores_esperados, contenedores_volcados, hora_inicio, hora_fin)
    SELECT m.modulo_id,
           pe.empresa_id,
           va.variedad_id,
           ca.calibre_id,
           p.fecha_cosecha, p.fecha_proceso, p.semana, p.anio, p.turno_packing,
           p.clase, p.mercado, p.mercado_valido, p.recuento, p.peso_kg, p.porcentaje,
           p.nota_packing, p.calibrador, p.acdt, p.acidez, p.defecto, p.programa,
           p.contenedores_esperados, p.contenedores_volcados, p.hora_inicio, p.hora_fin
    FROM stg.h02_packing p
    -- El módulo por sí solo no identifica un módulo (M01-M04 están en dos fundos), pero
    -- packing no trae fundo: se toma el primero por orden estable y se documenta la
    -- limitación en lugar de fingir una precisión que el origen no tiene.
    LEFT JOIN LATERAL (
        SELECT mo.modulo_id FROM core.modulo mo
        WHERE mo.codigo = p.modulo ORDER BY mo.modulo_id LIMIT 1
    ) m ON true
    LEFT JOIN core.productor_equivalencia pe
           ON pe.productor_norm = stg.fn_norm_texto(p.productor)
    LEFT JOIN core.variedad_alias va ON va.alias_norm = stg.fn_norm_texto(p.variedad)
    -- Por texto normalizado, no exacto: si no, "Descarte" (minúscula) queda sin resolver
    -- una vez que el catálogo unificó "Descarte"/"DESCARTE" bajo una sola grafía canónica.
    LEFT JOIN core.calibre ca ON stg.fn_norm_texto(ca.etiqueta) = stg.fn_norm_texto(p.calibre)
    WHERE p.fecha_proceso IS NOT NULL;

    GET DIAGNOSTICS v_n = ROW_COUNT;

    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'H02_BDElifab', 'core.packing', 'MERCADO_INVALIDO', 'N-2',
           'Valor de mercado no reconocible: ' || n || ' filas.',
           jsonb_build_object('mercado', mercado, 'filas', n)
    FROM (
        SELECT mercado, count(*) AS n FROM stg.h02_packing
        WHERE NOT mercado_valido GROUP BY 1
    ) d;

    SELECT count(*) INTO v_merc FROM core.packing WHERE NOT mercado_valido;
    RAISE NOTICE 'Packing: % filas, % calibres, % sin mercado asignable',
        v_n, (SELECT count(*) FROM core.calibre), v_merc;
END;
$$;

-- ── Forecast ────────────────────────────────────────────────────────────────

CREATE OR REPLACE PROCEDURE core.sp_cargar_forecast()
LANGUAGE plpgsql
AS $$
DECLARE v_c integer; v_s integer;
BEGIN
    TRUNCATE core.forecast_semanal, core.forecast_campania RESTART IDENTITY CASCADE;
    TRUNCATE core.version_forecast RESTART IDENTITY CASCADE;

    -- La versión deja de ser un texto que hay que parsear en cada consulta: se descompone
    -- una vez. El origen lo hacía con Int(Right(Left(Version,3),2)), que falla en silencio
    -- si alguien escribe S5 y no distingue S27 de S27_v2.
    INSERT INTO core.version_forecast (sistema, codigo, semana_emision, iteracion, es_presupuesto)
    SELECT 'campania', codigo, NULL,
           (row_number() OVER (PARTITION BY regexp_replace(codigo, '_v\d+$', '') ORDER BY codigo))::smallint,
           codigo ILIKE 'presupuesto%'
    FROM (SELECT DISTINCT version AS codigo FROM stg.r08_forecast
          WHERE version IS NOT NULL AND version <> '') v;

    INSERT INTO core.version_forecast (sistema, codigo, semana_emision, iteracion, es_presupuesto)
    SELECT 'semanal', codigo,
           CASE WHEN codigo ~ '^S(\d{1,2})' THEN (regexp_match(codigo, '^S(\d{1,2})'))[1]::smallint END,
           -- La iteración se numera por orden dentro de la semana: así S27, S27_v2, S27_v3 y
           -- S27_vDR quedan distinguidas aunque el sufijo no sea un número.
           (row_number() OVER (
                PARTITION BY CASE WHEN codigo ~ '^S(\d{1,2})'
                                  THEN (regexp_match(codigo, '^S(\d{1,2})'))[1]::smallint END
                ORDER BY codigo))::smallint,
           false
    FROM (SELECT DISTINCT version AS codigo FROM stg.r09_forecast
          WHERE version IS NOT NULL AND version <> '') v;

    -- R08 tiene una fila de subtotal de Excel igual que H00 y H01, y con 25.433.998 kg es la
    -- mayor de todas: el 3,9% de la cifra de control de SUM([KG Exp]) que publica la auditoría
    -- (N-13). Queda fuera por no tener versión, y se registra para que conste.
    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'R08_Forecast_Campaña', 'core.forecast_campania', 'SIN_IDENTIFICADORES', 'N-13',
           'Fila de subtotal de Excel: ' || round(kg_exp::numeric, 2)
           || ' kg exportables sin versión, módulo, campaña ni semana.',
           to_jsonb(f)
    FROM stg.r08_forecast f
    WHERE f.version IS NULL OR f.version = '';

    -- ADR-0005 / N-15: antes estas 624 filas quedaban con modulo_id NULL y NUNCA se
    -- registraban en cuarentena — a diferencia de todos los demás hechos. Se registran
    -- primero (con el mismo criterio LEFT JOIN que usa la carga) y luego se cargan con el
    -- módulo apuntando al centinela.
    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'R08_Forecast_Campaña', 'core.forecast_campania', 'MODULO_INEXISTENTE', 'N-15',
           'El módulo del origen no resuelve contra el maestro vigente.', to_jsonb(f)
    FROM stg.r08_forecast f
    WHERE (f.version IS NOT NULL AND f.version <> '')
      AND NOT EXISTS (
        SELECT 1 FROM core.modulo mo
        LEFT JOIN core.fundo_alias af ON af.alias_norm = f.fundo_norm
        WHERE mo.codigo = f.modulo AND (af.fundo_id IS NULL OR mo.fundo_id = af.fundo_id)
      );

    INSERT INTO core.forecast_campania (version_id, modulo_id, empresa_id, turno_id,
        campania_id, anio, semana, kg_exp, kg_des, kg_con, frutos_exp,
        c12, c14, c16, c18, c19, c20, c22, c24, c26)
    SELECT ve.version_id,
           coalesce(m.modulo_id, (SELECT modulo_id FROM core.modulo WHERE es_sentinel)),
           al.empresa_id, t.turno_id, ca.campania_id,
           f.anio, f.semana, f.kg_exp, f.kg_des, f.kg_con, f.frutos_exp,
           f.c12, f.c14, f.c16, f.c18, f.c19, f.c20, f.c22, f.c24, f.c26
    FROM stg.r08_forecast f
    JOIN core.version_forecast ve ON ve.sistema = 'campania' AND ve.codigo = f.version
    -- empresa_norm viene de la columna Fundo, que en R08 contiene la empresa (N-5).
    LEFT JOIN core.fundo_alias al ON al.alias_norm = f.empresa_norm
    LEFT JOIN core.fundo_alias af ON af.alias_norm = f.fundo_norm
    LEFT JOIN LATERAL (
        SELECT mo.modulo_id FROM core.modulo mo
        WHERE mo.codigo = f.modulo
          AND (af.fundo_id IS NULL OR mo.fundo_id = af.fundo_id)
        ORDER BY mo.modulo_id LIMIT 1
    ) m ON true
    LEFT JOIN core.turno t ON t.codigo = f.turno
    LEFT JOIN core.campania ca ON ca.codigo = f.campania;

    GET DIAGNOSTICS v_c = ROW_COUNT;

    -- ADR-0005 / N-15: antes estas 23 filas se registraban en cuarentena Y quedaban en core
    -- con lote_id NULL a la vez — doble registro sin excluirlas, distinto del resto de los
    -- hechos. Ahora se registran igual, pero cargan con el lote apuntando al centinela.
    INSERT INTO qua.rechazos (tabla_origen, tabla_destino, motivo, hallazgo, detalle, fila)
    SELECT 'R09_Forecast_Semanal', 'core.forecast_semanal',
           coalesce(motivo, 'LOTE_INEXISTENTE'), 'H-01',
           'Proyección sin lote identificable.', to_jsonb(v)
    FROM stg.r09_forecast v WHERE lote_id IS NULL;

    INSERT INTO core.forecast_semanal (version_id, lote_id, campania_id, pasada, area_ha,
        fecha_cos_ant, fecha_cos, semana, frutos_por_planta, peso_baya, frutos_total,
        rendimiento, kg, dr)
    SELECT ve.version_id,
           coalesce(f.lote_id, (SELECT lote_id FROM core.lote WHERE es_sentinel)),
           ca.campania_id, f.pasada, f.area_ha,
           f.fecha_cos_ant, f.fecha_cos, f.semana, f.frutos_por_planta, f.peso_baya,
           f.frutos_total, f.rendimiento, f.kg, f.dr
    FROM stg.r09_forecast f
    JOIN core.version_forecast ve ON ve.sistema = 'semanal' AND ve.codigo = f.version
    LEFT JOIN core.campania ca ON ca.codigo = f.campania;

    GET DIAGNOSTICS v_s = ROW_COUNT;

    RAISE NOTICE 'Forecast: % de campaña (% al módulo centinela) y % semanales (% al lote centinela), en % versiones',
        v_c, (SELECT count(*) FROM core.forecast_campania fc JOIN core.modulo mo USING (modulo_id) WHERE mo.es_sentinel),
        v_s, (SELECT count(*) FROM core.forecast_semanal fs JOIN core.lote l USING (lote_id) WHERE l.es_sentinel),
        (SELECT count(*) FROM core.version_forecast);
END;
$$;
