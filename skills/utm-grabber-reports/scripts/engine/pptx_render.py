"""
Summary dict -> native, editable PowerPoint deck (16:9), in any theme.

What the deck is made of:
  * native PowerPoint charts (editable data) for doughnuts, columns, stacked and
    grouped bars, lines, waterfalls and diverging bars
  * vector shapes for the custom visuals (bar lists, funnels, flows, heatmaps,
    quadrant maps, sparklines), drawn from the same geometry as the HTML report
  * native tables with in-cell bars and status pills
  * real text everywhere: every title, number and note can be edited
  * speaker notes on every content slide with the talking points

Slide plan: cover, "at a glance" (KPIs + headline), then one slide per content
section. A section header becomes the title of the slide that follows it. Long
tables continue onto extra slides. Footer: report name left, page number right.
"""
import math
import os
import re

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import (XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE,
                            XL_TICK_LABEL_POSITION, XL_TICK_MARK)
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt
from lxml import etree

from . import color as COL
from . import fmt
from .charts import fmt_value
from .measure import text_width
from .themes import pick_theme, resolve_theme

IN = 914400
# Keynote ignores embedded fonts and falls back to Helvetica. These factors are how
# much wider Helvetica sets the same text, so layouts keep headroom and never overflow.
FALLBACK_WIDTH = {"Instrument Serif": 1.36, "Barlow Condensed": 1.34, "Barlow": 1.08,
                  "IBM Plex Sans Condensed": 1.09}
SW, SH = 13.333, 7.5
MX = 0.62            # side margin
CONTENT_R = SW - MX
FOOT_Y = 7.04


def E(v):
    return Emu(int(round(v * IN)))


def rgb(h):
    h = COL.clean_hex(h).lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# ---------------------------------------------------------------------------
# Theme parameters specific to slides
# ---------------------------------------------------------------------------
SLIDE_STYLE = {
    "classic": {"radius": 0.04, "title": 32, "title_min": 22, "kicker_upper": True, "kpi": 46, "hero": 120,
                "card": "twotone", "accent": "italic", "title_bold": False, "body": 13},
    "boardroom": {"radius": 0.16, "title": 34, "title_min": 22, "kicker_upper": False, "kpi": 52, "hero": 132,
                  "card": "panel", "accent": "color", "title_bold": True, "body": 13.5},
    "ledger": {"radius": 0.06, "title": 26, "title_min": 18, "kicker_upper": False, "kpi": 30, "hero": 96,
               "card": "panel", "accent": "none", "title_bold": True, "body": 12.5},
    "studio": {"radius": 0.2, "title": 32, "title_min": 20, "kicker_upper": False, "kpi": 40, "hero": 120,
               "card": "panel", "accent": "color-bold", "title_bold": False, "body": 13.5},
}


class Deck(object):
    def __init__(self, summary, theme_key):
        self.summary = summary
        self.meta = summary.get("meta", {}) or {}
        self.key = theme_key
        self.theme = resolve_theme(theme_key, self.meta.get("brand_profile"))
        self.tk = self.theme["tokens"]
        self.fonts = self.theme["fonts"]
        self.ss = SLIDE_STYLE[theme_key]
        self.prs = Presentation()
        self.prs.slide_width = E(SW)
        self.prs.slide_height = E(SH)
        self.layout = self.prs.slide_layouts[6]
        self.compare = self.meta.get("compare_label") or "last period"
        self.company = (self.meta.get("brand_profile") or {}).get("company_name") or self.meta.get("customer_name") or ""
        self.report_name = ""
        self.slides = []
        # python-pptx's notes pages make Keynote reject the whole file ("format is
        # invalid"), so speaker notes are opt-in (PowerPoint and Google Slides only).
        self.speaker_notes = bool(self.meta.get("speaker_notes", False))

    # ------------------------------------------------------------------ fonts
    def font(self, role, bold=None, italic=None):
        f = self.fonts.get(role) or self.fonts["body"]
        b = f.get("pptx_bold", False) if bold is None else bold
        it = f.get("italic", False) if italic is None else italic
        return f["pptx"], b, it

    def measure(self, text, role, size, bold=None, italic=None, safe=True):
        fam, b, it = self.font(role, bold, italic)
        w = text_width(text, fam, size, 700 if b else 400, it) / 72.0
        return w * (FALLBACK_WIDTH.get(fam, 1.0) if safe else 1.0)

    def fit(self, text, role, max_w, max_h, start, minimum, max_lines=3, bold=None, italic=None, lh=1.12):
        """Largest size whose wrapped lines fit max_w x max_h (inches). Returns (size, n_lines)."""
        fam, b, it = self.font(role, bold, italic)
        size = start
        factor = FALLBACK_WIDTH.get(fam, 1.0)
        while True:
            lines = _wrap(text, fam, size, max_w * 72 * 0.94 / factor, 700 if b else 400, it)
            h = len(lines) * size * lh / 72.0
            if (len(lines) <= max_lines and h <= max_h) or size <= minimum:
                return size, len(lines)
            size -= 1

    # ------------------------------------------------------------- primitives
    def new_slide(self, notes=None, bg=None):
        s = self.prs.slides.add_slide(self.layout)
        fill = s.background.fill
        fill.solid()
        fill.fore_color.rgb = rgb(bg or self.tk["page"])
        self.slides.append(s)
        if notes and self.speaker_notes:
            try:
                s.notes_slide.notes_text_frame.text = fmt.clean_text(notes)
            except Exception:
                pass
        return s

    def rect(self, s, x, y, w, h, fill=None, line=None, radius=0.0, line_w=0.75, shape=None, alpha=None):
        if w <= 0 or h <= 0:
            return None
        kind = shape or (MSO_SHAPE.ROUNDED_RECTANGLE if radius > 0.001 else MSO_SHAPE.RECTANGLE)
        sp = s.shapes.add_shape(kind, E(x), E(y), E(w), E(h))
        if kind == MSO_SHAPE.ROUNDED_RECTANGLE:
            try:
                sp.adjustments[0] = max(0.0, min(0.5, radius / max(0.01, min(w, h))))
            except Exception:
                pass
        if fill:
            sp.fill.solid()
            sp.fill.fore_color.rgb = rgb(fill)
            if alpha is not None:
                _set_alpha(sp.fill, alpha)
        else:
            sp.fill.background()
        if line:
            sp.line.color.rgb = rgb(line)
            sp.line.width = Pt(line_w)
        else:
            sp.line.fill.background()
        sp.shadow.inherit = False
        tf = sp.text_frame
        tf.text = ""
        return sp

    def oval(self, s, cx, cy, r, fill, line=None, line_w=1.5):
        sp = s.shapes.add_shape(MSO_SHAPE.OVAL, E(cx - r), E(cy - r), E(2 * r), E(2 * r))
        sp.fill.solid()
        sp.fill.fore_color.rgb = rgb(fill)
        if line:
            sp.line.color.rgb = rgb(line)
            sp.line.width = Pt(line_w)
        else:
            sp.line.fill.background()
        sp.shadow.inherit = False
        return sp

    def line(self, s, x1, y1, x2, y2, color, width=0.75, dash=False):
        c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, E(x1), E(y1), E(x2), E(y2))
        c.line.color.rgb = rgb(color)
        c.line.width = Pt(width)
        if dash:
            c.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        return c

    def text(self, s, x, y, w, h, content, role="body", size=13, color=None, bold=None, italic=None,
             align="left", anchor="top", wrap=True, upper=False, tracking=None, lh=None, accent=None):
        """Text box. content: str (with *accent*) or list of paragraphs (str)."""
        tb = s.shapes.add_textbox(E(x), E(y), E(w), E(h))
        tf = tb.text_frame
        tf.word_wrap = wrap
        tf.auto_size = MSO_AUTO_SIZE.NONE
        for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
            setattr(tf, side, 0)
        tf.vertical_anchor = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}[anchor]
        paras = content if isinstance(content, list) else [content]
        for i, ptxt in enumerate(paras):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}[align]
            if lh:
                p.line_spacing = lh
            if i > 0 and len(paras) > 1:
                p.space_before = Pt(size * 0.55)
            ptxt = fmt.clean_text(ptxt if ptxt is not None else "")
            if upper:
                ptxt = ptxt.upper()
            parts = fmt.split_accent(ptxt) if accent is not False else [(ptxt, False)]
            if not parts:
                parts = [("", False)]
            for seg, is_acc in parts:
                r = p.add_run()
                r.text = seg
                fam, b, it = self.font(role, bold, italic)
                r.font.name = fam
                r.font.size = Pt(size)
                r.font.bold = b
                r.font.italic = it
                r.font.color.rgb = rgb(color or self.tk["ink"])
                if tracking:
                    r.font._rPr.set("spc", str(int(tracking)))
                if is_acc:
                    mode = self.ss["accent"] if accent is None else accent
                    if mode == "italic":
                        r.font.italic = True
                        r.font.color.rgb = rgb(self.tk["brand"])
                    elif mode == "color":
                        r.font.color.rgb = rgb(self.tk["brand_ink"])
                    elif mode == "color-bold":
                        r.font.color.rgb = rgb(self.tk["brand_ink"])
                        r.font.bold = True
                    elif mode == "on-brand":
                        r.font.bold = True
        return tb

    def card(self, s, x, y, w, h, kind="panel", fill=None):
        """Panel per theme. kind: panel | soft | plain | brand."""
        r = self.ss["radius"]
        if kind == "soft":
            return self.rect(s, x, y, w, h, fill or self.tk["soft"], None if self.key != "classic" else self.tk["line"], r)
        if kind == "brand":
            return self.rect(s, x, y, w, h, self.tk["brand_fill"], None, r)
        if kind == "plain":
            return None
        return self.rect(s, x, y, w, h, fill or self.tk["panel"], self.tk["line"], r)

    def twotone(self, s, x, y, w, h, top_h):
        """Classic two-tone card: tinted top zone + white bottom zone + hairline."""
        self.rect(s, x, y, w, h, "#FFFFFF", self.tk["line"], 0.0)
        self.rect(s, x + 0.006, y + 0.006, w - 0.012, top_h, self.tk["panel2"], None, 0.0)
        self.line(s, x, y + top_h, x + w, y + top_h, self.tk["line"], 0.75)

    def kicker(self, s, x, y, w, text, color=None, size=None):
        if not text:
            return 0
        if self.ss["kicker_upper"]:
            self.text(s, x, y, w, 0.25, text, "label", size or 9.5, color or self.tk["brand"], upper=True,
                      tracking=180, accent=False)
        else:
            self.text(s, x, y, w, 0.28, fmt.strip_accent(text), "strong", size or 12,
                      color or self.tk["brand_ink"], bold=True, accent=False)
        return 0.32

    # ------------------------------------------------------------- slide frame
    def frame(self, kicker=None, title=None, dek=None, notes=None):
        s = self.new_slide(notes)
        y = 0.46
        if kicker:
            y += self.kicker(s, MX, y, SW - 2 * MX, kicker)
        if title:
            role = "display"
            size, nl = self.fit(fmt.strip_accent(title), role, SW - 2 * MX, 1.3, self.ss["title"],
                                self.ss["title_min"], max_lines=2, bold=self.ss["title_bold"], lh=1.2)
            h = nl * size * 1.2 / 72.0 + 0.06
            self.text(s, MX, y, SW - 2 * MX, h, title, role, size, self.tk["ink"], bold=self.ss["title_bold"], lh=1.0)
            y += h + 0.04
        if dek:
            self.text(s, MX, y, 9.6, 0.4, dek, "body", 12.5, self.tk["ink2"], accent=False)
            y += 0.36
        return s, max(y + 0.2, 1.5)

    def footer(self, s, n, total):
        c = self.tk["ink3"]
        left = self.report_name + ((", " + self.company) if self.company and self.company not in self.report_name else "")
        self.text(s, MX, FOOT_Y, 8.0, 0.25, left, "label", 9, c, accent=False)
        self.text(s, SW - MX - 2.0, FOOT_Y, 2.0, 0.25, "%d / %d" % (n, total), "label", 9, c, align="right",
                  accent=False)

    # ------------------------------------------------------------------ logo
    def logo_bytes(self):
        """PNG/JPEG bytes for the brand logo (uploaded base64 or a reachable URL), else None."""
        if hasattr(self, "_logo_cache"):
            return self._logo_cache
        self._logo_cache = None
        logo = (self.meta.get("brand_profile") or {}).get("logo") or {}
        data = None
        try:
            if logo.get("type") == "upload" and logo.get("value"):
                import base64
                data = base64.b64decode(logo["value"])
            elif logo.get("type") == "url" and str(logo.get("value", "")).startswith("http"):
                import urllib.request
                req = urllib.request.Request(logo["value"], headers={"User-Agent": "Mozilla/5.0"})
                data = urllib.request.urlopen(req, timeout=4).read()
        except Exception:
            data = None
        if data and (data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff"):
            self._logo_cache = data
        return self._logo_cache

    def logo(self, s, x, y, max_w, max_h, text_color, text_size=14, badge=False):
        """Place the logo image (on a light badge when asked), or the company name as text."""
        data = self.logo_bytes()
        if not data:
            self.text(s, x, y, 7, 0.32, self.company, "display", text_size, text_color, bold=True, accent=False)
            return
        import io
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(data))
            ar = im.size[0] / float(im.size[1] or 1)
        except Exception:
            ar = 3.0
        h = max_h
        w = h * ar
        if w > max_w:
            w, h = max_w, max_w / ar
        if badge:
            self.rect(s, x - 0.12, y - 0.08, w + 0.24, h + 0.16, "#FFFFFF", None, 0.08)
        s.shapes.add_picture(io.BytesIO(data), E(x), E(y), E(w), E(h))

    # ================================================================ sections
    def cover(self, sec):
        kicker = fmt.clean_text(sec.get("kicker", ""))
        parts = [p.strip() for p in kicker.split("·") if p.strip()]
        self.report_name = parts[0] if parts else fmt.strip_accent(sec.get("title", ""))
        period = sec.get("period") or (" ".join(parts[1:]) if len(parts) > 1 else "")
        title = sec.get("title", "")
        dek = sec.get("subtitle") or sec.get("dek")
        bits = [b for b in (sec.get("meta_bits") or []) if b]
        sources = sec.get("sources") or self.meta.get("sources") or []
        notes = "%s. %s" % (fmt.strip_accent(title), dek or "")
        k = self.key
        if k == "studio":
            s = self.new_slide(notes)
            px, py, pw, ph = 0.36, 0.36, SW - 0.72, SH - 0.72
            self.rect(s, px, py, pw, ph, self.tk["brand_fill"], None, 0.34)
            on, on2 = self.tk["on_brand"], self.tk.get("on_brand_2", self.tk["on_brand"])
            x = px + 0.62
            self.logo(s, x, py + 0.42, 3.2, 0.42, on, 14, badge=True)
            cx = x
            for i, chip in enumerate([self.report_name, period]):
                if not chip:
                    continue
                w = self.measure(chip, "label", 11) + 0.36
                if i == 0:
                    self.rect(s, cx, py + 1.02, w, 0.34, COL.mix(self.tk["brand_fill"], on, 0.16), None, 0.17)
                else:
                    self.rect(s, cx, py + 1.02, w, 0.34, None, COL.mix(self.tk["brand_fill"], on, 0.4), 0.17)
                self.text(s, cx, py + 1.02, w, 0.34, chip, "label", 11, on, align="center", anchor="middle",
                          accent=False)
                cx += w + 0.12
            size, nl = self.fit(fmt.strip_accent(title), "display", 9.2, 2.6, 50, 30, max_lines=3, lh=1.22)
            th = nl * size * 1.22 / 72 + 0.12
            self.text(s, x, py + 1.65, 9.4, th, title, "display", size, on, lh=0.98, accent="on-brand")
            y = py + 1.65 + th + 0.12
            if dek:
                self.text(s, x, y, 8.6, 1.0, dek, "body", 15, on2, accent=False, lh=1.15)
            yb = py + ph - 1.15
            fx = x
            facts = []
            if self.meta.get("prepared_for"):
                facts.append(("Prepared for", self.meta["prepared_for"]))
            if self.meta.get("prepared_by"):
                facts.append(("Prepared by", self.meta["prepared_by"]))
            for lab, val in facts:
                self.text(s, fx, yb, 2.6, 0.22, lab, "label", 9.5, on2, accent=False)
                self.text(s, fx, yb + 0.22, 2.6, 0.28, val, "strong", 12, on, bold=True, accent=False)
                fx += 2.5
            self._source_chips(s, fx if facts else x, yb + 0.05, sources, on, COL.mix(self.tk["brand_fill"], on, 0.12),
                               COL.mix(self.tk["brand_fill"], on, 0.3), max_x=px + pw - 0.5, bits=bits if not sources else None)
            return
        s = self.new_slide(notes)
        if k == "boardroom":
            _bg_gradient(s, COL.mix(self.tk["page"], self.tk["brand"], 0.34), self.tk["page"])
            self.logo(s, MX, 0.48, 3.2, 0.42, self.tk["ink"], 14, badge=True)
            y = 2.0
            self.text(s, MX, y, 9, 0.3, self.report_name, "strong", 14, self.tk["brand_ink"], bold=True, accent=False)
            if period:
                w = self.measure(self.report_name, "strong", 14, bold=True)
                self.text(s, MX + w + 0.25, y, 5, 0.3, period, "body", 14, self.tk["ink2"], accent=False)
            size, nl = self.fit(fmt.strip_accent(title), "display", 10.5, 2.5, 54, 32, max_lines=3, bold=True, lh=1.18)
            th = nl * size * 1.18 / 72 + 0.12
            self.text(s, MX, y + 0.45, 11, th, title, "display", size, self.tk["ink"], bold=True, lh=0.95)
            y2 = y + 0.45 + th + 0.15
            if dek:
                self.text(s, MX, y2, 9.4, 0.9, dek, "body", 16, self.tk["ink2"], accent=False, lh=1.15)
            self._source_chips(s, MX, 6.35, sources, self.tk["ink"], self.tk["panel"], self.tk["line"],
                               max_x=SW - MX, bits=bits if not sources else None, detail_color=self.tk["ink3"])
            return
        if k == "ledger":
            self.rect(s, 0, 0, SW, 0.09, self.tk["brand"], None)
            self.logo(s, MX, 0.4, 3.2, 0.4, self.tk["ink"], 13)
            y = 1.7
            self.text(s, MX, y, 9, 0.3, self.report_name, "label", 13, self.tk["brand_ink"], bold=True, accent=False)
            if period:
                w = self.measure(self.report_name, "label", 13, bold=True)
                self.text(s, MX + w + 0.22, y, 5, 0.3, period, "label", 13, self.tk["ink2"], accent=False)
            size, nl = self.fit(fmt.strip_accent(title), "display", 11.4, 2.2, 40, 26, max_lines=3, bold=True, lh=1.2)
            th = nl * size * 1.2 / 72 + 0.12
            self.text(s, MX, y + 0.42, 11.8, th, title, "display", size, self.tk["ink"], bold=True, lh=1.02)
            y2 = y + 0.42 + th + 0.12
            if dek:
                self.text(s, MX, y2, 10.5, 0.8, dek, "body", 14, self.tk["ink2"], accent=False, lh=1.15)
            self.line(s, MX, 5.9, SW - MX, 5.9, self.tk["line"], 0.75)
            self._facts_row(s, MX, 6.08, bits, self.tk["ink2"])
            self._source_chips(s, MX, 6.5, sources, self.tk["ink"], self.tk["panel"], self.tk["line"], max_x=SW - MX,
                               detail_color=self.tk["ink3"], radius=0.04)
            return
        # classic
        if self.logo_bytes():
            self.logo(s, MX, 0.48, 3.2, 0.42, self.tk["ink"])
        else:
            self.text(s, MX, 0.5, 6, 0.4, self.company, "display", 22, self.tk["ink"], accent=False)
        self.line(s, MX, 1.08, SW - MX, 1.08, self.tk["line"], 0.75)
        y = 2.05
        self.text(s, MX, y, 11, 0.3, kicker, "label", 10.5, self.tk["brand"], upper=True, tracking=150, accent=False)
        size, nl = self.fit(fmt.strip_accent(title), "display", 11.4, 2.4, 50, 32, max_lines=3, lh=1.2)
        th = nl * size * 1.2 / 72 + 0.12
        self.text(s, MX, y + 0.42, 11.8, th, title, "display", size, self.tk["ink"], lh=1.0)
        y2 = y + 0.42 + th + 0.1
        if dek:
            self.text(s, MX, y2, 10.4, 0.8, dek, "body", 15, self.tk["ink2"], accent=False)
            y2 += 0.7
        if bits:
            self.text(s, MX, y2 + 0.1, 11.5, 0.35, "  ·  ".join(bits), "body", 13, self.tk["ink2"], accent=False)
        if sources:
            self._source_chips(s, MX, 6.35, sources, self.tk["ink"], "#FFFFFF", self.tk["line"], max_x=SW - MX,
                               detail_color=self.tk["ink2"], radius=0.03)

    def _facts_row(self, s, x, y, bits, color):
        for b in bits or []:
            w = self.measure(b, "body", 12) + 0.4
            self.text(s, x, y, w, 0.3, b, "body", 12, color, accent=False)
            x += w

    def _source_chips(self, s, x, y, sources, text_color, fill, line, max_x, bits=None, detail_color=None,
                      radius=0.15):
        items = []
        for src in sources or []:
            if isinstance(src, str):
                src = {"name": src}
            items.append((src.get("name", ""), src.get("detail", "")))
        if not items and bits:
            items = [(b, "") for b in bits]
        cx, cy = x, y
        from .html_render import PLATFORM_COLORS
        for name, detail in items:
            w = self.measure(name, "strong", 10.5, bold=True) + (self.measure(detail, "body", 10.5) + 0.12 if detail else 0) + 0.55
            if cx + w > max_x:
                cx, cy = x, cy + 0.4
            self.rect(s, cx, cy, w, 0.32, fill, line, min(radius, 0.16))
            dot = PLATFORM_COLORS.get(name.lower(), self.tk["brand"])
            self.oval(s, cx + 0.17, cy + 0.16, 0.045, dot)
            self.text(s, cx + 0.3, cy, w - 0.3, 0.32, name, "strong", 10.5, text_color, bold=True, anchor="middle",
                      accent=False)
            if detail:
                nw = self.measure(name, "strong", 10.5, bold=True)
                self.text(s, cx + 0.3 + nw + 0.1, cy, w, 0.32, detail, "body", 10.5, detail_color or text_color,
                          anchor="middle", accent=False)
            cx += w + 0.1

    # ----------------------------------------------------------------- KPIs
    def kpis(self, sec, insight=None):
        stats = sec.get("stats") or []
        title = (insight or {}).get("title") or "The numbers that matter."
        kick = (insight or {}).get("kicker") or "At a glance"
        notes = " ".join("%s: %s%s." % (x.get("label"), x.get("value"),
                                         (" (%s %s)" % (x.get("delta_label"), "vs " + self.compare)) if x.get("delta_label") else "")
                         for x in stats)
        if insight:
            notes += " " + " ".join(insight.get("body") or [])
        s, top = self.frame(kick, title, notes=notes)
        n = max(1, len(stats))
        gap = 0.18
        cols = n if n <= 4 else 3
        rows = 1 if n <= 4 else 2
        w = (SW - 2 * MX - gap * (cols - 1)) / cols
        body = (insight or {}).get("body") or []
        avail = 6.85 - top - (1.15 if body else 0)
        h = min(2.6, (avail - gap * (rows - 1)) / rows)
        for i, st in enumerate(stats):
            r, c = divmod(i, cols)
            self._kpi_card(s, MX + c * (w + gap), top + r * (h + gap), w, h, st, small=n > 4)
        if body:
            by = top + rows * h + (rows - 1) * gap + 0.3
            self.text(s, MX, by, SW - 2 * MX, 0.9, body[:2], "body", self.ss["body"] + 1, self.tk["ink2"],
                      accent=False, lh=1.15)

    def _kpi_card(self, s, x, y, w, h, st, small=False):
        k = self.key
        label = st.get("label", "")
        value = str(st.get("value", ""))
        pad = 0.22 if k != "ledger" else 0.18
        if k == "classic":
            top_h = h * 0.62
            self.twotone(s, x, y, w, h, top_h)
            size = self.fit_value(value, w - 2 * pad, self.ss["kpi"] * (0.8 if small else 1.0))
            self.text(s, x + pad, y + 0.15, w - 2 * pad, top_h - 0.2, value, "numeral", size, self.tk["ink"],
                      anchor="bottom", accent=False)
            self.text(s, x + pad, y + top_h + 0.08, w - 2 * pad - 0.9, h - top_h - 0.12, label, "label", 8.5,
                      self.tk["brand"], upper=True, tracking=160, anchor="middle", accent=False)
            d = self._delta_text(st, plain=False)
            if d:
                self.text(s, x + w - pad - 1.2, y + top_h + 0.08, 1.2, h - top_h - 0.12, d[0], "label", 8.5, d[1],
                          align="right", anchor="middle", accent=False)
            return
        if k == "boardroom" and st.get("emphasis"):
            self.rect(s, x, y, w, h, COL.mix(self.tk["panel"], self.tk["brand"], 0.22), self.tk["brand_ink"],
                      self.ss["radius"], 0.75)
        else:
            self.card(s, x, y, w, h)
        self.text(s, x + pad, y + pad - 0.02, w - 2 * pad, 0.3, label, "strong" if k != "ledger" else "label",
                  11.5 if k != "ledger" else 11, self.tk["ink2"], bold=False, accent=False)
        if st.get("source") and not small and w > 2.6:
            self.text(s, x + w - pad - 1.4, y + pad, 1.4, 0.26, st["source"], "label", 8.5, self.tk["ink3"],
                      align="right", accent=False)
        vsize = self.fit_value(value, w - 2 * pad, self.ss["kpi"] * (0.82 if small else 1.0))
        vy = y + pad + 0.32
        self.text(s, x + pad, vy, w - 2 * pad, vsize / 72.0 * 1.15, value, "numeral", vsize, self.tk["ink"],
                  accent=False)
        dy = vy + vsize / 72.0 * 1.12 + 0.04
        d = self._delta_text(st, plain=(k == "studio"))
        if d:
            if k == "studio":
                tw = min(w - 2 * pad, self.measure(d[0], "strong", 10, bold=True) + 0.32)
                self.rect(s, x + pad, dy, tw, 0.3, d[2], None, 0.15)
                self.text(s, x + pad + 0.12, dy, tw - 0.16, 0.3, d[0], "strong", 10, d[1], bold=True,
                          anchor="middle", accent=False)
            else:
                self.text(s, x + pad, dy, w - 2 * pad, 0.28, d[0], "label", 10.5, d[1], accent=False)
            dy += 0.34
        spark = st.get("spark")
        if spark and h - (dy - y) > 0.5:
            sh = min(0.55, h - (dy - y) - pad)
            col = self.tk["brand_ink"] if self.tk.get("dark") else self.tk["series"][0]
            self.sparkline(s, x + pad, y + h - pad - sh, w - 2 * pad, sh, spark, col)

    def fit_value(self, value, max_w, start):
        size = start
        while size > 12 and self.measure(value, "numeral", size) > max_w * 0.96:
            size -= 1
        return size

    def _delta_text(self, st, plain=False):
        lab, d = st.get("delta_label"), st.get("delta_direction") or "flat"
        if not lab and d == "flat":
            return None
        good = st.get("good", "up")
        tone = "flat" if d == "flat" or good == "neutral" else ("good" if d == good else "bad")
        col = {"good": self.tk["good"], "bad": self.tk["bad"]}.get(tone, self.tk["ink3"])
        soft = {"good": self.tk["good_soft"], "bad": self.tk["bad_soft"]}.get(tone, self.tk["panel2"])
        vs = st.get("compare") or self.compare
        if plain:
            arrow = {"up": "↑ ", "down": "↓ "}.get(d, "→ ")
            return arrow + fmt.plain_delta(lab, d, vs), col, soft
        arrow = {"up": "▲ ", "down": "▼ "}.get(d, "")
        if d == "flat":
            return "Flat vs %s" % vs, col, soft
        if self.key == "classic":
            return arrow + lab, col, soft
        return "%s%s  vs %s" % (arrow, lab, vs), col, soft

    # ----------------------------------------------------------- sparkline
    def sparkline(self, s, x, y, w, h, values, color, fill=True):
        vals = [fmt.to_num(v) for v in values or []]
        vals = [v for v in vals if v is not None]
        if len(vals) < 2:
            return
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        n = len(vals)
        pts = [(x + w * i / (n - 1), y + h * (1 - (v - lo) / span)) for i, v in enumerate(vals)]
        if fill:
            area = pts + [(x + w, y + h), (x, y + h)]
            self.poly(s, area, fill=color, alpha=0.13, closed=True)
        self.poly(s, pts, line=color, width=1.75)
        ex, ey = pts[-1]
        self.oval(s, ex, ey, 0.045, color, self.tk["panel"], 1.0)

    def poly(self, s, pts, fill=None, line=None, width=1.5, alpha=None, closed=False, dash=False):
        if len(pts) < 2:
            return None
        scale = 10000.0
        fb = s.shapes.build_freeform(int(pts[0][0] * scale), int(pts[0][1] * scale), scale=IN / scale)
        fb.add_line_segments([(int(px * scale), int(py * scale)) for px, py in pts[1:]], close=closed)
        sp = fb.convert_to_shape()
        if fill:
            sp.fill.solid()
            sp.fill.fore_color.rgb = rgb(fill)
            if alpha is not None:
                _set_alpha(sp.fill, alpha)
        else:
            sp.fill.background()
        if line:
            sp.line.color.rgb = rgb(line)
            sp.line.width = Pt(width)
            if dash:
                sp.line.dash_style = MSO_LINE_DASH_STYLE.DASH
            _round_joins(sp)
        else:
            sp.line.fill.background()
        sp.shadow.inherit = False
        return sp

    # ------------------------------------------------------- slide builders
    def chart_slide(self, sec, header=None, with_insight=False):
        chart = sec.get("chart") or {}
        kick, title, dek, sub = self._titles(sec, header, with_insight)
        notes = " ".join([fmt.strip_accent(sec.get("insight_title", "")), " ".join(sec.get("insight_body") or []),
                          sec.get("caption") or ""]).strip()
        s, top = self.frame(kick, title, dek, notes)
        bottom = 6.82
        if with_insight:
            cw = 7.75
            self.card(s, MX, top, cw, bottom - top)
            self.chart_area(s, chart, MX, top, cw, bottom - top, sub, sec.get("caption"))
            self.insight_panel(s, MX + cw + 0.2, top, SW - 2 * MX - cw - 0.2, bottom - top, sec,
                               show_title=bool(header) or bool(sec.get("chart_title")))
        else:
            self.card(s, MX, top, SW - 2 * MX, bottom - top)
            self.chart_area(s, chart, MX, top, SW - 2 * MX, bottom - top, sub, sec.get("caption"))

    def _titles(self, sec, header, with_insight):
        """Slide (kicker, title, dek, subtitle-inside-card)."""
        sub = sec.get("chart_title") or sec.get("title")
        if header:
            return header.get("kicker"), header.get("title"), header.get("dek"), sub
        if sec.get("chart_title") or sec.get("title"):
            return sec.get("insight_kicker") if not with_insight else None, sec.get("chart_title") or sec.get("title"), None, None
        if with_insight and sec.get("insight_title"):
            return sec.get("insight_kicker"), sec.get("insight_title"), None, None
        return None, sec.get("caption") or "", None, None

    def insight_panel(self, s, x, y, w, h, sec, show_title=True, kicker_key="insight_kicker",
                      title_key="insight_title", body_key="insight_body"):
        k = self.key
        pad = 0.28
        if k == "classic":
            top_h = min(1.45, h * 0.38)
            self.twotone(s, x, y, w, h, top_h)
        elif k == "studio":
            self.card(s, x, y, w, h, "soft")
        elif k == "boardroom":
            self.rect(s, x, y, w, h, self.tk["panel2"], self.tk["line"], self.ss["radius"])
        else:
            self.rect(s, x, y, w, h, self.tk["panel2"], self.tk["line"], self.ss["radius"])
        cy = y + pad
        kick = sec.get(kicker_key)
        if kick:
            cy += self.kicker(s, x + pad, cy, w - 2 * pad, kick, size=10.5 if k != "classic" else 8.5)
        title = sec.get(title_key)
        if title and show_title:
            size, nl = self.fit(fmt.strip_accent(title), "display", w - 2 * pad, 1.6, 20, 14, max_lines=4,
                                bold=self.ss["title_bold"])
            th = nl * size * 1.18 / 72 + 0.05
            self.text(s, x + pad, cy, w - 2 * pad, th, title, "display", size, self.tk["ink"],
                      bold=self.ss["title_bold"], lh=1.05)
            cy += th + 0.12
        if k == "classic":
            cy = max(cy, y + min(1.45, h * 0.38) + 0.2)
        body = sec.get(body_key) or []
        if isinstance(body, str):
            body = [body]
        if body:
            bs = self.ss["body"]
            fam, _, _ = self.font("body")
            while bs > 10:
                lines = sum(len(_wrap(b, fam, bs, (w - 2 * pad) * 72 * 0.93 / FALLBACK_WIDTH.get(fam, 1.0))) for b in body)
                if lines * bs * 1.3 / 72 + len(body) * bs * 0.55 / 72 <= (y + h - pad - cy):
                    break
                bs -= 0.5
            self.text(s, x + pad, cy, w - 2 * pad, y + h - pad - cy, body, "body", bs, self.tk["ink2"],
                      accent=False, lh=1.18)

    # -------------------------------------------------------- chart areas
    def chart_area(self, s, chart, x, y, w, h, subtitle=None, caption=None):
        pad = 0.25
        cy = y + pad
        if subtitle:
            self.text(s, x + pad, cy, w - 2 * pad, 0.32, subtitle, "display", 14, self.tk["ink"],
                      bold=self.ss["title_bold"])
            cy += 0.42
        cap_h = 0.3 if caption else 0.0
        ch_h = y + h - pad - cap_h - cy
        t = chart.get("type", "bar-vertical")
        cx, cw = x + pad, w - 2 * pad
        if t == "bar-horizontal":
            self.bar_list(s, chart, cx, cy, cw, ch_h)
        elif t in ("doughnut", "donut", "pie"):
            self.donut(s, chart, cx, cy, cw, ch_h)
        elif t in ("line-multi", "line", "area"):
            if chart.get("band") or chart.get("forecast_start") is not None:
                self.line_shapes(s, chart, cx, cy, cw, ch_h)
            else:
                self.native_line(s, chart, cx, cy, cw, ch_h)
        elif t in ("bar-vertical", "bar-stacked", "bar-grouped"):
            self.native_columns(s, chart, cx, cy, cw, ch_h)
        elif t == "waterfall":
            self.native_waterfall(s, chart, cx, cy, cw, ch_h)
        elif t == "bar-diverging":
            self.native_diverging(s, chart, cx, cy, cw, ch_h)
        elif t == "scatter":
            self.scatter(s, chart, cx, cy, cw, ch_h)
        elif t == "sankey":
            self.sankey(s, chart, cx, cy, cw, ch_h)
        elif t == "heatmap":
            self.heatmap(s, chart, cx, cy, cw, ch_h)
        else:
            self.native_columns(s, chart, cx, cy, cw, ch_h)
        if caption:
            self.text(s, x + pad, y + h - pad - 0.24, w - 2 * pad, 0.26, caption, "body", 10, self.tk["ink3"],
                      accent=False, align="center" if self.key == "classic" else "left")

    # bar list (horizontal bars as shapes, mirrors the HTML)
    def bar_list(self, s, chart, x, y, w, h):
        labels = [str(l) for l in chart.get("labels", [])][:12]
        vals = [fmt.to_num(v, 0.0) for v in chart.get("values", [])][:12]
        if not labels:
            return
        unit = chart.get("unit")
        total = chart.get("total") or sum(vals) or 1
        show_share = chart.get("show_share", unit != "%")
        vmax = max(vals) or 1
        n = len(labels)
        row_h = min(0.5, h / n)
        bar_h = min(0.2, row_h * 0.45)
        lab_w = min(w * 0.3, max(self.measure(l, "body", 12) for l in labels) + 0.2)
        val_w = 1.25 if show_share else 0.8
        bx, bw = x + lab_w, w - lab_w - val_w
        hl = chart.get("highlight")
        for i, (lab, v) in enumerate(zip(labels, vals)):
            cy = y + i * row_h + row_h / 2
            self.text(s, x, cy - 0.15, lab_w - 0.1, 0.3, fmt.strip_accent(lab), "body", 12, self.tk["ink"],
                      anchor="middle", accent=False, bold=(hl is not None and (hl == i or hl == lab)))
            if self.key != "classic":
                self.rect(s, bx, cy - bar_h / 2, bw, bar_h, self.tk["track"], None, bar_h / 2 if self.key == "studio" else 0.02)
            col = self.tk["series"][0]
            if hl is not None and not (hl == i or hl == lab):
                col = self.tk["neutral"]
            bwid = max(0.02, bw * v / vmax)
            self.rect(s, bx, cy - bar_h / 2, bwid, bar_h, col, None,
                      bar_h / 2 if self.key == "studio" else (0.02 if self.key != "classic" else 0))
            vtxt = fmt_value(v, unit)
            self.text(s, bx + bw + 0.12, cy - 0.15, 0.7, 0.3, vtxt, "strong", 12, self.tk["ink"], bold=True,
                      anchor="middle", accent=False)
            if show_share:
                self.text(s, bx + bw + 0.12 + self.measure(vtxt, "strong", 12, bold=True) + 0.1, cy - 0.15, 0.6, 0.3,
                          fmt.pct(100.0 * v / total), "body", 10, self.tk["ink3"], anchor="middle", accent=False)

    # donut: native doughnut + shape legend
    def donut(self, s, chart, x, y, w, h):
        labels = [str(l) for l in chart.get("labels", [])]
        vals = [fmt.to_num(v, 0.0) for v in chart.get("values", [])]
        pairs = [(l, v) for l, v in zip(labels, vals) if v > 0]
        if not pairs:
            return
        maxs = min(6, len(self.tk["series"]))
        if len(pairs) > maxs:
            pairs = pairs[:maxs - 1] + [("Other", sum(v for _, v in pairs[maxs - 1:]))]
        total = sum(v for _, v in pairs) or 1
        d = min(h, w * 0.45, 3.4)
        cd = CategoryChartData()
        cd.categories = [p[0] for p in pairs]
        cd.add_series("Share", [p[1] for p in pairs])
        gf = s.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT, E(x), E(y + (h - d) / 2), E(d), E(d), cd)
        ch = gf.chart
        ch.has_legend = False
        ch.has_title = False
        _chart_bg_none(ch)
        _hole(ch, 62)
        ser = ch.plots[0].series[0]
        for i, (lab, _) in enumerate(pairs):
            pt = ser.points[i]
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = rgb(self.tk["neutral"] if lab == "Other" else self.tk["series"][i])
            pt.format.line.color.rgb = rgb(self.tk["panel"])
            pt.format.line.width = Pt(1.5)
        lx = x + d + 0.45
        lw = min(4.2, x + w - lx)
        n = len(pairs)
        rh = min(0.42, h / max(1, n))
        ly = y + (h - rh * n) / 2
        unit = chart.get("unit")
        for i, (lab, v) in enumerate(pairs):
            cy = ly + i * rh + rh / 2
            col = self.tk["neutral"] if lab == "Other" else self.tk["series"][i]
            self.rect(s, lx, cy - 0.07, 0.14, 0.14, col, None, 0.03)
            self.text(s, lx + 0.26, cy - 0.15, lw - 1.5, 0.3, lab, "body", 12, self.tk["ink"], anchor="middle",
                      accent=False)
            val = fmt.pct(100.0 * v / total) if unit in ("%", None) else fmt_value(v, unit)
            if unit is None:
                val = fmt.compact(v)
            self.text(s, lx + lw - 1.25, cy - 0.15, 0.75, 0.3, val, "strong", 12, self.tk["ink"], bold=True,
                      align="right", anchor="middle", accent=False)
            if unit != "%":
                self.text(s, lx + lw - 0.48, cy - 0.15, 0.48, 0.3, fmt.pct(100.0 * v / total), "body", 10,
                          self.tk["ink3"], align="right", anchor="middle", accent=False)

    # native column charts
    def native_columns(self, s, chart, x, y, w, h):
        labels = [str(l) for l in chart.get("labels", [])]
        t = chart.get("type")
        cd = CategoryChartData()
        cd.categories = labels
        if chart.get("stacks"):
            series = chart["stacks"]
            kind = XL_CHART_TYPE.COLUMN_STACKED
        elif chart.get("groups"):
            series = chart["groups"]
            kind = XL_CHART_TYPE.COLUMN_CLUSTERED
        else:
            series = [{"label": chart.get("series_label") or "Value", "values": chart.get("values", [])}]
            kind = XL_CHART_TYPE.COLUMN_CLUSTERED
        for sr in series:
            cd.add_series(sr.get("label", ""), [fmt.to_num(v, 0.0) for v in sr.get("values", [])])
        gf = s.shapes.add_chart(kind, E(x), E(y), E(w), E(h), cd)
        ch = gf.chart
        self._style_axes(ch, chart.get("unit"))
        plot = ch.plots[0]
        plot.gap_width = 70 if len(series) > 1 else 90
        if kind == XL_CHART_TYPE.COLUMN_STACKED:
            plot.overlap = 100
        elif len(series) > 1:
            plot.overlap = -8
        hl = chart.get("highlight")
        for i, ser in enumerate(plot.series):
            ser.format.fill.solid()
            ser.format.fill.fore_color.rgb = rgb(self.tk["series"][i % len(self.tk["series"])])
            ser.format.line.fill.background()
            ser.invert_if_negative = False
            if hl is not None and len(series) == 1:
                for j, lab in enumerate(labels):
                    if not (hl == j or hl == lab):
                        pt = ser.points[j]
                        pt.format.fill.solid()
                        pt.format.fill.fore_color.rgb = rgb(self.tk["neutral"])
        if len(series) == 1 and chart.get("show_values", len(labels) <= 14):
            plot.has_data_labels = True
            dl = plot.data_labels
            self._font(dl.font, "label", 10, self.tk["ink2"])
            dl.number_format = _numfmt(chart.get("unit"))
            dl.number_format_is_linked = False
            dl.position = XL_LABEL_POSITION.OUTSIDE_END
        if len(series) > 1:
            ch.has_legend = True
            ch.legend.position = XL_LEGEND_POSITION.BOTTOM
            ch.legend.include_in_layout = False
            self._font(ch.legend.font, "body", 10.5, self.tk["ink2"])
        else:
            ch.has_legend = False

    def native_line(self, s, chart, x, y, w, h):
        labels = [str(l) for l in chart.get("labels", [])]
        if chart.get("series"):
            series = chart["series"]
        else:
            series = [{"label": chart.get("series_label") or "Value", "values": chart.get("values", [])}]
        cd = CategoryChartData()
        cd.categories = labels
        for sr in series:
            cd.add_series(sr.get("label", ""), [fmt.to_num(v) if v is not None else None for v in sr.get("values", [])])
        filled = chart.get("type") == "area" and len(series) == 1
        gf = s.shapes.add_chart(XL_CHART_TYPE.AREA if filled else XL_CHART_TYPE.LINE, E(x), E(y), E(w), E(h), cd)
        ch = gf.chart
        self._style_axes(ch, chart.get("unit"), line=True, n_labels=len(labels))
        plot = ch.plots[0]
        for i, ser in enumerate(plot.series):
            col = self.tk["series"][i % len(self.tk["series"])]
            if filled:
                ser.format.fill.solid()
                ser.format.fill.fore_color.rgb = rgb(col)
                _set_alpha(ser.format.fill, 0.14)
                ser.format.line.color.rgb = rgb(col)
                ser.format.line.width = Pt(2)
            else:
                ser.format.line.color.rgb = rgb(col)
                ser.format.line.width = Pt(2.25)
                ser.smooth = False
                ser.marker.style = XL_MARKER_STYLE.NONE
                if series[i].get("style") == "dashed":
                    ser.format.line.dash_style = MSO_LINE_DASH_STYLE.DASH
            vals = series[i].get("values", [])
            last = max([j for j, v in enumerate(vals) if v is not None] or [0])
            if not filled:
                pt = ser.points[last]
                pt.marker.style = XL_MARKER_STYLE.CIRCLE
                pt.marker.size = 7
                pt.marker.format.fill.solid()
                pt.marker.format.fill.fore_color.rgb = rgb(col)
                pt.marker.format.line.color.rgb = rgb(self.tk["panel"])
            if len(series) == 1 and vals:
                pt = ser.points[last]
                pt.data_label.has_text_frame = True
                pt.data_label.text_frame.text = fmt_value(fmt.to_num(vals[last], 0), chart.get("unit"))
                pt.data_label.position = XL_LABEL_POSITION.ABOVE
                r = pt.data_label.text_frame.paragraphs[0].runs[0]
                self._font(r.font, "strong", 10.5, self.tk["ink"], bold=True)
        if len(series) > 1:
            ch.has_legend = True
            ch.legend.position = XL_LEGEND_POSITION.BOTTOM
            ch.legend.include_in_layout = False
            self._font(ch.legend.font, "body", 10.5, self.tk["ink2"])
        else:
            ch.has_legend = False

    def native_waterfall(self, s, chart, x, y, w, h):
        steps = chart.get("steps") or []
        labels, base, up, down, total = [], [], [], [], []
        running = 0.0
        for st in steps:
            v = fmt.to_num(st.get("value"), 0.0)
            kind = st.get("kind", "delta")
            labels.append(st.get("label", ""))
            if kind in ("start", "total"):
                running = v
                base.append(0)
                total.append(v)
                up.append(0)
                down.append(0)
            else:
                if v >= 0:
                    base.append(running)
                    up.append(v)
                    down.append(0)
                else:
                    base.append(running + v)
                    down.append(-v)
                    up.append(0)
                total.append(0)
                running += v
        cd = CategoryChartData()
        cd.categories = labels
        cd.add_series("base", base)
        cd.add_series("Total", total)
        cd.add_series("Increase", up)
        cd.add_series("Decrease", down)
        gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_STACKED, E(x), E(y), E(w), E(h), cd)
        ch = gf.chart
        self._style_axes(ch, chart.get("unit"))
        plot = ch.plots[0]
        plot.gap_width = 55
        plot.overlap = 100
        cols = [None, self.tk["series"][0], self.tk["good"], self.tk["bad"]]
        for i, ser in enumerate(plot.series):
            if i == 0:
                ser.format.fill.background()
                ser.format.line.fill.background()
                continue
            ser.format.fill.solid()
            ser.format.fill.fore_color.rgb = rgb(cols[i])
            ser.format.line.fill.background()
            ser.invert_if_negative = False
            vals = [total, up, down][i - 1]
            for j, v in enumerate(vals):
                if v:
                    pt = ser.points[j]
                    pt.data_label.has_text_frame = True
                    sign = "" if i == 1 else ("+" if i == 2 else "−")
                    pt.data_label.text_frame.text = sign + fmt_value(v, chart.get("unit"))
                    pt.data_label.position = XL_LABEL_POSITION.INSIDE_END if i == 1 else XL_LABEL_POSITION.CENTER
                    r = pt.data_label.text_frame.paragraphs[0].runs[0]
                    self._font(r.font, "strong", 10, COL.readable_on(cols[i]), bold=True)
        ch.has_legend = False

    def native_diverging(self, s, chart, x, y, w, h):
        labels = [str(l) for l in chart.get("labels", [])]
        vals = [fmt.to_num(v, 0.0) for v in chart.get("values", [])]
        cd = CategoryChartData()
        cd.categories = list(reversed(labels))
        cd.add_series("Change", list(reversed(vals)))
        gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, E(x), E(y), E(w), E(h), cd)
        ch = gf.chart
        self._style_axes(ch, chart.get("unit"), horizontal=True)
        ch.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW
        plot = ch.plots[0]
        plot.gap_width = 60
        good_up = chart.get("good", "up") == "up"
        ser = plot.series[0]
        ser.invert_if_negative = False
        for j, v in enumerate(reversed(vals)):
            pt = ser.points[j]
            ok = (v >= 0) == good_up
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = rgb(self.tk["series"][0] if ok else self.tk["bad"])
        plot.has_data_labels = True
        dl = plot.data_labels
        self._font(dl.font, "label", 10, self.tk["ink2"])
        dl.number_format = _numfmt(chart.get("unit"), signed=True)
        dl.number_format_is_linked = False
        dl.position = XL_LABEL_POSITION.OUTSIDE_END
        ch.has_legend = False

    def _font(self, font, role, size, color, bold=None):
        fam, b, it = self.font(role, bold)
        font.name = fam
        font.size = Pt(size)
        font.bold = b
        font.italic = False if role != "numeral" else it
        font.color.rgb = rgb(color)

    def _style_axes(self, ch, unit, line=False, horizontal=False, n_labels=0):
        _chart_bg_none(ch)
        ch.has_title = False
        self._font(ch.font, "label", 10.5, self.tk["chart_text"])
        va, ca = ch.value_axis, ch.category_axis
        va.has_major_gridlines = True
        va.major_gridlines.format.line.color.rgb = rgb(self.tk["grid"])
        va.major_gridlines.format.line.width = Pt(0.75)
        va.format.line.fill.background()
        va.major_tick_mark = XL_TICK_MARK.NONE
        va.minor_tick_mark = XL_TICK_MARK.NONE
        va.tick_labels.number_format = _numfmt(unit)
        va.tick_labels.number_format_is_linked = False
        self._font(va.tick_labels.font, "label", 10, self.tk["chart_text"])
        ca.format.line.color.rgb = rgb(self.tk["axis"])
        ca.format.line.width = Pt(0.75)
        ca.major_tick_mark = XL_TICK_MARK.NONE
        ca.minor_tick_mark = XL_TICK_MARK.NONE
        ca.has_major_gridlines = False
        self._font(ca.tick_labels.font, "label", 10, self.tk["chart_text"])
        if line and n_labels > 12:
            skip = int(math.ceil(n_labels / 8.0))
            _tick_skip(ca, skip)

    # line chart with band / forecast drawn as shapes (exact match with HTML)
    def line_shapes(self, s, chart, x, y, w, h):
        labels = [str(l) for l in chart.get("labels", [])]
        series = chart.get("series") or [{"label": "", "values": chart.get("values", [])}]
        unit = chart.get("unit")
        band = chart.get("band") or {}
        allv = [fmt.to_num(v) for sr in series for v in sr.get("values", []) if v is not None]
        allv += [fmt.to_num(v) for v in band.get("upper", []) if v is not None]
        vmax = max(allv) if allv else 1
        ticks = fmt.axis_ticks(vmax * 1.1, 0)
        n = len(labels)
        gut = max(self.measure(fmt_value(t, unit), "label", 10) for t in ticks) + 0.15
        right = max([self.measure(sr.get("label", ""), "label", 10) for sr in series] + [0.3]) + 0.3
        px0, px1 = x + gut, x + w - right
        py0, py1 = y + 0.15, y + h - 0.45
        t0, t1 = ticks[0], ticks[-1]

        def X(i):
            return px0 + (px1 - px0) * (i / float(max(1, n - 1)))

        def Y(v):
            return py1 - (py1 - py0) * ((v - t0) / float((t1 - t0) or 1))

        for t in ticks:
            self.line(s, px0, Y(t), px1, Y(t), self.tk["axis"] if t == 0 else self.tk["grid"], 0.75)
            self.text(s, x, Y(t) - 0.1, gut - 0.1, 0.2, fmt_value(t, unit), "label", 10, self.tk["chart_text"],
                      align="right", anchor="middle", accent=False)
        fs = chart.get("forecast_start")
        if fs is not None and 0 < fs < n:
            fx = X(fs - 0.5)
            self.rect(s, fx, py0, px1 - fx, py1 - py0, self.tk["grid"], None, 0, alpha=0.45 if not self.tk.get("dark") else 0.3)
            self.text(s, fx + 0.08, py0 + 0.02, 2.5, 0.22, chart.get("forecast_label", "Forecast"), "label", 10,
                      self.tk["chart_text"], accent=False)
        if band.get("upper") and band.get("lower"):
            up = [(X(i), Y(fmt.to_num(v))) for i, v in enumerate(band["upper"]) if v is not None]
            lo = [(X(i), Y(fmt.to_num(v))) for i, v in enumerate(band["lower"]) if v is not None]
            if up and lo:
                self.poly(s, up + list(reversed(lo)), fill=self.tk["series"][0], alpha=0.16, closed=True)
        for j, sr in enumerate(series):
            col = self.tk["series"][j % len(self.tk["series"])]
            pts = [(X(i), Y(fmt.to_num(v)), i) for i, v in enumerate(sr.get("values", [])) if v is not None]
            if len(pts) < 2:
                continue
            if fs is not None and sr.get("style") != "dashed":
                solid = [(a, b) for a, b, i in pts if i < fs]
                dash = [(a, b) for a, b, i in pts if i >= fs - 1]
                if len(solid) > 1:
                    self.poly(s, solid, line=col, width=2.25)
                if len(dash) > 1:
                    self.poly(s, dash, line=col, width=2.25, dash=True)
            else:
                self.poly(s, [(a, b) for a, b, _ in pts], line=col, width=2.25, dash=sr.get("style") == "dashed")
            ex, ey, _ = pts[-1]
            self.oval(s, ex, ey, 0.055, col, self.tk["panel"], 1.25)
            if len(series) > 1 or sr.get("label"):
                self.text(s, ex + 0.12, ey - 0.11, right, 0.22, sr.get("label", ""), "label", 10, self.tk["ink2"],
                          anchor="middle", accent=False)
        # x labels: first, last, and evenly spaced
        k = max(1, int(math.ceil(n / 7.0)))
        for i in range(0, n, k):
            if i and n - 1 - i < k * 0.6:
                continue
            self.text(s, X(i) - 0.5, py1 + 0.08, 1.0, 0.22, labels[i], "label", 10, self.tk["chart_text"],
                      align="center", accent=False)
        self.text(s, X(n - 1) - 0.7, py1 + 0.08, 0.75, 0.22, labels[-1], "label", 10, self.tk["chart_text"],
                  align="right", accent=False)

    # ---------------------------------------------------------- scatter
    def scatter(self, s, chart, x, y, w, h):
        pts = chart.get("points") or []
        if not pts:
            return
        xs = [fmt.to_num(p.get("x"), 0.0) for p in pts]
        ys = [fmt.to_num(p.get("y"), 0.0) for p in pts]
        ss_ = [fmt.to_num(p.get("size"), 1.0) for p in pts]
        xu, yu = chart.get("x_unit"), chart.get("y_unit")
        xt = fmt.axis_ticks(max(xs) * 1.1 if max(xs) > 0 else 1, min(0.0, min(xs)))
        yt = fmt.axis_ticks(max(ys) * 1.12 if max(ys) > 0 else 1, min(0.0, min(ys)))
        gut = max(self.measure(fmt_value(t, yu), "label", 10) for t in yt) + 0.45
        px0, px1, py0, py1 = x + gut, x + w - 0.1, y + 0.05, y + h - 0.62

        def X(v):
            return px0 + (px1 - px0) * (v - xt[0]) / ((xt[-1] - xt[0]) or 1)

        def Y(v):
            return py1 - (py1 - py0) * (v - yt[0]) / ((yt[-1] - yt[0]) or 1)

        for t in yt:
            self.line(s, px0, Y(t), px1, Y(t), self.tk["grid"], 0.75)
            self.text(s, x + 0.3, Y(t) - 0.1, gut - 0.4, 0.2, fmt_value(t, yu), "label", 10, self.tk["chart_text"],
                      align="right", anchor="middle", accent=False)
        for t in xt:
            self.line(s, X(t), py0, X(t), py1, self.tk["grid"], 0.75)
            self.text(s, X(t) - 0.4, py1 + 0.06, 0.8, 0.2, fmt_value(t, xu), "label", 10, self.tk["chart_text"],
                      align="center", accent=False)
        if chart.get("x_label"):
            self.text(s, px0, py1 + 0.32, px1 - px0, 0.24, chart["x_label"], "label", 10.5, self.tk["ink2"],
                      align="center", accent=False)
        if chart.get("y_label"):
            tb = self.text(s, x - 0.55, (py0 + py1) / 2 - 0.12, 1.5, 0.24, chart["y_label"], "label", 10.5,
                           self.tk["ink2"], align="center", accent=False)
            tb.rotation = -90
        if chart.get("x_ref") is not None:
            self.line(s, X(chart["x_ref"]), py0, X(chart["x_ref"]), py1, self.tk["axis"], 1.25)
        if chart.get("y_ref") is not None:
            self.line(s, px0, Y(chart["y_ref"]), px1, Y(chart["y_ref"]), self.tk["axis"], 1.25)
        groups = []
        for p in pts:
            g = p.get("group")
            if g is not None and g not in groups:
                groups.append(g)
        smax = max(ss_) or 1
        order = sorted(range(len(pts)), key=lambda i: -ss_[i])
        for i in order:
            r = 0.07 + 0.17 * math.sqrt(ss_[i] / smax)
            gi = groups.index(pts[i].get("group")) if pts[i].get("group") in groups else 0
            col = self.tk["neutral"] if pts[i].get("muted") else self.tk["series"][gi]
            o = self.oval(s, X(xs[i]), Y(ys[i]), r, col, self.tk["panel"], 1.5)
            _set_alpha(o.fill, 0.82)
        placed = []
        max_labels = 9 if len(pts) > 9 else len(pts)
        labelled = 0
        for i in order:
            p = pts[i]
            if not p.get("label") or p.get("hide_label"):
                continue
            if labelled >= max_labels and not p.get("highlight"):
                continue
            r = 0.07 + 0.17 * math.sqrt(ss_[i] / smax)
            lw = self.measure(p["label"], "label", 9.5) + 0.05
            for lx, ly in ((X(xs[i]) + r + 0.05, Y(ys[i]) - 0.1), (X(xs[i]) - r - 0.05 - lw, Y(ys[i]) - 0.1),
                           (X(xs[i]) - lw / 2, Y(ys[i]) - r - 0.24), (X(xs[i]) - lw / 2, Y(ys[i]) + r + 0.02)):
                box = (lx, ly, lx + lw, ly + 0.2)
                if box[0] < px0 or box[2] > px1 or box[1] < py0 or box[3] > py1:
                    continue
                if any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]) for b in placed):
                    continue
                placed.append(box)
                self.text(s, lx, ly, lw + 0.1, 0.2, p["label"], "label", 9.5, self.tk["ink2"], accent=False)
                labelled += 1
                break
        q = chart.get("quadrants") or {}
        corner = {"tl": (px0 + 0.1, py0 + 0.05, "left"), "tr": (px1 - 2.1, py0 + 0.05, "right"),
                  "bl": (px0 + 0.1, py1 - 0.3, "left"), "br": (px1 - 2.1, py1 - 0.3, "right")}
        for kq, txt in q.items():
            if kq in corner and txt:
                cx, cy, al = corner[kq]
                self.text(s, cx, cy, 2.0, 0.24, txt, "label", 10, self.tk["ink3"], align=al, accent=False)
        if len(groups) > 1:
            lx = px0
            for gi, g in enumerate(groups):
                self.oval(s, lx + 0.06, y + h - 0.12, 0.06, self.tk["series"][gi])
                self.text(s, lx + 0.18, y + h - 0.23, 2.0, 0.22, g, "body", 10.5, self.tk["ink2"], accent=False)
                lx += self.measure(g, "body", 10.5) + 0.55

    # ----------------------------------------------------------- sankey
    def sankey(self, s, chart, x, y, w, h):
        links = [l for l in (chart.get("links") or []) if fmt.to_num(l.get("value"), 0) > 0]
        if not links:
            return
        L, R = [], []
        for l in links:
            if l["from"] not in L:
                L.append(l["from"])
            if l["to"] not in R:
                R.append(l["to"])
        if chart.get("left_order"):
            L = [n for n in chart["left_order"] if n in L] + [n for n in L if n not in chart["left_order"]]
        if chart.get("right_order"):
            R = [n for n in chart["right_order"] if n in R] + [n for n in R if n not in chart["right_order"]]
        lt = {n: sum(fmt.to_num(l["value"], 0) for l in links if l["from"] == n) for n in L}
        rt = {n: sum(fmt.to_num(l["value"], 0) for l in links if l["to"] == n) for n in R}
        tot = sum(lt.values()) or 1
        unit = chart.get("unit")
        lab_l = max(self.measure(n, "body", 11) for n in L) + 0.2
        lab_r = max(self.measure(n, "body", 11) for n in R) + 0.2
        top = y + 0.32
        nw = 0.12
        xl, xr = x + lab_l, x + w - lab_r - nw
        gap = 0.08
        avail = min(h - 0.35 - gap * (len(L) - 1), h - 0.35 - gap * (len(R) - 1))
        k = avail / tot
        if chart.get("left_title"):
            self.text(s, xl, y, 3, 0.24, chart["left_title"], "label", 10, self.tk["ink2"], accent=False)
        if chart.get("right_title"):
            self.text(s, xr + nw - 3, y, 3, 0.24, chart["right_title"], "label", 10, self.tk["ink2"], align="right",
                      accent=False)
        yl, cur = {}, top
        for n in L:
            yl[n] = cur
            cur += lt[n] * k + gap
        yr, cur = {}, top
        for n in R:
            yr[n] = cur
            cur += rt[n] * k + gap
        offl = dict((n, 0.0) for n in L)
        offr = dict((n, 0.0) for n in R)
        cols = dict((n, self.tk["series"][i % len(self.tk["series"])]) for i, n in enumerate(L))
        for l in sorted(links, key=lambda l: (L.index(l["from"]), R.index(l["to"]))):
            v = fmt.to_num(l["value"], 0) * k
            y0 = yl[l["from"]] + offl[l["from"]]
            y1 = yr[l["to"]] + offr[l["to"]]
            offl[l["from"]] += v
            offr[l["to"]] += v
            xa, xb = xl + nw, xr
            top_curve = _bezier((xa, y0), (xa + (xb - xa) / 2, y0), (xa + (xb - xa) / 2, y1), (xb, y1), 24)
            bot_curve = _bezier((xb, y1 + v), (xa + (xb - xa) / 2, y1 + v), (xa + (xb - xa) / 2, y0 + v), (xa, y0 + v), 24)
            self.poly(s, top_curve + bot_curve, fill=cols[l["from"]], alpha=0.36 if not self.tk.get("dark") else 0.45,
                      closed=True)
        for n in L:
            hh = max(0.03, lt[n] * k)
            self.rect(s, xl, yl[n], nw, hh, cols[n], None, 0.02)
            self.text(s, x, yl[n] + hh / 2 - 0.2, lab_l - 0.1, 0.22, n, "body", 11, self.tk["ink"], align="right",
                      anchor="middle", accent=False)
            if hh > 0.42:
                self.text(s, x, yl[n] + hh / 2 + 0.02, lab_l - 0.1, 0.2, fmt_value(lt[n], unit), "label", 9.5,
                          self.tk["ink3"], align="right", accent=False)
        for n in R:
            hh = max(0.03, rt[n] * k)
            self.rect(s, xr, yr[n], nw, hh, self.tk["ink2"] if not self.tk.get("dark") else self.tk["ink3"], None, 0.02)
            self.text(s, xr + nw + 0.1, yr[n] + hh / 2 - 0.2, lab_r, 0.22, n, "body", 11, self.tk["ink"],
                      anchor="middle", accent=False)
            if hh > 0.42:
                self.text(s, xr + nw + 0.1, yr[n] + hh / 2 + 0.02, lab_r, 0.2, fmt_value(rt[n], unit), "label", 9.5,
                          self.tk["ink3"], accent=False)

    # ---------------------------------------------------------- heatmap
    def heatmap(self, s, chart, x, y, w, h):
        rows, cols, vals = chart.get("rows") or [], chart.get("cols") or [], chart.get("values") or []
        if not rows or not cols:
            return
        flat = [fmt.to_num(v, 0.0) for r in vals for v in r]
        vmax = max(flat) or 1
        seq = self.tk["seq"]
        lab_w = max(self.measure(r, "label", 10.5) for r in rows) + 0.15
        top = y + 0.28
        gw = w - lab_w
        gh = h - 0.28 - 0.4
        cw, rh = gw / len(cols), gh / len(rows)
        every = chart.get("col_label_every", 1 if len(cols) <= 12 else 3)
        for j, c in enumerate(cols):
            if j % every == 0:
                self.text(s, x + lab_w + j * cw - 0.3, y, cw + 0.6, 0.22, c, "label", 9.5, self.tk["ink3"],
                          align="center", accent=False)
        show = chart.get("show_values", len(cols) <= 12)
        for i, r in enumerate(rows):
            self.text(s, x, top + i * rh, lab_w - 0.1, rh, r, "label", 10.5, self.tk["ink2"], anchor="middle",
                      accent=False)
            for j in range(len(cols)):
                v = fmt.to_num(vals[i][j] if i < len(vals) and j < len(vals[i]) else 0, 0.0)
                step = int(round((len(seq) - 1) * v / vmax)) if v > 0 else -1
                fill = seq[step] if step >= 0 else self.tk["track"]
                self.rect(s, x + lab_w + j * cw + 0.015, top + i * rh + 0.015, cw - 0.03, rh - 0.03, fill, None, 0.03)
                if show and v > 0:
                    self.text(s, x + lab_w + j * cw, top + i * rh, cw, rh, fmt_value(v, chart.get("unit")), "label", 9,
                              COL.readable_on(fill, target=3.0), align="center", anchor="middle", accent=False)
        sx = x + w - 2.6
        sy = y + h - 0.26
        self.text(s, sx - 0.75, sy - 0.03, 0.7, 0.22, chart.get("low_label", "Fewer"), "label", 9.5, self.tk["ink3"],
                  align="right", accent=False)
        for i, c in enumerate(seq):
            self.rect(s, sx + i * 0.22, sy, 0.22, 0.14, c, None)
        self.text(s, sx + len(seq) * 0.22 + 0.08, sy - 0.03, 0.8, 0.22, chart.get("high_label", "More"), "label", 9.5,
                  self.tk["ink3"], accent=False)

    # ----------------------------------------------------------- funnel
    def funnel(self, s, sec, x, y, w, h):
        stages = sec.get("stages") or []
        if not stages:
            return
        vals = [fmt.to_num(st.get("value"), 0.0) for st in stages]
        broken = len(vals) > 1 and vals[1] > 0 and vals[0] / vals[1] > 6
        ref = vals[1] if broken else (max(vals) or 1)
        mode = "dark" if self.tk.get("dark") else "light"
        ramp = COL.ordinal(self.tk["series"][0], len(stages), mode, self.tk["panel"])
        n = len(stages)
        lab_w = min(2.6, w * 0.3)
        row = h / n
        bar_h = min(0.42, row * 0.42)
        bx, bw = x + lab_w, (w - lab_w) * 0.78
        for i, st in enumerate(stages):
            cy = y + i * row + row * 0.58
            self.text(s, x, cy - 0.24, lab_w - 0.15, 0.28, st.get("label", ""), "strong", 12.5, self.tk["ink"],
                      bold=True, accent=False)
            if st.get("source"):
                self.text(s, x, cy + 0.04, lab_w - 0.15, 0.22, st["source"], "label", 9.5, self.tk["ink3"],
                          accent=False)
            frac = 1.0 if (broken and i == 0) else (0.88 if broken else 1.0) * vals[i] / (ref or 1)
            bwid = max(0.03, bw * frac)
            self.rect(s, bx, cy - bar_h / 2, bwid, bar_h, ramp[i], None,
                      bar_h / 2 if self.key == "studio" else (0.04 if self.key != "classic" else 0))
            if broken and i == 0:
                bk = self.rect(s, bx + bwid * 0.72, cy - bar_h / 2 - 0.05, 0.1, bar_h + 0.1, self.tk["panel"], None,
                               shape=MSO_SHAPE.PARALLELOGRAM)
            disp = st.get("display") or fmt_value(vals[i], sec.get("unit"))
            self.text(s, bx + bwid + 0.12, cy - 0.2, 1.6, 0.4, disp, "numeral", 17, self.tk["ink"], anchor="middle",
                      accent=False)
            if i > 0 and vals[i - 1] > 0:
                rate = 100.0 * vals[i] / vals[i - 1]
                txt = "↓ %s %s" % (fmt.pct(rate, 1 if rate < 10 else 0), st.get("conv_label") or "converted")
                self.text(s, bx, cy - row * 0.58 + row * 0.04 - 0.02, bw, 0.22, txt, "label", 10, self.tk["ink2"],
                          accent=False)

    # ------------------------------------------------------- table
    def table(self, sec, header=None):
        cols = sec.get("columns") or []
        rows = sec.get("rows") or []
        if not cols:
            return
        chunks = _chunks(rows, 11) if rows else [[]]
        for ci, chunk in enumerate(chunks):
            if header and ci == 0:
                kick, title, dek = header.get("kicker"), header.get("title"), header.get("dek")
                sub = sec.get("title")
            else:
                kick, title, dek, sub = (header or {}).get("kicker"), sec.get("title") or (header or {}).get("title", ""), None, None
                if ci > 0:
                    title = (fmt.strip_accent(title) + " (continued)") if title else "Continued"
            s, top = self.frame(kick, title, dek, notes=sec.get("caption"))
            if sub:
                self.text(s, MX, top - 0.05, SW - 2 * MX, 0.3, sub, "display", 14, self.tk["ink"], bold=self.ss["title_bold"])
                top += 0.4
            totals = sec.get("totals") if ci == len(chunks) - 1 else None
            self._table(s, cols, chunk, totals, MX, top, SW - 2 * MX, 6.6 - top)
            if sec.get("caption") and ci == len(chunks) - 1:
                self.text(s, MX, 6.62, SW - 2 * MX, 0.25, sec["caption"], "body", 10, self.tk["ink3"], accent=False)

    def _table(self, s, cols, rows, totals, x, y, w, max_h):
        nrows = len(rows) + 1 + (1 if totals else 0)
        rh = min(0.52, max_h / max(1, nrows))
        weights = []
        for c in cols:
            t = c.get("type", "name")
            weights.append({"rank": 0.45, "name": 2.3, "source": 2.0, "bar": 2.0, "spark": 1.2, "text": 2.6,
                            "trend": 1.15, "badge": 1.2, "platform": 1.7, "delta": 1.0}.get(t, 1.0))
        tw = sum(weights)
        widths = [w * k / tw for k in weights]
        gf = s.shapes.add_table(nrows, len(cols), E(x), E(y), E(w), E(rh * nrows))
        tbl = gf.table
        _no_table_style(gf)
        for j, wd in enumerate(widths):
            tbl.columns[j].width = E(wd)
        for i in range(nrows):
            tbl.rows[i].height = E(rh)
        colmax = {}
        for c in cols:
            if c.get("type") == "bar":
                colmax[c["key"]] = c.get("max") or max([fmt.to_num((r.get(c["key"]) or {}).get("value") if isinstance(r.get(c["key"]), dict) else r.get(c["key"]), 0) or 0 for r in rows] + [1])
        hdr_fill = self.tk["panel2"] if self.key != "studio" else self.tk["panel"]
        overlays = []
        for j, c in enumerate(cols):
            cell = tbl.cell(0, j)
            self._cell(cell, c.get("label", ""), "label", 9.5, self.tk["ink3"] if self.key != "classic" else self.tk["ink2"],
                       hdr_fill, align=c.get("align"), bold=self.key != "classic", upper=self.key == "classic")
            _cell_border(cell, bottom=self.tk["line"])
        for i, r in enumerate(rows):
            fill = self.tk["panel"] if not r.get("_highlight") else self.tk["brand_soft"]
            for j, c in enumerate(cols):
                cell = tbl.cell(i + 1, j)
                v = r.get(c["key"])
                t = c.get("type", "name")
                txt, col, role, bold = "", self.tk["ink"], "body", False
                if t in ("bar", "spark", "trend", "badge", "platform"):
                    overlays.append((i + 1, j, t, v, c))
                elif t == "delta":
                    lab, tone = _delta_cell(v, c)
                    txt, col, bold = lab, {"good": self.tk["good"], "bad": self.tk["bad"]}.get(tone, self.tk["ink3"]), True
                elif t == "rank":
                    txt, col, role = str(v or ""), self.tk["ink3"], "numeral" if self.key == "classic" else "body"
                elif t == "source":
                    txt, col, role = str(v or ""), self.tk["ink2"], "mono"
                elif t == "number":
                    txt, bold, role = str(v if not isinstance(v, dict) else v.get("label", "")), True, "numeral" if self.key in ("classic", "boardroom", "studio") else "body"
                else:
                    txt = str(v if not isinstance(v, dict) else v.get("label", "")) if v is not None else ""
                    bold = t == "name"
                    if t == "text":
                        col = self.tk["ink2"]
                size = 11 if t != "number" else 12
                maxw = widths[j] - 0.2
                txt = _ellipsize(self, fmt.clean_text(txt), role, size, maxw, bold)
                self._cell(cell, txt, role, size, col, fill, align=c.get("align"), bold=bold)
                _cell_border(cell, bottom=self.tk["line_soft"] if not self.tk.get("dark") else self.tk["line"])
        if totals:
            i = nrows - 1
            for j, c in enumerate(cols):
                v = totals.get(c["key"], "")
                if isinstance(v, dict):
                    v = v.get("label", "")
                cell = tbl.cell(i, j)
                self._cell(cell, _ellipsize(self, str(v), "strong", 11, widths[j] - 0.2, True), "strong", 11,
                           self.tk["ink"], self.tk["panel2"], align=c.get("align"), bold=True)
                _cell_border(cell, top=self.tk["ink3"])
        # overlays (bars, sparks, pills)
        xs = [x]
        for wd in widths[:-1]:
            xs.append(xs[-1] + wd)
        for (i, j, t, v, c) in overlays:
            cx, cy, cw = xs[j] + 0.1, y + i * rh, widths[j] - 0.2
            mid = cy + rh / 2
            if v is None:
                continue
            if t == "bar":
                num = fmt.to_num(v.get("value") if isinstance(v, dict) else v, 0.0)
                lab = (v.get("label") if isinstance(v, dict) else None) or fmt_value(num, c.get("unit"))
                lw = 0.55
                self.text(s, cx, mid - 0.13, lw, 0.26, lab, "strong", 11, self.tk["ink"], bold=True, align="right",
                          anchor="middle", accent=False)
                bx, bwid = cx + lw + 0.1, cw - lw - 0.1
                self.rect(s, bx, mid - 0.05, bwid, 0.1, self.tk["track"], None, 0.05 if self.key == "studio" else 0.01)
                frac = max(0.0, min(1.0, num / (colmax.get(c["key"]) or 1)))
                if frac > 0:
                    self.rect(s, bx, mid - 0.05, max(0.03, bwid * frac), 0.1, self.tk["series"][0], None,
                              0.05 if self.key == "studio" else 0.01)
            elif t == "spark":
                vals = v.get("values") if isinstance(v, dict) else v
                self.sparkline(s, cx, mid - 0.13, min(cw, 1.1), 0.26, vals, self.tk["series"][0], fill=False)
            elif t in ("trend", "badge"):
                if isinstance(v, dict):
                    lab = v.get("label", "")
                    tone = v.get("tone") or {"rising": "good", "steady": "neutral", "cooling": "warn", "cold": "bad"}.get(v.get("state"), "neutral")
                else:
                    lab, tone = str(v), "neutral"
                fg = {"good": self.tk["good"], "warn": self.tk["warn"], "bad": self.tk["bad"],
                      "brand": self.tk["brand_ink"]}.get(tone, self.tk["ink2"])
                bg = {"good": self.tk["good_soft"], "warn": self.tk["warn_soft"], "bad": self.tk["bad_soft"],
                      "brand": self.tk["brand_soft"]}.get(tone, self.tk["panel2"])
                pw = min(cw, self.measure(lab, "strong", 9.5, bold=True) + 0.3)
                if self.key == "classic":
                    self.oval(s, cx + 0.05, mid, 0.04, fg)
                    self.text(s, cx + 0.15, mid - 0.13, cw, 0.26, lab, "strong", 10, fg, bold=True, anchor="middle",
                              accent=False)
                else:
                    self.rect(s, cx, mid - 0.12, pw, 0.24, bg, None, 0.12 if self.key != "ledger" else 0.03)
                    self.text(s, cx, mid - 0.12, pw, 0.24, lab, "strong", 9.5, fg, bold=True, align="center",
                              anchor="middle", accent=False)
            elif t == "platform":
                from .html_render import PLATFORM_COLORS
                name = v.get("name") if isinstance(v, dict) else str(v)
                self.oval(s, cx + 0.05, mid, 0.045, PLATFORM_COLORS.get(name.lower(), self.tk["ink3"]))
                self.text(s, cx + 0.16, mid - 0.13, cw - 0.16, 0.26, _ellipsize(self, name, "body", 11, cw - 0.2, False),
                          "body", 11, self.tk["ink"], anchor="middle", accent=False)

    def _cell(self, cell, text, role, size, color, fill, align=None, bold=False, upper=False):
        cell.fill.solid()
        cell.fill.fore_color.rgb = rgb(fill)
        cell.margin_left = E(0.1)
        cell.margin_right = E(0.1)
        cell.margin_top = E(0.02)
        cell.margin_bottom = E(0.02)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf = cell.text_frame
        tf.word_wrap = False
        p = tf.paragraphs[0]
        p.alignment = {"right": PP_ALIGN.RIGHT, "center": PP_ALIGN.CENTER}.get(align or "", PP_ALIGN.LEFT)
        r = p.add_run()
        r.text = text.upper() if upper else text
        fam, b, it = self.font(role, bold)
        r.font.name = fam
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.italic = it if role == "numeral" else False
        r.font.color.rgb = rgb(color)
        if upper:
            r.font._rPr.set("spc", "120")

    # ------------------------------------------------------ recommendations
    def recs(self, sec, header=None):
        items = (sec.get("items") or [])[:6]
        kick = (header or {}).get("kicker") or "Next steps"
        title = (header or {}).get("title") or "What to do *next*."
        notes = " ".join("%d. %s: %s" % (i + 1, fmt.strip_accent(it.get("title", "")), it.get("body", "")) for i, it in enumerate(items))
        s, top = self.frame(kick, title, (header or {}).get("dek"), notes)
        n = len(items)
        if self.key == "ledger":
            rh = min(1.05, (6.85 - top) / max(1, n))
            self.rect(s, MX, top, SW - 2 * MX, rh * n, self.tk["panel"], self.tk["line"], self.ss["radius"])
            for i, it in enumerate(items):
                ry = top + i * rh
                if i:
                    self.line(s, MX, ry, SW - MX, ry, self.tk["line"], 0.75)
                self.text(s, MX + 0.25, ry + 0.14, 0.4, 0.3, "%d" % (i + 1), "numeral", 16, self.tk["brand_ink"], accent=False)
                lab = it.get("label") or ""
                self.text(s, MX + 0.7, ry + 0.12, 4.6, 0.22, lab, "label", 9.5, self.tk["ink3"], accent=False)
                self.text(s, MX + 0.7, ry + 0.32, 4.6, rh - 0.36, it.get("title", ""), "display", 13.5, self.tk["ink"],
                          bold=True, accent="none")
                self.text(s, MX + 5.6, ry + 0.14, SW - 2 * MX - 5.85, rh - 0.2, it.get("body", ""), "body", 12,
                          self.tk["ink2"], accent=False)
                self._rec_meta(s, it, SW - MX - 3.0, ry + rh - 0.36)
            return
        cols = 2 if n <= 4 else 3
        rows = int(math.ceil(n / float(cols)))
        gap = 0.2
        cw = (SW - 2 * MX - gap * (cols - 1)) / cols
        ch = min(2.4, (6.85 - top - gap * (rows - 1)) / rows)
        for i, it in enumerate(items):
            r, c = divmod(i, cols)
            x, y = MX + c * (cw + gap), top + r * (ch + gap)
            pad = 0.26
            if self.key == "classic":
                top_h = min(1.0, ch * 0.45)
                self.twotone(s, x, y, cw, ch, top_h)
                self.text(s, x + pad, y + 0.2, cw - 2 * pad, 0.22, it.get("label") or "Action %02d" % (i + 1), "label",
                          8.5, self.tk["brand"], upper=True, tracking=160, accent=False)
                self.text(s, x + pad, y + 0.45, cw - 2 * pad, top_h - 0.5, it.get("title", ""), "display", 17,
                          self.tk["ink"])
                self.text(s, x + pad, y + top_h + 0.16, cw - 2 * pad, ch - top_h - 0.5, it.get("body", ""), "body",
                          11.5, self.tk["ink"], accent=False)
                self._rec_meta(s, it, x + pad, y + ch - 0.36)
                continue
            self.card(s, x, y, cw, ch)
            tx = x + pad
            if self.key == "studio":
                self.oval(s, x + pad + 0.2, y + pad + 0.2, 0.2, self.tk["brand_fill"])
                self.text(s, x + pad, y + pad, 0.4, 0.4, str(i + 1), "numeral", 13, self.tk["on_brand"], align="center",
                          anchor="middle", accent=False)
                tx = x + pad + 0.6
            else:
                self.text(s, x + pad, y + pad - 0.04, 0.9, 0.5, "%02d" % (i + 1), "numeral", 26, self.tk["brand_ink"],
                          accent=False)
            ty = y + pad + (0 if self.key == "studio" else 0.5)
            lab = it.get("label") or ""
            if lab and not re.match(r"^(action|step)\s*0*\d+$", lab, re.I):
                self.text(s, tx, ty, cw - (tx - x) - pad, 0.22, lab, "label", 9.5, self.tk["ink3"], accent=False)
                ty += 0.24
            size, nl = self.fit(fmt.strip_accent(it.get("title", "")), "display", cw - (tx - x) - pad, 0.75, 18, 12,
                                max_lines=2, bold=self.ss["title_bold"], lh=1.2)
            self.text(s, tx, ty, cw - (tx - x) - pad, nl * size * 1.2 / 72 + 0.05, it.get("title", ""), "display",
                      size, self.tk["ink"], bold=self.ss["title_bold"])
            ty += nl * size * 1.2 / 72 + 0.1
            has_meta = bool(it.get("impact") or it.get("effort"))
            avail_h = y + ch - ty - (0.46 if has_meta else 0.2)
            bw_ = cw - (tx - x) - pad
            fam, _, _ = self.font("body")
            bsz = 12.5
            while bsz > 9.5:
                nl = len(_wrap(it.get("body", ""), fam, bsz, bw_ * 72 * 0.92 / FALLBACK_WIDTH.get(fam, 1.0)))
                if nl * bsz * 1.22 / 72 <= avail_h:
                    break
                bsz -= 0.5
            self.text(s, tx, ty, bw_, avail_h, it.get("body", ""), "body", bsz, self.tk["ink2"], accent=False, lh=1.12)
            if has_meta:
                self._rec_meta(s, it, tx, y + ch - 0.38)

    def _rec_meta(self, s, it, x, y):
        for key, word in (("impact", "impact"), ("effort", "effort")):
            v = it.get(key)
            if not v:
                continue
            lab = "%s %s" % (v, word)
            tone = {"high": "bad", "medium": "warn"}.get(str(v).lower(), "neutral") if key == "impact" else "neutral"
            fg = {"bad": self.tk["bad"], "warn": self.tk["warn"]}.get(tone, self.tk["ink2"])
            bg = {"bad": self.tk["bad_soft"], "warn": self.tk["warn_soft"]}.get(tone, self.tk["panel2"])
            w = self.measure(lab, "strong", 9, bold=True) + 0.28
            if self.key == "classic":
                self.text(s, x, y, w, 0.24, lab, "strong", 9, fg, bold=True, anchor="middle", accent=False)
            else:
                self.rect(s, x, y, w, 0.24, bg, None, 0.12 if self.key != "ledger" else 0.03)
                self.text(s, x, y, w, 0.24, lab, "strong", 9, fg, bold=True, align="center", anchor="middle", accent=False)
            x += w + 0.1

    # ---------------------------------------------------- statement slides
    def insight_slide(self, sec, header=None):
        tone = sec.get("tone", "neutral")
        s, top = self.frame((header or {}).get("kicker"), (header or {}).get("title"), notes=" ".join(sec.get("body") or []))
        x, y, w, h = MX, max(top, 1.4), SW - 2 * MX, 6.85 - max(top, 1.4)
        fill = {"good": self.tk["good_soft"], "bad": self.tk["bad_soft"], "warn": self.tk["warn_soft"]}.get(tone)
        if self.key == "classic":
            top_h = min(2.4, h * 0.5)
            self.twotone(s, x, y, w, h, top_h)
        elif self.key == "boardroom":
            self.rect(s, x, y, w, h, fill or COL.mix(self.tk["panel"], self.tk["brand"], 0.14), self.tk["line"], self.ss["radius"])
        else:
            self.rect(s, x, y, w, h, fill or (self.tk["soft"] if self.key == "studio" else self.tk["brand_soft"]),
                      None if self.key == "studio" else self.tk["line"], self.ss["radius"])
        pad = 0.5
        cy = y + pad
        if sec.get("kicker"):
            cy += self.kicker(s, x + pad, cy, w - 2 * pad, sec["kicker"])
        size, nl = self.fit(fmt.strip_accent(sec.get("title", "")), "display", w - 2 * pad, 2.0, 34, 22, max_lines=3,
                            bold=self.ss["title_bold"])
        th = nl * size * 1.15 / 72 + 0.1
        self.text(s, x + pad, cy, w - 2 * pad, th, sec.get("title", ""), "display", size, self.tk["ink"],
                  bold=self.ss["title_bold"], lh=1.05)
        cy += th + 0.25
        if self.key == "classic":
            cy = max(cy, y + min(2.4, h * 0.5) + 0.3)
        body = sec.get("body") or []
        if body:
            self.text(s, x + pad, cy, w - 2 * pad - 1.0, y + h - cy - 0.3, body, "body", 16, self.tk["ink2"],
                      accent=False, lh=1.2)

    def hero_slide(self, sec, header=None):
        s, top = self.frame((header or {}).get("kicker") or None, (header or {}).get("title"),
                            notes="%s: %s. %s" % (sec.get("kicker", ""), sec.get("value", ""), sec.get("label", "")))
        if self.key == "boardroom":
            _bg_gradient(s, COL.mix(self.tk["page"], self.tk["brand"], 0.26), self.tk["page"], center=True)
        cy = max(top, 1.5) + 0.2
        if sec.get("kicker"):
            self.text(s, MX, cy, SW - 2 * MX, 0.32, sec["kicker"], "strong" if self.key != "classic" else "label",
                      14 if self.key != "classic" else 11, self.tk["brand_ink"] if self.key != "classic" else self.tk["brand"],
                      bold=True, align="center", upper=self.key == "classic", tracking=150 if self.key == "classic" else None,
                      accent=False)
            cy += 0.45
        size = self.fit_value(str(sec.get("value", "")), SW - 2 * MX - 1.0, self.ss["hero"])
        self.text(s, MX, cy, SW - 2 * MX, size / 72.0 * 1.1, str(sec.get("value", "")), "numeral", size,
                  self.tk["brand_ink"] if self.key == "studio" else self.tk["ink"], align="center", accent=False)
        cy += size / 72.0 * 1.12
        d = self._delta_text(sec, plain=self.key == "studio")
        if d:
            self.text(s, MX, cy, SW - 2 * MX, 0.3, d[0], "strong", 13, d[1], bold=True, align="center", accent=False)
            cy += 0.4
        if sec.get("label"):
            self.text(s, MX + 1.5, cy, SW - 2 * MX - 3.0, 0.8, sec["label"], "body", 17, self.tk["ink2"],
                      align="center", accent=False)
            cy += 0.75
        if sec.get("spark") and cy < 6.2:
            col = self.tk["brand_ink"] if self.tk.get("dark") else self.tk["series"][0]
            self.sparkline(s, SW / 2 - 2.2, min(cy + 0.1, 6.0), 4.4, 0.6, sec["spark"], col)

    def closing(self, sec, notes_sec=None):
        title = sec.get("title", "")
        notes = " ".join(sec.get("bullets") or []) + " " + (sec.get("body") or "")
        s = self.new_slide(notes)
        if self.key == "boardroom":
            _bg_gradient(s, COL.mix(self.tk["page"], self.tk["brand"], 0.3), self.tk["page"])
        if self.key == "studio":
            self.rect(s, 0.36, 0.36, SW - 0.72, SH - 0.72, self.tk["soft"], None, 0.34)
        y = 1.0
        if sec.get("kicker"):
            y += self.kicker(s, MX + (0.3 if self.key == "studio" else 0), y, 10, sec["kicker"])
        x0 = MX + (0.3 if self.key == "studio" else 0)
        size, nl = self.fit(fmt.strip_accent(title), "display", SW - 2 * x0, 2.0, 40, 24, max_lines=3,
                            bold=self.ss["title_bold"])
        th = nl * size * 1.1 / 72 + 0.12
        self.text(s, x0, y, SW - 2 * x0, th, title, "display", size, self.tk["ink"], bold=self.ss["title_bold"],
                  lh=1.02, align="center" if self.key == "classic" else "left")
        y += th + 0.45
        stats = (sec.get("summary_stats") or [])[:4]
        if stats and self.key != "classic":
            gap = 0.25
            w = (SW - 2 * x0 - gap * (len(stats) - 1)) / len(stats)
            for i, st in enumerate(stats):
                sx = x0 + i * (w + gap)
                self.line(s, sx, y, sx + w, y, self.tk["line"], 1.0)
                self.text(s, sx, y + 0.15, w, 0.25, st.get("label", ""), "label", 11, self.tk["ink3"], accent=False)
                vs = self.fit_value(str(st.get("value", "")), w - 0.1, 36)
                self.text(s, sx, y + 0.42, w, vs / 72 * 1.2, str(st.get("value", "")), "numeral", vs, self.tk["ink"],
                          accent=False)
            y += 1.35
        bullets = (sec.get("bullets") or [])[:4]
        if bullets and self.key != "classic":
            for b in bullets:
                self.oval(s, x0 + 0.06, y + 0.14, 0.05, self.tk["brand_ink"] if self.tk.get("dark") else self.tk["series"][0])
                self.text(s, x0 + 0.25, y, SW - 2 * x0 - 0.3, 0.32, b, "body", 14, self.tk["ink2"], accent=False)
                y += 0.38
        if sec.get("body"):
            self.text(s, x0, min(y + 0.1, 6.4), SW - 2 * x0, 0.5, sec["body"], "body", 13, self.tk["ink2"], accent=False,
                      align="center" if self.key == "classic" else "left")
            y += 0.55
        if notes_sec and notes_sec.get("items"):
            items = notes_sec["items"]
            fam, _, _ = self.font("body")
            lines = sum(len(_wrap(it, fam, 9.5, (SW - 2 * x0) * 72 * 0.92 / FALLBACK_WIDTH.get(fam, 1.0))) for it in items)
            need = 0.3 + lines * 0.19
            ny = 6.85 - need
            if ny >= y + 0.15:
                self.line(s, x0, ny - 0.08, SW - x0, ny - 0.08, self.tk["line"], 0.75)
                self.text(s, x0, ny, 6, 0.24, notes_sec.get("title") or "How we built this report", "strong", 10,
                          self.tk["ink2"], bold=True, accent=False)
                self.text(s, x0, ny + 0.27, SW - 2 * x0, lines * 0.19 + 0.05, items, "body", 9.5, self.tk["ink3"],
                          accent=False, lh=1.0)
            else:
                self.notes_slide(notes_sec)

    # ------------------------------------------------------- new sections
    def funnel_slide(self, sec, header=None):
        has_side = bool(sec.get("insight_title") or sec.get("insight_body"))
        kick = (header or {}).get("kicker") or sec.get("insight_kicker")
        title = (header or {}).get("title") or sec.get("title") or sec.get("insight_title")
        s, top = self.frame(kick, title, (header or {}).get("dek"), notes=" ".join(sec.get("insight_body") or []))
        bottom = 6.82
        mw = 7.9 if has_side else SW - 2 * MX
        self.card(s, MX, top, mw, bottom - top)
        self.funnel(s, sec, MX + 0.3, top + 0.25, mw - 0.6, bottom - top - 0.5 - (0.3 if sec.get("caption") else 0))
        if sec.get("caption"):
            self.text(s, MX + 0.3, bottom - 0.42, mw - 0.6, 0.26, sec["caption"], "body", 10, self.tk["ink3"], accent=False)
        if has_side:
            self.insight_panel(s, MX + mw + 0.2, top, SW - 2 * MX - mw - 0.2, bottom - top, sec,
                               show_title=bool(header) or bool(sec.get("title")))

    def figure_slide(self, sec, header, chart, side=False):
        """flow / heatmap / matrix: full-width figure, optional insight panel."""
        kick = (header or {}).get("kicker") or sec.get("insight_kicker")
        title = (header or {}).get("title") or sec.get("chart_title") or sec.get("insight_title") or ""
        sub = sec.get("chart_title") if header else None
        s, top = self.frame(kick, title, (header or {}).get("dek"),
                            notes=" ".join([sec.get("caption") or ""] + list(sec.get("insight_body") or [])))
        bottom = 6.82
        mw = 7.9 if side else SW - 2 * MX
        self.card(s, MX, top, mw, bottom - top)
        self.chart_area(s, chart, MX, top, mw, bottom - top, sub, sec.get("caption"))
        if side:
            self.insight_panel(s, MX + mw + 0.2, top, SW - 2 * MX - mw - 0.2, bottom - top, sec,
                               show_title=bool(header) or bool(sec.get("chart_title")))

    def comparison_slide(self, sec, header=None):
        a, b = sec.get("a") or {}, sec.get("b") or {}
        title = (header or {}).get("title") or "%s vs *%s*" % (a.get("label", "A"), b.get("label", "B"))
        s, top = self.frame((header or {}).get("kicker"), title, (header or {}).get("dek"), notes=sec.get("caption"))
        x, y, w = MX, top, SW - 2 * MX
        rows = sec.get("rows") or []
        h = min(6.82 - top, 0.75 + 0.5 * len(rows) + (0.35 if sec.get("caption") else 0))
        self.card(s, x, y, w, h)
        lab_w = 2.9
        colw = (w - lab_w - 0.6) / 2
        ax, bx = x + 0.3 + lab_w, x + 0.3 + lab_w + colw + 0.2
        ca = self.tk["series"][0]
        cb = self.tk["series"][1] if len(self.tk["series"]) > 1 else self.tk["neutral"]
        self.rect(s, ax + colw - 0.15 - self.measure(a.get("label", ""), "display", 15, bold=True) - 0.25, y + 0.33, 0.13, 0.13, ca, None, 0.03)
        self.text(s, ax, y + 0.24, colw - 0.15, 0.32, a.get("label", ""), "display", 15, self.tk["ink"], bold=True,
                  align="right", accent=False)
        self.rect(s, bx + 0.15, y + 0.33, 0.13, 0.13, cb, None, 0.03)
        self.text(s, bx + 0.38, y + 0.24, colw, 0.32, b.get("label", ""), "display", 15, self.tk["ink"], bold=True,
                  accent=False)
        ry = y + 0.75
        for r in rows:
            av, bv = fmt.to_num(r.get("a"), 0.0) or 0.0, fmt.to_num(r.get("b"), 0.0) or 0.0
            mm = max(abs(av), abs(bv)) or 1
            self.line(s, x + 0.3, ry - 0.04, x + w - 0.3, ry - 0.04, self.tk["line_soft"] if not self.tk.get("dark") else self.tk["line"], 0.75)
            self.text(s, x + 0.3, ry, lab_w, 0.4, r.get("label", ""), "body", 12, self.tk["ink2"], anchor="middle",
                      accent=False)
            atxt = str(r.get("a_display") or r.get("a", "")) + (" ✓" if r.get("better") == "a" else "")
            btxt = str(r.get("b_display") or r.get("b", "")) + (" ✓" if r.get("better") == "b" else "")
            vw = 1.1
            self.text(s, ax, ry, vw, 0.4, atxt, "strong", 12.5, self.tk["ink"], bold=True, anchor="middle", accent=False)
            trk = colw - vw - 0.15
            self.rect(s, ax + vw + 0.05, ry + 0.14, trk, 0.12, self.tk["track"], None, 0.02)
            wa = trk * abs(av) / mm
            self.rect(s, ax + vw + 0.05 + trk - wa, ry + 0.14, max(0.02, wa), 0.12, ca, None, 0.02)
            self.rect(s, bx, ry + 0.14, trk, 0.12, self.tk["track"], None, 0.02)
            wb = trk * abs(bv) / mm
            self.rect(s, bx, ry + 0.14, max(0.02, wb), 0.12, cb, None, 0.02)
            self.text(s, bx + trk + 0.1, ry, vw + 0.2, 0.4, btxt, "strong", 12.5, self.tk["ink"], bold=True,
                      anchor="middle", accent=False)
            ry += 0.5
        if sec.get("caption"):
            self.text(s, x + 0.3, ry + 0.02, w - 0.6, 0.26, sec["caption"], "body", 10.5, self.tk["ink3"], accent=False)

    def callouts_slide(self, sec, header=None):
        items = (sec.get("items") or [])[:4]
        title = (header or {}).get("title") or (items[0].get("title") if items else "")
        s, top = self.frame((header or {}).get("kicker"), title if header else "The numbers side by *side*.",
                            notes=" ".join("%s %s %s" % (i.get("kicker", ""), i.get("value", ""), i.get("title", "")) for i in items))
        n = max(1, len(items))
        gap = 0.2
        w = (SW - 2 * MX - gap * (n - 1)) / n
        h = min(3.2, 6.82 - top)
        for i, it in enumerate(items):
            x = MX + i * (w + gap)
            self.card(s, x, top, w, h)
            pad = 0.3
            cy = top + pad
            if it.get("kicker"):
                self.text(s, x + pad, cy, w - 2 * pad, 0.25, it["kicker"], "label", 11, self.tk["ink3"], accent=False)
                cy += 0.35
            vs = self.fit_value(str(it.get("value", "")), w - 2 * pad, 48)
            tone = it.get("tone", "neutral")
            col = {"good": self.tk["good"], "bad": self.tk["bad"], "warn": self.tk["warn"]}.get(tone, self.tk["ink"])
            self.text(s, x + pad, cy, w - 2 * pad, vs / 72 * 1.2, str(it.get("value", "")), "numeral", vs, col, accent=False)
            cy += vs / 72 * 1.2 + 0.1
            self.text(s, x + pad, cy, w - 2 * pad, 0.8, it.get("title", ""), "display", 15, self.tk["ink"],
                      bold=self.ss["title_bold"])
            cy += 0.75
            if it.get("body"):
                self.text(s, x + pad, cy, w - 2 * pad, top + h - cy - pad, it["body"], "body", 11.5, self.tk["ink2"],
                          accent=False)

    def scorecard_slide(self, sec, header=None):
        items = sec.get("items") or []
        title = (header or {}).get("title") or sec.get("title") or "Tracking *health*"
        chunks = _chunks(items, 8) if items else [[]]
        for ci, chunk in enumerate(chunks):
            s, top = self.frame((header or {}).get("kicker"), title if ci == 0 else fmt.strip_accent(title) + " (continued)",
                                notes=" ".join("%s: %s, %s." % (i.get("label"), i.get("value", ""), i.get("detail", "")) for i in chunk))
            rh = min(0.82, (6.82 - top) / max(1, len(chunk)))
            small = rh < 0.66
            self.card(s, MX, top, SW - 2 * MX, rh * len(chunk))
            for i, it in enumerate(chunk):
                y = top + i * rh
                if i:
                    self.line(s, MX + 0.25, y, SW - MX - 0.25, y, self.tk["line_soft"] if not self.tk.get("dark") else self.tk["line"], 0.75)
                st = it.get("status", "info")
                fg = {"pass": self.tk["good"], "good": self.tk["good"], "warn": self.tk["warn"], "fail": self.tk["bad"],
                      "bad": self.tk["bad"]}.get(st, self.tk["ink2"])
                bg = {"pass": self.tk["good_soft"], "good": self.tk["good_soft"], "warn": self.tk["warn_soft"],
                      "fail": self.tk["bad_soft"], "bad": self.tk["bad_soft"]}.get(st, self.tk["panel2"])
                icon = {"pass": "✓", "good": "✓", "warn": "!", "fail": "✕", "bad": "✕"}.get(st, "i")
                self.oval(s, MX + 0.5, y + rh / 2, 0.17, bg)
                self.text(s, MX + 0.33, y + rh / 2 - 0.17, 0.34, 0.34, icon, "strong", 12, fg, bold=True, align="center",
                          anchor="middle", accent=False)
                self.text(s, MX + 0.85, y + (0.08 if small else 0.12), 8.6, 0.3, it.get("label", ""), "strong",
                          12 if small else 13, self.tk["ink"], bold=True, accent=False)
                if it.get("detail"):
                    dsz = 10 if small else 11
                    det = it["detail"]
                    fam, _, _ = self.font("body")
                    if len(_wrap(det, fam, dsz, 8.6 * 72 * 0.92 / FALLBACK_WIDTH.get(fam, 1.0))) > (1 if small else 2):
                        det = _ellipsize(self, det, "body", dsz, 8.6 * (1 if small else 2) * 0.92, False)
                    self.text(s, MX + 0.85, y + (0.34 if small else 0.42), 8.6, rh - 0.4, det, "body", dsz,
                              self.tk["ink2"], accent=False)
                self.text(s, SW - MX - 2.9, y, 1.6, rh, str(it.get("value", "")), "numeral", 20, self.tk["ink"],
                          align="right", anchor="middle", accent=False)
                word = it.get("status_label") or {"pass": "Healthy", "good": "Healthy", "warn": "Watch", "fail": "Fix",
                                                  "bad": "Fix"}.get(st, "Info")
                self.text(s, SW - MX - 1.15, y, 0.9, rh, word, "strong", 11, fg, bold=True, align="right",
                          anchor="middle", accent=False)

    def timeline_slide(self, sec, header=None):
        events = (sec.get("events") or [])[:7]
        title = (header or {}).get("title") or sec.get("title") or "The *journey*"
        s, top = self.frame((header or {}).get("kicker"), title, notes=" ".join("%s: %s." % (e.get("date"), e.get("title")) for e in events))
        rh = min(0.78, (6.82 - top) / max(1, len(events)))
        lx = MX + 0.25
        if len(events) > 1:
            self.line(s, lx, top + rh / 2 - 0.1, lx, top + (len(events) - 1) * rh + rh / 2 - 0.1, self.tk["line"], 1.5)
        for i, e in enumerate(events):
            y = top + i * rh
            kind = e.get("kind", "touch")
            col = self.tk["brand_ink"] if self.tk.get("dark") else self.tk["series"][0]
            if kind in ("conversion", "purchase"):
                self.oval(s, lx, y + rh / 2 - 0.1, 0.1, col)
            else:
                self.oval(s, lx, y + rh / 2 - 0.1, 0.1, self.tk["page"], col, 2.25)
            self.text(s, lx + 0.3, y + 0.05, 1.9, 0.3, e.get("date", ""), "label", 11, self.tk["ink3"], accent=False)
            self.text(s, lx + 2.3, y + 0.03, 8.5, 0.3, e.get("title", ""), "strong", 13, self.tk["ink"], bold=True, accent=False)
            dy = y + 0.33
            if e.get("detail"):
                self.text(s, lx + 2.3, dy, 6.4, 0.28, e["detail"], "body", 11, self.tk["ink2"], accent=False)
            tx = lx + 2.3 + min(6.4, self.measure(e.get("detail", ""), "body", 11) + 0.25) if e.get("detail") else lx + 2.3
            for tag in (e.get("tags") or [])[:3]:
                tw = self.measure(tag, "mono", 9.5) + 0.24
                if tx + tw > SW - MX:
                    break
                self.rect(s, tx, dy + 0.02, tw, 0.24, self.tk["panel2"], self.tk["line_soft"] if not self.tk.get("dark") else self.tk["line"], 0.05)
                self.text(s, tx, dy + 0.02, tw, 0.24, tag, "mono", 9.5, self.tk["ink2"], align="center", anchor="middle",
                          accent=False)
                tx += tw + 0.08

    def notes_slide(self, sec, header=None):
        s, top = self.frame("Method", sec.get("title") or "How we built this *report*.")
        items = sec.get("items") or []
        self.text(s, MX, top + 0.1, 10.5, 6.82 - top, ["•  " + i for i in items], "body", 13, self.tk["ink2"],
                  accent=False, lh=1.2)

    # ------------------------------------------------------------- build
    def build(self):
        secs = list(self.summary.get("sections") or [])
        header = None
        i = 0
        while i < len(secs):
            sec = secs[i]
            t = sec.get("type")
            nxt = secs[i + 1] if i + 1 < len(secs) else {}
            try:
                if t == "title-block":
                    self.cover(sec)
                elif t == "stat-strip":
                    if nxt.get("type") == "insight-card" and header is None:
                        self.kpis(sec, nxt)
                        i += 1
                    else:
                        self.kpis(sec, None)
                elif t == "section-header":
                    header = sec
                    i += 1
                    continue
                elif t == "chart-insight":
                    self.chart_slide(sec, header, with_insight=True)
                elif t == "chart":
                    self.chart_slide(sec, header, with_insight=False)
                elif t in ("ranked-list", "table"):
                    self.table(sec, header)
                elif t == "recommendations":
                    self.recs(sec, header)
                elif t == "insight-card":
                    self.insight_slide(sec, header)
                elif t == "hero-number":
                    self.hero_slide(sec, header)
                elif t == "closing":
                    self.closing(sec, getattr(self, "_pending_notes", None))
                    self._pending_notes = None
                elif t == "funnel":
                    self.funnel_slide(sec, header)
                elif t in ("flow", "sankey"):
                    spec = dict(sec)
                    spec["type"] = "sankey"
                    self.figure_slide(sec, header, spec)
                elif t == "heatmap":
                    spec = dict(sec)
                    spec["type"] = "heatmap"
                    self.figure_slide(sec, header, spec)
                elif t == "matrix":
                    spec = dict(sec)
                    spec["type"] = "scatter"
                    self.figure_slide(sec, header, spec, side=bool(sec.get("insight_title")))
                elif t == "comparison":
                    self.comparison_slide(sec, header)
                elif t == "callouts":
                    self.callouts_slide(sec, header)
                elif t == "scorecard":
                    self.scorecard_slide(sec, header)
                elif t == "timeline":
                    self.timeline_slide(sec, header)
                elif t == "notes":
                    if any(x.get("type") == "closing" for x in secs[i + 1:]):
                        self._pending_notes = sec
                    else:
                        self.notes_slide(sec, header)
            except Exception as exc:  # one bad section never sinks the deck
                import sys
                sys.stderr.write("pptx: skipped %s section: %s\n" % (t, exc))
            if t not in ("title-block",):
                header = None
            i += 1
        total = len(self.slides)
        for n, s in enumerate(self.slides, 1):
            if n == 1:
                continue
            self.footer(s, n, total)
        return self.prs


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------
def _chunks(items, max_per):
    """Split into the fewest balanced chunks of at most max_per (7 items -> 7, 13 -> 7 + 6)."""
    items = list(items)
    if len(items) <= max_per:
        return [items]
    n = -(-len(items) // max_per)
    size = -(-len(items) // n)
    return [items[i:i + size] for i in range(0, len(items), size)]


def _wrap(text, family, size, max_w_pt, weight=400, italic=False):
    words = str(text or "").split()
    if not words:
        return [""]
    lines, cur = [], words[0]
    for w in words[1:]:
        if text_width(cur + " " + w, family, size, weight, italic) <= max_w_pt:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _ellipsize(deck, text, role, size, max_w, bold):
    if deck.measure(text, role, size, bold=bold) <= max_w:
        return text
    while text and deck.measure(text + "…", role, size, bold=bold) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def _set_alpha(fill, alpha):
    try:
        clr = fill._xPr.find(qn("a:solidFill"))
        if clr is None:
            return
        node = clr[0]
        for old in node.findall(qn("a:alpha")):
            node.remove(old)
        a = etree.SubElement(node, qn("a:alpha"))
        a.set("val", str(int(alpha * 100000)))
    except Exception:
        pass


def _round_joins(sp):
    try:
        ln = sp.line._get_or_add_ln()
        ln.set("cap", "rnd")
        for old in ln.findall(qn("a:round")):
            ln.remove(old)
        etree.SubElement(ln, qn("a:round"))
    except Exception:
        pass


def _glow(slide, x, y, w, h, color, alpha):
    """A soft radial light behind content (Boardroom). Radial gradient to transparent."""
    sp = slide.shapes.add_shape(MSO_SHAPE.OVAL, E(x), E(y), E(w), E(h))
    sp.line.fill.background()
    sp.shadow.inherit = False
    spPr = sp._element.spPr
    for tag in ("a:solidFill", "a:noFill", "a:gradFill"):
        for el in spPr.findall(qn(tag)):
            spPr.remove(el)
    hexv = COL.clean_hex(color).lstrip("#")
    grad = etree.fromstring(
        '<a:gradFill xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" rotWithShape="1">'
        '<a:gsLst><a:gs pos="0"><a:srgbClr val="%s"><a:alpha val="%d"/></a:srgbClr></a:gs>'
        '<a:gs pos="100000"><a:srgbClr val="%s"><a:alpha val="0"/></a:srgbClr></a:gs></a:gsLst>'
        '<a:path path="circle"><a:fillToRect l="50000" t="50000" r="50000" b="50000"/></a:path></a:gradFill>'
        % (hexv, int(alpha * 100000), hexv))
    geom = spPr.find(qn("a:prstGeom"))
    geom.addnext(grad)
    # send to back
    tree = slide.shapes._spTree
    tree.remove(sp._element)
    tree.insert(2, sp._element)
    return sp


def _bg_gradient(slide, inner, outer, center=False):
    """Slide background: a smooth linear gradient from a brand-tinted corner to the page
    color. (Radial gradients band into visible rings in PowerPoint's PDF export.)"""
    bg = slide.background._cSld.get_or_add_bgPr()
    for el in list(bg):
        if el.tag != qn("a:effectLst"):
            bg.remove(el)
    a, b = COL.clean_hex(inner).lstrip("#"), COL.clean_hex(outer).lstrip("#")
    ang = 5400000 if center else 2700000
    grad = etree.fromstring(
        '<a:gradFill xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" rotWithShape="1">'
        '<a:gsLst><a:gs pos="0"><a:srgbClr val="%s"/></a:gs><a:gs pos="70000"><a:srgbClr val="%s"/></a:gs>'
        '<a:gs pos="100000"><a:srgbClr val="%s"/></a:gs></a:gsLst><a:lin ang="%d" scaled="0"/></a:gradFill>'
        % (a, b, b, ang))
    bg.insert(0, grad)
    if bg.find(qn("a:effectLst")) is None:
        etree.SubElement(bg, qn("a:effectLst"))


def _chart_bg_none(ch):
    cs = ch._chartSpace
    for parent in (cs, cs.find(qn("c:chart")).find(qn("c:plotArea"))):
        if parent is None:
            continue
        spPr = parent.find(qn("c:spPr"))
        if spPr is None:
            spPr = etree.SubElement(parent, qn("c:spPr"))
            if parent is cs:
                # c:spPr must come before c:txPr / externalData in chartSpace
                txPr = cs.find(qn("c:txPr"))
                if txPr is not None:
                    cs.remove(spPr)
                    txPr.addprevious(spPr)
        for el in list(spPr):
            spPr.remove(el)
        etree.SubElement(spPr, qn("a:noFill"))
        ln = etree.SubElement(spPr, qn("a:ln"))
        etree.SubElement(ln, qn("a:noFill"))


def _hole(ch, pct):
    try:
        el = ch._chartSpace.find(".//" + qn("c:holeSize"))
        if el is None:
            dn = ch._chartSpace.find(".//" + qn("c:doughnutChart"))
            el = etree.SubElement(dn, qn("c:holeSize"))
        el.set("val", str(int(pct)))
    except Exception:
        pass


def _tick_skip(axis, n):
    try:
        ax = axis._element
        for tag in ("c:tickLblSkip", "c:tickMarkSkip"):
            el = ax.find(qn(tag))
            if el is None:
                el = etree.SubElement(ax, qn(tag))
            el.set("val", str(int(n)))
        # schema order: tickLblSkip must follow lblOffset; move to the right spot
        nm = ax.find(qn("c:noMultiLvlLbl"))
        for tag in ("c:tickLblSkip", "c:tickMarkSkip"):
            el = ax.find(qn(tag))
            ax.remove(el)
            if nm is not None:
                nm.addprevious(el)
            else:
                ax.append(el)
    except Exception:
        pass


def _numfmt(unit, signed=False):
    if unit == "%":
        base = '0"%"'
    elif unit in ("$", "money"):
        base = '"$"#,##0'
    elif unit == "x":
        base = '0.0"x"'
    else:
        base = "#,##0"
    if signed:
        return "+%s;−%s;0" % (base, base)
    return base


def _no_table_style(gf):
    try:
        tbl = gf._element.graphic.graphicData.tbl
        tblPr = tbl.tblPr
        for attr in ("firstRow", "bandRow", "firstCol", "lastRow", "lastCol", "bandCol"):
            tblPr.set(attr, "0")
        sid = tblPr.find(qn("a:tableStyleId"))
        if sid is None:
            sid = etree.SubElement(tblPr, qn("a:tableStyleId"))
        sid.text = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"
    except Exception:
        pass


def _cell_border(cell, top=None, bottom=None):
    tcPr = cell._tc.get_or_add_tcPr()
    for side, col in (("a:lnL", None), ("a:lnR", None), ("a:lnT", top), ("a:lnB", bottom)):
        for el in tcPr.findall(qn(side)):
            tcPr.remove(el)
        ln = etree.SubElement(tcPr, qn(side))
        if col:
            ln.set("w", "9525")
            sf = etree.SubElement(ln, qn("a:solidFill"))
            c = etree.SubElement(sf, qn("a:srgbClr"))
            c.set("val", COL.clean_hex(col).lstrip("#"))
        else:
            ln.set("w", "0")
            etree.SubElement(ln, qn("a:noFill"))
    # borders must precede fill elements in tcPr
    fills = [el for el in tcPr if el.tag in (qn("a:solidFill"), qn("a:noFill"))]
    for f in fills:
        tcPr.remove(f)
        tcPr.append(f)


def _delta_cell(v, col):
    if isinstance(v, dict):
        d = v.get("direction", "flat")
        good = v.get("good", col.get("good", "up"))
        tone = "flat" if d == "flat" else ("good" if d == good else "bad")
        arrow = {"up": "▲ ", "down": "▼ "}.get(d, "")
        return arrow + str(v.get("label", "")), tone
    n = fmt.to_num(v)
    if n is None:
        return str(v or ""), "flat"
    d = "up" if n > 0 else ("down" if n < 0 else "flat")
    good = col.get("good", "up")
    tone = "flat" if d == "flat" else ("good" if d == good else "bad")
    return ("+" if n > 0 else "") + fmt_value(n, col.get("unit", "%")), tone


def _bezier(p0, p1, p2, p3, steps=20):
    out = []
    for i in range(steps + 1):
        t = i / float(steps)
        a = (1 - t) ** 3
        b = 3 * (1 - t) ** 2 * t
        c = 3 * (1 - t) * t ** 2
        d = t ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def build_pptx(summary, path, theme=None, embed_fonts=True):
    key = pick_theme(theme, summary)
    deck = Deck(summary, key)
    prs = deck.build()
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    prs.save(path)
    if embed_fonts:
        try:
            from .pptx_fonts import embed_fonts as _embed
            fams = []
            for role in ("display", "numeral", "body", "strong", "label", "mono"):
                f = deck.fonts.get(role)
                if f and f["pptx"] not in fams:
                    fams.append(f["pptx"])
            _embed(path, fams)
        except Exception as exc:  # embedding is a bonus; never fail the deck
            import sys
            sys.stderr.write("pptx: fonts not embedded (%s)\n" % exc)
    return path
