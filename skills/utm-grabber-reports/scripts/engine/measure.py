"""
Text measurement with the real theme fonts.

Charts use it to decide whether a label fits inside a bar or must sit outside,
and the PowerPoint renderer uses it to size type so nothing overflows its box.
Falls back to an average-width estimate when a font file cannot be loaded.
"""
import functools
import os

from . import fonts as F

try:
    from PIL import ImageFont
except Exception:  # pragma: no cover
    ImageFont = None

_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                      "assets", "fonts"))


def _family_name(css_stack):
    first = css_stack.split(",")[0].strip().strip('"').strip("'")
    return first


@functools.lru_cache(maxsize=256)
def _load(name, size_tenths):
    if ImageFont is None or not name:
        return None
    size = max(1, size_tenths) / 10.0
    for folder, ext in (("ttf", ".ttf"), ("web", ".woff2")):
        p = os.path.join(_ROOT, folder, name + ext)
        if os.path.exists(p):
            try:
                # Measure at 10x to keep sub-pixel precision with integer sizes.
                return ImageFont.truetype(p, int(round(size * 10)))
            except Exception:
                continue
    return None


def text_width(text, family, size, weight=400, italic=False, letter_spacing=0.0):
    """Width in px (or pt, same unit as size) of a single line of text."""
    text = "" if text is None else str(text)
    if not text:
        return 0.0
    fam = _family_name(family) if "," in family or '"' in family else family
    name = F.face_for(fam, weight, italic)
    font = _load(name, int(round(size * 10))) if name else None
    if font is not None:
        try:
            w = font.getlength(text) / 10.0
        except Exception:
            w = len(text) * size * 0.55
    else:
        w = len(text) * size * 0.55
    return w + letter_spacing * size * max(0, len(text) - 1)


def fit_size(text, family, max_width, start, minimum, weight=400, italic=False, step=0.5):
    """Largest size <= start (down to minimum) at which text fits on one line."""
    s = start
    while s > minimum and text_width(text, family, s, weight, italic) > max_width:
        s -= step
    return max(s, minimum)


def wrap_lines(text, family, size, max_width, weight=400, italic=False):
    """Greedy word wrap. Returns the list of lines."""
    words = str(text or "").split()
    if not words:
        return [""]
    lines, cur = [], words[0]
    for w in words[1:]:
        trial = cur + " " + w
        if text_width(trial, family, size, weight, italic) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def ellipsize(text, family, size, max_width, weight=400):
    text = str(text or "")
    if text_width(text, family, size, weight) <= max_width:
        return text
    ell = "…"
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if text_width(text[:mid].rstrip() + ell, family, size, weight) <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + ell
