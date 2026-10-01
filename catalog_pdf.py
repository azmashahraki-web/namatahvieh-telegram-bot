"""Offer and deliver the approved complete customer PDF in private chats."""
import hashlib
import re
import threading
from pathlib import Path
from urllib.error import HTTPError

VERSION = "14050709"
SHA256 = "51f3192640cd090bd4e842cf248332563bbee31991d4b07f5d38d4308f0624d8"
SIZE = 16083824
PAGES = 63
BUTTON = "📄 دریافت PDF کامل"
CALLBACK = "catalog_pdf"
FILENAME = "Price-List-and-Catalog-14050709-updated.pdf"
PARTS = ("catalog-14050709.part0", "catalog-14050709.part1")
CAPTION = "📄 لیست قیمت و کاتالوگ کامل فروشگاه — ۶۳ صفحه\nبه‌روزرسانی: ۹ مهر ۱۴۰۵\nقیمت‌های جدید هایسنس و دی‌کد در فایل اعمال شده‌اند.\nقیمت و موجودی نهایی هنگام خرید با فروشگاه تأیید می‌شود."


def document_bytes():
    directory = Path(__file__).resolve().parent / "assets"
    data = b"".join((directory / part).read_bytes() for part in PARTS)
    if len(data) != SIZE or hashlib.sha256(data).hexdigest() != SHA256 or not data.startswith(b"%PDF-"):
        raise ValueError("Approved catalog PDF integrity check failed")
    return data


def keyboard():
    return [[{"text": BUTTON, "callback_data": CALLBACK}]]


def normalize(text):
    text = (text or "").lower().replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"\s+", " ", text).strip()


def requests_pdf(text):
    """Require a document intent; ordinary questions about a model keep using AI."""
    t = normalize(text)
    command = t.split(maxsplit=1)[0].split("@", 1)[0] if t else ""
    if command in ("/catalog", "/pdf", "/pricelist") or t == normalize(BUTTON):
        return True
    if t.startswith("/"):
        return False
    if re.search(r"(?:نفرست|نده|نمی ?خواهم|نمی ?خوام|نمی ?خواد|نمی ?خواهد|لازم ندارم|ارسال نکن|بدون فایل)", t):
        return False
    # Short replies to our explicit file offer.
    if t in ("فایل را بفرست", "فایل رو بفرست", "فایل کامل را بفرست", "فایل کامل رو بفرست", "فایلش رو بفرست", "فایلش را بفرست", "پی دی اف", "pdf", "کاتالوگ", "کاتالوگ کامل", "لیست قیمت", "لیست قیمت کامل"):
        return True
    doc = any(w in t for w in ("pdf", "پی دی اف", "پی دی افش", "کاتالوگ", "لیست قیمت", "لیست کامل", "قیمت نامه"))
    action = any(w in t for w in ("بفرست", "ارسال", "دانلود", "دریافت", "بده", "می خوام", "می خواهم", "میخوام", "میخواهم", "دارید", "داری"))
    return doc and action


def should_offer(text):
    t = normalize(text)
    return any(w in t for w in ("قیمت", "کولر", "تلویزیون", "یخچال", "لباسشویی", "پکیج", "داکت", "کاتالوگ", "مقایسه", "هایسنس", "جی پلاس", "مشخصات", "مدل"))


def install(bot):
    original_text, original_callback, original_menu = bot.handle_text, bot.handle_callback, bot.main_menu
    upload_lock = threading.Lock()
    cache_key = "catalog_pdf_file_id_" + SHA256[:16]

    def send_catalog(uid, chat_id):
        try:
            try:
                bot.api("sendChatAction", {"chat_id": chat_id, "action": "upload_document"}, timeout=10)
            except Exception:
                pass
            with upload_lock:
                file_id = bot.cfg(cache_key)
                if file_id:
                    try:
                        return bot.api("sendDocument", {"chat_id": chat_id, "document": file_id, "caption": CAPTION}, timeout=90)
                    except HTTPError as exc:
                        if exc.code != 400:
                            raise
                result = bot.api("sendDocument", {"chat_id": chat_id, "caption": CAPTION},
                                 files={"document": (FILENAME, document_bytes(), "application/pdf")}, timeout=120)
                received_id = (result or {}).get("document", {}).get("file_id")
                if received_id:
                    try:
                        bot.setcfg(cache_key, received_id)
                    except Exception as exc:
                        print("Catalog cache save failed:", type(exc).__name__, flush=True)
                return result
        except Exception as exc:
            print("Catalog delivery failed:", type(exc).__name__, flush=True)
            return bot.send(chat_id, "ارسال فایل کامل فعلاً انجام نشد؛ لطفاً دکمه دریافت PDF را دوباره بزن یا از فروشنده درخواست کن.", keyboard())

    def main_menu(uid):
        menu = original_menu(uid)
        if not any(b.get("callback_data") == CALLBACK for row in menu for b in row):
            menu.insert(1, keyboard()[0])
        return menu

    def handle_text(message):
        chat = message.get("chat", {})
        user = message.get("from", {})
        if chat.get("type") == "private":
            # Preserve the owner's teaching flow even if the lesson mentions sending PDFs.
            command = (message.get("text") or "").strip()
            if requests_pdf(command):
                uid = int(user.get("id", 0))
                step, _ = bot.get_session(uid)
                if step != "admin_teach":
                    bot.ensure_user(user)
                    return send_catalog(uid, chat["id"])
        return original_text(message)

    def handle_callback(callback):
        chat = callback.get("message", {}).get("chat", {})
        if callback.get("data") == CALLBACK:
            bot.answer_cb(callback["id"])
            if chat.get("type") != "private":
                return
            user = callback["from"]
            bot.ensure_user(user)
            return send_catalog(int(user["id"]), chat["id"])
        return original_callback(callback)

    bot.main_menu, bot.handle_text, bot.handle_callback = main_menu, handle_text, handle_callback
    bot.catalog_keyboard, bot.catalog_should_offer = keyboard, should_offer
    bot.send_catalog = send_catalog
    print("Customer catalog PDF extension installed.", flush=True)
