from contextlib import contextmanager
from datetime import date
import os
import pytest

from aquanqa_campo_api.infrastructure.postgres.admin_repository import PostgresAdminRepository
from aquanqa_campo_api.infrastructure.postgres.admin_queries import analytics_rows_sql, unpack_analytics_rows
from aquanqa_campo_api.modules.admin.analytics import AnalyticsQuery


def test_packed_measurements_preserve_zero_null_and_evaluation_identity():
    groups = [{"fecha": date(2026, 8, 26), "lote_id": 12, "fundo": "F", "modulo": "M", "lote": "L",
               "measurements": [[10, 0, None, 2, 3, 4], [11, 1, 2, 3, 4, 5]]}]
    rows = unpack_analytics_rows(groups, "estadios")
    assert [row["source_id"] for row in rows] == [10, 11]
    assert rows[0]["detalle"] == {"e1": 0, "e2": None, "e3": 2, "e4": 3, "e5": 4}
    assert rows[1]["lote_id"] == 12


@pytest.mark.parametrize('with_series', [False, True])
def test_fast_snapshot_limits_measurements_to_effective_date_and_keeps_history_window(with_series):
    class Database:
        def __init__(self):
            self.calls = []

        @contextmanager
        def read(self):
            yield self

        @contextmanager
        def cursor(self):
            yield self

        def execute(self, sql, params):
            self.calls.append((sql, params))

        def fetchone(self):
            return {'available': [{'grano':'registro_access','fecha':'2026-08-26','n':10}],
                    'groups':[{'fecha':'2026-08-26','lote_id':12,'fundo':'F','modulo':'M','lote':'L',
                               'measurements':[[10,0,0,2,3,5]]}],
                    'trend':[{'fecha':'2026-08-26','evaluations':1,'complete':1,'e1':0,'e2':0,'e3':2,'e4':3,'e5':5}]}

    database = Database()
    result = PostgresAdminRepository(database).evaluation_analytics(
        AnalyticsQuery(module_key="estadios", include_trend=False, snapshot_series=with_series)
    )
    assert len(database.calls) == 1
    assert 'fecha=(SELECT fecha FROM chosen)' in database.calls[0][0]
    assert 'grano=(SELECT grano FROM chosen)' in database.calls[0][0]
    assert result.summary.evaluations == 1
    assert result.summary.categories["E5"] == 5
    if with_series:
        assert len(result.trend) == 1
        assert result.trend[0].categories['E5'] == 5
    else:
        assert result.trend == []
    assert result.trend_desde == date(2026, 7, 28)


def test_nested_compact_samples_preserve_zeros_nulls_and_conflicts():
    groups = [{"fecha": date(2026,8,26), "lote_id":1, "fundo":"F", "modulo":"M", "lote":"L", "measurements":[[1, [[1, 1, 0, None, "X"], [1, 2, 10, 0, None]]]]}]
    rows = unpack_analytics_rows(groups, "baya")
    assert rows[0]["detalle"]["observaciones"] == [
        {"numero_muestra":1,"numero_medicion":1,"diametro_mm":0,"peso_g":None,"estado_codigo":"X"},
        {"numero_muestra":1,"numero_medicion":2,"diametro_mm":10,"peso_g":0,"estado_codigo":None},
    ]

@pytest.mark.parametrize('count', [0, 1, 3])
def test_column_packing_preserves_constants_nulls_and_conflicting_ordinals(count):
    samples = [[1,1,0,None,'X'],[1,2,10,None,None],[3,1,None,None,'X']][:count]
    columns = [[s[i] for s in samples] for i in range(5)]
    packed = [count, *[c[0] if c and all(v == c[0] for v in c) else c for c in columns]]
    common = dict(fecha=date(2026,8,26),lote_id=1,fundo='F',modulo='M',lote='L')
    legacy = unpack_analytics_rows([{**common,'measurements':[[7,samples]]}], 'baya')
    actual = unpack_analytics_rows([{**common,'measurements':[[7,{'columns':packed}]]}], 'baya')
    assert actual == legacy

@pytest.mark.db
def test_sql_column_packing_roundtrips_mixed_nulls_weight_zero_and_empty_evaluations():
    import psycopg
    from psycopg.rows import dict_row
    dsn = os.getenv('AQUANQA_TEST_READ_DSN')
    if not dsn:
        pytest.skip('Requires read-only PostgreSQL connection')
    cte = """WITH test_samples(evaluacion_id,numero_muestra,numero_medicion,diametro_mm,peso_g,estado_codigo) AS (
      VALUES (1,1,1,10.0,0.0,'X'),(1,1,2,NULL,2.0,NULL),(1,3,1,5.0,NULL,'X'),
             (2,1,1,NULL,NULL,NULL)
    ), evaluaciones AS (
      SELECT x.evaluacion_id source_id,DATE '2026-08-20' fecha,1 lote_id,
        'F' fundo,'M' modulo,'L' lote,'{}'::jsonb detalle
      FROM (VALUES (1),(2),(3)) x(evaluacion_id))"""
    sql = analytics_rows_sql(cte,'TRUE','pesos').replace('core.ev_fruto_observacion','test_samples')
    with psycopg.connect(dsn,autocommit=True,row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            rows=unpack_analytics_rows(cursor.fetchall(),'pesos')
    samples=rows[0]['detalle']['observaciones']
    assert [s['numero_muestra'] for s in samples] == [1,1,3]
    assert [s['numero_medicion'] for s in samples] == [1,2,1]
    assert [s['peso_g'] for s in samples] == [0,2,None]
    assert [s['estado_codigo'] for s in samples] == ['X',None,'X']
    assert rows[1]['detalle']['observaciones'][0]['diametro_mm'] is None
    assert rows[2]['detalle']['observaciones'] == []
