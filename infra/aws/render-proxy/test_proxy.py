import importlib.util
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

spec=importlib.util.spec_from_file_location('proxy',Path(__file__).with_name('app.py'))
proxy=importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


def test_mutation_preserves_method_body_auth_query_and_status():
    observed=[]
    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"id":"example"}'
    def handle(request):
        observed.append((request.method,str(request.url),request.headers['authorization'],request.read()))
        return httpx.Response(201,stream=Body(),headers={'Content-Type':'application/json','Set-Cookie':'session=test; Secure; HttpOnly'})
    app=proxy.create_app('https://example.cloudfront.net',httpx.MockTransport(handle))
    with TestClient(app) as client:
        r=client.post('/v1/evaluaciones?x=1',content=b'{"id":"example"}',headers={'Authorization':'Bearer test','Content-Type':'application/json'})
        assert r.status_code==201
        assert r.json()=={'id':'example'}
        assert r.headers['x-aquanqa-backend']=='aws'
        assert r.headers['set-cookie']=='session=test; Secure; HttpOnly'
    assert observed==[('POST','https://example.cloudfront.net/v1/evaluaciones?x=1','Bearer test',b'{"id":"example"}')]


def test_failure_is_retryable_without_replaying_a_mutation():
    calls=[]
    def handle(request):
        calls.append(request.method)
        raise httpx.ConnectError('unavailable',request=request)
    with TestClient(proxy.create_app('https://example.cloudfront.net',httpx.MockTransport(handle))) as client:
        r=client.post('/v1/evaluaciones',json={'id':'example'})
        assert r.status_code==503
        assert r.headers['retry-after']=='15'
    assert calls==['POST']
