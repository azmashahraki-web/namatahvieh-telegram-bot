"""Authoritative dated customer prices, without factory prices. Source: 1405/07/19 customer catalog pages 67-69."""
import re

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
def install(bot):
    original = bot.handle_text
    def handle_text(message):
        if message.get("chat",{}).get("type") != "private":
            return original(message)
        raw = message.get("text","") or ""
        if raw.startswith("/"):
            return original(message)
        q = raw.upper().replace(" ","")
        matches = [(model,price) for model,price in PRICES.items() if re.search(r"(?<![A-Z0-9.])"+re.escape(model)+r"(?![A-Z0-9.])",q)]
        if matches:
            bot.ensure_user(message.get("from",{}))
            rows = [f"{model}: {price:,}" for model,price in matches[:15]]
            return bot.send(message["chat"]["id"], "💰 قیمت مصرف‌کننده جی‌پلاس:\n"+"\n".join(rows)+"\n\n"+NOTICE)
        if any(word in raw for word in ("قیمت","چند","نرخ","لیست")):
            for series,options in RADIATORS.items():
                if series in raw:
                    numbers = re.findall(r"\d+", raw.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹","0123456789")))
                    count = next((int(n) for n in numbers if int(n) in options),None)
                    if count:
                        bot.ensure_user(message.get("from",{}))
                        return bot.send(message["chat"]["id"],f"💰 رادیاتور {series} {count} پره: {options[count]:,}\n\n"+NOTICE)
        return original(message)
    bot.handle_text = handle_text
