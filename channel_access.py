"""Customer entry points and owner-controlled channel welcome panel."""
import threading
import time
from urllib.error import HTTPError


ALLOWED_UPDATES = ["message", "callback_query", "chat_member", "chat_join_request"]
CHAT_BUTTON = "💬 پرسیدن سؤال"
MENU_BUTTON = "📋 منوی اصلی"


def install(bot):
    original_text = bot.handle_text
    original_callback = bot.handle_callback
    publish_lock = threading.Lock()

    def chat_keyboard():
        return {"keyboard": [[CHAT_BUTTON, MENU_BUTTON]], "resize_keyboard": True,
                "is_persistent": True, "input_field_placeholder": "سؤال خود را اینجا بنویسید…"}

    def open_chat(uid, chat_id, greeting=None):
        bot.clear_session(uid)
        return bot.send(chat_id, greeting or
                        "💬 سؤالت را همین‌جا بنویس؛ مثلاً: برای خانه ۱۲۰ متری در زاهدان چه کولری پیشنهاد می‌کنید؟",
                        reply_markup=chat_keyboard())

    def start(chat_id, user, payload=""):
        bot.ensure_user(user, payload)
        uid = int(user["id"])
        if payload == "channel_setup":
            return preview_panel(uid, chat_id)
        name = user.get("first_name", "").strip()
        open_chat(uid, chat_id,
                  f"سلام {name}، خوش آمدی 🌷\n\n"
                  f"من دستیار هوشمند فروش و مشاوره {bot.BUSINESS_NAME} هستم.\n"
                  "درباره کولر گازی، لوازم خانگی و خدمات فروشگاه سؤالت را همین‌جا بنویس.\n\n"
                  "برای دیدن خدمات و ثبت استعلام یا درخواست تماس، «📋 منوی اصلی» را بزن.")
        if payload == "channel_quote":
            return bot.begin_quote(uid, chat_id)
        if payload == "channel_callback":
            return bot.begin_callback(uid, chat_id)

    def panel_content():
        username = bot.bot_username()
        if not username:
            raise RuntimeError("Bot username is not configured")
        base = f"https://t.me/{username}?start="
        text = ("به کانال خوش آمدید 🌷\n\n"
                "برای مشاوره خرید کولر گازی و لوازم خانگی، سؤال خود را از دستیار هوشمند فروشگاه بپرسید.\n\n"
                "👇 دکمه «پرسیدن سؤال» را بزنید؛ سپس در صفحه ربات «شروع / Start» را لمس کنید و سؤال خود را بنویسید.\n\n"
                "مثال: برای خانه ۱۲۰ متری در زاهدان چه کولری پیشنهاد می‌کنید؟\n\n"
                "قیمت روز و موجودی نهایی با فروشگاه تأیید می‌شود.")
        keyboard = [[{"text": CHAT_BUTTON, "url": base + "channel"}],
                    [{"text": "💰 استعلام قیمت", "url": base + "channel_quote"},
                     {"text": "📞 درخواست تماس فروشنده", "url": base + "channel_callback"}]]
        return text, keyboard

    def channel_info():
        channel = bot.cfg("channel_id")
        if not channel:
            raise ValueError("ابتدا کانال را با /setchannel @نام_کانال تنظیم کن.")
        chat = bot.api("getChat", {"chat_id": channel})
        if chat.get("type") != "channel":
            raise ValueError("کانال ثبت‌شده معتبر نیست؛ آدرس کانال را با /setchannel تنظیم کن.")
        me = bot.api("getMe")
        member = bot.api("getChatMember", {"chat_id": chat["id"], "user_id": me["id"]})
        if member.get("status") != "administrator" or not member.get("can_post_messages") or not member.get("can_edit_messages"):
            raise ValueError("در مدیران کانال، دسترسی «ارسال پیام» و «ویرایش پیام» را برای ربات فعال کن؛ ویرایش پیام برای سنجاق‌کردن هم لازم است.")
        return chat

    def preview_panel(uid, chat_id):
        if not bot.is_owner(uid):
            return bot.send(chat_id, "برای پرسیدن سؤال، /chat را بزن.")
        try:
            channel = channel_info()
            text, keyboard = panel_content()
            bot.send(chat_id, text, keyboard)
            return bot.send(chat_id,
                            f"پیش‌نمایش پیام کانال «{channel.get('title', '')}» آماده است.\n"
                            "با دکمه زیر همین پیام در کانال منتشر و سنجاق می‌شود. اگر قبلاً از همین دکمه منتشر شده باشد، همان پیام به‌روز می‌شود.",
                            [[{"text": "✅ انتشار و سنجاق در کانال", "callback_data": f"panel_publish:{channel['id']}"}]])
        except ValueError as exc:
            return bot.send(chat_id, str(exc))
        except Exception as exc:
            print("Channel panel preview failed:", type(exc).__name__, flush=True)
            return bot.send(chat_id, "دسترسی به کانال بررسی نشد. آدرس کانال و مدیر بودن ربات را بررسی کن و /channel_panel را دوباره بزن.")

    def publish_panel(uid, chat_id, expected_channel):
        if not bot.is_owner(uid):
            return
        with publish_lock:
            try:
                channel = channel_info()
                if str(channel["id"]) != expected_channel:
                    return bot.send(chat_id, "کانال تغییر کرده است. با /channel_panel پیش‌نمایش جدید را ببین.")
                text, keyboard = panel_content()
                key = f"channel_panel_message_{channel['id']}"
                message_id = bot.cfg(key)
                if message_id:
                    try:
                        bot.api("editMessageText", {"chat_id": channel["id"], "message_id": int(message_id),
                                                  "text": text, "reply_markup": {"inline_keyboard": keyboard}})
                    except HTTPError as exc:
                        error = exc.read().decode("utf-8", errors="replace")
                        if exc.code != 400 or "message is not modified" not in error.lower():
                            raise
                else:
                    sent = bot.api("sendMessage", {"chat_id": channel["id"], "text": text,
                                                  "disable_notification": "true",
                                                  "reply_markup": {"inline_keyboard": keyboard}})
                    message_id = sent["message_id"]
                    bot.setcfg(key, message_id)
                bot.api("pinChatMessage", {"chat_id": channel["id"], "message_id": int(message_id),
                                          "disable_notification": "true"})
                return bot.send(chat_id, "✅ پیام خوشامد و دکمه پرسیدن سؤال در کانال منتشر و سنجاق شد.")
            except ValueError as exc:
                return bot.send(chat_id, str(exc))
            except Exception as exc:
                print("Channel panel publish failed:", type(exc).__name__, flush=True)
                return bot.send(chat_id, "انتشار یا سنجاق کامل نشد. دسترسی ارسال و ویرایش پیام ربات را بررسی کن؛ سپس /channel_panel را بزن. پیام ثبت‌شده دوباره ارسال نمی‌شود.")

    def matches_channel(chat):
        configured = str(bot.cfg("channel_id", "") or "")
        return bool(configured and (configured == str(chat.get("id")) or
                    configured.lower() == "@" + str(chat.get("username", "")).lower()))

    def is_member(member):
        return member.get("status") in ("member", "administrator", "creator") or (
            member.get("status") == "restricted" and member.get("is_member"))

    def welcome_member(update):
        # Ordinary subscribers can only receive a DM if they previously started the bot.
        chat = update.get("chat", {})
        if not matches_channel(chat) or is_member(update.get("old_chat_member", {})) or not is_member(update.get("new_chat_member", {})):
            return
        user = update["new_chat_member"].get("user", {})
        if user.get("is_bot") or not user.get("id"):
            return
        uid = int(user["id"])
        if not bot.db("user_get", {"telegram_id": uid}):
            return
        key = f"channel_welcomed_{chat['id']}_{uid}"
        if bot.cfg(key):
            return
        try:
            _, keyboard = panel_content()
            bot.send(uid, f"سلام {user.get('first_name', '')} 🌷\nبه کانال خوش آمدی.\nبرای مشاوره خرید و پرسیدن سؤال، دکمه زیر را بزن.", keyboard)
            bot.setcfg(key, "1")
        except Exception as exc:
            print("Member welcome unavailable:", type(exc).__name__, flush=True)

    def welcome_join_request(update):
        # Telegram allows a short contact window for join requests, without changing admission rules.
        if not matches_channel(update.get("chat", {})) or update.get("from", {}).get("is_bot"):
            return
        if not update.get("user_chat_id") or not 0 <= time.time() - update.get("date", 0) < 270:
            return
        try:
            _, keyboard = panel_content()
            bot.send(update["user_chat_id"], "سلام، خوش آمدید 🌷\nدرخواست عضویت شما دریافت شده است. برای پرسیدن سؤال از دستیار فروشگاه، دکمه زیر را بزنید.", keyboard)
        except Exception as exc:
            print("Join request welcome unavailable:", type(exc).__name__, flush=True)

    def handle_text(msg):
        if msg.get("chat", {}).get("type") != "private":
            return original_text(msg)
        user = msg.get("from", {})
        uid = int(user.get("id", 0))
        chat_id = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()
        command = text.split(maxsplit=1)[0].split("@", 1)[0] if text.startswith("/") else text
        if command in ("/chat", "/cancel", CHAT_BUTTON, "/menu", MENU_BUTTON, "/channel_panel", "/help"):
            bot.ensure_user(user)
            if command == "/channel_panel":
                return preview_panel(uid, chat_id)
            if command in ("/menu", MENU_BUTTON):
                bot.clear_session(uid)
                return bot.send(chat_id, "خدمات فروشگاه؛ برای سؤال آزاد /chat را بزن:", bot.main_menu(uid))
            return open_chat(uid, chat_id)
        return original_text(msg)

    def handle_callback(callback):
        chat = callback.get("message", {}).get("chat", {})
        data = callback.get("data", "")
        if data.startswith("panel_publish:"):
            uid = int(callback.get("from", {}).get("id", 0))
            bot.answer_cb(callback["id"])
            if chat.get("type") != "private":
                return
            return publish_panel(uid, chat["id"], data.split(":", 1)[1])
        if data == "ai_help" and chat.get("type") == "private":
            uid = int(callback["from"]["id"])
            bot.ensure_user(callback["from"])
            bot.answer_cb(callback["id"])
            return open_chat(uid, chat["id"])
        return original_callback(callback)

    def configure_profile():
        commands = [{"command": "start", "description": "شروع و خوشامدگویی"},
                    {"command": "chat", "description": "پرسیدن سؤال از دستیار"},
                    {"command": "menu", "description": "خدمات، استعلام قیمت و درخواست تماس"},
                    {"command": "cancel", "description": "خروج از فرم و بازگشت به گفت‌وگو"},
                    {"command": "help", "description": "راهنمای پرسیدن سؤال"},
                    {"command": "privacy", "description": "حریم خصوصی"}]
        description = (f"به دستیار هوشمند {bot.BUSINESS_NAME} خوش آمدید 🌷\n"
                       "مشاوره خرید کولر گازی و لوازم خانگی، استعلام قیمت و درخواست تماس فروشنده.\n"
                       "دکمه شروع / Start را بزنید و سپس سؤال خود را همین‌جا بنویسید.")
        for language in ("", "fa"):
            bot.api("setMyCommands", {"commands": commands, "scope": {"type": "all_private_chats"}, "language_code": language})
            bot.api("setMyDescription", {"description": description[:512], "language_code": language})
            bot.api("setMyShortDescription", {"short_description": "مشاوره خرید کولر و لوازم خانگی؛ Start را بزنید و سؤال خود را بنویسید.", "language_code": language})
        bot.api("setChatMenuButton", {"menu_button": {"type": "commands"}})
        print("Customer chat profile and commands configured.", flush=True)

    bot.start = start
    bot.handle_text = handle_text
    bot.handle_callback = handle_callback
    bot.handle_chat_member = welcome_member
    bot.handle_chat_join_request = welcome_join_request
    bot.configure_customer_profile = configure_profile
    bot.preview_channel_panel = preview_panel
    print("Channel access extension installed.", flush=True)
