-- ============================================================================
-- 030 · raw · Cosecha y packing (H00, H01, H02)
-- ============================================================================

-- ── H00_VolumenCampo ────────────────────────────────────────────────────────
-- 30.812 filas, de las cuales 1 es una fila de subtotal de Excel (H-06).
CREATE TABLE IF NOT EXISTS raw.h00_volumen_campo (
    campania    text,
    fecha       text,
    fundo       text,
    variedad    text,
    modulo      text,
    lote        text,
    kg          text
);

COMMENT ON TABLE raw.h00_volumen_campo IS
    'H00_VolumenCampo — 30.812 filas. Kilos cosechados en campo: el dato primario de '
    'producción. Contiene 1 fila de subtotal de Excel con 930.662,06 kg y todos los '
    'identificadores vacíos (H-06). Es la referencia de KG frente a H01 (decisión D-3). '
    'La auditoría le atribuía además 151 filas de exceso por clave natural repetida en 34 '
    'grupos (N-9); eso dejó de ser cierto al normalizar los códigos de lote (N-3): hoy hay '
    '0 grupos repetidos (N-22).';
COMMENT ON COLUMN raw.h00_volumen_campo.campania IS '[Campaña] — C2022 a C2026.';
COMMENT ON COLUMN raw.h00_volumen_campo.fundo IS '[Fundo] — vocabulario B: empresa.';
COMMENT ON COLUMN raw.h00_volumen_campo.variedad IS
    '[Variedad] — 14 grafías, entre ellas POP (30.545) y SEKOYA POP (98), que son la misma. '
    'Aquí vive la variedad real, no en M_Lotes, que solo tiene Sekoya pop (N-6).';
COMMENT ON COLUMN raw.h00_volumen_campo.kg IS
    '[KG] — SUM crudo 33.381.134,66; sin la fila basura, 32.450.472,60.';

-- ── H01_ProdHistorica ───────────────────────────────────────────────────────
-- 30.626 filas, 2 de ellas subtotales (H-06). 187 filas menos que H00 (H-07).
CREATE TABLE IF NOT EXISTS raw.h01_prod_historica (
    fundo       text,
    campania    text,
    modulo      text,
    turno       text,
    lote        text,
    n_plantas   text,
    fecha       text,
    semana      text,
    kg          text,
    pana        text,
    peso        text
);

COMMENT ON TABLE raw.h01_prod_historica IS
    'H01_ProdHistorica — 30.626 filas. Cubre la misma cosecha que H00 pero con turno, paña, '
    'peso y nPlantas de origen. Tiene 187 filas menos que H00 en C2023/C2024 (4.486,59 kg, '
    'un promedio de 24 kg por fila frente a los ~1.060 kg del promedio general): son '
    'registros de volumen muy pequeño, excluidos por una regla que no está documentada en '
    'ninguna parte de la base porque se aplica en la carga, externa a Access (H-07).';
COMMENT ON COLUMN raw.h01_prod_historica.pana IS
    '[Paña] — número de pasada de cosecha. En arándano no se cosecha de una vez: se pasa '
    'varias veces recogiendo lo maduro, y el rendimiento por pasada decide cuántas hacer.';
COMMENT ON COLUMN raw.h01_prod_historica.peso IS '[Peso] — peso unitario de baya, en gramos.';
COMMENT ON COLUMN raw.h01_prod_historica.n_plantas IS
    '[nPlantas] — desnormalizado de M_Lotes; riesgo de divergencia.';
COMMENT ON COLUMN raw.h01_prod_historica.kg IS
    '[KG] — SUM crudo 33.441.319,22; sin las 2 filas basura, 32.445.986,02.';

-- ── H02_BDElifab ────────────────────────────────────────────────────────────
-- 117.536 filas y 35 columnas, 34 de ellas texto en el origen (H-10).
-- Su grano NO baja a lote: `lote` es una nota de packing (N-2).
CREATE TABLE IF NOT EXISTS raw.h02_bd_elifab (
    clases                     text,
    recuento                   text,
    peso_total_kg              text,
    porcentaje                 text,
    lote                       text,
    programa_clasificacion     text,
    contenedores_esperados     text,
    contenedores_volcados      text,
    peso_total_kg2             text,
    hora_inicio                text,
    hora_finalizacion          text,
    fecha_cosecha              text,
    fecha_proceso              text,
    productor1                 text,
    variedad                   text,
    modulo                     text,
    turno                      text,
    calibrador                 text,
    acdt                       text,
    calibre                    text,
    acdt2                      text,
    ensayo                     text,
    mercado                    text,
    semana                     text,
    s26                        text,
    s271                       text,
    modulo_acento              text,
    productor                  text,
    acidez                     text,
    defecto                    text,
    packet                     text,
    clasificacion              text,
    anio                       text,
    calibres                   text,
    mes                        text
);

COMMENT ON TABLE raw.h02_bd_elifab IS
    'H02_BDElifab — 117.536 filas. Resultado de la empacadora externa: cierra el ciclo '
    'comercial clasificando la fruta por calibre y mercado. Su grano NO llega a lote (N-2): '
    'el grano es (fecha proceso, módulo, turno de proceso, clase, calibre, mercado).';
COMMENT ON COLUMN raw.h02_bd_elifab.lote IS
    '[Lote] — NO es un lote de campo: contiene notas de packing (NP, "NP  910", "NP  212") '
    'y 1.254 vacíos. Resolverlo contra el maestro deja el 100% huérfano (N-2).';
COMMENT ON COLUMN raw.h02_bd_elifab.modulo IS
    '[Modulo] — el módulo sin prefijo ni relleno: 1, 2, ... 15. Se resuelve como '
    'M || lpad(modulo,2,''0'').';
COMMENT ON COLUMN raw.h02_bd_elifab.modulo_acento IS
    '[Módulo] — el mismo módulo con otra grafía ("Módulo 02"). Par duplicado de [Modulo] (H-10).';
COMMENT ON COLUMN raw.h02_bd_elifab.turno IS
    '[Turno] — turno de PROCESO de la empacadora: DÍA (90.702) / NOCHE (19.126). Dominio '
    'distinto del turno de riego T00-T12, aunque la columna se llame igual (N-2).';
COMMENT ON COLUMN raw.h02_bd_elifab.calibre IS
    '[Calibre] — escala ordenada en mm (12mm a 26mm+) más 4 valores que no son calibre: '
    '"-" (6.376), "Defectos" (1.434), "Descarte" (1.381) y "DESCARTE" (12.122). Guardada como '
    'texto: se ordena alfabéticamente y "10" va antes que "2" (H-10). "Descarte"/"DESCARTE" '
    'son la misma palabra con dos grafías y se unifican al cargar core.calibre; "Defectos" y '
    '"-" NO se fusionan con ella, por no haber evidencia de que sean sinónimos.';
COMMENT ON COLUMN raw.h02_bd_elifab.calibres IS
    '[Calibres] — el par duplicado de [Calibre] (H-10), pero mucho más grueso: solo 3 valores '
    '("-", "< 19 mm+", "> 19 mm+") frente a los 9 calibres reales de [Calibre]. Se extrae por '
    'trazabilidad y NO se usa para cargar core.calibre: [Calibre] es la fuente granular real.';
COMMENT ON COLUMN raw.h02_bd_elifab.mercado IS
    '[Mercado] — destino comercial y por tanto el indicador de rentabilidad: USA (44.134), '
    'DESCARTE (12.305), CHINA (11.827), ÁCIDO (7.167). Pero también ''0'' (41.428) y ''-'' '
    '(675): un tercio de la tabla no tiene mercado asignable (N-2).';
COMMENT ON COLUMN raw.h02_bd_elifab.productor1 IS
    '[Productor1] — 6 grafías del mismo productor (AQUANQA II, AQU II, AQUA II, AQUANQA I, '
    'AQUA, AQU I). M_EquivalenciaElifab existe para resolverlo.';
COMMENT ON COLUMN raw.h02_bd_elifab.productor IS
    '[Productor] — la versión ya normalizada: AQUA II / AQUA. Par duplicado de [Productor1].';
COMMENT ON COLUMN raw.h02_bd_elifab.hora_inicio IS
    '[Hora de inicio] — 47,8% nula: cualquier análisis de duración de packing cubre la '
    'mitad de los datos.';
COMMENT ON COLUMN raw.h02_bd_elifab.peso_total_kg IS
    '[Peso total (kg)] — el peso de ESTA fila: los kilos de esa clase/calibre concreto. Es el '
    'numerador del porcentaje y la única de las dos columnas de peso que se puede sumar '
    '(N-16). Suma 18.582.402 kg en las 117.536 filas.';
COMMENT ON COLUMN raw.h02_bd_elifab.peso_total_kg2 IS
    '[Peso total (kg)2] — NO es un duplicado de [Peso total (kg)], aunque se creyó que lo era '
    'y se eligió esta por tener 0 nulos frente a 1 (N-16 corrige a H-10). Es un total que se '
    'repite idéntico en cada fila del grupo (fecha proceso, módulo, turno, lote) en 2.535 de '
    '2.591 grupos, y actúa de denominador del porcentaje: % = 100 x peso1 / peso2, con un '
    'error medio de 0,25 pp. Sumarla por fila multiplica los kilos unas 24 veces. '
    'No es la suma de sus partes salvo en el 46% de los grupos: es un dato declarado aparte, '
    'compatible con un peso de recepción, pendiente de confirmar con Operaciones (N-21).';
