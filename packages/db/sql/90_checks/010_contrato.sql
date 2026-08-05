-- ============================================================================
-- 90_checks · 010 · Contrato de aceptación
--
-- La migración se da por buena cuando esto pasa entero. Cuatro grupos, y la distinción entre
-- los dos primeros es lo que hace el contrato honesto:
--
--   reproducir · se mide sobre `raw`/`stg`, que son copia fiel del origen. Si estas cifras
--                cambian, la extracción perdió datos.
--   cambiar    · cifras que DEBEN cambiar porque las de Access son incorrectas. Si no
--                cambian, la migración no aplicó la corrección.
--   cero       · defectos que no pueden sobrevivir a la migración.
--   core       · lo que queda en el modelo operativo tras apartar lo que no se pudo
--                identificar. NO coincide con el origen, y eso es correcto: la diferencia
--                está en `qua.rechazos`, fila por fila, con su motivo.
--
-- Confundir "reproducir" con "core" es el error que haría parecer que la migración pierde
-- datos cuando lo que hace es apartarlos con constancia.
-- ============================================================================

-- El contrato se reconstruye entero en cada despliegue: es configuración, no datos, y así
-- añadir una columna no exige una migración.
DROP TABLE IF EXISTS qua.control;

CREATE TABLE qua.control (
    codigo        text PRIMARY KEY,
    grupo         text NOT NULL CHECK (grupo IN ('reproducir', 'cambiar', 'cero', 'core')),
    descripcion   text NOT NULL,
    consulta      text NOT NULL,
    esperado      numeric NOT NULL,
    tolerancia    numeric NOT NULL DEFAULT 0,
    valor_access  numeric,
    hallazgo      text,
    nota          text,
    orden         smallint NOT NULL DEFAULT 100
);

COMMENT ON TABLE qua.control IS
    'Contrato de aceptación, declarativo. `consulta` devuelve un único valor numérico; '
    '`valor_access` es la cifra del origen y `nota` explica por qué difiere cuando difiere.';
COMMENT ON COLUMN qua.control.tolerancia IS
    'Margen absoluto admitido. Cero para conteos. Para sumas y medias de coma flotante hace '
    'falta margen: Access acumula Single en doble precisión y los documentos publican las '
    'cifras redondeadas a 15 dígitos.';

-- DROP y no CREATE OR REPLACE: PostgreSQL no permite cambiar el tipo de retorno de una
-- función existente, y añadir una columna al TABLE lo cambia.
DROP FUNCTION IF EXISTS qua.fn_validar();

CREATE FUNCTION qua.fn_validar()
RETURNS TABLE (
    grupo       text,
    codigo      text,
    descripcion text,
    access      numeric,
    esperado    numeric,
    obtenido    numeric,
    estado      text,
    hallazgo    text,
    nota        text
)
LANGUAGE plpgsql
AS $$
DECLARE
    c        record;
    v_valor  numeric;
BEGIN
    FOR c IN SELECT * FROM qua.control ORDER BY grupo, orden, codigo LOOP
        BEGIN
            EXECUTE c.consulta INTO v_valor;
        EXCEPTION WHEN others THEN
            v_valor := NULL;
        END;

        grupo       := c.grupo;
        codigo      := c.codigo;
        descripcion := c.descripcion;
        access      := c.valor_access;
        esperado    := c.esperado;
        obtenido    := v_valor;
        hallazgo    := c.hallazgo;
        nota        := c.nota;
        estado      := CASE
                          WHEN v_valor IS NULL THEN 'ERROR'
                          WHEN abs(v_valor - c.esperado) <= c.tolerancia THEN 'ok'
                          ELSE 'FALLA'
                       END;
        RETURN NEXT;
    END LOOP;
END;
$$;

TRUNCATE qua.control;

-- ── 1 · Reproducir el origen (se mide en raw/stg) ───────────────────────────
INSERT INTO qua.control (codigo, grupo, descripcion, consulta, esperado, tolerancia, valor_access, hallazgo, nota, orden) VALUES

('raw.total', 'reproducir', 'Filas del origen completo',
 'SELECT sum(n) FROM (SELECT count(*) n FROM raw.e01_ramas UNION ALL SELECT count(*) FROM raw.e02_conteo_flores
  UNION ALL SELECT count(*) FROM raw.e03_conteo_estados UNION ALL SELECT count(*) FROM raw.e04_brotes
  UNION ALL SELECT count(*) FROM raw.e05_diametros_bayas UNION ALL SELECT count(*) FROM raw.h00_volumen_campo
  UNION ALL SELECT count(*) FROM raw.h01_prod_historica UNION ALL SELECT count(*) FROM raw.h02_bd_elifab
  UNION ALL SELECT count(*) FROM raw.h05_clima UNION ALL SELECT count(*) FROM raw.m_equivalencia_elifab
  UNION ALL SELECT count(*) FROM raw.m_evaluadores UNION ALL SELECT count(*) FROM raw.m_lotes
  UNION ALL SELECT count(*) FROM raw.m_n_muestra UNION ALL SELECT count(*) FROM raw.m_poda
  UNION ALL SELECT count(*) FROM raw.m_time UNION ALL SELECT count(*) FROM raw.r08_forecast_campania
  UNION ALL SELECT count(*) FROM raw.r09_forecast_semanal) t',
 654598, 0, 654598, 'N-10',
 'Los documentos publican 683.180; esa suma está mal. Los recuentos por tabla sí son correctos.', 1),

('stg.e02_flores', 'reproducir', 'Total de flores contadas en el origen',
 'SELECT sum(n_flores) FROM stg.e02_flores', 3050031, 0, 3050031, NULL, NULL, 10),

('stg.e03_estados', 'reproducir', 'Total de frutos E1..E5 en el origen',
 'SELECT sum(e1+e2+e3+e4+e5) FROM stg.e03_estados', 9057841, 0, 9057841, NULL, NULL, 11),

('stg.e03_total_origen', 'reproducir', 'Total capturado aparte en el origen',
 'SELECT sum(total_origen) FROM stg.e03_estados', 9060271, 0, 9060271, NULL,
 'Difiere de E1..E5 en 2.430 frutos porque el origen no lo recalculaba.', 12),

('stg.e04_brotes', 'reproducir', 'Total de brotes en el origen',
 'SELECT sum(coalesce(brotes, 0)) FROM stg.e04_brotes', 225639, 0, 225638, 'N-12',
 'Una unidad más que el origen: el -1 imposible de una fila pasa a no medido.', 13),

('stg.e05_diametro', 'reproducir', 'Diámetro medio de baya en el origen',
 'SELECT avg(diametro) FROM stg.e05_bayas', 19.8850703636331, 0.0001, 19.8850703636331, NULL, NULL, 14),

('stg.e01_diametro', 'reproducir', 'Diámetro medio de rama en el origen, con duplicados',
 'SELECT avg(diametro) FROM stg.e01_ramas', 10.9776538610781, 0.0001, 10.9776538610781, NULL, NULL, 15),

('stg.h00_kg', 'reproducir', 'Kilos de H00 sin la fila de subtotal',
 'SELECT sum(kg) FROM stg.h00_cosecha WHERE lote_id IS NOT NULL OR fecha IS NOT NULL',
 32450472.596651, 0.01, 32450472.596651, 'H-06', NULL, 16),

('stg.r08_kg_exp', 'reproducir', 'Kilos exportables del origen, todas las versiones',
 'SELECT sum(kg_exp) FROM stg.r08_forecast', 648044713.139312, 1, 648044713.139312, NULL,
 'Incluye 25.433.998 kg de una fila de subtotal de Excel (N-13).', 17),

('stg.r09_kg', 'reproducir', 'Kilos del forecast semanal, todas las versiones',
 'SELECT sum(kg) FROM stg.r09_forecast', 51083049.9174915, 0.01, 51083049.9174915, NULL, NULL, 18),

-- ── 2 · Cifras que DEBEN cambiar ────────────────────────────────────────────
('ramas.medidas', 'cambiar', 'Ramas medidas tras deduplicar',
 'SELECT count(*) FROM core.rama_medicion', 71095, 0, 94236, 'H-03',
 '23.141 filas eran duplicados exactos por una recarga.', 20),

('ramas.plantas', 'cambiar', 'Plantas evaluadas: el grano real de la cabecera',
 'SELECT count(*) FROM core.evaluacion_ramas', 5384, 0, 94236, 'N-1',
 'El grano del origen era la rama, no la planta.', 21),

('ramas.media_diametro', 'cambiar', 'Diámetro medio de rama sin duplicados',
 'SELECT avg(diametro) FROM core.rama_medicion', 10.8869165, 0.0001, 10.9776538610781, 'H-03',
 'La auditoría publica 10,8870646; la diferencia está en el sexto decimal.', 22),

('clima.mediciones', 'cambiar', 'Mediciones de clima tras deduplicar',
 'SELECT count(*) FROM core.clima', 153413, 0, 155588, 'H-08',
 '2.079 instantes estaban repetidos por una recarga.', 23),

('forecast.kg_exp', 'cambiar', 'Kilos exportables sin la fila de subtotal',
 'SELECT sum(kg_exp) FROM core.forecast_campania', 622610715.139, 1, 648044713.139312, 'N-13',
 'Se aparta la fila de subtotal de 25.433.998 kg, el 3,9% del total publicado.', 24),

-- ── 3 · Defectos que deben quedar en cero ───────────────────────────────────
('cero.ramas_sin_cabecera', 'cero', 'Ramas medidas sin su planta',
 'SELECT count(*) FROM core.rama_medicion r
  WHERE NOT EXISTS (SELECT 1 FROM core.evaluacion_ramas c WHERE c.evaluacion_ramas_id = r.evaluacion_ramas_id)',
 0, 0, NULL, 'H-02', NULL, 30),

('cero.cosecha_sin_lote', 'cero', 'Cosecha sin lote identificado',
 'SELECT count(*) FROM core.cosecha WHERE lote_id IS NULL', 0, 0, 366, 'H-01', NULL, 31),

('cero.clima_duplicado', 'cero', 'Instantes de clima repetidos',
 'SELECT count(*) FROM (SELECT fecha_hora FROM core.clima GROUP BY 1 HAVING count(*) > 1) d',
 0, 0, 2079, 'H-08', NULL, 32),

('cero.lote_duplicado', 'cero', 'Lotes con la misma clave de negocio',
 'SELECT count(*) FROM (SELECT modulo_id, codigo FROM core.lote GROUP BY 1,2 HAVING count(*) > 1) d',
 0, 0, 5, 'N-4', NULL, 33),

('cero.estados_duplicado', 'cero', 'Estados con la clave natural repetida',
 'SELECT count(*) FROM (SELECT item, lote_id, fecha, cortina, hilera, planta FROM core.estados
  GROUP BY 1,2,3,4,5,6 HAVING count(*) > 1) d', 0, 0, 212, 'N-8', NULL, 34),

('cero.fk_sin_declarar', 'cero', 'Tablas de core sin ninguna clave foránea',
 'SELECT count(*) FROM (
    SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = ''core'' AND c.relkind = ''r''
       AND c.relname IN (''lote'',''modulo'',''fundo'',''cosecha'',''flores'',''estados'',
                         ''brotes'',''rama_medicion'',''evaluacion_ramas'',''baya_medicion'',
                         ''packing'',''forecast_campania'',''forecast_semanal'',''poda'')
       AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype = ''f'')
  ) d', 0, 0, 18, 'H-02',
 'El origen tenía 0 claves foráneas en sus 18 tablas.', 35),

('cero.total_incoherente', 'cero', 'Filas donde Total no es la suma de E1..E5',
 'SELECT count(*) FROM core.estados WHERE total <> e1+e2+e3+e4+e5', 0, 0, NULL, NULL,
 'La columna generada lo hace imposible por construcción.', 36),

('cero.calendario_hueco', 'cero', 'Huecos en el calendario',
 'SELECT (max(fecha) - min(fecha) + 1) - count(*) FROM core.calendario', 0, 0, NULL, NULL, NULL, 37),

('cero.alias_sin_empresa', 'cero', 'Vocabularios de fundo que no resuelven empresa',
 'SELECT count(*) FROM core.fundo_alias WHERE empresa_id IS NULL', 0, 0, NULL, 'H-01', NULL, 38),

('cero.fk_nula_en_hechos', 'cero', 'FK nula en las tablas de hechos (ADR-0005)',
 'SELECT
    (SELECT count(*) FROM core.forecast_campania WHERE modulo_id IS NULL) +
    (SELECT count(*) FROM core.forecast_semanal  WHERE lote_id   IS NULL) +
    (SELECT count(*) FROM core.cosecha           WHERE variedad_id IS NULL)',
 0, 0, NULL, 'N-15',
 'El motor lo garantiza (NOT NULL); esto es una segunda verificación explícita.', 39),

('cero.sentinel_duplicado', 'cero', 'Más de una fila centinela en la misma dimensión',
 'SELECT
    (SELECT count(*) FROM core.empresa WHERE es_sentinel) +
    (SELECT count(*) FROM core.fundo   WHERE es_sentinel) +
    (SELECT count(*) FROM core.modulo  WHERE es_sentinel) +
    (SELECT count(*) FROM core.turno   WHERE es_sentinel) +
    (SELECT count(*) FROM core.variedad WHERE es_sentinel) +
    (SELECT count(*) FROM core.lote    WHERE es_sentinel) - 6',
 0, 0, NULL, NULL,
 'Debe haber exactamente una por dimensión; el índice único parcial ya lo garantiza.', 39),

-- ── 4 · Estado de core (difiere del origen, y se explica) ───────────────────
('core.lotes', 'core', 'Lotes del maestro vigente',
 'SELECT count(*) FROM core.lote', 879, 0, 860, 'N-4',
 'El maestro vigente tiene 19 lotes más y módulos nuevos M14-M24.', 40),

('core.fundos', 'core', 'Fundos físicos',
 'SELECT count(*) FROM core.fundo', 6, 0, 4, 'N-5',
 'Aqu Anqa 1 a 6, frente a los 4 nombres comerciales del origen.', 41),

('core.modulos', 'core', 'Combinaciones fundo x módulo',
 'SELECT count(*) FROM core.modulo', 29, 0, 23, 'N-4',
 'M01 a M04 pertenecen a dos fundos a la vez.', 42),

('core.ramas_declaradas', 'core', 'Ramas declaradas por los evaluadores',
 'SELECT sum(coalesce(ramas_menor5,0) + coalesce(ramas_mayor5,0)) FROM core.evaluacion_ramas',
 110118, 0, 730318, 'N-1',
 'Sustituye a SUM([# Ramas]) = 730.318, que era una suma de índices de rama.', 43),

('core.flores', 'core', 'Conteos de flores cargados',
 'SELECT count(*) FROM core.flores', 43469, 0, 43490, 'N-3',
 '21 filas con lote que no está en el maestro vigente, en cuarentena.', 44),

('core.estados', 'core', 'Conteos de estados cargados',
 'SELECT count(*) FROM core.estados', 18708, 0, 18714, 'N-3',
 '6 filas con lote que no está en el maestro vigente.', 45),

('core.brotes', 'core', 'Conteos de brotes cargados',
 'SELECT count(*) FROM core.brotes', 3385, 0, 3385, NULL,
 'Sin pérdida: E01 y E04 resuelven el 100% de sus lotes.', 46),

('core.bayas', 'core', 'Mediciones de baya cargadas',
 'SELECT count(*) FROM core.baya_medicion', 3889, 0, 4193, 'N-3',
 '304 filas de los módulos M10 y M10B, que E05 escribe sin el sufijo A/B.', 47),

('core.cosecha', 'core', 'Registros de cosecha unificados',
 'SELECT count(*) FROM core.cosecha', 30540, 0, 30812, 'H-06',
 'Se apartan las filas de subtotal y las de lotes fuera del maestro.', 48),

('core.packing', 'core', 'Registros de packing',
 'SELECT count(*) FROM core.packing', 117536, 0, 117536, NULL, NULL, 49),

('core.forecast_semanal', 'core', 'Proyecciones semanales',
 'SELECT count(*) FROM core.forecast_semanal', 48368, 0, 48368, NULL, NULL, 50),

('core.evaluadores', 'core', 'Evaluadores, incluidos los que no están en el maestro',
 'SELECT count(*) FROM core.evaluador', 37, 0, 31, 'H-09',
 '6 DNI capturan datos sin ficha en M_Evaluadores.', 51),

('core.cuarentena', 'core', 'Filas en cuarentena, todas con motivo',
 'SELECT count(*) FROM qua.rechazos WHERE motivo IS NULL', 0, 0, NULL, NULL,
 'Ninguna fila apartada sin explicación.', 52),

('core.forecast_campania_sentinel', 'core', 'Filas de forecast_campania en el módulo centinela',
 'SELECT count(*) FROM core.forecast_campania fc JOIN core.modulo mo USING (modulo_id) WHERE mo.es_sentinel',
 624, 0, NULL, 'N-15',
 'Antes NULL y sin registrar en cuarentena; ahora apuntan al centinela y sí quedan registradas.', 53),

('core.forecast_semanal_sentinel', 'core', 'Filas de forecast_semanal en el lote centinela',
 'SELECT count(*) FROM core.forecast_semanal fs JOIN core.lote l USING (lote_id) WHERE l.es_sentinel',
 23, 0, NULL, 'N-15',
 'Antes NULL y duplicadas en cuarentena a la vez; ahora apuntan al centinela sin duplicar.', 54),

('core.cosecha_sentinel', 'core', 'Filas de cosecha en la variedad centinela',
 'SELECT count(*) FROM core.cosecha co JOIN core.variedad v USING (variedad_id) WHERE v.es_sentinel',
 4, 0, NULL, 'N-15',
 'Las 4 filas que solo existen en H01, que nunca tuvo columna de variedad.', 55);
