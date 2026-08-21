import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bot

try:
    import ai_assistant
    ai_assistant.install(bot)
except Exception as e:
    print("AI extension failed to load:", repr(e), flush=True)

PORT = int(os.getenv("PORT", "10000"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()


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


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code=200, body=b"ok", content_type="text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/health"):
            self._reply(200, b"namatahvieh bot is running")
        else:
            self._reply(404, b"not found")

    def do_POST(self):
        if self.path != "/telegram":
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
    if os.getenv("AI_SELFTEST", "0") == "1":
        try:
            import ai_smoketest
            ai_smoketest.run()
        except Exception as e:
            print("AI self-test: FAIL", type(e).__name__, flush=True)
    configure_webhook()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"HTTP server listening on {PORT}", flush=True)
    server.serve_forever()
