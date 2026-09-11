"""Compress bounded analytical JSON responses without buffering CSV exports."""

from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send


class AnalyticsCompressionMiddleware:
    def __init__(self, app: ASGIApp, api_prefix: str = '/v1') -> None:
        self.app = app
        self.compressed = GZipMiddleware(app, minimum_size=1024, compresslevel=3)
        base = api_prefix.rstrip('/') + '/admin/evaluaciones/analitica'
        self.paths = {base, base + '/tendencia'}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] == 'http' and scope['method'] == 'GET' and scope['path'] in self.paths:
            await self.compressed(scope, receive, send)
        else:
            await self.app(scope, receive, send)
