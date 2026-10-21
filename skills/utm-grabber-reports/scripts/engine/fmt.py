"""
Number and text formatting shared by every renderer.

Values arrive from recipes either as display strings ("1,248", "$13.6K", "37%")
or as numbers. Renderers never reformat a string a recipe already formatted;
these helpers exist for chart axes, data labels and table cells that carry raw
numbers.
"""
import math
import re

MINUS = "−"


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def to_num(v, default=None):
    """Parse '1,248', '$13.6K', '37%', '−6' into a float. Returns default if not numeric."""
    if is_num(v):
        return float(v)
    if not isinstance(v, str):
        return default
    s = v.strip().replace(MINUS, "-").replace(",", "").replace("$", "").replace("€", "") \
        .replace("£", "").replace("%", "").replace("pts", "").replace("pt", "").strip()
    mult = 1.0
    if s[-1:].upper() == "K":
        mult, s = 1e3, s[:-1]
    elif s[-1:].upper() == "M":
        mult, s = 1e6, s[:-1]
    elif s[-1:].upper() == "B":
        mult, s = 1e9, s[:-1]
    s = s.rstrip("x").strip()
    try:
        return float(s) * mult
    except ValueError:
        return default


def compact(n, decimals=1):
    """1,284 / 12.9K / 4.2M. Integers under 10,000 keep full precision with commas."""
    if not is_num(n):
        return str(n) if n is not None else ""
    neg = n < 0
    a = abs(n)
    if a >= 1e9:
        s = _trim(a / 1e9, decimals) + "B"
    elif a >= 1e6:
        s = _trim(a / 1e6, decimals) + "M"
    elif a >= 1e4:
        s = _trim(a / 1e3, decimals) + "K"
    elif a == int(a):
        s = "{:,}".format(int(a))
    else:
        s = "{:,.{d}f}".format(a, d=decimals)
    return (MINUS if neg else "") + s


def _trim(x, decimals):
    s = "{:.{d}f}".format(x, d=decimals)
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def num(n, decimals=0):
    if not is_num(n):
        return str(n) if n is not None else ""
    s = "{:,.{d}f}".format(abs(n), d=decimals)
    return (MINUS if n < 0 else "") + s


def money(n, currency="$", decimals=None):
    if not is_num(n):
        return str(n) if n is not None else ""
    a = abs(n)
    if a >= 1e4:
        body = compact(a)
    elif decimals is not None:
        body = "{:,.{d}f}".format(a, d=decimals)
    elif a >= 100 or a == int(a):
        body = "{:,.0f}".format(a)
    else:
        body = "{:,.2f}".format(a)
    return (MINUS if n < 0 else "") + currency + body


def pct(n, decimals=0):
    if not is_num(n):
        return str(n) if n is not None else ""
    return (MINUS if n < 0 else "") + _trim(abs(n), decimals) + "%"


def axis_ticks(vmax, vmin=0.0, target=5):
    """Clean axis ticks (0 / 50 / 100 ...) covering [vmin, vmax]."""
    if not is_num(vmax):
        vmax = 1.0
    if vmax <= vmin:
        vmax = vmin + 1.0
    span = vmax - vmin
    raw = span / max(1, target)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if span / step <= target:
            break
    lo = math.floor(vmin / step) * step
    hi = math.ceil(vmax / step) * step
    ticks = []
    t = lo
    while t <= hi + step * 0.001:
        ticks.append(round(t, 10))
        t += step
    return ticks


def tick_label(v, unit=None):
    if unit == "%":
        return pct(v)
    if unit in ("$", "money"):
        return money(v)
    return compact(v)


def split_accent(text):
    """'Paid is *51%* of leads.' -> [('Paid is ', False), ('51%', True), (' of leads.', False)]"""
    if not text:
        return []
    parts = re.split(r"(\*[^*]+\*)", str(text))
    out = []
    for p in parts:
        if not p:
            continue
        if len(p) > 2 and p.startswith("*") and p.endswith("*"):
            out.append((p[1:-1], True))
        else:
            out.append((p, False))
    return out


def strip_accent(text):
    return "".join(t for t, _ in split_accent(text))


def plain_delta(label, direction, compare="last period"):
    """'+12%' + 'up' -> 'Up 12% from last period' (Studio's plain-English deltas)."""
    if not label:
        return ""
    if str(label).strip().lower() == "new":
        return "New: none in %s" % compare
    lab = str(label).strip().lstrip("+").replace(MINUS, "").lstrip("-").strip()
    import re as _re
    lab = _re.sub(r"\s*pts?\b", " pts", lab).strip()
    if _re.match(r"^1(\.0)? pts$", lab):
        lab = "1 pt"
    if direction == "up":
        return "Up %s from %s" % (lab, compare)
    if direction == "down":
        return "Down %s from %s" % (lab, compare)
    return "Flat vs %s" % compare


def clean_text(s):
    """House rule: no em dashes in anything we render. Swap for a colon or comma."""
    if s is None:
        return ""
    s = str(s)
    while "—" in s:
        m = re.search(r"\s*—\s*", s)
        before, after = s[:m.start()], s[m.end():]
        if ":" in before:
            after = after[:1].upper() + after[1:]
            s = before.rstrip(" ,") + ". " + after
        else:
            s = before.rstrip(" ,") + ": " + after
    return s
