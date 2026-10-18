"""Uptime reports.  python report.py [hours] [--send]"""
import csv, glob, html, json, os, socket, sys
from urllib.parse import urlparse
from datetime import datetime, timedelta
from common import *

REPORTS = os.path.join(ROOT, "reports")


def P(s):
    return datetime.fromisoformat(s)


def short(site):
    return site.split("://", 1)[-1].rstrip("/")


def etype(err):
    """'CONNECTION_REFUSED: server refused...' -> 'CONNECTION_REFUSED'; HTTP errors keep their text."""
    err = (err or "").strip()
    return err if err.startswith("HTTP") else (err.split(":")[0].strip() or "UNKNOWN")


def compute(hours=24):
    end = now()
    start = end - timedelta(hours=hours)
    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, "checks-*.csv"))):
        rows += [r for r in read_csv(f) if P(r["time_utc"]) >= start]
    first = min((P(r["time_utc"]) for r in rows), default=end)
    window = max(60, (end - max(start, first)).total_seconds())
    incidents = read_csv(INCIDENTS)
    try:
        state = json.load(open(STATE))
    except Exception:
        state = {}

    sites = []
    for site in CFG["sites"]:
        mine = [r for r in rows if r["site"] == site]
        inc = []
        for i in incidents:
            if i["site"] != site:
                continue
            a, b = max(P(i["down_since_utc"]), start), min(P(i["up_at_utc"]), end)
            if b > a:
                inc.append((a, b, i["reason"], False))
        s = state.get(site, {})
        if s.get("status") == "down":
            inc.append((max(P(s["down_since"]), start), end, s.get("reason", ""), True))
        down = sum((b - a).total_seconds() for a, b, _, _ in inc)
        ms = sorted(int(r["response_ms"]) for r in mine if r["up"] == "1")
        fails = [r for r in mine if r["up"] == "0"]
        errs = {}
        for r in fails:
            errs[etype(r["error"])] = errs.get(etype(r["error"]), 0) + 1
        sites.append(dict(site=site, outages=inc, down=down, fails=fails,
                          errors=dict(sorted(errs.items(), key=lambda kv: -kv[1])),
                          p95=ms[max(0, int(len(ms) * 0.95) - 1)] if ms else 0,
                          pct=max(0.0, 100 * (1 - down / window)), checks=len(mine),
                          failed=sum(r["up"] == "0" for r in mine),
                          avg=sum(ms) // len(ms) if ms else 0, max=max(ms) if ms else 0))
    return dict(start=start, end=end, hours=hours, window=window, sites=sites, rows=rows)


def label(hours):
    return f"{int(hours // 24)}d" if hours >= 48 and hours % 24 == 0 else f"{hours:g}h"


def bar(pct, n=20):
    return "▓" * int(pct / 100 * n) + "░" * (n - int(pct / 100 * n))


def render_html(d):
    e = html.escape
    out = [f"📊 <b>Uptime report · last {label(d['hours'])}</b>",
           f"🕒 {local_short(d['start'])} → {local_short(d['end'])} IST"]
    if d["window"] < (d["end"] - d["start"]).total_seconds() - 120:
        out.append(f"<i>Monitoring data covers only {fmt_dur(d['window'])}</i>")
    for s in d["sites"]:
        icon = "🔴" if any(o[3] for o in s["outages"]) else ("🟡" if s["outages"] else "🟢")
        out += ["", f"{icon} <b>{e(short(s['site']))}</b>",
                f"<code>{bar(s['pct'])}</code> <b>{s['pct']:.3f}%</b>",
                f"Downtime <b>{fmt_dur(s['down'])}</b> · Outages <b>{len(s['outages'])}</b>",
                f"Checks {s['checks']} · Failed {s['failed']} · Avg {s['avg']} ms · Max {s['max']} ms"]
        if s["errors"]:
            out.append("Errors: " + " · ".join(f"{n}× {e(k)}" for k, n in list(s["errors"].items())[:5]))
        for a, b, why, ongoing in s["outages"][-12:]:
            end_txt = "<b>still down</b>" if ongoing else local_short(b)
            out.append(f"  🔻 {local_short(a)} → {end_txt} ({fmt_dur((b - a).total_seconds())})"
                       + (f"\n      <i>{e(why[:80])}</i>" if why else ""))
        if len(s["outages"]) > 12:
            out.append(f"  … and {len(s['outages']) - 12} earlier outages (use /pdf for all)")
    return "\n".join(out)


def render_text(d):
    out = [f"UPTIME REPORT (last {label(d['hours'])})",
           f"Period: {local(d['start'])}  to  {local(d['end'])}", ""]
    for s in d["sites"]:
        out += [f"== {s['site']}",
                f"Uptime: {s['pct']:.3f}%   Total downtime: {fmt_dur(s['down'])}   "
                f"Outages: {len(s['outages'])}",
                f"Checks: {s['checks']}   Failed: {s['failed']}   Avg response: {s['avg']} ms"]
        for a, b, why, ongoing in s["outages"]:
            out.append(f"  - DOWN {local(a)} -> {'STILL DOWN' if ongoing else local(b)}"
                       f"  ({fmt_dur((b - a).total_seconds())})  [{why}]")
        out.append("")
    return "\n".join(out)


def export_csv(hours=24):
    """Returns (checks_csv_path, outages_csv_path)."""
    d = compute(hours)
    os.makedirs(REPORTS, exist_ok=True)
    stamp = f"{now().astimezone(LOCAL):%Y%m%d-%H%M}"
    p1 = os.path.join(REPORTS, f"checks-last{label(hours)}-{stamp}.csv")
    p2 = os.path.join(REPORTS, f"outages-last{label(hours)}-{stamp}.csv")
    with open(p1, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time_ist", "site", "up", "http_code", "response_ms", "error"])
        for r in d["rows"]:
            w.writerow([local(P(r["time_utc"])), r["site"], r["up"], r["http_code"],
                        r["response_ms"], r["error"]])
    with open(p2, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["site", "down_since_ist", "up_at_ist", "duration", "duration_sec", "reason", "ongoing"])
        for s in d["sites"]:
            for a, b, why, ongoing in s["outages"]:
                sec = (b - a).total_seconds()
                w.writerow([s["site"], local(a), "" if ongoing else local(b), fmt_dur(sec), int(sec), why,
                            "yes" if ongoing else "no"])
    return p1, p2


def write_pdf(d):
    from fpdf import FPDF  # pip install fpdf2

    def L(s):
        return str(s).encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.set_auto_page_break(True, 15)
    pdf.add_page()

    def line(txt, size=10, bold=False, h=5.5, font="Helvetica"):
        pdf.set_font(font, "B" if bold else "", size)
        pdf.multi_cell(0, h, L(txt), new_x="LMARGIN", new_y="NEXT")

    total_fail = sum(s["failed"] for s in d["sites"])
    line("Website Availability Evidence Report", 18, True, 10)
    line(f"Period: {local(d['start'])}  to  {local(d['end'])}   (all times IST, UTC+5:30)")
    line(f"Monitoring data available for: {fmt_dur(d['window'])}")
    pdf.ln(2)
    line("Method", 12, True, 7)
    line(f"Checks run from an independent monitor on Oracle Cloud (not on the hosting provider's network). "
         f"Every {fmt_dur(CFG['normal_interval_seconds'])} an HTTPS GET request is sent to each URL with a "
         f"{CFG['timeout_seconds']}s timeout; HTTP 200-399 counts as UP. A failed check is retried "
         f"{CFG['confirm_retries']} times, {CFG['confirm_delay_seconds']}s apart. If all retries fail the site is "
         f"declared DOWN and rechecked every {fmt_dur(CFG['down_recheck_seconds'])} until it answers; "
         f"the downtime is measured from the first failure to the first success. "
         f"Short failures that recover during the retries are still listed below as failed checks.", 9, False, 5)

    for s in d["sites"]:
        host = urlparse(s["site"]).hostname
        try:
            ip = ", ".join(sorted({a[4][0] for a in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}))
        except Exception:
            ip = "could not resolve"
        pdf.ln(4)
        line(s["site"], 14, True, 8)
        line(f"Server address (DNS now): {ip}", 9)
        line(f"Availability: {s['pct']:.3f}%     Confirmed downtime: {fmt_dur(s['down'])}     "
             f"Confirmed outages: {len(s['outages'])}", 10, True)
        rate = 100 * s["failed"] / s["checks"] if s["checks"] else 0
        line(f"Checks: {s['checks']}     Failed checks: {s['failed']} ({rate:.1f}%)     "
             f"Response time: avg {s['avg']} ms, 95th pct {s['p95']} ms, max {s['max']} ms")
        if s["errors"]:
            pdf.ln(1)
            line("Failure types:", 10, True)
            for k, n in s["errors"].items():
                line(f"   {n:>4} x  {k}", 10, False, 5, "Courier")
        if s["outages"]:
            pdf.ln(1)
            line("Confirmed outages:", 10, True)
            for a, b, why, ongoing in s["outages"]:
                line(f"   {local(a)}  ->  {'STILL DOWN' if ongoing else local(b)}   "
                     f"({fmt_dur((b - a).total_seconds())})", 9, True)
                if why:
                    line(f"        first error: {why}", 9)
        if s["fails"]:
            hrs = {}
            for r in s["fails"]:
                h = P(r["time_utc"]).astimezone(LOCAL).hour
                hrs[h] = hrs.get(h, 0) + 1
            top = max(hrs.values())
            pdf.ln(1)
            line("Failed checks by hour of day (IST):", 10, True)
            for h in sorted(hrs):
                line(f"   {h:02d}:00  {'#' * max(1, round(20 * hrs[h] / top))} {hrs[h]}", 9, False, 4.5, "Courier")
            pdf.ln(1)
            line("Every failed check:", 10, True)
            for r in s["fails"][-400:]:
                line(f"   {local(P(r['time_utc']))}   {r['response_ms']:>5} ms   {r['error'] or 'HTTP ' + r['http_code']}",
                     8, False, 4.2, "Courier")
            if len(s["fails"]) > 400:
                line(f"   ... {len(s['fails']) - 400} earlier failures not shown (see the CSV export)", 8)
    pdf.ln(4)
    line(f"Total failed checks across all sites: {total_fail}. Raw data: CSV export of every check.", 9)
    os.makedirs(REPORTS, exist_ok=True)
    path = os.path.join(REPORTS, f"evidence-last{label(d['hours'])}-{now().astimezone(LOCAL):%Y%m%d-%H%M}.pdf")
    pdf.output(path)
    return path


def send_report(hours=24, pdf=False):
    d = compute(hours)
    os.makedirs(REPORTS, exist_ok=True)
    open(os.path.join(REPORTS, f"report-{now().astimezone(LOCAL):%Y-%m-%d}.txt"), "w",
         encoding="utf-8").write(render_text(d))
    telegram(render_html(d), html=True)
    if pdf:
        try:
            send_document(write_pdf(d), "Report PDF (share with hosting provider)")
        except ImportError:
            pass


if __name__ == "__main__":
    nums = [a for a in sys.argv[1:] if not a.startswith("--")]
    hrs = float(nums[0]) if nums else 24
    if "--send" in sys.argv:
        send_report(hrs, pdf=True)
    else:
        print(render_text(compute(hrs)))
