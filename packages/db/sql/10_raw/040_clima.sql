-- ============================================================================
-- 040 · raw · Clima (H05)
-- ============================================================================

-- 155.588 filas para 153.413 timestamps distintos: 2.079 grupos duplicados (H-08).
CREATE TABLE IF NOT EXISTS raw.h05_clima (
    fecha              text,
    barometro          text,
    temp               text,
    temp_alta          text,
    temp_baja          text,
    humedad            text,
    punto_rocio        text,
    bulbo_humedo       text,
    vel_viento         text,
    direc_viento       text,
    viento_corriente   text,
    alta_vel_viento    text,
    alta_direc_viento  text,
    viento_frio        text,
    indice_calor       text,
    thw_index          text,
    tshw_index         text,
    lluvia             text,
    tasa_lluvia        text,
    rad_sol            text,
    ener_solar         text,
    rad_sol_alta       text,
    et_mm              text,
    dg_calentamiento   text,
    dg_enfriamiento    text
);

COMMENT ON TABLE raw.h05_clima IS
    'H05_Clima — 155.588 filas de estación meteorológica automática. Un timestamp identifica '
    'unívocamente una medición (no hay columna de estación, así que tampoco cabe la lectura '
    'de "dos sensores"), y hay 2.079 grupos duplicados exactos por recarga: 153.413 '
    'timestamps distintos (H-08).';
COMMENT ON COLUMN raw.h05_clima.temp_alta IS
    '[TembAlta] — el nombre original tiene un typo (Temb en lugar de Temp); se corrige aquí.';
COMMENT ON COLUMN raw.h05_clima.lluvia IS
    '[Lluvia] — SUM crudo 160,600. Es el caso más grave de H-08: la lluvia de los momentos '
    'duplicados se cuenta dos veces y sobrestima la precipitación acumulada, que es lo que '
    'alimenta las decisiones de riego y de manejo de enfermedad fúngica. Un acumulado '
    'sobrestimado puede inducir a regar de menos.';
COMMENT ON COLUMN raw.h05_clima.et_mm IS
    '[ET-mm] — evapotranspiración: determina la necesidad de riego.';
COMMENT ON COLUMN raw.h05_clima.dg_calentamiento IS
    '[DGCalentamiento] — grados-día de calentamiento. Junto con dg_enfriamiento son los '
    'acumuladores térmicos que predicen la velocidad de desarrollo del fruto.';
COMMENT ON COLUMN raw.h05_clima.thw_index IS
    '[THWIndex] — índice temperatura-humedad-viento.';
