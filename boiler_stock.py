"""Owner-confirmed boiler prices and availability override older records."""
import re
STOCK = {22:730000000,24:820000000,26:980000000}
NOTICE = 'موجودی قطعی اعلام‌شده فروشگاه: فقط پکیج بوتان بی‌تا ۲۲، ۲۴ و ۲۶ موجود است. سایر پکیج‌های بوتان و تمام پکیج‌های ایران‌رادیاتور ناموجودند. قیمت‌ها به ریال: بی‌تا ۲۲: ۷۳۰٬۰۰۰٬۰۰۰؛ بی‌تا ۲۴: ۸۲۰٬۰۰۰٬۰۰۰؛ بی‌تا ۲۶: ۹۸۰٬۰۰۰٬۰۰۰. این اطلاعات بر تمام قیمت‌ها و موجودی‌های قدیمی پکیج اولویت دارد. حمل جداگانه هماهنگ می‌شود.'
def answer(raw):
 import latest_prices
 q=latest_prices.normalize(raw)
 boiler=any(x in q for x in ('پکیج','شوفاژ','BITA','بی تا','بیتا','بی‌تا','پرلا','پارما','PERLA','PARMA'))
 if not boiler:return None
 bita=any(x in q for x in ('BITA','بی تا','بیتا'))
 if bita:
  caps=[c for c in STOCK if re.search(r'(?<!\d)'+str(c)+r'(?:000|[٬,]000)?(?!\d)',q)]
  if caps:return '\n'.join(f'پکیج بوتان بی‌تا {c}: {STOCK[c]:,} ریال — موجود' for c in caps)+'\n\n'+NOTICE
 if any(x in q for x in ('پرلا','پارما','PERLA','PARMA','ایران رادیاتور')):return 'این پکیج در فروشگاه ناموجود است.\n\n'+NOTICE
 if any(x in q for x in ('قیمت','موجود','دارید','دارین','چند','لیست','پکیج','BITA','بی تا','بیتا')):return NOTICE
 return None
def install(bot):
 original=bot.handle_text
 def handle(message):
  raw=message.get('text','') or ''
  if message.get('chat',{}).get('type')!='private' or raw.startswith('/'):return original(message)
  step,_=bot.get_session(int(message.get('from',{}).get('id',0)))
  import catalog_pdf
  if step or catalog_pdf.requests_pdf(raw):return original(message)
  result=answer(raw)
  if result:return bot.send(message['chat']['id'],result,bot.catalog_keyboard())
  return original(message)
 bot.handle_text=handle
