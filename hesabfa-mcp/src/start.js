const API_BASE = process.env.HESABFA_API_BASE || 'https://api.hesabfa.com/v1';

async function verifyHesabfaCredentials() {
  const apiKey = process.env.HESABFA_API_KEY;
  const loginToken = process.env.HESABFA_LOGIN_TOKEN;

  if (!apiKey || !loginToken) {
    console.log('Hesabfa credential validation: skipped (missing credentials)');
    return;
  }

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    let response;
    try {
      response = await fetch(`${API_BASE}/setting/getBusinessInfo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          apiKey,
          loginToken,
          userId: '',
          password: ''
        }),
        signal: controller.signal
      });
    } finally {
      clearTimeout(timeout);
    }

    const text = await response.text();
    let payload;
    try {
      payload = JSON.parse(text);
    } catch {
      throw new Error(`non-JSON response (HTTP ${response.status})`);
    }

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    if (payload?.Success === false || (!payload?.Success && payload?.ErrorCode)) {
      const code = payload?.ErrorCode ?? 'unknown';
      throw new Error(`API error ${code}`);
    }

    console.log('Hesabfa credential validation: success');
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.log(`Hesabfa credential validation: failed (${message})`);
  }
}

await verifyHesabfaCredentials();
await import('./index.js');
