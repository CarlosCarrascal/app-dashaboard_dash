import { test } from 'node:test';
import assert from 'node:assert/strict';
import { handle, UPSTREAM } from './worker.mjs';

test('writes preserve body, authorization, query and error status without retries', async () => {
  let calls = 0;
  const result = await handle(new Request('https://example.pages.dev/v1/evaluaciones?a=1', {
    method: 'POST', headers: { Authorization: 'Bearer test', 'Content-Type': 'application/json' }, body: '{"test":true}',
  }), {}, async request => {
    calls++;
    assert.equal(request.url, UPSTREAM + '/v1/evaluaciones?a=1');
    assert.equal(request.method, 'POST');
    assert.equal(request.headers.get('authorization'), 'Bearer test');
    assert.equal(await request.text(), '{"test":true}');
    assert.equal(request.redirect, 'manual');
    return new Response('unavailable', { status: 503 });
  });
  assert.equal(calls, 1);
  assert.equal(result.status, 503);
  assert.equal(await result.text(), 'unavailable');
  assert.equal(result.headers.get('cache-control'), 'no-store');
});

test('SPA routes use assets and never proxy arbitrary paths', async () => {
  const result = await handle(new Request('https://example.pages.dev/login'), {
    ASSETS: { fetch: async () => new Response('angular') },
  }, () => { throw new Error('Unexpected upstream fetch'); });
  assert.equal(await result.text(), 'angular');
});

test('upstream redirects stay on the new site without following them', async () => {
  const result = await handle(new Request('https://example.pages.dev/v1/test'), {}, async () =>
    new Response(null, { status: 307, headers: { location: UPSTREAM + '/v1/test/' } }));
  assert.equal(result.status, 307);
  assert.equal(result.headers.get('location'), 'https://example.pages.dev/v1/test/');
});

test('Swagger uses the same origin and keeps API schema', async () => {
  const result = await handle(new Request('https://example.pages.dev/openapi.json'), {}, async () =>
    Response.json({ openapi: '3.1.0', paths: { '/v1/test': {} }, servers: [{ url: UPSTREAM }] }));
  const schema = await result.json();
  assert.equal(schema.servers[0].url, '/');
  assert.ok(schema.paths['/v1/test']);
});
