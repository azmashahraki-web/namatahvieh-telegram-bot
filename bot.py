import os, json, time, secrets, string, csv, io, traceback
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError

TOKEN=os.getenv("BOT_TOKEN","").strip()
SETUP_SECRET=os.getenv("SETUP_SECRET","").strip()
BUSINESS_NAME=os.getenv("BUSINESS_NAME","نما تهویه")
REWARD_POINTS=int(os.getenv("REWARD_POINTS","1") or "1")
SUPABASE_URL=os.getenv("SUPABASE_URL","").rstrip("/")
SUPABASE_KEY=os.getenv("SUPABASE_KEY","").strip()
BOT_DB_SECRET=os.getenv("BOT_DB_SECRET","").strip()
API=f"https://api.telegram.org/bot{TOKEN}/" if TOKEN else ""

def db(action,payload=None):
    if not (SUPABASE_URL and SUPABASE_KEY and BOT_DB_SECRET):
        raise RuntimeError("Supabase configuration missing")
    body=json.dumps({"action":action,"payload":payload or {}},ensure_ascii=False).encode()
    req=Request(SUPABASE_URL+"/rest/v1/rpc/bot_api",data=body,headers={
        "Content-Type":"application/json","apikey":SUPABASE_KEY,
        "Authorization":"Bearer "+SUPABASE_KEY,"x-app-api-key":BOT_DB_SECRET})
    try:
        with urlopen(req,timeout=30) as r:
            raw=r.read().decode()
            return json.loads(raw) if raw else None
    except HTTPError as e:
        detail=e.read().decode(errors="replace")
        raise RuntimeError(f"DB {e.code}: {detail[:500]}")

def cfg(k,default=None):
    x=db("cfg_get",{"k":k}); return x.get("value") if x and x.get("value") is not None else default
def setcfg(k,v): return db("cfg_set",{"k":k,"v":str(v)})
def owner_id():
    v=cfg("owner_id"); return int(v) if v and str(v).isdigit() else None
def is_owner(uid): return owner_id()==int(uid)

def api(method,data=None,files=None,timeout=60):
    if not TOKEN: raise RuntimeError("BOT_TOKEN missing")
    url=API+method; data=data or {}
    if files:
        boundary="----TG"+secrets.token_hex(8); body=bytearray()
        def add(s): body.extend(s.encode())
        for k,v in data.items(): add(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
        for field,(filename,content,ctype) in files.items():
            add(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n')
            body.extend(content); add("\r\n")
        add(f"--{boundary}--\r\n")
        req=Request(url,data=bytes(body),headers={"Content-Type":f"multipart/form-data; boundary={boundary}"})
    else:
        payload=urlencode({k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v) for k,v in data.items()}).encode()
        req=Request(url,data=payload)
    with urlopen(req,timeout=timeout) as r: out=json.loads(r.read().decode())
    if not out.get("ok"): raise RuntimeError(out)
    return out.get("result")

def send(chat_id,text,keyboard=None,reply_markup=None):
    d={"chat_id":chat_id,"text":text}
    if reply_markup is not None:d["reply_markup"]=reply_markup
    elif keyboard is not None:d["reply_markup"]={"inline_keyboard":keyboard}
    return api("sendMessage",d)
def answer_cb(cid,text=None,alert=False):
    d={"callback_query_id":cid}
    if text:d["text"]=text
    if alert:d["show_alert"]="true"
    try:api("answerCallbackQuery",d)
    except:pass

def main_menu(uid):
    kb=[
      [{"text":"❄️ مشاوره خرید کولر گازی","callback_data":"consult_ac"}],
      [{"text":"🏠 لوازم خانگی","callback_data":"home_menu"},{"text":"💰 استعلام قیمت","callback_data":"quote"}],
      [{"text":"📞 درخواست تماس فروشنده","callback_data":"callback"}],
    ]
    link=cfg("channel_link")
    if link:kb.append([{"text":"📢 کانال آزما شهرکی","url":link},{"text":"✅ بررسی عضویت","callback_data":"verify"}])
    kb += [[{"text":"🎁 لینک دعوت من","callback_data":"invite"},{"text":"⭐ امتیاز من","callback_data":"points"}]]
    return kb

def ensure_user(u,payload=""):
    return db("ensure_user",{"telegram_id":int(u["id"]),"first_name":u.get("first_name",""),
        "username":u.get("username",""),"start_payload":payload or ""})

def start(chat_id,u,payload=""):
    ensure_user(u,payload)
    extra="\n\n🔐 مالک ربات هنوز ثبت نشده است." if owner_id() is None else ""
    send(chat_id,f'سلام {u.get("first_name","")} 👋\n\nبه ربات فروش و مشاوره {BUSINESS_NAME} خوش آمدی.\nمی‌توانی ظرفیت کولر را بررسی کنی، قیمت بگیری، درخواست تماس ثبت کنی و با معرفی دوستان امتیاز بگیری.{extra}',main_menu(u["id"]))

def verify_membership(uid,chat_id):
    ch=cfg("channel_id")
    if not ch:return send(chat_id,"کانال هنوز تنظیم نشده است.")
    try:
        m=api("getChatMember",{"chat_id":ch,"user_id":uid})
        ok=m.get("status") in ("member","administrator","creator") or (m.get("status")=="restricted" and m.get("is_member"))
    except:ok=False
    if not ok:return send(chat_id,"هنوز عضویتت تأیید نشد. اول عضو کانال شو و دوباره بررسی عضویت را بزن.",main_menu(uid))
    x=db("verify_award",{"telegram_id":uid,"points":REWARD_POINTS})
    if x and x.get("awarded") and x.get("referrer_id"):
        try:send(int(x["referrer_id"]),f'🎉 یک معرفی واقعی تأیید شد و {x.get("points",REWARD_POINTS)} امتیاز گرفتی.')
        except:pass
    send(chat_id,"✅ عضویتت تأیید شد.",main_menu(uid))

def bot_username():
    v=cfg("bot_username")
    if v:return v
    try:
        v=api("getMe").get("username",""); setcfg("bot_username",v); return v
    except:return ""

def invite(uid,chat_id):
    r=db("user_get",{"telegram_id":uid})
    if not r:return
    b=bot_username()
    if not b:return send(chat_id,"نام کاربری ربات مشخص نشد.")
    link=f'https://t.me/{b}?start=r_{r["ref_code"]}'
    send(chat_id,f"🎁 لینک اختصاصی تو:\n{link}\n\nهر دوست واقعی که از این لینک بیاید و عضویت کانال او تأیید شود، برایت امتیاز ثبت می‌شود.")

def set_session(uid,step,data=None):db("session_set",{"telegram_id":uid,"step":step,"data":data or {}})
def get_session(uid):
    r=db("session_get",{"telegram_id":uid})
    return (r.get("step"),r.get("data") or {}) if r else (None,{})
def clear_session(uid):db("session_delete",{"telegram_id":uid})

def normalize_digits(s):
    return s.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩","01234567890123456789"))
def calc_btu(city,area,usage):
    base={"مسکونی":650,"اداری":750,"تجاری":850}.get(usage,700)
    if any(x in city for x in ["زاهدان","چابهار","اهواز","بندرعباس","بوشهر","کیش","قشم","کرمان","یزد"]):base*=1.12
    need=area*base
    return next((x for x in [9000,12000,18000,24000,30000,36000,48000,60000] if x>=need),60000)

def begin_ac(uid,chat_id):set_session(uid,"ac_city",{});send(chat_id,"❄️ شهر محل نصب را بنویس:")
def home_menu(uid,chat_id):
    kb=[[{"text":"📺 تلویزیون","callback_data":"hp_تلویزیون"},{"text":"🧊 یخچال","callback_data":"hp_یخچال"}],
        [{"text":"🧺 لباسشویی","callback_data":"hp_لباسشویی"},{"text":"🍽 ظرفشویی","callback_data":"hp_ظرفشویی"}],
        [{"text":"🔎 محصول دیگر","callback_data":"hp_سایر"}]]
    send(chat_id,"چه محصولی می‌خواهی؟",kb)
def begin_home(uid,chat_id,product=""):
    d={"product":product} if product and product!="سایر" else {}
    step="home_city" if d else "home_product";set_session(uid,step,d)
    send(chat_id,"شهر شما؟" if d else "نام محصول را بنویس:")
def begin_quote(uid,chat_id):set_session(uid,"quote_product",{});send(chat_id,"💰 نام دقیق محصول یا مدل موردنظرت را بنویس:")
def begin_callback(uid,chat_id):set_session(uid,"callback_reason",{});send(chat_id,"📞 خیلی خوب. کوتاه بنویس برای چه موضوعی می‌خواهی با تو تماس بگیریم:")

def ask_phone(chat_id):
    rm={"keyboard":[[{"text":"📱 ارسال شماره من","request_contact":True}],["بدون شماره ادامه می‌دهم"]],"resize_keyboard":True,"one_time_keyboard":True}
    send(chat_id,"برای تماس فروشنده، شماره‌ات را با دکمه زیر بفرست. ارسال شماره اختیاری است.",reply_markup=rm)

def save_lead(uid,kind,d,phone=""):
    x=db("lead_insert",{"telegram_id":uid,"kind":kind,"city":d.get("city"),"area":d.get("area"),
      "usage":d.get("usage"),"budget":d.get("budget"),"recommended_btu":d.get("btu"),
      "phone":phone,"product":d.get("product"),"details":d})
    oid=owner_id(); camp=(x or {}).get("campaign") or "مستقیم"
    if oid:
        try:
            if kind=="کولر گازی":
                txt=f'🔥 لید جدید کولر گازی\nشهر: {d.get("city")}\nمتراژ: {d.get("area")} متر\nکاربری: {d.get("usage")}\nاولویت: {d.get("budget")}\nظرفیت اولیه: {d.get("btu")} BTU\nتلفن: {phone or "ثبت نشده"}\nکمپین: {camp}'
            elif kind=="استعلام قیمت":
                txt=f'💰 استعلام قیمت جدید\nمحصول/مدل: {d.get("product")}\nشهر: {d.get("city")}\nتلفن: {phone or "ثبت نشده"}\nکمپین: {camp}'
            elif kind=="درخواست تماس":
                txt=f'📞 درخواست تماس جدید\nموضوع: {d.get("reason")}\nتلفن: {phone or "ثبت نشده"}\nکمپین: {camp}'
            else:
                txt=f'🔥 لید لوازم خانگی\nمحصول: {d.get("product")}\nشهر: {d.get("city")}\nبودجه/اولویت: {d.get("budget")}\nتلفن: {phone or "ثبت نشده"}\nکمپین: {camp}'
            send(oid,txt)
        except:pass

def finish(uid,chat_id,kind,d,phone=""):
    save_lead(uid,kind,d,phone);clear_session(uid)
    if kind=="کولر گازی":
        msg=f'✅ درخواست ثبت شد.\n\nپیشنهاد اولیه برای {d.get("area")} متر در {d.get("city")}: حدود {d.get("btu")} BTU.\nانتخاب نهایی باید با شرایط واقعی محل نصب کنترل شود.'
    elif kind=="استعلام قیمت":msg="✅ استعلام قیمت ثبت شد و برای پیگیری فروش ارسال شد."
    elif kind=="درخواست تماس":msg="✅ درخواست تماس ثبت شد."
    else:msg="✅ درخواست خرید ثبت شد و برای پیگیری فروش ارسال شد."
    send(chat_id,msg,reply_markup={"remove_keyboard":True});send(chat_id,"چه کار دیگری انجام بدهم؟",main_menu(uid))

def handle_text(msg):
    chat=msg["chat"];chat_id=chat["id"];u=msg.get("from",{});uid=int(u.get("id",0));text=(msg.get("text") or "").strip()
    if chat.get("type")!="private":return
    if text.startswith("/start"):
        p=text.split(maxsplit=1);return start(chat_id,u,p[1].strip() if len(p)>1 else "")
    ensure_user(u)
    if text.startswith("/claim"):
        p=text.split(maxsplit=1)
        if owner_id() is not None:return send(chat_id,"مالک ربات قبلاً ثبت شده است.")
        if len(p)==2 and SETUP_SECRET and secrets.compare_digest(p[1].strip(),SETUP_SECRET):
            setcfg("owner_id",uid);return send(chat_id,"✅ این حساب به‌عنوان مالک ربات ثبت شد.")
        return send(chat_id,"کد راه‌اندازی صحیح نیست.")
    if text=="/id":return send(chat_id,f"Telegram ID: {uid}")
    if text.startswith("/setchannel"):
        if not is_owner(uid):return send(chat_id,"این دستور فقط برای مالک ربات است.")
        p=text.split(maxsplit=1)
        if len(p)<2:return send(chat_id,"مثال: /setchannel @azmashahraki")
        ch=p[1].strip();setcfg("channel_id",ch)
        if ch.startswith("@"):setcfg("channel_link","https://t.me/"+ch[1:])
        return send(chat_id,f"✅ کانال روی {ch} تنظیم شد.")
    if text.startswith("/setlink"):
        if not is_owner(uid):return
        p=text.split(maxsplit=1)
        if len(p)==2:setcfg("channel_link",p[1].strip());send(chat_id,"✅ لینک کانال ذخیره شد.")
        return
    if text=="/admin":
        if not is_owner(uid):return
        x=db("stats")
        return send(chat_id,f'📊 داشبورد فروش\n\n👥 کاربران: {x["users"]}\n✅ اعضای تأییدشده: {x["verified"]}\n🎁 معرفی موفق: {x["referrals"]}\n🔥 لید فروش: {x["leads"]}')
    if text=="/campaigns":
        if not is_owner(uid):return
        rows=db("campaigns") or []
        return send(chat_id,"\n".join(["📈 کمپین‌ها"]+[f'{r["campaign"]}: {r["users"]} ورودی / {r["leads"]} لید' for r in rows[:20]]))
    if text=="/leads":
        if not is_owner(uid):return
        rows=db("leads_all") or [];s=io.StringIO();w=csv.writer(s)
        cols=["id","telegram_id","kind","product","city","area","usage","budget","recommended_btu","phone","campaign","status","created_at"]
        w.writerow(cols)
        for r in rows:w.writerow([r.get(k) for k in cols])
        return api("sendDocument",{"chat_id":chat_id,"caption":"خروجی لیدها"},files={"document":("leads.csv",("\ufeff"+s.getvalue()).encode(),"text/csv")})
    if text=="/privacy":return send(chat_id,"اطلاعات فقط برای عضویت، امتیاز معرفی و پیگیری فروش ذخیره می‌شود. شماره تماس اختیاری است. برای حذف اطلاعات /delete_me را بفرست.")
    if text=="/delete_me":
        db("delete_user",{"telegram_id":uid});return send(chat_id,"✅ اطلاعات شخصی ثبت‌شده‌ات حذف شد.")

    step,d=get_session(uid)
    if not step:return send(chat_id,"از منوی زیر انتخاب کن:",main_menu(uid))
    if step=="ac_city":d["city"]=text[:80];set_session(uid,"ac_area",d);return send(chat_id,"متراژ تقریبی چند متر است؟ فقط عدد.")
    if step=="ac_area":
        try:area=float(normalize_digits(text).replace(",","."))
        except:return send(chat_id,"فقط عدد بنویس؛ مثلاً 85")
        if area<5 or area>1000:return send(chat_id,"متراژ را بین 5 تا 1000 وارد کن.")
        d["area"]=area;set_session(uid,"ac_usage",d)
        return send(chat_id,"نوع کاربری چیست؟",[[{"text":"مسکونی","callback_data":"use_مسکونی"},{"text":"اداری","callback_data":"use_اداری"}],[{"text":"تجاری","callback_data":"use_تجاری"}]])
    if step=="home_product":d["product"]=text[:100];set_session(uid,"home_city",d);return send(chat_id,"شهر شما؟")
    if step=="home_city":d["city"]=text[:80];set_session(uid,"home_budget",d);return send(chat_id,"بودجه یا اولویتت را بنویس (اقتصادی، کیفیت بالا یا بازه قیمت):")
    if step=="home_budget":d["budget"]=text[:120];set_session(uid,"home_phone",d);return ask_phone(chat_id)
    if step=="quote_product":d["product"]=text[:160];set_session(uid,"quote_city",d);return send(chat_id,"شهر شما؟")
    if step=="quote_city":d["city"]=text[:80];set_session(uid,"quote_phone",d);return ask_phone(chat_id)
    if step=="callback_reason":d["reason"]=text[:250];set_session(uid,"callback_phone",d);return ask_phone(chat_id)
    if step.endswith("_phone"):
        kind={"ac_phone":"کولر گازی","home_phone":"لوازم خانگی","quote_phone":"استعلام قیمت","callback_phone":"درخواست تماس"}.get(step)
        if text=="بدون شماره ادامه می‌دهم":return finish(uid,chat_id,kind,d,"")
        return send(chat_id,'از دکمه «ارسال شماره من» استفاده کن یا «بدون شماره ادامه می‌دهم» را بزن.')

def handle_contact(msg):
    u=msg.get("from",{});uid=int(u.get("id",0));chat_id=msg["chat"]["id"];ensure_user(u)
    c=msg.get("contact",{});phone=c.get("phone_number","")
    if c.get("user_id") and int(c["user_id"])!=uid:phone=""
    step,d=get_session(uid)
    kind={"ac_phone":"کولر گازی","home_phone":"لوازم خانگی","quote_phone":"استعلام قیمت","callback_phone":"درخواست تماس"}.get(step)
    if kind:finish(uid,chat_id,kind,d,phone)

def handle_callback(cb):
    uid=int(cb["from"]["id"]);chat_id=cb.get("message",{}).get("chat",{}).get("id",uid);data=cb.get("data","")
    ensure_user(cb["from"]);answer_cb(cb["id"])
    if data=="verify":return verify_membership(uid,chat_id)
    if data=="invite":return invite(uid,chat_id)
    if data=="points":
        r=db("user_get",{"telegram_id":uid});return send(chat_id,f'⭐ امتیاز فعلی تو: {r.get("points",0) if r else 0}')
    if data=="consult_ac":return begin_ac(uid,chat_id)
    if data=="home_menu":return home_menu(uid,chat_id)
    if data=="quote":return begin_quote(uid,chat_id)
    if data=="callback":return begin_callback(uid,chat_id)
    if data.startswith("hp_"):return begin_home(uid,chat_id,data[3:])
    if data.startswith("use_"):
        step,d=get_session(uid)
        if step!="ac_usage":return
        d["usage"]=data[4:];set_session(uid,"ac_budget",d)
        return send(chat_id,"اولویت خریدت چیست؟",[[{"text":"اقتصادی","callback_data":"budget_اقتصادی"},{"text":"متعادل","callback_data":"budget_متعادل"}],[{"text":"بهترین کیفیت","callback_data":"budget_بهترین کیفیت"}]])
    if data.startswith("budget_"):
        step,d=get_session(uid)
        if step!="ac_budget":return
        d["budget"]=data[7:];d["btu"]=calc_btu(d.get("city",""),float(d.get("area",0)),d.get("usage",""))
        set_session(uid,"ac_phone",d);send(chat_id,f'پیشنهاد اولیه ظرفیت: حدود {d["btu"]} BTU');return ask_phone(chat_id)

def run():
    if not TOKEN:
        print("BOT_TOKEN missing",flush=True)
        while True:time.sleep(3600)
    try:
        me=api("getMe");setcfg("bot_username",me.get("username",""));print("Bot online:",me.get("username"),flush=True)
    except Exception as e:print("startup failed:",repr(e),flush=True)
    offset=0
    while True:
        try:
            ups=api("getUpdates",{"timeout":45,"offset":offset,"allowed_updates":["message","callback_query"]},timeout=55)
            for up in ups:
                offset=max(offset,int(up["update_id"])+1)
                try:
                    if "callback_query" in up:handle_callback(up["callback_query"])
                    elif "message" in up:
                        m=up["message"];handle_contact(m) if "contact" in m else handle_text(m)
                except Exception:traceback.print_exc()
        except (HTTPError,URLError,TimeoutError) as e:print("poll error",repr(e),flush=True);time.sleep(3)
        except Exception:traceback.print_exc();time.sleep(3)

if __name__=="__main__":run()
