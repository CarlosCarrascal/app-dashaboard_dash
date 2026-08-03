-- ============================================================================
-- 060 · raw · Forecast (R08, R09)
--
-- Dos sistemas de pronóstico paralelos con horizontes distintos. Lo esencial para
-- interpretarlos: AMBOS acumulan todo el histórico de re-proyecciones, no solo la vigente.
-- Sumar sin filtrar por versión mezcla escenarios del mismo periodo y da cifras que no
-- significan nada — los 648 M de kg de R08 son 15 escenarios sumados, frente a los ~32,45 M
-- de cosecha real de las cinco campañas.
-- ============================================================================

-- ── R08_Forecast_Campaña ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw.r08_forecast_campania (
    version        text,
    fundo          text,
    fundo_ppto     text,
    modulo         text,
    turno          text,
    anio           text,
    semana         text,
    kg_exp         text,
    kg_des         text,
    kg_con         text,
    frt_total_exp  text,
    campania       text,
    c12            text,
    c14            text,
    c16            text,
    c18            text,
    c19            text,
    c20            text,
    c22            text,
    c24            text,
    c26            text
);

COMMENT ON TABLE raw.r08_forecast_campania IS
    'R08_Forecast_Campaña — 101.715 filas. Proyección a nivel de campaña por módulo, con '
    'desglose por destino comercial y calibre. Acumula 15 versiones: Presupuesto 2026 es la '
    'línea base aprobada y cada Proy_<mes> una revisión posterior.';
COMMENT ON COLUMN raw.r08_forecast_campania.fundo IS
    '[Fundo] — ATENCIÓN: aquí contiene la EMPRESA (Aqu Anqa II / Aqu Anqa), al revés que en '
    'M_Lotes. La semántica de las dos columnas de fundo está invertida (N-5).';
COMMENT ON COLUMN raw.r08_forecast_campania.fundo_ppto IS
    '[FundoPPto] — ATENCIÓN: aquí contiene el FUNDO FÍSICO, ya con la nomenclatura nueva '
    '(Aqu Anqa 1..6) en el 96% de las filas, mezclado con alias antiguos en el resto. Que '
    'esta tabla ya use la nomenclatura vigente es lo que permite cerrar la decisión D-4 con '
    'datos en lugar de con una consulta a Agronomía (N-5).';
COMMENT ON COLUMN raw.r08_forecast_campania.kg_exp IS
    '[KG Exp] — kilos exportables. SUM = 648.044.713,14 sobre las 15 versiones. Es la '
    'columna que R0801_ResCampaña toma como "los kilos del forecast", y ese precedente es el '
    'que resuelve la decisión D-1.';
COMMENT ON COLUMN raw.r08_forecast_campania.kg_des IS '[Kg Des] — descarte. SUM = 32.280.549,28.';
COMMENT ON COLUMN raw.r08_forecast_campania.kg_con IS '[Kg Con] — consumo. SUM = 9.359.445,44.';
COMMENT ON COLUMN raw.r08_forecast_campania.c12 IS
    '[C12] — desglose por calibre de 12 mm. Las 9 columnas C12..C26 tienen los mismos 13.121 '
    'nulos: son las versiones antiguas, previas a que se proyectara por calibre.';
-- No existe ninguna columna KG genérica, y R0902_Forecast_Sem_vs_Camp la pide: H-04 caso 6.

-- ── R09_Forecast_Semanal ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw.r09_forecast_semanal (
    campania       text,
    pasada         text,
    modulo         text,
    turno          text,
    lote           text,
    area           text,
    fecha_cos_ant  text,
    fecha_cos      text,
    sem            text,
    frt_cos        text,
    peso           text,
    frutos_total   text,
    rend           text,
    kg             text,
    dr             text,
    version        text,
    fund_ppto      text,
    fundo          text
);

COMMENT ON TABLE raw.r09_forecast_semanal IS
    'R09_Forecast_Semanal — 48.368 filas. Proyección semanal a nivel de lote: más granular y '
    'de horizonte más corto que R08. Acumula 46 versiones S01..S32 con sufijos _v2/_v3/_V2 '
    '(mayúsculas inconsistentes). SUM(Kg) = 51.083.049,92.';
COMMENT ON COLUMN raw.r09_forecast_semanal.modulo IS '[Mod] — módulo, abreviado en el origen.';
COMMENT ON COLUMN raw.r09_forecast_semanal.version IS
    '[Version] — codifica la semana de emisión. La consulta R0901_Forecas_SemAc la parsea con '
    'Int(Right(Left(Version,3),2)) para quedarse con la proyección vigente de cada semana, un '
    'nowcast bien pensado pero frágil: si alguien escribe S5 en vez de S05 el parseo falla sin '
    'error, y no desambigua entre S27, S27_v2 y S27_v3, así que la semana 27 aparece tres '
    'veces. En core se descompone en semana_emision e iteracion.';
COMMENT ON COLUMN raw.r09_forecast_semanal.fundo IS
    '[Fundo] — mezcla DOS vocabularios en la misma columna: alias operativos '
    '(Aqu Anqa II - Kawsay Allpa, 11.539 filas) y fundos físicos nuevos (Aqu Anqa 4, '
    'Aqu Anqa 2...) (N-5).';
COMMENT ON COLUMN raw.r09_forecast_semanal.fund_ppto IS
    '[FundPPTo] — typo del origen (falta la o de FundoPPTo). Mezcla empresa con alias: '
    'incluye Aqu Anqa II - Ampliación, que no es una empresa (N-5).';
COMMENT ON COLUMN raw.r09_forecast_semanal.frt_cos IS
    '[FrtCos] — frutos a cosechar POR PLANTA. Multiplicado por las plantas del lote da el '
    'total absoluto: es el paso que convierte un muestreo en una proyección de volumen.';
COMMENT ON COLUMN raw.r09_forecast_semanal.pasada IS
    '[Pasada] — 47,1% nula, igual que peso y frutos_total: son las versiones que no '
    'proyectaban a ese nivel de detalle.';
