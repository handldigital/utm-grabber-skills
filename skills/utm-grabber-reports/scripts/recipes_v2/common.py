"""
Shared toolkit for v2 report recipes.

Every recipe is a pure function: inputs (UTM Grabber entries, plus optional
connector rows) -> a summary dict that matches references/report-schema.md.
Use these helpers so every report formats numbers, deltas, periods and empty
states the same way.
"""
import datetime as _dt
import os
import sys
from collections import Counter, OrderedDict

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_HERE)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from helpers import classify_traffic_source, get_field  # noqa: E402
from connectors import (first_touch_channel, lead_campaign, lead_content, lead_email,  # noqa: E402
                        lead_platform, lead_source_medium, lead_term, norm_key, sources_meta)

MINUS = "−"
CHANNELS = ["Paid", "Organic", "Social", "Referral", "Direct"]


def _read_version():
    try:
        with open(os.path.join(_SCRIPTS, "..", "VERSION.md")) as f:
            return f.read().strip()
    except Exception:
        return "2.0.0"


SKILL_VERSION = _read_version()

DEFAULT_BRAND = {
    "company_name": "UTM Grabber",
    "logo": {"type": "text", "value": "UTM Grabber"},
    "colors": {"primary": "#0160BF", "accent": "#2E90FA", "ink": "#0B1B34",
               "muted": "#64748B", "surface": "#F3F1FA"},
}


# ---------------------------------------------------------------------------
# meta + empty states
# ---------------------------------------------------------------------------
def meta(brand=None, customer_name=None, customer_domain="", compare_label=None, sources=None,
         prepared_by=None, prepared_for=None, theme=None, generated_at=None):
    brand = brand or DEFAULT_BRAND
    m = {
        "customer_name": customer_name or brand.get("company_name", ""),
        "customer_domain": customer_domain or "",
        "brand_profile": brand,
        "skill_version": SKILL_VERSION,
        "generated_at": generated_at or (_dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"),
    }
    if compare_label:
        m["compare_label"] = compare_label
    if sources:
        m["sources"] = sources
    if prepared_by:
        m["prepared_by"] = prepared_by
    if prepared_for:
        m["prepared_for"] = prepared_for
    if theme:
        m["theme"] = theme
    return m


def empty_report(report_name, m, reason="No form submissions in this period.", hint=None):
    return {"meta": m, "sections": [
        {"type": "title-block", "kicker": report_name, "title": "No *data* for this period yet.",
         "meta_bits": [m.get("customer_domain", "")] if m.get("customer_domain") else []},
        {"type": "insight-card", "kicker": "Why this is empty", "title": "We found no *submissions* to report on.",
         "body": [reason, hint or "Check that your forms are live, UTM Grabber is active, and the form plugin is connected."]},
        {"type": "closing", "kicker": "Next step", "title": "Next: check *tracking* and run this again.",
         "body": "As soon as submissions arrive, this report fills itself in."},
    ]}


# ---------------------------------------------------------------------------
# numbers
# ---------------------------------------------------------------------------
def n(v):
    """1186 -> '1,186'; 12.5 -> '12.5'."""
    if v is None:
        return "–"
    if isinstance(v, float) and not v.is_integer():
        return "{:,.1f}".format(v)
    return "{:,}".format(int(round(v)))


def money(v, decimals=None):
    if v is None:
        return "–"
    neg = v < 0
    a = abs(v)
    if decimals is None:
        decimals = 0 if a >= 100 else 2
    if a >= 100000:
        s = "${:,.0f}K".format(a / 1000.0) if a < 1e6 else "${:,.2f}M".format(a / 1e6)
    elif a >= 10000:
        s = "${:,.1f}K".format(a / 1000.0).replace(".0K", "K")
    else:
        s = "${:,.{d}f}".format(a, d=decimals)
    return (MINUS if neg else "") + s


def pct(v, decimals=0):
    if v is None:
        return "–"
    if decimals == 0:
        return "{}%".format(int(round(v)))
    return "{:.{d}f}%".format(v, d=decimals)


def ratio(v):
    return "–" if v is None else "{:.1f}x".format(v)


def safe_div(a, b):
    return (a / b) if b else None


def share(part, whole):
    return 100.0 * part / whole if whole else 0.0


# ---------------------------------------------------------------------------
# deltas
# ---------------------------------------------------------------------------
def delta(current, prior, kind="pct", good="up", flat_below=3.0, unit_fmt=None):
    """Stat-strip delta fields.

    kind="pct"   relative change ('+14%')
    kind="pts"   percentage-point change for rates ('+4 pts')
    kind="abs"   absolute change formatted with unit_fmt ('+$0.40')
    """
    out = {"good": good}
    if current is None or prior is None:
        return out
    if kind == "pts":
        d = current - prior
        if abs(d) < 1.0:
            out.update(delta_label="Flat", delta_direction="flat")
            return out
        pts_n = abs(int(round(d)))
        out.update(delta_label="%s%s %s" % ("+" if d > 0 else MINUS, n(pts_n), "pt" if pts_n == 1 else "pts"),
                   delta_direction="up" if d > 0 else "down")
        return out
    if kind == "abs":
        d = current - prior
        if d == 0:
            out.update(delta_label="Flat", delta_direction="flat")
            return out
        f = unit_fmt or n
        out.update(delta_label="%s%s" % ("+" if d > 0 else MINUS, f(abs(d))),
                   delta_direction="up" if d > 0 else "down")
        return out
    if prior == 0:
        if current == 0:
            out.update(delta_label="Flat", delta_direction="flat")
        else:
            out.update(delta_label="New", delta_direction="up")
        return out
    p = 100.0 * (current - prior) / abs(prior)
    if abs(p) < flat_below:
        out.update(delta_label="Flat", delta_direction="flat")
        return out
    out.update(delta_label="%s%d%%" % ("+" if p > 0 else MINUS, int(round(abs(p)))),
               delta_direction="up" if p > 0 else "down")
    return out


def stat(label, value, current=None, prior=None, kind="pct", good="up", spark=None, source=None,
         note=None, unit_fmt=None):
    s = {"label": label, "value": value}
    if prior is not None and current is not None:
        s.update(delta(current, prior, kind, good, unit_fmt=unit_fmt))
    else:
        s["good"] = good
    if spark:
        s["spark"] = [round(x, 2) if isinstance(x, float) else x for x in spark]
    if source:
        s["source"] = source
    if note:
        s["note"] = note
    return s


# ---------------------------------------------------------------------------
# dates and periods
# ---------------------------------------------------------------------------
def entry_dt(e):
    s = get_field(e, "Date Created", "date_created", "Date", "date")
    if not s:
        return None
    s = s.replace("T", " ").replace("Z", "")
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(s[:19] if f.endswith("%S") else s[:16] if f.endswith("%M") else s[:10], f)
        except ValueError:
            continue
    return None


def span(entries):
    ds = [d for d in (entry_dt(e) for e in entries) if d]
    if not ds:
        return None, None
    return min(ds).date(), max(ds).date()


def period_label(start, end):
    """date, date -> 'Sep 1 to Sep 30, 2026'."""
    if not start or not end:
        return ""
    if start.year == end.year:
        if start.month == end.month and start.day == 1 and (end + _dt.timedelta(days=1)).day == 1:
            return start.strftime("%B %Y")
        return "%s to %s" % (_md(start), _md(end) + end.strftime(", %Y"))
    return "%s, %d to %s, %d" % (_md(start), start.year, _md(end), end.year)


def is_full_month(start, end):
    return bool(start and end and start.day == 1 and start.month == end.month and start.year == end.year
                and (end + _dt.timedelta(days=1)).day == 1)


def period_name(start, end, short=False):
    """'September' for a calendar month, else 'The last 30 days' / 'This week'."""
    if not start or not end:
        return "This period"
    if is_full_month(start, end):
        return start.strftime("%B")
    days = (end - start).days + 1
    if days == 1:
        return start.strftime("%A, %B ") + str(start.day) if not short else "That day"
    if days == 7:
        return "This week"
    return "The last %d days" % days if not short else "Last %d days" % days


def prior_name(start, end):
    """Name for the comparison period: 'August' or 'the previous 30 days'."""
    if not start or not end:
        return "last period"
    if is_full_month(start, end):
        return start.strftime("%B")
    days = (end - start).days + 1
    if days == 1:
        return "the day before"
    return "the previous %d days" % days if days != 7 else "last week"


def _md(d):
    return "%s %d" % (d.strftime("%b"), d.day)


def daily_counts(entries, start=None, end=None, predicate=None):
    """Counts per day across [start, end] inclusive, zero-filled. Returns (labels, values)."""
    if start is None or end is None:
        start, end = span(entries)
    if not start:
        return [], []
    c = Counter()
    for e in entries:
        if predicate and not predicate(e):
            continue
        d = entry_dt(e)
        if d:
            c[d.date()] += 1
    labels, values = [], []
    d = start
    while d <= end:
        labels.append(_md(d))
        values.append(c.get(d, 0))
        d += _dt.timedelta(days=1)
    return labels, values


def weekly_counts(entries, start=None, end=None, predicate=None):
    labels, values = daily_counts(entries, start, end, predicate)
    wl, wv = [], []
    for i in range(0, len(values), 7):
        wl.append(labels[i])
        wv.append(sum(values[i:i + 7]))
    return wl, wv


# ---------------------------------------------------------------------------
# labels
# ---------------------------------------------------------------------------
def pretty(s, fallback="(not set)"):
    """'brand_search' -> 'Brand search'; keeps acronyms like 'US' and 'Q1'."""
    s = str(s or "").strip()
    if not s:
        return fallback
    words = s.replace("_", " ").replace("-", " ").split()
    out = []
    for i, w in enumerate(words):
        if w.isupper() and len(w) <= 4:
            out.append(w)
        elif any(ch.isdigit() for ch in w) and len(w) <= 4:
            out.append(w.upper())
        else:
            out.append(w.capitalize() if i == 0 else w.lower())
    return " ".join(out)


def source_label(src):
    known = {"google": "Google", "facebook": "Facebook", "instagram": "Instagram", "linkedin": "LinkedIn",
             "bing": "Bing", "youtube": "YouTube", "tiktok": "TikTok", "newsletter": "Newsletter",
             "chatgpt": "ChatGPT", "chatgpt.com": "ChatGPT", "perplexity": "Perplexity", "x": "X",
             "twitter": "X (Twitter)", "email": "Email", "hubspot": "HubSpot", "meta": "Meta"}
    s = str(src or "").strip().lower()
    return known.get(s, pretty(s))


def top_with_other(counter_items, k=5, other="Other"):
    """[(label, value)] sorted desc -> top k-1 + Other when there are more than k."""
    items = sorted(counter_items, key=lambda x: -x[1])
    if len(items) <= k:
        return items
    head = items[:k - 1]
    rest = sum(v for _, v in items[k - 1:])
    return head + [(other, rest)]


def last_touch(e):
    return classify_traffic_source(e)


def first_touch(e):
    return first_touch_channel(e)


__all__ = [name for name in dir() if not name.startswith("_")]
