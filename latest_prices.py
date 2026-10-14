"""Customer amounts copied verbatim from the supplied Gplus sheet and dated radiator image.

No currency conversion or capacity-to-model inference is allowed.
"""
import re
import unicodedata

DATA = """GTV-32SD648N|370000000
GTV-43SH648NR|605000000
GTV-50SU789NR|836000000
GTV-55SU789NL|990000000
GTV-55SQ789N|910000000
GTV-55SQ789NP|910000000
GTV-55SO631NO|1810000000
GTV-65SU789NP|1400000000
GTV-65SQ789NR|1890000000
GTV-75SU888SP|2050000000
GTV-75SQ888SP|1960000000
GTV-65SO631NO|2400000000
GWM-R808W.N|960000000
GWM-R808S.N|980000000
GWM-R909W.N|1120000000
GWM-R909S.N|1140000000
GDW-R5673W|1100000000
GDW-R5673S|1120000000
GDW-R5673NS|1150000000
GDW-R5683W|1250000000
GDW-R5683S|1270000001
GDW-R5683NS|1300000000
GDW-R1599W|1419000000
GDW-R1599S|1439000000
GDW-R1599NS|1459000000
GDW-R1599B|1479000001
GSS-R7927W|2900000000
GSS-R7926W|2900000000
GSS-R7927S|2987000000
GSS-R7927BS|3074000000
GRF-R3120W|1200000000
GRF-R3120S|1236000000
GSS-R9515NS|1900000000
GSS-R7639W|2400000000
GSS-R7639BS|2546160000
GSS-R7639S|2472000000
GVC-A24W|270000000
GVC-A24S|280000000
GVC-A24B|290000000"""
PRICES = dict((model, int(value)) for model,value in (line.split("|") for line in DATA.splitlines()))
RADIATORS = {
    "ایل پرمو": {3:62960700,5:104934500,7:146908300,10:209869000},
    "ویتوریا": {3:53196000,5:88660000,7:124124000,10:177320000},
    "آلنا": {3:53196000,5:88660000,7:124124000,10:177320000},
}
NOTICE = "قیمت مصرف‌کننده مطابق لیست ۱۹ مهر ۱۴۰۵ است. واحد پول در فایل منبع مشخص نشده؛ مبلغ و موجودی نهایی هنگام خرید تأیید می‌شود."


def normalize(text):
    text = unicodedata.normalize("NFKC", text or "").upper()
    text = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    text = text.replace("ي", "ی").replace("ك", "ک").replace("آ", "ا").replace("\u200c", " ")
    for dash in "–—−‑":
        text = text.replace(dash, "-")
    return re.sub(r"\s*([-\.])\s*", r"\1", text)


def exact_prices(text):
    q = normalize(text)
    return [(model, price) for model, price in PRICES.items()
            if re.search(r"(?<![A-Z0-9.\-])" + re.escape(model) + r"(?![A-Z0-9\-]|\.[A-Z0-9])", q)]


def radiator_prices(text):
    q = normalize(text)
    counts = set(int(n) for n in re.findall(r"(?<!\d)(\d+)\s*پره", q))
    for word, count in (("سه", 3), ("پنج", 5), ("هفت", 7), ("ده", 10)):
        if re.search(r"(?<!\w)" + word + r"\s+پره", q):
            counts.add(count)
    return [(f"رادیاتور {series} {count} پره", options[count])
            for series, options in RADIATORS.items() if normalize(series) in q
            for count in sorted(counts) if count in options]


def install(bot):
    original = bot.handle_text
    def handle_text(message):
        if message.get("chat",{}).get("type") != "private":
            return original(message)
        raw = message.get("text","") or ""
        if raw.strip().startswith("/"):
            return original(message)
        uid = int(message.get("from", {}).get("id", 0))
        step, _ = bot.get_session(uid)
        if step:
            return original(message)
        # Keep explicit PDF requests in the document handler, even with a model in the text.
        import catalog_pdf
        if catalog_pdf.requests_pdf(raw):
            return original(message)
        q = normalize(raw)
        price_intent = any(word in q for word in ("قیمت", "چند", "نرخ", "لیست", "مبلغ", "PRICE"))
        matches = exact_prices(raw)
        bare_model = len(matches) == 1 and q.strip() == matches[0][0]
        if not price_intent and not bare_model:
            return original(message)
        models = re.findall(r"(?<![A-Z0-9.\-])G(?:TV|WM|DW|SS|RF|VC)-[A-Z0-9.\-]+", q)
        unknown = [model.rstrip(".") for model in models if model.rstrip(".") not in PRICES]
        matches += radiator_prices(raw)
        if matches:
            bot.ensure_user(message.get("from",{}))
            rows = [f"{model}: {price:,}" for model,price in matches]
            rows += [f"{model}: قیمت تأییدشده برای این کد دقیق ثبت نشده است." for model in unknown]
            return bot.send(message["chat"]["id"], "💰 قیمت مصرف‌کننده:\n"+"\n".join(rows)+"\n\n"+NOTICE,
                            bot.catalog_keyboard())
        if unknown:
            return bot.send(message["chat"]["id"], "برای این کد دقیق قیمت تأییدشده ثبت نشده است: " + "، ".join(unknown) + "\nکد کامل مدل را بررسی کنید یا از فروشنده استعلام بگیرید.")
        if any(normalize(series) in q for series in RADIATORS):
            return bot.send(message["chat"]["id"], "نام سری و تعداد پره را دقیق بنویسید؛ قیمت تأییدشده فقط برای ۳، ۵، ۷ و ۱۰ پره ثبت شده است.")
        if re.search(r"جی\s*پلاس|GPLUS|GAC-", q) and any(w in q for w in ("کولر", "اسپلیت", "GAC-")):
            return bot.send(message["chat"]["id"], "برگه جدید کولر جی‌پلاس قیمت را بر اساس سری و ظرفیت آورده و کد دقیق مدل و واحد پول را مشخص نکرده است. برای قیمت قطعی، عکس پلاک یا کد کامل مدل و تأیید فروشنده لازم است.")
        return original(message)
    bot.handle_text = handle_text
