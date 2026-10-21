"""
SVG charts for the report engine.

Vector output, so charts stay razor sharp in the PDF and at any zoom. Every chart
follows the same mark rules in every theme:

  * bars and columns are at most 24px thick, grow from one baseline, and have a
    rounded data end (radius from the theme) with a square base
  * lines are 2px with round joins; markers are r>=4 with a 2px ring in the panel
    color; area fills are a 10% wash of the series color
  * gridlines are solid hairlines one step off the panel; there is never a second
    y-axis
  * text wears text colors, never the series color; labels are selective (peak,
    last value, the one bar the story is about)

Each renderer returns {"svg": str, "legend": [...], "height": int, "table": (head, rows)}.
"""
import math

from . import fmt
from .measure import text_width

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _f(x):
    return ("%.2f" % x).rstrip("0").rstrip(".")


class Ctx(object):
    """Resolved theme values a chart needs, plus a text measurer."""

    def __init__(self, theme, size=12.0):
        tk = theme["tokens"]
        self.tk = tk
        self.series = list(tk["series"])
        self.panel = tk["panel"]
        self.grid = tk["grid"]
        self.axis = tk["axis"]
        self.text = tk["chart_text"]
        self.ink = tk["ink"]
        self.ink2 = tk["ink2"]
        self.neutral = tk.get("neutral", "#C9CED8")
        self.round = theme["style"].get("bar_round", 4)
        lab = theme["fonts"].get("chart") or theme["fonts"]["label"]
        self.family = lab["css"]
        self.weight = lab.get("weight", 400)
        self.size = size
        self.dark = tk.get("dark", False)
        self.key = theme["key"]

    def tw(self, s, size=None, weight=None):
        return text_width(s, self.family, size or self.size, weight or self.weight)

    def color(self, i):
        if i < len(self.series):
            return self.series[i]
        return self.neutral


def _txt(x, y, s, cls="ct", anchor="start", fill=None, size=None, weight=None, extra=""):
    attrs = ['x="%s"' % _f(x), 'y="%s"' % _f(y), 'class="%s"' % cls]
    if anchor != "start":
        attrs.append('text-anchor="%s"' % anchor)
    if fill:
        attrs.append('fill="%s"' % fill)
    if size:
        attrs.append('font-size="%s"' % _f(size))
    if weight:
        attrs.append('font-weight="%s"' % weight)
    if extra:
        attrs.append(extra)
    return "<text %s>%s</text>" % (" ".join(attrs), esc(s))


def bar_path(x, y, w, h, r, end="top"):
    """Rectangle with only the data end rounded. end in top|bottom|right|left."""
    if w <= 0 or h <= 0:
        return ""
    r = max(0.0, min(r, w / 2.0 if end in ("top", "bottom") else h / 2.0,
                     h if end in ("top", "bottom") else w))
    x2, y2 = x + w, y + h
    if r <= 0.01:
        return "M%s %sH%sV%sH%sZ" % (_f(x), _f(y), _f(x2), _f(y2), _f(x))
    if end == "top":
        return ("M%s %sV%sQ%s %s %s %sH%sQ%s %s %s %sV%sZ" %
                (_f(x), _f(y2), _f(y + r), _f(x), _f(y), _f(x + r), _f(y), _f(x2 - r),
                 _f(x2), _f(y), _f(x2), _f(y + r), _f(y2)))
    if end == "bottom":
        return ("M%s %sV%sQ%s %s %s %sH%sQ%s %s %s %sV%sZ" %
                (_f(x), _f(y), _f(y2 - r), _f(x), _f(y2), _f(x + r), _f(y2), _f(x2 - r),
                 _f(x2), _f(y2), _f(x2), _f(y2 - r), _f(y)))
    if end == "right":
        return ("M%s %sH%sQ%s %s %s %sV%sQ%s %s %s %sH%sZ" %
                (_f(x), _f(y), _f(x2 - r), _f(x2), _f(y), _f(x2), _f(y + r), _f(y2 - r),
                 _f(x2), _f(y2), _f(x2 - r), _f(y2), _f(x)))
    # left
    return ("M%s %sH%sQ%s %s %s %sV%sQ%s %s %s %sH%sZ" %
            (_f(x2), _f(y), _f(x + r), _f(x), _f(y), _f(x), _f(y + r), _f(y2 - r),
             _f(x), _f(y2), _f(x + r), _f(y2), _f(x2)))


def _svg(width, height, body, label=""):
    return ('<svg class="chart-svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img" '
            'aria-label="%s" preserveAspectRatio="xMidYMid meet">%s</svg>' %
            (width, height, width, height, esc(label), "".join(body)))


def fmt_value(v, unit=None, decimals=None):
    if v is None:
        return ""
    if unit == "%":
        return fmt.pct(v, decimals if decimals is not None else (0 if abs(v) >= 10 or v == int(v) else 1))
    if unit in ("$", "money", "usd"):
        return fmt.money(v)
    if unit == "x":
        return "%sx" % fmt._trim(v, 1)
    if decimals is not None:
        return fmt.num(v, decimals)
    return fmt.compact(v)


def _nums(vals):
    out = []
    for v in vals or []:
        n = fmt.to_num(v, 0.0)
        out.append(n if n is not None else 0.0)
    return out


def _label_stride(labels, band, ctx, size):
    """Show every k-th category label so labels never collide."""
    if not labels:
        return 1
    widest = max(ctx.tw(l, size) for l in labels) + 10
    k = 1
    while widest > band * k and k < len(labels):
        k += 1
    return k


def _x_labels(labels, x_of, ctx, size, y, x_min, x_max):
    """Category labels along a continuous axis at an even stride. The first and
    last labels are always shown; a label that would touch the last one is dropped."""
    n = len(labels)
    if not n:
        return []
    gap = size * 1.1
    widest = max(ctx.tw(l, size) for l in labels)
    step_px = (x_of(n - 1) - x_of(0)) / max(1, n - 1) if n > 1 else widest
    stride = 1
    while stride < n and step_px * stride < widest + gap:
        stride += 1
    idx = list(range(0, n, stride))
    last_w = ctx.tw(labels[n - 1], size)
    if idx[-1] != n - 1:
        while idx and x_of(n - 1) - last_w - gap < x_of(idx[-1]) + ctx.tw(labels[idx[-1]], size) / 2:
            idx.pop()
        idx.append(n - 1)
    def box(i):
        w = ctx.tw(labels[i], size)
        x = x_of(i)
        if i == 0:
            return (x, x + w)
        if i == n - 1:
            return (x - w, x)
        return (x - w / 2, x + w / 2)

    keep = []
    for i in idx:
        b = box(i)
        if keep and b[0] < box(keep[-1])[1] + gap:
            if i == n - 1:
                keep.pop()
            else:
                continue
        keep.append(i)
    out = []
    for i in keep:
        x = x_of(i)
        anchor = "middle"
        if i == 0:
            anchor = "start"
        elif i == n - 1:
            anchor = "end"
        out.append(_txt(x, y, labels[i], "ct ct-x", anchor, ctx.text, size))
    return out


def _wrap(label, max_w, ctx, size, max_lines=3):
    """Word-wrap a category label to at most max_lines lines of max_w px."""
    words = str(label).split()
    if not words:
        return [""]
    lines, cur = [], words[0]
    for w in words[1:]:
        if ctx.tw(cur + " " + w, size) <= max_w:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines - 1] + [" ".join(lines[max_lines - 1:])]
    return lines


def _y_axis(ctx, ticks, x0, x1, y_of, unit, body, size):
    for t in ticks:
        y = y_of(t)
        body.append('<line x1="%s" x2="%s" y1="%s" y2="%s" stroke="%s" stroke-width="1"/>' %
                    (_f(x0), _f(x1), _f(y), _f(y), ctx.axis if t == 0 else ctx.grid))
        body.append(_txt(x0 - 8, y + size * 0.35, fmt_value(t, unit), "ct ct-tick", "end",
                         ctx.text, size))


def _gutter(ctx, ticks, unit, size):
    return max(ctx.tw(fmt_value(t, unit), size) for t in ticks) + 12 if ticks else 30


# ---------------------------------------------------------------------------
# Column charts (single, stacked, grouped)
# ---------------------------------------------------------------------------
def columns(spec, ctx, width, height):
    labels = [str(l) for l in spec.get("labels", [])]
    unit = spec.get("unit")
    size = ctx.size
    stacks = spec.get("stacks")
    groups = spec.get("groups")
    if stacks:
        series = [{"label": s.get("label", ""), "values": _nums(s.get("values"))} for s in stacks]
        mode = "stacked"
    elif groups:
        series = [{"label": s.get("label", ""), "values": _nums(s.get("values"))} for s in groups]
        mode = "grouped"
    else:
        series = [{"label": spec.get("series_label", ""), "values": _nums(spec.get("values"))}]
        mode = "single"
    n = len(labels)
    if n == 0:
        return empty(ctx, width, height)
    if mode == "stacked":
        totals = [sum(s["values"][i] if i < len(s["values"]) else 0 for s in series) for i in range(n)]
        vmax = max(totals) if totals else 1
    else:
        vmax = max(max(s["values"] or [0]) for s in series)
    vmin = min(0.0, min(min(s["values"] or [0]) for s in series))
    ticks = fmt.axis_ticks(vmax * 1.08 if vmax > 0 else 1, vmin)
    top_pad = size * 2.0
    bottom = size * 2.6
    left = _gutter(ctx, ticks, unit, size)
    right = 8
    plot_w = width - left - right
    plot_h = height - top_pad - bottom
    t0, t1 = ticks[0], ticks[-1]

    def y_of(v):
        return top_pad + plot_h * (1 - (v - t0) / (t1 - t0 if t1 != t0 else 1))

    band = plot_w / n
    body = []
    _y_axis(ctx, ticks, left, width - right, y_of, unit, body, size)
    highlight = spec.get("highlight")
    if mode == "grouped":
        k = len(series)
        bar_w = min(24.0, (band * 0.72 - 2 * (k - 1)) / k)
        cluster = bar_w * k + 2 * (k - 1)
    else:
        bar_w = min(24.0 if n > 6 else 40.0, band * 0.62)
        cluster = bar_w
    base = y_of(0)
    for i, lab in enumerate(labels):
        cx = left + band * i + band / 2
        if mode == "stacked":
            acc = 0.0
            segs = [(j, s["values"][i] if i < len(s["values"]) else 0.0) for j, s in enumerate(series)]
            segs = [(j, v) for j, v in segs if v > 0]
            for idx, (j, v) in enumerate(segs):
                y_top = y_of(acc + v)
                y_bot = y_of(acc)
                gap = 2 if idx > 0 else 0
                h = max(0.0, y_bot - y_top - gap)
                last = idx == len(segs) - 1
                d = bar_path(cx - bar_w / 2, y_top, bar_w, h, ctx.round if last else 0, "top")
                body.append('<path d="%s" fill="%s" data-tip="%s"/>' %
                            (d, ctx.color(j), esc("%s · %s: %s" % (lab, series[j]["label"], fmt_value(v, unit)))))
                acc += v
        elif mode == "grouped":
            x = cx - cluster / 2
            for j, s in enumerate(series):
                v = s["values"][i] if i < len(s["values"]) else 0.0
                y_top = y_of(max(v, 0))
                h = abs(y_of(v) - base)
                d = bar_path(x, min(y_top, base), bar_w, h, ctx.round, "top" if v >= 0 else "bottom")
                body.append('<path d="%s" fill="%s" data-tip="%s"/>' %
                            (d, ctx.color(j), esc("%s · %s: %s" % (lab, s["label"], fmt_value(v, unit)))))
                x += bar_w + 2
        else:
            v = series[0]["values"][i] if i < len(series[0]["values"]) else 0.0
            col = ctx.color(0)
            if highlight is not None and highlight != i and highlight != lab:
                col = ctx.neutral
            y_top = y_of(max(v, 0))
            h = abs(y_of(v) - base)
            d = bar_path(cx - bar_w / 2, min(y_top, base), bar_w, h, ctx.round, "top" if v >= 0 else "bottom")
            body.append('<path d="%s" fill="%s" data-tip="%s"/>' %
                        (d, col, esc("%s: %s" % (lab, fmt_value(v, unit)))))
            show_val = spec.get("show_values", n <= 14)
            if show_val:
                body.append(_txt(cx, y_top - 6, fmt_value(v, unit), "ct ct-val", "middle", ctx.ink2, size * 0.95))
    stride = _label_stride(labels, band, ctx, size)
    for i, lab in enumerate(labels):
        if i % stride:
            continue
        cx = left + band * i + band / 2
        body.append(_txt(cx, height - bottom + size * 1.55, lab, "ct ct-x", "middle", ctx.text, size))
    legend = []
    if mode != "single":
        legend = [(s["label"], ctx.color(j)) for j, s in enumerate(series)]
    head = ["Label"] + ([s["label"] for s in series] if mode != "single" else [spec.get("series_label") or "Value"])
    rows = [[lab] + [fmt_value(s["values"][i] if i < len(s["values"]) else 0, unit) for s in series]
            for i, lab in enumerate(labels)]
    return {"svg": _svg(width, height, body, spec.get("title", "")), "legend": legend,
            "height": height, "table": (head, rows)}


# ---------------------------------------------------------------------------
# Lines and areas (one or many series, optional forecast band)
# ---------------------------------------------------------------------------
def lines(spec, ctx, width, height):
    labels = [str(l) for l in spec.get("labels", [])]
    unit = spec.get("unit")
    size = ctx.size
    filled = spec.get("type") in ("area",)
    if spec.get("series"):
        series = [{"label": s.get("label", ""), "values": [fmt.to_num(v) if v is not None else None
                                                           for v in s.get("values", [])],
                   "style": s.get("style", "solid")} for s in spec["series"]]
    else:
        series = [{"label": spec.get("series_label", ""),
                   "values": [fmt.to_num(v) if v is not None else None for v in spec.get("values", [])],
                   "style": "solid"}]
    n = len(labels)
    if n == 0:
        return empty(ctx, width, height)
    band = spec.get("band") or {}
    allv = [v for s in series for v in s["values"] if v is not None]
    allv += [fmt.to_num(v, 0) for v in band.get("upper", []) or [] if v is not None]
    vmax = max(allv) if allv else 1
    vmin = min(0.0, min(allv) if allv else 0)
    ticks = fmt.axis_ticks(vmax * 1.1 if vmax > 0 else 1, vmin)
    top_pad = size * 2.2
    bottom = size * 2.6
    left = _gutter(ctx, ticks, unit, size)
    right_pad = 12
    if spec.get("end_labels", len(series) > 1):
        right_pad = max(right_pad, max(ctx.tw(s["label"], size) for s in series) + 22)
    plot_w = width - left - right_pad
    plot_h = height - top_pad - bottom
    t0, t1 = ticks[0], ticks[-1]

    def y_of(v):
        return top_pad + plot_h * (1 - (v - t0) / (t1 - t0 if t1 != t0 else 1))

    def x_of(i):
        return left + (plot_w * i / (n - 1) if n > 1 else plot_w / 2)

    body = []
    _y_axis(ctx, ticks, left, left + plot_w, y_of, unit, body, size)
    # forecast band
    if band.get("upper") and band.get("lower"):
        up = [fmt.to_num(v) for v in band["upper"]]
        lo = [fmt.to_num(v) for v in band["lower"]]
        pts_u = [(x_of(i), y_of(v)) for i, v in enumerate(up) if v is not None]
        idx_l = [i for i, v in enumerate(lo) if v is not None]
        pts_l = [(x_of(i), y_of(lo[i])) for i in reversed(idx_l)]
        if pts_u and pts_l:
            d = "M" + " L".join("%s %s" % (_f(x), _f(y)) for x, y in pts_u + pts_l) + "Z"
            body.append('<path d="%s" fill="%s" fill-opacity="0.14"/>' % (d, ctx.color(0)))
    fstart = spec.get("forecast_start")
    if fstart is not None and 0 < fstart < n:
        fx = x_of(fstart - 0.5) if fstart > 0 else x_of(0)
        body.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s" fill-opacity="%s"/>' %
                    (_f(fx), _f(top_pad), _f(left + plot_w - fx), _f(plot_h), ctx.grid,
                     "0.55" if not ctx.dark else "0.35"))
        body.append(_txt(fx + 8, top_pad + size * 1.2, spec.get("forecast_label", "Forecast"),
                         "ct ct-note", "start", ctx.text, size * 0.95))
    legend = []
    end_labels = []
    for j, s in enumerate(series):
        col = ctx.color(j)
        pts = [(x_of(i), y_of(v), v, i) for i, v in enumerate(s["values"]) if v is not None]
        if not pts:
            continue
        legend.append((s["label"], col))
        if filled or (len(series) == 1 and spec.get("fill", True)):
            d = ("M%s %s " % (_f(pts[0][0]), _f(y_of(max(0, t0))))) + \
                " ".join("L%s %s" % (_f(x), _f(y)) for x, y, _, _ in pts) + \
                " L%s %sZ" % (_f(pts[-1][0]), _f(y_of(max(0, t0))))
            body.append('<path d="%s" fill="%s" fill-opacity="0.10"/>' % (d, col))
        segs = []
        if fstart is not None and s.get("style") != "dashed":
            solid = [p for p in pts if p[3] < fstart]
            dashed = [p for p in pts if p[3] >= fstart - 1]
            segs = [(solid, False), (dashed, True)]
        else:
            segs = [(pts, s.get("style") == "dashed")]
        for seg, dashed in segs:
            if len(seg) < 2:
                continue
            d = "M" + " L".join("%s %s" % (_f(x), _f(y)) for x, y, _, _ in seg)
            body.append('<path d="%s" fill="none" stroke="%s" stroke-width="2" stroke-linejoin="round" '
                        'stroke-linecap="round"%s/>' % (d, col, ' stroke-dasharray="5 5"' if dashed else ""))
        # hover targets
        for x, y, v, i in pts:
            body.append('<circle cx="%s" cy="%s" r="9" fill="transparent" data-tip="%s"/>' %
                        (_f(x), _f(y), esc("%s · %s%s" % (labels[i], fmt_value(v, unit),
                                                           (" · " + s["label"]) if s["label"] else ""))))
        # end marker + selective labels
        lx, ly, lv, li = pts[-1]
        body.append('<circle cx="%s" cy="%s" r="4.5" fill="%s" stroke="%s" stroke-width="2"/>' %
                    (_f(lx), _f(ly), col, ctx.panel))
        if len(series) > 1 and spec.get("end_labels", True):
            end_labels.append([ly, s["label"], col, lx])
        elif len(series) == 1:
            body.append(_txt(lx - 2, ly - 12, fmt_value(lv, unit), "ct ct-val ct-strong", "end", ctx.ink, size))
            if spec.get("annotate_peak", True) and len(pts) > 4:
                pk = max(pts, key=lambda p: p[2])
                if pk[3] != li and pk[3] != 0:
                    body.append('<circle cx="%s" cy="%s" r="4.5" fill="%s" stroke="%s" stroke-width="2"/>' %
                                (_f(pk[0]), _f(pk[1]), col, ctx.panel))
                    lab = "Peak %s · %s" % (fmt_value(pk[2], unit), labels[pk[3]])
                    tw = ctx.tw(lab, size * 0.95)
                    tx = min(max(pk[0], left + tw / 2), left + plot_w - tw / 2)
                    body.append(_txt(tx, pk[1] - 12, lab, "ct ct-note", "middle", ctx.ink2, size * 0.95))
    # end labels for multi-series, nudged apart with leader lines
    if end_labels:
        end_labels.sort(key=lambda e: e[0])
        min_gap = size * 1.25
        for k in range(1, len(end_labels)):
            if end_labels[k][0] - end_labels[k - 1][0] < min_gap:
                end_labels[k][0] = end_labels[k - 1][0] + min_gap
        for y, lab, col, lx in end_labels:
            body.append(_txt(lx + 12, y + size * 0.35, lab, "ct ct-end", "start", ctx.ink2, size))
    body.extend(_x_labels(labels, x_of, ctx, size, height - bottom + size * 1.55, left, left + plot_w))
    head = ["Label"] + [s["label"] or "Value" for s in series]
    rows = [[lab] + [fmt_value(s["values"][i], unit) if i < len(s["values"]) and s["values"][i] is not None else ""
                     for s in series] for i, lab in enumerate(labels)]
    if len(series) == 1:
        legend = []
    return {"svg": _svg(width, height, body, spec.get("title", "")), "legend": legend,
            "height": height, "table": (head, rows)}


# ---------------------------------------------------------------------------
# Donut
# ---------------------------------------------------------------------------
def donut(spec, ctx, size_px=220, center_value=None, center_label=None):
    labels = [str(l) for l in spec.get("labels", [])]
    vals = _nums(spec.get("values"))
    pairs = [(l, v) for l, v in zip(labels, vals) if v > 0]
    total = sum(v for _, v in pairs) or 1.0
    max_slices = min(6, len(ctx.series))
    if len(pairs) > max_slices:
        head = pairs[:max_slices - 1]
        rest = sum(v for _, v in pairs[max_slices - 1:])
        pairs = head + [("Other", rest)]
    cx = cy = size_px / 2.0
    R = size_px / 2.0 - 2
    thick = R * 0.26
    r = R - thick / 2
    body = []
    a0 = -math.pi / 2
    gap = 0.012 if len(pairs) > 1 else 0
    legend = []
    for i, (lab, v) in enumerate(pairs):
        frac = v / total
        col = ctx.neutral if lab == "Other" else ctx.color(i)
        a1 = a0 + frac * 2 * math.pi
        s, e = a0 + gap, a1 - gap
        if e > s:
            large = 1 if (e - s) > math.pi else 0
            x0, y0 = cx + r * math.cos(s), cy + r * math.sin(s)
            x1, y1 = cx + r * math.cos(e), cy + r * math.sin(e)
            if len(pairs) == 1:
                body.append('<circle cx="%s" cy="%s" r="%s" fill="none" stroke="%s" stroke-width="%s"/>' %
                            (_f(cx), _f(cy), _f(r), col, _f(thick)))
            else:
                body.append('<path d="M%s %s A%s %s 0 %d 1 %s %s" fill="none" stroke="%s" stroke-width="%s" '
                            'data-tip="%s"/>' % (_f(x0), _f(y0), _f(r), _f(r), large, _f(x1), _f(y1), col,
                                                 _f(thick), esc("%s: %s (%s)" % (lab, fmt_value(v, spec.get("unit") if spec.get("unit") != "%" else None),
                                                                                  fmt.pct(100 * frac)))))
        legend.append((lab, col, v, 100.0 * frac))
        a0 = a1
    cv = center_value if center_value is not None else spec.get("center_value")
    cl = center_label if center_label is not None else spec.get("center_label")
    if cv is not None:
        body.append(_txt(cx, cy + 4, cv, "ct-center", "middle", ctx.ink))
        if cl:
            body.append(_txt(cx, cy + 24, cl, "ct ct-center-label", "middle", ctx.text))
    head = ["Segment", "Value", "Share"]
    rows = [[l, fmt_value(v, spec.get("unit") if spec.get("unit") != "%" else None), fmt.pct(p)]
            for l, _, v, p in legend]
    return {"svg": _svg(size_px, size_px, body, spec.get("title", "")), "legend": legend,
            "height": size_px, "table": (head, rows)}


# ---------------------------------------------------------------------------
# Waterfall
# ---------------------------------------------------------------------------
def waterfall(spec, ctx, width, height):
    steps = spec.get("steps") or []
    unit = spec.get("unit")
    size = ctx.size
    if not steps:
        return empty(ctx, width, height)
    running = 0.0
    bars = []
    for s in steps:
        v = fmt.to_num(s.get("value"), 0.0)
        kind = s.get("kind", "delta")
        if kind in ("start", "total"):
            lo, hi = 0.0, v
            running = v
        else:
            lo, hi = running, running + v
            running += v
        bars.append((s.get("label", ""), kind, v, min(lo, hi), max(lo, hi)))
    vmax = max(b[4] for b in bars)
    vmin = min(0.0, min(b[3] for b in bars))
    ticks = fmt.axis_ticks(vmax * 1.12 if vmax > 0 else 1, vmin)
    top_pad, bottom = size * 2.0, size * 4.4
    left = _gutter(ctx, ticks, unit, size)
    plot_w = width - left - 8
    plot_h = height - top_pad - bottom
    t0, t1 = ticks[0], ticks[-1]

    def y_of(v):
        return top_pad + plot_h * (1 - (v - t0) / (t1 - t0 if t1 != t0 else 1))

    body = []
    _y_axis(ctx, ticks, left, width - 8, y_of, unit, body, size)
    n = len(bars)
    band = plot_w / n
    bw = min(56.0, band * 0.58)
    prev_top = None
    for i, (lab, kind, v, lo, hi) in enumerate(bars):
        cx = left + band * i + band / 2
        if kind in ("start", "total"):
            col = ctx.color(0)
        else:
            col = ctx.tk["good"] if v >= 0 else ctx.tk["bad"]
        y1, y2 = y_of(hi), y_of(lo)
        d = bar_path(cx - bw / 2, y1, bw, max(1.0, y2 - y1), min(ctx.round, 3), "top")
        body.append('<path d="%s" fill="%s"%s data-tip="%s"/>' %
                    (d, col, ' fill-opacity="0.85"' if kind == "delta" else "",
                     esc("%s: %s" % (lab, fmt_value(v, unit)))))
        sign = ""
        if kind == "delta":
            sign = "+" if v > 0 else ""
        body.append(_txt(cx, y1 - 7, sign + fmt_value(v, unit), "ct ct-val ct-strong", "middle", ctx.ink, size))
        if prev_top is not None:
            body.append('<line x1="%s" x2="%s" y1="%s" y2="%s" stroke="%s" stroke-width="1"/>' %
                        (_f(prev_top[0]), _f(cx - bw / 2), _f(prev_top[1]), _f(prev_top[1]), ctx.axis))
        run_y = y_of(hi if (kind in ("start", "total") or v >= 0) else lo)
        prev_top = (cx + bw / 2, run_y)
    lab_size = size if band >= 70 else size * 0.9
    for i, (lab, _, _, _, _) in enumerate(bars):
        cx = left + band * i + band / 2
        for k, line in enumerate(_wrap(lab, band - 6, ctx, lab_size, 3)):
            body.append(_txt(cx, height - bottom + lab_size * (1.5 + 1.2 * k), line, "ct ct-x", "middle", ctx.text, lab_size))
    head = ["Step", "Value"]
    rows = [[b[0], fmt_value(b[2], unit)] for b in bars]
    return {"svg": _svg(width, height, body, spec.get("title", "")), "legend": [], "height": height,
            "table": (head, rows)}


# ---------------------------------------------------------------------------
# Diverging horizontal bars (change vs a baseline)
# ---------------------------------------------------------------------------
def diverging(spec, ctx, width, row_h=30):
    labels = [str(l) for l in spec.get("labels", [])]
    vals = _nums(spec.get("values"))
    unit = spec.get("unit")
    size = ctx.size
    n = len(labels)
    if not n:
        return empty(ctx, width, 120)
    lab_w = min(width * 0.34, max(ctx.tw(l, size) for l in labels) + 14)
    val_w = max(ctx.tw(("+" if v > 0 else "") + fmt_value(v, unit), size) for v in vals) + 10
    plot_x0 = lab_w + val_w
    plot_x1 = width - val_w
    vmax = max(abs(v) for v in vals) or 1
    mid = (plot_x0 + plot_x1) / 2
    half = (plot_x1 - plot_x0) / 2
    height = int(n * row_h + size * 1.2)
    body = ['<line x1="%s" x2="%s" y1="0" y2="%s" stroke="%s" stroke-width="1"/>' %
            (_f(mid), _f(mid), _f(height - 4), ctx.axis)]
    good_up = spec.get("good", "up") == "up"
    for i, (lab, v) in enumerate(zip(labels, vals)):
        y = i * row_h + 6
        bh = min(18.0, row_h - 10)
        w = half * abs(v) / vmax
        positive = v >= 0
        is_good = positive if good_up else not positive
        col = ctx.color(0) if is_good else ctx.tk["bad"]
        if positive:
            d = bar_path(mid, y, w, bh, ctx.round, "right")
            vx, anchor = mid + w + 6, "start"
        else:
            d = bar_path(mid - w, y, w, bh, ctx.round, "left")
            vx, anchor = mid - w - 6, "end"
        body.append('<path d="%s" fill="%s" data-tip="%s"/>' % (d, col, esc("%s: %s" % (lab, fmt_value(v, unit)))))
        body.append(_txt(0, y + bh / 2 + size * 0.36, lab, "ct ct-cat", "start", ctx.ink2, size))
        body.append(_txt(vx, y + bh / 2 + size * 0.36, ("+" if v > 0 else "") + fmt_value(v, unit),
                         "ct ct-val ct-strong", anchor, ctx.ink, size))
    head = ["Label", "Change"]
    rows = [[l, fmt_value(v, unit)] for l, v in zip(labels, vals)]
    return {"svg": _svg(width, height, body, spec.get("title", "")), "legend": [], "height": height,
            "table": (head, rows)}


# ---------------------------------------------------------------------------
# Scatter / quadrant map
# ---------------------------------------------------------------------------
def scatter(spec, ctx, width, height):
    pts = spec.get("points") or []
    size = ctx.size
    if not pts:
        return empty(ctx, width, height)
    xs = [fmt.to_num(p.get("x"), 0.0) for p in pts]
    ys = [fmt.to_num(p.get("y"), 0.0) for p in pts]
    ss = [fmt.to_num(p.get("size"), 1.0) for p in pts]
    xu, yu = spec.get("x_unit"), spec.get("y_unit")
    xt = fmt.axis_ticks(max(xs) * 1.1 if max(xs) > 0 else 1, min(0.0, min(xs)))
    yt = fmt.axis_ticks(max(ys) * 1.12 if max(ys) > 0 else 1, min(0.0, min(ys)))
    left = _gutter(ctx, yt, yu, size) + size * 1.4
    top, right, bottom = size * 1.2, 16, size * 4.0
    pw, ph = width - left - right, height - top - bottom

    def X(v):
        return left + pw * (v - xt[0]) / ((xt[-1] - xt[0]) or 1)

    def Y(v):
        return top + ph * (1 - (v - yt[0]) / ((yt[-1] - yt[0]) or 1))

    body = []
    for t in yt:
        body.append('<line x1="%s" x2="%s" y1="%s" y2="%s" stroke="%s"/>' % (_f(left), _f(left + pw), _f(Y(t)), _f(Y(t)), ctx.grid))
        body.append(_txt(left - 8, Y(t) + size * 0.35, fmt_value(t, yu), "ct ct-tick", "end", ctx.text, size))
    for t in xt:
        body.append('<line x1="%s" x2="%s" y1="%s" y2="%s" stroke="%s"/>' % (_f(X(t)), _f(X(t)), _f(top), _f(top + ph), ctx.grid))
        body.append(_txt(X(t), top + ph + size * 1.5, fmt_value(t, xu), "ct ct-tick", "middle", ctx.text, size))
    # axis titles
    if spec.get("x_label"):
        body.append(_txt(left + pw / 2, height - size * 0.6, spec["x_label"], "ct ct-axis-title", "middle", ctx.ink2, size))
    if spec.get("y_label"):
        body.append('<text class="ct ct-axis-title" fill="%s" text-anchor="middle" transform="translate(%s %s) rotate(-90)">%s</text>' %
                    (ctx.ink2, _f(size * 0.95), _f(top + ph / 2), esc(spec["y_label"])))
    # quadrant reference lines
    xr, yr = spec.get("x_ref"), spec.get("y_ref")
    if xr is not None:
        body.append('<line x1="%s" x2="%s" y1="%s" y2="%s" stroke="%s" stroke-width="1.2"/>' % (_f(X(xr)), _f(X(xr)), _f(top), _f(top + ph), ctx.axis))
    if yr is not None:
        body.append('<line x1="%s" x2="%s" y1="%s" y2="%s" stroke="%s" stroke-width="1.2"/>' % (_f(left), _f(left + pw), _f(Y(yr)), _f(Y(yr)), ctx.axis))
    q = spec.get("quadrants") or {}
    pad = 10
    corner = {"tl": (left + pad, top + size * 1.3, "start"), "tr": (left + pw - pad, top + size * 1.3, "end"),
              "bl": (left + pad, top + ph - pad, "start"), "br": (left + pw - pad, top + ph - pad, "end")}
    placed = []
    quad_txt = []
    for k, txt in q.items():
        if k in corner and txt:
            x, y, a = corner[k]
            w = ctx.tw(txt, size)
            x0 = x if a == "start" else x - w
            placed.append((x0 - 4, y - size - 2, x0 + w + 4, y + 4))
            quad_txt.append(_txt(x, y, txt, "ct ct-quad", a, ctx.tk.get("ink3", ctx.text), size))
    smax = max(ss) or 1
    groups = []
    for p in pts:
        g = p.get("group")
        if g is not None and g not in groups:
            groups.append(g)
    order = sorted(range(len(pts)), key=lambda i: -ss[i])
    for i in order:
        p = pts[i]
        r = 5 + 13 * math.sqrt(ss[i] / smax)
        gi = groups.index(p.get("group")) if p.get("group") in groups else 0
        col = ctx.color(gi) if groups else ctx.color(0)
        if p.get("muted"):
            col = ctx.neutral
        body.append('<circle cx="%s" cy="%s" r="%s" fill="%s" fill-opacity="0.78" stroke="%s" stroke-width="2" data-tip="%s"/>' %
                    (_f(X(xs[i])), _f(Y(ys[i])), _f(r), col, ctx.panel,
                     esc("%s · %s %s · %s %s" % (p.get("label", ""), spec.get("x_label", "x"), fmt_value(xs[i], xu),
                                                  spec.get("y_label", "y"), fmt_value(ys[i], yu)))))
    for i in order:
        rr = 5 + 13 * math.sqrt(ss[i] / smax)
        placed.append((X(xs[i]) - rr, Y(ys[i]) - rr, X(xs[i]) + rr, Y(ys[i]) + rr))
    for i in order:
        p = pts[i]
        if not p.get("label") or p.get("hide_label"):
            continue
        r = 5 + 13 * math.sqrt(ss[i] / smax)
        lab = p["label"]
        w = ctx.tw(lab, size * 0.95)
        cands = [(X(xs[i]) + r + 5, Y(ys[i]) + size * 0.35, "start"),
                 (X(xs[i]) - r - 5, Y(ys[i]) + size * 0.35, "end"),
                 (X(xs[i]), Y(ys[i]) - r - 6, "middle"),
                 (X(xs[i]), Y(ys[i]) + r + size + 2, "middle")]
        for x, y, a in cands:
            x0 = x if a == "start" else (x - w if a == "end" else x - w / 2)
            box = (x0, y - size, x0 + w, y + 3)
            if box[0] < left or box[2] > left + pw or box[1] < top or box[3] > top + ph:
                continue
            own = (X(xs[i]) - r, Y(ys[i]) - r, X(xs[i]) + r, Y(ys[i]) + r)
            if any(b != own and not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]) for b in placed):
                continue
            placed.append(box)
            body.append(_txt(x, y, lab, "ct ct-pt", a, ctx.ink2, size * 0.95))
            break
    body.extend(quad_txt)
    legend = [(g, ctx.color(k)) for k, g in enumerate(groups)] if len(groups) > 1 else []
    head = ["Item", spec.get("x_label", "x"), spec.get("y_label", "y")]
    rows = [[p.get("label", ""), fmt_value(xs[i], xu), fmt_value(ys[i], yu)] for i, p in enumerate(pts)]
    return {"svg": _svg(width, height, body, spec.get("title", "")), "legend": legend, "height": height,
            "table": (head, rows)}


# ---------------------------------------------------------------------------
# Sankey (two columns: e.g. first touch -> last touch)
# ---------------------------------------------------------------------------
def sankey(spec, ctx, width, height):
    links = [l for l in (spec.get("links") or []) if fmt.to_num(l.get("value"), 0) > 0]
    size = ctx.size
    if not links:
        return empty(ctx, width, height)
    left_nodes, right_nodes = [], []
    for l in links:
        if l["from"] not in left_nodes:
            left_nodes.append(l["from"])
        if l["to"] not in right_nodes:
            right_nodes.append(l["to"])
    if spec.get("left_order"):
        left_nodes = [n for n in spec["left_order"] if n in left_nodes] + [n for n in left_nodes if n not in spec["left_order"]]
    if spec.get("right_order"):
        right_nodes = [n for n in spec["right_order"] if n in right_nodes] + [n for n in right_nodes if n not in spec["right_order"]]
    lt = {n: sum(fmt.to_num(l["value"], 0) for l in links if l["from"] == n) for n in left_nodes}
    rt = {n: sum(fmt.to_num(l["value"], 0) for l in links if l["to"] == n) for n in right_nodes}
    total = sum(lt.values()) or 1
    unit = spec.get("unit")
    lab_l = max(ctx.tw("%s  %s" % (n, fmt_value(lt[n], unit)), size) for n in left_nodes) + 14
    lab_r = max(ctx.tw("%s  %s" % (n, fmt_value(rt[n], unit)), size) for n in right_nodes) + 14
    title_h = size * 2.0
    node_w = 12
    x_l = lab_l
    x_r = width - lab_r - node_w
    gap = 8
    avail_l = height - title_h - gap * (len(left_nodes) - 1) - 4
    avail_r = height - title_h - gap * (len(right_nodes) - 1) - 4
    k = min(avail_l, avail_r) / total
    body = []
    if spec.get("left_title"):
        body.append(_txt(x_l, size * 1.1, spec["left_title"], "ct ct-col-title", "start", ctx.ink2, size))
    if spec.get("right_title"):
        body.append(_txt(x_r + node_w, size * 1.1, spec["right_title"], "ct ct-col-title", "end", ctx.ink2, size))
    ypos_l, y = {}, title_h
    for n in left_nodes:
        ypos_l[n] = y
        y += lt[n] * k + gap
    ypos_r, y = {}, title_h
    for n in right_nodes:
        ypos_r[n] = y
        y += rt[n] * k + gap
    off_l = {n: 0.0 for n in left_nodes}
    off_r = {n: 0.0 for n in right_nodes}
    colors = {n: ctx.color(i) for i, n in enumerate(left_nodes)}
    links_sorted = sorted(links, key=lambda l: (left_nodes.index(l["from"]), right_nodes.index(l["to"])))
    for l in links_sorted:
        v = fmt.to_num(l["value"], 0) * k
        y0 = ypos_l[l["from"]] + off_l[l["from"]]
        y1 = ypos_r[l["to"]] + off_r[l["to"]]
        off_l[l["from"]] += v
        off_r[l["to"]] += v
        xa, xb = x_l + node_w, x_r
        mx = (xa + xb) / 2
        d = ("M%s %s C%s %s %s %s %s %s L%s %s C%s %s %s %s %s %sZ" %
             (_f(xa), _f(y0), _f(mx), _f(y0), _f(mx), _f(y1), _f(xb), _f(y1),
              _f(xb), _f(y1 + v), _f(mx), _f(y1 + v), _f(mx), _f(y0 + v), _f(xa), _f(y0 + v)))
        body.append('<path d="%s" fill="%s" fill-opacity="%s" data-tip="%s"/>' %
                    (d, colors[l["from"]], "0.34" if not ctx.dark else "0.42",
                     esc("%s → %s: %s" % (l["from"], l["to"], fmt_value(fmt.to_num(l["value"], 0), unit)))))
    for n in left_nodes:
        h = max(2.0, lt[n] * k)
        body.append('<rect x="%s" y="%s" width="%d" height="%s" rx="2" fill="%s"/>' % (_f(x_l), _f(ypos_l[n]), node_w, _f(h), colors[n]))
        body.append(_txt(x_l - 8, ypos_l[n] + h / 2 + size * 0.35, n, "ct ct-node", "end", ctx.ink, size))
        body.append(_txt(x_l - 8, ypos_l[n] + h / 2 + size * 1.55, fmt_value(lt[n], unit), "ct ct-node-val", "end", ctx.text, size * 0.92)
                    if h > size * 2.2 else "")
    for n in right_nodes:
        h = max(2.0, rt[n] * k)
        body.append('<rect x="%s" y="%s" width="%d" height="%s" rx="2" fill="%s"/>' % (_f(x_r), _f(ypos_r[n]), node_w, _f(h), ctx.ink2 if not ctx.dark else ctx.ink3 if hasattr(ctx, "ink3") else ctx.text))
        body.append(_txt(x_r + node_w + 8, ypos_r[n] + h / 2 + size * 0.35, n, "ct ct-node", "start", ctx.ink, size))
        body.append(_txt(x_r + node_w + 8, ypos_r[n] + h / 2 + size * 1.55, fmt_value(rt[n], unit), "ct ct-node-val", "start", ctx.text, size * 0.92)
                    if h > size * 2.2 else "")
    head = ["From", "To", "Value"]
    rows = [[l["from"], l["to"], fmt_value(fmt.to_num(l["value"], 0), unit)] for l in links_sorted]
    return {"svg": _svg(width, int(height), body, spec.get("title", "")), "legend": [], "height": height,
            "table": (head, rows)}


# ---------------------------------------------------------------------------
# Sparkline (KPI tiles, table cells)
# ---------------------------------------------------------------------------
def sparkline(values, ctx, width=120, height=32, color=None, fill=True, end_dot=True):
    vals = [fmt.to_num(v) for v in (values or [])]
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    pad = 3.5
    n = len(vals)

    def X(i):
        return pad + (width - 2 * pad) * i / (n - 1)

    def Y(v):
        return pad + (height - 2 * pad) * (1 - (v - lo) / span)

    col = color or ctx.color(0)
    d = "M" + " L".join("%s %s" % (_f(X(i)), _f(Y(v))) for i, v in enumerate(vals))
    body = []
    if fill:
        body.append('<path d="%s L%s %s L%s %sZ" fill="%s" fill-opacity="0.12"/>' %
                    (d, _f(X(n - 1)), _f(height), _f(X(0)), _f(height), col))
    body.append('<path d="%s" fill="none" stroke="%s" stroke-width="1.75" stroke-linejoin="round" stroke-linecap="round"/>' % (d, col))
    if end_dot:
        body.append('<circle cx="%s" cy="%s" r="3" fill="%s" stroke="%s" stroke-width="1.5"/>' %
                    (_f(X(n - 1)), _f(Y(vals[-1])), col, ctx.panel))
    return ('<svg class="spark" viewBox="0 0 %d %d" width="%d" height="%d" aria-hidden="true" '
            'preserveAspectRatio="none">%s</svg>' % (width, height, width, height, "".join(body)))


def empty(ctx, width, height, msg="No data in this period"):
    body = [_txt(width / 2, height / 2, msg, "ct ct-empty", "middle", ctx.text, ctx.size)]
    return {"svg": _svg(width, height, body, msg), "legend": [], "height": height, "table": (["", ""], [])}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
SVG_TYPES = {"bar-vertical", "bar-stacked", "bar-grouped", "line", "area", "line-multi",
             "doughnut", "donut", "pie", "waterfall", "bar-diverging", "scatter", "sankey"}


def render(spec, theme, width, height=None, size=12.0):
    ctx = Ctx(theme, size)
    t = (spec or {}).get("type", "bar-vertical")
    if t in ("bar-vertical", "bar-stacked", "bar-grouped", "column"):
        return columns(spec, ctx, width, height or 300)
    if t in ("line", "area", "line-multi"):
        return lines(spec, ctx, width, height or 300)
    if t in ("doughnut", "donut", "pie"):
        return donut(spec, ctx, int(height or 220))
    if t == "waterfall":
        return waterfall(spec, ctx, width, height or 320)
    if t == "bar-diverging":
        return diverging(spec, ctx, width)
    if t == "scatter":
        return scatter(spec, ctx, width, height or 380)
    if t == "sankey":
        return sankey(spec, ctx, width, height or 360)
    return columns(spec, ctx, width, height or 300)
