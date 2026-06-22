"""
Native PDF generator (v1.1+) — print the real HTML report via headless Chromium.

Earlier versions rebuilt a *separate* JS-free HTML document and pre-rendered every
chart to SVG with matplotlib, purely because WeasyPrint can't execute the template's
Chart.js. Chromium runs JS, so we now print `templates/report-shell.html` directly:
one rendering path, charts identical to the on-screen report, ~500 fewer lines.

Offline by design (matching the old path's guarantee): Chart.js and the brand fonts
are bundled and inlined / referenced via file:// at render time, so PDF generation
never depends on a CDN being reachable.

PDF is always light theme — gradient is a PPTX-only feature — so we force light
before rendering, regardless of what the brand profile asks for.

Usage:
    from build_pdf import build_pdf_from_summary
    build_pdf_from_summary(summary_dict, '/mnt/user-data/outputs/report.pdf')
"""
import json
import os
import re
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_TEMPLATE = os.path.normpath(os.path.join(_HERE, '..', 'templates', 'report-shell.html'))
_FONT_DIR = os.path.normpath(os.path.join(_HERE, '..', 'assets', 'fonts'))
_CHART_JS = os.path.normpath(os.path.join(_HERE, '..', 'assets', 'chart.umd.min.js'))


def _font_face_css():
    """Inline @font-face block pointing at the bundled TTFs via absolute file:// URLs."""
    def url(name):
        return 'file://' + os.path.join(_FONT_DIR, name)
    faces = [
        ('Instrument Serif', 'normal', 400, 'InstrumentSerif-Regular.ttf'),
        ('Instrument Serif', 'italic', 400, 'InstrumentSerif-Italic.ttf'),
        ('Geist', 'normal', 400, 'Geist-Regular.ttf'),
        ('Geist', 'normal', 500, 'Geist-Medium.ttf'),
        ('Geist Mono', 'normal', 400, 'GeistMono-Regular.ttf'),
    ]
    rules = '\n'.join(
        f'@font-face{{font-family:"{fam}";font-style:{style};font-weight:{wt};'
        f'src:url("{url(fn)}") format("truetype");}}'
        for fam, style, wt, fn in faces
    )
    return f'<style id="pdf-fonts">\n{rules}\n</style>'


def _render_report_html(summary):
    """Inject summary into the template and swap CDN deps for bundled, offline ones.

    - Forces brand theme to light (PDF never renders gradient).
    - Replaces the Google Fonts <link> with an inline @font-face block (bundled TTFs).
    - Replaces the Chart.js CDN <script> with the bundled copy, animation disabled
      so canvases paint deterministically for a static print.
    """
    summary = json.loads(json.dumps(summary))  # deep copy — don't mutate caller's dict
    brand = summary.setdefault('meta', {}).setdefault('brand_profile', {})
    if isinstance(brand, dict):
        brand['theme'] = 'light'

    with open(_TEMPLATE) as f:
        html = f.read()

    payload = json.dumps(summary, ensure_ascii=False)
    html = re.sub(
        r'<script id="report-data" type="application/json">.*?</script>',
        lambda _m: '<script id="report-data" type="application/json">\n' + payload + '\n</script>',
        html, count=1, flags=re.DOTALL,
    )

    # Swap Google Fonts stylesheet link → inline bundled @font-face
    html = re.sub(
        r'<link[^>]*fonts\.googleapis\.com[^>]*>',
        lambda _m: _font_face_css(),
        html, count=1,
    )

    # Swap Chart.js CDN script → bundled inline copy + animation off
    with open(_CHART_JS) as f:
        chart_js = f.read()
    inline_chart = (
        '<script>' + chart_js + '</script>\n'
        '<script>if(window.Chart){Chart.defaults.animation=false;'
        'Chart.defaults.animations=false;}</script>'
    )
    html = re.sub(
        r'<script[^>]*src="[^"]*[Cc]hart[^"]*"[^>]*></script>',
        lambda _m: inline_chart,
        html, count=1,
    )
    return html


def build_pdf_from_summary(summary, output_path, validate=False):
    """Render a summary dict to a PDF via headless Chromium. Returns output_path.

    validate=True runs schema validation first. Off by default — recipes are
    schema-valid by construction; pass True when hand-building a summary."""
    if validate:
        try:
            from validate_schema import validate_summary
            errors = validate_summary(summary)
            if errors:
                print(f"Warning: {len(errors)} schema issue(s) — proceeding anyway:")
                for e in errors[:5]:
                    print(f"  • {e}")
        except ImportError:
            pass

    from playwright.sync_api import sync_playwright

    html = _render_report_html(summary)
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    # Render from a temp .html FILE (not set_content) so the file:// font URLs are
    # allowed to load — Chromium blocks file:// access from an about:blank origin.
    tmp = tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8')
    try:
        tmp.write(html)
        tmp.close()
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto('file://' + tmp.name, wait_until='load')
            page.wait_for_timeout(500)  # let Chart.js paint canvases post-load
            page.pdf(
                path=output_path,
                print_background=True,
                prefer_css_page_size=True,  # honor the template's @page (letter + margins)
            )
            browser.close()
    finally:
        os.unlink(tmp.name)
    return output_path


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        print("Usage: python build_pdf.py <summary.json> <output.pdf>")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        summary = json.load(f)
    path = build_pdf_from_summary(summary, sys.argv[2])
    print(f"✓ Wrote PDF: {path}")
