-- ============================================================================
-- 30_stg · 030 · Mapa de identidad materializado
--
-- Resolver el lote fila a fila costaría 94.236 llamadas solo en E01_Ramas. Pero las
-- combinaciones DISTINTAS de (fundo, módulo, lote) que aparecen en todas las fuentes juntas
-- son unos pocos miles, así que se resuelven una vez y los hechos hacen un JOIN normal.
--
-- El efecto secundario es más valioso que el rendimiento: el mapa es una tabla que se puede
-- mirar. Ver por qué una fila quedó huérfana deja de ser un ejercicio de depuración y pasa a
-- ser un SELECT.
-- ============================================================================

CREATE TABLE IF NOT EXISTS stg.mapa_lote (
    mapa_id      integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fundo_norm   text,
    modulo_norm  text,
    lote_norm    text,
    clave        text GENERATED ALWAYS AS (
                     coalesce(fundo_norm, '') || '|' ||
                     coalesce(modulo_norm, '') || '|' ||
                     coalesce(lote_norm, '')
                 ) STORED,
    lote_id      integer REFERENCES core.lote(lote_id),
    motivo       text,
    fuentes      text NOT NULL,
    filas        bigint NOT NULL DEFAULT 0,
    UNIQUE NULLS NOT DISTINCT (fundo_norm, modulo_norm, lote_norm)
);

CREATE UNIQUE INDEX IF NOT EXISTS mapa_lote_clave_idx ON stg.mapa_lote (clave);

COMMENT ON TABLE stg.mapa_lote IS
    'Cada combinación distinta de fundo, módulo y lote observada en el origen, con el lote al '
    'que se resuelve o el motivo por el que no. `fuentes` y `filas` dicen a cuántas filas '
    'afecta cada caso, que es lo que permite decidir si un huérfano importa.';
COMMENT ON COLUMN stg.mapa_lote.motivo IS
    'NULL cuando se resolvió. Si no: SIN_IDENTIFICADORES, LOTE_INEXISTENTE o LOTE_AMBIGUO.';

CREATE INDEX IF NOT EXISTS mapa_lote_busqueda_idx
    ON stg.mapa_lote (modulo_norm, lote_norm, fundo_norm);
CREATE INDEX IF NOT EXISTS mapa_lote_motivo_idx ON stg.mapa_lote (motivo)
    WHERE motivo IS NOT NULL;

-- Todas las combinaciones (fundo, módulo, lote) del origen, ya normalizadas.
CREATE OR REPLACE VIEW stg.v_combinaciones_ubicacion AS
SELECT fuente, fundo_norm, modulo_norm, lote_norm, count(*) AS filas
FROM (
    SELECT 'e01_ramas' AS fuente, stg.fn_norm_texto(fundo) AS fundo_norm,
           stg.fn_norm_modulo(modulo) AS modulo_norm, stg.fn_norm_lote(lote) AS lote_norm
    FROM raw.e01_ramas
    UNION ALL SELECT 'e02_conteo_flores', stg.fn_norm_texto(fundo),
           stg.fn_norm_modulo(modulo), stg.fn_norm_lote(lote) FROM raw.e02_conteo_flores
    UNION ALL SELECT 'e03_conteo_estados', stg.fn_norm_texto(fundo),
           stg.fn_norm_modulo(modulo), stg.fn_norm_lote(lote) FROM raw.e03_conteo_estados
    UNION ALL SELECT 'e04_brotes', stg.fn_norm_texto(fundo),
           stg.fn_norm_modulo(modulo), stg.fn_norm_lote(lote) FROM raw.e04_brotes
    -- E05 no trae fundo, solo módulo, turno y lote.
    UNION ALL SELECT 'e05_diametros_bayas', NULL,
           stg.fn_norm_modulo(modulo), stg.fn_norm_lote(lote) FROM raw.e05_diametros_bayas
    UNION ALL SELECT 'h00_volumen_campo', stg.fn_norm_texto(fundo),
           stg.fn_norm_modulo(modulo), stg.fn_norm_lote(lote) FROM raw.h00_volumen_campo
    UNION ALL SELECT 'h01_prod_historica', stg.fn_norm_texto(fundo),
           stg.fn_norm_modulo(modulo), stg.fn_norm_lote(lote) FROM raw.h01_prod_historica
    UNION ALL SELECT 'm_poda', stg.fn_norm_texto(fundo),
           stg.fn_norm_modulo(modulo), stg.fn_norm_lote(lote) FROM raw.m_poda
    UNION ALL SELECT 'm_n_muestra', stg.fn_norm_texto(fundo),
           stg.fn_norm_modulo(modulo), stg.fn_norm_lote(lote) FROM raw.m_n_muestra
    UNION ALL SELECT 'r09_forecast_semanal', stg.fn_norm_texto(fundo),
           stg.fn_norm_modulo(modulo), stg.fn_norm_lote(lote) FROM raw.r09_forecast_semanal
) t
GROUP BY fuente, fundo_norm, modulo_norm, lote_norm;

COMMENT ON VIEW stg.v_combinaciones_ubicacion IS
    'Combinaciones normalizadas de ubicación por fuente. H02_BDElifab no aparece porque su '
    'grano no llega a lote (N-2), y H05_Clima tampoco porque el clima no tiene ubicación.';

CREATE OR REPLACE PROCEDURE stg.sp_refrescar_mapa_lote()
LANGUAGE plpgsql
AS $$
DECLARE
    v_total     bigint;
    v_resueltos bigint;
    v_filas_ko  bigint;
BEGIN
    TRUNCATE stg.mapa_lote;

    INSERT INTO stg.mapa_lote (fundo_norm, modulo_norm, lote_norm, lote_id, motivo, fuentes, filas)
    SELECT c.fundo_norm,
           c.modulo_norm,
           c.lote_norm,
           (stg.fn_resolver_lote_detalle(c.fundo_norm, c.modulo_norm, c.lote_norm)).lote_id,
           (stg.fn_resolver_lote_detalle(c.fundo_norm, c.modulo_norm, c.lote_norm)).motivo,
           string_agg(DISTINCT c.fuente, ',' ORDER BY c.fuente),
           sum(c.filas)
    FROM stg.v_combinaciones_ubicacion c
    GROUP BY c.fundo_norm, c.modulo_norm, c.lote_norm;

    SELECT count(*), count(*) FILTER (WHERE lote_id IS NOT NULL),
           coalesce(sum(filas) FILTER (WHERE lote_id IS NULL), 0)
      INTO v_total, v_resueltos, v_filas_ko
    FROM stg.mapa_lote;

    RAISE NOTICE 'mapa_lote: % combinaciones, % resueltas (% por ciento), % filas de hechos sin lote',
        v_total, v_resueltos, round(100.0 * v_resueltos / nullif(v_total, 0), 1), v_filas_ko;
END;
$$;

COMMENT ON PROCEDURE stg.sp_refrescar_mapa_lote() IS
    'Recalcula el mapa. Hay que llamarlo después de cargar core.lote y cada vez que cambie el '
    'maestro o se añada un alias de fundo.';

-- Resolución lista para usar desde los hechos: JOIN por clave única, no llamada por fila.
CREATE OR REPLACE VIEW stg.v_resolucion AS
SELECT clave, fundo_norm, modulo_norm, lote_norm, lote_id, motivo
FROM stg.mapa_lote;
