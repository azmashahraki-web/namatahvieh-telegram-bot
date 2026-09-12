const DEFAULT_PUBLIC_BASE_URL = 'https://hesabfa-readonly-mcp.onrender.com';

// This setting is exposed in health checks, OAuth metadata, redirects and tokens.
// Never reflect malformed configuration: copied requests can contain credentials.
export function publicBaseUrl(env = process.env, warn = console.warn) {
  const value = env.PUBLIC_BASE_URL;
  if (value == null || value === '') return DEFAULT_PUBLIC_BASE_URL;
  try {
    if (typeof value !== 'string' || value.length > 2048) throw new Error();
    const text = value.trim();
    if (/\s/.test(text)) throw new Error();
    const url = new URL(text);
    if (url.protocol !== 'https:' || url.username || url.password ||
        url.pathname !== '/' || url.search || url.hash) throw new Error();
    return url.origin;
  } catch {
    warn('Invalid PUBLIC_BASE_URL; using the default Hesabfa connector origin.');
    return DEFAULT_PUBLIC_BASE_URL;
  }
}
