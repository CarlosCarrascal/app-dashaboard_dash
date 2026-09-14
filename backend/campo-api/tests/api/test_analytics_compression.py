import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from aquanqa_campo_api.api.analytics_compression import AnalyticsCompressionMiddleware


@pytest.mark.parametrize('path', ['/v1/admin/evaluaciones/analitica', '/v1/admin/evaluaciones/analitica/tendencia'])
def test_analytical_payload_is_identical_with_compression(path):
    app = FastAPI()
    payload = {'lots': [{'label': 'Lote de prueba', 'median': 0, 'missing': None}] * 100}
    app.add_api_route(path, lambda: payload)
    app.add_middleware(AnalyticsCompressionMiddleware)
    with TestClient(app) as client:
        plain = client.get(path, headers={'Accept-Encoding': 'identity'})
        compressed = client.get(path, headers={'Accept-Encoding': 'gzip'})
    assert compressed.json() == plain.json() == payload
    assert compressed.headers['content-encoding'] == 'gzip'
    assert 'Accept-Encoding' in compressed.headers['vary']
    assert int(compressed.headers['content-length']) < len(plain.content) / 2
    assert 'content-encoding' not in plain.headers


@pytest.mark.parametrize('path', ['/v1/admin/evaluaciones/exportar', '/v1/auth/login'])
def test_unrelated_responses_are_untouched(path):
    app = FastAPI()
    app.add_api_route(path, lambda: {'value': 'x' * 3000})
    app.add_middleware(AnalyticsCompressionMiddleware)
    with TestClient(app) as client:
        result = client.get(path, headers={'Accept-Encoding': 'gzip'})
    assert 'content-encoding' not in result.headers


def test_small_response_with_custom_prefix_remains_uncompressed():
    app = FastAPI()
    app.add_api_route('/api/admin/evaluaciones/analitica', lambda: {'lots': []})
    app.add_middleware(AnalyticsCompressionMiddleware, api_prefix='/api/')
    with TestClient(app) as client:
        result = client.get('/api/admin/evaluaciones/analitica', headers={'Accept-Encoding': 'gzip'})
    assert result.json() == {'lots': []}
    assert 'content-encoding' not in result.headers
