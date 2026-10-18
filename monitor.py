"""Website uptime monitor.
  python monitor.py           one run (GitHub Actions): check, and stay while anything is down
  python monitor.py --daemon  run forever with the Telegram command bot (VPS / Oracle)
  python monitor.py --test    send a test Telegram message and exit
"""
import csv, http, http.client, json, os, socket, ssl, sys, threading, time, urllib.request, urllib.error
from common import *

META = os.path.join(DATA, "meta.json")


def describe(e):
    """Readable failure name, close to what a browser would show (e.g. ERR_SSL_PROTOCOL_ERROR)."""
    r = e.reason if isinstance(e, urllib.error.URLError) else e
    if isinstance(r, (socket.timeout, TimeoutError)) or "timed out" in str(r):
        return f"TIMEOUT: no response in {CFG['timeout_seconds']}s"
    if isinstance(r, ssl.SSLCertVerificationError):
        return f"SSL_CERT_ERROR: {r.verify_message}"
    if isinstance(r, ssl.SSLError):
        return f"SSL_PROTOCOL_ERROR: {r.reason or r}"
    if isinstance(r, ConnectionRefusedError):
        return "CONNECTION_REFUSED: server refused the connection"
    if isinstance(r, ConnectionResetError):
        return "CONNECTION_RESET: server dropped the connection"
    if isinstance(r, socket.gaierror):
        return "DNS_FAILURE: domain did not resolve"
    if isinstance(r, (http.client.RemoteDisconnected, http.client.BadStatusLine, http.client.IncompleteRead)):
        return "EMPTY_RESPONSE: server closed the connection without replying"
    return f"{type(r).__name__}: {r}"[:150]


def check(url):
    t0 = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "UptimeCheck/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=CFG["timeout_seconds"]) as r:
            code, err = r.status, ""
    except urllib.error.HTTPError as e:
        try:
            phrase = http.HTTPStatus(e.code).phrase
        except ValueError:
            phrase = ""
        code, err = e.code, f"HTTP {e.code} {phrase}".strip()
    except Exception as e:
        code, err = 0, describe(e)
    ms = int((time.time() - t0) * 1000)
    return (200 <= code < 400), code, ms, err


def append(path, header, row):
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(header)
        w.writerow(row)


def log_check(site, ok, code, ms, err):
    path = os.path.join(DATA, f"checks-{now():%Y-%m}.csv")
    append(path, ["time_utc", "site", "up", "http_code", "response_ms", "error"],
           [now().isoformat(timespec="seconds"), site, int(ok), code, ms, err])


def load_json(path):
    try:
        return json.load(open(path))
    except Exception:
        return {}


def save_json(path, obj):
    os.makedirs(DATA, exist_ok=True)
    json.dump(obj, open(path, "w"), indent=1)


def cycle(st):
    reload_cfg()
    if CFG["paused"]:
        return False
    for site in CFG["sites"]:
        s = st.setdefault(site, {"status": "up"})
        ok, code, ms, err = check(site)
        first_fail = now()
        if not ok and s["status"] == "up":  # confirm before alerting
            for _ in range(CFG["confirm_retries"]):
                time.sleep(CFG["confirm_delay_seconds"])
                ok, code, ms, err = check(site)
                if ok:
                    break
        log_check(site, ok, code, ms, err)

        if not ok and s["status"] == "up":
            s.update(status="down", down_since=first_fail.isoformat(),
                     reason=err or f"HTTP {code}", last_alert=now().isoformat())
            telegram(f"🔴 DOWN: {site}\nSince: {local(first_fail)}\nReason: {s['reason']}")
        elif not ok:
            last = datetime.fromisoformat(s["last_alert"])
            if (now() - last).total_seconds() >= CFG["still_down_reminder_minutes"] * 60:
                dur = (now() - datetime.fromisoformat(s["down_since"])).total_seconds()
                s["last_alert"] = now().isoformat()
                telegram(f"🔴 STILL DOWN: {site}\nDown for {fmt_dur(dur)}\nReason: {err or code}")
        elif ok and s["status"] == "down":
            start = datetime.fromisoformat(s["down_since"])
            dur = (now() - start).total_seconds()
            append(INCIDENTS, ["site", "down_since_utc", "up_at_utc", "duration_sec", "reason"],
                   [site, s["down_since"], now().isoformat(timespec="seconds"), int(dur), s["reason"]])
            telegram(f"🟢 RECOVERED: {site}\nDown: {local(start)}\nUp: {local(now())}\n"
                     f"Total downtime: {fmt_dur(dur)}")
            st[site] = s = {"status": "up"}
        s.update(last_check=now().isoformat(), last_code=code, last_ms=ms, last_err=err)
        print(f"{now():%H:%M:%S} {site} {'UP' if ok else 'DOWN'} {code} {ms}ms {err}", flush=True)
    save_json(STATE, st)
    return any(st[s]["status"] == "down" for s in CFG["sites"])


def maybe_daily_report():
    t = now().astimezone(LOCAL)
    meta = load_json(META)
    today = t.strftime("%Y-%m-%d")
    if "last_report" not in meta:  # first start: begin tomorrow
        meta["last_report"] = today
        save_json(META, meta)
    elif t.hour >= CFG["daily_report_hour"] and meta["last_report"] != today:
        meta["last_report"] = today
        save_json(META, meta)
        import report
        report.send_report(24, pdf=True)


def bot_loop():
    import bot
    bot.setup()
    while True:
        try:
            ok = bot.handle_updates(30)
        except Exception as e:
            print("bot error:", e, flush=True)
            ok = False
        if not ok:
            time.sleep(5)


if __name__ == "__main__":
    os.makedirs(DATA, exist_ok=True)
    if "--test" in sys.argv:
        telegram(f"✅ Test message from uptime monitor\nTime: {local(now())}\n"
                 f"Watching: {', '.join(CFG['sites'])}")
        sys.exit()
    st = load_json(STATE)
    if "--daemon" in sys.argv:
        threading.Thread(target=bot_loop, daemon=True).start()
        while True:
            down = cycle(st)
            try:
                maybe_daily_report()
            except Exception as e:
                print("report error:", e, flush=True)
            WAKE.wait(CFG["down_recheck_seconds"] if down else CFG["normal_interval_seconds"])
            WAKE.clear()
    else:
        try:  # GitHub mode: answer any commands sent since the last run
            import bot
            bot.handle_updates(0)
        except Exception as e:
            print("bot error:", e)
        end = time.time() + CFG["max_job_minutes"] * 60
        while cycle(st) and time.time() < end:
            time.sleep(CFG["down_recheck_seconds"])
