from pathlib import Path

SQL = (
    Path(__file__).parents[3] / "db" / "sql" / "80_analytics" / "040_evidence_claim_history.sql"
).read_text(encoding="utf-8")
SQL_COMPACTO = " ".join(SQL.split())


def test_migracion_de_historial_es_idempotente_y_no_reemplaza_la_tabla_vigente():
    assert "BEGIN;" in SQL
    assert "COMMIT;" in SQL
    assert "CREATE TABLE IF NOT EXISTS analytics.evidence_claim_history" in SQL
    assert "PRIMARY KEY (claim_id, run_id)" in SQL
    assert "REFERENCES analytics.forecast_run(run_id) ON DELETE RESTRICT" in SQL
    assert "CREATE INDEX IF NOT EXISTS ix_evidence_claim_history_run" in SQL
    assert "CREATE OR REPLACE VIEW reporting.evidencia_analitica_historica" in SQL
    assert "FROM analytics.evidence_claim WHERE run_id IS NOT NULL" in SQL_COMPACTO
    assert "ON CONFLICT (claim_id, run_id) DO NOTHING" in SQL
    assert "analytics.evidence_claim SET" not in SQL
    assert "model_feature_evidence" not in SQL


def test_migracion_declara_tipos_jsonb_del_historial():
    assert "CHECK (jsonb_typeof(alcance) = 'object')" in SQL
    assert "CHECK (jsonb_typeof(supuestos) = 'array')" in SQL
    assert "CHECK (jsonb_typeof(limitaciones) = 'array')" in SQL
    assert "CHECK (jsonb_typeof(referencias) = 'array')" in SQL


def test_backfill_conserva_jsonb_legacy_sin_abortar_y_emite_diagnostico():
    assert "RAISE WARNING" in SQL
    assert "jsonb_build_object('_legacy_jsonb'" in SQL
    assert "jsonb_build_array(jsonb_build_object(" in SQL
    assert "COALESCE(alcance, 'null'::jsonb)" in SQL
    assert "COALESCE(supuestos, 'null'::jsonb)" in SQL
    assert "COALESCE(limitaciones, 'null'::jsonb)" in SQL
    assert "COALESCE(referencias, 'null'::jsonb)" in SQL
    assert "jsonb_typeof(alcance) = 'object'" in SQL
    assert "jsonb_typeof(supuestos) = 'array'" in SQL
    assert "jsonb_typeof(limitaciones) = 'array'" in SQL
    assert "jsonb_typeof(referencias) = 'array'" in SQL
    assert "supuestos[0]->''_legacy_jsonb''" in SQL
    assert "limitaciones[0]->''_legacy_jsonb''" in SQL
    assert "referencias[0]->''_legacy_jsonb''" in SQL


def test_normalizacion_ocurre_despues_del_backfill_y_es_por_fila():
    backfill = SQL.index("INSERT INTO analytics.evidence_claim_history")
    backfill_fin = SQL.index("ON CONFLICT (claim_id, run_id) DO NOTHING;", backfill)
    normalizacion = SQL.index("-- Normalización posterior al backfill")
    assert backfill < backfill_fin < normalizacion
    assert "CREATE OR REPLACE FUNCTION pg_temp.normalizar_claim_jsonb" in SQL
    assert "FOR v_claim IN" in SQL
    assert "FROM analytics.evidence_claim" in SQL
    assert "FOR UPDATE" in SQL
    assert "UPDATE analytics.evidence_claim" in SQL
    assert "pg_temp.normalizar_claim_jsonb(" in SQL
    assert "EXCEPTION WHEN others THEN" in SQL
    assert "jsonb_typeof(v_claim.alcance) IS DISTINCT FROM 'object'" in SQL
    assert "jsonb_typeof(v_claim.referencias) IS DISTINCT FROM 'array'" in SQL


def test_normalizacion_convierte_strings_validos_y_conserva_strings_invalidos():
    assert "(p_valor #>> '{}')::jsonb" in SQL
    assert "IF jsonb_typeof(v_parseado) = p_tipo_esperado THEN" in SQL
    assert "string JSON válido" in SQL
    assert "string que no es JSON válido" in SQL
    assert "jsonb_build_object('_legacy_jsonb', COALESCE(p_valor, 'null'::jsonb))" in SQL
    assert "se conserva el valor original bajo _legacy_jsonb" in SQL
    assert "RAISE WARNING" in SQL


def test_normalizacion_y_checks_de_la_tabla_vigente_son_idempotentes():
    normalizacion = SQL.index("-- Normalización posterior al backfill")
    checks_vigentes = SQL.index("-- Protege futuras escrituras")
    assert normalizacion < checks_vigentes
    assert "IF v_tipo_original = p_tipo_esperado THEN" in SQL
    assert "IF NOT EXISTS (" in SQL[checks_vigentes:]
    assert "ck_evidence_claim_alcance_json" in SQL
    assert "ck_evidence_claim_supuestos_json" in SQL
    assert "ck_evidence_claim_limitaciones_json" in SQL
    assert "ck_evidence_claim_referencias_json" in SQL
    assert "ADD CONSTRAINT" in SQL[checks_vigentes:]


def test_normalizacion_no_toca_identidad_ni_relacion_de_features():
    assert "SET claim_id" not in SQL
    assert "SET run_id" not in SQL
    assert "model_feature_evidence" not in SQL


def test_checks_90_exigen_historial_tipos_y_correspondencia():
    checks = (
        Path(__file__).parents[3] / "db" / "sql" / "90_checks" / "030_analytics.sql"
    ).read_text(encoding="utf-8")
    compacto = " ".join(checks.split())

    assert "'evidence_claim_history'" in checks
    assert "reporting.evidencia_analitica_historica" in checks
    assert "jsonb_typeof(alcance) IS DISTINCT FROM 'object'" in checks
    assert "jsonb_typeof(supuestos) IS DISTINCT FROM 'array'" in checks
    assert "jsonb_typeof(limitaciones) IS DISTINCT FROM 'array'" in checks
    assert "jsonb_typeof(referencias) IS DISTINCT FROM 'array'" in checks
    assert "FROM analytics.evidence_claim vigente" in compacto
    assert "analytics.evidence_claim_history historico" in compacto
    assert "historico.run_id = vigente.run_id" in compacto
    assert "historico.claim_id IS NULL" in checks
