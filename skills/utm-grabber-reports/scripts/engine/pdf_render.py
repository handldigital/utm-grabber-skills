"""
Summary dict -> PDF, printed by headless Chromium from the print layout.

Every theme prints full-bleed (dark pages stay dark to the edge) with a running
footer: report name on the left, "Page X of Y" on the right, none on the cover
page. Letter by default; pass paper="a4" (or set meta.paper) for A4.

Vector all the way down: charts are inline SVG, fonts are embedded subsets, so
text stays selectable and charts stay sharp at any zoom.
"""
import os
import re
import tempfile

from . import fmt
from .html_render import render_html
from .themes import pick_theme, resolve_theme

PAPER = {"letter": ("8.5in", "11in"), "a4": ("210mm", "297mm")}


class PdfUnavailable(RuntimeError):
    """Headless Chromium could not start here, so no PDF was made.

    Typical cause: an app sandbox (Codex on macOS refuses Chromium with
    "bootstrap_check_in ... Permission denied (1100)"), or Playwright/Chromium
    missing. Don't make a PDF any other way: tell the user, and offer the web page
    (which they can save as a PDF from their browser's print menu) or the
    PowerPoint deck, or a retry once they let the step run outside the sandbox.
    """


def _page_css(theme, title, paper, modern=True):
    tk = theme["tokens"]
    w, h = PAPER.get(paper, PAPER["letter"])
    label_font = theme["fonts"]["label"]["css"]
    title = fmt.strip_accent(fmt.clean_text(title or ""))
    if len(title) > 72:
        title = title[:70].rstrip() + "…"
    title = title.replace("\\", "").replace('"', "'")
    color = tk["ink3"]
    if not modern:
        return "@page{size:%s %s;margin:0.55in 0.6in 0.7in}" % (w, h)
    return ('@page{size:%s %s;margin:0.55in 0.6in 0.72in;background:%s;'
            '@bottom-left{content:"%s";color:%s;font-family:%s;font-size:8.5pt;vertical-align:middle}'
            '@bottom-right{content:"Page " counter(page) " of " counter(pages);color:%s;font-family:%s;'
            'font-size:8.5pt;vertical-align:middle}}'
            '@page :first{@bottom-left{content:none}@bottom-right{content:none}}' %
            (w, h, tk["page"], title, color, label_font, color, label_font))


def render_print_html(summary, theme=None, paper=None, modern=True):
    key = pick_theme(theme, summary)
    meta = summary.get("meta", {}) or {}
    th = resolve_theme(key, meta.get("brand_profile"))
    paper = (paper or meta.get("paper") or "letter").lower()
    title_sec = next((s for s in summary.get("sections", []) if s.get("type") == "title-block"), {})
    report_name = (title_sec.get("kicker") or "").split("·")[0].strip() or \
        fmt.strip_accent(title_sec.get("title", ""))
    company = (meta.get("brand_profile") or {}).get("company_name") or meta.get("customer_name") or ""
    footer = "%s%s" % (report_name, (", " + company) if company and company not in report_name else "")
    html = render_html(summary, key, target="print")
    page_css = "<style>%s</style>" % _page_css(th, footer, paper, modern)
    return html.replace("</head>", page_css + "</head>", 1)


def build_pdf(summary, path, theme=None, paper=None):
    """Render the summary to a PDF at path. Returns path. Raises PdfUnavailable when
    Chromium can't start here."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise PdfUnavailable("PDF_UNAVAILABLE: Playwright isn't installed here (%s)." % e) from e

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:
            first = (str(e).strip().splitlines() or [type(e).__name__])[0][:300]
            raise PdfUnavailable("PDF_UNAVAILABLE: headless Chromium couldn't start here, usually because "
                                 "this app's sandbox blocks it (%s)." % first) from e
        try:
            major = int(re.match(r"(\d+)", browser.version).group(1))
        except Exception:
            major = 0
        modern = major >= 131   # @page backgrounds + margin boxes
        html = render_print_html(summary, theme, paper, modern)
        tmp = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
        try:
            tmp.write(html)
            tmp.close()
            page = browser.new_page()
            page.goto("file://" + tmp.name, wait_until="load")
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(150)
            kwargs = dict(path=path, print_background=True, prefer_css_page_size=True)
            if not modern:
                kwargs.update(display_header_footer=True, header_template="<div></div>",
                              footer_template='<div style="font-size:8px;width:100%;padding:0 0.6in;'
                                              'text-align:right;color:#888"><span class="pageNumber"></span> / '
                                              '<span class="totalPages"></span></div>')
            page.pdf(**kwargs)
        finally:
            browser.close()
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
    return path
