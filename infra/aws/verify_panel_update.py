"""Read-only SQL and HTTP checks for the dashboard update, using AWS credentials."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from datetime import date, timedelta
from uuid import uuid4
import psycopg
import requests
from deploy import ROOT, session, outputs, load

sys.path.insert(0, str(ROOT / 'backend/campo-api/src'))
from aquanqa_campo_api.core.security import encode_token
from aquanqa_campo_api.infrastructure.postgres.connection import PostgresConnectionFactory
from aquanqa_campo_api.infrastructure.postgres.admin_repository import PostgresAdminRepository
from aquanqa_campo_api.modules.admin.schemas import AdminEvaluationQuery
from aquanqa_campo_api.modules.admin.weekly_report import WeeklyReportQuery

p = argparse.ArgumentParser()
p.add_argument('--http', action='store_true')
args = p.parse_args()
s = session()
o = outputs(s)
folder = Path(os.environ['APPDATA']) / 'Aquanqa/pgadmin'
dsn = psycopg.conninfo.make_conninfo(host=o['DbHost'], dbname='aquanqa_live', user='aquanqa_consulta', passfile=str(folder/'pgpass.conf'), sslmode='verify-full', sslrootcert=str(folder/'us-east-1-bundle.pem'), connect_timeout=15)
factory = PostgresConnectionFactory(dsn)
repo = PostgresAdminRepository(factory)
try:
    counts = repo.evaluation_counts(AdminEvaluationQuery())
    with psycopg.connect(dsn) as c:
        user = c.execute("SELECT u.usuario_id FROM core.m_usuario u JOIN core.m_rol r USING (rol_id) WHERE u.activo AND r.codigo='admin' ORDER BY u.usuario_id LIMIT 1").fetchone()[0]
        expected = c.execute("SELECT count(*) FROM core.ev_evaluacion WHERE estado_registro='vigente'").fetchone()[0]
    assert counts.total == expected
    assert sum(item.total for item in counts.por_modulo) == counts.total
    assert repo.evaluation_counts(AdminEvaluationQuery(fundo_id=2147483647)).total == 0
    assert PostgresAdminRepository(factory, usuario_id=2147483647, unrestricted=False).evaluation_counts(AdminEvaluationQuery()).total == 0
    for metric in ['n_flores', 'cuajo']:
        assert repo.weekly_report(WeeklyReportQuery(metric=metric)).points
    assert not PostgresAdminRepository(factory, usuario_id=2147483647, unrestricted=False).weekly_report(WeeklyReportQuery()).points
    print('SQL counts, empty filter and user scope: PASS', flush=True)
finally:
    factory.close()
if args.http:
    secret = json.loads(s.client('secretsmanager').get_secret_value(SecretId=load('app-secret')['arn'])['SecretString'])
    token = encode_token({'sub':str(user), 'typ':'access', 'iat':int(time.time()), 'exp':int(time.time())+600, 'jti':str(uuid4())}, secret['jwt'])
    paths = ['/v1/health/ready','/v1/auth/me','/v1/admin/evaluaciones/conteos','/v1/admin/qa/resumen','/v1/admin/maestros/fundos','/v1/admin/evaluaciones?page_size=1','/v1/admin/cargas?page_size=1','/openapi.json']
    for base in ['https://d28iujqq12ix9m.cloudfront.net','https://aquanqa.pages.dev','https://aquanqa-campo-api.onrender.com']:
        for path in paths:
            response = requests.get(base+path, headers={'Authorization':'Bearer '+token}, timeout=90)
            assert response.status_code == 200, (base,path,response.status_code)
            if path == '/openapi.json': assert '/v1/admin/evaluaciones/conteos' in response.json()['paths']
        assert requests.get(base+'/v1/admin/evaluaciones/conteos', timeout=30).status_code == 401
        report_path = '/v1/admin/evaluaciones/informe-semanal'
        for metric in ['n_flores', 'cuajo']:
            report = requests.get(base+report_path, params={'metric':metric}, headers={'Authorization':'Bearer '+token}, timeout=90)
            assert report.status_code == 200, (base, metric, report.status_code)
            assert report.json()['points'], (base, metric, 'empty weekly report')
            deck = requests.get(base+report_path+'/pptx', params={'metric':metric}, headers={'Authorization':'Bearer '+token}, timeout=90)
            assert deck.status_code == 200, (base, metric, 'pptx', deck.status_code)
            with ZipFile(BytesIO(deck.content)) as archive:
                assert archive.testzip() is None
                assert 'ppt/presentation.xml' in archive.namelist()
                content_types = ET.fromstring(archive.read('[Content_Types].xml'))
                charts = [item.get('PartName').lstrip('/') for item in content_types if item.get('ContentType', '').endswith('drawingml.chart+xml')]
                assert charts and all(name in archive.namelist() for name in charts)
        assert requests.get(base+report_path, timeout=30).status_code == 401
        print(base + ': weekly reports and PowerPoint exports PASS', flush=True)
        print(base + ': authenticated routes and anonymous denial PASS', flush=True)
    for module in ['estadios','flores','brotes','ramas','baya','pesos']:
        base = 'https://aquanqa.pages.dev/v1/admin/evaluaciones'
        response=requests.get(base+'/analitica',params={'module_key':module,'snapshot':'true','include_trend':'false'},headers={'Authorization':'Bearer '+token},timeout=90)
        assert response.status_code==200,(module,'snapshot',response.status_code)
        snapshot=response.json()
        if snapshot.get('hasta') and snapshot.get('grano'):
            end=date.fromisoformat(snapshot['hasta'])
            params={'module_key':module,'series_only':'true','grano':snapshot['grano'],'desde':str(end-timedelta(days=83)),'hasta':str(end)}
            response=requests.get(base+'/analitica/tendencia',params=params,headers={'Authorization':'Bearer '+token},timeout=90)
            assert response.status_code==200,(module,'trend',response.status_code)
        print(module+': dashboard snapshot and trend PASS',flush=True)
