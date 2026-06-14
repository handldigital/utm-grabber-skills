"""
Native PDF generator.

Takes a summary dict (same schema the HTML template uses) and produces a PDF
via WeasyPrint. Charts are pre-rendered as SVG using matplotlib — no JavaScript
required at conversion time, so the output is fully deterministic.

Usage:
    from build_pdf import build_pdf_from_summary
    build_pdf_from_summary(summary_dict, '/mnt/user-data/outputs/report.pdf')
"""
import html
import os
import sys
from datetime import datetime

from chart_renderer import render_chart


# ---- HTML generation (Python-side, no JS) ----

def _esc(s):
    if s is None:
        return ''
    return html.escape(str(s), quote=True)


def _render_title(s):
    """Convert *word* fragments to <em> tags, escape rest."""
    if not s:
        return ''
    out = []
    in_italic = False
    current = []
    for ch in str(s):
        if ch == '*':
            if in_italic:
                out.append(f'<em>{html.escape("".join(current))}</em>')
            else:
                out.append(html.escape("".join(current)))
            current = []
            in_italic = not in_italic
        else:
            current.append(ch)
    # flush
    if in_italic:
        # Unclosed asterisk — just append the rest as plain
        out.append('*' + html.escape("".join(current)))
    else:
        out.append(html.escape("".join(current)))
    return ''.join(out)


def _render_title_block(s):
    kicker = f'<div class="kicker">{_esc(s["kicker"])}</div>' if s.get('kicker') else ''
    meta = ''
    if s.get('meta_bits'):
        meta = '<div class="meta-line">' + ''.join(f'<span>{_esc(m)}</span>' for m in s['meta_bits']) + '</div>'
    return f'<div class="title-block">{kicker}<h1>{_render_title(s.get("title",""))}</h1>{meta}</div>'


def _render_stat_strip(s):
    stats = s.get('stats', [])
    cards = []
    for st in stats:
        delta = ''
        if st.get('delta_label'):
            dir_ = st.get('delta_direction', 'flat')
            label = '' if dir_ == 'flat' else _esc(st["delta_label"])
            delta = f'<span class="stat-delta {dir_}">{label}</span>'
        cards.append(f'''<div class="stat-card">
  <div class="stat-value">{_esc(st.get("value",""))}</div>
  <div class="stat-label"><span>{_esc(st.get("label",""))}</span>{delta}</div>
</div>''')
    return f'<div class="stat-strip cols-{len(stats)}">{"".join(cards)}</div>'


def _render_hero_number(s):
    kicker = f'<div class="hero-kicker">{_esc(s["kicker"])}</div>' if s.get('kicker') else ''
    label = ''
    if s.get('label'):
        label = f'<div class="hero-bottom"><div class="hero-label">{_esc(s["label"])}</div></div>'
    return f'''<div class="hero-number">
  <div class="hero-top">
    {kicker}
    <div class="hero-value">{_esc(s.get("value",""))}</div>
  </div>
  {label}
</div>'''


def _render_section_header(s):
    num = f'<span class="section-number">{_esc(s.get("number",""))}</span>' if s.get('number') else ''
    kicker = f'<span class="section-kicker">{_esc(s.get("kicker",""))}</span>' if s.get('kicker') else ''
    return f'<div class="section-header">{num}{kicker}<h2>{_render_title(s.get("title",""))}</h2></div>'


def _render_chart_block(s, colors):
    svg = render_chart(s.get('chart', {}), colors) or ''
    caption = f'<div class="chart-caption">{_esc(s["caption"])}</div>' if s.get('caption') else ''
    return f'<div class="chart-block"><div class="chart-wrap">{svg}</div>{caption}</div>'


def _render_chart_insight(s, colors):
    svg = render_chart(s.get('chart', {}), colors) or ''
    caption = f'<div class="chart-caption">{_esc(s["caption"])}</div>' if s.get('caption') else ''
    ik = f'<div class="insight-kicker">{_esc(s["insight_kicker"])}</div>' if s.get('insight_kicker') else ''
    it = f'<h3>{_render_title(s["insight_title"])}</h3>' if s.get('insight_title') else ''
    ib = ''
    if s.get('insight_body'):
        ib = '<div class="insight-body">' + ''.join(f'<p>{_esc(p)}</p>' for p in s['insight_body']) + '</div>'
    return f'''<div class="chart-block with-insight">
  <div><div class="chart-wrap">{svg}</div>{caption}</div>
  <div class="insight-card"><div class="insight-top">{ik}{it}</div>{ib}</div>
</div>'''


def _render_ranked_list(s):
    cols = s.get('columns', [])
    header = ''.join(
        f'<th class="{"align-right" if c.get("align") == "right" else "align-center" if c.get("align") == "center" else ""}" '
        f'style="{"width:" + c["width"] + ";" if c.get("width") else ""}">{_esc(c.get("label",""))}</th>'
        for c in cols
    )
    rows_html = []
    for row in s.get('rows', []):
        cells = []
        for c in cols:
            v = row.get(c['key'])
            align_cls = ' align-right' if c.get('align') == 'right' else ' align-center' if c.get('align') == 'center' else ''
            cls = f'col-{c.get("type", "name")}{align_cls}'
            if c.get('type') == 'trend' and isinstance(v, dict):
                cells.append(f'<td class="{cls}"><span class="trend-pill {_esc(v.get("state", "steady"))}">{_esc(v.get("label", ""))}</span></td>')
            else:
                cells.append(f'<td class="{cls}">{_esc(v) if v is not None else ""}</td>')
        rows_html.append(f'<tr>{"".join(cells)}</tr>')
    return f'<div class="ranked-list"><table><thead><tr>{header}</tr></thead><tbody>{"".join(rows_html)}</tbody></table></div>'


def _render_recommendations(s):
    cards = []
    for i, r in enumerate(s.get('items', [])):
        label = r.get('label', f'Action {str(i+1).zfill(2)}')
        cards.append(f'''<div class="rec-card">
  <div class="rec-top">
    <div class="rec-number">{_esc(label)}</div>
    <h3>{_render_title(r.get("title",""))}</h3>
  </div>
  <div class="rec-body"><p>{_esc(r.get("body",""))}</p></div>
</div>''')
    return f'<div class="recommendations-grid">{"".join(cards)}</div>'


def _render_insight_card(s):
    kicker = f'<div class="insight-kicker">{_esc(s["kicker"])}</div>' if s.get('kicker') else ''
    title = f'<h3>{_render_title(s["title"])}</h3>' if s.get('title') else ''
    body = ''
    if s.get('body'):
        body = '<div class="insight-body">' + ''.join(f'<p>{_esc(p)}</p>' for p in s['body']) + '</div>'
    return f'<div class="standalone-insight"><div class="insight-top">{kicker}{title}</div>{body}</div>'


def _render_closing(s):
    body = f'<p class="closing-body">{_esc(s["body"])}</p>' if s.get('body') else ''
    return f'<div class="closing"><h2>{_render_title(s.get("title","Thank *you* for reading."))}</h2>{body}</div>'


def _render_section(s, colors):
    t = s.get('type')
    fn = {
        'title-block': _render_title_block,
        'stat-strip': _render_stat_strip,
        'hero-number': _render_hero_number,
        'section-header': _render_section_header,
        'recommendations': _render_recommendations,
        'insight-card': _render_insight_card,
        'closing': _render_closing,
        'ranked-list': _render_ranked_list,
    }.get(t)
    if fn:
        return fn(s)
    if t == 'chart':
        return _render_chart_block(s, colors)
    if t == 'chart-insight':
        return _render_chart_insight(s, colors)
    return ''


# ---- Top-level HTML shell for PDF ----
# This is a JS-free version of report-shell.html. Same design tokens, same
# two-tone language. Charts are inline SVG (not canvas). Brand colors are
# substituted server-side rather than via runtime JS.

_PRINT_CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pdf_styles.css')


def _load_pdf_css():
    css_parts = []
    # Prefer bundled fonts via @font-face (no network needed)
    font_dirs = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'fonts'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'fonts'),
        '/home/claude/fonts',
    ]
    font_dir = next((d for d in font_dirs if os.path.isdir(d)), None)
    if font_dir:
        fd = os.path.abspath(font_dir)
        css_parts.append(f'''
@font-face {{ font-family: "Instrument Serif"; font-style: normal; font-weight: 400;
  src: url("file://{fd}/InstrumentSerif-Regular.ttf") format("truetype"); }}
@font-face {{ font-family: "Instrument Serif"; font-style: italic; font-weight: 400;
  src: url("file://{fd}/InstrumentSerif-Italic.ttf") format("truetype"); }}
@font-face {{ font-family: "Geist"; font-style: normal; font-weight: 400;
  src: url("file://{fd}/Geist-Regular.ttf") format("truetype"); }}
@font-face {{ font-family: "Geist"; font-style: normal; font-weight: 500;
  src: url("file://{fd}/Geist-Medium.ttf") format("truetype"); }}
@font-face {{ font-family: "Geist Mono"; font-style: normal; font-weight: 400;
  src: url("file://{fd}/GeistMono-Regular.ttf") format("truetype"); }}
''')

    if os.path.exists(_PRINT_CSS_PATH):
        with open(_PRINT_CSS_PATH) as f:
            main_css = f.read()
        # Strip the @import line if fonts are bundled — avoids network dependency
        if font_dir:
            main_css = '\n'.join(l for l in main_css.split('\n') if not l.strip().startswith('@import'))
        css_parts.append(main_css)

    return '\n'.join(css_parts)


def build_pdf_html(summary):
    """
    Build a JS-free HTML string suitable for WeasyPrint.
    Returns the complete HTML document as a string.
    """
    meta = summary.get('meta', {})
    brand = meta.get('brand_profile', {}) or {}
    colors = brand.get('colors', {}) or {}
    theme = (brand.get('theme') or 'light').lower()

    # Compute gradient end color if gradient theme
    def _mix_hex(a, b, t):
        def h2r(h):
            s = (h or '#000000').lstrip('#')
            return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        r1, g1, b1 = h2r(a); r2, g2, b2 = h2r(b)
        return '#{:02X}{:02X}{:02X}'.format(
            int(r1 * (1-t) + r2 * t), int(g1 * (1-t) + g2 * t), int(b1 * (1-t) + b2 * t))
    grad_end = _mix_hex(colors.get('ink', '#0B1B34'),
                        colors.get('primary', '#0160BF'), 0.35)

    # Brand CSS variables
    brand_css = f''':root {{
      --b-primary: {colors.get("primary", "#0160BF")};
      --b-accent:  {colors.get("accent",  "#2E90FA")};
      --b-ink:     {colors.get("ink",     "#0B1B34")};
      --b-muted:   {colors.get("muted",   "#64748B")};
      --b-surface: {colors.get("surface", "#F5F7FB")};
      --b-grad-end: {grad_end};
    }}'''

    # Logo
    logo = brand.get('logo', {})
    if logo.get('type') == 'url':
        logo_html = f'<img src="{_esc(logo["value"])}" alt="{_esc(brand.get("company_name",""))}">'
    elif logo.get('type') == 'upload':
        logo_html = f'<img src="data:image/png;base64,{_esc(logo["value"])}" alt="{_esc(brand.get("company_name",""))}">'
    elif logo.get('type') == 'text':
        logo_html = logo['value']  # trusted HTML
    else:
        logo_html = _esc(brand.get('company_name') or meta.get('customer_name', ''))

    tag_html = ''  # Removed "× UTM Grabber" — just company name in logo slot

    # Footer
    domain = meta.get('customer_domain', '')
    footer_source = f'Data source: UTM Grabber · {_esc(domain)}'
    ver = meta.get('skill_version', '0.8.2')
    gen_date = ''
    if meta.get('generated_at'):
        try:
            dt = datetime.fromisoformat(meta['generated_at'].replace('Z', '+00:00'))
            gen_date = dt.strftime('%b %-d, %Y')
        except Exception:
            pass
    footer_version = f'Prepared by UTM Grabber · v{ver}{" · " + gen_date if gen_date else ""}'

    # Render all sections
    sections_html = ''.join(_render_section(s, colors) for s in summary.get('sections', []))

    css = _load_pdf_css()

    # PDF is light-only — PPTX and HTML support gradient; PDF stays editorial.
    body_class = ''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Attribution Report</title>
<style>
{css}
{brand_css}
</style>
</head>
<body class="{body_class}">
<div class="report">
  <div class="report-header">
    <div class="brand-logo">{logo_html}</div>
  </div>
  <div id="sections-root">{sections_html}</div>
  <div class="report-footer">
    <span>{footer_source}</span>
    <span>{footer_version}</span>
  </div>
</div>
</body>
</html>'''


def build_pdf_from_summary(summary, output_path, validate=False):
    """Convert a summary dict to a PDF file. Returns the output path.

    Recipes in `report_recipes.py` are schema-valid by construction, so validation
    is off by default. Pass `validate=True` when building a summary by hand or
    debugging an unfamiliar source."""
    if validate:
        try:
            from validate_schema import validate_summary
            errors = validate_summary(summary)
            if errors:
                print(f"Warning: {len(errors)} schema issue(s) — proceeding anyway:")
                for e in errors[:5]:
                    print(f"  • {e}")
        except ImportError:
            pass  # Validator not available, proceed

    from weasyprint import HTML
    html_str = build_pdf_html(summary)
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    HTML(string=html_str).write_pdf(output_path)
    return output_path


def build_html_for_pdf(summary, output_path):
    """Save the JS-free HTML that would go to the PDF (useful for debugging)."""
    html_str = build_pdf_html(summary)
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(html_str)
    return output_path


if __name__ == '__main__':
    import json
    if len(sys.argv) != 3:
        print("Usage: python build_pdf.py <summary.json> <output.pdf>")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        summary = json.load(f)
    path = build_pdf_from_summary(summary, sys.argv[2])
    print(f"✓ Wrote PDF: {path}")
