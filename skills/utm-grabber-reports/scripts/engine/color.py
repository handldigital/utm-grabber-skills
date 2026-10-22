"""
Color math for the report engine.

Everything here is computed, never eyeballed: OKLab / OKLCH conversions, WCAG
contrast, color-vision-deficiency simulation (Machado et al. 2009, severity 1.0)
and the palette builders every theme uses.

The categorical palette always puts the customer's brand color in slot 1, then
fills the remaining slots from a validated reference order, skipping any hue that
would sit too close to a slot already taken. Adjacent slots are held to the same
gates as the data-viz validator: OKLab delta E >= 15 under normal vision and
>= 8 under protan / deutan simulation (6 is the legal floor).
"""
import math

# ---------------------------------------------------------------------------
# Thresholds (mirrors the data-viz validator)
# ---------------------------------------------------------------------------
BAND = {"light": (0.43, 0.77), "dark": (0.48, 0.67)}
CHROMA_FLOOR = 0.10
CVD_TARGET, CVD_FLOOR = 8.0, 6.0
NORMAL_FLOOR = 15.0

MACHADO = {
    "protan": ((0.152286, 1.052583, -0.204868),
               (0.114503, 0.786281, 0.099216),
               (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968),
               (0.280085, 0.672501, 0.047413),
               (-0.011820, 0.042940, 0.968881)),
}

# Reference categorical palette (validated order, light and dark steps).
REFERENCE = {
    "light": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4",
              "#008300", "#4a3aa7", "#e34948"],
    "dark": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181",
             "#008300", "#9085e9", "#e66767"],
}

STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a",
          "critical": "#d03b3b"}


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------
def clean_hex(h, default="#0160BF"):
    if not isinstance(h, str):
        return default
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return default
    try:
        int(h, 16)
    except ValueError:
        return default
    return "#" + h.upper()


def hex_to_rgb(h):
    h = clean_hex(h).lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#" + "".join("%02X" % max(0, min(255, int(round(c * 255)))) for c in rgb)


def _s2lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lin2s(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _lin(h):
    return tuple(_s2lin(c) for c in hex_to_rgb(h))


def _oklab_from_lin(rgb):
    r, g, b = rgb
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def _lin_from_oklab(lab):
    L, a, b = lab
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)


def oklab(h):
    return _oklab_from_lin(_lin(h))


def oklch(h):
    L, a, b = oklab(h)
    C = math.hypot(a, b)
    H = (math.degrees(math.atan2(b, a)) + 360) % 360
    return L, C, H


def _in_gamut(rgb, eps=1e-4):
    return all(-eps <= c <= 1 + eps for c in rgb)


def from_oklch(L, C, H):
    """OKLCH -> hex, reducing chroma until the color fits in sRGB."""
    L = max(0.0, min(1.0, L))
    hr = math.radians(H)
    lo, hi = 0.0, max(0.0, C)
    lab = (L, hi * math.cos(hr), hi * math.sin(hr))
    rgb = _lin_from_oklab(lab)
    if not _in_gamut(rgb):
        for _ in range(24):
            mid = (lo + hi) / 2
            rgb_mid = _lin_from_oklab((L, mid * math.cos(hr), mid * math.sin(hr)))
            if _in_gamut(rgb_mid):
                lo = mid
            else:
                hi = mid
        rgb = _lin_from_oklab((L, lo * math.cos(hr), lo * math.sin(hr)))
    return rgb_to_hex(tuple(_lin2s(c) for c in rgb))


# ---------------------------------------------------------------------------
# Measures
# ---------------------------------------------------------------------------
def rel_lum(h):
    r, g, b = _lin(h)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = rel_lum(a), rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _simulate(h, kind):
    r, g, b = _lin(h)
    M = MACHADO[kind]
    return tuple(max(0.0, min(1.0, M[i][0] * r + M[i][1] * g + M[i][2] * b)) for i in range(3))


def delta_e(a, b, kind=None):
    la = _oklab_from_lin(_simulate(a, kind) if kind else _lin(a))
    lb = _oklab_from_lin(_simulate(b, kind) if kind else _lin(b))
    return 100 * math.sqrt(sum((x - y) ** 2 for x, y in zip(la, lb)))


def cvd_delta(a, b):
    return min(delta_e(a, b, "protan"), delta_e(a, b, "deutan"))


def is_dark(h):
    return rel_lum(h) < 0.18


# ---------------------------------------------------------------------------
# Adjustments
# ---------------------------------------------------------------------------
def mix(a, b, t):
    """Mix a -> b by t (0..1) in OKLab. t=0 gives a."""
    la, lb = oklab(a), oklab(b)
    lab = tuple(x + (y - x) * t for x, y in zip(la, lb))
    return rgb_to_hex(tuple(_lin2s(c) for c in _lin_from_oklab(lab)))


def with_lightness(h, L, chroma_scale=1.0, max_chroma=None):
    _, C, H = oklch(h)
    C = C * chroma_scale
    if max_chroma is not None:
        C = min(C, max_chroma)
    return from_oklch(L, C, H)


def ensure_contrast(fg, bg, target=4.5):
    """Move fg's OKLCH lightness away from bg until contrast >= target.

    Hue and (as far as the gamut allows) chroma are kept, so the brand still reads
    as itself. Returns fg unchanged when it already passes."""
    fg, bg = clean_hex(fg), clean_hex(bg)
    if contrast(fg, bg) >= target:
        return fg
    L, C, H = oklch(fg)
    darker = rel_lum(bg) > 0.18
    step = -0.01 if darker else 0.01
    cand = fg
    for _ in range(100):
        L = max(0.0, min(1.0, L + step))
        cand = from_oklch(L, C, H)
        if contrast(cand, bg) >= target or L in (0.0, 1.0):
            break
    return cand


def snap_to_band(h, mode="light"):
    """Pull a color into the chart lightness band and above the chroma floor."""
    lo, hi = BAND[mode]
    L, C, H = oklch(h)
    L = min(max(L, lo + 0.01), hi - 0.01)
    if C < CHROMA_FLOOR:
        C = CHROMA_FLOOR + 0.01
    return from_oklch(L, C, H)


def readable_on(bg, light="#FFFFFF", dark="#101418", target=4.5):
    """Pick light or dark text for a filled background."""
    cl, cd = contrast(light, bg), contrast(dark, bg)
    if cl >= target and cl >= cd:
        return light
    if cd >= target:
        return dark
    return light if cl > cd else dark


# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------
def _ok_neighbors(a, b, floor=CVD_FLOOR):
    return delta_e(a, b) >= NORMAL_FLOOR and cvd_delta(a, b) >= floor


def brand_slot(primary, mode="light"):
    """The brand's chart color. Achromatic brands (black, gray) keep a neutral
    slate instead of inventing a hue."""
    primary = clean_hex(primary)
    L, C, H = oklch(primary)
    if C < 0.035:
        return from_oklch(0.40 if mode == "light" else 0.86, 0.015, 255)
    return snap_to_band(primary, mode)


def categorical(primary, accent=None, mode="light", n=6):
    """Brand color in slot 1, then validated reference hues, reference order first.

    A depth-first search walks the candidates in preference order (brand accent,
    then the reference palette) and returns the first sequence where every
    adjacent pair clears the normal-vision floor (15) and the CVD target (8), and
    no two slots anywhere are near-duplicates. If the target cannot be met it
    retries at the CVD floor (6), then returns the longest valid sequence found.
    Charts fold extra series into "Other" rather than inventing hues."""
    ref = REFERENCE[mode]
    slot1 = brand_slot(primary, mode)
    pool = []
    if accent:
        acc = brand_slot(accent, mode)
        if delta_e(acc, slot1) >= NORMAL_FLOOR + 1:
            pool.append(acc)
    pool += [c for c in ref if delta_e(c, slot1) >= NORMAL_FLOOR + 1]

    cache = {}

    def ok_adj(a, b, floor):
        key = (a, b, floor)
        if key not in cache:
            cache[key] = _ok_neighbors(a, b, floor)
        return cache[key]

    best = [slot1]
    for floor in (CVD_TARGET, CVD_FLOOR):
        found = [None]
        longest = [[slot1]]

        def dfs(seq, remaining):
            if found[0] is not None:
                return
            if len(seq) > len(longest[0]):
                longest[0] = list(seq)
            if len(seq) == n:
                found[0] = list(seq)
                return
            for i, cand in enumerate(remaining):
                if not ok_adj(seq[-1], cand, floor):
                    continue
                if any(delta_e(cand, used) < 10 for used in seq):
                    continue
                dfs(seq + [cand], remaining[:i] + remaining[i + 1:])
                if found[0] is not None:
                    return

        dfs([slot1], pool)
        if found[0] is not None:
            return found[0]
        if len(longest[0]) > len(best):
            best = longest[0]
    return best


def sequential(primary, mode="light", steps=7):
    """One-hue ramp for magnitude (heatmaps). Light end recedes toward the page."""
    _, C, H = oklch(snap_to_band(primary, mode))
    C = max(C, 0.12)
    if mode == "light":
        Ls = [0.96 - i * (0.96 - 0.36) / (steps - 1) for i in range(steps)]
        Cs = [C * (0.18 + 0.82 * i / (steps - 1)) for i in range(steps)]
    else:
        Ls = [0.26 + i * (0.80 - 0.26) / (steps - 1) for i in range(steps)]
        Cs = [C * (0.30 + 0.70 * i / (steps - 1)) for i in range(steps)]
    return [from_oklch(L, c, H) for L, c in zip(Ls, Cs)]


def ordinal(primary, n, mode="light", surface="#FFFFFF"):
    """Discrete ordered ramp (funnel stages). Darkest first, light end >= 2:1."""
    _, C, H = oklch(snap_to_band(primary, mode))
    C = max(C, 0.11)
    if n <= 1:
        return [snap_to_band(primary, mode)]
    if mode == "light":
        start, end = 0.42, 0.80
    else:
        start, end = 0.78, 0.46
    out = []
    for i in range(n):
        L = start + (end - start) * i / (n - 1)
        out.append(from_oklch(L, C * (1 - 0.25 * i / (n - 1)), H))
    # keep the pale end readable as a mark
    while contrast(out[-1], surface) < 2.0 and mode == "light":
        out = [with_lightness(c, oklch(c)[0] - 0.03) for c in out]
    return out


def diverging(primary, mode="light"):
    """Cool pole / neutral / warm pole. The brand supplies the cool pole when it is cool."""
    _, _, H = oklch(primary)
    cool = snap_to_band(primary, mode) if 150 <= H <= 300 else REFERENCE[mode][0]
    warm = REFERENCE[mode][7]
    mid = "#EDEDEA" if mode == "light" else "#383835"
    return cool, mid, warm


def tint(h, page="#FFFFFF", amount=0.08):
    """Very pale brand tint for fills, mixed toward the page color."""
    return mix(page, clean_hex(h), amount)


def validate(palette, mode="light"):
    """Return (ok, worst_normal, worst_cvd) over adjacent pairs."""
    worst_n, worst_c = 99.0, 99.0
    for a, b in zip(palette, palette[1:]):
        worst_n = min(worst_n, delta_e(a, b))
        worst_c = min(worst_c, cvd_delta(a, b))
    return (worst_n >= NORMAL_FLOOR and worst_c >= CVD_FLOOR), worst_n, worst_c
