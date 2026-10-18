import csv, json, os, threading, urllib.request, urllib.parse, uuid
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
STATE = os.path.join(DATA, "state.json")
INCIDENTS = os.path.join(DATA, "incidents.csv")
SETTINGS = os.path.join(DATA, "settings.json")  # overrides written by the Telegram bot
WAKE = threading.Event()  # set when a setting changes so the daemon re-cycles at once

CFG = {}


def reload_cfg():
    base = json.load(open(os.path.join(ROOT, "config.json")))
    try:
        base.update(json.load(open(SETTINGS)))
    except Exception:
        pass
    base.setdefault("paused", False)
    base.setdefault("daily_report_hour", 8)
    CFG.clear()
    CFG.update(base)


def save_setting(key, value):
    try:
        cur = json.load(open(SETTINGS))
    except Exception:
        cur = {}
    cur[key] = value
    os.makedirs(DATA, exist_ok=True)
    json.dump(cur, open(SETTINGS, "w"), indent=1)
    reload_cfg()
    WAKE.set()


reload_cfg()
LOCAL = timezone(timedelta(hours=CFG["timezone_offset_hours"]))


def now():
    return datetime.now(timezone.utc)


def local(dt):
    return dt.astimezone(LOCAL).strftime("%d-%b-%Y %H:%M:%S IST")


def local_short(dt):
    return dt.astimezone(LOCAL).strftime("%d %b %H:%M")


def fmt_dur(sec):
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return " ".join(p for p in (f"{h}h" if h else "", f"{m}m" if m else "", f"{s}s" if s else "") if p) or "0s"


def tg_api(method, params=None, body=None, ctype=None, timeout=20):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[telegram not configured]", method)
        return None
    if body is None:
        body = urllib.parse.urlencode(params or {}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", body,
                                 {"Content-Type": ctype} if ctype else {})
    try:
        return json.load(urllib.request.urlopen(req, timeout=timeout))
    except Exception as e:
        print("telegram failed:", e)
        return None


def telegram(text, html=False, markup=None):
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not chat or not os.environ.get("TELEGRAM_BOT_TOKEN"):
        print("[telegram not configured]", text.encode("ascii", "replace").decode())
        return None
    p = {"chat_id": chat, "text": text, "disable_web_page_preview": "true"}
    if html:
        p["parse_mode"] = "HTML"
    if markup:
        p["reply_markup"] = json.dumps(markup)
    return tg_api("sendMessage", p)


def send_document(path, caption=""):
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    b = uuid.uuid4().hex
    parts = []
    for k, v in {"chat_id": chat, "caption": caption}.items():
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    name = os.path.basename(path)
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="document"; '
                 f'filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
                 + open(path, "rb").read() + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    return tg_api("sendDocument", body=b"".join(parts),
                  ctype=f"multipart/form-data; boundary={b}", timeout=60)


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
