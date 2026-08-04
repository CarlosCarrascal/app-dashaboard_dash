-- ============================================================================
-- 30_stg · 040 · Vistas normalizadas
--
-- Una vista por tabla de origen, con los tipos ya convertidos, los códigos canónicos y el
-- lote resuelto (o su motivo). Son la única fuente desde la que se carga `core`: ninguna
-- carga lee `raw` directamente, para que la normalización exista en un solo sitio.
-- ============================================================================

-- ── Maestro vigente de lotes ────────────────────────────────────────────────
CREATE OR REPLACE VIEW stg.v_maestro_lote AS
SELECT stg.fn_norm_texto(fundo_ppto)   AS empresa_norm,
       btrim(fundo_ppto)               AS empresa,
       stg.fn_norm_texto(fundo)        AS fundo_norm,
       btrim(fundo)                    AS fundo,
       btrim(fundo_pptom5)             AS alias_operativo,
       stg.fn_norm_texto(fundo_pptom5) AS alias_norm,
       stg.fn_norm_modulo(modulo)      AS modulo,
       stg.fn_norm_turno(turno)        AS turno,
       stg.fn_norm_lote(lote)          AS lote,
       btrim(variedad)                 AS variedad,
       stg.fn_a_numero(area)           AS area_ha,
       stg.fn_a_entero(n_plantas)      AS n_plantas,
       stg.fn_a_fecha(fecha_siembra)   AS fecha_siembra,
       nullif(btrim(maceta), '')       AS maceta,
       nullif(btrim(tipo_fibra), '')   AS tipo_fibra,
       nullif(btrim(key_map), '')      AS key_map
FROM raw.m_lotes_maestro;

COMMENT ON VIEW stg.v_maestro_lote IS
    'Maestro vigente ya normalizado: 879 lotes. Es la fuente de identidad (ADR-0003).';

-- ── Evaluaciones ────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW stg.v_e01_ramas AS
SELECT r.lote_id,
       r.motivo,
       stg.fn_a_fecha(e.fecha)     AS fecha,
       stg.fn_a_entero(e.cortina)  AS cortina,
       stg.fn_a_entero(e.hilera)   AS hilera,
       stg.fn_a_entero(e.planta)   AS planta,
       btrim(e.evaluador)          AS dni,
       stg.fn_conteo(e.ramas_lt5) AS ramas_menor5,
       stg.fn_conteo(e.ramas_gt5) AS ramas_mayor5,
       stg.fn_a_entero(e.num_ramas) AS nro_rama,
       stg.fn_a_real(e.diametro)    AS diametro,
       btrim(e.id_origen)           AS id_origen,
       btrim(e.actividad)           AS actividad
FROM raw.e01_ramas e
LEFT JOIN stg.v_resolucion r
       ON r.clave = stg.fn_clave_ubicacion(e.fundo, e.modulo, e.lote);

COMMENT ON VIEW stg.v_e01_ramas IS
    'Ramas normalizadas. Cada fila es una RAMA medida (N-1): nro_rama es el índice de la rama '
    'dentro de la planta, no un total, y ramas_menor5 y ramas_mayor5 son atributos de la '
    'planta repetidos en todas sus filas.';

CREATE OR REPLACE VIEW stg.v_e02_flores AS
SELECT r.lote_id,
       r.motivo,
       stg.fn_a_fecha(e.fecha)    AS fecha,
       stg.fn_a_entero(e.cortina) AS cortina,
       stg.fn_a_entero(e.hilera)  AS hilera,
       stg.fn_a_entero(e.planta)  AS planta,
       btrim(e.evaluador)         AS dni,
       stg.fn_conteo(e.n_flores) AS n_flores,
       stg.fn_conteo(e.cuajo)    AS cuajo,
       stg.fn_conteo(e.ya)       AS yemas_abiertas,
       stg.fn_conteo(e.yp)       AS yemas_por_abrir,
       stg.fn_a_hora(e.hora)       AS hora,
       nullif(btrim(e.item), '')   AS item
FROM raw.e02_conteo_flores e
LEFT JOIN stg.v_resolucion r
       ON r.clave = stg.fn_clave_ubicacion(e.fundo, e.modulo, e.lote);

CREATE OR REPLACE VIEW stg.v_e03_estados AS
SELECT r.lote_id,
       r.motivo,
       stg.fn_a_fecha(e.fecha)    AS fecha,
       stg.fn_a_entero(e.cortina) AS cortina,
       stg.fn_a_entero(e.hilera)  AS hilera,
       stg.fn_a_entero(e.planta)  AS planta,
       btrim(e.evaluador)         AS dni,
       coalesce(stg.fn_conteo(e.e1), 0) AS e1,
       coalesce(stg.fn_conteo(e.e2), 0) AS e2,
       coalesce(stg.fn_conteo(e.e3), 0) AS e3,
       coalesce(stg.fn_conteo(e.e4), 0) AS e4,
       coalesce(stg.fn_conteo(e.e5), 0) AS e5,
       stg.fn_a_entero(e.total)   AS total_origen,
       coalesce(nullif(btrim(e.item), ''), '(sin item)') AS item
FROM raw.e03_conteo_estados e
LEFT JOIN stg.v_resolucion r
       ON r.clave = stg.fn_clave_ubicacion(e.fundo, e.modulo, e.lote);

COMMENT ON VIEW stg.v_e03_estados IS
    'Estados normalizados. `item` forma parte de la clave natural — con él la clave da '
    'exactamente 18.714 filas y sin él rechazaría 212 (hallazgo N-8).';

CREATE OR REPLACE VIEW stg.v_e04_brotes AS
SELECT r.lote_id,
       r.motivo,
       stg.fn_a_fecha(e.fecha)    AS fecha,
       upper(btrim(e.piso))       AS piso,
       stg.fn_a_entero(e.cortina) AS cortina,
       stg.fn_a_entero(e.hilera)  AS hilera,
       stg.fn_a_entero(e.planta)  AS planta,
       btrim(e.evaluador)         AS dni,
       stg.fn_conteo(e.brotes)  AS brotes,
       nullif(btrim(e.des1), '')  AS des1,
       nullif(btrim(e.des2), '')  AS des2,
       nullif(btrim(e.des3), '')  AS des3,
       stg.fn_a_hora(e.hora)      AS hora
FROM raw.e04_brotes e
LEFT JOIN stg.v_resolucion r
       ON r.clave = stg.fn_clave_ubicacion(e.fundo, e.modulo, e.lote);

CREATE OR REPLACE VIEW stg.v_e05_bayas AS
SELECT r.lote_id,
       r.motivo,
       stg.fn_a_fecha(e.fecha)    AS fecha,
       stg.fn_a_entero(e.cortina) AS cortina,
       stg.fn_a_entero(e.hilera)  AS hilera,
       stg.fn_a_real(e.diametro)  AS diametro,
       stg.fn_norm_turno(e.turno) AS turno,
       -- El origen no identifica la baya: se numera por orden estable dentro de su grupo (N-7).
       row_number() OVER (
           PARTITION BY r.lote_id, stg.fn_a_fecha(e.fecha),
                        stg.fn_a_entero(e.cortina), stg.fn_a_entero(e.hilera)
           ORDER BY stg.fn_a_real(e.diametro), e.ctid
       ) AS nro_muestra
FROM raw.e05_diametros_bayas e
LEFT JOIN stg.v_resolucion r
       ON r.clave = stg.fn_clave_ubicacion(NULL, e.modulo, e.lote);

COMMENT ON VIEW stg.v_e05_bayas IS
    'Diámetro de baya. Una fila es una baya medida, ~97 por hilera y fecha (N-7): como el '
    'origen no la identifica, nro_muestra se asigna por orden de diámetro, que es estable '
    'entre ejecuciones.';

-- ── Cosecha ─────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW stg.v_h00_cosecha AS
SELECT r.lote_id,
       r.motivo,
       upper(btrim(h.campania))   AS campania,
       stg.fn_a_fecha(h.fecha)    AS fecha,
       btrim(h.variedad)          AS variedad,
       stg.fn_a_real(h.kg)        AS kg
FROM raw.h00_volumen_campo h
LEFT JOIN stg.v_resolucion r
       ON r.clave = stg.fn_clave_ubicacion(h.fundo, h.modulo, h.lote);

CREATE OR REPLACE VIEW stg.v_h01_cosecha AS
SELECT r.lote_id,
       r.motivo,
       upper(btrim(h.campania))     AS campania,
       stg.fn_a_fecha(h.fecha)      AS fecha,
       stg.fn_norm_turno(h.turno)   AS turno,
       stg.fn_a_entero(h.n_plantas) AS n_plantas,
       stg.fn_a_entero(h.semana)    AS semana,
       stg.fn_a_real(h.kg)          AS kg,
       stg.fn_a_entero(h.pana)      AS pana,
       stg.fn_a_real(h.peso)        AS peso_baya
FROM raw.h01_prod_historica h
LEFT JOIN stg.v_resolucion r
       ON r.clave = stg.fn_clave_ubicacion(h.fundo, h.modulo, h.lote);

-- ── Packing ─────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW stg.v_h02_packing AS
SELECT stg.fn_norm_modulo(coalesce(nullif(btrim(p.modulo_acento), ''), p.modulo)) AS modulo,
       stg.fn_norm_turno_packing(p.turno)        AS turno_packing,
       stg.fn_a_fecha(p.fecha_cosecha)           AS fecha_cosecha,
       stg.fn_a_fecha(p.fecha_proceso)           AS fecha_proceso,
       stg.fn_semana(p.semana)                   AS semana,
       stg.fn_a_entero(p.anio)                   AS anio,
       btrim(p.calibre)                          AS calibre,
       stg.fn_calibre_mm(p.calibre)              AS calibre_mm,
       upper(btrim(p.mercado))                   AS mercado,
       upper(btrim(p.mercado)) IN ('CHINA', 'USA', 'ÁCIDO', 'ACIDO', 'DESCARTE') AS mercado_valido,
       btrim(p.clases)                           AS clase,
       btrim(p.variedad)                         AS variedad,
       btrim(p.productor)                        AS productor,
       btrim(p.productor1)                       AS productor_origen,
       stg.fn_a_entero(p.recuento)               AS recuento,
       -- De los dos "peso total" se conserva el que no tiene nulos (H-10).
       stg.fn_a_real(coalesce(p.peso_total_kg2, p.peso_total_kg)) AS peso_kg,
       stg.fn_a_numero(p.porcentaje)             AS porcentaje,
       nullif(btrim(p.lote), '')                 AS nota_packing,
       btrim(p.calibrador)                       AS calibrador,
       btrim(p.acdt)                             AS acdt,
       btrim(p.acidez)                           AS acidez,
       btrim(p.defecto)                          AS defecto,
       btrim(p.programa_clasificacion)           AS programa,
       stg.fn_a_entero(p.contenedores_esperados) AS contenedores_esperados,
       stg.fn_a_entero(p.contenedores_volcados)  AS contenedores_volcados,
       stg.fn_a_hora(p.hora_inicio)              AS hora_inicio,
       stg.fn_a_hora(p.hora_finalizacion)        AS hora_fin
FROM raw.h02_bd_elifab p;

COMMENT ON VIEW stg.v_h02_packing IS
    'Packing normalizado. No resuelve lote a propósito: su grano no llega ahí, y su columna '
    '[Lote] es una nota de packing que aquí se llama nota_packing (N-2). El módulo se toma de '
    '[Módulo] ("Módulo 02") con [Modulo] ("2") como respaldo.';

-- ── Clima ───────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW stg.v_h05_clima AS
SELECT stg.fn_a_timestamp(fecha)      AS fecha_hora,
       stg.fn_a_real(barometro)       AS barometro,
       stg.fn_a_real(temp)            AS temp,
       stg.fn_a_real(temp_alta)       AS temp_alta,
       stg.fn_a_real(temp_baja)       AS temp_baja,
       stg.fn_a_real(humedad)         AS humedad,
       stg.fn_a_real(punto_rocio)     AS punto_rocio,
       stg.fn_a_real(bulbo_humedo)    AS bulbo_humedo,
       stg.fn_a_real(vel_viento)      AS vel_viento,
       nullif(btrim(direc_viento), '') AS direc_viento,
       stg.fn_a_real(viento_corriente) AS viento_corriente,
       stg.fn_a_real(alta_vel_viento)  AS alta_vel_viento,
       nullif(btrim(alta_direc_viento), '') AS alta_direc_viento,
       stg.fn_a_real(viento_frio)     AS viento_frio,
       stg.fn_a_real(indice_calor)    AS indice_calor,
       stg.fn_a_real(thw_index)       AS thw_index,
       stg.fn_a_real(tshw_index)      AS tshw_index,
       stg.fn_a_real(lluvia)          AS lluvia,
       stg.fn_a_real(tasa_lluvia)     AS tasa_lluvia,
       stg.fn_a_real(rad_sol)         AS rad_sol,
       stg.fn_a_real(ener_solar)      AS ener_solar,
       stg.fn_a_real(rad_sol_alta)    AS rad_sol_alta,
       stg.fn_a_real(et_mm)           AS et_mm,
       stg.fn_a_real(dg_calentamiento) AS dg_calentamiento,
       stg.fn_a_real(dg_enfriamiento)  AS dg_enfriamiento
FROM raw.h05_clima;

-- ── Maestros y forecast ─────────────────────────────────────────────────────

CREATE OR REPLACE VIEW stg.v_m_poda AS
SELECT r.lote_id,
       r.motivo,
       upper(btrim(p.campania))       AS campania,
       stg.fn_a_fecha(p.fecha_inicio) AS fecha_inicio,
       stg.fn_a_fecha(p.fecha_siembra) AS fecha_siembra,
       stg.fn_a_numero(p.area)        AS area_ha,
       btrim(p.variedad)              AS variedad
FROM raw.m_poda p
LEFT JOIN stg.v_resolucion r
       ON r.clave = stg.fn_clave_ubicacion(p.fundo, p.modulo, p.lote);

CREATE OR REPLACE VIEW stg.v_m_evaluadores AS
SELECT btrim(dni)                        AS dni,
       nullif(btrim(nombres), '')        AS nombres,
       nullif(btrim(apellidos), '')      AS apellidos,
       nullif(btrim(cod), '')            AS codigo,
       nullif(btrim(zona), '')           AS zona,
       nullif(btrim(celular), '')        AS celular,
       stg.fn_a_fecha_dmy(inicio_labores) AS inicio_labores,
       stg.fn_a_fecha_dmy(nacimiento)    AS nacimiento,
       coalesce(btrim(estado) = 'true', false) AS activo
FROM raw.m_evaluadores;

CREATE OR REPLACE VIEW stg.v_m_n_muestra AS
SELECT r.lote_id,
       r.motivo,
       btrim(m.evaluacion)        AS evaluacion,
       stg.fn_a_entero(m.cortina) AS cortina,
       stg.fn_a_entero(m.hilera)  AS hilera,
       stg.fn_a_entero(m.planta)  AS planta,
       stg.fn_a_entero(m.muestras) AS muestras
FROM raw.m_n_muestra m
LEFT JOIN stg.v_resolucion r
       ON r.clave = stg.fn_clave_ubicacion(m.fundo, m.modulo, m.lote);

CREATE OR REPLACE VIEW stg.v_m_time AS
SELECT stg.fn_a_fecha(fecha)      AS fecha,
       stg.fn_a_entero(sem)       AS semana,
       stg.fn_mes_abrev(mes)      AS mes_num,
       btrim(mes)                 AS mes_abrev,
       stg.fn_a_entero(anio)      AS anio,
       stg.fn_a_entero(sev_conteo) AS sem_ev_conteo,
       nullif(btrim(mes_sem), '') AS mes_sem
FROM raw.m_time;

CREATE OR REPLACE VIEW stg.v_r08_forecast AS
SELECT btrim(f.version)                  AS version,
       -- Semántica invertida en el origen: Fundo trae la empresa y FundoPPto el fundo (N-5).
       stg.fn_norm_texto(f.fundo)         AS empresa_norm,
       stg.fn_norm_texto(f.fundo_ppto)    AS fundo_norm,
       stg.fn_norm_modulo(f.modulo)       AS modulo,
       stg.fn_norm_turno(f.turno)         AS turno,
       upper(btrim(f.campania))           AS campania,
       stg.fn_a_entero(f.anio)            AS anio,
       stg.fn_a_entero(f.semana)          AS semana,
       stg.fn_a_real(f.kg_exp)            AS kg_exp,
       stg.fn_a_real(f.kg_des)            AS kg_des,
       stg.fn_a_real(f.kg_con)            AS kg_con,
       stg.fn_a_real(f.frt_total_exp)     AS frutos_exp,
       stg.fn_a_numero(f.c12) AS c12, stg.fn_a_numero(f.c14) AS c14,
       stg.fn_a_numero(f.c16) AS c16, stg.fn_a_numero(f.c18) AS c18,
       stg.fn_a_numero(f.c19) AS c19, stg.fn_a_numero(f.c20) AS c20,
       stg.fn_a_numero(f.c22) AS c22, stg.fn_a_numero(f.c24) AS c24,
       stg.fn_a_numero(f.c26) AS c26
FROM raw.r08_forecast_campania f;

CREATE OR REPLACE VIEW stg.v_r09_forecast AS
SELECT r.lote_id,
       r.motivo,
       btrim(f.version)                AS version,
       upper(btrim(f.campania))        AS campania,
       stg.fn_a_entero(f.pasada)       AS pasada,
       stg.fn_a_numero(f.area)         AS area_ha,
       stg.fn_a_fecha(f.fecha_cos_ant) AS fecha_cos_ant,
       stg.fn_a_fecha(f.fecha_cos)     AS fecha_cos,
       stg.fn_a_entero(f.sem)          AS semana,
       stg.fn_a_real(f.frt_cos)        AS frutos_por_planta,
       stg.fn_a_real(f.peso)           AS peso_baya,
       stg.fn_a_real(f.frutos_total)   AS frutos_total,
       stg.fn_a_real(f.rend)           AS rendimiento,
       stg.fn_a_real(f.kg)             AS kg,
       stg.fn_a_entero(f.dr)           AS dr
FROM raw.r09_forecast_semanal f
LEFT JOIN stg.v_resolucion r
       ON r.clave = stg.fn_clave_ubicacion(f.fundo, f.modulo, f.lote);
