"""Retain the mobile app's existing Render URL after the AWS migration."""
from contextlib import asynccontextmanager
import os
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from starlette.background import BackgroundTask
from starlette.responses import JSONResponse, StreamingResponse

HOP_HEADERS = {b'host',b'connection',b'keep-alive',b'proxy-authenticate',b'proxy-authorization',b'te',b'trailer',b'transfer-encoding',b'upgrade'}


def create_app(upstream=None, transport=None):
    upstream = (upstream or os.environ['AQUANQA_UPSTREAM_URL']).rstrip('/')
    parsed = urlsplit(upstream)
    if parsed.scheme!='https' or not parsed.hostname.endswith('.cloudfront.net') or parsed.path:
        raise ValueError('Expected an HTTPS CloudFront origin without a path')

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(timeout=httpx.Timeout(90,connect=10),follow_redirects=False,transport=transport) as client:
            app.state.client=client
            yield

    app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)

    @app.api_route('/{path:path}',methods=['GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS'])
    async def forward(request: Request, path: str):
        target=upstream+request.url.path
        if request.url.query: target+='?'+request.url.query
        headers=[(k,v) for k,v in request.headers.raw if k.lower() not in HOP_HEADERS]
        outgoing=app.state.client.build_request(request.method,target,headers=headers,content=request.stream())
        try:
            response=await app.state.client.send(outgoing,stream=True)
        except httpx.RequestError:
            return JSONResponse({'detail':'El servicio está temporalmente ocupado; reintenta la sincronización.'},status_code=503,headers={'Retry-After':'15'})
        result=StreamingResponse(response.aiter_raw(),status_code=response.status_code,background=BackgroundTask(response.aclose))
        result.raw_headers=[(k,v) for k,v in response.headers.raw if k.lower() not in HOP_HEADERS]
        result.headers['X-Aquanqa-Backend']='aws'
        return result

    return app


if os.environ.get('AQUANQA_UPSTREAM_URL'):
    app=create_app()
