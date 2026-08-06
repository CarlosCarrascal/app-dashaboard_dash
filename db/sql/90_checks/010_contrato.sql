-- ============================================================================
-- 90_checks · 010 · Contrato de aceptación
--
-- La migración se da por buena cuando esto pasa entero. Cinco grupos, y la distinción entre
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
--   reporting  · cifra de control de cada vista de compatibilidad (36 vistas, bloques 1-4,
--                tarea #33). Congela el conteo verificado el día en que se construyó cada
--                vista; una FALLA aquí no dice "esto está mal", dice "esto cambió desde
--                entonces" — recontar contra `core`/`fact` antes de decidir qué hacer.
--
-- Confundir "reproducir" con "core" es el error que haría parecer que la migración pierde
-- datos cuando lo que hace es apartarlos con constancia.
-- ============================================================================

-- El contrato se reconstruye entero en cada despliegue: es configuración, no datos, y así
-- añadir una columna no exige una migración.
DROP TABLE IF EXISTS qua.control;

CREATE TABLE qua.control (
    codigo        text PRIMARY KEY,
    grupo         text NOT NULL CHECK (grupo IN ('reproducir', 'cambiar', 'cero', 'core', 'reporting')),
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

-- N-23: cada tabla del origen que pierde filas tiene que explicar por qué. Esta comprobación
-- cuenta las tablas donde entraron menos filas de las que tenía Access Y no hay ni una sola
-- entrada en cuarentena que lo justifique. Es la garantía de que nada desaparece en silencio.
('cero.tabla_pierde_sin_rastro', 'cero', 'Tablas con filas perdidas y sin rastro en cuarentena',
 $q$SELECT count(*) FROM (VALUES
      ('E02_ConteoFlores', (SELECT count(*) FROM core.flores),            43490),
      ('E03_ConteoEstados',(SELECT count(*) FROM core.estados),           18714),
      ('E05_DiametrosBayas',(SELECT count(*) FROM core.baya_medicion),     4193),
      ('M_nMuestra',       (SELECT count(*) FROM core.muestra_requerida),   681),
      ('M_Poda',           (SELECT count(*) FROM core.poda),               2159)
    ) AS t(tabla, en_core, en_access)
    WHERE en_core < en_access
      AND NOT EXISTS (SELECT 1 FROM qua.rechazos r WHERE r.tabla_origen = t.tabla)$q$,
 0, 0, NULL, 'N-23',
 'M_nMuestra era la única que descartaba una fila sin registrarla; ya no.', 39),

-- N-16: el defecto era sumar el total del grupo una vez por fila. Si peso_kg vuelve a
-- apuntar a la columna equivocada, esta comprobación lo detecta al instante: 18,58 M kg es
-- coherente con los 32,39 M de cosecha; 789,60 M no lo es por un factor de 24.
('cero.peso_packing_inflado', 'cero', 'peso_kg de packing por encima de la cosecha real (N-16)',
 'SELECT CASE WHEN (SELECT sum(peso_kg) FROM core.packing)
                 > (SELECT sum(kg) FROM core.cosecha) THEN 1 ELSE 0 END',
 0, 0, NULL, 'N-16',
 'Lo empacado no puede superar lo cosechado. peso_kg_lote es un total repetido y NO se suma.', 39),

-- ── 4 · Estado de core (difiere del origen, y se explica) ───────────────────
-- `esperado` es el 879/6/29 del maestro vigente MÁS la fila centinela de ADR-0005 (+1 en
-- cada uno): sin sumarla, estos tres quedaban en FALLA por un desajuste del propio contrato,
-- no por la diferencia real con Access, que sigue intacta en `valor_access` y en la nota.
('core.lotes', 'core', 'Lotes del maestro vigente',
 'SELECT count(*) FROM core.lote', 880, 0, 860, 'N-4',
 'El maestro vigente tiene 19 lotes más y módulos nuevos M14-M24, más 1 fila centinela.', 40),

('core.fundos', 'core', 'Fundos físicos',
 'SELECT count(*) FROM core.fundo', 7, 0, 4, 'N-5',
 'Aqu Anqa 1 a 6 frente a los 4 nombres comerciales del origen, más 1 fila centinela.', 41),

('core.modulos', 'core', 'Combinaciones fundo x módulo',
 'SELECT count(*) FROM core.modulo', 30, 0, 23, 'N-4',
 'M01 a M04 pertenecen a dos fundos a la vez, más 1 fila centinela.', 42),

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
 'Las 4 filas que solo existen en H01, que nunca tuvo columna de variedad.', 55),

-- Las dos recuperaciones de la auditoría de mapeo: datos que antes se perdían en silencio.
('core.estados_con_hora', 'core', 'Estados con la hora de captura recuperada',
 'SELECT count(*) FROM core.estados WHERE hora IS NOT NULL',
 13224, 0, 13230, 'N-17',
 'La columna [F16] del origen perdió su encabezado y se descartaba como residuo; es la hora. '
 'En el origen son 13.230: las 6 que faltan están en las filas que van a cuarentena.', 56),

('core.packing_programa_rescatado', 'core', 'Packing con el programa rescatado de otra columna',
 'SELECT count(*) FROM stg.h02_packing WHERE programa_rescatado',
 390, 0, 0, 'N-19',
 'Traían el nombre del programa dentro de [Contenedores volcados]; antes se perdía al castear.', 57),

('core.packing_kg', 'core', 'Kilos empacados (la columna sumable, N-16)',
 'SELECT round(sum(peso_kg)) FROM core.packing',
 18582402, 100, NULL, 'N-16',
 'Antes sumaba 789,60 M kg porque usaba el total del grupo repetido en cada fila.', 58),

-- ── 5 · Vistas de compatibilidad de reporting (bloques 1-4, tarea #33) ──────
-- Hoy estas 36 vistas solo se habían verificado ad-hoc, fuera de `npm run validate`. La
-- cifra de `esperado` es el conteo real contra la base cargada el día en que se agregó este
-- check: no es una cifra publicada por Access ni por el plan de migración, es el punto de
-- referencia para detectar si una vista se rompe en un cambio futuro de `core`/`fact`.

-- Bloque 1 · flores y ramas (01xx + 02xx)
('reporting.0104_promflores', 'reporting', '0104_PromFlores',
 'SELECT count(*) FROM reporting."0104_PromFlores"', 9033, 0, NULL, NULL, NULL, 60),
('reporting.0105_acumflores', 'reporting', '0105_AcumFlores',
 'SELECT count(*) FROM reporting."0105_AcumFlores"', 858, 0, NULL, NULL, NULL, 61),
('reporting.0107_yemasab', 'reporting', '0107_YemasAb',
 'SELECT count(*) FROM reporting."0107_YemasAb"', 9033, 0, NULL, NULL, NULL, 62),
('reporting.0102_cantramas', 'reporting', '0102_CantRamas',
 'SELECT count(*) FROM reporting."0102_CantRamas"', 5384, 0, NULL, NULL, NULL, 63),
('reporting.0101_diametros', 'reporting', '0101_Diametros',
 'SELECT count(*) FROM reporting."0101_Diametros"', 71095, 0, NULL, NULL, NULL, 64),
('reporting.0108_diam', 'reporting', '0108_diam',
 'SELECT count(*) FROM reporting."0108_diam"', 71095, 0, NULL, NULL, NULL, 65),
('reporting.0106_rafloyem', 'reporting', '0106_RaFloYem',
 'SELECT count(*) FROM reporting."0106_RaFloYem"', 89881, 0, NULL, NULL, NULL, 66),
('reporting.01_flores_c2025', 'reporting', '01_Flores_C2025',
 'SELECT count(*) FROM reporting."01_Flores_C2025"', 9033, 0, 487368, 'H-05',
 'Access unía Sem contra M_Time.SEvConteo, semana contra día: explotaba ×54.', 67),
('reporting.0202_florestruno', 'reporting', '0202_FloresTurno',
 'SELECT count(*) FROM reporting."0202_FloresTurno"', 2648, 0, NULL, NULL, NULL, 68),

-- Bloque 2 · estados y brotes (03xx + 04xx)
('reporting.0302_conteoajustado', 'reporting', '0302_ConteoAjustado',
 'SELECT count(*) FROM reporting."0302_ConteoAjustado"', 2798, 0, NULL, NULL, NULL, 70),
('reporting.0303_conteoestados_turno', 'reporting', '0303_ConteoEstados_Turno',
 'SELECT count(*) FROM reporting."0303_ConteoEstados_Turno"', 13990, 0, NULL, NULL, NULL, 71),
('reporting.0304_conteoest_flo_turno', 'reporting', '0304_ConteoEst_Flo_Turno',
 'SELECT count(*) FROM reporting."0304_ConteoEst_Flo_Turno"', 16638, 0, NULL, NULL, NULL, 72),
('reporting.0306_frutosflores', 'reporting', '0306_FrutosFlores',
 'SELECT count(*) FROM reporting."0306_FrutosFlores"', 27741, 0, NULL, NULL, NULL, 73),
('reporting.0307_estadosflores', 'reporting', '0307_EstadosFlores',
 'SELECT count(*) FROM reporting."0307_EstadosFlores"', 16232, 0, NULL, NULL, NULL, 74),
('reporting.0401_estados_planta', 'reporting', '0401_Estados_planta',
 'SELECT count(*) FROM reporting."0401_Estados_planta"', 18708, 0, NULL, NULL, NULL, 75),
('reporting.0402_conteobrotes', 'reporting', '0402_ConteoBrotes',
 'SELECT count(*) FROM reporting."0402_ConteoBrotes"', 3385, 0, NULL, 'H-04',
 'Access referenciaba E04_ConteoBrotes, que no existe; el objeto real es E04_Brotes (caso 1).', 76),
('reporting.e', 'reporting', 'E',
 'SELECT count(*) FROM reporting."E"', 1938, 0, NULL, 'H-04',
 'Access pedía Actividad de E03_ConteoEstados, columna que solo existe en E01_Ramas (caso 4).', 77),

-- Bloque 3 · cosecha, clima y maestros (H0xxx + M_)
('reporting.h0100_resumen_kgcosecha', 'reporting', 'H0100_Resumen_kgCosecha',
 'SELECT count(*) FROM reporting."H0100_Resumen_kgCosecha"', 30536, 0, NULL, NULL, NULL, 80),
('reporting.h0102_produccionidiaria', 'reporting', 'H0102_Producciondiaria',
 'SELECT count(*) FROM reporting."H0102_Producciondiaria"', 30536, 0, NULL, NULL, NULL, 81),
('reporting.h0103_resmodulo', 'reporting', 'H0103_ResModulo',
 'SELECT count(*) FROM reporting."H0103_ResModulo"', 91, 0, NULL, NULL, NULL, 82),
('reporting.h0104_fechafincosecha', 'reporting', 'H0104_FechaFinCosecha',
 'SELECT count(*) FROM reporting."H0104_FechaFinCosecha"', 2328, 0, NULL, 'D-6',
 'Sin el filtro fijo Campaña=C2026 de la subconsulta de última paña.', 83),
('reporting.h0105_rendturno_pana', 'reporting', 'H0105_RendTurno_paña',
 'SELECT count(*) FROM reporting."H0105_RendTurno_paña"', 8025, 0, NULL, 'D-6',
 'Sin el filtro fijo Campaña=C2025; el join usa Fundo en vez de Fundo_pptom5 (N-21).', 84),
('reporting.h0201_pesobaya_elifab', 'reporting', 'H0201_PesoBaya_Elifab',
 'SELECT count(*) FROM reporting."H0201_PesoBaya_Elifab"', 17322, 0, NULL, NULL, NULL, 85),
('reporting.h0501_variablesclima', 'reporting', 'H0501_VariablesClima',
 'SELECT count(*) FROM reporting."H0501_VariablesClima"', 153413, 0, NULL, NULL, NULL, 86),
('reporting.h0502_temperatura_variacion', 'reporting', 'H0502_Temperatura_variacion',
 'SELECT count(*) FROM reporting."H0502_Temperatura_variacion"', 1603, 0, NULL, NULL, NULL, 87),
('reporting.m_edadcultivo', 'reporting', 'M_EdadCultivo',
 'SELECT count(*) FROM reporting."M_EdadCultivo"', 866, 0, NULL, NULL, NULL, 88),
('reporting.m_lote_turno', 'reporting', 'M_Lote_turno',
 'SELECT count(*) FROM reporting."M_Lote_turno"', 879, 0, NULL, NULL, NULL, 89),
('reporting.m_mod', 'reporting', 'M_Mod',
 'SELECT count(*) FROM reporting."M_Mod"', 29, 0, NULL, NULL, NULL, 90),
('reporting.tplantas', 'reporting', 'TPlantas',
 'SELECT count(*) FROM reporting."TPlantas"', 29, 0, NULL, NULL, NULL, 91),
('reporting.r0101_kgcosecha', 'reporting', 'R0101_KgCosecha',
 'SELECT count(*) FROM reporting."R0101_KgCosecha"', 30536, 0, NULL, 'H-04',
 'Access referenciaba R01_VolumenCampo, que no existe (caso 2).', 92),

-- Bloque 4 · forecast (R0xxx)
('reporting.r0801_forecast_campania_semmes', 'reporting', 'R0801_Forecast_Campaña_SemMes',
 'SELECT count(*) FROM reporting."R0801_Forecast_Campaña_SemMes"', 305142, 0, NULL, 'H-04',
 'Access pedía M_Time.CampProAra y .Trimestre, columnas que no existen (caso 5).', 93),
('reporting.r0801_rescampania', 'reporting', 'R0801_ResCampaña',
 'SELECT count(*) FROM reporting."R0801_ResCampaña"', 1182, 0, NULL, NULL, NULL, 94),
('reporting.r0802_resumenanio', 'reporting', 'R0802_ResumenAño',
 'SELECT count(*) FROM reporting."R0802_ResumenAño"', 1273, 0, NULL, 'H-04',
 'Access referenciaba R0901_ResCampaña, que no existe (caso 3).', 95),
('reporting.r0901_forecas_semac', 'reporting', 'R0901_Forecas_SemAc',
 'SELECT count(*) FROM reporting."R0901_Forecas_SemAc"', 9007, 0, NULL, NULL, NULL, 96),
('reporting.r0902_forecast_sem_vs_camp', 'reporting', 'R0902_Forecast_Sem_vs_Camp',
 'SELECT count(*) FROM reporting."R0902_Forecast_Sem_vs_Camp"', 103476, 0, NULL, 'H-04',
 'Access pedía R08_Forecast_Campaña.KG, columna que no existe (caso 6); usa KG Exp (D-1).', 97),
('reporting.r0903_forecast_frtstotal', 'reporting', 'R0903_Forecast_FrtsTotal',
 'SELECT count(*) FROM reporting."R0903_Forecast_FrtsTotal"', 48368, 0, NULL, NULL, NULL, 98),

-- Analítica (070): el panel módulo x semana. No reproduce nada de Access — es nuevo — así
-- que su cifra de control es el conteo verificado el día en que se construyó.
('reporting.panel_modulo_semana', 'reporting', 'Panel analítico módulo x semana',
 'SELECT count(*) FROM reporting.v_analitica_modulo_semana', 1183, 0, NULL, NULL,
 'Semana por año ISO y sin lotes ficticios L000.', 99),

('reporting.clima_diario', 'reporting', 'Clima colapsado a día, con GDD agronómico',
 'SELECT count(*) FROM reporting.v_clima_diario', 1603, 0, NULL, NULL,
 'Una fila por día con registro de la única estación del fundo.', 100),

('reporting.poda_modulo', 'reporting', 'Poda de referencia por módulo y campaña',
 'SELECT count(*) FROM reporting.v_poda_modulo', 62, 0, NULL, 'N-20',
 'Media ponderada por área; excluye las 54 filas sin fecha de poda.', 101),

-- El panel no puede inventar ni perder kilos: tiene que cuadrar con core.cosecha una vez
-- excluidos los lotes ficticios. La tolerancia es por el redondeo a 3 decimales por celda.
('cero.panel_kg_descuadra', 'cero', 'Diferencia de kg entre el panel y core.cosecha',
 'SELECT abs((SELECT sum(kg) FROM reporting.v_analitica_modulo_semana)
           - (SELECT sum(co.kg) FROM core.cosecha co JOIN core.lote l USING (lote_id)
              WHERE NOT l.es_ficticio AND NOT l.es_sentinel))',
 0, 0.5, NULL, NULL,
 'Si se descuadra, el panel dejó de excluir los L000 o duplicó una celda.', 40),

-- Guardián del defecto de semana: agrupar por (anio, semana) del calendario mezcla el año
-- calendario con la semana ISO y produce celdas que abarcan enero Y diciembre — verificado
-- en 428 filas y 309.190 kg dentro de (2025, semana 1). El panel usa anio_semana, que va
-- por año ISO; esta comprobación falla si alguien vuelve al par suelto.
('cero.panel_semana_contaminada', 'cero', 'Celdas del panel que abarcan más de 7 días',
 'SELECT count(*) FROM reporting.v_analitica_modulo_semana
  WHERE semana_hasta - semana_desde > 6 OR dias_en_semana <> 7',
 0, 0, NULL, 'H-05', NULL, 41),

-- N-25: `modulo.codigo` se repite entre fundos (M01 existe en Aqu Anqa 1 Y en Aqu Anqa
-- 2, con historias de poda y cosecha distintas). Si alguna vez el panel deja de exponer
-- modulo_id como clave, agrupar por `modulo` a solas mezclaría módulos físicos
-- distintos sin ningún error visible — este check lo detecta antes de que llegue a un
-- análisis o a un modelo.
('cero.panel_clave_no_unica', 'cero', 'Panel con más de una fila por módulo_id x campaña x semana',
 'SELECT count(*) - count(DISTINCT (modulo_id, campania, anio_semana))
  FROM reporting.v_analitica_modulo_semana',
 0, 0, NULL, 'N-25', NULL, 42),

-- Riego (fuente externa, cargada 2026-08-06): reconciliar core contra stg asegura que
-- ningún módulo se sumó dos veces ni se perdió al agregar por semana.
('reporting.riego_semanal', 'reporting', 'Riego semanal por módulo (fuente externa a Access)',
 'SELECT count(*) FROM core.riego_semanal', 1060, 0, NULL, NULL,
 '20 módulos x 53 semanas ISO de 2025 (incluida la semana de solape con 2026).', 102),

('cero.riego_agua_descuadra', 'cero', 'Diferencia de agua_m3 entre core.riego_semanal y stg',
 'SELECT abs((SELECT sum(agua_m3) FROM core.riego_semanal)
           - (SELECT sum(agua_m3) FROM stg.v_riego_diario))',
 0, 1, NULL, NULL,
 'Si se descuadra, la agregación semanal perdió o duplicó un día/turno.', 43),

('cero.riego_peso_incompleto', 'cero', 'Módulo local del riego cuyos pesos no suman 1',
 $q$SELECT count(*) FROM (
      SELECT archivo, modulo_local, sum(peso) AS total
      FROM stg.mapa_modulo_riego GROUP BY 1,2 HAVING abs(sum(peso) - 1) > 0.001
    ) d$q$,
 0, 0, NULL, 'D-7',
 'El reparto de M10A/M10B (u otro que se agregue) debe repartir el 100% del módulo, ni más ni menos.', 44);
