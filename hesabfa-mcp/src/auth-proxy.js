import express from 'express';
import crypto from 'node:crypto';
import http from 'node:http';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const PORT = Number(process.env.PORT || 3000);
const INTERNAL_PORT = 3001;
const BASE = String(process.env.PUBLIC_BASE_URL || 'https://hesabfa-readonly-mcp.onrender.com').replace(/\/+$/, '');
const RESOURCE = `${BASE}/mcp`;
const SCOPE = 'hesabfa:read';
const ACCESS_TTL = 60 * 60 * 12;
const REFRESH_TTL = 60 * 60 * 24 * 90;
const CODE_TTL = 5 * 60;
const bootNonce = crypto.randomBytes(24).toString('base64url');
const usedCodes = new Set();

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const localOnlyPreload = path.join(__dirname, 'force-localhost.cjs');

function boolEnv(name, fallback = false) {
  const value = process.env[name];
  if (value == null) return fallback;
  return String(value).toLowerCase() === 'true';
}
function signingKey() {
  if (!process.env.OAUTH_SIGNING_SECRET) throw new Error('OAuth signing secret is not configured.');
  return Buffer.from(process.env.OAUTH_SIGNING_SECRET, 'utf8');
}
function safeEq(a, b) {
  const x = Buffer.from(String(a ?? ''), 'utf8');
  const y = Buffer.from(String(b ?? ''), 'utf8');
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}
function b64json(v) { return Buffer.from(JSON.stringify(v), 'utf8').toString('base64url'); }
function parseB64(v) { return JSON.parse(Buffer.from(v, 'base64url').toString('utf8')); }
function sign(payload, stable = true) {
  const body = b64json(payload);
  const key = stable ? signingKey() : Buffer.concat([signingKey(), Buffer.from(bootNonce)]);
  const sig = crypto.createHmac('sha256', key).update(body).digest('base64url');
  return `${body}.${sig}`;
}
function verify(token, stable = true) {
  const [body, sig, extra] = String(token || '').split('.');
  if (!body || !sig || extra) throw new Error('Malformed token.');
  const key = stable ? signingKey() : Buffer.concat([signingKey(), Buffer.from(bootNonce)]);
  const expected = crypto.createHmac('sha256', key).update(body).digest('base64url');
  if (!safeEq(sig, expected)) throw new Error('Invalid token signature.');
  const p = parseB64(body);
  if (p.exp && Number(p.exp) < Math.floor(Date.now() / 1000)) throw new Error('Token expired.');
  return p;
}
function validRedirect(uri) {
  try {
    const u = new URL(uri);
    return u.protocol === 'https:' && u.hostname === 'chatgpt.com' &&
      (u.pathname === '/connector_platform_oauth_redirect' ||
       /^\/connector\/oauth\/[A-Za-z0-9_-]+$/.test(u.pathname));
  } catch { return false; }
}
function normalizeScope(value) {
  const scopes = String(value || SCOPE).split(/\s+/).filter(Boolean);
  if (!scopes.length) scopes.push(SCOPE);
  if (scopes.some((s) => s !== SCOPE)) throw new Error('Unsupported OAuth scope.');
  return [...new Set(scopes)].join(' ');
}
function makeClient(body) {
  const uris = Array.isArray(body?.redirect_uris) ? body.redirect_uris.filter(validRedirect) : [];
  if (!uris.length) throw new Error('No supported ChatGPT redirect URI was provided.');
  return `azma_${sign({ typ: 'client', redirect_uris: uris, iat: Math.floor(Date.now()/1000), v: 1 })}`;
}
function readClient(clientId) {
  if (!String(clientId || '').startsWith('azma_')) throw new Error('Unknown OAuth client.');
  const p = verify(String(clientId).slice(5));
  if (p.typ !== 'client' || !Array.isArray(p.redirect_uris)) throw new Error('Invalid OAuth client.');
  return p;
}
function accessToken(clientId, scope) {
  const now = Math.floor(Date.now()/1000);
  return sign({ typ:'access', iss:BASE, aud:RESOURCE, client_id:clientId, scope, iat:now, exp:now+ACCESS_TTL, jti:crypto.randomUUID() });
}
function refreshToken(clientId, scope) {
  const now = Math.floor(Date.now()/1000);
  return sign({ typ:'refresh', iss:BASE, aud:RESOURCE, client_id:clientId, scope, iat:now, exp:now+REFRESH_TTL, jti:crypto.randomUUID() });
}
function checkAccess(token) {
  const p = verify(token);
  if (p.typ !== 'access' || p.iss !== BASE || p.aud !== RESOURCE ||
      !String(p.scope || '').split(/\s+/).includes(SCOPE)) throw new Error('Invalid access token.');
  return p;
}
function authReady() {
  return Boolean(process.env.OAUTH_SIGNING_SECRET && process.env.CHATGPT_LINK_PASSWORD);
}
function esc(v) {
  return String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;')
    .replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
}
function params(src = {}) {
  return {
    response_type: src.response_type, client_id: src.client_id, redirect_uri: src.redirect_uri,
    scope: src.scope, state: src.state, code_challenge: src.code_challenge,
    code_challenge_method: src.code_challenge_method, resource: src.resource
  };
}
function validateAuthRequest(p) {
  if (!authReady()) throw new Error('Account linking is not configured yet.');
  if (p.response_type !== 'code') throw new Error('Only response_type=code is supported.');
  const client = readClient(p.client_id);
  if (!client.redirect_uris.includes(p.redirect_uri) || !validRedirect(p.redirect_uri)) throw new Error('Redirect URI mismatch.');
  if (p.code_challenge_method !== 'S256' || !p.code_challenge) throw new Error('PKCE S256 is required.');
  if (p.resource !== RESOURCE) throw new Error('Invalid OAuth resource.');
  return normalizeScope(p.scope);
}
function sendChallenge(res) {
  res.set('WWW-Authenticate', `Bearer resource_metadata="${BASE}/.well-known/oauth-protected-resource", scope="${SCOPE}"`);
  return res.status(401).json({ error: 'authentication_required' });
}

const child = spawn(process.execPath, [path.join(__dirname, 'index.js')], {
  env: {
    ...process.env,
    PORT: String(INTERNAL_PORT),
    MCP_ENABLED: 'true',
    NODE_OPTIONS: `${process.env.NODE_OPTIONS || ''} --require=${localOnlyPreload}`.trim()
  },
  stdio: ['ignore', 'inherit', 'inherit']
});
child.on('exit', (code, signal) => {
  console.error(`Internal MCP server exited (code=${code}, signal=${signal}).`);
  process.exit(code ?? 1);
});

const app = express();
app.disable('x-powered-by');

app.get('/', (_req, res) => res.type('text').send('Hesabfa Read-Only MCP Connector'));
app.get('/health', (_req, res) => res.json({
  ok: true,
  mcpEnabled: boolEnv('MCP_ENABLED', false),
  hesabfaCredentialsConfigured: Boolean(process.env.HESABFA_API_KEY && process.env.HESABFA_LOGIN_TOKEN),
  oauthSigningConfigured: Boolean(process.env.OAUTH_SIGNING_SECRET),
  linkPasswordConfigured: Boolean(process.env.CHATGPT_LINK_PASSWORD),
  internalMcpAlive: !child.killed,
  resource: RESOURCE
}));

app.get('/.well-known/oauth-protected-resource', (_req, res) => res.json({
  resource: RESOURCE,
  authorization_servers: [BASE],
  scopes_supported: [SCOPE],
  resource_documentation: BASE
}));
app.get('/.well-known/oauth-authorization-server', (_req, res) => res.json({
  issuer: BASE,
  authorization_response_iss_parameter_supported: true,
  authorization_endpoint: `${BASE}/oauth/authorize`,
  token_endpoint: `${BASE}/oauth/token`,
  registration_endpoint: `${BASE}/oauth/register`,
  response_types_supported: ['code'],
  grant_types_supported: ['authorization_code', 'refresh_token'],
  token_endpoint_auth_methods_supported: ['none'],
  code_challenge_methods_supported: ['S256'],
  scopes_supported: [SCOPE]
}));

app.post('/oauth/register', express.json({limit:'64kb'}), (req, res) => {
  try {
    const client_id = makeClient(req.body);
    const client = readClient(client_id);
    res.status(201).json({
      client_id, client_id_issued_at: Math.floor(Date.now()/1000),
      redirect_uris: client.redirect_uris, token_endpoint_auth_method: 'none',
      grant_types: ['authorization_code','refresh_token'], response_types:['code']
    });
  } catch (e) {
    res.status(400).json({ error:'invalid_client_metadata', error_description:e.message });
  }
});

app.get('/oauth/authorize', (req, res) => {
  const p = params(req.query);
  try { validateAuthRequest(p); }
  catch (e) { return res.status(400).send(`OAuth request rejected: ${esc(e.message)}`); }
  const hidden = Object.entries(p).filter(([,v]) => v != null)
    .map(([k,v]) => `<input type="hidden" name="${esc(k)}" value="${esc(v)}">`).join('\n');
  res.type('html').send(`<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Connect Hesabfa to ChatGPT</title><style>
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#f6f7f9;margin:0;padding:32px;color:#111}
.card{max-width:460px;margin:8vh auto;background:#fff;padding:28px;border-radius:16px;box-shadow:0 8px 30px #00000014}
h1{font-size:22px;margin:0 0 10px}p{line-height:1.5;color:#444}.scope{background:#f2f3f5;border-radius:9px;padding:10px 12px;font-size:14px}
input{width:100%;box-sizing:border-box;padding:12px;border:1px solid #bbb;border-radius:9px;font-size:16px;margin:10px 0 16px}
button{width:100%;padding:12px;border:0;border-radius:9px;background:#111;color:#fff;font-size:16px;cursor:pointer}
</style></head><body><div class="card"><h1>Connect Hesabfa to ChatGPT</h1>
<p>This private connector gives ChatGPT read-only access to your Hesabfa accounting data.</p>
<div class="scope">Permission: <strong>Read Hesabfa data</strong></div>
<form method="post" action="/oauth/authorize">${hidden}
<label>Connection password</label><input name="password" type="password" autocomplete="current-password" required autofocus>
<button type="submit">Authorize ChatGPT</button></form></div></body></html>`);
});

app.post('/oauth/authorize', express.urlencoded({extended:false,limit:'64kb'}), (req, res) => {
  const p = params(req.body);
  try {
    const scope = validateAuthRequest(p);
    if (!safeEq(req.body?.password, process.env.CHATGPT_LINK_PASSWORD)) throw new Error('Incorrect connection password.');
    const now = Math.floor(Date.now()/1000), jti = crypto.randomUUID();
    const code = sign({
      typ:'authorization_code', jti, client_id:p.client_id, redirect_uri:p.redirect_uri,
      code_challenge:p.code_challenge, resource:RESOURCE, scope, iat:now, exp:now+CODE_TTL
    }, false);
    const u = new URL(p.redirect_uri);
    u.searchParams.set('code', code);
    if (p.state) u.searchParams.set('state', p.state);
    u.searchParams.set('iss', BASE);
    return res.redirect(302, u.toString());
  } catch (e) {
    if (p.redirect_uri && validRedirect(p.redirect_uri)) {
      const u = new URL(p.redirect_uri);
      u.searchParams.set('error','access_denied');
      u.searchParams.set('error_description', e.message);
      if (p.state) u.searchParams.set('state', p.state);
      u.searchParams.set('iss', BASE);
      return res.redirect(302, u.toString());
    }
    return res.status(400).send(`Authorization failed: ${esc(e.message)}`);
  }
});

app.post('/oauth/token',
  express.urlencoded({extended:false,limit:'64kb'}), express.json({limit:'64kb'}),
  (req, res) => {
    try {
      const grant = req.body?.grant_type, clientId = req.body?.client_id;
      readClient(clientId);
      if (grant === 'authorization_code') {
        const p = verify(req.body?.code, false);
        if (p.typ !== 'authorization_code' || p.client_id !== clientId) throw new Error('Invalid authorization code.');
        if (usedCodes.has(p.jti)) throw new Error('Authorization code already used.');
        if (p.redirect_uri !== req.body?.redirect_uri) throw new Error('Redirect URI mismatch.');
        if (p.resource !== RESOURCE || (req.body?.resource && req.body.resource !== RESOURCE)) throw new Error('Resource mismatch.');
        const verifier = String(req.body?.code_verifier || '');
        if (!verifier) throw new Error('Missing PKCE code_verifier.');
        const challenge = crypto.createHash('sha256').update(verifier).digest('base64url');
        if (!safeEq(challenge, p.code_challenge)) throw new Error('PKCE verification failed.');
        usedCodes.add(p.jti); if (usedCodes.size > 2000) usedCodes.clear();
        const scope = normalizeScope(p.scope);
        return res.json({token_type:'Bearer',access_token:accessToken(clientId,scope),expires_in:ACCESS_TTL,
          refresh_token:refreshToken(clientId,scope),scope});
      }
      if (grant === 'refresh_token') {
        const p = verify(req.body?.refresh_token);
        if (p.typ !== 'refresh' || p.iss !== BASE || p.aud !== RESOURCE || p.client_id !== clientId) throw new Error('Invalid refresh token.');
        if (req.body?.resource && req.body.resource !== RESOURCE) throw new Error('Resource mismatch.');
        const scope = normalizeScope(p.scope);
        return res.json({token_type:'Bearer',access_token:accessToken(clientId,scope),expires_in:ACCESS_TTL,
          refresh_token:refreshToken(clientId,scope),scope});
      }
      throw new Error('Unsupported grant_type.');
    } catch (e) {
      res.status(400).json({error:'invalid_grant',error_description:e.message});
    }
  });

app.all('/mcp', (req, res) => {
  if (!boolEnv('MCP_ENABLED', false)) return res.status(503).json({error:'MCP endpoint is disabled.'});
  const h = String(req.headers.authorization || '');
  if (!h.startsWith('Bearer ')) return sendChallenge(res);
  try { checkAccess(h.slice(7)); } catch { return sendChallenge(res); }

  const headers = {...req.headers};
  delete headers.host; delete headers.authorization; delete headers['content-length'];
  const upstream = http.request({
    hostname:'127.0.0.1', port:INTERNAL_PORT, path:'/mcp', method:req.method, headers
  }, (up) => {
    res.status(up.statusCode || 502);
    for (const [k,v] of Object.entries(up.headers)) {
      if (v != null && !['transfer-encoding','connection'].includes(k.toLowerCase())) res.setHeader(k,v);
    }
    up.pipe(res);
  });
  upstream.on('error', (e) => {
    if (!res.headersSent) res.status(502).json({error:'internal_mcp_unavailable'});
    else res.end();
    console.error(e);
  });
  req.pipe(upstream);
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Secure Hesabfa MCP proxy listening on ${PORT}`);
  console.log(`Public resource: ${RESOURCE}`);
  console.log(`MCP enabled: ${boolEnv('MCP_ENABLED', false)}`);
  console.log(`OAuth signing configured: ${Boolean(process.env.OAUTH_SIGNING_SECRET)}`);
  console.log(`ChatGPT link password configured: ${Boolean(process.env.CHATGPT_LINK_PASSWORD)}`);
});
