import { USER_LOG_URL, getUserLogs, userLogStatus } from './user-logs.js';

function copiedRequestKind(raw) {
  const match = /^curl(?:\.exe)?\s+(?:--url\s+)?(?:'([^']*)'|"([^"]*)"|(\S+))/.exec(raw);
  if (!match) return 'UNKNOWN';
  let url;
  try { url = new URL(match[1] ?? match[2] ?? match[3]); }
  catch { return 'INVALID_URL'; }
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return 'INVALID_URL';
  if (url.href === USER_LOG_URL) return 'USER_LOG_REPORT';
  if (url.hostname === 'core.hesabfa.com' && /getUserLog/i.test(url.pathname)) return 'VARIANT_USER_LOG_URL';
  if (!['app.hesabfa.com', 'core.hesabfa.com', 'api.hesabfa.com'].includes(url.hostname)) return 'OTHER_HOST';
  if (/\.css$/i.test(url.pathname)) return 'HESABFA_STYLESHEET';
  if (/\.js$/i.test(url.pathname)) return 'HESABFA_SCRIPT';
  if (url.pathname.endsWith('/users-log')) return 'HESABFA_REPORT_PAGE';
  return 'HESABFA_OTHER_REQUEST';
}

// Diagnostics are fixed labels and booleans, never copied text or header values.
export function userLogDiagnostics(env = process.env) {
  const raw = typeof env.HESABFA_USER_LOG_CURL === 'string' ? env.HESABFA_USER_LOG_CURL.trim() : '';
  const status = userLogStatus(env);
  const methodMatch = /(?:^|\s)(?:-X|--request)\s+['"]?([A-Z]+)\b/.exec(raw);
  const method = methodMatch ? (['POST', 'OPTIONS', 'GET'].includes(methodMatch[1]) ? methodMatch[1] : 'OTHER')
    : /(?:^|\s)(?:--data(?:-raw|-binary)?|-d)\s/.test(raw) ? 'POST' : 'UNSPECIFIED';
  return {
    configured: status.configured,
    code: status.code,
    reason: status.configured ? 'CONFIGURED' : status.reason,
    requestKind: copiedRequestKind(raw),
    curlCommand: /^curl(?:\.exe)?\s/.test(raw),
    fetchCommand: /^fetch\s*\(/.test(raw),
    exactReportUrl: raw.includes(USER_LOG_URL),
    cookieField: /(?:^|\s)(?:-b|--cookie)\s|\bcookie\s*:/i.test(raw),
    xsrfField: /\bx-xsrf-token\s*:/i.test(raw),
    businessField: /\bhesabfa-business-key\s*:/i.test(raw),
    authorizationField: /\bauthorization\s*:/i.test(raw),
    cmdContinuation: /\^(?:\r?\n|[ \t]+-)/.test(raw),
    cmdQuotes: /\^"/.test(raw),
    flattenedBashContinuation: /\\[ \t]+-/.test(raw),
    method
  };
}

export async function verifyUserLogConnection({ env = process.env, request = getUserLogs,
  log = console.log, now = new Date() } = {}) {
  const diagnostic = userLogDiagnostics(env);
  log(`Hesabfa user log diagnostics: ${JSON.stringify(diagnostic)}`);
  if (!diagnostic.configured) return { code: diagnostic.code, verified: false };
  const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tehran', year: 'numeric', month: '2-digit', day: '2-digit' });
  const isoDay = value => {
    const parts = Object.fromEntries(date.formatToParts(value).map(part => [part.type, part.value]));
    return `${parts.year}-${parts.month}-${parts.day}`;
  };
  try {
    const result = await request({ start: isoDay(new Date(now.getTime() - 7 * 86400000)), end: isoDay(now), take: 1 }, { env });
    const outcome = { code: 'USER_LOG_VERIFIED', verified: true, hasRows: result.data.length > 0 };
    log(`Hesabfa user log live check: ${JSON.stringify(outcome)}`);
    return outcome;
  } catch (error) {
    const knownCodes = ['USER_LOG_SESSION_EXPIRED_OR_FORBIDDEN', 'USER_LOG_HTTP_ERROR',
      'USER_LOG_CONNECTION_FAILED', 'USER_LOG_RESPONSE_INVALID', 'USER_LOG_CONFIG_INVALID', 'USER_LOG_SESSION_REQUIRED'];
    const code = knownCodes.includes(error?.code) ? error.code : 'USER_LOG_CHECK_FAILED';
    const outcome = { code, verified: false };
    if (code === 'USER_LOG_SESSION_EXPIRED_OR_FORBIDDEN' && [401, 403].includes(error?.httpStatus)) {
      outcome.httpStatus = error.httpStatus;
    }
    log(`Hesabfa user log live check: ${JSON.stringify(outcome)}`);
    return outcome;
  }
}
