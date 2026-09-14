export const UPSTREAM = 'https://d28iujqq12ix9m.cloudfront.net';
const isApi = path => path === '/v1' || path.startsWith('/v1/') || ['/docs', '/docs/oauth2-redirect', '/redoc', '/openapi.json'].includes(path);

export async function handle(request, env, upstreamFetch = fetch) {
  const url = new URL(request.url);
  if (!isApi(url.pathname)) return env.ASSETS.fetch(request);
  const target = new URL(url.pathname + url.search, UPSTREAM);
  const headers = new Headers(request.headers);
  headers.delete('host');
  const forwarded = new Request(target, {
    method: request.method, headers, redirect: 'manual',
    ...(!['GET', 'HEAD'].includes(request.method) ? { body: request.body, duplex: 'half' } : {}),
  });
  const response = await upstreamFetch(forwarded);
  const outgoing = new Headers(response.headers);
  outgoing.set('Cache-Control', 'no-store');
  outgoing.set('X-Aquanqa-Backend', 'aws');
  const location = outgoing.get('location');
  if (location) {
    const redirect = new URL(location, target);
    if (redirect.origin === UPSTREAM) outgoing.set('location', url.origin + redirect.pathname + redirect.search + redirect.hash);
  }
  if (url.pathname === '/openapi.json' && response.ok && request.method === 'GET') {
    const schema = await response.json();
    schema.servers = [{ url: '/', description: 'API AWS mediante Cloudflare Pages' }];
    outgoing.delete('content-length');
    outgoing.delete('content-encoding');
    outgoing.delete('etag');
    return new Response(JSON.stringify(schema), { status: response.status, headers: outgoing });
  }
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers: outgoing });
}

export default { fetch(request, env) { return handle(request, env); } };
