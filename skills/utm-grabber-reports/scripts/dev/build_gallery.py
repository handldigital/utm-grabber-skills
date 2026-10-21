"""
Dev tool: build the sample gallery (every report in every look) for review.

    python scripts/dev/build_gallery.py OUT_DIR [--reports a,b] [--full-formats | --html-only] [--live-url URL]

Writes:
  OUT_DIR/index.html                   the gallery (theme tabs, a card per report)
  OUT_DIR/gallery.html                 the same page without the document skeleton or the
                                       PowerPoint links, to publish as a claude.ai Artifact
                                       (downloads capability; Artifacts can't serve .pptx)
  OUT_DIR/html/{report}-{theme}.html   every report in every theme
  OUT_DIR/pdf/, OUT_DIR/pptx/          PDF + PowerPoint for every report in Studio,
                                       and for the flagships in all four themes
                                       (--full-formats: every report, every theme)
  OUT_DIR/thumbs/{report}-{theme}.jpg  card thumbnails
Needs the Bash sandbox off (headless Chromium).
"""
import asyncio
import base64
import html as _html
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)

from demo_v2 import REPORTS, TITLES, demo_summary  # noqa: E402
from build_report import build_report  # noqa: E402
from engine.fonts import font_face_css  # noqa: E402
from engine.themes import THEME_INFO  # noqa: E402

THEMES = ["studio", "boardroom", "ledger", "classic"]
FLAGSHIPS = ["monthly", "full-funnel", "true-roas", "qbr"]

GROUPS = [
    ("Core performance", ["monthly", "weekly", "daily-pulse", "qbr", "leaderboard", "campaign-deep-dive",
                          "paid-vs-organic", "anomaly", "forecast", "side-by-side", "agency-rollup"]),
    ("Leads, forms and tracking", ["audit", "lead-scorer", "lead-profile", "form-performance", "landing-page",
                                   "source-to-crm", "lead-timing"]),
    ("Paid media, revenue and journeys", ["ad-creative", "keyword", "budget-simulator", "revenue", "ai-referrals",
                                          "journey"]),
    ("Leads joined with ads, analytics and CRM",
     ["full-funnel", "true-roas", "conversion-truth", "traffic-to-lead", "pipeline", "wasted-spend"]),
]

NEW = {"daily-pulse", "qbr", "lead-timing", "revenue", "ai-referrals", "journey", "full-funnel", "true-roas",
       "conversion-truth", "traffic-to-lead", "pipeline", "wasted-spend"}


BACK = ('<a class="g-back" href="../index.html" onclick="if(history.length>1){history.back();return false}">'
        '&larr; All reports</a><style>.g-back{position:fixed;left:16px;bottom:calc(16px + env(safe-area-inset-bottom,0px));'
        'z-index:99;font:600 13px/1 system-ui,-apple-system,sans-serif;color:#0b1b34;background:rgba(255,255,255,.95);'
        'border:1px solid rgba(11,27,52,.16);border-radius:999px;padding:10px 14px;text-decoration:none;'
        'box-shadow:0 4px 14px rgba(0,0,0,.18)}.g-back:focus-visible{outline:2px solid #0160bf;outline-offset:2px}'
        '@media print{.g-back{display:none}}</style>')


def add_back_link(path):
    """Gallery copies only: a fixed button back to the gallery (reports open in place, not in a new tab)."""
    with open(path, encoding="utf-8") as f:
        doc = f.read()
    if 'class="g-back"' in doc:
        return
    i = doc.find(">", doc.find("<body")) + 1
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc[:i] + BACK + doc[i:])


async def _thumbs(paths, out_dir):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1280, "height": 860}, device_scale_factor=1)
        pg = await ctx.new_page()
        for src, dst in paths:
            await pg.goto("file://" + os.path.abspath(src))
            await pg.add_style_tag(content=".g-back{display:none!important}")
            await pg.evaluate("document.fonts.ready")
            await pg.wait_for_timeout(120)
            await pg.screenshot(path=dst + ".png")
            try:
                from PIL import Image
                im = Image.open(dst + ".png").convert("RGB")
                im = im.resize((640, 430))
                im.save(dst, quality=82)
                os.unlink(dst + ".png")
            except Exception:
                pass
        await b.close()


def main():
    out = os.path.abspath(sys.argv[1])
    only = None
    for i, a in enumerate(sys.argv):
        if a == "--reports" and i + 1 < len(sys.argv):
            only = sys.argv[i + 1].split(",")
    full = "--full-formats" in sys.argv
    live_url = None
    for i, a in enumerate(sys.argv):
        if a == "--live-url" and i + 1 < len(sys.argv):
            live_url = sys.argv[i + 1]
    html_only = "--html-only" in sys.argv   # rebuild web pages + thumbnails, keep existing PDF/PPTX files
    for d in ("html", "pdf", "pptx", "thumbs"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    from recipes_v2 import RECIPES
    reports = [r for r in REPORTS if r in RECIPES and (not only or r in only)]
    built, shots, failed = {}, [], []
    for r in reports:
        for t in THEMES:
            try:
                s = demo_summary(r, t)
                m = s.setdefault("meta", {})
                m["sources"] = (m.get("sources") or []) + [{"name": "Sample data", "detail": "fictional business"}]
                paths = [os.path.join(out, "html", "%s-%s.html" % (r, t))]
                files = [os.path.join(out, "pdf", "%s-%s.pdf" % (r, t)), os.path.join(out, "pptx", "%s-%s.pptx" % (r, t))]
                if html_only:
                    build_report(s, paths, theme=t, validate=False)
                    paths += [f for f in files if os.path.exists(f)]
                else:
                    if full or t == "studio" or r in FLAGSHIPS:
                        paths += files
                    build_report(s, paths, theme=t, validate=False)
                add_back_link(paths[0])
                built[(r, t)] = paths
                shots.append((paths[0], os.path.join(out, "thumbs", "%s-%s.jpg" % (r, t))))
                print("built", r, t)
            except Exception as exc:
                failed.append((r, t, str(exc)))
                print("FAILED", r, t, exc)
    asyncio.run(_thumbs(shots, out))
    _index(out, reports, built, live_url)
    print("gallery:", os.path.join(out, "index.html"), "| failed:", failed)


def _index(out, reports, built, live_url=None):
    """Writes index.html (a full page, for opening from the folder) and gallery.html (the same page
    without the document skeleton, for publishing as a claude.ai Artifact with the downloads capability)."""
    def rel(p):
        return os.path.relpath(p, out)

    css_fonts = font_face_css(["rubik-500", "rubik-700", "work-sans-400", "work-sans-500", "work-sans-600"])
    tabs = "".join('<button type="button" class="tab" id="tab-%s" data-t="%s" aria-pressed="%s"><b>%s</b><span>%s</span></button>' % (
        t, t, "true" if t == "studio" else "false", THEME_INFO[t]["name"], _html.escape(THEME_INFO[t]["best_for"])) for t in THEMES)
    groups = []
    for gname, keys in GROUPS:
        cards = []
        for r in keys:
            if r not in reports:
                continue
            per_theme = []
            for t in THEMES:
                paths = built.get((r, t))
                if not paths:
                    continue
                links = ['<a href="%s">Web page</a>' % rel(paths[0])]
                for p in paths[1:]:
                    kind = "PDF" if p.endswith(".pdf") else "PowerPoint"
                    links.append('<a class="dl" href="%s" data-dl="%s">%s</a>' % (rel(p), os.path.basename(p), kind))
                per_theme.append('<div class="v%s" data-t="%s"><a class="shot" href="%s" '
                                 'aria-label="Open %s in %s"><img loading="lazy" src="thumbs/%s-%s.jpg" alt=""></a>'
                                 '<h3>%s%s</h3><p class="links">%s</p></div>' % (
                    " on" if t == "studio" else "", t, rel(paths[0]), _html.escape(TITLES.get(r, r)), THEME_INFO[t]["name"],
                    r, t, _html.escape(TITLES.get(r, r)), ' <em class="new">New</em>' if r in NEW else "", "".join(links)))
            if per_theme:
                cards.append('<article class="card">%s</article>' % "".join(per_theme))
        if cards:
            groups.append('<section class="group"><h2>%s</h2><div class="grid">%s</div></section>' % (
                _html.escape(gname), "".join(cards)))
    if live_url and os.path.exists(os.path.join(out, "thumbs", "live-demo.jpg")):
        groups.insert(0, '<section class="group"><h2>Live dashboard</h2><div class="grid"><article class="card"><div class="v on" '
                      'data-t="all"><a class="shot" href="%s" target="_blank" rel="noopener" aria-label="Open the live dashboard demo">'
                      '<img loading="lazy" src="thumbs/live-demo.jpg" alt=""></a><h3>Live leads dashboard <em class="new">New</em></h3>'
                      '<p class="links"><a href="%s" target="_blank" rel="noopener">Open the live demo</a></p><p class="card-note">Pulls fresh '
                      'numbers from your UTM Grabber connection every time it opens. The demo simulates that with sample data.</p>'
                      '</div></article></div></section>' % (_html.escape(live_url), _html.escape(live_url)))
    n_new = len([r for r in reports if r in NEW])
    title = "<title>UTM Grabber Reports</title>"
    style = """<style>%s
/* Layout: a brand band with the look switcher, then report cards grouped by job. */
:root{--bg:#ffffff;--ink:#0b1b34;--ink2:#4a5568;--line:#e2e6ee;--card:#ffffff;--soft:#eef4fc;--brand:#0160bf;
  --band:#0160bf;--on-band:#ffffff;--tab:rgba(255,255,255,.14);--tab-on:#ffffff;--on-tab:#0b1b34;--new:#e6f0fb;--focus:#0160bf;
  --f-display:"Rubik",system-ui,sans-serif;--f-body:"Work Sans",system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0d131c;--ink:#e9eef6;--ink2:#a4afc0;--line:#243041;
  --card:#131b27;--soft:#172234;--brand:#6fb0f5;--band:#0b2a4f;--on-band:#ffffff;--tab:rgba(255,255,255,.1);--tab-on:#e9eef6;
  --on-tab:#0b1b34;--new:#16304f;--focus:#6fb0f5;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0d131c;--ink:#e9eef6;--ink2:#a4afc0;--line:#243041;--card:#131b27;--soft:#172234;--brand:#6fb0f5;
  --band:#0b2a4f;--on-band:#ffffff;--tab:rgba(255,255,255,.1);--tab-on:#e9eef6;--on-tab:#0b1b34;--new:#16304f;--focus:#6fb0f5;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;font-family:var(--f-body);color:var(--ink);background:var(--bg);-webkit-font-smoothing:antialiased}
.band{background:var(--band);color:var(--on-band);padding-inline:16px}
.wrap{max-width:1240px;margin-inline:auto}
.band .wrap{padding-block:56px 40px}
h1{font-family:var(--f-display);font-weight:500;font-size:clamp(32px,5vw,50px);letter-spacing:-.03em;line-height:1.05;margin:0;max-width:19ch;text-wrap:balance}
.lede{font-size:18px;line-height:1.55;margin:16px 0 0;max-width:62ch;opacity:.9}
.fine{font-size:14px;margin:10px 0 0;opacity:.75}
.tabs{display:flex;gap:10px;flex-wrap:wrap;margin-top:30px}
.tab{all:unset;cursor:pointer;padding:12px 18px;border-radius:14px;background:var(--tab);display:flex;flex-direction:column;gap:3px;min-width:170px}
.tab b{font-family:var(--f-display);font-weight:500;font-size:17px}
.tab span{font-size:12.5px;opacity:.8}
.tab[aria-pressed="true"]{background:var(--tab-on);color:var(--on-tab)}
.tab:focus-visible{outline:2px solid var(--on-band);outline-offset:3px}
main{padding-inline:16px}
main .wrap{padding-block:44px 72px;display:flex;flex-direction:column;gap:56px}
h2{font-family:var(--f-display);font-weight:500;font-size:24px;letter-spacing:-.02em;margin:0 0 18px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(272px,1fr));gap:22px}
.card{border:1px solid var(--line);border-radius:16px;overflow:hidden;background:var(--card);min-width:0}
.v{display:none;padding-bottom:16px}
.v.on{display:block}
.shot{display:block;border-bottom:1px solid var(--line)}
.shot img{display:block;width:100%%;max-width:100%%;aspect-ratio:640/430;object-fit:cover;object-position:top}
.card h3{font-family:var(--f-display);font-weight:500;font-size:16px;line-height:1.3;margin:0;padding:14px 16px 0}
.new{font-style:normal;font-size:11px;font-weight:600;color:var(--brand);background:var(--new);padding:2px 8px;border-radius:999px;margin-left:6px;vertical-align:2px;white-space:nowrap}
.links{display:flex;flex-wrap:wrap;gap:6px 14px;margin:0;padding:10px 16px 0;font-size:13.5px}
.links a{color:var(--brand);text-decoration:none;font-weight:500}
.links a:hover{text-decoration:underline}
a:focus-visible{outline:2px solid var(--focus);outline-offset:2px;border-radius:4px}
.links .busy{opacity:.55;pointer-events:none}
.card-note{font-size:13px;line-height:1.5;color:var(--ink2);padding:8px 16px 0;margin:0}
footer{padding-inline:16px;color:var(--ink2);font-size:13.5px;line-height:1.5}
footer .wrap{padding-block:0 48px}
@media (max-width:640px){.band .wrap{padding-block:32px 28px}.lede{font-size:16.5px}.tab{min-width:0;flex:1 1 40%%}main .wrap{padding-block:28px 56px;gap:40px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>""" % css_fonts
    content = """<header class="band"><div class="wrap"><h1>Hand every client a report that looks designer-made.</h1>
<p class="lede">All %d UTM Grabber reports in four looks. Open any of them as a web page, a PDF or an editable PowerPoint deck. %d are new, and six of those join your leads with ad, analytics and CRM data.</p>
<p class="fine">Every number here is sample data for two fictional businesses.</p>
<div class="tabs" role="group" aria-label="Report look">%s</div></div></header>
<main><div class="wrap">%s</div></main>
<footer><div class="wrap">Built with UTM Grabber Reports v2.0. Sample businesses: Northwind Dental (form leads, Google and Meta Ads, Google Analytics, HubSpot) and Harbor Linen Co. (a WooCommerce store).</div></footer>""" % (
        len(reports), n_new, tabs, "".join(groups))
    script = """<script>(function(){
function show(t){document.querySelectorAll('.tab').forEach(function(b){b.setAttribute('aria-pressed',b.dataset.t===t?'true':'false')});
document.querySelectorAll('.v').forEach(function(v){if(v.dataset.t!=='all')v.classList.toggle('on',v.dataset.t===t)});
try{localStorage.setItem('utmg-gallery-look',t)}catch(e){}}
document.querySelectorAll('.tab').forEach(function(b){b.addEventListener('click',function(){show(b.dataset.t)})});
var s='studio';try{s=localStorage.getItem('utmg-gallery-look')||'studio'}catch(e){}
if(!document.querySelector('.tab[data-t="'+s+'"]'))s='studio';show(s);
/* Inside the claude.ai viewer, files are saved through the downloads capability; opened from a folder,
   the PDF and PowerPoint links work as plain links. */
var framed=false;try{framed=window.self!==window.top}catch(e){framed=true}
function hideFileLinks(){document.querySelectorAll('a.dl').forEach(function(a){a.hidden=true})}
var dlp=(window.claude&&typeof window.claude.use==='function')?window.claude.use('downloads'):Promise.resolve(null);
dlp.then(function(d){if(!d&&framed)hideFileLinks()},function(){if(framed)hideFileLinks()});
document.addEventListener('click',function(ev){
  var a=ev.target.closest&&ev.target.closest('a.dl');if(!a||!framed)return;ev.preventDefault();
  a.classList.add('busy');
  dlp.then(function(d){if(!d){hideFileLinks();return}
    return fetch(a.getAttribute('href')).then(function(r){if(!r.ok)throw new Error('fetch');return r.blob()})
      .then(function(b){return d.save({filename:a.dataset.dl,data:b})})})
    .catch(function(e){if(e&&(e.code==='unavailable'||e.code==='not_granted'))hideFileLinks()})
    .then(function(){a.classList.remove('busy')});
});
})();</script>"""
    full = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">%s%s</head>'
            '<body>%s%s</body></html>' % (title, style, content, script))
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(full)
    # Artifacts can't serve .pptx files, so the published copy drops those links and says where the decks are.
    import re
    shared = re.sub(r'<a class="dl" href="pptx/[^"]+" data-dl="[^"]+">PowerPoint</a>', "", content)
    shared = shared.replace('<p class="fine">Every number here is sample data for two fictional businesses.</p>',
                            '<p class="fine">Every number here is sample data for two fictional businesses. The editable '
                            'PowerPoint version of each report sits in the pptx folder next to this gallery in Google Drive.</p>')
    with open(os.path.join(out, "gallery.html"), "w", encoding="utf-8") as f:
        f.write(title + style + shared + script)


if __name__ == "__main__":
    main()
