-- Señal interna del orquestador para una reconstrucción completa autorizada.
--
-- Este archivo solo se antepone a los bloques cuando el ETL ya verificó:
--   1) que el destino es aquanqa_migracion,
--   2) que existe backup/baseline,
--   3) que el usuario pasó --allow-full-core-rebuild.
--
-- Debe ejecutarse dentro de la --single-transaction del orquestador. El GUC es local a esa
-- transacción, de modo que una ejecución manual o incremental no puede saltarse los guards.

\set ON_ERROR_STOP on

DO $full_core_authorization$
BEGIN
    IF current_database() <> 'aquanqa_migracion' THEN
        RAISE EXCEPTION
            'Reconstrucción core bloqueada: la BD actual es %, se exige aquanqa_migracion.',
            current_database();
    END IF;

    PERFORM set_config('aquanqa.allow_full_core', 'on', true);
END
$full_core_authorization$;

SELECT current_database() AS base_reconstruccion,
       current_setting('aquanqa.allow_full_core', true) AS autorizacion;
