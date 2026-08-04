-- ============================================================================
-- 20_core · 050 · Operación: cosecha, packing, clima y forecast
--
-- Correcciones que se declaran aquí:
--
--   H-06 · NOT NULL en las dimensiones de cosecha bloquea las 3 filas de subtotal de Excel
--          que aportaban 1.925.995 kg fantasma — kilos que solo aparecían en el total general
--          y desaparecían en cuanto el tablero segmentaba por cualquier cosa.
--   H-07 · una sola entidad de cosecha, con el origen registrado, en lugar de dos tablas con
--          reglas propias que difieren en 187 filas sin que nada lo explique.
--   H-08 · la clave primaria del clima es el timestamp. Un instante identifica una medición:
--          no puede haber dos temperaturas para el mismo momento en la misma estación.
--   H-10 · packing tipado, con los 5 pares de columnas duplicadas consolidados.
--   N-2  · packing referencia MÓDULO, no lote: su [Lote] es una nota de packing.
--   N-5  · forecast con las columnas de fundo desinvertidas y la versión descompuesta.
-- ============================================================================

-- ── Cosecha ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.cosecha (
    cosecha_id      integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lote_id         integer NOT NULL REFERENCES core.lote(lote_id),
    fecha           date NOT NULL,
    campania_id     smallint NOT NULL REFERENCES core.campania(campania_id),
    variedad_id     smallint REFERENCES core.variedad(variedad_id),
    kg              numeric(12,4) NOT NULL CHECK (kg >= 0),
    pana            smallint CHECK (pana > 0),
    peso_baya       numeric(8,4) CHECK (peso_baya > 0),
    n_plantas       integer,
    semana          smallint,
    en_h00          boolean NOT NULL DEFAULT false,
    en_h01          boolean NOT NULL DEFAULT false,
    kg_h01          numeric(12,4),
    registros_h00   smallint NOT NULL DEFAULT 0,
    -- La paña queda FUERA de la clave: H00, que es la referencia de kilos, no la trae, y
    -- solo aparece en H01. Meterla en la clave impediría reconciliar ambas fuentes.
    UNIQUE (lote_id, fecha, campania_id)
);

COMMENT ON TABLE core.cosecha IS
    'Kilos cosechados por lote y fecha: el hecho primario de producción. Unifica H00 y H01, que '
    'registran la misma cosecha con reglas distintas (H-07). La referencia de KG es H00, que '
    'conserva los registros completos en C2023 y C2024 — H01 tiene 187 filas menos, y las que '
    'le faltan promedian 24 kg frente a los ~1.060 kg del promedio general, así que son '
    'registros de volumen muy pequeño excluidos por una regla que no está documentada en '
    'ninguna parte porque se aplicaba en la carga, externa a Access.';
COMMENT ON COLUMN core.cosecha.fecha IS
    'NOT NULL. Es lo que bloquea las 3 filas de subtotal de Excel de H-06: tenían todos los '
    'identificadores vacíos y 1.925.995 kg entre las tres.';
COMMENT ON COLUMN core.cosecha.pana IS
    'Número de pasada de cosecha. En arándano no se cosecha de una vez: se pasa varias veces '
    'recogiendo lo maduro, y el rendimiento por pasada decide cuántas vale la pena hacer.';
COMMENT ON COLUMN core.cosecha.en_h00 IS
    'La fila existe en H00_VolumenCampo. Junto con en_h01 hace la reconciliación auditable en '
    'lugar de oculta.';
COMMENT ON COLUMN core.cosecha.kg_h01 IS
    'Los kilos según H01, cuando difieren de los de H00. Permite cuantificar el desfase por '
    'campaña sin mantener dos tablas de hechos.';
COMMENT ON COLUMN core.cosecha.registros_h00 IS
    'Cuántas filas de H00 se agregaron en esta. Normalmente 1; hay 34 grupos donde el origen '
    'repite la clave y suma 151 filas de exceso (N-9). Se suman los kilos, que es lo que '
    'preserva el total de control, y el caso queda registrado en cuarentena.';

CREATE INDEX IF NOT EXISTS cosecha_lote_fecha_idx ON core.cosecha (lote_id, fecha);
CREATE INDEX IF NOT EXISTS cosecha_campania_idx ON core.cosecha (campania_id);

-- ── Clima ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.clima (
    fecha_hora          timestamp PRIMARY KEY,
    barometro           numeric(8,2),
    temp                numeric(6,2),
    temp_alta           numeric(6,2),
    temp_baja           numeric(6,2),
    humedad             numeric(6,2),
    punto_rocio         numeric(6,2),
    bulbo_humedo        numeric(6,2),
    vel_viento          numeric(6,2),
    direc_viento        text,
    viento_corriente    numeric(6,2),
    alta_vel_viento     numeric(6,2),
    alta_direc_viento   text,
    viento_frio         numeric(6,2),
    indice_calor        numeric(6,2),
    thw_index           numeric(6,2),
    tshw_index          numeric(6,2),
    lluvia              numeric(8,3),
    tasa_lluvia         numeric(8,3),
    rad_sol             numeric(10,3),
    ener_solar          numeric(10,3),
    rad_sol_alta        numeric(10,3),
    et_mm               numeric(8,3),
    dg_calentamiento    numeric(8,3),
    dg_enfriamiento     numeric(8,3)
);

COMMENT ON TABLE core.clima IS
    'Registro de la estación meteorológica: 153.413 mediciones tras deduplicar las 155.588 del '
    'origen. La PK es el timestamp, y eso ES la corrección de H-08: un instante identifica una '
    'medición, no puede haber dos temperaturas para el mismo momento. Antes había 2.079 grupos '
    'duplicados por una recarga.';
COMMENT ON COLUMN core.clima.temp_alta IS
    'En el origen se llamaba TembAlta, con un typo. Corregido aquí.';
COMMENT ON COLUMN core.clima.lluvia IS
    'Precipitación. Era el caso más grave de H-08: la lluvia de los momentos duplicados se '
    'contaba dos veces y sobrestimaba el acumulado, que es lo que alimenta las decisiones de '
    'riego y el manejo de enfermedad fúngica. Un acumulado sobrestimado induce a regar de menos.';
COMMENT ON COLUMN core.clima.dg_calentamiento IS
    'Grados-día. Con et_mm son las variables de mayor valor agronómico de la tabla: predicen la '
    'velocidad de desarrollo del fruto y la necesidad de riego.';

-- ── Packing ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.calibre (
    calibre_id      smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    etiqueta        text NOT NULL UNIQUE,
    mm              numeric(5,2),
    orden           smallint NOT NULL,
    es_descarte     boolean NOT NULL DEFAULT false
);

COMMENT ON TABLE core.calibre IS
    'Calibre comercial como dimensión ORDENADA. En el origen era texto, así que se ordenaba '
    'alfabéticamente y "10" iba antes que "2" (H-10). El calibre determina el mercado de '
    'destino y por tanto el precio.';
COMMENT ON COLUMN core.calibre.orden IS
    'Posición en la escala. Es lo que permite que 12mm < 14mm < ... < 26mm+ ordene bien.';
COMMENT ON COLUMN core.calibre.es_descarte IS
    'true para valores que no son un calibre (DESCARTE), que en el origen convivían con los '
    'milímetros en la misma columna.';

CREATE TABLE IF NOT EXISTS core.productor_equivalencia (
    productor_norm  text PRIMARY KEY,
    productor       text NOT NULL,
    empresa_id      smallint REFERENCES core.empresa(empresa_id),
    origen          text NOT NULL
);

COMMENT ON TABLE core.productor_equivalencia IS
    'Traduce el nombre de productor que usa la empacadora al de la empresa. En el origen era '
    'M_EquivalenciaElifab, la única tabla que resolvía explícitamente un problema de '
    'vocabulario — el precedente de core.fundo_alias. Hace falta porque H02 escribe el mismo '
    'productor de seis formas (AQUANQA II, AQU II, AQUA II...).';

CREATE TABLE IF NOT EXISTS core.packing (
    packing_id      integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    modulo_id       smallint REFERENCES core.modulo(modulo_id),
    empresa_id      smallint REFERENCES core.empresa(empresa_id),
    variedad_id     smallint REFERENCES core.variedad(variedad_id),
    calibre_id      smallint REFERENCES core.calibre(calibre_id),
    fecha_cosecha   date NOT NULL,
    fecha_proceso   date NOT NULL,
    semana          smallint,
    anio            smallint,
    turno_packing   text CHECK (turno_packing IN ('DIA', 'NOCHE')),
    clase           text,
    mercado         text,
    mercado_valido  boolean NOT NULL DEFAULT true,
    recuento        integer CHECK (recuento >= 0),
    peso_kg         numeric(12,4) CHECK (peso_kg >= 0),
    porcentaje      numeric(8,4),
    nota_packing    text,
    calibrador      text,
    acdt            text,
    acidez          text,
    defecto         text,
    programa        text,
    contenedores_esperados integer,
    contenedores_volcados  integer,
    hora_inicio     time,
    hora_fin        time
);

COMMENT ON TABLE core.packing IS
    'Resultado de la empacadora externa: 117.536 filas. Cierra el ciclo comercial clasificando '
    'la fruta por calibre y mercado. Referencia MÓDULO y no lote, porque su columna [Lote] no '
    'contiene lotes de campo sino notas de packing (NP, "NP  910"): resolverlas contra el '
    'maestro deja el 100% huérfano (hallazgo N-2).';
COMMENT ON COLUMN core.packing.turno_packing IS
    'Turno de proceso de la empacadora: DIA o NOCHE. Es un dominio DISTINTO del turno de riego '
    'T00-T12, aunque en el origen ambas columnas se llamen Turno (N-2). El origen escribe '
    'además Noche y NOCHE como dos grafías.';
COMMENT ON COLUMN core.packing.mercado IS
    'Destino comercial: la distribución entre CHINA, USA, ÁCIDO y DESCARTE es el indicador de '
    'rentabilidad de la campaña.';
COMMENT ON COLUMN core.packing.mercado_valido IS
    'false para los valores que no son un mercado. El origen tiene 41.428 filas con ''0'' y 675 '
    'con ''-'': un tercio de la tabla no tiene mercado asignable, algo que la auditoría no '
    'recogía (N-2).';
COMMENT ON COLUMN core.packing.nota_packing IS
    'La columna [Lote] del origen, conservada con su nombre real.';
COMMENT ON COLUMN core.packing.hora_inicio IS
    '47,8% nula en el origen: cualquier análisis de duración de packing cubre la mitad de los '
    'datos y el tablero debe indicarlo.';

CREATE INDEX IF NOT EXISTS packing_fecha_proceso_idx ON core.packing (fecha_proceso);
CREATE INDEX IF NOT EXISTS packing_fecha_cosecha_idx ON core.packing (fecha_cosecha);
CREATE INDEX IF NOT EXISTS packing_modulo_idx ON core.packing (modulo_id);
CREATE INDEX IF NOT EXISTS packing_calibre_idx ON core.packing (calibre_id);

-- ── Forecast ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.version_forecast (
    version_id      smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sistema         text NOT NULL CHECK (sistema IN ('campania', 'semanal')),
    codigo          text NOT NULL,
    semana_emision  smallint,
    iteracion       smallint NOT NULL DEFAULT 1,
    es_presupuesto  boolean NOT NULL DEFAULT false,
    UNIQUE (sistema, codigo)
);

COMMENT ON TABLE core.version_forecast IS
    'Escenario de proyección. 15 versiones en el sistema de campaña (Presupuesto 2026 es la '
    'línea base y cada Proy_<mes> una revisión) y 46 en el semanal (S01..S32 con sufijos). '
    'Toda medida sobre forecast DEBE filtrar una versión: sin filtro se suman escenarios '
    'distintos del mismo periodo, y de ahí salen los 648 M de kg de R08 frente a los ~32,45 M '
    'de cosecha real de las cinco campañas.';
COMMENT ON COLUMN core.version_forecast.semana_emision IS
    'Semana en que se emitió la proyección, extraída del código. En el origen se obtenía con '
    'Int(Right(Left(Version,3),2)), un parseo que falla en silencio si alguien escribe S5 en '
    'vez de S05 y que no distingue S27 de S27_v2.';
COMMENT ON COLUMN core.version_forecast.iteracion IS
    'Número de iteración dentro de la misma semana o mes: 1 para S27, 2 para S27_v2. Es lo que '
    'permite quedarse con la proyección vigente sin contar la semana tres veces.';

CREATE TABLE IF NOT EXISTS core.forecast_campania (
    forecast_campania_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version_id      smallint NOT NULL REFERENCES core.version_forecast(version_id),
    modulo_id       smallint REFERENCES core.modulo(modulo_id),
    empresa_id      smallint REFERENCES core.empresa(empresa_id),
    turno_id        smallint REFERENCES core.turno(turno_id),
    campania_id     smallint REFERENCES core.campania(campania_id),
    anio            smallint,
    semana          smallint,
    kg_exp          numeric(14,4),
    kg_des          numeric(14,4),
    kg_con          numeric(14,4),
    frutos_exp      numeric(14,2),
    c12 numeric(12,3), c14 numeric(12,3), c16 numeric(12,3), c18 numeric(12,3),
    c19 numeric(12,3), c20 numeric(12,3), c22 numeric(12,3), c24 numeric(12,3),
    c26 numeric(12,3)
);

COMMENT ON TABLE core.forecast_campania IS
    'Proyección a nivel de campaña por módulo, con desglose por destino y calibre: 101.715 '
    'filas. En el origen la semántica de sus dos columnas de fundo estaba invertida respecto a '
    'M_Lotes — Fundo traía la empresa y FundoPPto el fundo físico — y aquí se desinvierte (N-5).';
COMMENT ON COLUMN core.forecast_campania.kg_exp IS
    'Kilos exportables. Es la columna que R0801_ResCampaña usa como "los kilos del forecast", y '
    'ese precedente resuelve la decisión D-1: no existe ningún KG genérico, y R0902 lo pedía.';
COMMENT ON COLUMN core.forecast_campania.c12 IS
    'Proyección para el calibre de 12 mm. Las nueve columnas de calibre tienen los mismos '
    '13.121 nulos: son las versiones previas a que se proyectara por calibre.';

CREATE TABLE IF NOT EXISTS core.forecast_semanal (
    forecast_semanal_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version_id      smallint NOT NULL REFERENCES core.version_forecast(version_id),
    lote_id         integer REFERENCES core.lote(lote_id),
    campania_id     smallint REFERENCES core.campania(campania_id),
    pasada          smallint,
    area_ha         numeric(10,4),
    fecha_cos_ant   date,
    fecha_cos       date,
    semana          smallint,
    frutos_por_planta numeric(12,4),
    peso_baya       numeric(8,4),
    frutos_total    numeric(14,2),
    rendimiento     numeric(12,4),
    kg              numeric(14,4),
    dr              smallint
);

COMMENT ON TABLE core.forecast_semanal IS
    'Proyección semanal a nivel de lote: 48.368 filas, más granular y de horizonte más corto '
    'que la de campaña. En el origen su columna Fundo mezclaba dos vocabularios distintos en '
    'la misma columna (N-5).';
COMMENT ON COLUMN core.forecast_semanal.frutos_por_planta IS
    'Frutos a cosechar POR PLANTA (FrtCos en el origen). Multiplicado por las plantas del lote '
    'da el total absoluto: es el paso que convierte un muestreo en una proyección de volumen.';

CREATE INDEX IF NOT EXISTS forecast_campania_version_idx ON core.forecast_campania (version_id);
CREATE INDEX IF NOT EXISTS forecast_semanal_version_idx ON core.forecast_semanal (version_id);
CREATE INDEX IF NOT EXISTS forecast_semanal_lote_idx ON core.forecast_semanal (lote_id);
