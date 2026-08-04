-- ============================================================================
-- 40_qua · 010 · Cuarentena
--
-- La primera regla del plan de migración: **nada se descarta en silencio**. Toda fila que no
-- entra en `core` queda aquí con su contenido íntegro en jsonb y el motivo, de forma que si
-- Agronomía determina que era válida se pueda reprocesar sin volver al .accdb.
--
-- Los umbrales esperados están declarados en qua.umbral: si una carga rechaza más de lo
-- previsto, la validación lo señala en lugar de dejarlo pasar.
-- ============================================================================

CREATE TABLE IF NOT EXISTS qua.rechazos (
    rechazo_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tabla_origen    text NOT NULL,
    tabla_destino   text,
    motivo          text NOT NULL,
    hallazgo        text,
    detalle         text,
    fila            jsonb NOT NULL,
    cargado_en      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rechazos_motivo_idx ON qua.rechazos (tabla_origen, motivo);
CREATE INDEX IF NOT EXISTS rechazos_hallazgo_idx ON qua.rechazos (hallazgo);

COMMENT ON TABLE qua.rechazos IS
    'Filas que no entraron en core, con su contenido completo. `fila` conserva el registro '
    'íntegro para poder reprocesarlo; `hallazgo` lo enlaza con el defecto de la auditoría que '
    'lo explica.';
COMMENT ON COLUMN qua.rechazos.motivo IS
    'Motivo tipificado. Los previstos: SIN_IDENTIFICADORES, LOTE_INEXISTENTE, LOTE_AMBIGUO, '
    'DUPLICADO_EXACTO, CLAVE_NATURAL_REPETIDA, CONFLICTO_DIAMETRO_RAMA, '
    'EVALUADOR_SIN_MAESTRO, MERCADO_INVALIDO, TIMESTAMP_DUPLICADO.';

-- ── Umbrales esperados ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS qua.umbral (
    motivo          text PRIMARY KEY,
    tope            bigint NOT NULL,
    hallazgo        text,
    explicacion     text NOT NULL
);

COMMENT ON TABLE qua.umbral IS
    'Cuánta cuarentena es normal por motivo. Superar un tope no es un error de la migración: '
    'es señal de que hay un caso que la auditoría no vio y que hay que mirar antes de seguir.';

INSERT INTO qua.umbral (motivo, tope, hallazgo, explicacion) VALUES
    ('SIN_IDENTIFICADORES', 10, 'H-06',
     'Las 3 filas de subtotal de Excel (1 en H00, 2 en H01) con 1.925.995 kg entre ellas, más '
     '1 fila de E02 con el lote vacío. Si aparecen muchas más, hay filas basura que la '
     'auditoría no detectó.'),
    ('LOTE_INEXISTENTE', 900, 'N-3',
     'El par (módulo, lote) no está en el maestro vigente. Se esperan ~730 filas de ~280.000, '
     'concentradas en M04/L078-L080, M10/L191, M17/L042 y unos pocos más.'),
    ('LOTE_AMBIGUO', 50, 'N-4',
     'El par existe en las dos empresas y el fundo de la fila no permite distinguir. Son los 9 '
     'pares de M01-M04 que el maestro repite.'),
    ('DUPLICADO_EXACTO', 24000, 'H-03',
     'Filas idénticas por recarga: 23.141 en E01_Ramas y 2.175 en H05_Clima.'),
    ('CONFLICTO_DIAMETRO_RAMA', 5000, 'N-1',
     'La misma rama de la misma planta y fecha con dos diámetros distintos: 4.557 casos. No es '
     'una recarga, es un conflicto de captura que necesita criterio agronómico.'),
    ('CLAVE_NATURAL_REPETIDA', 1000, 'N-9',
     'La clave natural se repite con medidas distintas. E02_ConteoFlores no tiene ninguna clave '
     'única (161 conflictos con la mejor disponible) y H00 tiene 151 filas de exceso.'),
    ('EVALUADOR_SIN_MAESTRO', 10, 'H-09',
     'DNI que captura datos y no está en M_Evaluadores: 2 en E01_Ramas.'),
    ('MERCADO_INVALIDO', 45000, 'N-2',
     'H02_BDElifab tiene 41.428 filas con mercado ''0'' y 675 con ''-''. Se cargan marcadas, no '
     'se descartan: son un tercio de la tabla.'),
    ('TIMESTAMP_DUPLICADO', 2500, 'H-08',
     'Mediciones de clima con el mismo instante: 2.175 filas de exceso.'),
    ('DIAMETRO_FUERA_DE_RANGO', 60, 'N-13',
     'Diámetros físicamente imposibles: 29 ramas por encima de 50 mm (hasta 8.789) y 3 bayas '
     'por encima de 40 mm (hasta 13.381), casi con seguridad decimales perdidos. Se cargan '
     'igual porque las cifras de control de la auditoría los incluyen; excluirlos bajaría la '
     'media de rama de 10,89 a 10,62 y la de baya de 19,89 a 16,34.'),
    ('CONTEO_NEGATIVO', 10, 'N-13',
     'Conteos con valor negativo, imposibles: 1 fila en E02_ConteoFlores y 1 en E04_Brotes. '
     'Se convierten a NULL porque el origen ya usa NULL para lo no medido.')
ON CONFLICT (motivo) DO UPDATE
    SET tope = excluded.tope,
        hallazgo = excluded.hallazgo,
        explicacion = excluded.explicacion;

-- ── Reconciliación de cosecha ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS qua.reconciliacion_cosecha (
    campania        text NOT NULL,
    filas_h00       bigint NOT NULL,
    filas_h01       bigint NOT NULL,
    kg_h00          numeric(16,6) NOT NULL,
    kg_h01          numeric(16,6) NOT NULL,
    filas_solo_h00  bigint NOT NULL,
    filas_solo_h01  bigint NOT NULL,
    calculado_en    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (campania)
);

COMMENT ON TABLE qua.reconciliacion_cosecha IS
    'Diferencia entre H00_VolumenCampo y H01_ProdHistorica, campaña por campaña. Existe porque '
    'la migración unifica ambas en core.cosecha y esa diferencia no debe desaparecer sin dejar '
    'rastro (H-07): son 187 filas y 4.486,59 kg, concentradas en C2023 y C2024, excluidas por '
    'una regla que no está documentada en ninguna parte de la base.';

-- ── Vistas de estado ────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW qua.v_resumen AS
SELECT r.motivo,
       u.hallazgo,
       count(*)                        AS filas,
       u.tope,
       count(*) > u.tope               AS excede_umbral,
       string_agg(DISTINCT r.tabla_origen, ', ' ORDER BY r.tabla_origen) AS tablas,
       u.explicacion
FROM qua.rechazos r
LEFT JOIN qua.umbral u ON u.motivo = r.motivo
GROUP BY r.motivo, u.hallazgo, u.tope, u.explicacion
ORDER BY count(*) DESC;

COMMENT ON VIEW qua.v_resumen IS
    'Lo primero que hay que mirar tras una carga: cuánto se rechazó, por qué, y si excede lo '
    'previsto.';

CREATE OR REPLACE VIEW qua.v_alertas AS
SELECT motivo, hallazgo, filas, tope, filas - tope AS exceso, explicacion
FROM qua.v_resumen
WHERE excede_umbral
ORDER BY filas - tope DESC;

COMMENT ON VIEW qua.v_alertas IS
    'Motivos que superan su umbral. Si devuelve filas, hay que revisarlas antes de dar la '
    'migración por buena: significa que aparecieron casos que la auditoría no cubría.';
