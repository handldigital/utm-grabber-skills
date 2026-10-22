"""
Dev tool: build the subset font files the report engine embeds.

Not used at report time. Run it only when a theme's typefaces change:

    python scripts/dev/build_fonts.py [extra-source-dir ...]

For every font in engine/fonts.py it finds the source TTF (assets/fonts/, then
~/Library/Fonts, then any extra dirs given), subsets it to Latin + the symbols
reports use, and writes two files:

    assets/fonts/web/<name>.woff2   embedded (base64) in HTML and PDF
    assets/fonts/ttf/<name>.ttf     used to measure text for PowerPoint layout

All typefaces are SIL Open Font License, so redistribution inside the skill is fine.
"""
import os
import sys

from fontTools import subset
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from engine.fonts import FONT_FILES  # noqa: E402

UNICODES = (
    list(range(0x20, 0x7F)) + list(range(0xA0, 0x180)) +   # Latin, Latin-1, Ext-A
    list(range(0x2010, 0x2028)) + list(range(0x2030, 0x203B)) +  # dashes, quotes, bullets
    [0x2039, 0x203A, 0x2044, 0x2070, 0x2074, 0x20AC, 0x20A3, 0x20A4, 0x20B9,
     0x20BA, 0x20BD, 0x2116, 0x2122, 0x2190, 0x2191, 0x2192, 0x2193, 0x2197,
     0x2198, 0x2212, 0x2215, 0x2219, 0x221E, 0x2248, 0x2260, 0x2264, 0x2265,
     0x00D7, 0x00F7, 0x25B2, 0x25BC, 0x25B4, 0x25BE, 0x25CF, 0x25CB, 0x25A0,
     0x25A1, 0x25C6, 0x2713, 0x2717, 0x2715, 0x2605, 0x2022, 0x2026]
)


def find_source(fname):
    dirs = [os.path.join(ROOT, "assets", "fonts"), os.path.expanduser("~/Library/Fonts"),
            "/Library/Fonts"] + sys.argv[1:]
    for d in dirs:
        p = os.path.join(d, fname)
        if os.path.exists(p):
            return p
    return None


def build_one(name, src_name):
    src = find_source(src_name)
    if not src:
        print(f"  MISSING source {src_name}")
        return False
    opts = subset.Options()
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    opts.glyph_names = False
    opts.hinting = False
    opts.desubroutinize = True
    for flavor, folder, ext in ((None, "ttf", ".ttf"), ("woff2", "web", ".woff2")):
        font = TTFont(src)
        opts.flavor = flavor
        sub = subset.Subsetter(options=opts)
        sub.populate(unicodes=UNICODES)
        sub.subset(font)
        out = os.path.join(ROOT, "assets", "fonts", folder, name + ext)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        font.flavor = flavor
        font.save(out)
    size = os.path.getsize(os.path.join(ROOT, "assets", "fonts", "web", name + ".woff2"))
    print(f"  {name:32s} <- {os.path.basename(src):36s} woff2 {size // 1024}K")
    return True


def main():
    ok = True
    for name, src_name in FONT_FILES.items():
        ok = build_one(name, src_name) and ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
