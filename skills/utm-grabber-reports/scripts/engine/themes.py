"""
Report themes.

A theme is a look: typefaces, surfaces, card treatment and how the brand color is
used. Every theme accepts any customer brand (primary, accent, ink, muted,
surface) and derives contrast-safe colors from it, so a report stays legible
whether the brand is navy, neon pink, mustard yellow or black.

    classic    The original v1 design, preserved: two-tone cards, italic serif
               numerals, mono kickers. Calm and print-friendly.
    boardroom  Dark and cinematic. Built for the big screen and the quarterly
               meeting. Condensed numerals, luminous charts.
    ledger     Dense and exact. Built for operators who live in the numbers:
               tabular figures, a left rail of section titles, small multiples.
    studio     Bright and friendly. Built for client-facing reports: a brand-color
               cover, big readable numbers, plain-English changes.

Usage:
    from engine.themes import resolve_theme
    t = resolve_theme("studio", brand_profile)
    t["tokens"]["brand_ink"], t["fonts"]["display"], ...
"""
from . import color as C

THEME_ORDER = ["studio", "boardroom", "ledger", "classic"]
DEFAULT_THEME = "studio"

THEME_INFO = {
    "classic": {
        "name": "Classic",
        "tagline": "The original report design. Calm, editorial and print-friendly.",
        "best_for": "Printed reports and long reads",
    },
    "boardroom": {
        "name": "Boardroom",
        "tagline": "Dark and cinematic. Made for the big screen and the quarterly meeting.",
        "best_for": "Presenting to leadership",
    },
    "ledger": {
        "name": "Ledger",
        "tagline": "Dense and exact. Every number at a glance, built for operators.",
        "best_for": "Weekly ops reviews and analysts",
    },
    "studio": {
        "name": "Studio",
        "tagline": "Bright and friendly. Your brand on the cover, every change in plain English.",
        "best_for": "Client-facing reports",
    },
}

# Legacy brand_profile.theme values map onto the new themes.
ALIASES = {
    "light": "classic", "gradient": "boardroom", "dark": "boardroom",
    "default": DEFAULT_THEME, "original": "classic", "v1": "classic",
    "editorial": "classic", "executive": "boardroom", "analyst": "ledger",
    "dense": "ledger", "bright": "studio", "client": "studio", "agency": "studio",
}

UTMG_BRAND = {
    "company_name": "UTM Grabber",
    "logo": {"type": "text", "value": "UTM Grabber"},
    "colors": {"primary": "#0160BF", "accent": "#2E90FA", "ink": "#0B1B34",
               "muted": "#64748B", "surface": "#F3F1FA"},
}


def normalize_theme(key):
    if not key:
        return None
    k = str(key).strip().lower()
    if k in THEME_INFO:
        return k
    return ALIASES.get(k)


def pick_theme(explicit=None, summary=None):
    """Explicit argument > summary.meta.theme > brand_profile.theme > default."""
    for cand in (explicit,
                 (summary or {}).get("meta", {}).get("theme"),
                 ((summary or {}).get("meta", {}).get("brand_profile") or {}).get("theme")):
        k = normalize_theme(cand)
        if k:
            return k
    return DEFAULT_THEME


def _brand_colors(brand):
    colors = dict(UTMG_BRAND["colors"])
    colors.update({k: v for k, v in ((brand or {}).get("colors") or {}).items() if v})
    return {k: C.clean_hex(v, UTMG_BRAND["colors"].get(k, "#0160BF")) for k, v in colors.items()}


def _font(css, pptx, pptx_bold=False, weight=400, italic=False):
    return {"css": css, "pptx": pptx, "pptx_bold": pptx_bold, "weight": weight,
            "italic": italic}


# ---------------------------------------------------------------------------
# Theme builders
# ---------------------------------------------------------------------------
def _classic(bc):
    primary, accent = bc["primary"], bc["accent"]
    page, panel = "#FDFCFE", "#FFFFFF"
    ink, muted = bc["ink"], bc["muted"]
    surface = bc.get("surface") or "#F3F1FA"
    tokens = {
        "dark": False,
        "page": page, "panel": panel, "panel2": surface, "soft": surface,
        "line": "#E2E4EA", "line_css": "rgba(11,27,52,0.10)", "line_soft": "rgba(11,27,52,0.06)",
        "ink": ink, "ink2": muted, "ink3": muted,
        "brand": primary, "brand_ink": C.ensure_contrast(primary, panel, 4.5),
        "brand_fill": primary, "on_brand": C.readable_on(primary),
        "brand_soft": surface, "accent": accent,
        "good": "#1D7A4A", "bad": "#C4353A", "warn": "#B26A00",
        "good_soft": "#E6F4EC", "bad_soft": "#FBEAEA", "warn_soft": "#FFF4DE",
        "grid": "#ECEDF1", "axis": "#C9CDD6", "track": "#EEF0F4", "chart_text": muted,
        "series": [primary, accent, "#FFC857", "#30B47A", "#6FB1E8", "#F59E0B", ink],
        "seq": C.sequential(primary, "light"),
        "neutral": "#C9CED8",
    }
    fonts = {
        "display": _font('"Instrument Serif", Georgia, serif', "Instrument Serif"),
        "numeral": _font('"Instrument Serif", Georgia, serif', "Instrument Serif", italic=True),
        "body": _font('"Geist", "Inter", system-ui, sans-serif', "Geist"),
        "strong": _font('"Geist", "Inter", system-ui, sans-serif', "Geist", weight=500),
        "label": _font('"Geist Mono", ui-monospace, monospace', "Geist Mono"),
        "mono": _font('"Geist Mono", ui-monospace, monospace', "Geist Mono"),
    }
    fonts["chart"] = fonts["body"]
    files = ["instrument-serif-400", "instrument-serif-400i", "geist-400", "geist-500",
             "geist-mono-400"]
    style = {"accent": "italic-brand", "radius": 4, "radius_sm": 4, "kicker_upper": True,
             "bar_round": 0, "page_width": 1180, "chart_size": 12.5}
    return tokens, fonts, files, style


def _boardroom(bc):
    primary, accent = bc["primary"], bc["accent"]
    L, Cc, H = C.oklch(primary)
    if Cc < 0.035:
        H, Cc = 255, 0.02
    tint_c = min(max(Cc * 0.22, 0.012), 0.032)
    page = C.from_oklch(0.165, tint_c, H)
    panel = C.from_oklch(0.205, tint_c, H)
    panel2 = C.from_oklch(0.245, tint_c * 1.1, H)
    line = C.mix(panel, "#FFFFFF", 0.10)
    ink = "#F3F5F8"
    ink2 = C.from_oklch(0.80, 0.018, H)
    ink3 = C.from_oklch(0.66, 0.022, H)
    glow = C.ensure_contrast(C.with_lightness(primary, max(L, 0.66)), panel, 4.6)
    series = C.categorical(primary, accent, "dark")
    if Cc >= 0.035:
        series[0] = C.with_lightness(series[0], min(max(C.oklch(series[0])[0], 0.60), 0.66))
    series[0] = C.ensure_contrast(series[0], panel, 3.0)
    tokens = {
        "dark": True,
        "page": page, "panel": panel, "panel2": panel2, "soft": panel2,
        "line": line, "line_css": "rgba(255,255,255,0.09)", "line_soft": "rgba(255,255,255,0.05)",
        "ink": ink, "ink2": ink2, "ink3": ink3,
        "brand": primary, "brand_ink": glow, "brand_fill": C.with_lightness(primary, min(max(L, 0.45), 0.55)),
        "on_brand": "#FFFFFF", "brand_soft": C.mix(panel, glow, 0.16), "accent": accent,
        "good": "#4ED38A", "bad": "#FF7B7B", "warn": "#F6BE5A",
        "good_soft": C.mix(panel, "#4ED38A", 0.16), "bad_soft": C.mix(panel, "#FF7B7B", 0.16),
        "warn_soft": C.mix(panel, "#F6BE5A", 0.16),
        "grid": C.mix(panel, "#FFFFFF", 0.07), "axis": C.mix(panel, "#FFFFFF", 0.20),
        "track": C.mix(panel, "#FFFFFF", 0.07), "chart_text": ink3,
        "series": series,
        "seq": C.sequential(primary, "dark"),
        "neutral": C.mix(panel, "#FFFFFF", 0.28),
    }
    fonts = {
        "display": _font('"Barlow", "Helvetica Neue", Arial, sans-serif', "Barlow", True, 600),
        "numeral": _font('"Barlow Condensed", "Arial Narrow", sans-serif', "Barlow Condensed", True, 600),
        "body": _font('"Barlow", "Helvetica Neue", Arial, sans-serif', "Barlow"),
        "strong": _font('"Barlow", "Helvetica Neue", Arial, sans-serif', "Barlow", True, 600),
        "label": _font('"Barlow Condensed", "Arial Narrow", sans-serif', "Barlow Condensed", False, 500),
        "mono": _font('"IBM Plex Mono", ui-monospace, monospace', "IBM Plex Mono"),
    }
    files = ["barlow-400", "barlow-500", "barlow-600", "barlow-700",
             "barlow-condensed-500", "barlow-condensed-600", "barlow-condensed-700",
             "plex-mono-400"]
    style = {"accent": "brand", "radius": 14, "radius_sm": 8, "kicker_upper": False,
             "bar_round": 4, "page_width": 1200, "chart_size": 13.5}
    return tokens, fonts, files, style


def _ledger(bc):
    primary, accent = bc["primary"], bc["accent"]
    _, Cc, H = C.oklch(primary)
    if Cc < 0.035:
        H = 255
    page = C.from_oklch(0.962, 0.005, H)
    panel = "#FFFFFF"
    panel2 = C.from_oklch(0.978, 0.006, H)
    tokens = {
        "dark": False,
        "page": page, "panel": panel, "panel2": panel2, "soft": panel2,
        "line": "#DCE1E8", "line_css": "#DCE1E8", "line_soft": "#EBEEF2",
        "ink": "#10161F", "ink2": "#475262", "ink3": "#6E7887",
        "brand": primary, "brand_ink": C.ensure_contrast(primary, panel, 4.6),
        "brand_fill": primary, "on_brand": C.readable_on(primary),
        "brand_soft": C.tint(primary, panel, 0.10), "accent": accent,
        "good": "#0B7A3B", "bad": "#BF3029", "warn": "#956000",
        "good_soft": "#E5F3EA", "bad_soft": "#FBE9E7", "warn_soft": "#FBF0D9",
        "grid": "#EDF0F4", "axis": "#C3CAD4", "track": "#EDF0F4", "chart_text": "#6E7887",
        "series": C.categorical(primary, accent, "light"),
        "seq": C.sequential(primary, "light"),
        "neutral": "#C3CAD4",
    }
    fonts = {
        "display": _font('"IBM Plex Sans", "Helvetica Neue", Arial, sans-serif', "IBM Plex Sans", True, 600),
        "numeral": _font('"IBM Plex Sans", "Helvetica Neue", Arial, sans-serif', "IBM Plex Sans", False, 500),
        "body": _font('"IBM Plex Sans", "Helvetica Neue", Arial, sans-serif', "IBM Plex Sans"),
        "strong": _font('"IBM Plex Sans", "Helvetica Neue", Arial, sans-serif', "IBM Plex Sans", True, 600),
        "label": _font('"IBM Plex Sans Condensed", "Arial Narrow", sans-serif', "IBM Plex Sans Condensed"),
        "mono": _font('"IBM Plex Mono", ui-monospace, monospace', "IBM Plex Mono"),
    }
    files = ["plex-sans-400", "plex-sans-500", "plex-sans-600", "plex-sans-700",
             "plex-condensed-400", "plex-condensed-500", "plex-condensed-600",
             "plex-mono-400", "plex-mono-500"]
    style = {"accent": "plain", "radius": 6, "radius_sm": 3, "kicker_upper": False,
             "bar_round": 2, "page_width": 1280, "chart_size": 12}
    return tokens, fonts, files, style


def _studio(bc):
    primary, accent = bc["primary"], bc["accent"]
    _, Cc, H = C.oklch(primary)
    if Cc < 0.035:
        H = 255
    panel = "#FFFFFF"
    soft = C.from_oklch(0.972, min(0.014, max(Cc * 0.12, 0.004)), H)
    on_brand = C.readable_on(primary)
    tokens = {
        "dark": False,
        "page": "#FFFFFF", "panel": panel, "panel2": soft, "soft": soft,
        "line": "#E6E8EE", "line_css": "#E6E8EE", "line_soft": "#F0F1F5",
        "ink": "#141821", "ink2": "#4C5464", "ink3": "#737B8B",
        "brand": primary, "brand_ink": C.ensure_contrast(primary, panel, 4.6),
        "brand_fill": primary, "on_brand": on_brand,
        "on_brand_2": C.mix(primary, on_brand, 0.78),
        "brand_soft": C.tint(primary, panel, 0.11), "accent": accent,
        "good": "#0B7A3B", "bad": "#C0322B", "warn": "#9A6100",
        "good_soft": "#E4F5EA", "bad_soft": "#FDEBE9", "warn_soft": "#FFF3DA",
        "grid": "#EEF0F4", "axis": "#CDD2DB", "track": "#EFF1F5", "chart_text": "#737B8B",
        "series": C.categorical(primary, accent, "light"),
        "seq": C.sequential(primary, "light"),
        "neutral": "#CDD2DB",
    }
    fonts = {
        "display": _font('"Rubik", "Helvetica Neue", Arial, sans-serif', "Rubik", False, 500),
        "numeral": _font('"Rubik", "Helvetica Neue", Arial, sans-serif', "Rubik", True, 700),
        "body": _font('"Work Sans", "Helvetica Neue", Arial, sans-serif', "Work Sans"),
        "strong": _font('"Work Sans", "Helvetica Neue", Arial, sans-serif', "Work Sans", True, 600),
        "label": _font('"Work Sans", "Helvetica Neue", Arial, sans-serif', "Work Sans", False, 500),
        "mono": _font('"IBM Plex Mono", ui-monospace, monospace', "IBM Plex Mono"),
    }
    files = ["rubik-400", "rubik-500", "rubik-700", "work-sans-400", "work-sans-500",
             "work-sans-600", "plex-mono-400"]
    style = {"accent": "brand", "radius": 18, "radius_sm": 10, "kicker_upper": False,
             "bar_round": 4, "page_width": 1080, "chart_size": 12.5}
    return tokens, fonts, files, style


_BUILDERS = {"classic": _classic, "boardroom": _boardroom, "ledger": _ledger,
             "studio": _studio}


def resolve_theme(key, brand_profile=None):
    key = normalize_theme(key) or DEFAULT_THEME
    bc = _brand_colors(brand_profile)
    tokens, fonts, files, style = _BUILDERS[key](bc)
    t = {"key": key, "info": THEME_INFO[key], "tokens": tokens, "fonts": fonts,
         "font_files": files, "style": style, "brand_colors": bc}
    return t


def css_vars(theme):
    """:root custom properties for a resolved theme."""
    tk = theme["tokens"]
    f = theme["fonts"]
    lines = []
    for k, v in tk.items():
        if isinstance(v, str):
            lines.append("--%s:%s;" % (k.replace("_", "-"), v))
    for i, c in enumerate(tk["series"]):
        lines.append("--s%d:%s;" % (i + 1, c))
    for i, c in enumerate(tk["seq"]):
        lines.append("--q%d:%s;" % (i + 1, c))
    for role, spec in f.items():
        lines.append("--f-%s:%s;" % (role, spec["css"]))
    st = theme["style"]
    lines.append("--r:%dpx;--r-sm:%dpx;--page-w:%dpx;" % (st["radius"], st["radius_sm"], st["page_width"]))
    return ":root{" + "".join(lines) + "}"
