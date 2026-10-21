"""
Live dashboard: a claude.ai Artifact page that pulls fresh leads from the
viewer's own UTM Grabber connection each time it opens, and every 15 minutes
while it stays open. Without that connection it shows the snapshot saved here.

    from engine.live import build_live
    caps = build_live(entries, "/path/live-acme.com.artifact.html",
                      connector="UTM Grabber", form_plugin="gravity-form", form_ids=[1, 3],
                      window="7", theme="studio", brand_profile=brand,
                      customer_domain="acme.com", form_label="Gravity Forms")
    # publish the file with the Artifact tool, passing capabilities=caps

entries: normalized UTM Grabber entries (helpers.load_entries), ideally the last
60 days, so the 7 and 30 day views and their comparisons show before live data
arrives. Only dates and attribution fields go into the page: never names,
emails, phones or IP addresses.

connector: the UTM Grabber connector's display name in the viewer's claude.ai
account, exactly as listed. form_plugin / form_ids: what the page asks for,
the same values the report pulled. A path ending in .artifact.html gets the
skeleton-free page for the Artifact tool; any other path gets a full page for a
local preview (live data needs the claude.ai viewer).
"""
import datetime as _dt
import html as _html
import json
import os
from urllib.parse import urlparse

from . import fmt
from .fonts import font_face_css
from .html_render import _gen_date, _logo, R
from .themes import css_vars, pick_theme, resolve_theme

_HERE = os.path.dirname(os.path.abspath(__file__))
WINDOWS = (("today", "Today"), ("7", "7 days"), ("30", "30 days"), ("90", "90 days"))


def _read(*parts):
    with open(os.path.join(_HERE, *parts), encoding="utf-8") as f:
        return f.read()


def _field(e, *keys):
    for k in keys:
        v = e.get(k)
        if v not in (None, "") and str(v).strip():
            return str(v).strip()
    return ""


def slim_entries(entries):
    """Dates and attribution fields only, in the shape the page computes from."""
    out = []
    for e in entries or []:
        url = _field(e, "Source URL", "source_url")
        path = url
        if url:
            try:
                path = urlparse(url).path or "/"
            except ValueError:
                path = url
        d = _field(e, "Date Created", "date_created")
        if not d:
            continue
        out.append({"d": d, "s": _field(e, "utm_source (HandL)", "utm_source").lower(),
                    "m": _field(e, "utm_medium (HandL)", "utm_medium").lower(),
                    "c": _field(e, "utm_campaign (HandL)", "utm_campaign"),
                    "ts": _field(e, "traffic_source (HandL)", "traffic_source").lower(),
                    "g": 1 if _field(e, "gclid (HandL)", "gclid") else 0,
                    "f": 1 if _field(e, "fbclid (HandL)", "fbclid") else 0,
                    "k": 1 if _field(e, "msclkid (HandL)", "msclkid") else 0,
                    "rf": 1 if _field(e, "referrer (first touch, HandL)", "referrer") else 0,
                    "u": path, "fm": _field(e, "Form ID", "form_id")})
    out.sort(key=lambda x: x["d"])
    return out


def capabilities(connector="UTM Grabber"):
    """The runtime capability the published page declares: one connector, one read tool."""
    return {"mcp": {"servers": [{"server": connector, "tools": ["get_entries"]}]}}


def build_live(entries, path, connector="UTM Grabber", form_plugin=None, form_ids=None, window="7", theme=None,
               brand_profile=None, customer_name=None, customer_domain="", form_label=None, demo=False,
               generated_at=None, snapshot_from=None, snapshot_to=None):
    """Write the live dashboard page and return the capabilities to publish it with
    ({} for a demo, which simulates the connection and calls nothing)."""
    summary = {"meta": {"brand_profile": brand_profile, "customer_name": customer_name,
                        "customer_domain": customer_domain, "generated_at": generated_at}}
    key = pick_theme(theme, summary)
    th = resolve_theme(key, brand_profile)
    r = R(summary, th, "screen")
    snap = slim_entries(entries)
    days = sorted({x["d"][:10] for x in snap})
    s_from = snapshot_from or (days[0] if days else _dt.date.today().isoformat())
    s_to = snapshot_to or (days[-1] if days else _dt.date.today().isoformat())
    live = bool(not demo and form_plugin and form_ids)
    tk = th["tokens"]
    cfg = {
        "server": connector, "form_plugin": form_plugin, "form_ids": list(form_ids or []),
        "window": window if window in dict(WINDOWS) else "7", "live": live, "demo": bool(demo),
        "theme": {"key": key, "accent": th["style"]["accent"], "chartSize": th["style"].get("chart_size", 12.5),
                  "fonts": {"chart": th["fonts"].get("chart") or th["fonts"]["label"], "numeral": th["fonts"]["numeral"]},
                  "tokens": {k: tk[k] for k in ("panel", "grid", "axis", "chart_text", "ink", "ink2", "neutral",
                                                  "brand_ink", "series", "dark") if k in tk}},
        "snapshot": {"entries": snap, "from": s_from, "to": s_to,
                     "at": generated_at or _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")},
    }
    brand_name = (brand_profile or {}).get("company_name") or customer_name or ""
    name = ("%s live leads" % brand_name) if brand_name else "Live leads"
    facts = [b for b in (customer_domain, form_label) if b]
    if demo:
        facts.append("Sample data: a fictional business")
    tabs = "".join('<button type="button" class="lv-tab" data-win="%s" aria-pressed="false">%s</button>' % (k, lab)
                   for k, lab in WINDOWS)
    notes = ["Live numbers come from %s each time this page opens, and every 15 minutes while it stays open." % connector,
             "Without that connection (signed out, or %s not added to claude.ai) the page shows the numbers saved on %s."
             % (connector, _gen_date({"generated_at": cfg["snapshot"]["at"]})),
             "Leads count form submissions%s. Channels follow UTM Grabber's traffic source, then the tags: ad click IDs "
             "and paid mediums count as Paid." % ((" on " + form_label) if form_label else ""),
             "This page keeps only dates and tracking fields: no names, emails or other personal details."]
    if demo:
        notes.insert(0, "Sample data for a fictional business. Live updates are simulated.")
    body = (
        '<div class="rp dash lv" id="live-root" data-k="%s">'
        '<header class="d-top"><div class="d-id"><span class="d-logo">%s</span><span class="d-report">Live leads</span>'
        '<span class="d-period"></span></div><div class="lv-ctl"><div class="lv-tabs" role="group" aria-label="Time window">%s</div>'
        '<button type="button" class="lv-refresh">Refresh</button><span class="lv-status" role="status" aria-live="polite"></span></div></header>'
        '<section class="d-hero"><div class="d-hl"><h1 class="d-h1"></h1><p class="d-dek"></p>%s</div></section>'
        '<p class="lv-msg" hidden></p><main class="lv-body"></main>'
        '<details class="d-notes"><summary>How this page works</summary><ul>%s</ul></details>'
        '<footer class="rp-foot"><span>%s</span><span>Prepared with UTM Grabber, v%s</span></footer></div>' %
        (key, _logo(r), tabs, ('<p class="d-facts">%s</p>' % "".join("<span>%s</span>" % _html.escape(f) for f in facts)) if facts else "",
         "".join("<li>%s</li>" % _html.escape(fmt.clean_text(n)) for n in notes),
         _html.escape("Data: %s%s" % (connector if live or demo else "UTM Grabber", (" for " + customer_domain) if customer_domain else "")),
         _html.escape(_skill_version())))
    css = "\n".join([font_face_css(th["font_files"]), css_vars(th), _read("css", "base.css"), _read("css", "%s.css" % key),
                     _read("css", "dash.css"), _read("css", "%s.dash.css" % key), _read("css", "live.css"),
                     ":root{color-scheme:%s}" % ("dark" if tk.get("dark") else "light")])
    data = json.dumps(cfg, separators=(",", ":")).replace("</", "<\\/")
    script = '<script type="application/json" id="live-config">%s</script><script>%s</script>' % (data, _read("js", "live.js"))
    classes = ["t-screen", "is-dash"] + (["is-dark"] if tk.get("dark") else [])
    title = "<title>%s</title>" % _html.escape(name)
    if path.lower().endswith(".artifact.html"):
        page = ('%s<script>document.documentElement.classList.add(%s)</script><style>%s</style>%s%s' %
                (title, ",".join("'%s'" % c for c in classes), css, body, script))
    else:
        page = ('<!doctype html><html lang="en" class="%s"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">%s<style>%s</style></head>'
                '<body>%s%s</body></html>' % (" ".join(classes), title, css, body, script))
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    return capabilities(connector) if live else {}


def _skill_version():
    try:
        with open(os.path.join(_HERE, "..", "..", "VERSION.md")) as f:
            return f.read().strip()
    except OSError:
        return "2.0.0"


__all__ = ["build_live", "capabilities", "slim_entries"]
