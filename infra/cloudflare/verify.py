"""Read-only checks against the Pages deployment; credentials stay in memory."""
import json
from pathlib import Path
import sys
import time
from uuid import uuid4
import requests
import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'infra/aws'))
sys.path.insert(0, str(ROOT / 'backend/campo-api/src'))
from backup import render_config
from aquanqa_campo_api.core.security import encode_token

base = 'https://aquanqa.pages.dev'
_, _, env = render_config()
with psycopg.connect(env['AQUANQA_API_DATABASE_URL']) as connection:
    connection.execute('SET TRANSACTION READ ONLY')
    user = connection.execute('SELECT usuario_id FROM core.m_usuario WHERE activo ORDER BY usuario_id LIMIT 1').fetchone()[0]
token = encode_token({'sub': str(user), 'typ': 'access', 'iat': int(time.time()), 'exp': int(time.time()) + 900, 'jti': str(uuid4())}, env['AQUANQA_JWT_SECRET'])
checks = []
for path in ['/v1/health/ready', '/v1/auth/me', '/v1/catalogos/fundos', '/v1/admin/evaluaciones?page_size=1', '/v1/admin/cargas?page_size=1', '/docs', '/openapi.json']:
    response = requests.get(base + path, headers={'Authorization': 'Bearer ' + token}, timeout=90)
    assert response.status_code == 200, (path, response.status_code)
    assert response.headers.get('X-Aquanqa-Backend') == 'aws', path
    assert response.headers.get('Cache-Control') == 'no-store', path
    if path == '/openapi.json':
        assert response.json()['servers'][0]['url'] == '/'
    checks.append({'path': path, 'status': response.status_code})
    print(path + ': PASS', flush=True)
response = requests.get(base + '/v1/admin/evaluaciones', timeout=60)
assert response.status_code == 401
checks.append({'path': '/v1/admin/evaluaciones (unauthenticated)', 'status': 401})
for origin in [base, 'https://d28iujqq12ix9m.cloudfront.net']:
    response = requests.get(origin + '/login', timeout=60)
    assert response.status_code == 200 and '<app-root' in response.text
    print(origin + '/login: PASS', flush=True)
report = {'frontend': base + '/login', 'api': base + '/v1', 'docs': base + '/docs', 'upstream': 'https://d28iujqq12ix9m.cloudfront.net', 'database': 'AWS RDS aquanqa-production / aquanqa_live (unchanged)', 'checks': checks, 'production_mutations': False}
Path(__file__).with_name('deployment.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
