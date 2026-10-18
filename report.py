"""24h report. python report.py [--send]  -> reports/report-YYYY-MM-DD.txt (+ optional Telegram)"""
import glob, json, os, sys
from datetime import datetime, timedelta
from common import *

end = now()
start = end - timedelta(hours=24)


def P(s):
    return datetime.fromisoformat(s)


checks = []
for f in glob.glob(os.path.join(DATA, "checks-*.csv")):
    checks += [r for r in read_csv(f) if P(r["time_utc"]) >= start]
incidents = read_csv(os.path.join(DATA, "incidents.csv"))
try:
    state = json.load(open(os.path.join(DATA, "state.json")))
except Exception:
    state = {}

lines = ["UPTIME REPORT (last 24 hours)",
         f"Period: {local(start)}  to  {local(end)}", ""]
for site in CFG["sites"]:
    rows = [r for r in checks if r["site"] == site]
    inc = []
    for i in incidents:
        if i["site"] != site:
            continue
        a, b = max(P(i["down_since_utc"]), start), min(P(i["up_at_utc"]), end)
        if b > a:
            inc.append((a, b, i["reason"], False))
    s = state.get(site, {})
    if s.get("status") == "down":
        inc.append((max(P(s["down_since"]), start), end, s["reason"], True))
    down = sum((b - a).total_seconds() for a, b, _, _ in inc)
    pct = 100 * (1 - down / 86400)
    ms = [int(r["response_ms"]) for r in rows if r["up"] == "1"]
    lines += [f"== {site}",
              f"Uptime: {pct:.3f}%   Total downtime: {fmt_dur(down)}   Outages: {len(inc)}",
              f"Checks: {len(rows)}   Failed: {sum(r['up'] == '0' for r in rows)}   "
              f"Avg response: {sum(ms) // len(ms) if ms else 0} ms"]
    for a, b, why, ongoing in inc:
        lines.append(f"  - DOWN {local(a)} -> {'STILL DOWN' if ongoing else local(b)}"
                     f"  ({fmt_dur((b - a).total_seconds())})  [{why}]")
    lines.append("")

text = "\n".join(lines)
os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
path = os.path.join(ROOT, "reports", f"report-{end.astimezone(LOCAL):%Y-%m-%d}.txt")
open(path, "w", encoding="utf-8").write(text)
print(text)
if "--send" in sys.argv:
    telegram(text[:4000])
