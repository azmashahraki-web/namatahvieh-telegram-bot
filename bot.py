import os, json, time, sqlite3, secrets, string, csv, io, traceback
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError

TOKEN = os.getenv('BOT_TOKEN','').strip()
SETUP_SECRET = os.getenv('SETUP_SECRET','').strip()
DB_PATH = os.getenv('DB_PATH','/data/bot.db')
BUSINESS_NAME = os.getenv('BUSINESS_NAME','نما تهویه')
REWARD_POINTS = int(os.getenv('REWARD_POINTS','1') or '1')
API = f'https://api.telegram.org/bot{TOKEN}/' if TOKEN else ''

os.makedirs(os.path.dirname(DB_PATH) or '.', exist_ok=True)
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row

SCHEMA = '''
CREATE TABLE IF NOT EXISTS config (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS users (
  telegram_id INTEGER PRIMARY KEY,
  first_name TEXT, username TEXT, ref_code TEXT UNIQUE,
  referrer_id INTEGER, campaign TEXT,
  verified INTEGER DEFAULT 0, points INTEGER DEFAULT 0,
  created_at INTEGER
);
CREATE TABLE IF NOT EXISTS rewards (
  referred_id INTEGER PRIMARY KEY,
  referrer_id INTEGER NOT NULL,
  points INTEGER NOT NULL,
  created_at INTEGER
);
CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  telegram_id INTEGER, kind TEXT, city TEXT, area REAL,
  usage TEXT, budget TEXT, recommended_btu INTEGER,
  phone TEXT, campaign TEXT, created_at INTEGER
);
CREATE TABLE IF NOT EXISTS sessions (
  telegram_id INTEGER PRIMARY KEY,
  step TEXT, data TEXT
);
'''
conn.executescript(SCHEMA)
conn.commit()

def q1(sql, args=()):
    return conn.execute(sql,args).fetchone()

def qall(sql,args=()):
    return conn.execute(sql,args).fetchall()

def execsql(sql,args=()):
    cur=conn.execute(sql,args); conn.commit(); return cur

def cfg(k, default=None):
    r=q1('SELECT v FROM config WHERE k=?',(k,)); return r['v'] if r else default

def setcfg(k,v):
    execsql('INSERT INTO config(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v',(k,str(v)))

def owner_id():
    v=cfg('owner_id'); return int(v) if v and v.isdigit() else None

def is_owner(uid):
    return owner_id()==int(uid)

def api(method, data=None, files=None, timeout=60):
    if not TOKEN: raise RuntimeError('BOT_TOKEN missing')
    url=API+method
    data=data or {}
    if files:
        boundary='----TG'+secrets.token_hex(8)
        body=bytearray()
        def add(s): body.extend(s.encode('utf-8'))
        for k,v in data.items():
            add(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
        for field,(filename,content,ctype) in files.items():
            add(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n')
            body.extend(content); add('\r\n')
        add(f'--{boundary}--\r\n')
        req=Request(url,data=bytes(body),headers={'Content-Type':f'multipart/form-data; boundary={boundary}'})
    else:
        payload=urlencode({k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v) for k,v in data.items()}).encode()
        req=Request(url,data=payload)
    with urlopen(req, timeout=timeout) as r:
        out=json.loads(r.read().decode())
    if not out.get('ok'): raise RuntimeError(out)
    return out.get('result')

def send(chat_id,text,keyboard=None,parse_mode=None,reply_markup=None):
    d={'chat_id':chat_id,'text':text}
    if parse_mode: d['parse_mode']=parse_mode
    if reply_markup is not None: d['reply_markup']=reply_markup
    elif keyboard is not None: d['reply_markup']={'inline_keyboard':keyboard}
    return api('sendMessage',d)

def answer_cb(cb_id,text=None,alert=False):
    d={'callback_query_id':cb_id}
    if text: d['text']=text
    if alert: d['show_alert']='true'
    try: api('answerCallbackQuery',d)
    except Exception: pass

def main_menu(uid):
    channel_link=cfg('channel_link')
    kb=[]
    if channel_link: kb.append([{'text':'📢 عضویت در کانال','url':channel_link}])
    kb += [
      [{'text':'✅ عضو شدم؛ بررسی کن','callback_data':'verify'}],
      [{'text':'❄️ مشاوره خرید کولر گازی','callback_data':'consult_ac'}],
      [{'text':'🏠 مشاوره لوازم خانگی','callback_data':'consult_home'}],
      [{'text':'🎁 لینک دعوت من','callback_data':'invite'}],
      [{'text':'⭐ امتیاز من','callback_data':'points'}],
    ]
    return kb

def ensure_user(u, payload=''):
    uid=int(u['id']); now=int(time.time())
    row=q1('SELECT * FROM users WHERE telegram_id=?',(uid,))
    new=row is None
    if new:
        alphabet=string.ascii_letters+string.digits
        while True:
            rc=''.join(secrets.choice(alphabet) for _ in range(8))
            if not q1('SELECT 1 FROM users WHERE ref_code=?',(rc,)): break
        referrer=None; campaign=None
        if payload.startswith('r_'):
            rr=q1('SELECT telegram_id FROM users WHERE ref_code=?',(payload[2:],))
            if rr and int(rr['telegram_id'])!=uid: referrer=int(rr['telegram_id'])
        elif payload.startswith('c_'):
            campaign=payload[2:][:80]
        execsql('INSERT INTO users(telegram_id,first_name,username,ref_code,referrer_id,campaign,created_at) VALUES(?,?,?,?,?,?,?)',
                (uid,u.get('first_name',''),u.get('username',''),rc,referrer,campaign,now))
    else:
        execsql('UPDATE users SET first_name=?, username=? WHERE telegram_id=?',(u.get('first_name',''),u.get('username',''),uid))
        if payload.startswith('c_') and not row['campaign']:
            execsql('UPDATE users SET campaign=? WHERE telegram_id=?',(payload[2:][:80],uid))
    return q1('SELECT * FROM users WHERE telegram_id=?',(uid,))

def start(chat_id, u, payload=''):
    ensure_user(u,payload)
    extra=''
    if owner_id() is None:
        extra='\n\n🔐 مالک ربات هنوز ثبت نشده است.'
    send(chat_id,
         f'سلام {u.get("first_name","")} 👋\n\nبه ربات {BUSINESS_NAME} خوش آمدی. اینجا می‌توانی مشاوره خرید بگیری، عضو کانال شوی و با معرفی دوستان امتیاز بگیری.{extra}',
         main_menu(u['id']))

def verify_membership(uid, chat_id):
    ch=cfg('channel_id')
    if not ch:
        send(chat_id,'کانال هنوز توسط مدیر تنظیم نشده است.'); return
    try:
        m=api('getChatMember',{'chat_id':ch,'user_id':uid})
        ok=m.get('status') in ('member','administrator','creator') or (m.get('status')=='restricted' and m.get('is_member'))
    except Exception:
        ok=False
    if not ok:
        send(chat_id,'هنوز عضویتت تأیید نشد. اول وارد کانال شو و دوباره «عضو شدم» را بزن.', main_menu(uid)); return
    row=q1('SELECT * FROM users WHERE telegram_id=?',(uid,))
    if not row: return
    if not row['verified']:
        execsql('UPDATE users SET verified=1 WHERE telegram_id=?',(uid,))
        rid=row['referrer_id']
        if rid and not q1('SELECT 1 FROM rewards WHERE referred_id=?',(uid,)):
            execsql('INSERT INTO rewards(referred_id,referrer_id,points,created_at) VALUES(?,?,?,?)',(uid,rid,REWARD_POINTS,int(time.time())))
            execsql('UPDATE users SET points=points+? WHERE telegram_id=?',(REWARD_POINTS,rid))
            try: send(rid,f'🎉 یک معرفی واقعی تأیید شد و {REWARD_POINTS} امتیاز گرفتی.')
            except Exception: pass
    send(chat_id,'✅ عضویتت تأیید شد.', main_menu(uid))

def bot_username():
    v=cfg('bot_username')
    if v: return v
    try:
        me=api('getMe'); v=me.get('username',''); setcfg('bot_username',v); return v
    except Exception: return ''

def invite(uid,chat_id):
    row=q1('SELECT ref_code FROM users WHERE telegram_id=?',(uid,))
    if not row: return
    b=bot_username()
    if not b: send(chat_id,'نام کاربری ربات مشخص نشد.'); return
    link=f'https://t.me/{b}?start=r_{row["ref_code"]}'
    send(chat_id,f'🎁 لینک اختصاصی تو:\n{link}\n\nهر دوست واقعی که از این لینک بیاید و عضویت کانال او تأیید شود، برایت امتیاز ثبت می‌شود.')

def set_session(uid,step,data=None):
    execsql('INSERT INTO sessions(telegram_id,step,data) VALUES(?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET step=excluded.step,data=excluded.data',(uid,step,json.dumps(data or {},ensure_ascii=False)))

def get_session(uid):
    r=q1('SELECT * FROM sessions WHERE telegram_id=?',(uid,))
    if not r:return None,{}
    try:d=json.loads(r['data'] or '{}')
    except:d={}
    return r['step'],d

def clear_session(uid): execsql('DELETE FROM sessions WHERE telegram_id=?',(uid,))

def begin_ac(uid,chat_id):
    set_session(uid,'ac_city',{})
    send(chat_id,'❄️ خیلی خوب. شهر محل نصب را بنویس (مثلاً مشهد یا زاهدان):')

def begin_home(uid,chat_id):
    set_session(uid,'home_product',{})
    send(chat_id,'🏠 چه وسیله‌ای می‌خواهی؟ مثلاً تلویزیون، یخچال، لباسشویی یا ظرفشویی:')

def normalize_digits(s):
    trans=str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789')
    return s.translate(trans)

def calc_btu(city, area, usage):
    base={'مسکونی':650,'اداری':750,'تجاری':850}.get(usage,700)
    hot=['زاهدان','چابهار','اهواز','بندرعباس','بوشهر','کیش','قشم','کرمان','یزد']
    if any(x in city for x in hot): base*=1.12
    need=area*base
    standards=[9000,12000,18000,24000,30000,36000,48000,60000]
    return next((x for x in standards if x>=need),60000)

def save_lead(uid, kind, d, phone=''):
    u=q1('SELECT campaign FROM users WHERE telegram_id=?',(uid,))
    camp=u['campaign'] if u else None
    execsql('INSERT INTO leads(telegram_id,kind,city,area,usage,budget,recommended_btu,phone,campaign,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (uid,kind,d.get('city'),d.get('area'),d.get('usage'),d.get('budget'),d.get('btu'),phone,camp,int(time.time())))
    oid=owner_id()
    if oid:
        try:
            if kind=='کولر گازی':
                txt=f'🔥 لید جدید کولر گازی\nشهر: {d.get("city")}\nمتراژ: {d.get("area")} متر\nکاربری: {d.get("usage")}\nاولویت: {d.get("budget")}\nپیشنهاد اولیه: {d.get("btu")} BTU\nتلفن: {phone or "ثبت نشده"}\nکمپین: {camp or "مستقیم"}\nTelegram ID: {uid}'
            else:
                txt=f'🔥 لید جدید لوازم خانگی\nمحصول: {d.get("product")}\nشهر: {d.get("city")}\nبودجه/اولویت: {d.get("budget")}\nتلفن: {phone or "ثبت نشده"}\nکمپین: {camp or "مستقیم"}\nTelegram ID: {uid}'
            send(oid,txt)
        except Exception: pass

def ask_phone(chat_id):
    rm={'keyboard':[[{'text':'📱 ارسال شماره من','request_contact':True}],['بدون شماره ادامه می‌دهم']], 'resize_keyboard':True,'one_time_keyboard':True}
    send(chat_id,'اگر می‌خواهی فروشنده با تو تماس بگیرد، شماره‌ات را با دکمه زیر بفرست. در غیر این صورت «بدون شماره ادامه می‌دهم» را بزن.',reply_markup=rm)

def finish_ac(uid,chat_id,d,phone=''):
    save_lead(uid,'کولر گازی',d,phone)
    clear_session(uid)
    send(chat_id,f'✅ درخواستت ثبت شد.\n\nپیشنهاد اولیه برای {d.get("area")} متر در {d.get("city")}: حدود {d.get("btu")} BTU.\n\nاین عدد غربال‌گری اولیه است؛ آفتاب‌گیری، ارتفاع سقف و شرایط محل نصب باید برای انتخاب نهایی بررسی شود.',reply_markup={'remove_keyboard':True})
    send(chat_id,'چه کار دیگری انجام بدهم؟',main_menu(uid))

def finish_home(uid,chat_id,d,phone=''):
    save_lead(uid,'لوازم خانگی',d,phone)
    clear_session(uid)
    send(chat_id,'✅ درخواستت ثبت شد و برای پیگیری فروش ارسال شد.',reply_markup={'remove_keyboard':True})
    send(chat_id,'چه کار دیگری انجام بدهم؟',main_menu(uid))

def handle_text(msg):
    chat=msg['chat']; chat_id=chat['id']; u=msg.get('from',{}); uid=int(u.get('id',0)); text=(msg.get('text') or '').strip()
    if chat.get('type')!='private': return
    payload=''
    if text.startswith('/start'):
        parts=text.split(maxsplit=1); payload=parts[1].strip() if len(parts)>1 else ''
        start(chat_id,u,payload); return
    ensure_user(u)
    if text.startswith('/claim'):
        parts=text.split(maxsplit=1)
        if owner_id() is not None:
            send(chat_id,'مالک ربات قبلاً ثبت شده است.'); return
        if len(parts)==2 and SETUP_SECRET and secrets.compare_digest(parts[1].strip(),SETUP_SECRET):
            setcfg('owner_id',uid); send(chat_id,'✅ این حساب به‌عنوان مالک ربات ثبت شد. حالا کانال را با دستور زیر تنظیم کن:\n/setchannel @username'); return
        send(chat_id,'کد راه‌اندازی صحیح نیست.'); return
    if text=='/id': send(chat_id,f'Telegram ID: {uid}'); return
    if text.startswith('/setchannel'):
        if not is_owner(uid): send(chat_id,'این دستور فقط برای مالک ربات است.'); return
        parts=text.split(maxsplit=1)
        if len(parts)<2: send(chat_id,'مثال: /setchannel @namatahvieh'); return
        ch=parts[1].strip()
        setcfg('channel_id',ch)
        if ch.startswith('@'): setcfg('channel_link','https://t.me/'+ch[1:])
        send(chat_id,f'✅ کانال روی {ch} تنظیم شد. ربات باید در همان کانال Admin باشد.'); return
    if text.startswith('/setlink'):
        if not is_owner(uid): return
        parts=text.split(maxsplit=1)
        if len(parts)==2: setcfg('channel_link',parts[1].strip()); send(chat_id,'✅ لینک کانال ذخیره شد.')
        return
    if text=='/admin':
        if not is_owner(uid): return
        total=q1('SELECT COUNT(*) c FROM users')['c']; ver=q1('SELECT COUNT(*) c FROM users WHERE verified=1')['c']; leads=q1('SELECT COUNT(*) c FROM leads')['c']; refs=q1('SELECT COUNT(*) c FROM rewards')['c']
        send(chat_id,f'📊 داشبورد\nکاربران: {total}\nعضویت تأییدشده: {ver}\nمعرفی موفق: {refs}\nلید فروش: {leads}'); return
    if text=='/campaigns':
        if not is_owner(uid): return
        rows=qall("SELECT COALESCE(campaign,'مستقیم') camp, COUNT(*) n FROM users GROUP BY COALESCE(campaign,'مستقیم') ORDER BY n DESC LIMIT 20")
        lrows={r['camp']:r['n'] for r in qall("SELECT COALESCE(campaign,'مستقیم') camp, COUNT(*) n FROM leads GROUP BY COALESCE(campaign,'مستقیم')")}
        lines=['📈 کمپین‌ها']+[f"{r['camp']}: {r['n']} ورودی / {lrows.get(r['camp'],0)} لید" for r in rows]
        send(chat_id,'\n'.join(lines)); return
    if text=='/leads':
        if not is_owner(uid): return
        rows=qall('SELECT * FROM leads ORDER BY id DESC')
        s=io.StringIO(); w=csv.writer(s); w.writerow(['id','telegram_id','kind','city','area','usage','budget','recommended_btu','phone','campaign','created_at'])
        for r in rows:w.writerow([r[k] for k in r.keys()])
        content=('\ufeff'+s.getvalue()).encode('utf-8')
        api('sendDocument',{'chat_id':chat_id,'caption':'خروجی لیدها'},files={'document':('leads.csv',content,'text/csv')}); return
    if text=='/privacy':
        send(chat_id,'حریم خصوصی: اطلاعاتی که خودت در ربات وارد می‌کنی فقط برای عضویت، امتیاز معرفی و پیگیری درخواست فروش ذخیره می‌شود. شماره تماس اختیاری است. برای حذف اطلاعاتت /delete_me را بفرست.'); return
    if text=='/delete_me':
        execsql('DELETE FROM sessions WHERE telegram_id=?',(uid,)); execsql('DELETE FROM leads WHERE telegram_id=?',(uid,)); execsql('DELETE FROM users WHERE telegram_id=?',(uid,)); send(chat_id,'اطلاعات شخصی ثبت‌شده‌ات حذف شد.'); return

    step,d=get_session(uid)
    if not step:
        send(chat_id,'از منوی زیر انتخاب کن:',main_menu(uid)); return
    if step=='ac_city':
        d['city']=text[:80]; set_session(uid,'ac_area',d); send(chat_id,'متراژ تقریبی فضای موردنظر چند متر است؟ فقط عدد را بنویس.'); return
    if step=='ac_area':
        try: area=float(normalize_digits(text).replace(',','.'))
        except: send(chat_id,'فقط متراژ را به‌صورت عدد بنویس؛ مثلاً 85'); return
        if area<5 or area>1000: send(chat_id,'متراژ را بین 5 تا 1000 متر وارد کن.'); return
        d['area']=area; set_session(uid,'ac_usage',d)
        kb=[[{'text':'مسکونی','callback_data':'use_مسکونی'},{'text':'اداری','callback_data':'use_اداری'}],[{'text':'تجاری','callback_data':'use_تجاری'}]]
        send(chat_id,'نوع کاربری چیست؟',kb); return
    if step=='home_product':
        d['product']=text[:100]; set_session(uid,'home_city',d); send(chat_id,'شهر شما؟'); return
    if step=='home_city':
        d['city']=text[:80]; set_session(uid,'home_budget',d); send(chat_id,'حدود بودجه یا اولویتت را بنویس (مثلاً اقتصادی، کیفیت بالا، یا بازه قیمت):'); return
    if step=='home_budget':
        d['budget']=text[:120]; set_session(uid,'home_phone',d); ask_phone(chat_id); return
    if step=='ac_phone':
        if text=='بدون شماره ادامه می‌دهم': finish_ac(uid,chat_id,d,''); return
        send(chat_id,'برای ارسال شماره از دکمه «ارسال شماره من» استفاده کن یا «بدون شماره ادامه می‌دهم» را بزن.'); return
    if step=='home_phone':
        if text=='بدون شماره ادامه می‌دهم': finish_home(uid,chat_id,d,''); return
        send(chat_id,'برای ارسال شماره از دکمه «ارسال شماره من» استفاده کن یا «بدون شماره ادامه می‌دهم» را بزن.'); return

def handle_contact(msg):
    u=msg.get('from',{}); uid=int(u.get('id',0)); chat_id=msg['chat']['id']; ensure_user(u)
    c=msg.get('contact',{}); phone=c.get('phone_number','')
    if c.get('user_id') and int(c['user_id'])!=uid: phone=''
    step,d=get_session(uid)
    if step=='ac_phone': finish_ac(uid,chat_id,d,phone)
    elif step=='home_phone': finish_home(uid,chat_id,d,phone)

def handle_callback(cb):
    uid=int(cb['from']['id']); chat_id=cb.get('message',{}).get('chat',{}).get('id',uid); data=cb.get('data','')
    ensure_user(cb['from']); answer_cb(cb['id'])
    if data=='verify': verify_membership(uid,chat_id)
    elif data=='invite': invite(uid,chat_id)
    elif data=='points':
        r=q1('SELECT points FROM users WHERE telegram_id=?',(uid,)); send(chat_id,f'⭐ امتیاز فعلی تو: {r["points"] if r else 0}')
    elif data=='consult_ac': begin_ac(uid,chat_id)
    elif data=='consult_home': begin_home(uid,chat_id)
    elif data.startswith('use_'):
        step,d=get_session(uid)
        if step!='ac_usage': return
        d['usage']=data[4:]; set_session(uid,'ac_budget',d)
        kb=[[{'text':'اقتصادی','callback_data':'budget_اقتصادی'},{'text':'متعادل','callback_data':'budget_متعادل'}],[{'text':'بهترین کیفیت','callback_data':'budget_بهترین کیفیت'}]]
        send(chat_id,'اولویت خریدت چیست؟',kb)
    elif data.startswith('budget_'):
        step,d=get_session(uid)
        if step!='ac_budget': return
        d['budget']=data[7:]; d['btu']=calc_btu(d.get('city',''),float(d.get('area',0)),d.get('usage',''))
        set_session(uid,'ac_phone',d)
        send(chat_id,f'پیشنهاد اولیه ظرفیت: حدود {d["btu"]} BTU')
        ask_phone(chat_id)

def run():
    if not TOKEN:
        print('BOT_TOKEN is not configured; service is idle.', flush=True)
        while True: time.sleep(3600)
    try:
        me=api('getMe'); setcfg('bot_username',me.get('username','')); print('Bot online:',me.get('username'),flush=True)
    except Exception as e:
        print('getMe failed:',e,flush=True)
    offset=0
    while True:
        try:
            updates=api('getUpdates',{'timeout':45,'offset':offset,'allowed_updates':['message','callback_query']},timeout=55)
            for up in updates:
                offset=max(offset,int(up['update_id'])+1)
                try:
                    if 'callback_query' in up: handle_callback(up['callback_query'])
                    elif 'message' in up:
                        m=up['message']
                        if 'contact' in m: handle_contact(m)
                        else: handle_text(m)
                except Exception:
                    traceback.print_exc()
        except (HTTPError,URLError,TimeoutError) as e:
            print('poll error',repr(e),flush=True); time.sleep(3)
        except Exception:
            traceback.print_exc(); time.sleep(3)

if __name__=='__main__': run()
