"""
Dev tool: test the live dashboard page (engine/live.py + engine/js/live.js).

    python scripts/dev/test_live.py OUT_DIR

Builds the page in all four themes from the sample data, then drives it in
headless Chromium with a simulated claude.ai viewer (window.claude.use("mcp")):
  * snapshot: no viewer, viewer without the capability
  * live: the connection answers in the connector's text page format, over
    several pages, with field labels; also a structured payload
  * failures: not connected, needs reauth, a tool error (relayed), a retryable
    outage that recovers, a denial that stops unattended refreshes
Checks the numbers against the report engine's own channel rules, the calls the
page makes (dates, pages, the one-row prior count), layout on desktop and phone,
and console errors. Needs the Bash sandbox off (headless Chromium).
"""
import asyncio
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)

from demo_data_v2 import get_dataset  # noqa: E402
from engine.live import build_live  # noqa: E402
from helpers import classify_traffic_source  # noqa: E402

THEMES = ["studio", "boardroom", "ledger", "classic"]
END = dt.date(2026, 9, 30)

MOCK = r"""
window.__calls = [];
window.__serve = function (server, tool, input, opts) {
  var mode = window.__mode;
  window.__n = (window.__n || 0) + 1;
  if (mode === "not_connected") return Promise.reject({code: "server_not_connected", server: server, message: "x"});
  if (mode === "reauth") return Promise.reject({code: "needs_reauth", server: server, message: "x"});
  if (mode === "tool_error") return Promise.reject({code: "tool_error", server: server,
    message: "Your free plan covers the last 30 days of leads. Upgrade to UTM Grabber Premium for your full history: https://utmgrabber.com/pricing"});
  if (mode === "flaky" && window.__n === 1) return Promise.reject({code: "server_unavailable", retryable: true, retryAfterMs: 50, message: "x"});
  var cfg = JSON.parse(document.getElementById("live-config").textContent), snap = cfg.snapshot;
  function pd(s) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s); return new Date(+m[1], +m[2] - 1, +m[3]); }
  function ymd(d) { return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
  var t0 = new Date(), today = new Date(t0.getFullYear(), t0.getMonth(), t0.getDate());
  var shift = Math.round((today - pd(snap.to)) / 864e5);
  var rows = snap.entries.map(function (e) {
    var d = pd(e.d), n = new Date(d.getFullYear(), d.getMonth(), d.getDate() + shift);
    return {form_id: "1", date_created: ymd(n) + e.d.slice(10), "3": e.s, "4": e.m, "5": e.c, "6": e.ts, "7": e.g ? "Cj0" : "",
            "8": e.f ? "IwAR" : "", "9": e.k ? "ms1" : "", "10": e.rf ? "https://ref.example/" : "", source_url: "https://site.example" + e.u,
            "First Name": "Jane", "Work Email": "jane@example.com"};
  });
  var a = pd(input.selected_start_date), b = pd(input.selected_end_date);
  rows = rows.filter(function (r) { var d = pd(r.date_created); return d >= a && d <= b; });
  var per = input.per_page || 50, pages = Math.max(1, Math.ceil(rows.length / per)), page = input.page || 1;
  var labels = {"1": {"3": "utm_source (HandL)", "4": "utm_medium (HandL)", "5": "utm_campaign (HandL)", "6": "traffic_source (HandL)",
                      "7": "gclid (HandL)", "8": "fbclid (HandL)", "9": "msclkid (HandL)", "10": "referrer (first touch, HandL)"}};
  var slice = rows.slice((page - 1) * per, page * per);
  if (mode === "structured") {
    var obj = {entries: slice, field_labels: labels, total: rows.length, total_pages: pages};
    return Promise.resolve({content: [{type: "text", text: JSON.stringify(obj)}], structuredContent: obj, payload: obj});
  }
  var text = "Found " + rows.length + " entries for gravity-form forms [1] between " + input.selected_start_date + " and " +
    input.selected_end_date + ".\nPage " + page + " of " + pages + " (" + per + " per page, " + rows.length.toLocaleString("en-US") +
    " total matching entries).\nField labels (form_id -> field -> label): " + JSON.stringify(labels) + "\nEntries:\n" +
    JSON.stringify(slice, null, 1) + (page < pages ? "\nMore entries available. Call again with page=" + (page + 1) + " to fetch the next page." : "");
  return Promise.resolve({content: [{type: "text", text: text}], payload: text});
};
if (window.__mode !== "none") {
  window.claude = {use: function (name) {
    if (window.__mode === "null" || name !== "mcp") return Promise.resolve(null);
    return Promise.resolve({callTool: function (server, tool, input, opts) {
      window.__calls.push({server: server, tool: tool, input: input, opts: opts});
      return window.__serve(server, tool, input, opts);
    }});
  }};
}
"""

READ = r"""() => {
  const q = s => document.querySelector(s);
  const panel = t => [...document.querySelectorAll('.panel')].find(p => (p.querySelector('.p-title') || {}).textContent.includes(t));
  const bars = p => p ? [...p.querySelectorAll('.bl-row')].map(r => [r.querySelector('.bl-label').textContent,
      r.querySelector('.bl-val').childNodes[0].textContent]) : [];
  const vals = [...document.querySelectorAll('.d-kpis .kpi-value')].map(e => e.textContent);
  return {h1: q('.d-h1').textContent, dek: q('.d-dek').textContent, status: q('.lv-status').textContent,
          statusCls: q('.lv-status').className, msg: q('.lv-msg').hidden ? '' : q('.lv-msg').textContent, kpis: vals,
          channels: bars(panel('came from')), period: q('.d-period').textContent,
          overflow: document.documentElement.scrollWidth > innerWidth,
          clipped: [...document.querySelectorAll('.panel, .kpi')].filter(e => e.scrollWidth > e.clientWidth + 2).length,
          pressed: [...document.querySelectorAll('.lv-tab')].filter(b => b.getAttribute('aria-pressed') === 'true').map(b => b.dataset.win),
          personal: /jane@example\.com|Jane/.test(document.body.innerHTML),
          calls: window.__calls || []};
}"""


def expected(entries, days=7):
    start = END - dt.timedelta(days=days - 1)
    cur = [e for e in entries if start.isoformat() <= str(e.get("Date Created"))[:10] <= END.isoformat()]
    ch = {}
    for e in cur:
        c = classify_traffic_source(e)
        ch[c] = ch.get(c, 0) + 1
    return len(cur), ch


async def run(out):
    from playwright.async_api import async_playwright
    ds = get_dataset("northwind")
    snap = [e for e in ds["leads_history"] if str(e.get("Date Created", ""))[:10] >= (END - dt.timedelta(days=59)).isoformat()]
    exp_total, exp_ch = expected(snap)
    pages = {}
    for t in THEMES:
        for kind in ("live", "demo"):
            p = os.path.join(out, "%s-%s.html" % (kind, t))
            build_live(snap, p, connector="UTM Grabber", form_plugin="gravity-form" if kind == "live" else None,
                       form_ids=[1] if kind == "live" else None, theme=t, brand_profile=ds["brand"],
                       customer_domain=ds["domain"], form_label=ds["form_label"], demo=(kind == "demo"),
                       generated_at="2026-09-30T18:00:00")
            pages[(kind, t)] = p
    fails, results = [], []

    def check(name, cond, detail=""):
        results.append((name, bool(cond)))
        if not cond:
            fails.append("%s %s" % (name, detail))

    async with async_playwright() as pw:
        b = await pw.chromium.launch()

        async def open_page(path, mode, w=1440, h=900, wait=900):
            ctx = await b.new_context(viewport={"width": w, "height": h})
            await ctx.add_init_script("window.__mode = %s;" % json.dumps(mode) + MOCK)
            pg = await ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            await pg.goto("file://" + path)
            await pg.evaluate("document.fonts.ready")
            await pg.wait_for_timeout(wait)
            return ctx, pg, errs

        for t in THEMES:
            live = pages[("live", t)]
            # snapshot only: plain file, no viewer
            ctx, pg, errs = await open_page(live, "none")
            r = await pg.evaluate(READ)
            ch = {k: int(v.replace(",", "")) for k, v in r["channels"]}
            check("%s snapshot total" % t, r["kpis"][0].replace(",", "") == str(exp_total), r["kpis"][:1])
            check("%s snapshot channels" % t, ch == exp_ch, (ch, exp_ch))
            check("%s snapshot status" % t, "is-snap" in r["statusCls"] and "Numbers from Sep 30, 2026" in r["status"], r["status"])
            check("%s snapshot message" % t, "signed in" in r["msg"], r["msg"])
            check("%s no personal data" % t, not r["personal"])
            check("%s no errors (snapshot)" % t, not errs, errs[:2])
            await pg.screenshot(path=os.path.join(out, "shot-snapshot-%s.png" % t))
            await ctx.close()
            # viewer without the capability
            ctx, pg, errs = await open_page(live, "null")
            r = await pg.evaluate(READ)
            check("%s no-capability message" % t, "signed in" in r["msg"] and "is-snap" in r["statusCls"], r["msg"])
            await ctx.close()
            # live: text pages
            for mode in ("ok", "structured"):
                ctx, pg, errs = await open_page(live, mode)
                r = await pg.evaluate(READ)
                ch = {k: int(v.replace(",", "")) for k, v in r["channels"]}
                calls = r["calls"]
                first = [c for c in calls if c["input"].get("per_page") == 100 and c["input"].get("page") == 1]
                prior = [c for c in calls if c["input"].get("per_page") == 1]
                check("%s %s live status" % (t, mode), "is-live" in r["statusCls"] and "updated just now" in r["status"], r["status"])
                check("%s %s live total" % (t, mode), r["kpis"][0].replace(",", "") == str(exp_total), (r["kpis"][:1], exp_total))
                check("%s %s live channels" % (t, mode), ch == exp_ch, (ch, exp_ch))
                check("%s %s calls" % (t, mode), first and prior and all(c["tool"] == "get_entries" and c["server"] == "UTM Grabber" for c in calls)
                      and first[0]["input"]["selected_form_plugin"] == "gravity-form" and first[0]["input"]["selected_form_ids"] == [1],
                      [c["input"] for c in calls][:3])
                if first:
                    s0 = dt.date.fromisoformat(first[0]["input"]["selected_start_date"])
                    e0 = dt.date.fromisoformat(first[0]["input"]["selected_end_date"])
                    check("%s %s 7-day window" % (t, mode), (e0 - s0).days == 6 and e0 == dt.date.today(), (s0, e0))
                n_pages = len([c for c in calls if c["input"].get("per_page") == 100])
                check("%s %s paged" % (t, mode), n_pages >= 2, n_pages)
                check("%s %s no personal data" % (t, mode), not r["personal"])
                check("%s %s no errors" % (t, mode), not errs, errs[:2])
                if mode == "ok":
                    await pg.screenshot(path=os.path.join(out, "shot-live-%s.png" % t))
                    # window switch: 30 days, then today
                    await pg.click('.lv-tab[data-win="30"]')
                    await pg.wait_for_timeout(900)
                    r30 = await pg.evaluate(READ)
                    tot30, _ = expected(snap, 30)
                    check("%s 30-day live total" % t, r30["kpis"][0].replace(",", "") == str(tot30) and r30["pressed"] == ["30"],
                          (r30["kpis"][:1], tot30, r30["pressed"]))
                    await pg.click('.lv-tab[data-win="today"]')
                    await pg.wait_for_timeout(900)
                    rt = await pg.evaluate(READ)
                    check("%s today view" % t, rt["pressed"] == ["today"] and "today" in rt["h1"].lower(), rt["h1"])
                    # refresh bypasses the cache
                    await pg.click(".lv-refresh")
                    await pg.wait_for_timeout(900)
                    rr = await pg.evaluate(READ)
                    check("%s refresh" % t, any((c.get("opts") or {}).get("cache", {}).get("refresh") for c in rr["calls"]))
                await ctx.close()
            # failures
            for mode, needle in (("not_connected", "Add UTM Grabber in claude.ai Settings > Connectors"),
                                 ("reauth", "Reconnect UTM Grabber"),
                                 ("tool_error", "Your free plan covers the last 30 days")):
                ctx, pg, errs = await open_page(live, mode)
                r = await pg.evaluate(READ)
                check("%s %s message" % (t, mode), needle in r["msg"] and "is-snap" in r["statusCls"], (r["msg"], r["status"]))
                check("%s %s keeps the snapshot" % (t, mode), r["kpis"][0].replace(",", "") == str(exp_total))
                check("%s %s one call" % (t, mode), len(r["calls"]) <= 2, len(r["calls"]))
                await ctx.close()
            ctx, pg, errs = await open_page(live, "flaky", wait=1500)
            r = await pg.evaluate(READ)
            check("%s retry recovers" % t, "is-live" in r["statusCls"] and not r["msg"], (r["status"], r["msg"]))
            await ctx.close()
            # demo page: simulated connection, no capability needed
            ctx, pg, errs = await open_page(pages[("demo", t)], "none", wait=3000)
            r = await pg.evaluate(READ)
            check("%s demo live" % t, "live demo" in r["status"].lower() and "sample data" in (await pg.inner_text(".d-facts")).lower(), r["status"])
            check("%s demo no errors" % t, not errs, errs[:2])
            await ctx.close()
            # phone layout
            ctx, pg, errs = await open_page(live, "ok", 390, 844)
            r = await pg.evaluate(READ)
            check("%s phone layout" % t, not r["overflow"] and r["clipped"] == 0, (r["overflow"], r["clipped"]))
            await pg.screenshot(path=os.path.join(out, "shot-phone-%s.png" % t), full_page=True)
            await ctx.close()
            ctx, pg, errs = await open_page(live, "ok")
            r = await pg.evaluate(READ)
            check("%s desktop layout" % t, not r["overflow"] and r["clipped"] == 0, (r["overflow"], r["clipped"]))
            await ctx.close()
        await b.close()
    ok = sum(1 for _, v in results if v)
    print("%d/%d checks passed" % (ok, len(results)))
    for f in fails:
        print("FAIL", f)
    return not fails


if __name__ == "__main__":
    out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "live-test")
    os.makedirs(out, exist_ok=True)
    sys.exit(0 if asyncio.run(run(out)) else 1)
