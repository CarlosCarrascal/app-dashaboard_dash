-- Sustituye el estado «replicado» por «consistente» en las afirmaciones publicables.
--
-- «Replicado» prometía algo que el análisis nunca comprobó: que la asociación se hubiera
-- vuelto a encontrar en otra campaña, en otro fundo o de forma prospectiva. Lo que el
-- código verifica es que resiste sus propios filtros —corrección por multiplicidad,
-- placebo de calendario, signo estable entre módulos y concordancia con el modelo mixto—.
-- Eso es consistencia interna, no replicación.
--
-- La diferencia importa porque la interfaz leía la etiqueta literalmente y mostraba «se
-- repitió en condiciones distintas» al pie de conclusiones que solo se habían medido una
-- vez. Con la etiqueta anterior seguía siendo posible publicar como replicada una relación
-- cuyo modelo mixto daba p = 0,43.
--
-- Idempotente: se puede volver a ejecutar sin efecto.

BEGIN;

-- 1. Ampliar el dominio antes de tocar las filas, para no violar el CHECK a mitad.
ALTER TABLE analytics.evidence_claim DROP CONSTRAINT IF EXISTS evidence_claim_estado_check;
ALTER TABLE analytics.evidence_claim
    ADD CONSTRAINT evidence_claim_estado_check
    CHECK (estado IN ('exploratorio', 'consistente', 'replicado', 'predictivo', 'causal'));

-- 2. Reetiquetar lo ya publicado. No se borra ni se degrada nada: la misma evidencia pasa
--    a llamarse por lo que de verdad se comprobó.
UPDATE analytics.evidence_claim SET estado = 'consistente' WHERE estado = 'replicado';

COMMENT ON COLUMN analytics.evidence_claim.estado IS
    'exploratorio | consistente | predictivo | causal. «consistente» = resiste los filtros '
    'internos (multiplicidad, placebo, estabilidad de signo, concordancia con el modelo '
    'mixto) sobre los datos disponibles; NO implica replicación externa ni validación '
    'prospectiva. «replicado» queda admitido solo por compatibilidad histórica y no se '
    'vuelve a emitir.';

COMMIT;
