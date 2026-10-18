import csv, json, os, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
CFG = json.load(open(os.path.join(ROOT, "config.json")))
LOCAL = timezone(timedelta(hours=CFG["timezone_offset_hours"]))


def now():
    return datetime.now(timezone.utc)


def local(dt):
    return dt.astimezone(LOCAL).strftime("%d-%b-%Y %H:%M:%S IST")


def fmt_dur(sec):
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return (f"{h}h " if h else "") + (f"{m}m " if h or m else "") + f"{s}s"


def telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[telegram not configured]", text.encode("ascii", "replace").decode())
        return
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    try:
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=20)
    except Exception as e:
        print("telegram failed:", e)


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
