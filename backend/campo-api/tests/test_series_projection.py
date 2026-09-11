import os
from datetime import date
import pytest
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from aquanqa_campo_api.infrastructure.postgres.admin_queries import series_trend_sql
from aquanqa_campo_api.modules.admin.analytics import AnalyticsQuery, build_trend, build_series


def test_series_preserves_empty_dates_and_null_quantiles():
    q = AnalyticsQuery(module_key='flores', hasta=date(2026,8,22))
    points = build_series([dict(fecha=date(2026,8,20), evaluations=2, observations=0, excluded=0, n=0, quantiles=None)], q)
    assert len(points) == 3
    assert points[0].evaluations == 2
    assert points[0].distribution.median is None
    assert points[1].evaluations == 0
    assert build_series([],q) == []


@pytest.mark.db
@pytest.mark.parametrize('family', ['flores','brotes'])
def test_simple_sql_series_preserves_zero_null_and_invalid_counts(family):
    dsn = os.getenv('AQUANQA_TEST_READ_DSN')
    if not dsn:
        pytest.skip('Requires read-only PostgreSQL test connection')
    cte = """WITH evaluaciones AS (
      SELECT d::date fecha,v::double precision series_value FROM (VALUES
        ('2026-08-20','0'),('2026-08-20','2'),('2026-08-20',NULL),
        ('2026-08-21',NULL),('2026-08-21','-1'),('2026-08-21','NaN'),
        ('2026-08-21','Infinity')) input(d,v))"""
    with psycopg.connect(dsn,autocommit=True,row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute(series_trend_sql(cte,'TRUE',family,'n_flores',False))
            rows = cursor.fetchall()
    assert rows[0]['evaluations'] == 3 and rows[0]['n'] == 2
    assert rows[0]['quantiles'] == [.5,1,1.5]
    assert rows[1]['evaluations'] == 4 and rows[1]['n'] == 0
    assert rows[1]['quantiles'] is None
    assert all(r['observations'] == 0 and r['excluded'] == 0 for r in rows)


@pytest.mark.db
@pytest.mark.parametrize('family', ['baya','pesos','ramas'])
@pytest.mark.parametrize('state', [None,'X'])
def test_sql_series_matches_sample_rules_without_writing_database(family, state):
    dsn = os.getenv('AQUANQA_TEST_READ_DSN')
    if not dsn:
        pytest.skip('Requires read-only PostgreSQL test connection')
    samples = []
    for ordinal, measurement, diameter, weight, code, suspect in [
        (1,1,10,2,'X',False), (2,1,None,None,'X',False),
        (3,1,100,20,'X',False), (3,1,200,40,'Y',False),
        (4,2,300,60,'X',False), (5,1,5,1,'X',True),
        (6,1,0,0,None,False), (7,1,20,4,'X',False),
    ]:
        samples.append(dict(evaluacion_id=1,numero_muestra=ordinal,numero_rama=ordinal,
            numero_medicion=measurement,diametro_mm=diameter,peso_g=weight,estado_codigo=code,sospechoso=suspect))
    cte = """WITH test_samples AS (SELECT * FROM jsonb_to_recordset(%s::jsonb) AS s(
      evaluacion_id bigint,numero_muestra integer,numero_rama integer,numero_medicion integer,
      diametro_mm numeric,peso_g numeric,estado_codigo text,sospechoso boolean)),
      evaluaciones AS (SELECT 1::bigint source_id,DATE '2026-08-20' fecha)"""
    sql = series_trend_sql(cte,'TRUE',family,'n_flores',bool(state))
    sql = sql.replace('core.ev_fruto_observacion','test_samples').replace('core.ev_rama_observacion','test_samples')
    q = AnalyticsQuery(module_key=family,desde=date(2026,8,20),hasta=date(2026,8,22),estado=state)
    if family == 'ramas':
        detail = {'mediciones':[dict(nro_rama=s['numero_rama'],numero_medicion=s['numero_medicion'],diametro=s['diametro_mm'],sospechoso=s['sospechoso']) for s in samples]}
    else:
        detail = {'observaciones':[{k:v for k,v in s.items() if k not in ('sospechoso','numero_rama','evaluacion_id')} for s in samples]}
    expected = build_trend([dict(source_id=1,fecha=date(2026,8,20),detalle=detail)],q)
    with psycopg.connect(dsn,autocommit=True,row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql,[Jsonb(samples),state] if state else [Jsonb(samples)])
            actual = build_series(cursor.fetchall(),q)
    for a,b in zip(actual,expected,strict=True):
        assert (a.evaluations,a.observations,a.excluded)==(b.evaluations,b.observations,b.excluded)
        assert a.distribution.n == b.distribution.n
        assert a.distribution.median == b.distribution.median
        assert a.distribution.q1 == b.distribution.q1
        assert a.distribution.q3 == b.distribution.q3
