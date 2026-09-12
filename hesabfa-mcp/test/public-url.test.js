import test from 'node:test';
import assert from 'node:assert/strict';
import { publicBaseUrl } from '../src/public-url.js';

const origin = 'https://hesabfa-readonly-mcp.onrender.com';

test('public origin defaults correctly and accepts a secure custom origin', () => {
  assert.equal(publicBaseUrl({}), origin);
  assert.equal(publicBaseUrl({ PUBLIC_BASE_URL: '' }), origin);
  assert.equal(publicBaseUrl({ PUBLIC_BASE_URL: `${origin}/` }), origin);
  assert.equal(publicBaseUrl({ PUBLIC_BASE_URL: 'https://connector.example:8443/' }),
    'https://connector.example:8443');
});

test('copied credentials and malformed origins cannot reach public responses or logs', () => {
  const values = [
    "curl --url 'https://core.hesabfa.com/api/report/getUserLog' -b 'API-TOKEN=fixture-secret'",
    'https://name:fixture-secret@example.com',
    'https://example.com/?token=fixture-secret',
    'https://example.com/#fixture-secret',
    'https://example.com/fixture-secret',
    'https://example.com\nfixture-secret',
    'http://example.com',
    'not-a-url',
    42
  ];
  for (const value of values) {
    const messages = [];
    assert.equal(publicBaseUrl({ PUBLIC_BASE_URL: value }, message => messages.push(message)), origin);
    assert.equal(messages.length, 1);
    assert.doesNotMatch(messages[0], /fixture-secret|core\.hesabfa|API-TOKEN/);
  }
});
