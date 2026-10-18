"""Website uptime monitor.
  python monitor.py           one run (GitHub Actions): check, and stay while anything is down
  python monitor.py --daemon  run forever (VPS / Oracle)
"""
import csv, json, os, sys, time, urllib.request, urllib.error
from common import *

STATE = os.path.join(DATA, "state.json")
INCIDENTS = os.path.join(DATA, "incidents.csv")


def check(url):
    t0 = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "UptimeCheck/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=CFG["timeout_seconds"]) as r:
            code, err = r.status, ""
    except urllib.error.HTTPError as e:
        code, err = e.code, f"HTTP {e.code}"
    except Exception as e:
        code, err = 0, f"{type(e).__name__}: {e}"[:150]
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


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save_state(st):
    os.makedirs(DATA, exist_ok=True)
    json.dump(st, open(STATE, "w"), indent=1)


def cycle(st):
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
            st[site] = {"status": "up"}
        print(f"{now():%H:%M:%S} {site} {'UP' if ok else 'DOWN'} {code} {ms}ms {err}")
    save_state(st)
    return any(v["status"] == "down" for v in st.values())


if __name__ == "__main__":
    os.makedirs(DATA, exist_ok=True)
    st = load_state()
    if "--daemon" in sys.argv:
        while True:
            down = cycle(st)
            time.sleep(CFG["down_recheck_seconds"] if down else CFG["normal_interval_seconds"])
    else:
        end = time.time() + CFG["max_job_minutes"] * 60
        while cycle(st) and time.time() < end:
            time.sleep(CFG["down_recheck_seconds"])
