import test from 'node:test';
import assert from 'node:assert/strict';
import { USER_LOG_URL, readUserLogHeaders, userLogStatus, userLogPayload, getUserLogs } from '../src/user-logs.js';

// Synthetic test credentials only. Never use a captured real request in tests.
const copiedRequest = `curl '${USER_LOG_URL}' \\\n  -H 'accept: application/json' \\\n  -H 'hesabfa-business-key: test-business' \\\n  -H 'x-xsrf-token: test-xsrf' \\\n  -H 'host: forbidden.example' \\\n  -b 'session=test-cookie; csrf=test-cookie2' \\\n  --data-raw '{"start":"1990-01-01","loadOptions":{"take":999999}}'`;
const env = { HESABFA_USER_LOG_CURL: copiedRequest };
const args = { start: '2026-09-10', end: '2026-09-10' };
const row = { id: 7, dateTime: '2026-09-10T08:00:00', user: 'Test User', action: 100, title: 'Test', description: 'Synthetic activity' };

test('imports the required session headers from a copied browser request', () => {
  assert.deepEqual(readUserLogHeaders(env), {
    'hesabfa-business-key': 'test-business', 'x-xsrf-token': 'test-xsrf', cookie: 'session=test-cookie; csrf=test-cookie2'
  });
  const headerCookie = copiedRequest.replace("-b 'session=test-cookie; csrf=test-cookie2'", "-H 'Cookie: session=test-cookie; csrf=test-cookie2'");
  assert.equal(readUserLogHeaders({ HESABFA_USER_LOG_CURL: headerCookie }).cookie, 'session=test-cookie; csrf=test-cookie2');
});

test('preserves captured website Authorization only for the fixed report endpoint', async () => {
  const authorization = 'basic synthetic-browser-auth';
  const websiteEnv = { ...env,
    HESABFA_USER_LOG_CURL: copiedRequest + ` -H 'Authorization: ${authorization}'`,
    HESABFA_API_KEY: 'synthetic-public-api-key',
    HESABFA_LOGIN_TOKEN: 'synthetic-public-login-token'
  };
  assert.equal(readUserLogHeaders(websiteEnv).authorization, authorization);
  await getUserLogs(args, { env: websiteEnv, fetchImpl: async (url, options) => {
    assert.equal(url, USER_LOG_URL);
    assert.equal(options.headers.authorization, authorization);
    assert.equal(options.redirect, 'error');
    assert.equal(options.headers.host, undefined);
    assert.doesNotMatch(JSON.stringify(options), /synthetic-public/);
    return new Response(JSON.stringify({ data: [row], totalCount: 1 }));
  } });
  assert.doesNotMatch(JSON.stringify(userLogStatus(websiteEnv)), /synthetic-browser-auth|synthetic-public/);
  for (const raw of [
    websiteEnv.HESABFA_USER_LOG_CURL + " -H 'authorization: duplicate-private-auth'",
    websiteEnv.HESABFA_USER_LOG_CURL.replace(authorization, authorization + '\r\ninjected: private-auth'),
    websiteEnv.HESABFA_USER_LOG_CURL.replace(USER_LOG_URL, 'https://example.com/getUserLog')
  ]) assert.throws(() => readUserLogHeaders({ HESABFA_USER_LOG_CURL: raw }),
    error => error.code === 'USER_LOG_CONFIG_INVALID' && !/synthetic-browser-auth|private-auth/.test(error.message));
});

test('rejects other destinations, additional commands, file options and missing session headers', () => {
  for (const raw of [
    copiedRequest.replace(USER_LOG_URL, 'https://example.com/api/report/getUserLog'),
    copiedRequest + ' ; echo test',
    copiedRequest + ' --config /tmp/config',
    copiedRequest.replace('-H \'x-xsrf-token: test-xsrf\'', ''),
    copiedRequest.replace('test-xsrf', 'test-xsrf\r\ninjected: secret'),
    copiedRequest + " -H 'cookie: duplicate=secret'",
    copiedRequest.replace("curl '", "curl 'broken")
  ]) assert.throws(() => readUserLogHeaders({ HESABFA_USER_LOG_CURL: raw }), { code: 'USER_LOG_CONFIG_INVALID' });
});

test('configuration status is explicit, contains no secrets and does not claim live verification', () => {
  assert.equal(userLogStatus({}).code, 'USER_LOG_SESSION_REQUIRED');
  assert.equal(userLogStatus(env).configured, true);
  assert.equal(userLogStatus(env).liveVerified, false);
  assert.doesNotMatch(JSON.stringify(userLogStatus(env)), /test-cookie|test-xsrf|test-business/);
});

test('Iran calendar days have correct UTC boundaries and supplied timestamps retain their instant', () => {
  const p = userLogPayload(args);
  assert.equal(p.start, '2026-09-09T20:30:00.000Z');
  assert.equal(p.end, '2026-09-10T20:29:59.999Z');
  assert.equal(userLogPayload({ start: '2026-09-10T08:00:00', end: '2026-09-10T09:00:00+03:30' }).start, '2026-09-10T04:30:00.000Z');
  assert.equal(userLogPayload({ start: '2026-09-10T08:00:00Z', end: '2026-09-10T09:00:00Z' }).start, '2026-09-10T08:00:00.000Z');
});

test('invalid dates, Persian year input, reversed ranges and oversized requests are rejected', () => {
  for (const overrides of [
    { start: '1405-06-20' }, { start: '2026-02-30' }, { start: '2026-09-10T25:00:00Z' },
    { start: '2026-09-11' }, { start: '2026-08-01' }, { take: 101 }, { skip: -1 }, { userId: {} }
  ]) assert.throws(() => userLogPayload({ ...args, ...overrides }));
  assert.equal(userLogPayload({ start: '2026-09-01', end: '2026-10-01' }).end, '2026-10-01T20:29:59.999Z');
});

test('uses the fixed read-only endpoint, current query and complete pagination metadata', async () => {
  const result = await getUserLogs({ ...args, take: 1, skip: 5, userId: 'selected-user' }, { env,
    fetchImpl: async (url, options) => {
      assert.equal(url, USER_LOG_URL);
      assert.equal(options.method, 'POST');
      assert.equal(options.redirect, 'error');
      assert.equal(options.headers.host, undefined);
      assert.equal(options.headers.authorization, undefined);
      const body = JSON.parse(options.body);
      assert.equal(body.userId, 'selected-user');
      assert.equal(body.start, '2026-09-09T20:30:00.000Z');
      assert.deepEqual(body.loadOptions, { skip: 5, take: 1, requireTotalCount: true, sort: [{ selector: 'logDateTime', desc: true }] });
      assert.equal(body.apiKey, undefined);
      assert.equal(body.loginToken, undefined);
      return new Response(JSON.stringify({ data: [{ ...row, internal: 'omit' }], totalCount: 8 }));
    }
  });
  assert.deepEqual(result.data, [row]);
  assert.equal(result.nextSkip, 6);
  assert.equal(result.totalCount, 8);
});

test('valid empty and final pages terminate pagination', async () => {
  for (const payload of [{ data: [], totalCount: 0 }, { data: [row], totalCount: 1 }]) {
    const result = await getUserLogs(args, { env, fetchImpl: async () => new Response(JSON.stringify(payload)) });
    assert.equal(result.nextSkip, null);
  }
});

test('expired or unauthorized sessions cannot become empty activity reports or expose body text', async () => {
  for (const status of [401, 403]) await assert.rejects(
    getUserLogs(args, { env, fetchImpl: async () => new Response('secret-response-test-cookie', { status }) }),
    error => error.code === 'USER_LOG_SESSION_EXPIRED_OR_FORBIDDEN' && error.httpStatus === status && !error.message.includes('test-cookie')
  );
});

test('network failures, server errors and redirects never expose captured credentials', async () => {
  await assert.rejects(getUserLogs(args, { env, fetchImpl: async () => { throw new Error('redirect: test-cookie'); } }),
    error => error.code === 'USER_LOG_CONNECTION_FAILED' && !error.message.includes('test-cookie'));
  await assert.rejects(getUserLogs(args, { env, fetchImpl: async () => new Response('test-cookie', { status: 500 }) }),
    error => error.code === 'USER_LOG_HTTP_ERROR' && !error.message.includes('test-cookie'));
});

test('unexpected login pages, error envelopes and inconsistent pagination fail explicitly', async () => {
  for (const body of [
    '<html>login test-cookie</html>', '{}', '{"data":[],"totalCount":3}',
    '{"data":[],"totalCount":"0"}', '{"Success":false,"ErrorMessage":"test-cookie"}',
    JSON.stringify({ data: [row], totalCount: 0 }),
    JSON.stringify({ data: [{}], totalCount: 1 })
  ]) await assert.rejects(getUserLogs(args, { env, fetchImpl: async () => new Response(body) }),
    error => error.code === 'USER_LOG_RESPONSE_INVALID' && !error.message.includes('test-cookie'));
});

test('a missing session makes no external request', async () => {
  await assert.rejects(getUserLogs(args, { env: {}, fetchImpl: () => assert.fail('must not call network') }),
    { code: 'USER_LOG_SESSION_REQUIRED' });
});
