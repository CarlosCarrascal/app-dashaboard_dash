-- ============================================================================
-- 20_core · 020 · Tiempo: campaña, calendario, semana de evaluación, poda
--
-- Aquí se corrigen dos defectos de la dimensión de tiempo del origen:
--
--   H-04 caso 5 · a M_Time le faltan `Trimestre` y `CampProAra`, y dos consultas las piden.
--                 El trimestre es trivial; la campaña productiva necesita fechas de corte.
--   H-05        · la explosión x54 de 01_Flores_C2025 sale de unir una tabla semanal contra
--                 M_Time, que tiene grano diario. La solución estructural es que exista una
--                 dimensión de grano semanal a la que unirse.
-- ============================================================================

CREATE TABLE IF NOT EXISTS core.campania (
    campania_id     smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo          text NOT NULL UNIQUE,
    fecha_inicio    date,
    fecha_fin       date,
    origen_fechas   text NOT NULL DEFAULT 'derivado'
                    CHECK (origen_fechas IN ('derivado', 'declarado')),
    CHECK (fecha_fin IS NULL OR fecha_inicio IS NULL OR fecha_fin >= fecha_inicio)
);

COMMENT ON TABLE core.campania IS
    'Ciclo productivo anual: C2022 a C2026. Una campaña NO coincide con el año calendario '
    '(C2025 abarca meses de 2025 y 2026), y esa es la causa de que H0103_ResModulo parta los '
    'totales al agrupar por año y campaña a la vez.';
COMMENT ON COLUMN core.campania.origen_fechas IS
    'derivado = las fechas salen del rango real observado en los hechos, que es el supuesto '
    'en uso mientras Planeamiento no entregue el calendario oficial (decisión D-2, ver '
    'core.config_decision). declarado = fechas oficiales.';

CREATE TABLE IF NOT EXISTS core.calendario (
    fecha               date PRIMARY KEY,
    anio                smallint NOT NULL,
    mes                 smallint NOT NULL CHECK (mes BETWEEN 1 AND 12),
    dia                 smallint NOT NULL CHECK (dia BETWEEN 1 AND 31),
    trimestre           smallint NOT NULL CHECK (trimestre BETWEEN 1 AND 4),
    semana              smallint NOT NULL CHECK (semana BETWEEN 1 AND 53),
    dia_semana          smallint NOT NULL CHECK (dia_semana BETWEEN 1 AND 7),
    mes_abrev           text NOT NULL,
    anio_mes            text NOT NULL,
    anio_semana         text NOT NULL,
    sem_ev_conteo       smallint,
    mes_sem             text,
    campanias_activas   smallint NOT NULL DEFAULT 0
);

COMMENT ON TABLE core.calendario IS
    'Dimensión de tiempo con grano de día, del 2022-03-01 al 2027-12-31. Reemplaza a M_Time y '
    'además a la tabla BD_Calendario que ambos informes de Power BI construyen por su cuenta '
    'en DAX: trae ya el trimestre, anio_semana y anio_mes que esa tabla aportaba, para que el '
    'reapuntado no pierda nada.';
COMMENT ON COLUMN core.calendario.sem_ev_conteo IS
    'Semana de evaluación de conteo, desplazada respecto a la semana calendario porque el '
    'corte agronómico no cae en domingo: difieren en 527 de los 1.224 días poblados. Nunca '
    'unir una tabla semanal contra esta columna — para eso está core.semana_evaluacion.';
COMMENT ON COLUMN core.calendario.campanias_activas IS
    'Cuántas campañas tienen actividad ese día. Es informativo, y hay una razón de peso para '
    'que NO exista una columna campania_id: las campañas SE SOLAPAN. Solo en cosecha, C2023 '
    'llega al 2024-02-16 y C2024 arranca el 2023-12-18 — 61 días compartidos; contando poda y '
    'forecast el solape sube a 354 días (hallazgo N-11). Una fecha no determina la campaña, '
    'porque dos lotes podados en momentos distintos están en campañas distintas el mismo día. '
    'La campaña se resuelve por lote con core.fn_campania_de_lote().';

CREATE TABLE IF NOT EXISTS core.semana_evaluacion (
    anio            smallint NOT NULL,
    sem_ev_conteo   smallint NOT NULL,
    fecha_inicio    date NOT NULL,
    fecha_fin       date NOT NULL,
    dias            smallint NOT NULL,
    PRIMARY KEY (anio, sem_ev_conteo),
    CHECK (fecha_fin >= fecha_inicio)
);

COMMENT ON TABLE core.semana_evaluacion IS
    'Dimensión de grano SEMANAL, una fila por (año, semana de evaluación). Existe para que '
    'ninguna consulta futura vuelva a unir una tabla semanal contra una tabla de días: eso es '
    'lo que multiplicó por 54 las filas de 01_Flores_C2025 (H-05). Unir contra esto, nunca '
    'contra core.calendario.sem_ev_conteo.';

CREATE TABLE IF NOT EXISTS core.poda (
    poda_id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lote_id         integer NOT NULL REFERENCES core.lote(lote_id),
    campania_id     smallint NOT NULL REFERENCES core.campania(campania_id),
    fecha_inicio    date,
    fecha_siembra   date,
    area_ha         numeric(10,4),
    UNIQUE (lote_id, campania_id)
);

COMMENT ON TABLE core.poda IS
    'Poda por lote y campaña. fecha_inicio es el origen del tiempo agronómico: en arándano el '
    'desarrollo se mide en días desde la poda, no en fechas absolutas, porque dos lotes '
    'podados con un mes de diferencia están en estados fenológicos distintos el mismo día del '
    'calendario. 7 de las 40 consultas dependen de esto.';
COMMENT ON COLUMN core.poda.fecha_siembra IS
    'Duplica core.lote.fecha_siembra en el origen (M_Poda.FSiembra), con riesgo de '
    'divergencia. Se conserva para poder auditar la diferencia.';

CREATE INDEX IF NOT EXISTS poda_lote_idx ON core.poda (lote_id);
CREATE INDEX IF NOT EXISTS calendario_sem_ev_idx ON core.calendario (anio, sem_ev_conteo);

-- ── Campaña de un hecho ─────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION core.fn_campania_de_lote(p_lote_id integer, p_fecha date)
RETURNS smallint
LANGUAGE sql STABLE PARALLEL SAFE
AS $$
    -- La campaña de un lote en una fecha es la de su poda más reciente anterior a esa fecha.
    -- Es la única forma correcta de derivarla, porque las campañas se solapan en el
    -- calendario pero NO dentro de un mismo lote: un lote solo está en una campaña a la vez
    -- (N-11).
    SELECT p.campania_id
    FROM core.poda p
    WHERE p.lote_id = p_lote_id
      AND p.fecha_inicio IS NOT NULL
      AND p.fecha_inicio <= p_fecha
    ORDER BY p.fecha_inicio DESC
    LIMIT 1;
$$;

COMMENT ON FUNCTION core.fn_campania_de_lote(integer, date) IS
    'Campaña productiva de un lote en una fecha, derivada de su poda. Responde a la columna '
    'CampProAra que M_Time no tiene y que rompe R0801_Forecast_Campaña_SemMes (H-04 caso 5) '
    '— pero por lote, que es como el dato tiene sentido, no por fecha.';
