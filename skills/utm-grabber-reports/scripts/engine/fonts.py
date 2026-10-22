"""
Font registry for the report engine.

Every typeface ships inside the skill as a Latin subset (assets/fonts/web/*.woff2
for HTML + PDF, assets/fonts/ttf/*.ttf for measuring PowerPoint text). Reports
embed the WOFF2 files as base64, so an HTML report renders identically offline,
inside a corporate firewall, or when forwarded as an email attachment. No call
to a font CDN is ever made.
"""
import base64
import functools
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_FONT_ROOT = os.path.normpath(os.path.join(_HERE, "..", "..", "assets", "fonts"))

# name -> source file (see scripts/dev/build_fonts.py)
FONT_FILES = {
    # Classic (the original v1 look)
    "instrument-serif-400": "InstrumentSerif-Regular.ttf",
    "instrument-serif-400i": "InstrumentSerif-Italic.ttf",
    "geist-400": "Geist-Regular.ttf",
    "geist-500": "Geist-Medium.ttf",
    "geist-mono-400": "GeistMono-Regular.ttf",
    # Boardroom
    "barlow-400": "Barlow-Regular.ttf",
    "barlow-500": "Barlow-Medium.ttf",
    "barlow-600": "Barlow-SemiBold.ttf",
    "barlow-700": "Barlow-Bold.ttf",
    "barlow-condensed-500": "BarlowCondensed-Medium.ttf",
    "barlow-condensed-600": "BarlowCondensed-SemiBold.ttf",
    "barlow-condensed-700": "BarlowCondensed-Bold.ttf",
    # Ledger
    "plex-sans-400": "IBMPlexSans-Regular.ttf",
    "plex-sans-500": "IBMPlexSans-Medium.ttf",
    "plex-sans-600": "IBMPlexSans-SemiBold.ttf",
    "plex-sans-700": "IBMPlexSans-Bold.ttf",
    "plex-condensed-400": "IBMPlexSansCondensed-Regular.ttf",
    "plex-condensed-500": "IBMPlexSansCondensed-Medium.ttf",
    "plex-condensed-600": "IBMPlexSansCondensed-SemiBold.ttf",
    "plex-mono-400": "IBMPlexMono-Regular.ttf",
    "plex-mono-500": "IBMPlexMono-Medium.ttf",
    # Studio
    "rubik-400": "Rubik-Regular.ttf",
    "rubik-500": "Rubik-Medium.ttf",
    "rubik-700": "Rubik-Bold.ttf",
    "work-sans-400": "WorkSans-Regular.ttf",
    "work-sans-500": "WorkSans-Medium.ttf",
    "work-sans-600": "WorkSans-SemiBold.ttf",
}

# CSS family name, weight, style for each file
FACES = {
    "instrument-serif-400": ("Instrument Serif", 400, "normal"),
    "instrument-serif-400i": ("Instrument Serif", 400, "italic"),
    "geist-400": ("Geist", 400, "normal"),
    "geist-500": ("Geist", 500, "normal"),
    "geist-mono-400": ("Geist Mono", 400, "normal"),
    "barlow-400": ("Barlow", 400, "normal"),
    "barlow-500": ("Barlow", 500, "normal"),
    "barlow-600": ("Barlow", 600, "normal"),
    "barlow-700": ("Barlow", 700, "normal"),
    "barlow-condensed-500": ("Barlow Condensed", 500, "normal"),
    "barlow-condensed-600": ("Barlow Condensed", 600, "normal"),
    "barlow-condensed-700": ("Barlow Condensed", 700, "normal"),
    "plex-sans-400": ("IBM Plex Sans", 400, "normal"),
    "plex-sans-500": ("IBM Plex Sans", 500, "normal"),
    "plex-sans-600": ("IBM Plex Sans", 600, "normal"),
    "plex-sans-700": ("IBM Plex Sans", 700, "normal"),
    "plex-condensed-400": ("IBM Plex Sans Condensed", 400, "normal"),
    "plex-condensed-500": ("IBM Plex Sans Condensed", 500, "normal"),
    "plex-condensed-600": ("IBM Plex Sans Condensed", 600, "normal"),
    "plex-mono-400": ("IBM Plex Mono", 400, "normal"),
    "plex-mono-500": ("IBM Plex Mono", 500, "normal"),
    "rubik-400": ("Rubik", 400, "normal"),
    "rubik-500": ("Rubik", 500, "normal"),
    "rubik-700": ("Rubik", 700, "normal"),
    "work-sans-400": ("Work Sans", 400, "normal"),
    "work-sans-500": ("Work Sans", 500, "normal"),
    "work-sans-600": ("Work Sans", 600, "normal"),
}


def ttf_path(name):
    p = os.path.join(_FONT_ROOT, "ttf", name + ".ttf")
    return p if os.path.exists(p) else None


@functools.lru_cache(maxsize=64)
def _woff2_b64(name):
    p = os.path.join(_FONT_ROOT, "web", name + ".woff2")
    if not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def font_face_css(names):
    """@font-face rules for the given font names, WOFF2 inlined as base64."""
    rules = []
    for name in names:
        fam, wt, style = FACES[name]
        data = _woff2_b64(name)
        if not data:
            continue
        rules.append(
            '@font-face{font-family:"%s";font-style:%s;font-weight:%d;font-display:block;'
            'src:url(data:font/woff2;base64,%s) format("woff2");}' % (fam, style, wt, data))
    return "\n".join(rules)


def face_for(family, weight=400, italic=False):
    """Best registered file for a family/weight (nearest weight wins)."""
    style = "italic" if italic else "normal"
    best, best_d = None, 1e9
    for name, (fam, wt, st) in FACES.items():
        if fam != family or st != style:
            continue
        d = abs(wt - weight)
        if d < best_d:
            best, best_d = name, d
    if best is None and italic:
        return face_for(family, weight, False)
    return best
