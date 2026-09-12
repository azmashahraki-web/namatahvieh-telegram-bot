import test from 'node:test';
import assert from 'node:assert/strict';
import { userLogDiagnostics, verifyUserLogConnection } from '../src/user-log-check.js';

const env = { HESABFA_USER_LOG_CURL: "curl 'https://core.hesabfa.com/api/report/getUserLog' -H 'x-xsrf-token: synthetic-secret-xsrf' -H 'hesabfa-business-key: synthetic-secret-business' -b 'session=synthetic-secret-cookie' --data-raw '{}'" };

test('diagnostics identify a preflight request without disclosing its content', () => {
  const result = userLogDiagnostics({ HESABFA_USER_LOG_CURL: "curl 'https://core.hesabfa.com/api/report/getUserLog' -X 'OPTIONS' -H 'secret: synthetic-secret'" });
  assert.equal(result.method, 'OPTIONS');
  assert.equal(result.cookieField, false);
  assert.equal(result.configured, false);
  assert.equal(result.requestKind, 'USER_LOG_REPORT');
  assert.equal(result.reason, 'WRONG_METHOD');
  assert.doesNotMatch(JSON.stringify(result), /synthetic-secret/);
});

test('diagnostics distinguish the copied asset, report page, and report without exposing private URL data', () => {
  const cases = [
    ['https://app.hesabfa.com/styles.private-name.css?token=private-url-token', 'HESABFA_STYLESHEET'],
    ['https://app.hesabfa.com/app/private-business-key/users-log', 'HESABFA_REPORT_PAGE'],
    ['https://core.hesabfa.com/api/report/getUserLog?token=private-url-token', 'VARIANT_USER_LOG_URL'],
    ['https://private-user:private-password@core.hesabfa.com/api/report/getUserLog', 'INVALID_URL'],
    ['https://private-host.example/private-path', 'OTHER_HOST']
  ];
  for (const [url, kind] of cases) {
    const result = userLogDiagnostics({ HESABFA_USER_LOG_CURL: `curl '${url}' -b 'session=private-cookie'` });
    assert.equal(result.requestKind, kind);
    assert.equal(result.configured, false);
    assert.doesNotMatch(JSON.stringify(result), /private-|https:\/\//);
  }
  assert.equal(userLogDiagnostics(env).requestKind, 'USER_LOG_REPORT');
});

test('a configured live check queries recent Iran dates and logs no rows or credentials', async () => {
  const logs = [];
  const outcome = await verifyUserLogConnection({ env, now: new Date('2026-09-11T21:00:00Z'), log: x => logs.push(x),
    request: async (args, options) => {
      assert.equal(args.start, '2026-09-05');
      assert.equal(args.end, '2026-09-12');
      assert.equal(args.take, 1);
      assert.equal(options.env, env);
      return { data: [{ user: 'private-person', description: 'private-activity' }] };
    }
  });
  assert.equal(outcome.verified, true);
  assert.equal(outcome.hasRows, true);
  assert.doesNotMatch(logs.join('\n'), /synthetic-secret|private-person|private-activity/);
});

test('invalid settings avoid network calls and live errors never disclose error messages', async () => {
  const invalid = await verifyUserLogConnection({ env: {}, log: () => {}, request: () => assert.fail('unexpected network') });
  assert.equal(invalid.verified, false);
  const logs = [];
  const failure = await verifyUserLogConnection({ env, log: x => logs.push(x), request: async () => {
    throw Object.assign(new Error('private-error'), { code: 'private-error' });
  } });
  assert.equal(failure.code, 'USER_LOG_CHECK_FAILED');
  assert.doesNotMatch(logs.join('\n'), /private-error|synthetic-secret/);
});
