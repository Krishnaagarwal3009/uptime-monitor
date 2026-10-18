"""Telegram command handler. Only the configured chat is obeyed."""
import html as H, json, os, re
from datetime import datetime
from common import *
import report as R

OFFSET = os.path.join(DATA, "bot_offset.json")
KEYBOARD = {"keyboard": [[{"text": "/status"}, {"text": "/report"}],
                         [{"text": "/pdf"}, {"text": "/csv"}],
                         [{"text": "/check"}, {"text": "/settings"}],
                         [{"text": "/help"}]], "resize_keyboard": True}

HELP = """🤖 <b>Uptime Monitor</b>

<b>See</b>
/status – live status of every site
/check – check all sites right now
/report [24h|6h|7d] – pretty report
/pdf [24h] – PDF report (share with host)
/csv [24h] – CSV files of checks and outages

<b>Speed</b>
/interval 2m – normal check interval
/downinterval 30s – recheck speed while a site is down
/timeout 20 – seconds before a check fails
/reminder 30 – "still down" reminder, in minutes

<b>Sites</b>
/sites – list sites
/add https://example.com
/remove example.com

<b>Control</b>
/pause · /resume – stop or start alerts
/reporttime 8 – hour (IST) of the daily report
/settings – show all settings
/test – check the bot replies"""

COMMANDS = {}


def cmd(*names):
    def deco(fn):
        for n in names:
            COMMANDS[n] = fn
        return fn
    return deco


def reply(text, **kw):
    telegram(text, html=True, **kw)


def parse_dur(s, default="m"):
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(s|sec|m|min|h|d)?", s.strip().lower())
    if not m:
        return None
    return int(float(m[1]) * {"s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "d": 86400}[m[2] or default])


def parse_hours(s):
    if not s.strip():
        return 24
    sec = parse_dur(s, "h")
    if not sec or not 3600 <= sec <= 30 * 86400:
        raise ValueError("Use 1h to 30d, e.g. /report 6h or /report 7d")
    return sec / 3600


def gh_note():
    return ("\n<i>Note: on GitHub Actions the 5-minute schedule is fixed, so this only affects "
            "rechecks while a site is down.</i>") if os.environ.get("GITHUB_ACTIONS") else ""


def ago(iso):
    return fmt_dur((now() - datetime.fromisoformat(iso)).total_seconds()) + " ago"


@cmd("start", "help")
def c_help(a):
    reply(HELP, markup=KEYBOARD)


@cmd("test")
def c_test(a):
    reply(f"✅ Bot is working · {local_short(now())} IST")


@cmd("status")
def c_status(a):
    try:
        st = json.load(open(STATE))
    except Exception:
        st = {}
    out = ["📡 <b>Live status</b>" + ("  ⏸ <b>PAUSED</b>" if CFG["paused"] else "")]
    for site in CFG["sites"]:
        s = st.get(site)
        if not s or "last_check" not in s:
            out += ["", f"⚪ <b>{H.escape(R.short(site))}</b>\n    no data yet"]
        elif s["status"] == "down":
            dur = (now() - datetime.fromisoformat(s["down_since"])).total_seconds()
            out += ["", f"🔴 <b>{H.escape(R.short(site))}</b>",
                    f"    DOWN for <b>{fmt_dur(dur)}</b> · since {local_short(datetime.fromisoformat(s['down_since']))}",
                    f"    <i>{H.escape(s.get('reason', '')[:90])}</i> · checked {ago(s['last_check'])}"]
        else:
            out += ["", f"🟢 <b>{H.escape(R.short(site))}</b>",
                    f"    UP · HTTP {s['last_code']} · {s['last_ms']} ms · checked {ago(s['last_check'])}"]
    out += ["", f"⚙️ Every {fmt_dur(CFG['normal_interval_seconds'])} · "
                f"{fmt_dur(CFG['down_recheck_seconds'])} when down"]
    reply("\n".join(out))


@cmd("check")
def c_check(a):
    import monitor
    out = ["🔎 <b>Checked just now</b>"]
    for site in CFG["sites"]:
        ok, code, ms, err = monitor.check(site)
        out.append(f"{'🟢' if ok else '🔴'} {H.escape(R.short(site))} · "
                   + (f"HTTP {code} · {ms} ms" if ok else H.escape(err or f"HTTP {code}")))
    reply("\n".join(out))


@cmd("report")
def c_report(a):
    reply(R.render_html(R.compute(parse_hours(a))))


@cmd("pdf")
def c_pdf(a):
    d = R.compute(parse_hours(a))
    try:
        path = R.write_pdf(d)
    except ImportError:
        return reply("PDF needs the <code>fpdf2</code> package on the server. See the setup guide, step 'Part 2'.")
    send_document(path, f"Uptime report · last {R.label(d['hours'])}")


@cmd("csv")
def c_csv(a):
    hrs = parse_hours(a)
    p1, p2 = R.export_csv(hrs)
    send_document(p1, f"All checks · last {R.label(hrs)}")
    send_document(p2, f"Outages · last {R.label(hrs)}")


def set_duration(key, a, lo, hi, name, example):
    sec = parse_dur(a, "m")
    if not a.strip():
        return reply(f"{name} is currently <b>{fmt_dur(CFG[key])}</b>.\nChange it like: <code>{example}</code>")
    if sec is None or not lo <= sec <= hi:
        return reply(f"⚠️ Use a value between {fmt_dur(lo)} and {fmt_dur(hi)}, e.g. <code>{example}</code>")
    save_setting(key, sec)
    reply(f"✅ {name} is now <b>{fmt_dur(sec)}</b>" + gh_note())


@cmd("interval")
def c_interval(a):
    set_duration("normal_interval_seconds", a, 30, 86400, "Normal check interval", "/interval 2m")


@cmd("downinterval")
def c_downinterval(a):
    set_duration("down_recheck_seconds", a, 15, 3600, "Recheck interval while down", "/downinterval 30s")


@cmd("timeout")
def c_timeout(a):
    set_duration("timeout_seconds", (a.strip() + "s") if a.strip().isdigit() else a, 5, 120,
                 "Request timeout", "/timeout 20")


@cmd("reminder")
def c_reminder(a):
    if not a.strip():
        return reply(f"Reminder is every <b>{CFG['still_down_reminder_minutes']} min</b>. Change: <code>/reminder 15</code>")
    if not a.strip().isdigit() or not 5 <= int(a) <= 1440:
        return reply("⚠️ Use minutes between 5 and 1440, e.g. <code>/reminder 15</code>")
    save_setting("still_down_reminder_minutes", int(a))
    reply(f"✅ 'Still down' reminder every <b>{int(a)} min</b>")


@cmd("reporttime")
def c_reporttime(a):
    if not a.strip().isdigit() or not 0 <= int(a) <= 23:
        return reply(f"Daily report is at <b>{CFG['daily_report_hour']}:00 IST</b>. Change: <code>/reporttime 8</code> (0-23)")
    save_setting("daily_report_hour", int(a))
    reply(f"✅ Daily report will be sent at <b>{int(a)}:00 IST</b>")


@cmd("sites")
def c_sites(a):
    reply("🌐 <b>Monitored sites</b>\n" + "\n".join(f"• {H.escape(s)}" for s in CFG["sites"]))


@cmd("add")
def c_add(a):
    url = a.strip()
    if not re.fullmatch(r"https?://[^\s/]+\S*", url):
        return reply("⚠️ Send the full address, e.g. <code>/add https://example.com</code>")
    if url in CFG["sites"]:
        return reply("Already monitored.")
    save_setting("sites", CFG["sites"] + [url])
    reply(f"✅ Added <b>{H.escape(url)}</b>. Now monitoring {len(CFG['sites'])} sites.")


@cmd("remove")
def c_remove(a):
    q = a.strip().lower()
    hits = [s for s in CFG["sites"] if q and (q == s.lower() or q == R.short(s).lower())]
    if not hits:
        hits = [s for s in CFG["sites"] if q and q in s.lower()]
    if len(hits) != 1:
        return reply("⚠️ Say which site, e.g. <code>/remove example.com</code>. " + ("No match." if not hits else "Matches several."))
    save_setting("sites", [s for s in CFG["sites"] if s != hits[0]])
    reply(f"✅ Removed <b>{H.escape(hits[0])}</b>. Now monitoring {len(CFG['sites'])} sites.")


@cmd("pause")
def c_pause(a):
    save_setting("paused", True)
    reply("⏸ <b>Paused.</b> No checks or alerts until /resume.")


@cmd("resume")
def c_resume(a):
    save_setting("paused", False)
    reply("▶️ <b>Resumed.</b> Checking now.")


@cmd("settings")
def c_settings(a):
    reply("⚙️ <b>Settings</b>\n"
          f"• Normal interval: <b>{fmt_dur(CFG['normal_interval_seconds'])}</b>  (/interval)\n"
          f"• While down: <b>{fmt_dur(CFG['down_recheck_seconds'])}</b>  (/downinterval)\n"
          f"• Timeout: <b>{CFG['timeout_seconds']}s</b>  (/timeout)\n"
          f"• Still-down reminder: <b>{CFG['still_down_reminder_minutes']} min</b>  (/reminder)\n"
          f"• Daily report: <b>{CFG['daily_report_hour']}:00 IST</b>  (/reporttime)\n"
          f"• Alerts: <b>{'PAUSED' if CFG['paused'] else 'on'}</b>  (/pause /resume)\n"
          f"• Sites: <b>{len(CFG['sites'])}</b>  (/sites)")


def handle_message(m):
    if str(m["chat"]["id"]) != str(os.environ.get("TELEGRAM_CHAT_ID")):
        return
    text = (m.get("text") or "").strip()
    if not text.startswith("/"):
        return
    parts = text.split(None, 1)
    name = parts[0][1:].split("@")[0].lower()
    fn = COMMANDS.get(name)
    if not fn:
        return reply("Unknown command. Send /help")
    try:
        fn(parts[1] if len(parts) > 1 else "")
    except Exception as e:
        reply(f"⚠️ {H.escape(str(e))}")


def handle_updates(timeout=0):
    """Fetch and process pending messages. Returns False if Telegram could not be reached."""
    try:
        off = json.load(open(OFFSET))["offset"]
    except Exception:
        off = 0
    r = tg_api("getUpdates", {"offset": off, "timeout": timeout,
                              "allowed_updates": json.dumps(["message"])}, timeout=timeout + 15)
    if not r or not r.get("ok"):
        return False
    for u in r["result"]:
        off = u["update_id"] + 1
        if "message" in u:
            handle_message(u["message"])
    os.makedirs(DATA, exist_ok=True)
    json.dump({"offset": off}, open(OFFSET, "w"))
    return True


def setup():
    tg_api("setMyCommands", {"commands": json.dumps([
        {"command": "status", "description": "Live status of all sites"},
        {"command": "report", "description": "Report (e.g. /report 24h)"},
        {"command": "pdf", "description": "PDF report"},
        {"command": "csv", "description": "CSV logs"},
        {"command": "check", "description": "Check sites now"},
        {"command": "interval", "description": "Change check interval"},
        {"command": "downinterval", "description": "Recheck speed when down"},
        {"command": "sites", "description": "List sites"},
        {"command": "pause", "description": "Pause alerts"},
        {"command": "resume", "description": "Resume alerts"},
        {"command": "settings", "description": "Show settings"},
        {"command": "help", "description": "All commands"}])})
