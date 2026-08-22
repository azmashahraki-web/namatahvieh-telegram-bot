import html
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

import bot

try:
    import ai_assistant
    ai_assistant.install(bot)
except Exception as e:
    print("AI extension failed to load:", repr(e), flush=True)

PORT = int(os.getenv("PORT", "10000"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
GEMINI_SETUP_TOKEN = os.getenv("GEMINI_SETUP_TOKEN", "").strip()


def dispatch(update):
    try:
        if "callback_query" in update:
            bot.handle_callback(update["callback_query"])
        elif "message" in update:
            m = update["message"]
            if "contact" in m:
                bot.handle_contact(m)
            else:
                bot.handle_text(m)
    except Exception:
        bot.traceback.print_exc()


def setup_page(title, message, token="", show_form=False, error=False):
    form = ""
    if show_form:
        action = "/setup-gemini?token=" + quote(token, safe="")
        form = f"""
        <form method="post" action="{html.escape(action, quote=True)}">
          <label for="gemini_key">Gemini API Key</label>
          <input id="gemini_key" name="gemini_key" type="password" autocomplete="off" minlength="20" required autofocus>
          <button type="submit">تست و فعال‌سازی</button>
        </form>
        <p class="note">کلید در این صفحه نمایش داده یا در لاگ ثبت نمی‌شود.</p>
        """
    cls = "error" if error else "ok"
    doc = f"""<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer"><title>{html.escape(title)}</title>
<style>body{{font-family:Tahoma,Arial,sans-serif;max-width:620px;margin:60px auto;padding:0 20px;line-height:1.9;background:#f6f7f9;color:#1f2937}}.card{{background:white;padding:28px;border-radius:18px;box-shadow:0 8px 30px #0001}}h1{{font-size:22px}}input{{width:100%;box-sizing:border-box;padding:13px;margin:10px 0 16px;border:1px solid #bbb;border-radius:10px;font-size:16px}}button{{padding:12px 18px;border:0;border-radius:10px;cursor:pointer;font-size:16px}}.note{{font-size:13px;color:#666}}.error{{color:#b42318}}.ok{{color:#067647}}</style></head>
<body><div class="card"><h1>{html.escape(title)}</h1><p class="{cls}">{html.escape(message)}</p>{form}</div></body></html>"""
    return doc.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code=200, body=b"ok", content_type="text/plain; charset=utf-8", extra_headers=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _secure_html(self, code, body):
        self._reply(code, body, "text/html; charset=utf-8", {
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
        })

    def _setup_token_ok(self, token):
        return bool(GEMINI_SETUP_TOKEN and token and secrets.compare_digest(token, GEMINI_SETUP_TOKEN))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/health"):
            self._reply(200, b"namatahvieh bot is running")
            return
        if parsed.path == "/setup-gemini":
            token = (parse_qs(parsed.query).get("token") or [""])[0]
            if not self._setup_token_ok(token):
                self._reply(404, b"not found")
                return
            try:
                if hasattr(bot, "ai_gemini_secret_exists") and bot.ai_gemini_secret_exists():
                    self._secure_html(200, setup_page("Gemini", "کلید Gemini قبلاً با موفقیت تنظیم شده است."))
                    return
            except Exception:
                pass
            self._secure_html(200, setup_page("فعال‌سازی Gemini", "کلید ساخته‌شده در Google AI Studio را اینجا وارد کن.", token, True))
            return
        self._reply(404, b"not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/setup-gemini":
            token = (parse_qs(parsed.query).get("token") or [""])[0]
            if not self._setup_token_ok(token):
                self._reply(404, b"not found")
                return
            if not all(hasattr(bot, name) for name in ("ai_test_gemini_key", "ai_store_gemini_key")):
                self._secure_html(503, setup_page("خطا", "بخش Gemini هنوز روی سرور آماده نشده است.", error=True))
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 10000:
                    raise ValueError("bad length")
                raw = self.rfile.read(length).decode("utf-8", errors="replace")
                key = (parse_qs(raw).get("gemini_key") or [""])[0].strip()
                if len(key) < 20:
                    self._secure_html(400, setup_page("کلید نامعتبر", "کلید واردشده خیلی کوتاه است. دوباره امتحان کن.", token, True, True))
                    return
                ok, detail = bot.ai_test_gemini_key(key)
                if not ok:
                    self._secure_html(400, setup_page("تست Gemini ناموفق بود", detail or "کلید یا دسترسی Gemini معتبر نیست.", token, True, True))
                    return
                bot.ai_store_gemini_key(key)
                bot.setcfg("ai_provider", "gemini")
                bot.setcfg("ai_enabled", "1")
                try:
                    oid = bot.owner_id()
                    if oid:
                        bot.send(oid, "✅ Gemini با موفقیت تست و فعال شد. دستیار هوشمند ربات آماده است.")
                except Exception:
                    pass
                self._secure_html(200, setup_page("انجام شد ✅", "Gemini با موفقیت تست، ذخیره و فعال شد. حالا می‌توانی ربات را امتحان کنی."))
                return
            except Exception as e:
                print("Gemini setup error:", type(e).__name__, flush=True)
                self._secure_html(500, setup_page("خطا", "ذخیره کلید انجام نشد. دوباره امتحان کن.", token, True, True))
                return

        if parsed.path != "/telegram":
            self._reply(404, b"not found")
            return
        if WEBHOOK_SECRET:
            supplied = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if supplied != WEBHOOK_SECRET:
                self._reply(403, b"forbidden")
                return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            update = json.loads(raw.decode("utf-8"))
            threading.Thread(target=dispatch, args=(update,), daemon=True).start()
            self._reply(200, b"ok")
        except Exception:
            bot.traceback.print_exc()
            self._reply(400, b"bad request")

    def log_message(self, format, *args):
        pass


def configure_webhook():
    if not bot.TOKEN:
        print("BOT_TOKEN is not configured; HTTP service is ready but Telegram webhook is disabled.", flush=True)
        return
    try:
        me = bot.api("getMe")
        bot.setcfg("bot_username", me.get("username", ""))
        print("Bot online:", me.get("username"), flush=True)
        if WEBHOOK_URL:
            data = {
                "url": WEBHOOK_URL + "/telegram",
                "allowed_updates": ["message", "callback_query"],
                "drop_pending_updates": False,
            }
            if WEBHOOK_SECRET:
                data["secret_token"] = WEBHOOK_SECRET
            bot.api("setWebhook", data)
            print("Webhook configured:", WEBHOOK_URL + "/telegram", flush=True)
        else:
            print("WEBHOOK_URL is missing; webhook not configured yet.", flush=True)
    except Exception as e:
        print("Webhook configuration failed:", repr(e), flush=True)


if __name__ == "__main__":
    configure_webhook()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"HTTP server listening on {PORT}", flush=True)
    server.serve_forever()
