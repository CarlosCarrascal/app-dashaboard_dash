-- ============================================================================
-- 030 · Decisiones de negocio parametrizadas
--
-- Tres defectos de la auditoría no tienen corrección técnica: dependen de una definición
-- de negocio que Planeamiento y Agronomía aún no han dado. En lugar de bloquear la
-- migración, se implementan con un supuesto explícito guardado aquí.
--
-- Cambiar una decisión = UPDATE + REFRESH de las vistas materializadas. No re-migrar.
-- ============================================================================

CREATE TABLE IF NOT EXISTS core.config_decision (
    clave        text PRIMARY KEY,
    valor        text NOT NULL,
    descripcion  text NOT NULL,
    hallazgo     text,
    estado       text NOT NULL DEFAULT 'provisional'
                 CHECK (estado IN ('provisional', 'confirmado')),
    decide       text NOT NULL,
    confirmado_por text,
    confirmado_en  timestamptz,
    actualizado_en timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE core.config_decision IS
    'Supuestos de negocio en uso. estado=provisional significa que el valor se eligió por '
    'inferencia y debe confirmarlo el área indicada en "decide".';
COMMENT ON COLUMN core.config_decision.valor IS
    'Valor en texto; cada consumidor lo interpreta según su clave.';

INSERT INTO core.config_decision (clave, valor, descripcion, hallazgo, estado, decide) VALUES

    ('forecast.columna_kg',
     'kg_exp',
     'Qué kilos de R08_Forecast_Campaña representan "los kilos del forecast". Opciones: '
     'kg_exp (648.044.713,14) | kg_exp+kg_con (657.404.158,58) | kg_exp+kg_des+kg_con '
     '(689.684.707,86). Se elige kg_exp por el precedente interno de R0801_ResCampaña, que '
     'suma solo exportable porque es la fruta que genera margen.',
     'H-04 caso 6 / D-1', 'provisional', 'Planeamiento'),

    ('forecast.version_campana_comparada',
     '',
     'Versión de R08 que debe compararse contra R09 en R0902_Forecast_Sem_vs_Camp. Vacío = '
     'sin filtrar, que es el comportamiento actual y NO tiene sentido: R08 acumula 15 '
     'proyecciones y R09 46, así que la comparación suma escenarios distintos del mismo '
     'periodo. Mientras esté vacío, la vista se expone con una advertencia.',
     'H-04 caso 6 / D-1', 'provisional', 'Planeamiento'),

    ('campania.origen_fechas',
     'derivado',
     'De dónde salen las fechas de corte de cada campaña productiva. derivado = del rango '
     'real observado en H00/H01/M_Poda por campaña. Cuando Planeamiento entregue el '
     'calendario oficial, pasa a "declarado" y se cargan en core.campania.',
     'H-04 caso 5 / D-2', 'provisional', 'Planeamiento'),

    ('cosecha.origen_referencia_kg',
     'H00',
     'Cuál de las dos tablas de cosecha es la referencia de KG. H00 conserva los registros '
     'completos en C2023/C2024 (187 filas y 4.486,59 kg más que H01); H01 aporta turno, '
     'paña, peso y nPlantas. Se toma H00 para la medida y H01 para los atributos, '
     'reconciliando por clave.',
     'H-07 / D-3', 'provisional', 'Agronomía'),

    ('ramas.semantica_nro_rama',
     'indice_de_rama',
     'Qué significa E01_Ramas.[# Ramas]. Verificado como índice de la rama medida (1-33), '
     'no como total de ramas: en un mismo punto y fecha hay una fila por rama con su propio '
     'diámetro. De ello depende que la métrica de ramas sea 110.095 (declaradas) o 71.095 '
     '(medidas) en lugar de 730.318 (suma de índices).',
     'N-1 / ADR-0002', 'provisional', 'Agronomía')

ON CONFLICT (clave) DO NOTHING;

-- Lectura tipada, para no repetir el cast en cada vista.
CREATE OR REPLACE FUNCTION core.fn_config(p_clave text)
RETURNS text
LANGUAGE sql STABLE
AS $$
    SELECT valor FROM core.config_decision WHERE clave = p_clave;
$$;

COMMENT ON FUNCTION core.fn_config(text) IS
    'Valor de una decisión de negocio. Usar en vistas en lugar de codificar el supuesto.';
