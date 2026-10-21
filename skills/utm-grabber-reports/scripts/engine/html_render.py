"""
Summary dict -> self-contained HTML report, in any theme.

The output is one static file: fonts (base64 WOFF2), styles and SVG charts are all
inline, so it renders the same offline, in a browser, as an email attachment, or
printed to PDF. A few lines of optional JavaScript add hover tooltips; nothing
depends on them.

target="screen"  responsive page (desktop chart + phone chart variants)
target="print"   the layout the PDF builder prints (one chart variant sized to
                 the page, print typography)
"""
import datetime as _dt
import html as _html
import os
import re

from . import charts as CH
from . import fmt
from .fonts import font_face_css
from .themes import css_vars, pick_theme, resolve_theme

_CSS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "css")

PLATFORM_COLORS = {
    "utm grabber": "#0160BF", "utmg": "#0160BF", "google ads": "#1A73E8", "meta ads": "#0866FF",
    "facebook ads": "#0866FF", "google analytics": "#E8710A", "ga4": "#E8710A",
    "google analytics 4": "#E8710A", "hubspot": "#FF5C35", "salesforce": "#00A1E0",
    "pipedrive": "#1A1A1A", "woocommerce": "#7F54B3", "stripe": "#635BFF",
    "linkedin ads": "#0A66C2", "microsoft ads": "#00A4EF", "bing ads": "#00A4EF",
    "tiktok ads": "#111111", "search console": "#34A853", "google search console": "#34A853",
    "callrail": "#0A3B5C", "gohighlevel": "#2F6BFF", "zoho crm": "#E42527", "shopify": "#5E8E3E",
    "mailchimp": "#FFE01B", "klaviyo": "#111111", "activecampaign": "#356AE6",
}


def esc(s):
    return _html.escape(fmt.clean_text(s) if s is not None else "", quote=True)


def _read_css(name):
    p = os.path.join(_CSS_DIR, name)
    if not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8") as f:
        return f.read()


class R(object):
    """Render context."""

    def __init__(self, summary, theme, target):
        self.summary = summary
        self.meta = summary.get("meta", {}) or {}
        self.theme = theme
        self.key = theme["key"]
        self.tk = theme["tokens"]
        self.style = theme["style"]
        self.target = target
        self.print = target == "print"
        self.chart_n = 0
        page_w = self.style["page_width"]
        pad = 48 if self.key != "ledger" else 40
        self.content_w = page_w - 2 * pad
        if self.key == "ledger":
            self.content_w -= 236          # left rail
        if self.print:
            self.content_w = 700 if self.key != "ledger" else 700
        self.compare = self.meta.get("compare_label") or "last period"
        self.dash = False          # dashboard layout (screen): panels in a 12-column grid
        self.slot_w = None         # inner width of the panel being rendered
        self.slot_narrow = False   # panel too narrow for side-by-side chart + insight

    # -- text ---------------------------------------------------------------
    def title(self, text, tag="span"):
        """Render a title with its single *accent* fragment per the theme."""
        mode = self.style["accent"]
        out = []
        for part, is_acc in fmt.split_accent(fmt.clean_text(text)):
            if is_acc and mode != "plain":
                out.append('<em class="acc">%s</em>' % _html.escape(part))
            else:
                out.append(_html.escape(part))
        return "".join(out)

    def kicker(self, text):
        if not text:
            return ""
        return '<p class="kicker">%s</p>' % esc(text)

    def chart_sizes(self, slot="full"):
        """(wide_w, narrow_w) for a chart slot."""
        if self.slot_w:
            w = self.slot_w
            if slot == "main" and not self.slot_narrow:
                w = int(w * 0.6)
            return int(w), 340
        w = self.content_w
        if slot == "main":
            w = int(w * (0.60 if not self.print else 0.58))
        elif slot == "half":
            w = int((w - 24) / 2)
        return int(w), 340

    # -- charts -------------------------------------------------------------
    def chart(self, spec, slot="full", height=None):
        if not spec:
            return ""
        self.chart_n += 1
        t = spec.get("type", "bar-vertical")
        if t == "bar-horizontal":
            return self.bar_list(spec)
        if t in ("doughnut", "donut", "pie"):
            return self.donut(spec, slot)
        if t == "heatmap":
            return self.heatmap_grid(spec)
        if t == "funnel":
            return self.funnel_html(spec)
        wide_w, narrow_w = self.chart_sizes(slot)
        h = height or spec.get("height")
        if not h:
            h = {"line": 300, "area": 300, "line-multi": 320, "waterfall": 320, "scatter": 400,
                 "sankey": 380}.get(t, 300)
            if slot == "main":
                h = int(h * 0.95)
        size = self.style.get("chart_size", 12.0) if not self.print else self.style.get("chart_size", 12.0) * 0.86
        if self.print:
            h = int(h * 0.82)
        elif self.dash:
            h = int(h * (0.8 if self.slot_narrow else 0.86))
            if self.slot_w and self.slot_w > 1000 and t in ("line", "area", "line-multi", "bar-vertical", "bar-grouped",
                                                             "bar-stacked"):
                h = min(h, 230)
        wide = CH.render(spec, self.theme, wide_w, h, size)
        parts = ['<div class="viz viz-%s">' % esc(t)]
        if self.print:
            parts.append(wide["svg"])
        else:
            narrow = CH.render(spec, self.theme, narrow_w, int(h * 0.9) if t != "sankey" else int(h * 1.05), 11.0)
            parts.append('<div class="v-wide">%s</div><div class="v-narrow">%s</div>' % (wide["svg"], narrow["svg"]))
        parts.append(self.legend(wide.get("legend")))
        parts.append(self.data_table(wide.get("table")))
        parts.append("</div>")
        return "".join(parts)

    def legend(self, items):
        if not items:
            return ""
        out = ['<ul class="legend">']
        for it in items:
            lab, col = it[0], it[1]
            out.append('<li><i style="background:%s"></i>%s</li>' % (col, esc(lab)))
        out.append("</ul>")
        return "".join(out)

    def data_table(self, table):
        if self.print or not table:
            return ""
        head, rows = table
        if not rows:
            return ""
        th = "".join("<th>%s</th>" % esc(h) for h in head)
        tr = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % esc(c) for c in r) for r in rows[:60])
        return ('<details class="dt"><summary>Show the numbers</summary><div class="dt-wrap"><table>'
                '<thead><tr>%s</tr></thead><tbody>%s</tbody></table></div></details>' % (th, tr))

    def bar_list(self, spec):
        labels = [str(l) for l in spec.get("labels", [])]
        vals = [fmt.to_num(v, 0.0) for v in spec.get("values", [])]
        unit = spec.get("unit")
        vmax = max(vals) if vals else 1
        total = spec.get("total") or sum(vals) or 1
        show_share = spec.get("show_share", unit != "%")
        hl = spec.get("highlight")
        notes = spec.get("notes") or []
        rows = []
        for i, (lab, v) in enumerate(zip(labels, vals)):
            w = 100.0 * v / vmax if vmax else 0
            share = '<span class="bl-share">%s</span>' % fmt.pct(100.0 * v / total) if show_share else ""
            cls = "bl-row"
            if hl is not None and (hl == i or hl == lab):
                cls += " is-hl"
            elif hl is not None:
                cls += " is-dim"
            note = ""
            if i < len(notes) and notes[i]:
                note = '<span class="bl-note">%s</span>' % esc(notes[i])
            rows.append('<li class="%s" data-tip="%s"><span class="bl-label">%s%s</span>'
                        '<span class="bl-track"><span class="bl-fill" style="width:%.2f%%"></span></span>'
                        '<span class="bl-val">%s%s</span></li>' %
                        (cls, esc("%s: %s" % (lab, CH.fmt_value(v, unit))), esc(lab), note, w,
                         esc(CH.fmt_value(v, unit)), share))
        x_title = spec.get("x_title")
        cap = '<p class="bl-axis">%s</p>' % esc(x_title) if x_title else ""
        return '<div class="viz viz-barlist"><ol class="barlist">%s</ol>%s</div>' % ("".join(rows), cap)

    def donut(self, spec, slot):
        size = 210 if not self.print else 168
        if self.key == "boardroom" and not self.print:
            size = 230
        res = CH.render(spec, self.theme, size, size, 12.0)
        unit = spec.get("unit")
        items = []
        for lab, col, v, p in res["legend"]:
            val = fmt.pct(p) if unit == "%" or unit is None else CH.fmt_value(v, unit)
            sub = "" if unit == "%" else '<span class="dl-sub">%s</span>' % fmt.pct(p)
            if unit is None:
                val = fmt.compact(v)
                sub = '<span class="dl-sub">%s</span>' % fmt.pct(p)
            items.append('<li><i style="background:%s"></i><span class="dl-label">%s</span>'
                         '<span class="dl-val">%s%s</span></li>' % (col, esc(lab), esc(val), sub))
        return ('<div class="viz viz-donut-wrap"><div class="viz-donut"><div class="donut-svg">%s</div><ul class="donut-legend">%s</ul></div>%s</div>' %
                (res["svg"], "".join(items), self.data_table(res.get("table"))))

    def heatmap_grid(self, spec):
        rows = spec.get("rows") or []
        cols = spec.get("cols") or []
        vals = spec.get("values") or []
        flat = [fmt.to_num(v, 0.0) for r in vals for v in r]
        vmax = max(flat) if flat else 1
        seq = self.tk["seq"]
        unit = spec.get("unit")
        col_every = spec.get("col_label_every", 1 if len(cols) <= 12 else 3)
        out = ['<div class="viz viz-heat"><div class="heat" style="--cols:%d">' % len(cols)]
        out.append('<span class="heat-corner"></span>')
        for j, c in enumerate(cols):
            out.append('<span class="heat-col">%s</span>' % (esc(c) if j % col_every == 0 else ""))
        for i, r in enumerate(rows):
            out.append('<span class="heat-row">%s</span>' % esc(r))
            for j, c in enumerate(cols):
                v = fmt.to_num(vals[i][j] if i < len(vals) and j < len(vals[i]) else 0, 0.0)
                step = 0 if vmax <= 0 else int(round((len(seq) - 1) * (v / vmax)))
                bg = seq[step] if v > 0 else self.tk["track"]
                txt_col = "#FFFFFF" if step >= len(seq) - 3 and v > 0 else self.tk["ink2"]
                if self.tk.get("dark") and v > 0:
                    txt_col = "#FFFFFF" if step >= 3 else self.tk["ink"]
                show = spec.get("show_values", len(cols) <= 12)
                out.append('<span class="heat-cell" style="background:%s;color:%s" data-tip="%s">%s</span>' %
                           (bg, txt_col, esc("%s · %s: %s" % (r, c, CH.fmt_value(v, unit))),
                            esc(CH.fmt_value(v, unit)) if show and v > 0 else ""))
        out.append("</div>")
        lo_lab = spec.get("low_label", "Fewer")
        hi_lab = spec.get("high_label", "More")
        sw = "".join('<i style="background:%s"></i>' % c for c in seq)
        out.append('<div class="heat-scale"><span>%s</span><span class="heat-ramp">%s</span><span>%s</span></div>' %
                   (esc(lo_lab), sw, esc(hi_lab)))
        out.append("</div>")
        return "".join(out)

    def funnel_html(self, spec):
        stages = spec.get("stages") or []
        if not stages:
            return ""
        vals = [fmt.to_num(s.get("value"), 0.0) for s in stages]
        vmax = max(vals) or 1
        unit = spec.get("unit")
        from . import color as _C
        mode = "dark" if self.tk.get("dark") else "light"
        ramp = _C.ordinal(self.tk["series"][0], len(stages), mode, self.tk["panel"])
        # When the top stage dwarfs the next one (sessions vs leads), break the
        # scale: the top bar is drawn full with a break mark and the rest are
        # scaled to stage two, so every stage stays visible and readable.
        broken = len(vals) > 1 and vals[1] > 0 and vals[0] / vals[1] > 6
        ref = vals[1] if broken else vmax
        out = ['<ol class="funnel%s">' % (" is-broken" if broken else "")]
        for i, s in enumerate(stages):
            v = vals[i]
            if broken and i == 0:
                w = 100.0
            else:
                w = max(1.5, (88.0 if broken else 100.0) * v / (ref or 1))
            conv = ""
            if i > 0 and vals[i - 1] > 0:
                rate = 100.0 * v / vals[i - 1]
                conv = ('<span class="fn-conv"><span class="fn-conv-arrow">\u2193</span>%s %s</span>' %
                        (esc(fmt.pct(rate, 1 if rate < 10 else 0)), esc(s.get("conv_label") or "converted")))
            src = ('<span class="fn-src">%s</span>' % esc(s["source"])) if s.get("source") else ""
            note = ('<span class="fn-note">%s</span>' % esc(s["note"])) if s.get("note") else ""
            brk = '<span class="fn-break" aria-hidden="true"></span>' if broken and i == 0 else ""
            out.append('<li class="fn-stage" style="--w:%.2f%%;--fn-c:%s">%s<div class="fn-head"><span class="fn-label">%s</span>%s</div>'
                       '<div class="fn-bar"><span class="fn-track"><span class="fn-fill"></span>%s</span><span class="fn-val">%s</span></div>%s</li>' %
                       (w, ramp[i], conv, esc(s.get("label", "")), src, brk, esc(s.get("display") or CH.fmt_value(v, unit)), note))
        out.append("</ol>")
        return '<div class="viz viz-funnel">%s</div>' % "".join(out)


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------
def _source_chips(r, sources):
    if not sources:
        return ""
    out = ['<ul class="sources" aria-label="Data sources">']
    for s in sources:
        if isinstance(s, str):
            s = {"name": s}
        name = s.get("name", "")
        col = s.get("color") or PLATFORM_COLORS.get(name.lower(), r.tk["ink3"])
        detail = ('<span class="src-detail">%s</span>' % esc(s["detail"])) if s.get("detail") else ""
        out.append('<li class="src"><i style="background:%s"></i><span class="src-name">%s</span>%s</li>' %
                   (col, esc(name), detail))
    out.append("</ul>")
    return "".join(out)


def sec_title(r, s):
    kicker = fmt.clean_text(s.get("kicker", ""))
    parts = [p.strip() for p in kicker.split("·") if p.strip()]
    report_name = parts[0] if parts else ""
    period = s.get("period") or (" ".join(parts[1:]) if len(parts) > 1 else "")
    meta_bits = [b for b in (s.get("meta_bits") or []) if b]
    sources = s.get("sources") or r.meta.get("sources")
    dek = s.get("subtitle") or s.get("dek")
    prepared = s.get("prepared_for") or r.meta.get("prepared_for")
    by = s.get("prepared_by") or r.meta.get("prepared_by")
    out = ['<section class="s s-title">']
    if r.key == "classic":
        out.append('<div class="t-inner">')
        out.append(r.kicker(kicker))
        out.append('<h1 class="h1">%s</h1>' % r.title(s.get("title", "")))
        if dek:
            out.append('<p class="dek">%s</p>' % esc(dek))
        if meta_bits:
            out.append('<div class="meta-line">%s</div>' % "".join("<span>%s</span>" % esc(b) for b in meta_bits))
        out.append(_source_chips(r, sources))
        out.append("</div></section>")
        return "".join(out)
    out.append('<div class="t-inner">')
    top = []
    if report_name:
        top.append('<p class="t-report">%s</p>' % esc(report_name))
    if period:
        top.append('<p class="t-period">%s</p>' % esc(period))
    out.append('<div class="t-top">%s</div>' % "".join(top))
    out.append('<h1 class="h1">%s</h1>' % r.title(s.get("title", "")))
    if dek:
        out.append('<p class="dek">%s</p>' % esc(dek))
    facts = []
    if prepared:
        facts.append('<div class="fact"><dt>Prepared for</dt><dd>%s</dd></div>' % esc(prepared))
    if by:
        facts.append('<div class="fact"><dt>Prepared by</dt><dd>%s</dd></div>' % esc(by))
    for b in meta_bits:
        facts.append('<div class="fact fact-plain"><dd>%s</dd></div>' % esc(b))
    if facts:
        out.append('<dl class="facts">%s</dl>' % "".join(facts))
    out.append(_source_chips(r, sources))
    out.append("</div></section>")
    return "".join(out)


def _delta_html(r, stat):
    lab = stat.get("delta_label")
    d = stat.get("delta_direction") or "flat"
    if not lab and d == "flat":
        return ""
    good_dir = stat.get("good", "up")
    if d == "flat":
        tone = "flat"
    elif good_dir == "neutral":
        tone = "neutral"
    else:
        tone = "good" if d == good_dir else "bad"
    vs = stat.get("compare") or r.compare
    if r.key == "studio":
        txt = fmt.plain_delta(lab, d, vs)
        arrow = {"up": "↑", "down": "↓"}.get(d, "→")
        # "Up 8%" + "from August": narrow cards break between the two, never inside either
        m = re.match(r"^(.*?)\s+((?:from|vs|none in)\s.*)$", txt)
        dtx = ('<span class="dm">%s</span> <span class="dvs">%s</span>' % (esc(m.group(1)), esc(m.group(2)))) if m else esc(txt)
        return '<p class="delta %s %s"><span class="arw">%s</span><span class="dtx">%s</span></p>' % (d, tone, arrow, dtx)
    if r.key == "classic":
        if d == "flat":
            return '<span class="delta flat %s"></span>' % tone
        return '<span class="delta %s %s">%s</span>' % (d, tone, esc(lab))
    arrow = {"up": "▲", "down": "▼"}.get(d, "●")
    if d == "flat":
        lab = lab or "Flat"
        if lab.strip() in ("—", "-", ""):
            lab = "Flat"
    return ('<p class="delta %s %s"><span class="arw">%s</span><span class="dv">%s</span><span class="vs">vs %s</span></p>' %
            (d, tone, arrow, esc(lab), esc(vs)))


def _vw(r, value, role="numeral"):
    """Measured width of a number in em, for CSS auto-fit (see .kpi-value)."""
    from .measure import text_width
    f = r.theme["fonts"][role]
    w = text_width(str(value), f["css"], 100.0, f.get("weight", 400), f.get("italic", False)) / 100.0
    return ' style="--vw:%.3f"' % max(0.6, w)


def sec_kpis(r, s):
    stats = s.get("stats") or []
    n = len(stats)
    long_label = any(len(str(st.get("label", ""))) > 17 or (st.get("source") and len(str(st.get("label", ""))) + len(str(st.get("source"))) > 26) for st in stats)
    out = ['<section class="s s-kpis n%d%s">' % (n, " lbl2" if long_label else "")]
    for i, st in enumerate(stats):
        cls = "kpi"
        if st.get("emphasis") or (r.key == "boardroom" and i == 0 and n >= 4 and st.get("emphasis") is not False):
            cls += " kpi-lead"
        spark = ""
        if st.get("spark") and r.key != "classic":
            ctx = CH.Ctx(r.theme)
            col = r.tk["brand_ink"] if r.tk.get("dark") else r.tk["series"][0]
            spark = '<div class="kpi-spark">%s</div>' % CH.sparkline(st["spark"], ctx, 160, 36, col)
        note = ('<p class="kpi-note">%s</p>' % esc(st["note"])) if st.get("note") else ""
        src = ('<span class="kpi-src">%s</span>' % esc(st["source"])) if st.get("source") else ""
        if r.key == "classic":
            out.append('<div class="%s"><div class="kpi-value"%s>%s</div><div class="kpi-foot"><span class="kpi-label">%s</span>%s</div></div>' %
                       (cls, _vw(r, st.get("value", "")), esc(st.get("value", "")), esc(st.get("label", "")), _delta_html(r, st)))
        else:
            out.append('<div class="%s"><div class="kpi-head"><p class="kpi-label">%s</p>%s</div>'
                       '<p class="kpi-value"%s>%s</p>%s%s%s</div>' %
                       (cls, esc(st.get("label", "")), src, _vw(r, st.get("value", "")), esc(st.get("value", "")), _delta_html(r, st), spark, note))
    out.append("</section>")
    return "".join(out)


def sec_hero(r, s):
    spark = ""
    if s.get("spark") and r.key != "classic":
        ctx = CH.Ctx(r.theme)
        spark = '<div class="hero-spark">%s</div>' % CH.sparkline(s["spark"], ctx, 360, 64, r.tk["series"][0] if not r.tk.get("dark") else r.tk["brand_ink"])
    delta = _delta_html(r, s) if s.get("delta_label") else ""
    return ('<section class="s s-hero"><div class="hero-top">%s<p class="hero-value"%s>%s</p>%s</div>'
            '%s%s</section>' %
            (r.kicker(s.get("kicker")), _vw(r, s.get("value", "")), esc(s.get("value", "")), delta,
             ('<div class="hero-bottom"><p class="hero-label">%s</p></div>' % esc(s["label"])) if s.get("label") else "",
             spark))


def sec_head(r, s):
    num = s.get("number")
    return ('<header class="s s-head">%s%s<h2 class="h2">%s</h2>%s</header>' %
            (('<span class="sh-num">%s</span>' % esc(num)) if num else "",
             ('<p class="sh-kicker">%s</p>' % esc(s["kicker"])) if s.get("kicker") else "",
             r.title(s.get("title", "")),
             ('<p class="sh-dek">%s</p>' % esc(s["dek"])) if s.get("dek") else ""))


def _fig(r, s, inner):
    title = ('<h3 class="fig-title">%s</h3>' % r.title(s["chart_title"])) if s.get("chart_title") else ""
    cap = ('<figcaption class="caption">%s</figcaption>' % esc(s["caption"])) if s.get("caption") else ""
    return '<figure class="fig">%s%s%s</figure>' % (title, inner, cap)


def sec_chart(r, s):
    return '<section class="s s-chart">%s</section>' % _fig(r, s, r.chart(s.get("chart"), "full"))


def _insight_body(r, paras):
    if not paras:
        return ""
    if isinstance(paras, str):
        paras = [paras]
    return '<div class="ins-body">%s</div>' % "".join("<p>%s</p>" % esc(p) for p in paras)


def sec_chart_insight(r, s):
    chart = s.get("chart") or {}
    slot = "main"
    fig = _fig(r, s, r.chart(chart, slot))
    aside = ('<aside class="ins"><div class="ins-top">%s<h3 class="h3">%s</h3></div>%s</aside>' %
             (r.kicker(s.get("insight_kicker")), r.title(s.get("insight_title", "")),
              _insight_body(r, s.get("insight_body"))))
    kind = chart.get("type", "")
    return '<section class="s s-chart-insight ci-%s">%s%s</section>' % (esc(kind), fig, aside)


def _cell(r, col, v, colmax):
    t = col.get("type", "name")
    if v is None:
        return ""
    if t == "trend" and isinstance(v, dict):
        return '<span class="pill trend %s">%s</span>' % (esc(v.get("state", "steady")), esc(v.get("label", "")))
    if t == "badge":
        if isinstance(v, dict):
            return '<span class="pill badge %s">%s</span>' % (esc(v.get("tone", "neutral")), esc(v.get("label", "")))
        return '<span class="pill badge neutral">%s</span>' % esc(v)
    if t == "delta":
        if isinstance(v, dict):
            d = v.get("direction", "flat")
            good = v.get("good", col.get("good", "up"))
            tone = "flat" if d == "flat" else ("good" if d == good else "bad")
            arrow = {"up": "▲", "down": "▼"}.get(d, "")
            return '<span class="cell-delta %s">%s%s</span>' % (tone, ('<span class="arw">%s</span>' % arrow) if arrow else "", esc(v.get("label", "")))
        n = fmt.to_num(v)
        if n is None:
            return esc(v)
        d = "up" if n > 0 else ("down" if n < 0 else "flat")
        good = col.get("good", "up")
        tone = "flat" if d == "flat" else ("good" if d == good else "bad")
        unit = col.get("unit", "%")
        lab = ("+" if n > 0 else "") + CH.fmt_value(n, unit)
        return '<span class="cell-delta %s">%s</span>' % (tone, esc(lab))
    if t == "bar":
        if isinstance(v, dict):
            n = fmt.to_num(v.get("value"), 0.0)
            lab = v.get("label") or CH.fmt_value(n, col.get("unit"))
        else:
            n = fmt.to_num(v, 0.0)
            lab = v if isinstance(v, str) else CH.fmt_value(n, col.get("unit"))
        w = 100.0 * n / colmax if colmax else 0
        return ('<span class="cell-bar"><span class="cb-val">%s</span><span class="cb-track"><span class="cb-fill" style="width:%.1f%%"></span></span></span>' %
                (esc(lab), max(0.0, min(100.0, w))))
    if t == "spark":
        vals = v.get("values") if isinstance(v, dict) else v
        return CH.sparkline(vals, CH.Ctx(r.theme), 90, 22, None, fill=False)
    if t == "platform":
        name = v.get("name") if isinstance(v, dict) else str(v)
        c = PLATFORM_COLORS.get(name.lower(), r.tk["ink3"])
        return '<span class="plat"><i style="background:%s"></i>%s</span>' % (c, esc(name))
    if isinstance(v, dict):
        v = v.get("label", "")
    return esc(v)


def sec_table(r, s):
    cols = s.get("columns") or []
    rows = s.get("rows") or []
    if not cols:
        return ""
    colmax = {}
    for c in cols:
        if c.get("type") == "bar":
            m = 0.0
            for row in rows:
                v = row.get(c["key"])
                n = fmt.to_num(v.get("value") if isinstance(v, dict) else v, 0.0)
                m = max(m, n or 0.0)
            colmax[c["key"]] = c.get("max") or m or 1.0
    th = []
    for c in cols:
        cls = ["c-%s" % c.get("type", "name")]
        if c.get("align"):
            cls.append("a-%s" % c["align"])
        style = ' style="width:%s"' % esc(c["width"]) if c.get("width") and r.key == "classic" else ""
        th.append('<th class="%s"%s>%s</th>' % (" ".join(cls), style, esc(c.get("label", ""))))
    body = []
    for row in rows:
        tds = []
        for c in cols:
            cls = ["c-%s" % c.get("type", "name")]
            if c.get("align"):
                cls.append("a-%s" % c["align"])
            tds.append('<td class="%s">%s</td>' % (" ".join(cls), _cell(r, c, row.get(c["key"]), colmax.get(c["key"]))))
        rcls = []
        if row.get("_highlight"):
            rcls.append("is-hl")
        if row.get("_muted"):
            rcls.append("is-muted")
        body.append('<tr%s>%s</tr>' % (' class="%s"' % " ".join(rcls) if rcls else "", "".join(tds)))
    foot = ""
    if s.get("totals"):
        tot = s["totals"]
        tds = []
        for c in cols:
            cls = ["c-%s" % c.get("type", "name")]
            if c.get("align"):
                cls.append("a-%s" % c["align"])
            v = tot.get(c["key"], "")
            if isinstance(v, dict):
                v = v.get("label", "")
            tds.append('<td class="%s">%s</td>' % (" ".join(cls), esc(v)))
        foot = "<tfoot><tr>%s</tr></tfoot>" % "".join(tds)
    title = ('<h3 class="tbl-title">%s</h3>' % r.title(s["title"])) if s.get("title") else ""
    cap = ('<p class="caption">%s</p>' % esc(s["caption"])) if s.get("caption") else ""
    return ('<section class="s s-table">%s<div class="tbl-wrap"><table class="tbl"><thead><tr>%s</tr></thead>'
            '<tbody>%s</tbody>%s</table></div>%s</section>' % (title, "".join(th), "".join(body), foot, cap))


def _re_generic_label(label):
    import re as _re
    return bool(_re.match(r"^(action|step|fix|rec)\s*0*\d+$", str(label).strip(), _re.I))


def sec_recs(r, s):
    items = s.get("items") or []
    out = ['<section class="s s-recs n%d"><ol class="recs">' % len(items)]
    for i, it in enumerate(items):
        meta = []
        if it.get("impact"):
            meta.append('<span class="pill impact %s">%s impact</span>' % (esc(str(it["impact"]).lower()), esc(it["impact"])))
        if it.get("effort"):
            meta.append('<span class="pill effort">%s effort</span>' % esc(it["effort"]))
        if it.get("metric"):
            meta.append('<span class="rec-metric">%s</span>' % esc(it["metric"]))
        label = it.get("label") or "Action %02d" % (i + 1)
        if r.key != "classic" and _re_generic_label(label):
            label = ""
        out.append('<li class="rec"><div class="rec-top">%s<h3 class="h3">%s</h3></div>'
                   '<div class="rec-body"><p>%s</p>%s</div></li>' %
                   (('<p class="rec-label">%s</p>' % esc(label)) if label else "", r.title(it.get("title", "")), esc(it.get("body", "")),
                    ('<div class="rec-meta">%s</div>' % "".join(meta)) if meta else ""))
    out.append("</ol></section>")
    return "".join(out)


def sec_insight(r, s):
    tone = s.get("tone", "neutral")
    return ('<section class="s s-insight tone-%s"><div class="ins-top">%s<h3 class="h3">%s</h3></div>%s</section>' %
            (esc(tone), r.kicker(s.get("kicker")), r.title(s.get("title", "")), _insight_body(r, s.get("body"))))


def sec_closing(r, s):
    stats = s.get("summary_stats") or []
    bullets = s.get("bullets") or []
    st_html = ""
    if stats:
        st_html = '<dl class="cl-stats n%d">%s</dl>' % (len(stats), "".join(
            '<div><dt>%s</dt><dd%s>%s</dd></div>' % (esc(x.get("label", "")), _vw(r, x.get("value", "")), esc(x.get("value", ""))) for x in stats[:4]))
    bl = ""
    if bullets:
        bl = '<ul class="cl-bullets">%s</ul>' % "".join("<li>%s</li>" % esc(b) for b in bullets[:4])
    body = ('<p class="cl-body">%s</p>' % esc(s["body"])) if s.get("body") else ""
    return ('<section class="s s-closing"><div class="cl-inner">%s<h2 class="h2 cl-title">%s</h2>%s%s%s</div></section>' %
            (r.kicker(s.get("kicker")), r.title(s.get("title", "")), st_html, bl, body))


def sec_funnel(r, s):
    spec = {"stages": s.get("stages"), "unit": s.get("unit")}
    head = ""
    if s.get("title"):
        head = '<h3 class="fig-title">%s</h3>' % r.title(s["title"])
    side = ""
    if s.get("insight_title") or s.get("insight_body"):
        side = ('<aside class="ins"><div class="ins-top">%s<h3 class="h3">%s</h3></div>%s</aside>' %
                (r.kicker(s.get("insight_kicker")), r.title(s.get("insight_title", "")), _insight_body(r, s.get("insight_body"))))
    cap = ('<p class="caption">%s</p>' % esc(s["caption"])) if s.get("caption") else ""
    cls = "s s-funnel" + (" has-side" if side else "")
    return '<section class="%s"><div class="fn-main">%s%s%s</div>%s</section>' % (cls, head, r.funnel_html(spec), cap, side)


def sec_flow(r, s):
    spec = dict(s)
    spec["type"] = "sankey"
    inner = r.chart(spec, "full", s.get("height"))
    return '<section class="s s-flow">%s</section>' % _fig(r, s, inner)


def sec_heatmap(r, s):
    spec = dict(s)
    spec["type"] = "heatmap"
    return '<section class="s s-heatmap">%s</section>' % _fig(r, s, r.heatmap_grid(spec))


def sec_matrix(r, s):
    spec = dict(s)
    spec["type"] = "scatter"
    fig = _fig(r, s, r.chart(spec, "main" if s.get("insight_title") else "full", s.get("height")))
    if s.get("insight_title"):
        aside = ('<aside class="ins"><div class="ins-top">%s<h3 class="h3">%s</h3></div>%s</aside>' %
                 (r.kicker(s.get("insight_kicker")), r.title(s.get("insight_title", "")), _insight_body(r, s.get("insight_body"))))
        return '<section class="s s-chart-insight s-matrix">%s%s</section>' % (fig, aside)
    return '<section class="s s-matrix">%s</section>' % fig


def sec_comparison(r, s):
    a, b = s.get("a") or {}, s.get("b") or {}
    rows = s.get("rows") or []
    head = ('<div class="cmp-head"><div class="cmp-side cmp-a"><i style="background:%s"></i><span>%s</span>%s</div>'
            '<div class="cmp-vs">vs</div><div class="cmp-side cmp-b"><i style="background:%s"></i><span>%s</span>%s</div></div>' %
            (r.tk["series"][0], esc(a.get("label", "A")), ('<small>%s</small>' % esc(a["sub"])) if a.get("sub") else "",
             r.tk["series"][1] if len(r.tk["series"]) > 1 else r.tk["neutral"], esc(b.get("label", "B")),
             ('<small>%s</small>' % esc(b["sub"])) if b.get("sub") else ""))
    out = ['<section class="s s-compare">', head, '<ul class="cmp-rows">']
    for row in rows:
        av, bv = fmt.to_num(row.get("a"), None), fmt.to_num(row.get("b"), None)
        m = max(abs(av or 0), abs(bv or 0)) or 1
        wa = 100.0 * abs(av or 0) / m
        wb = 100.0 * abs(bv or 0) / m
        win = row.get("better")
        out.append('<li class="cmp-row"><span class="cmp-metric">%s</span>'
                   '<span class="cmp-cell cmp-a%s"><b>%s</b><span class="cmp-bar"><span style="width:%.1f%%"></span></span></span>'
                   '<span class="cmp-cell cmp-b%s"><span class="cmp-bar"><span style="width:%.1f%%"></span></span><b>%s</b></span></li>' %
                   (esc(row.get("label", "")), " is-win" if win == "a" else "", esc(row.get("a_display") or row.get("a", "")), wa,
                    " is-win" if win == "b" else "", wb, esc(row.get("b_display") or row.get("b", ""))))
    out.append("</ul>")
    if s.get("caption"):
        out.append('<p class="caption">%s</p>' % esc(s["caption"]))
    out.append("</section>")
    return "".join(out)


def sec_timeline(r, s):
    events = s.get("events") or []
    out = ['<section class="s s-timeline">']
    if s.get("title"):
        out.append('<h3 class="fig-title">%s</h3>' % r.title(s["title"]))
    out.append('<ol class="tl">')
    for e in events:
        kind = e.get("kind", "touch")
        out.append('<li class="tl-ev k-%s"><span class="tl-dot"></span><div class="tl-when">%s</div>'
                   '<div class="tl-what"><p class="tl-title">%s</p>%s%s</div></li>' %
                   (esc(kind), esc(e.get("date", "")), esc(e.get("title", "")),
                    ('<p class="tl-detail">%s</p>' % esc(e["detail"])) if e.get("detail") else "",
                    ('<p class="tl-tags">%s</p>' % "".join('<span class="tag">%s</span>' % esc(t) for t in e.get("tags", []))) if e.get("tags") else ""))
    out.append("</ol></section>")
    return "".join(out)


_STATUS_ICON = {"pass": "✓", "good": "✓", "warn": "!", "fail": "✕", "bad": "✕", "info": "i"}


def sec_scorecard(r, s):
    items = s.get("items") or []
    out = ['<section class="s s-score">']
    if s.get("title"):
        out.append('<h3 class="fig-title">%s</h3>' % r.title(s["title"]))
    out.append('<ul class="score">')
    for it in items:
        st = it.get("status", "info")
        out.append('<li class="sc st-%s"><span class="sc-icon" aria-hidden="true">%s</span>'
                   '<div class="sc-main"><p class="sc-label">%s</p>%s</div><p class="sc-value">%s</p>'
                   '<span class="sc-status">%s</span></li>' %
                   (esc(st), _STATUS_ICON.get(st, "i"), esc(it.get("label", "")),
                    ('<p class="sc-detail">%s</p>' % esc(it["detail"])) if it.get("detail") else "",
                    esc(it.get("value", "")), esc(it.get("status_label") or {"pass": "Healthy", "good": "Healthy",
                                                                              "warn": "Watch", "fail": "Fix",
                                                                              "bad": "Fix"}.get(st, "Info"))))
    out.append("</ul></section>")
    return "".join(out)


def sec_callouts(r, s):
    items = s.get("items") or []
    out = ['<section class="s s-callouts n%d">' % len(items)]
    for it in items:
        tone = it.get("tone", "neutral")
        out.append('<div class="co tone-%s">%s<p class="co-value"%s>%s</p><p class="co-title">%s</p>%s</div>' %
                   (esc(tone), ('<p class="co-kicker">%s</p>' % esc(it["kicker"])) if it.get("kicker") else "",
                    _vw(r, it.get("value", "")), esc(it.get("value", "")), r.title(it.get("title", "")),
                    ('<p class="co-body">%s</p>' % esc(it["body"])) if it.get("body") else ""))
    out.append("</section>")
    return "".join(out)


def sec_notes(r, s):
    items = s.get("items") or []
    title = s.get("title") or "How we built this report"
    return ('<section class="s s-notes"><h3 class="notes-title">%s</h3><ul>%s</ul></section>' %
            (esc(title), "".join("<li>%s</li>" % esc(i) for i in items)))


RENDERERS = {
    "title-block": sec_title, "stat-strip": sec_kpis, "hero-number": sec_hero,
    "section-header": sec_head, "chart": sec_chart, "chart-insight": sec_chart_insight,
    "ranked-list": sec_table, "table": sec_table, "recommendations": sec_recs,
    "insight-card": sec_insight, "closing": sec_closing, "funnel": sec_funnel,
    "flow": sec_flow, "sankey": sec_flow, "heatmap": sec_heatmap, "matrix": sec_matrix,
    "comparison": sec_comparison, "timeline": sec_timeline, "scorecard": sec_scorecard,
    "callouts": sec_callouts, "notes": sec_notes,
}


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def _logo(r):
    brand = r.meta.get("brand_profile") or {}
    logo = brand.get("logo") or {}
    name = brand.get("company_name") or r.meta.get("customer_name") or ""
    if logo.get("type") == "url" and logo.get("value"):
        return '<img class="logo-img" src="%s" alt="%s">' % (esc(logo["value"]), esc(name))
    if logo.get("type") == "upload" and logo.get("value"):
        v = logo["value"]
        mime = "image/svg+xml" if v.strip().startswith("PHN2") else "image/png"
        return '<img class="logo-img" src="data:%s;base64,%s" alt="%s">' % (mime, esc(v), esc(name))
    text = logo.get("value") if logo.get("type") == "text" else name
    text = fmt.clean_text(text or name)
    # text logos are rendered as text, never as raw HTML
    import re as _re
    text = _re.sub(r"<[^>]+>", "", text or "")
    return '<span class="logo-text">%s</span>' % _html.escape(text)


def _chapters(sections):
    """Group sections under their section-header: [(header|None, [sections])]."""
    chapters = [(None, [])]
    for s in sections:
        if s.get("type") == "section-header":
            chapters.append((s, []))
        else:
            chapters[-1][1].append(s)
    return [c for c in chapters if c[0] is not None or c[1]]


def _gen_date(meta):
    g = meta.get("generated_at")
    try:
        d = _dt.datetime.strptime(g[:10], "%Y-%m-%d")
    except Exception:
        d = _dt.datetime.utcnow()
    return d.strftime("%b %-d, %Y") if os.name != "nt" else d.strftime("%b %d, %Y")


_JS = r"""
(function(){var tip=document.createElement('div');tip.className='tip';document.body.appendChild(tip);
function show(e){var t=e.target.closest('[data-tip]');if(!t){tip.style.opacity=0;return;}
tip.textContent=t.getAttribute('data-tip');tip.style.opacity=1;var x=e.clientX+14,y=e.clientY+14;
var w=tip.offsetWidth,h=tip.offsetHeight;if(x+w>innerWidth-8)x=e.clientX-w-14;if(y+h>innerHeight-8)y=e.clientY-h-14;
tip.style.transform='translate('+x+'px,'+y+'px)';}
document.addEventListener('mousemove',show);document.addEventListener('mouseleave',function(){tip.style.opacity=0;});})();
"""


# ---------------------------------------------------------------------------
# Dashboard layout (screen default): a slim header, the numbers right under
# it, then every chart, table and insight as a panel in a 12-column grid, so
# one screen shows the whole picture. Print keeps the document layout.
# ---------------------------------------------------------------------------
DASH_W = 1312          # content width the panels are sized for (a 1360px window)
DASH_GAP = 16
DASH_PAD = 20

_DASH_SPAN = {"insight-card": 4, "hero-number": 4, "chart-insight": 6, "chart": 6, "funnel": 6, "flow": 6,
              "sankey": 6, "matrix": 6, "comparison": 6, "timeline": 6, "scorecard": 6, "callouts": 12,
              "recommendations": 12, "stat-strip": 12}
_DASH_SKIP = ("title-block", "closing", "notes", "section-header")


def _dash_pref(s):
    t = s.get("type")
    if t in ("ranked-list", "table"):
        return 6 if len(s.get("columns") or []) <= 4 else 12
    if t == "heatmap":
        return 12 if len(s.get("cols") or []) > 12 else 6
    if t == "chart":
        ch = s.get("chart") or {}
        n = len(ch.get("labels") or [])
        if ch.get("type") in ("bar-grouped", "bar-stacked", "bar-vertical") and n > 10:
            return 12
    return _DASH_SPAN.get(t, 6)


def _dash_inner_w(span):
    col = (DASH_W - 11 * DASH_GAP) / 12.0
    return int(span * col + (span - 1) * DASH_GAP - 2 * DASH_PAD)


def _dash_panels(sections):
    """One panel per content section. A chapter's header heads its first panel;
    later panels in the chapter carry the chapter name as a small label."""
    panels = []
    head = None
    first = False
    kpis_seen = False
    for s in sections:
        t = s.get("type")
        if t == "stat-strip" and not kpis_seen:   # the first one is the KPI band under the header
            kpis_seen = True
            continue
        if t == "section-header":
            head, first = s, True
            continue
        if t in _DASH_SKIP or t not in RENDERERS:
            continue
        panels.append({"sec": s, "head": head if first else None,
                       "label": (head or {}).get("kicker") if head and not first else None,
                       "span": _dash_pref(s)})
        first = False
    return panels


def _dash_pack(panels):
    """Greedy rows of 12: a panel that doesn't fit starts a new row, and the
    last panel of the row it leaves stretches to fill it."""
    row, used = [], 0
    for p in panels:
        if used + p["span"] > 12:
            if row:
                row[-1]["span"] += 12 - used
            row, used = [], 0
        row.append(p)
        used += p["span"]
        if used == 12:
            row, used = [], 0
    if row:
        row[-1]["span"] += 12 - used
    return panels


def _dash_panel_title(sec):
    t = sec.get("type")
    if t == "comparison":
        a, b = sec.get("a") or {}, sec.get("b") or {}
        if a.get("label") and b.get("label"):
            return "%s vs %s" % (a["label"], b["label"])
    return None


def _dash_panel(r, p):
    sec, span = p["sec"], p["span"]
    r.slot_w = _dash_inner_w(span)
    r.slot_narrow = span < 8
    head = ""
    h = p.get("head")
    if h:
        head = ('<header class="p-head">%s<h2 class="p-title">%s</h2>%s</header>' %
                (('<p class="p-kicker">%s</p>' % esc(h["kicker"])) if h.get("kicker") else "",
                 r.title(h.get("title", "")), ('<p class="p-dek">%s</p>' % esc(h["dek"])) if h.get("dek") else ""))
    else:
        bits = []
        if p.get("label"):
            bits.append('<p class="p-kicker">%s</p>' % esc(p["label"]))
        alt = _dash_panel_title(sec)
        if alt:
            bits.append('<h2 class="p-title">%s</h2>' % esc(alt))
        if bits:
            head = '<header class="p-head p-head-sm">%s</header>' % "".join(bits)
    try:
        inner = RENDERERS[sec["type"]](r, sec)
    except Exception as exc:  # one bad section never breaks the report
        inner = '<!-- skipped %s: %s -->' % (esc(sec.get("type")), esc(exc))
    r.slot_w, r.slot_narrow = None, False
    cls = "panel span-%d p-%s %s" % (span, esc(sec.get("type")), "p-narrow" if span < 8 else "p-wide")
    if sec.get("type") == "insight-card":
        cls += " tone-%s" % esc(sec.get("tone", "neutral"))
    if p.get("extra"):
        cls += " has-next"
    return '<article class="%s">%s%s%s</article>' % (cls, head, inner, p.get("extra", ""))


def _dash_next(r, closing):
    """The closing's next step, pulled up beside the headline."""
    if not closing or not closing.get("title"):
        return ""
    title = fmt.clean_text(closing["title"])
    label = "Next step"
    m = re.match(r"^(Next(?: [a-z]+)?):\s*(.+)$", title, re.S)
    if m:
        label = m.group(1) if m.group(1) != "Next" else "Next step"
        rest = m.group(2)
        title = rest[:1].upper() + rest[1:]
    bullets = [b for b in (closing.get("bullets") or []) if b][:4]
    bl = ('<ul class="d-next-list">%s</ul>' % "".join("<li>%s</li>" % esc(b) for b in bullets)) if bullets else ""
    return '<aside class="d-next"><p class="d-next-k">%s</p><p class="d-next-t">%s</p>%s</aside>' % (
        esc(label), r.title(title), bl)


def _dash_header(r, t, nxt=""):
    kicker = fmt.clean_text(t.get("kicker", ""))
    parts = [x.strip() for x in kicker.split("·") if x.strip()]
    report_name = parts[0] if parts else ""
    period = t.get("period") or (" ".join(parts[1:]) if len(parts) > 1 else "")
    sources = t.get("sources") or r.meta.get("sources")
    prepared = t.get("prepared_for") or r.meta.get("prepared_for")
    by = t.get("prepared_by") or r.meta.get("prepared_by")
    facts = []
    if prepared:
        facts.append("For %s" % prepared)
    if by:
        facts.append("By %s" % by)
    facts += [b for b in (t.get("meta_bits") or []) if b]
    top = ('<header class="d-top"><div class="d-id"><span class="d-logo">%s</span>%s%s</div>%s</header>' %
           (_logo(r), ('<span class="d-report">%s</span>' % esc(report_name)) if report_name else "",
            ('<span class="d-period">%s</span>' % esc(period)) if period else "", _source_chips(r, sources)))
    dek = t.get("subtitle") or t.get("dek")
    hl = ('<div class="d-hl"><h1 class="d-h1">%s</h1>%s%s</div>' %
          (r.title(t.get("title", "")), ('<p class="d-dek">%s</p>' % esc(dek)) if dek else "",
           ('<p class="d-facts">%s</p>' % "".join("<span>%s</span>" % esc(f) for f in facts)) if facts else ""))
    return top + '<section class="d-hero%s">%s%s</section>' % (" has-next" if nxt else "", hl, nxt)


def _dash_body(r, sections):
    r.dash = True
    title_sec = next((x for x in sections if x.get("type") == "title-block"), {})
    closing = next((x for x in sections if x.get("type") == "closing"), None)
    kpis = ""
    for x in sections:
        if x.get("type") == "stat-strip":
            kpis = sec_kpis(r, x).replace('class="s s-kpis', 'class="s s-kpis d-kpis', 1)
            break
    panels = _dash_panels(sections)
    # a hero number the headline already states is a repeat on a dashboard
    head_text = fmt.strip_accent(fmt.clean_text(title_sec.get("title", "")))
    panels = [p for p in panels if not (p["sec"].get("type") == "hero-number"
                                        and str(p["sec"].get("value", "")).strip()
                                        and str(p["sec"]["value"]).strip() in head_text)]
    nxt = _dash_next(r, closing)
    hero_next = ""
    if nxt:
        # the next step sits with the opening takeaway (insight and action in one column);
        # with no takeaway to pair with, it sits beside the headline
        lead = panels[0] if panels and panels[0]["sec"].get("type") == "insight-card" else None
        if lead:
            lead["extra"] = nxt
        else:
            hero_next = nxt
    panels = _dash_pack(panels)
    out = [_dash_header(r, title_sec, hero_next), kpis]
    out.append('<div class="d-grid">%s</div>' % "".join(_dash_panel(r, p) for p in panels))
    notes = [x for x in sections if x.get("type") == "notes"]
    for n_ in notes:
        items = n_.get("items") or []
        out.append('<details class="d-notes"><summary>%s</summary><ul>%s</ul></details>' %
                   (esc(n_.get("title") or "How we built this report"), "".join("<li>%s</li>" % esc(i) for i in items)))
    return "".join(out)


def render_html(summary, theme=None, target="screen", layout=None, fragment=False):
    """layout: "dashboard" (screen default) or "document" (one long read; print always uses it).
    fragment=True returns the page without its document skeleton, for publishing as a claude.ai
    Artifact (the host adds the skeleton): title first, then styles, then the report."""
    key = pick_theme(theme, summary)
    meta = summary.get("meta", {}) or {}
    th = resolve_theme(key, meta.get("brand_profile"))
    r = R(summary, th, target)
    sections = summary.get("sections") or []
    layout = layout or meta.get("layout") or "dashboard"
    dash = target == "screen" and layout == "dashboard"
    # document title
    title_sec = next((s for s in sections if s.get("type") == "title-block"), {})
    doc_title = fmt.strip_accent(fmt.clean_text(title_sec.get("title", "Attribution report")))
    company = (meta.get("brand_profile") or {}).get("company_name") or meta.get("customer_name") or ""
    body = []
    for head, secs in ([] if dash else _chapters(sections)):
        cls = "chapter" + (" ch-cover" if head is None else "")
        body.append('<div class="%s">' % cls)
        if head is not None:
            body.append('<div class="ch-rail">%s</div>' % sec_head(r, head))
        body.append('<div class="ch-body">')
        for s in secs:
            fn = RENDERERS.get(s.get("type"))
            if not fn:
                continue
            try:
                body.append(fn(r, s))
            except Exception as exc:  # one bad section never breaks the report
                body.append('<!-- skipped %s: %s -->' % (esc(s.get("type")), esc(exc)))
        body.append("</div></div>")
    sources = meta.get("sources") or title_sec.get("sources") or []
    src_names = ", ".join((s.get("name") if isinstance(s, dict) else str(s)) for s in sources) or "UTM Grabber"
    domain = meta.get("customer_domain") or ""
    footer_left = "Data: %s%s" % (src_names, (" for " + domain) if domain else "")
    by = meta.get("prepared_by")
    footer_right = "%sPrepared with UTM Grabber, v%s, %s" % (
        ("%s. " % by) if by else "", meta.get("skill_version", "2.0.0"), _gen_date(meta))
    css = "\n".join([font_face_css(th["font_files"]), css_vars(th), _read_css("base.css"),
                     _read_css("%s.css" % key)])
    if target == "print":
        css += "\n" + _read_css("print.css") + "\n" + _read_css("%s.print.css" % key)
    elif dash:
        css += "\n" + _read_css("dash.css") + "\n" + _read_css("%s.dash.css" % key)
    head = ('<!doctype html><html lang="en" data-theme="%s" class="t-%s%s"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta name="generator" content="UTM Grabber Reports %s">'
            '<title>%s%s</title><style>%s</style></head>' %
            (key, target + (" is-dash" if dash else ""), " is-dark" if th["tokens"].get("dark") else "",
             esc(meta.get("skill_version", "")),
             esc(doc_title), (" | " + esc(company)) if company else "", css))
    top = ('<header class="rp-top"><div class="rp-brand">%s</div><div class="rp-top-meta">%s</div></header>' %
           (_logo(r), esc(meta.get("prepared_for") and ("For " + meta["prepared_for"]) or domain)))
    foot = ('<footer class="rp-foot"><span>%s</span><span>%s</span></footer>' % (esc(footer_left), esc(footer_right)))
    js = "" if target == "print" else "<script>%s</script>" % _JS
    if fragment:
        report_name = fmt.clean_text(title_sec.get("kicker", "")).split("·")[0].strip() or "Attribution report"
        name = ("%s %s" % (company, report_name)) if company else report_name
        classes = ["t-screen"] + (["is-dash"] if dash else []) + (["is-dark"] if th["tokens"].get("dark") else [])
        css += ":root{color-scheme:%s}" % ("dark" if th["tokens"].get("dark") else "light")
        main = (_dash_body(r, sections) if dash else top + "".join(body))
        return ('<title>%s</title><script>document.documentElement.classList.add(%s)</script><style>%s</style>'
                '<div class="rp%s"><main class="rp-main">%s</main>%s</div>%s' %
                (esc(name), ",".join("'%s'" % c for c in classes), css, " dash" if dash else "", main, foot, js))
    if dash:
        return "%s<body><div class=\"rp dash\"><main class=\"rp-main\">%s</main>%s</div>%s</body></html>" % (
            head, _dash_body(r, sections), foot, js)
    return "%s<body><div class=\"rp\">%s<main class=\"rp-main\">%s</main>%s</div>%s</body></html>" % (
        head, top, "".join(body), foot, js)


def write_html(summary, path, theme=None, layout=None):
    """A path ending in .artifact.html gets the skeleton-free page for a claude.ai Artifact."""
    html = render_html(summary, theme, "screen", layout, fragment=path.lower().endswith(".artifact.html"))
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
