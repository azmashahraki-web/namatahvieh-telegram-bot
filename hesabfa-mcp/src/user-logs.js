// The web report is separate from the public API. Never send API credentials here.
export const USER_LOG_URL = 'https://core.hesabfa.com/api/report/getUserLog';
const SESSION_ENV = 'HESABFA_USER_LOG_CURL';
const REQUIRED_HEADERS = ['cookie', 'x-xsrf-token', 'hesabfa-business-key'];
const ALLOWED_HEADERS = new Set(REQUIRED_HEADERS);

export class UserLogError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'UserLogError';
    this.code = code;
  }
}

const configError = (reason = 'INVALID_CURL') => Object.assign(new UserLogError('USER_LOG_CONFIG_INVALID',
  'درخواست ذخیره‌شدهٔ لاگ معتبر نیست. از گزارش لاگ کاربران پالیز، Copy as cURL (bash) را دوباره در HESABFA_USER_LOG_CURL سرور ذخیره کنید؛ مقدار را در چت نفرستید.'), { reason });

// Parse copied text as data only. No shell, eval, command substitution, or file reads.
function curlWords(text) {
  const words = [];
  let word = '', quote = '', active = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quote === "'") {
      if (ch === "'") quote = '';
      else word += ch;
      continue;
    }
    if (ch === '\\' && quote !== "'") {
      if (i + 1 >= text.length) throw configError('TRAILING_ESCAPE');
      const next = text[++i];
      if (next === '\n') continue;
      if (next === '\r' && text[i + 1] === '\n') { i++; continue; }
      if (quote === '"' && !['"', '\\', '$', '`'].includes(next)) word += '\\';
      word += next;
      active = true;
      continue;
    }
    if (quote === '"') {
      if (ch === '"') quote = '';
      else word += ch;
      continue;
    }
    if (ch === "'" || ch === '"') { quote = ch; active = true; continue; }
    if (/\s/.test(ch)) {
      if (active) { words.push(word); word = ''; active = false; }
      continue;
    }
    word += ch;
    active = true;
  }
  if (quote) throw configError('UNCLOSED_QUOTE');
  if (active) words.push(word);
  return words;
}

export function readUserLogHeaders(env = process.env) {
  const raw = env[SESSION_ENV];
  if (!raw) throw new UserLogError('USER_LOG_SESSION_REQUIRED',
    'ابزار لاگ نصب است، اما نشست وب حسابفا تنظیم نشده است. Copy as cURL (bash) درخواست getUserLog در گزارش پالیز را مستقیماً در متغیر HESABFA_USER_LOG_CURL سرویس Render ذخیره کنید؛ رمز، کوکی یا درخواست را در چت نفرستید.');
  if (typeof raw !== 'string' || raw.length > 100000) throw configError('INVALID_LENGTH_OR_TYPE');
  const words = curlWords(raw);
  if (words.shift() !== 'curl') throw configError('NOT_BASH_CURL');
  let url;
  const headers = {};
  function addHeader(name, value) {
    name = name.trim().toLowerCase();
    if (!ALLOWED_HEADERS.has(name)) return;
    value = value.trim();
    if (!value || /[\r\n\0]/.test(value) || value.length > 32768 || headers[name]) throw configError('INVALID_OR_DUPLICATE_HEADER');
    headers[name] = value;
  }
  for (let i = 0; i < words.length; i++) {
    const arg = words[i];
    if (['-H', '--header', '-b', '--cookie', '--url', '-X', '--request', '--data', '--data-raw', '--data-binary', '-d'].includes(arg)) {
      const value = words[++i];
      if (value === undefined) throw configError('MISSING_ARGUMENT');
      if (arg === '-H' || arg === '--header') {
        const colon = value.indexOf(':');
        if (colon < 1) throw configError('INVALID_HEADER');
        addHeader(value.slice(0, colon), value.slice(colon + 1));
      } else if (arg === '-b' || arg === '--cookie') {
        if (!value.includes('=')) throw configError('INVALID_COOKIE');
        addHeader('cookie', value);
      } else if (arg === '--url') {
        if (url) throw configError('MULTIPLE_URLS');
        url = value;
      } else if ((arg === '-X' || arg === '--request') && value !== 'POST') throw configError('WRONG_METHOD');
      // Captured dates, filters, and all other body content are deliberately ignored.
    } else if (['--compressed', '--http2', '--http1.1'].includes(arg)) {
      continue;
    } else if (arg === USER_LOG_URL && !url) {
      url = arg;
    } else throw configError('UNSUPPORTED_ARGUMENT_OR_URL');
  }
  if (url !== USER_LOG_URL) throw configError('WRONG_URL');
  if (REQUIRED_HEADERS.some(key => !headers[key])) throw configError('MISSING_SESSION_HEADERS');
  return headers;
}

export function userLogStatus(env = process.env) {
  try {
    readUserLogHeaders(env);
    return { configured: true, code: 'USER_LOG_SESSION_CONFIGURED',
      message: 'نشست ذخیره شده است؛ اعتبار آن فقط با دریافت موفق گزارش تأیید می‌شود.',
      liveVerified: false, readOnly: true, timeZone: 'Asia/Tehran' };
  } catch (error) {
    return { configured: false, code: error.code || 'USER_LOG_CONFIG_INVALID',
      reason: error.reason || 'SESSION_NOT_CONFIGURED',
      message: error.message, liveVerified: false, readOnly: true, timeZone: 'Asia/Tehran' };
  }
}

function dateBoundary(value, end) {
  // Iran has used UTC+03:30 year-round since 2023. Earlier dates require an offset.
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}):(\d{2})(\.\d{1,3})?(Z|[+-]\d{2}:\d{2})?)?$/.exec(value || '');
  if (!match) throw new UserLogError('USER_LOG_DATE_INVALID', 'تاریخ میلادی را به شکل YYYY-MM-DD یا زمان ISO وارد کنید.');
  const [, y, m, d, h, min, sec, fraction = '', zone = ''] = match;
  const year = Number(y), month = Number(m), day = Number(d);
  if (year < 2000 || year > 2100 || month < 1 || month > 12 || day < 1 ||
      day > new Date(Date.UTC(year, month, 0)).getUTCDate() ||
      (h !== undefined && (Number(h) > 23 || Number(min) > 59 || Number(sec) > 59)) ||
      (year < 2023 && !zone)) {
    throw new UserLogError('USER_LOG_DATE_INVALID', 'تاریخ میلادی نامعتبر است؛ برای تاریخ پیش از ۲۰۲۳، اختلاف ساعت را صریح بنویسید.');
  }
  const time = h === undefined ? (end ? '23:59:59.999' : '00:00:00.000') : `${h}:${min}:${sec}${fraction}`;
  const ms = Date.parse(`${y}-${m}-${d}T${time}${zone || '+03:30'}`);
  if (!Number.isFinite(ms)) throw new UserLogError('USER_LOG_DATE_INVALID', 'زمان یا اختلاف ساعت معتبر نیست.');
  return ms;
}

export function userLogPayload({ start, end, userId = '', skip = 0, take = 50 }) {
  const startMs = dateBoundary(start, false), endMs = dateBoundary(end, true);
  if (endMs < startMs || endMs - startMs >= 31 * 86400000) {
    throw new UserLogError('USER_LOG_RANGE_INVALID', 'بازه باید مرتب و حداکثر ۳۱ روز باشد.');
  }
  if (!Number.isSafeInteger(skip) || skip < 0 || skip > 1000000 ||
      !Number.isInteger(take) || take < 1 || take > 100 || typeof userId !== 'string' || userId.length > 200) {
    throw new UserLogError('USER_LOG_INPUT_INVALID', 'پارامترهای صفحه‌بندی یا شناسهٔ کاربر نامعتبر است.');
  }
  return { start: new Date(startMs).toISOString(), end: new Date(endMs).toISOString(), userId,
    loadOptions: { requireTotalCount: true, skip, take, sort: [{ selector: 'logDateTime', desc: true }] } };
}

export async function getUserLogs(args, { env = process.env, fetchImpl = fetch } = {}) {
  const request = userLogPayload(args);
  const headers = readUserLogHeaders(env);
  let response, text;
  try {
    response = await fetchImpl(USER_LOG_URL, {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(30000),
      headers: { ...headers, 'content-type': 'application/json', accept: 'application/json',
        origin: 'https://app.hesabfa.com', referer: 'https://app.hesabfa.com/', language: 'fa' },
      body: JSON.stringify(request)
    });
    if ([401, 403].includes(response.status)) {
      throw new UserLogError('USER_LOG_SESSION_EXPIRED_OR_FORBIDDEN',
        'حسابفا دسترسی نشست را رد کرد. ورود معتبر، دسترسی گزارش لاگ کاربران و انتخاب پالیز را بررسی و درخواست ذخیره‌شده را تازه کنید. این خطا به معنی نبود فعالیت کاربران نیست.');
    }
    if (!response.ok) throw new UserLogError('USER_LOG_HTTP_ERROR', `دریافت لاگ از حسابفا ناموفق بود (HTTP ${response.status}).`);
    text = await response.text();
  } catch (error) {
    if (error instanceof UserLogError) throw error;
    // Do not expose fetch errors, copied cURL text, headers, cookies, or response bodies.
    throw new UserLogError('USER_LOG_CONNECTION_FAILED', 'ارتباط با گزارش لاگ برقرار نشد یا مهلت پاسخ تمام شد.');
  }
  let payload;
  try {
    if (text.length > 1000000) throw new Error();
    payload = JSON.parse(text);
  } catch {
    throw new UserLogError('USER_LOG_RESPONSE_INVALID', 'پاسخ گزارش لاگ JSON معتبر و قابل پردازش نیست.');
  }
  const { skip, take } = request.loadOptions;
  if (!payload || !Array.isArray(payload.data) || !Number.isSafeInteger(payload.totalCount) ||
      payload.totalCount < 0 || payload.data.length > take ||
      (payload.data.length && payload.totalCount < skip + payload.data.length) ||
      (!payload.data.length && skip < payload.totalCount)) {
    throw new UserLogError('USER_LOG_RESPONSE_INVALID', 'ساختار یا صفحه‌بندی پاسخ لاگ معتبر نیست؛ گزارش خالی تأیید نشده است.');
  }
  const fields = ['id', 'dateTime', 'user', 'action', 'title', 'description'];
  const data = payload.data.map(row => {
    if (!row || typeof row !== 'object' || row.id == null || typeof row.dateTime !== 'string') {
      throw new UserLogError('USER_LOG_RESPONSE_INVALID', 'یکی از ردیف‌های لاگ معتبر نیست.');
    }
    return Object.fromEntries(fields.filter(key => Object.hasOwn(row, key)).map(key => [key, row[key]]));
  });
  return { source: 'hesabfa_web_user_log', timeZone: 'Asia/Tehran',
    start: request.start, end: request.end, userId: request.userId,
    data, totalCount: payload.totalCount, skip, take,
    nextSkip: skip + data.length < payload.totalCount ? skip + data.length : null };
}
