"""Customer amounts copied verbatim from the supplied Gplus sheet and dated radiator image.

Amounts are in IRR after the user-authorized market and catalog currency audit.
No capacity-to-model inference is allowed.
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
NOTICE = "تمام مبالغ به ریال است؛ قیمت مصرف‌کننده مطابق لیست ۱۹ مهر ۱۴۰۵ است. موجودی هر مدل باید از فروشگاه استعلام شود؛ درج قیمت به معنی موجودبودن کالا نیست. قیمت نهایی هنگام خرید تأیید می‌شود."


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


def category_prices(text):
    """Return only the approved Gplus rows, without asking customers for a code."""
    q = normalize(text)
    # Never present another brand's request as a Gplus quote.
    if re.search(r"هایسنس|سامسونگ|ال\s*جی|دوو|اسنوا|پاکشوما|بوش|نکسار|HISENSE|SAMSUNG|BOSCH|\bLG\b", q):
        return []
    categories = (
        ("تلویزیون جی‌پلاس", r"تلویزیون|تلوزیون|\bTV\b", ("GTV-",)),
        ("ظرفشویی جی‌پلاس", r"ظرف\s*شوی", ("GDW-",)),
        ("ساید و یخچال جی‌پلاس", r"ساید|یخچال|فریزر", ("GSS-", "GRF-")),
        ("لباسشویی جی‌پلاس", r"لباس\s*شوی", ("GWM-",)),
    )
    return [(title, [(model, amount) for model, amount in PRICES.items()
                     if model.startswith(prefixes)])
            for title, pattern, prefixes in categories if re.search(pattern, q)]


def radiator_prices(text):
    q = normalize(text)
    names = {normalize(series): series for series in RADIATORS}
    mentions = list(re.finditer("|".join(map(re.escape, names)), q))
    rows = []
    for index, mention in enumerate(mentions):
        # Associate each count with its own series, never a cross-product of all counts.
        segment = q[mention.end():mentions[index + 1].start() if index + 1 < len(mentions) else len(q)]
        if len(mentions) == 1:
            segment = q
        counts = set(int(n) for n in re.findall(r"(?<!\d)(\d+)\s*پره", segment))
        for word, count in (("سه", 3), ("پنج", 5), ("هفت", 7), ("ده", 10)):
            if re.search(r"(?<!\w)" + word + r"\s+پره", segment):
                counts.add(count)
        series = names[mention.group()]
        for count in sorted(counts):
            if count in RADIATORS[series]:
                row = (f"رادیاتور {series} {count} پره", RADIATORS[series][count])
                if row not in rows:
                    rows.append(row)
    return rows


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
        categories = category_prices(raw)
        explicit_document = re.search(r"PDF|پی\s*دی\s*اف|کاتالوگ|فایل", normalize(raw))
        if catalog_pdf.requests_pdf(raw) and (not categories or explicit_document):
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
            rows = [f"{model}: {price:,} ریال" for model,price in matches]
            rows += [f"{model}: قیمت تأییدشده برای این کد دقیق ثبت نشده است." for model in unknown]
            return bot.send(message["chat"]["id"], "💰 قیمت مصرف‌کننده:\n"+"\n".join(rows)+"\n\n"+NOTICE,
                            bot.catalog_keyboard())
        if unknown:
            return bot.send(message["chat"]["id"], "برای این کد دقیق قیمت تأییدشده ثبت نشده است: " + "، ".join(unknown) + "\nکد کامل مدل را بررسی کنید یا از فروشنده استعلام بگیرید.")
        if categories:
            bot.ensure_user(message.get("from", {}))
            blocks = [title + ":\n" + "\n".join(f"{model}: {amount:,} ریال" for model, amount in rows)
                      for title, rows in categories]
            return bot.send(message["chat"]["id"], "💰 قیمت‌های تأییدشده جی‌پلاس:\n\n" +
                            "\n\n".join(blocks) + "\n\n" + NOTICE, bot.catalog_keyboard())
        if any(normalize(series) in q for series in RADIATORS):
            return bot.send(message["chat"]["id"], "نام سری و تعداد پره را دقیق بنویسید؛ قیمت تأییدشده فقط برای ۳، ۵، ۷ و ۱۰ پره ثبت شده است.")
        if re.search(r"جی\s*پلاس|GPLUS|GAC-", q) and any(w in q for w in ("کولر", "اسپلیت", "GAC-")):
            return bot.send(message["chat"]["id"], "برگه جدید کولر قیمت را به ریال بر اساس سری و ظرفیت آورده و کد دقیق مدل را مشخص نکرده است. برای قیمت قطعی، عکس پلاک یا کد کامل مدل و تأیید فروشنده لازم است.")
        return original(message)
    bot.handle_text = handle_text
