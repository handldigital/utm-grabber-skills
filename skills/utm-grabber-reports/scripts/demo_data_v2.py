"""
Demo data v2: synthetic, internally consistent, multi-platform demo datasets for
the v2 report recipes.

    from demo_data_v2 import get_dataset, list_datasets
    ds = get_dataset("northwind")   # local dental clinic: Google Ads + Meta Ads + GA4 + HubSpot
    ds = get_dataset("harbor")      # home goods store: WooCommerce + Google/Meta/Microsoft Ads + GA4 + HubSpot

Every source joins to every other one:
  * paid leads carry utm_campaign == connectors.norm_key(ad campaign name) and
    utm_content == norm_key(ad name); Google search leads carry a real keyword in utm_term
  * GA4 visit rows share the leads' lowercase (source, medium) and landing pages
  * HubSpot deals share the leads' lowercase emails
  * WooCommerce orders carry the same UTM Grabber fields as leads

Ad, visit and deal rows are already in the connectors.py normalized shapes
(AdRow, VisitRow, DealRow). Lead and order entries use the named UTM Grabber keys
from references/data-dictionary.md.

Deterministic (seeded random.Random instances with md5-derived sub-seeds, never the
global random state, never hash()). Standard library only, Python 3.9 compatible.
Each (dataset, seed) is built once and cached in memory: treat the result as read-only.
"""
import bisect
import datetime as _dt
import hashlib
import math
import os
import random
import string
import sys
from collections import Counter, defaultdict

try:
    from urllib.parse import quote_plus
except ImportError:  # pragma: no cover
    from urllib import quote_plus

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from connectors import norm_key  # noqa: E402

YEAR = 2026
HISTORY_MONTHS = (4, 5, 6, 7, 8, 9)  # April 1 to September 30: Q2 and Q3 2026
CURRENT_MONTH, PRIOR_MONTH = 9, 8
ASOF = _dt.date(2026, 10, 5)  # "today": CRM stages reflect what was known on this day
DEFAULT_SEEDS = {"northwind": 9301, "harbor": 9302}
CLIENTS_SEED = 9303
_CACHE = {}
_CLIENT_CACHE = {}


# ---------------------------------------------------------------------------
# Small deterministic utilities
# ---------------------------------------------------------------------------
def _sub_seed(*parts):
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return int(hashlib.md5(raw).hexdigest()[:15], 16)


def _rng(*parts):
    return random.Random(_sub_seed(*parts))


def _month_days(month):
    d = _dt.date(YEAR, month, 1)
    out = []
    while d.month == month:
        out.append(d)
        d += _dt.timedelta(days=1)
    return out


def _pick(r, weighted):
    """weighted: list of (value, weight) pairs."""
    vals = [v for v, _ in weighted]
    ws = [w for _, w in weighted]
    return r.choices(vals, weights=ws, k=1)[0]


def _alloc(r, n, weights):
    """Spread n items over the buckets at random, proportional to weights."""
    counts = [0] * len(weights)
    if n <= 0 or not weights or sum(weights) <= 0:
        return counts
    for i in r.choices(range(len(weights)), weights=weights, k=n):
        counts[i] += 1
    return counts


def _spread(r, n, weights):
    """Low-variance allocation (systematic sampling): every bucket gets its expected share, rounded
    up or down. Used where a planted shape must not drown in multinomial noise."""
    counts = [0] * len(weights)
    total = float(sum(weights))
    if n <= 0 or total <= 0:
        return counts
    step = total / n
    pos = r.uniform(0, step)
    acc, i = 0.0, 0
    for k in range(n):
        target = pos + k * step
        while i < len(weights) - 1 and acc + weights[i] < target:
            acc += weights[i]
            i += 1
        counts[i] += 1
    return counts


def _split_exact(total, weights):
    """Largest-remainder integer split of total (deterministic, sums exactly)."""
    s = float(sum(weights))
    if total <= 0 or s <= 0:
        return [0] * len(weights)
    raw = [total * w / s for w in weights]
    base = [int(x) for x in raw]
    order = sorted(range(len(weights)), key=lambda i: (-(raw[i] - base[i]), i))
    for i in order[:total - sum(base)]:
        base[i] += 1
    return base


_TOKEN = string.ascii_letters + string.digits


def _token(r, n, alphabet=_TOKEN):
    return "".join(r.choice(alphabet) for _ in range(n))


def _gclid(r):
    return "Cj0KCQjw" + _token(r, 44, _TOKEN + "_-")


def _wbraid(r):
    return "CjkKCQjw" + _token(r, 36, _TOKEN + "_-")


def _fbclid(r):
    return "IwAR" + _token(r, 52, _TOKEN + "_-")


def _msclkid(r):
    return _token(r, 32, "0123456789abcdef")


def _path(url):
    u = str(url or "").split("://", 1)[-1]
    u = "/" + u.split("/", 1)[1] if "/" in u else "/"
    u = u.split("?")[0].split("#")[0]
    return u if u == "/" else u.rstrip("/")


def _join_key(e):
    """The (source, medium) key connectors.join_visits_to_leads files a lead under."""
    src = str(e.get("utm_source (HandL)") or "").strip().lower()
    med = str(e.get("utm_medium (HandL)") or "").strip().lower()
    if not src and not med:
        return ("(direct)", "(none)")
    return (src or "(not set)", med or "(not set)")


# ---------------------------------------------------------------------------
# People, devices
# ---------------------------------------------------------------------------
_FIRST = ["Avery", "Jordan", "Maya", "Priya", "Daniel", "Sofia", "Marcus", "Elena", "Noah", "Hannah",
          "Omar", "Grace", "Leo", "Chloe", "Ethan", "Aisha", "Lucas", "Nora", "Mateo", "Ruby", "Isaac",
          "Leah", "Caleb", "Zoe", "Owen", "Ivy", "Felix", "Amara", "Theo", "Clara", "Jonah", "Mei",
          "Elijah", "Lila", "Gabriel", "Naomi", "Adrian", "Hazel", "Samir", "Julia", "Wesley", "Tessa",
          "Rohan", "Paige", "Diego", "Freya", "Malik", "Camila", "Simon", "Esther", "Kenji", "Bianca",
          "Victor", "Sadie", "Andre", "Lucia", "Emmett", "Jada", "Rafael", "Wren", "Harper", "Nikhil",
          "Rosa", "Tobias", "Imani", "Quinn", "Anya", "Gideon", "Marisol", "Hugo"]
_LAST = ["Alvarez", "Brennan", "Castillo", "Delgado", "Ellison", "Fairbanks", "Gallagher", "Holloway",
         "Ibarra", "Jansen", "Kowalski", "Lindqvist", "Mercado", "Nakamura", "Okafor", "Pemberton",
         "Quintero", "Rasmussen", "Salazar", "Thornton", "Underwood", "Valdez", "Whitfield", "Yamamoto",
         "Zielinski", "Abernathy", "Bachman", "Calloway", "Dunleavy", "Eastman", "Ferreira", "Gutierrez",
         "Hendricks", "Iverson", "Jaramillo", "Kaplan", "Lockhart", "Moreno", "Navarro", "Osei",
         "Prescott", "Radcliffe", "Sandoval", "Tran", "Vance", "Winslow", "Brandt", "Coleman",
         "Dimitrov", "Esposito", "Grantham", "Haddad", "Ingram", "Juarez", "Kimura", "Larkin",
         "McAllister", "Novak", "Oyelaran", "Reyes", "Sorensen", "Takahashi", "Ueda", "Vasquez",
         "Whitaker", "Yilmaz", "Zamora", "Bhatt", "Chen", "Duarte", "Engel", "Farouk", "Greer", "Huang",
         "Lindgren", "Mehta", "Nguyen", "Ostrowski", "Petrakis", "Sato"]
_BLOCKED_NAMES = {("ivy", "park"), ("grace", "park"), ("diego", "reyes")}
# Reserved example domains (RFC 2606): realistic-looking addresses that can never reach a real inbox.
_MAIL_DOMAINS = [("example.com", 46), ("example.net", 26), ("example.org", 16), ("mail.example.com", 12)]


class _People(object):
    """Invents people with unique lowercase emails."""

    def __init__(self, r, area_codes=None):
        self.r = r
        self.area = area_codes or []
        self.used = set()  # membership tests only, never iterated

    def new(self, company_domain=None):
        r = self.r
        while True:
            first, last = r.choice(_FIRST), r.choice(_LAST)
            if (first.lower(), last.lower()) not in _BLOCKED_NAMES:
                break
        f = first.lower()
        l = last.lower()
        if company_domain:
            local = r.choice(["%s.%s" % (f, l), "%s%s" % (f[0], l), f, "%s.%s" % (f, l)])
            dom = company_domain
        else:
            local = r.choice(["%s.%s" % (f, l), "%s%s" % (f, l), "%s%s%d" % (f, l, r.randint(1, 99)),
                              "%s_%s" % (f, l), "%s%s" % (f[0], l), "%s.%s%d" % (f, l, r.randint(70, 99)),
                              "%s.%s" % (f, l)])
            dom = _pick(r, _MAIL_DOMAINS)
        email = "%s@%s" % (local, dom)
        k = 2
        while email in self.used:
            email = "%s%d@%s" % (local, k, dom)
            k += 1
        self.used.add(email)
        p = {"first": first, "last": last, "email": email}
        if self.area:
            p["phone"] = "(%s) 555-%04d" % (r.choice(self.area), r.randint(200, 9999))
        return p


_UA = {
    "iphone": [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0.1 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.7 Mobile/15E148 Safari/604.1"],
    "android": [
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"],
    "windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"],
    "mac": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"],
}
_UA_INAPP = {
    ("iphone", "facebook"): "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 [FBAN/FBIOS;FBAV/521.0.0.38.104;FBBV/783412940;FBDV/iPhone16,2;FBMD/iPhone;FBSN/iOS;FBSV/18.6;FBSS/3;FBID/phone;FBLC/en_US;FBOP/5]",
    ("iphone", "instagram"): "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 398.0.0.31.87 (iPhone15,3; iOS 18_6; en_US; en; scale=3.00; 1290x2796; 791245631)",
    ("android", "facebook"): "Mozilla/5.0 (Linux; Android 14; SM-S921U Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/140.0.7339.51 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/521.0.0.44.98;]",
    ("android", "instagram"): "Mozilla/5.0 (Linux; Android 14; Pixel 8 Build/AP2A.240905.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/140.0.7339.51 Mobile Safari/537.36 Instagram 398.0.0.31.87 Android (34/14; 420dpi; 1080x2400; Google/google; Pixel 8; shiba; shiba; en_US; 801234567)",
}
_DEVICES = [("iphone", 45), ("android", 20), ("windows", 20), ("mac", 15)]


def _user_agent(r, touch, dev):
    src = touch.get("source", "").lower()
    if dev in ("iphone", "android") and src in ("facebook", "instagram") and r.random() < 0.55:
        return _UA_INAPP[(dev, src)]
    return r.choice(_UA[dev])


# ---------------------------------------------------------------------------
# Shared stream templates
# ---------------------------------------------------------------------------
# (id, utm_source, utm_medium, organic_source_str, ref domain, referrer, share of AI leads)
_AI = [
    ("ai_chatgpt", "chatgpt.com", "", "OpenAI/ChatGPT", "chatgpt.com", "https://chatgpt.com/", 55),
    ("ai_perplexity", "perplexity.ai", "referral", "Perplexity", "perplexity.ai", "https://www.perplexity.ai/", 17),
    ("ai_gemini", "gemini.google.com", "referral", "Gemini", "gemini.google.com", "https://gemini.google.com/", 12),
    ("ai_copilot", "copilot.microsoft.com", "referral", "Copilot", "copilot.microsoft.com", "https://copilot.microsoft.com/", 9),
    ("ai_claude", "claude.ai", "referral", "Claude", "claude.ai", "https://claude.ai/", 7),
]


def _ai_streams(totals, orders=None, rate=0.025):
    out = []
    for sid, src, med, org, ref, referrer, _w in _AI:
        out.append(dict(id=sid, kind="ai", role="ai", source=src, medium=med, org=org, ref=ref,
                        referrer=referrer, targets={}, orders={}, rate=rate))
    for key, src_totals in (("targets", totals), ("orders", orders or {})):
        for m, tot in src_totals.items():
            for s, n in zip(out, _split_exact(tot, [a[6] for a in _AI])):
                s[key][m] = n
    return out


def _organic_streams(google, bing, ddg, orders=None):
    spec = [("org_google", "google", "Google", "google.com", "https://www.google.com/", google, 0.018),
            ("org_bing", "bing", "Bing", "bing.com", "https://www.bing.com/", bing, 0.022),
            ("org_ddg", "duckduckgo", "DuckDuckGo", "duckduckgo.com", "https://duckduckgo.com/", ddg, 0.024)]
    out = []
    for i, (sid, src, org, ref, referrer, tg, rate) in enumerate(spec):
        out.append(dict(id=sid, kind="organic", role="organic", source=src, medium="organic", org=org, ref=ref,
                        referrer=referrer, targets=tg, orders=(orders[i] if orders else {}), rate=rate))
    return out


# Which channel a journey started on, given the channel that closed it:
# role -> (probability first touch differs, [(first-touch role, weight)]).
# Meta prospecting and AI assistants open journeys that brand search and direct visits close.
_TRANSITIONS = {
    "brand": (0.65, [("prospect", 30), ("ai", 25), ("organic", 25), ("search", 10), ("referral", 10)]),
    "direct": (0.60, [("prospect", 25), ("organic", 25), ("ai", 20), ("search", 15), ("referral", 15)]),
    "retarget": (0.90, [("search", 40), ("prospect", 35), ("organic", 25)]),
    "email": (0.75, [("organic", 30), ("search", 25), ("prospect", 20), ("direct", 15), ("brand", 10)]),
    "search": (0.33, [("prospect", 40), ("ai", 30), ("organic", 30)]),
    "shopping": (0.30, [("prospect", 45), ("organic", 30), ("ai", 25)]),
    "organic": (0.25, [("ai", 40), ("prospect", 30), ("referral", 30)]),
    "prospect": (0.11, [("organic", 50), ("ai", 50)]),
    "ai": (0.05, [("organic", 100)]),
    "social": (0.10, [("organic", 50), ("ai", 50)]),
    "referral": (0.10, [("organic", 50), ("ai", 50)]),
}


# ---------------------------------------------------------------------------
# Northwind Dental: local services, lead gen, Google Ads + Meta Ads + HubSpot
# ---------------------------------------------------------------------------
_NW_SERVICES = [("Cleaning", 30), ("Checkup", 28), ("Emergency", 12), ("Whitening", 10), ("Invisalign", 11),
                ("Implants", 9)]
_NW_AMOUNTS = {"Cleaning": (180, 350), "Checkup": (150, 320), "Whitening": (400, 700),
               "Invisalign": (3500, 6000), "Implants": (3000, 5500), "Emergency": (250, 900)}
_NW_EMBED = {"/", "/emergency-dentist", "/invisalign", "/dental-implants", "/teeth-whitening", "/new-patients",
             "/whitening-offer", "/invisalign-consult", "/new-patient-special", "/book-appointment", "/insurance"}


def _nw_biz(r, s):
    svc = s.get("service")
    if not svc or r.random() < 0.07:
        svc = _pick(r, _NW_SERVICES)
    ins = _pick(r, [("Yes", 58), ("No", 22), ("Not sure", 20)])
    if svc == "Emergency":
        pref = _pick(r, [("As soon as possible", 80), ("Weekday evening", 10), ("Saturday", 10)])
    else:
        pref = _pick(r, [("Weekday morning", 35), ("Weekday afternoon", 25), ("Weekday evening", 20),
                         ("Saturday", 20)])
    form = "2" if svc == "Emergency" and r.random() < 0.85 else "1"
    return form, {"Service": svc, "Insurance": ins, "Preferred Time": pref}, None


def _nw_source_url(r, p, s, page, form):
    if form == "2":
        return p["base"] + "/emergency-dentist"
    if page in _NW_EMBED and r.random() < 0.75:
        return p["base"] + page
    return p["base"] + "/book-appointment"


def _nw_amount(r, e):
    lo, hi = _NW_AMOUNTS.get(e.get("Service"), (180, 350))
    return float(int(r.uniform(lo, hi) / 5) * 5)


def _m(*vals):
    """A monthly series for April to September 2026."""
    return dict(zip(HISTORY_MONTHS, vals))


def _northwind():
    G, M = "Google Ads", "Meta Ads"
    S = [
        dict(id="g_brand", kind="paid", platform=G, role="brand", campaign="Brand - Northwind Dental",
             ad_group="Brand terms", ads=[("RSA - Northwind Official", 6), ("RSA - Book Online Today", 4)],
             keywords=[("northwind dental", 55), ("northwind dental alder bay", 25), ("northwind dentist", 20)],
             page="/", targets=_m(86, 87, 88, 88, 94, 105), spend=_m(1100, 1120, 1140, 1150, 1180, 1250),
             cpc=1.40, ctr=0.22),
        dict(id="g_emergency", kind="paid", platform=G, role="search", campaign="Emergency Dentist - Exact",
             ad_group="Emergency core", ads=[("RSA - Same Day Emergency Care", 6), ("RSA - Open Late Tonight", 4)],
             keywords=[("emergency dentist", 34), ("emergency dentist near me", 30), ("dentist open now", 14),
                       ("same day dentist", 12), ("tooth pain dentist", 10)],
             page="/emergency-dentist", targets=_m(103, 104, 106, 103, 106, 118),
             spend=_m(5100, 5150, 5200, 5250, 5300, 5600), cpc=4.20, ctr=0.085, service="Emergency",
             hours="emergency", dow="emergency"),
        dict(id="g_invisalign", kind="paid", platform=G, role="search", campaign="Invisalign - Phrase",
             ad_group="Invisalign", ads=[("RSA - Free Invisalign Consult", 5), ("RSA - Clear Aligners Monthly Plan", 5)],
             keywords=[("invisalign cost", 32), ("invisalign near me", 30), ("clear aligners", 22),
                       ("invisalign dentist", 16)],
             page="/invisalign", targets=_m(46, 46, 47, 45, 47, 52), spend=_m(3050, 3080, 3100, 3120, 3150, 3300),
             cpc=3.60, ctr=0.06, service="Invisalign"),
        dict(id="g_implants", kind="paid", platform=G, role="search", campaign="Dental Implants - Phrase",
             ad_group="Implants", ads=[("RSA - Implants Done in One Place", 5), ("RSA - Implant Financing", 5)],
             keywords=[("dental implants cost", 34), ("tooth implant near me", 28), ("implant dentist", 22),
                       ("all on 4 implants", 16)],
             wasted=[("free dental implants", 0.18)],
             page="/dental-implants", targets=_m(33, 33, 33, 32, 32, 34), spend=_m(3700, 3720, 3750, 3780, 3800, 3900),
             cpc=5.80, ctr=0.05, service="Implants"),
        dict(id="g_whitening", kind="paid", platform=G, role="search", campaign="Teeth Whitening - Broad",
             ad_group="Whitening", ads=[("RSA - Professional Whitening", 5), ("RSA - Whiter in One Visit", 5)],
             keywords=[("teeth whitening", 40), ("professional teeth whitening", 34), ("teeth whitening near me", 26)],
             wasted=[("diy teeth whitening kit", 0.15)],
             page="/teeth-whitening", targets=_m(37, 37, 38, 36, 36, 38), spend=_m(2000, 2010, 2020, 2030, 2050, 2100),
             cpc=2.10, ctr=0.055, service="Whitening"),
        dict(id="g_general", kind="paid", platform=G, role="search", campaign="General Dentistry - Local",
             ad_group="General", ads=[("RSA - New Patients Welcome", 5), ("RSA - Family Dentist Alder Bay", 5)],
             keywords=[("dentist near me", 36), ("family dentist", 22), ("dental cleaning", 18),
                       ("dental checkup", 14), ("new patient dentist", 10)],
             wasted=[("dental hygienist jobs", 0.08)],
             page="/new-patients", targets=_m(62, 64, 65, 61, 62, 68), spend=_m(2500, 2520, 2550, 2580, 2600, 2700),
             cpc=2.60, ctr=0.065),
        dict(id="m_retarget", kind="paid", platform=M, role="retarget", campaign="Retargeting - Site Visitors",
             ad_group="Site visitors 30 days", ads=[("Carousel - Smile Gallery", 5), ("Video - Tour the Clinic", 5)],
             page="/new-patients", targets=_m(46, 49, 54, 60, 66, 72), spend=_m(1300, 1400, 1500, 1600, 1700, 1800),
             cpm=21.0, ctr=0.019, fb_share=0.6),
        dict(id="m_prospect", kind="paid", platform=M, role="prospect", campaign="Prospecting - Lookalike New Patients",
             ad_group="Lookalike 3 percent new patients",
             ads=[("Static - New Patient Special", 4), ("Reel - First Visit Walkthrough", 3),
                  ("Carousel - Family Care", 3)],
             page="/new-patient-special", targets=_m(60, 64, 70, 80, 86, 95),
             spend=_m(2600, 2800, 3100, 3300, 3500, 3600), cpm=11.5, ctr=0.021, fb_share=0.58, over_fixed=1.60),
        dict(id="m_whitening", kind="paid", platform=M, role="prospect", campaign="Whitening Offer",
             ad_group="Women 25 to 54 within 10 miles",
             ads=[("Static - $99 Whitening", 9), ("Reel - Before and After", 1)],
             page="/whitening-offer", targets=_m(45, 48, 52, 64, 74, 32), spend=_m(1100, 1200, 1300, 1450, 1550, 1500),
             cpm=12.5, ctr=0.024, fb_share=0.55, service="Whitening",
             fatigue={"ad": "Static - $99 Whitening", "start": _dt.date(2026, 8, 30), "half_life": 6.0}),
        dict(id="m_invisalign", kind="paid", platform=M, role="prospect", campaign="Invisalign Consult Promo",
             ad_group="Adults 22 to 45 interested in orthodontics",
             ads=[("Reel - Aligner Day in the Life", 5), ("Static - Free Consult and Scan", 5)],
             page="/invisalign-consult", targets=_m(24, 24, 24, 36, 42, 88), spend=_m(700, 700, 700, 900, 1100, 2200),
             cpm=13.0, ctr=0.022, fb_share=0.5, service="Invisalign"),
    ]
    S += _organic_streams(_m(114, 116, 118, 117, 118, 128), _m(15, 15, 15, 15, 14, 15), _m(6, 6, 6, 6, 6, 7))
    S += _ai_streams(_m(16, 21, 27, 34, 42, 60))
    newsletter = [("monthly_newsletter", 1)]
    S += [
        dict(id="soc_facebook", kind="social", role="social", source="facebook", medium="social",
             ref="facebook.com", referrer="https://m.facebook.com/", targets=_m(10, 10, 10, 9, 10, 10), rate=0.012),
        dict(id="soc_instagram", kind="social", role="social", source="instagram", medium="social",
             ref="instagram.com", referrer="https://l.instagram.com/", targets=_m(7, 8, 8, 8, 8, 8), rate=0.012),
        dict(id="soc_tiktok", kind="social", role="social", source="tiktok", medium="organic", campaign="bio_link",
             ref="tiktok.com", referrer="https://www.tiktok.com/", targets=_m(0, 0, 0, 0, 0, 20), rate=0.011),
        dict(id="email", kind="email", role="email", source="newsletter", medium="email",
             campaigns=dict((m, newsletter) for m in HISTORY_MONTHS),
             alt_campaign="recall_reminder", alt_share=0.4, contents=["cta_button", "header_link", "footer_link"],
             targets=_m(38, 39, 40, 40, 42, 45), rate=0.045),
        dict(id="ref_parents", kind="referral", role="referral", source="alderbayparents.org",
             campaign="family_dentist_guide", ref="alderbayparents.org",
             referrer="https://alderbayparents.org/best-family-dentists", tagged=0.75,
             targets=_m(15, 15, 15, 15, 16, 18), rate=0.036),
        dict(id="ref_chamber", kind="referral", role="referral", source="alderbaychamber.org",
             campaign="member_directory", ref="alderbaychamber.org",
             referrer="https://alderbaychamber.org/directory/health", tagged=0.6,
             targets=_m(8, 9, 9, 9, 9, 10), rate=0.032),
        dict(id="ref_directory", kind="referral", role="referral", source="alderbayhealthdirectory.org",
             campaign="provider_listing", ref="alderbayhealthdirectory.org",
             referrer="https://alderbayhealthdirectory.org/dentists", tagged=0.8,
             targets=_m(10, 10, 10, 10, 11, 12), rate=0.038),
        dict(id="direct", kind="direct", role="direct", targets=_m(72, 73, 74, 74, 78, 85), rate=0.015),
    ]
    return dict(
        name="northwind", domain="northwinddental.com", form_label="Gravity Forms",
        industry="Dental clinic (local services)",
        brand={"company_name": "Northwind Dental", "logo": {"type": "text", "value": "Northwind Dental"},
               "colors": {"primary": "#0E7C66", "accent": "#F2A541", "ink": "#0B1F1A", "muted": "#5A6B64",
                          "surface": "#EEF7F4"}},
        forms=[{"id": "1", "title": "Book a consult"}, {"id": "2", "title": "Emergency visit request"},
               {"id": "3", "title": "Smile giveaway (spring)"}],
        dow={"default": [1.0, 1.25, 1.2, 1.15, 0.9, 0.45, 0.35], "emergency": [1.1, 1.0, 1.0, 1.0, 1.05, 0.95, 0.9]},
        hours={"default": [0.04, 0.02, 0.01, 0.01, 0.02, 0.08, 0.3, 0.85, 1.55, 2.05, 2.15, 1.85, 1.65, 1.55,
                           1.4, 1.25, 1.1, 1.0, 0.95, 1.05, 1.0, 0.75, 0.4, 0.15],
               "emergency": [0.25, 0.15, 0.1, 0.1, 0.15, 0.3, 0.6, 1.0, 1.3, 1.4, 1.4, 1.3, 1.3, 1.25, 1.2, 1.15,
                             1.15, 1.2, 1.3, 1.45, 1.5, 1.3, 0.9, 0.5]},
        morning_boost=1.3,
        holidays={_dt.date(2026, 5, 25): 0.45, _dt.date(2026, 7, 4): 0.3, _dt.date(2026, 9, 7): 0.45},
        spend_dow=[1.05, 1.08, 1.06, 1.04, 0.98, 0.9, 0.89],
        session_ratio=0.86,
        streams=S,
        pages={"organic": [("/", 30), ("/emergency-dentist", 15), ("/invisalign", 12), ("/dental-implants", 10),
                           ("/teeth-whitening", 8), ("/new-patients", 10), ("/insurance", 10),
                           ("/book-appointment", 5)],
               "ai": [("/", 25), ("/emergency-dentist", 20), ("/invisalign", 20), ("/dental-implants", 20),
                      ("/insurance", 15)],
               "social": [("/", 40), ("/whitening-offer", 30), ("/new-patients", 30)],
               "email": [("/book-appointment", 50), ("/whitening-offer", 25), ("/invisalign-consult", 25)],
               "referral": [("/", 50), ("/new-patients", 30), ("/insurance", 20)],
               "direct": [("/", 60), ("/book-appointment", 25), ("/new-patients", 15)]},
        dead={"organic": [("/blog/how-long-does-teeth-whitening-last", 0.26), ("/blog/chipped-tooth-what-to-do", 0.16),
                          ("/careers", 0.08)],
              "ai": [("/blog/chipped-tooth-what-to-do", 0.12)],
              "social": [("/blog/how-long-does-teeth-whitening-last", 0.25)],
              "direct": [("/careers", 0.2), ("/blog/how-long-does-teeth-whitening-last", 0.05)],
              "referral": [("/careers", 0.08)]},
        blog_first_touch=0.012,
        biz=_nw_biz, source_url=_nw_source_url,
        repeat_rate=0.025, area_codes=["360", "564", "253"],
        over={"Google Ads": 1.23, "Meta Ads": 1.28},
        entry_start=16420, deal_start=41875200000,
        strip_rate=0.08, typo_rate=0.03, case_rate=0.05, fbclid_rate=0.40,
        dormant={"form": "3", "service": "Whitening", "counts": _m(4, 3, 3, 2, 2, 2)},
        deal=dict(pipeline="New patients", eligible=None,
                  p_role={"brand": 0.57, "search": 0.48, "retarget": 0.47, "prospect": 0.31, "organic": 0.49,
                          "ai": 0.54, "social": 0.35, "email": 0.49, "referral": 0.57, "direct": 0.51},
                  p_default=0.42, p_field=("Service", {"Emergency": 1.15, "Implants": 0.9, "Invisalign": 0.95}),
                  outcomes=[("won", 50), ("lost", 40), ("open", 10)],
                  outcomes_role={"prospect": [("won", 42), ("lost", 48), ("open", 10)],
                                 "brand": [("won", 56), ("lost", 34), ("open", 10)]},
                  amount=_nw_amount, create_mean=2.5, close_mean=4.5, unmatched=0.04),
    )


# ---------------------------------------------------------------------------
# Harbor Linen Co.: home goods e-commerce, WooCommerce + Google/Meta/Microsoft Ads
# ---------------------------------------------------------------------------
_HB_INQ = [("Newsletter", 70), ("Order question", 18), ("Quote request", 8), ("Wholesale", 4)]
_HB_INQ_B2B = [("Wholesale", 50), ("Quote request", 38), ("Order question", 6), ("Newsletter", 6)]
_HB_FORM = {"Newsletter": "1", "Quote request": "2", "Wholesale": "2", "Order question": "3"}
_HB_CO_A = ["Saltgrass", "Willow Creek", "Bayview", "Cedar Hollow", "Tidewater", "Marigold", "Juniper",
            "Lanternfish", "Driftwood", "Fernway", "Pebble Point", "Old Mill", "Sandpiper", "Bluff Street",
            "Gull Rock", "Kestrel", "Meadowlark", "Sorrel", "Whistling Pine", "Low Tide"]
_HB_CO_B = ["Inn", "Rentals", "Boutique Hotel", "Lodge", "Cottages", "Guesthouse", "Bistro", "Spa",
            "Vacation Homes", "Interiors", "Bed and Breakfast", "Supper Club"]
_CATALOG = {
    "bedding": [("Stonewashed Linen Duvet Cover", 189.0), ("Linen Sheet Set", 159.0), ("Linen Pillowcase Pair", 48.0),
                ("Waffle Knit Blanket", 119.0)],
    "bath": [("Waffle Bath Towel Set", 89.0), ("Turkish Hand Towels (2)", 34.0), ("Linen Shower Curtain", 78.0),
             ("Cotton Bath Mat", 42.0)],
    "kitchen": [("Linen Tea Towels (3)", 29.0), ("Ceramic Pour-Over Set", 64.0), ("Stoneware Mug", 24.0),
                ("Linen Napkins (4)", 38.0), ("Linen Apron", 42.0)],
    "decor": [("Wool Throw Blanket", 129.0), ("Beeswax Taper Candles (2)", 22.0), ("Rattan Storage Basket", 58.0),
              ("Linen Cushion Cover", 46.0)],
}
_CATEGORY_MIX = [("bedding", 42), ("bath", 24), ("kitchen", 18), ("decor", 16)]


def _hb_biz(r, s):
    inq = _pick(r, s.get("inquiry") or _HB_INQ)
    biz = {"Inquiry Type": inq}
    dom = None
    if inq in ("Quote request", "Wholesale"):
        name = "%s %s" % (r.choice(_HB_CO_A), r.choice(_HB_CO_B))
        biz["Company"] = name
        dom = norm_key(name).replace("_", "") + ".example"
    return _HB_FORM[inq], biz, dom


def _hb_source_url(r, p, s, page, form):
    if form == "2":
        return p["base"] + "/wholesale"
    if form == "3":
        return p["base"] + "/contact"
    if r.random() < 0.7:
        return p["base"] + page
    return p["base"] + r.choice(["/", "/collections/linen-bedding", "/collections/best-sellers"])


def _hb_amount(r, e):
    v = math.exp(r.uniform(math.log(1500), math.log(12000)))
    return float(int(v / 50) * 50)


def _harbor():
    G, M, B = "Google Ads", "Meta Ads", "Microsoft Ads"
    S = [
        dict(id="g_brand", kind="paid", platform=G, role="brand", campaign="Brand - Harbor Linen",
             ad_group="Brand terms", ads=[("RSA - Harbor Linen Official Store", 6), ("RSA - Free Shipping Over $75", 4)],
             keywords=[("harbor linen", 55), ("harbor linen co", 30), ("harbor linen duvet", 15)],
             page="/", targets=_m(78, 80, 82, 80, 84, 100), orders=_m(56, 58, 60, 61, 62, 70),
             spend=_m(1350, 1380, 1400, 1420, 1450, 1500), cpc=0.95, ctr=0.2),
        dict(id="g_shopping", kind="paid", platform=G, role="shopping", campaign="Shopping - All Products",
             ad_group="All products", ads=[("Bedding", 40), ("Bath", 25), ("Kitchen", 20), ("Decor", 15)],
             page_by_ad={"Bedding": "/products/stonewashed-linen-duvet-cover", "Bath": "/products/waffle-bath-towel-set",
                         "Kitchen": "/products/ceramic-pour-over-set", "Decor": "/products/wool-throw-blanket"},
             category_by_ad={"Bedding": "bedding", "Bath": "bath", "Kitchen": "kitchen", "Decor": "decor"},
             targets=_m(86, 88, 90, 89, 94, 112), orders=_m(98, 101, 104, 106, 108, 120),
             spend=_m(7600, 7900, 8200, 8400, 8600, 8000), cpc=3.10, ctr=0.012),
        dict(id="g_pmax", kind="paid", platform=G, role="shopping", campaign="PMax - Home Essentials",
             ad_group="Asset groups", ads=[("Linen Bedding", 45), ("Bath Towels", 30), ("Gift Guide", 25)],
             page_by_ad={"Linen Bedding": "/collections/linen-bedding", "Bath Towels": "/collections/bath",
                         "Gift Guide": "/gift-guide"},
             category_by_ad={"Linen Bedding": "bedding", "Bath Towels": "bath", "Gift Guide": "decor"},
             targets=_m(66, 69, 70, 70, 76, 92), orders=_m(78, 81, 84, 86, 88, 95),
             spend=_m(6400, 6600, 6900, 7100, 7400, 7200), cpc=3.40, ctr=0.018),
        dict(id="g_linen", kind="paid", platform=G, role="search", campaign="Search - Linen Bedding",
             ad_group="Linen bedding", ads=[("RSA - Stonewashed Linen Bedding", 5), ("RSA - Sleep Cooler in Linen", 5)],
             keywords=[("linen duvet cover", 36), ("linen sheets", 30), ("stonewashed linen bedding", 20),
                       ("linen bedding set", 14)],
             wasted=[("linen fabric by the yard", 0.18), ("how to wash linen sheets", 0.12)],
             page="/collections/linen-bedding", category="bedding",
             targets=_m(64, 64, 65, 62, 52, 22), orders=_m(62, 63, 64, 60, 55, 30),
             spend=_m(3300, 3300, 3300, 3300, 3300, 3200), cpc=3.20, ctr=0.055),
        dict(id="g_wholesale", kind="paid", platform=G, role="search", campaign="Search - Wholesale Linens",
             ad_group="Wholesale", ads=[("RSA - Hotel and Rental Linens Wholesale", 6),
                                        ("RSA - Bulk Towels for Hospitality", 4)],
             keywords=[("wholesale linen supplier", 32), ("bulk towels for hotels", 28), ("linen wholesale", 22),
                       ("airbnb linens bulk", 18)],
             wasted=[("linen supply jobs", 0.10)],
             page="/wholesale", category="bath", inquiry=_HB_INQ_B2B,
             targets=_m(31, 32, 33, 34, 34, 38), orders=_m(4, 4, 5, 5, 5, 5),
             spend=_m(2900, 2950, 3000, 3100, 3200, 3300), cpc=5.40, ctr=0.045),
        dict(id="m_prospect", kind="paid", platform=M, role="prospect", campaign="Prospecting - Broad Home",
             ad_group="Broad 25 to 64 US",
             ads=[("Video - Slow Sunday Morning", 8.5), ("Static - Linen in Five Colors", 1.0),
                  ("Carousel - Best Sellers", 0.5)],
             page="/collections/best-sellers", targets=_m(28, 31, 34, 40, 44, 42), orders=_m(26, 28, 31, 35, 38, 40),
             spend=_m(3400, 3700, 4000, 4400, 4700, 4700), cpm=11.0, ctr=0.012, fb_share=0.55, over_fixed=1.60,
             fatigue={"ad": "Video - Slow Sunday Morning", "start": _dt.date(2026, 9, 1), "half_life": 5.0,
                      "absorb": True}),
        dict(id="m_retarget", kind="paid", platform=M, role="retarget", campaign="Retargeting - Cart Abandoners",
             ad_group="Added to cart 14 days",
             ads=[("Dynamic - Still Thinking It Over", 6), ("Static - 10% Off Your First Order", 4)],
             page="/products/stonewashed-linen-duvet-cover", targets=_m(24, 26, 29, 33, 36, 38),
             orders=_m(40, 43, 47, 52, 56, 60), spend=_m(1800, 1950, 2100, 2250, 2400, 2500),
             cpm=16.0, ctr=0.016, fb_share=0.5),
        dict(id="m_catalog", kind="paid", platform=M, role="prospect", campaign="Catalog - Dynamic Products",
             ad_group="Advantage plus catalog", ads=[("DPA - Bedding", 5), ("DPA - Bath", 3), ("DPA - Kitchen", 2)],
             page_by_ad={"DPA - Bedding": "/products/linen-sheet-set", "DPA - Bath": "/products/waffle-bath-towel-set",
                         "DPA - Kitchen": "/products/ceramic-pour-over-set"},
             category_by_ad={"DPA - Bedding": "bedding", "DPA - Bath": "bath", "DPA - Kitchen": "kitchen"},
             targets=_m(14, 16, 17, 18, 24, 48), orders=_m(20, 21, 22, 24, 28, 55),
             spend=_m(1200, 1300, 1400, 1500, 1600, 3200), cpm=12.0, ctr=0.013, fb_share=0.6),
        dict(id="m_ugc", kind="paid", platform=M, role="prospect", campaign="UGC Reels - Testing",
             ad_group="Broad reels placements",
             ads=[("Reel - Customer Bedroom Tour", 5), ("Reel - Towel Softness Test", 5)],
             page="/collections/best-sellers", targets=_m(6, 7, 8, 9, 12, 12), orders=_m(4, 5, 5, 6, 7, 8),
             spend=_m(500, 600, 700, 800, 900, 1400), cpm=9.0, ctr=0.011, fb_share=0.35),
        dict(id="b_brand", kind="paid", platform=B, role="brand", campaign="MS - Brand Harbor Linen",
             ad_group="Brand terms", ads=[("RSA - Harbor Linen Official Store", 10)],
             keywords=[("harbor linen", 70), ("harbor linen co", 30)], page="/",
             targets=_m(10, 10, 11, 11, 12, 14), orders=_m(7, 7, 7, 8, 8, 8),
             spend=_m(460, 470, 480, 490, 500, 520), cpc=1.25, ctr=0.18),
        dict(id="b_shopping", kind="paid", platform=B, role="shopping", campaign="MS - Shopping All Products",
             ad_group="All products", ads=[("Bedding", 60), ("Bath", 40)],
             page_by_ad={"Bedding": "/products/stonewashed-linen-duvet-cover", "Bath": "/products/waffle-bath-towel-set"},
             category_by_ad={"Bedding": "bedding", "Bath": "bath"},
             targets=_m(14, 15, 15, 16, 16, 18), orders=_m(9, 9, 10, 10, 10, 12),
             spend=_m(950, 980, 1000, 1020, 1050, 1080), cpc=2.80, ctr=0.011),
    ]
    S += _organic_streams(_m(53, 54, 55, 56, 57, 60), _m(6, 6, 6, 6, 7, 7), _m(3, 3, 3, 3, 3, 3),
                          orders=(_m(72, 73, 74, 75, 76, 85), _m(9, 9, 9, 9, 9, 9), _m(3, 3, 3, 3, 3, 3)))
    S += _ai_streams(_m(8, 11, 14, 18, 23, 32), orders=_m(5, 7, 9, 12, 15, 22))
    weekly = [("weekly_newsletter", 1)]
    S += [
        dict(id="soc_instagram", kind="social", role="social", source="instagram", medium="social",
             ref="instagram.com", referrer="https://l.instagram.com/", targets=_m(10, 11, 11, 11, 11, 10),
             orders=_m(7, 7, 8, 8, 8, 8), rate=0.013),
        dict(id="soc_facebook", kind="social", role="social", source="facebook", medium="social",
             ref="facebook.com", referrer="https://m.facebook.com/", targets=_m(4, 4, 4, 4, 5, 4),
             orders=_m(3, 3, 3, 3, 3, 3), rate=0.012),
        dict(id="soc_pinterest", kind="social", role="social", source="pinterest", medium="social",
             ref="pinterest.com", referrer="https://www.pinterest.com/", targets=_m(0, 0, 0, 0, 0, 18),
             orders=_m(0, 0, 0, 0, 0, 14), rate=0.012),
        dict(id="email", kind="email", role="email", source="newsletter", medium="email",
             campaigns={4: weekly, 5: [("weekly_newsletter", 70), ("memorial_day_sale", 30)], 6: weekly,
                        7: [("weekly_newsletter", 65), ("summer_sale", 35)], 8: weekly,
                        9: [("weekly_newsletter", 75), ("labor_day_sale", 25)]},
             alt_campaign="welcome_series", alt_share=0.3, contents=["hero_image", "product_grid", "footer_link"],
             inquiry=[("Order question", 50), ("Newsletter", 20), ("Quote request", 18), ("Wholesale", 12)],
             targets=_m(34, 35, 36, 37, 38, 40), orders=_m(80, 82, 84, 86, 88, 95), rate=0.045),
        dict(id="ref_journal", kind="referral", role="referral", source="coastalhomejournal.org",
             campaign="fall_gift_guide", ref="coastalhomejournal.org",
             referrer="https://coastalhomejournal.org/gift-guide", tagged=0.8,
             targets=_m(9, 9, 9, 9, 10, 11), orders=_m(11, 11, 11, 12, 12, 13), rate=0.035),
        dict(id="ref_innkeepers", kind="referral", role="referral", source="innkeepersnetwork.org",
             campaign="supplier_directory", ref="innkeepersnetwork.org",
             referrer="https://innkeepersnetwork.org/suppliers/linens", tagged=0.6, inquiry=_HB_INQ_B2B,
             pages=[("/wholesale", 80), ("/", 20)],
             targets=_m(6, 6, 7, 7, 7, 8), orders=_m(2, 2, 2, 2, 2, 2), rate=0.04),
        dict(id="ref_blog", kind="referral", role="referral", source="quietroomsblog.net", campaign="",
             ref="quietroomsblog.net", referrer="https://quietroomsblog.net/linen-bedding-review", tagged=0.3,
             targets=_m(5, 5, 5, 5, 5, 5), orders=_m(8, 8, 9, 9, 9, 10), rate=0.03),
        dict(id="direct", kind="direct", role="direct", targets=_m(43, 44, 45, 46, 46, 46),
             orders=_m(62, 64, 66, 68, 70, 75), rate=0.015),
    ]
    return dict(
        name="harbor", domain="harborlinenco.com", form_label="WPForms + WooCommerce",
        industry="Home goods e-commerce",
        brand={"company_name": "Harbor Linen Co.", "logo": {"type": "text", "value": "Harbor Linen Co."},
               "colors": {"primary": "#1F2A5C", "accent": "#D9805F", "ink": "#121833", "muted": "#5B6282",
                          "surface": "#F1F2F8"}},
        forms=[{"id": "1", "title": "Newsletter signup"}, {"id": "2", "title": "Wholesale and quote requests"},
               {"id": "3", "title": "Contact us"}],
        dow={"default": [0.95, 0.9, 0.9, 0.95, 0.95, 1.15, 1.25]},
        hours={"default": [0.35, 0.2, 0.1, 0.08, 0.08, 0.12, 0.25, 0.45, 0.6, 0.7, 0.8, 0.85, 1.0, 0.95, 0.85,
                           0.8, 0.8, 0.9, 1.1, 1.35, 1.55, 1.6, 1.3, 0.75]},
        morning_boost=None,
        holidays={_dt.date(2026, 5, 23): 1.2, _dt.date(2026, 5, 24): 1.25, _dt.date(2026, 5, 25): 1.3,
                  _dt.date(2026, 7, 4): 0.8, _dt.date(2026, 9, 5): 1.25, _dt.date(2026, 9, 6): 1.3,
                  _dt.date(2026, 9, 7): 1.35},
        spend_dow=[0.97, 0.95, 0.95, 0.97, 1.0, 1.07, 1.09],
        session_ratio=0.80,
        streams=S,
        pages={"organic": [("/", 25), ("/collections/linen-bedding", 25), ("/collections/bath", 15),
                           ("/products/stonewashed-linen-duvet-cover", 15), ("/gift-guide", 10), ("/wholesale", 5),
                           ("/contact", 5)],
               "ai": [("/", 25), ("/collections/linen-bedding", 30), ("/products/linen-sheet-set", 25),
                      ("/wholesale", 20)],
               "social": [("/", 30), ("/collections/best-sellers", 40), ("/gift-guide", 30)],
               "email": [("/collections/new-arrivals", 45), ("/collections/best-sellers", 30), ("/contact", 25)],
               "referral": [("/", 40), ("/gift-guide", 35), ("/wholesale", 25)],
               "direct": [("/", 60), ("/contact", 20), ("/collections/linen-bedding", 20)]},
        dead={"organic": [("/blog/how-to-wash-linen", 0.28), ("/blog/linen-vs-cotton-sheets", 0.18), ("/careers", 0.07)],
              "ai": [("/blog/linen-vs-cotton-sheets", 0.15)],
              "social": [("/blog/linen-vs-cotton-sheets", 0.35)],
              "direct": [("/careers", 0.15), ("/blog/how-to-wash-linen", 0.05)],
              "referral": [("/blog/how-to-wash-linen", 0.10)]},
        blog_first_touch=0.012,
        biz=_hb_biz, source_url=_hb_source_url,
        repeat_rate=0.02, area_codes=None,
        over={"Google Ads": 1.22, "Meta Ads": 1.27, "Microsoft Ads": 1.24},
        value_over={"Google Ads": 1.24, "Meta Ads": 1.33, "Microsoft Ads": 1.18},
        entry_start=4980, order_start=46310, deal_start=41875900000,
        strip_rate=0.08, typo_rate=0.03, case_rate=0.05, fbclid_rate=0.40,
        dormant=None,
        deal=dict(pipeline="Wholesale", eligible=("Inquiry Type", ("Quote request", "Wholesale")),
                  p_role={}, p_default=0.45, p_field=None,
                  outcomes=[("won", 46), ("lost", 40), ("open", 14)], outcomes_role={},
                  amount=_hb_amount, create_mean=2.5, close_mean=6.0, unmatched=0.04),
    )


def _finalize(p):
    p["base"] = "https://" + p["domain"]
    p["by_id"] = dict((s["id"], s) for s in p["streams"])
    p["form_titles"] = dict((f["id"], f["title"]) for f in p["forms"])
    p["campaign_keys"] = set(norm_key(s["campaign"]) for s in p["streams"] if s["kind"] == "paid")
    by_role = defaultdict(list)
    for s in p["streams"]:
        by_role[s["role"]].append(s)
    p["by_role"] = dict(by_role)
    tables = {}
    for name, hours in p["hours"].items():
        rows = []
        for wd in range(7):
            w = list(hours)
            if name == "default" and p.get("morning_boost") and wd in (1, 2, 3):
                for h in range(8, 12):
                    w[h] *= p["morning_boost"]
            rows.append(w)
        tables[name] = rows
    p["hour_tables"] = tables
    return p


# ---------------------------------------------------------------------------
# Lead and order engine
# ---------------------------------------------------------------------------
def _fatigue(s, ad, d):
    """Creative fatigue: the ad's response halves every half_life days after start."""
    f = s.get("fatigue")
    if not f or f["ad"] != ad or d < f["start"]:
        return 1.0
    return 0.5 ** ((d - f["start"]).days / float(f["half_life"]))


def _stream_day_mult(s, d):
    if not s.get("fatigue") or s["fatigue"].get("absorb"):
        return 1.0  # absorb: the platform shifts delivery, so the campaign's volume holds
    tot = float(sum(w for _, w in s["ads"]))
    return sum(w * _fatigue(s, a, d) for a, w in s["ads"]) / tot


def _slots(p, months, seed, key):
    """Every (datetime, stream id) for leads (key='targets') or orders (key='orders'), time ordered."""
    out = []
    for s in p["streams"]:
        tg = s.get(key) or {}
        dow = p["dow"].get(s.get("dow") or "default") or p["dow"]["default"]
        table = p["hour_tables"].get(s.get("hours") or "default") or p["hour_tables"]["default"]
        for m in months:
            n = tg.get(m, 0)
            if n <= 0:
                continue
            r = _rng(p["name"], seed, key, s["id"], m)
            days = _month_days(m)
            w = [dow[d.weekday()] * p["holidays"].get(d, 1.0) * r.uniform(0.8, 1.2) * _stream_day_mult(s, d)
                 for d in days]
            alloc = _spread if s.get("fatigue") else _alloc  # keep the fatigue curve readable
            for d, c in zip(days, alloc(r, n, w)):
                hw = table[d.weekday()]
                for _ in range(c):
                    h = r.choices(range(24), weights=hw, k=1)[0]
                    out.append((_dt.datetime(d.year, d.month, d.day, h, r.randint(0, 59), r.randint(0, 59)),
                                s["id"]))
    out.sort()
    return out


def _choose_ad_kw(r, s, d):
    if s["kind"] != "paid":
        return "", ""
    ads = s["ads"]
    ad = r.choices([a for a, _ in ads], weights=[w * _fatigue(s, a, d) for a, w in ads], k=1)[0]
    kws = s.get("keywords")
    return ad, (_pick(r, kws) if kws else "")


def _choose_fatigued(r, s, d, cum):
    """Last-touch ad for a stream with a fatiguing ad. Systematic sampling: the fatiguing ad gets a lead
    each time its running expected share crosses a whole number, so its weekly decline shows without
    small-number noise. Other ads and keywords are still drawn at random."""
    fad = s["fatigue"]["ad"]
    ws = [(a, w * _fatigue(s, a, d)) for a, w in s["ads"]]
    share = dict(ws)[fad] / sum(w for _, w in ws)
    key = (s["id"], d.month)
    before = cum[key]
    cum[key] = before + share
    if math.floor(cum[key] + 0.5) > math.floor(before + 0.5):
        ad = fad
    else:
        others = [(a, w) for a, w in ws if a != fad]
        ad = _pick(r, others) if others else fad
    kws = s.get("keywords")
    return ad, (_pick(r, kws) if kws else "")


def _touch_page(r, p, s, ad, first=False):
    if s["kind"] == "paid":
        return (s.get("page_by_ad") or {}).get(ad) or s.get("page") or "/"
    if first and s["kind"] in ("organic", "ai") and r.random() < p.get("blog_first_touch", 0):
        blogs = [pg for pg, _ in p["dead"].get("organic", []) if pg.startswith("/blog/")]
        if blogs:
            return r.choice(blogs)
    return _pick(r, s.get("pages") or p["pages"].get(s["role"]) or [("/", 1)])


def _landing_url(base, page, t, utm_in_url=True):
    """Landing URL as captured. Organic search and most AI assistants arrive without UTMs in the URL
    (UTM Grabber derives source and medium from the referrer); ChatGPT appends utm_source itself."""
    q = []
    for k in ("source", "medium", "campaign", "content", "term"):
        if t[k] and utm_in_url:
            q.append("utm_%s=%s" % (k, quote_plus(t[k])))
    for k in ("gclid", "wbraid", "fbclid", "msclkid"):
        if t[k]:
            q.append("%s=%s" % (k, t[k]))
    return base + page + ("?" + "&".join(q) if q else "")


def _touch(r, p, s, month, ad, kw, page):
    """One visit's attribution fields, as UTM Grabber would capture them."""
    t = dict(source="", medium="", campaign="", content="", term="", gclid="", wbraid="", fbclid="",
             msclkid="", traffic="Direct", org="", ref="", referrer="", page=page)
    k = s["kind"]
    if k == "paid":
        plat = s["platform"]
        t.update(campaign=norm_key(s["campaign"]), content=norm_key(ad), traffic="Paid")
        if plat == "Google Ads":
            t.update(source="google", medium="cpc", term=kw, ref="google.com", referrer="https://www.google.com/")
            x = r.random()
            if x < 0.88:
                t["gclid"] = _gclid(r)
            elif x < 0.95:
                t["wbraid"] = _wbraid(r)
        elif plat == "Meta Ads":
            src = "facebook" if r.random() < s.get("fb_share", 0.6) else "instagram"
            t.update(source=src, medium="paid_social", ref=src + ".com", fbclid=_fbclid(r),
                     referrer="https://m.facebook.com/" if src == "facebook" else "https://l.instagram.com/")
            # _hygiene() later keeps fbclid on exactly fbclid_rate of Meta leads
        else:  # Microsoft Ads
            t.update(source="bing", medium="cpc", term=kw, ref="bing.com", referrer="https://www.bing.com/")
            if r.random() < 0.9:
                t["msclkid"] = _msclkid(r)
    elif k in ("organic", "ai"):
        t.update(source=s["source"], medium=s["medium"], traffic="Organic", org=s["org"], ref=s["ref"],
                 referrer=s["referrer"])
    elif k == "social":
        t.update(source=s["source"], medium=s["medium"], campaign=s.get("campaign", ""), traffic="Social",
                 ref=s["ref"], referrer=s["referrer"])
        if s["source"] == "facebook" and r.random() < 0.5:
            t["fbclid"] = _fbclid(r)
    elif k == "email":
        camp = s["alt_campaign"] if r.random() < s.get("alt_share", 0) else _pick(r, s["campaigns"][month])
        t.update(source=s["source"], medium=s["medium"], campaign=camp, content=r.choice(s["contents"]),
                 traffic="Referral")
    elif k == "referral":
        t.update(traffic="Referral", ref=s["ref"], referrer=s["referrer"])
        if r.random() < s.get("tagged", 0.7):
            t.update(source=s["source"], medium="referral", campaign=s.get("campaign", ""))
    if s.get("untagged"):
        # links shipped without UTMs: an ad keeps only its click ID, an email looks like a direct visit
        fb = t["fbclid"] if k == "paid" and r.random() < 0.9 else ""
        t.update(source="", medium="", campaign="", content="", term="", fbclid=fb)
        if k == "paid":
            t["traffic"] = "Social"
        else:
            t.update(traffic="Direct", ref="", referrer="")
    in_url = k not in ("organic", "ai") or s.get("source") == "chatgpt.com"
    t["url"] = _landing_url(p["base"], page, t, in_url)
    return t


def _first_stream(r, p, cands, s, month):
    roles = [(role, w) for role, w in cands if p["by_role"].get(role)]
    if not roles:
        return None
    pool = [x for x in p["by_role"][_pick(r, roles)] if x["id"] != s["id"]]
    ws = [max((x.get("targets") or {}).get(month, 0), 0) for x in pool]
    if not pool or sum(ws) <= 0:
        return None
    return r.choices(pool, weights=ws, k=1)[0]


def _handl(last, first, ua):
    return {
        "utm_source (HandL)": last["source"], "utm_medium (HandL)": last["medium"],
        "utm_campaign (HandL)": last["campaign"], "utm_content (HandL)": last["content"],
        "utm_term (HandL)": last["term"], "gclid (HandL)": last["gclid"], "fbclid (HandL)": last["fbclid"],
        "msclkid (HandL)": last["msclkid"], "wbraid (HandL)": last["wbraid"],
        "traffic_source (HandL)": last["traffic"], "organic_source_str (HandL)": last["org"],
        "handl_ref_domain (HandL)": last["ref"], "handl_landing_page (HandL)": last["url"],
        "user_agent (HandL)": ua,
        "utm_source (first touch, HandL)": first["source"], "utm_medium (first touch, HandL)": first["medium"],
        "utm_campaign (first touch, HandL)": first["campaign"],
        "traffic_source (first touch, HandL)": first["traffic"],
        "landing_page (first touch, HandL)": first["url"], "referrer (first touch, HandL)": first["referrer"],
    }


def _recent_person(r, recent, d, days):
    lo = bisect.bisect_left(recent[0], (d - _dt.timedelta(days=days)).toordinal())
    pool = recent[1][lo:]
    return r.choice(pool) if pool else None


def _order_person(r, people, recent, lead_pool, d):
    x = r.random()
    if lead_pool and x < 0.22:
        hi = bisect.bisect_right(lead_pool[0], d.toordinal())
        if hi:
            return lead_pool[1][r.randrange(hi)]  # a subscriber or inquirer who later bought
    elif x < 0.30 and recent[1]:
        return r.choice(recent[1])  # returning customer
    person = people.new()
    recent[0].append(d.toordinal())
    recent[1].append(person)
    return person


def _order_fields(r, s, ad, t, person):
    cat = (s.get("category_by_ad") or {}).get(ad) or s.get("category") or _pick(r, _CATEGORY_MIX)
    picks = [r.choice(_CATALOG[cat])]
    for _ in range(_pick(r, [(0, 50), (1, 30), (2, 15), (3, 5)])):
        picks.append(r.choice(_CATALOG[_pick(r, _CATEGORY_MIX)]))
    qty = {}
    price = {}
    for name, pr in picks:
        qty[name] = qty.get(name, 0) + (2 if r.random() < 0.1 else 1)
        price[name] = pr
    total = sum(price[nm] * q for nm, q in qty.items())
    if s["kind"] == "email" or r.random() < 0.12:
        total *= 0.9  # newsletter discount code
    if total < 75:
        total += 8.95  # shipping under the free-shipping line
    names = [nm if q == 1 else "%s x%d" % (nm, q) for nm, q in qty.items()]
    return {"Order ID": "", "Order Total": "%.2f" % total,
            "Order Status": "refunded" if r.random() < 0.04 else "completed",
            "Billing Email": person["email"], "First Name": person["first"], "Last Name": person["last"],
            "Date Created": t.strftime("%Y-%m-%d %H:%M:%S"), "Products": ", ".join(names)}


def _build_items(p, slots, seed, people, kind, lead_pool=None):
    """Turn slots into entries. Returns items: {e, s, ad, kw, date, same, page} (s = true stream)."""
    r = _rng(p["name"], seed, kind, "build")
    decks = {}  # exact device mix per month (iPhone 45 / Android 20 / Windows 20 / Mac 15), shuffled
    for m, n in sorted(Counter(t.month for t, _ in slots).items()):
        deck = []
        for (dev, _w), k in zip(_DEVICES, _split_exact(n, [w for _, w in _DEVICES])):
            deck += [dev] * k
        _rng(p["name"], seed, kind, "devices", m).shuffle(deck)
        decks[m] = deck
    items = []
    recent = ([], [])  # (ordinals, people) for repeat submitters or returning customers
    fat_cum = defaultdict(float)
    for t, sid in slots:
        s = p["by_id"][sid]
        d = t.date()
        if s.get("fatigue"):
            ad, kw = _choose_fatigued(r, s, d, fat_cum)
        else:
            ad, kw = _choose_ad_kw(r, s, d)
        page = _touch_page(r, p, s, ad)
        last = _touch(r, p, s, t.month, ad, kw, page)
        first, same = last, True
        prob, cands = _TRANSITIONS.get(s["role"], (0.0, []))
        if r.random() < prob:
            fs = _first_stream(r, p, cands, s, t.month)
            if fs is not None:
                fad, fkw = _choose_ad_kw(r, fs, d)
                first = _touch(r, p, fs, t.month, fad, fkw, _touch_page(r, p, fs, fad, True))
                same = False
        ua = _user_agent(r, last, decks[t.month].pop())
        if kind == "lead":
            form, biz, company_dom = p["biz"](r, s)
            person = None
            if company_dom is None and recent[0] and r.random() < p.get("repeat_rate", 0):
                person = _recent_person(r, recent, d, 60)
            if person is None:
                person = people.new(company_dom)
                recent[0].append(d.toordinal())
                recent[1].append(person)
            e = {"Entry ID": "", "Form ID": form, "Form Title": p["form_titles"][form],
                 "Date Created": t.strftime("%Y-%m-%d %H:%M:%S"), "First Name": person["first"],
                 "Last Name": person["last"], "Email": person["email"]}
            if person.get("phone"):
                e["Phone"] = person["phone"]
            e.update(biz)
            e["Source URL"] = p["source_url"](r, p, s, page, form)
        else:
            person = _order_person(r, people, recent, lead_pool, d)
            e = _order_fields(r, s, ad, t, person)
        e.update(_handl(last, first, ua))
        items.append({"e": e, "s": s, "ad": ad, "kw": kw, "date": d, "same": same, "page": page})
    return items


# Hygiene problems planted on purpose -----------------------------------------
_MISSPELL = {"emergency": "emergancy", "invisalign": "invisaline", "implants": "implant", "dental": "dentel",
             "retargeting": "retargetting", "whitening": "whitning", "prospecting": "prospectng",
             "shopping": "shoping", "bedding": "beding", "wholesale": "wholsale", "catalog": "catalogue",
             "brand": "brnad", "general": "genral", "teeth": "teath", "lookalike": "look_alike",
             "promo": "promotion", "offer": "ofer", "storm": "strom", "roof": "rooof", "divorce": "divorse",
             "linen": "linnen", "pmax": "p_max", "search": "serch"}


def _typo(r, camp, valid):
    parts = camp.split("_")
    for _ in range(40):
        q = list(parts)
        idx = [i for i, w in enumerate(q) if w in _MISSPELL]
        if idx and r.random() < 0.8:
            i = r.choice(idx)
            q[i] = _MISSPELL[q[i]]
        else:
            i = r.randrange(len(q))
            if len(q[i]) > 3:
                j = r.randrange(1, len(q[i]) - 1)
                q[i] = q[i][:j] + q[i][j + 1:]
        if len(q) > 2 and r.random() < 0.5:
            q = q[:-1]
        cand = "_".join(q)
        if cand != camp and norm_key(cand) not in valid:
            return cand
    return camp + "_old_v1"


def _swap_param(url, name, old, new):
    a = "%s=%s" % (name, quote_plus(old))
    return url.replace(a, "%s=%s" % (name, quote_plus(new)), 1) if a in url else url


def _strip(r, p, it):
    """A redirect dropped the UTMs: only the gclid survived."""
    e = it["e"]
    if not e["gclid (HandL)"]:
        e["gclid (HandL)"] = _gclid(r)
        e["wbraid (HandL)"] = ""
    for f in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"):
        e[f + " (HandL)"] = ""
    url = p["base"] + it["page"] + "?gclid=" + e["gclid (HandL)"]
    e["handl_landing_page (HandL)"] = url
    if it["same"]:
        for f in ("utm_source", "utm_medium", "utm_campaign"):
            e[f + " (first touch, HandL)"] = ""
        e["landing_page (first touch, HandL)"] = url
    it["stripped"] = True


def _drop_fbclid(it):
    """The landing page or a consent tool lost Meta's click ID."""
    e = it["e"]
    fb = e["fbclid (HandL)"]
    if not fb:
        return
    e["fbclid (HandL)"] = ""
    fields = ["handl_landing_page (HandL)"] + (["landing_page (first touch, HandL)"] if it["same"] else [])
    for f in fields:
        e[f] = e[f].replace("&fbclid=" + fb, "").replace("?fbclid=" + fb, "")


def _hygiene(p, items, seed, tag):
    r = _rng(p["name"], seed, tag, "hygiene")
    by_month = defaultdict(list)
    for it in items:
        by_month[it["date"].month].append(it)
    for m in sorted(by_month):
        group = by_month[m]
        google = [it for it in group if it["s"].get("platform") == "Google Ads"]
        for it in r.sample(google, int(round(p.get("strip_rate", 0.08) * len(google)))):
            _strip(r, p, it)
        meta = [it for it in group if it["s"].get("platform") == "Meta Ads" and not it["s"].get("untagged")]
        keep = set(id(it) for it in r.sample(meta, int(round(p.get("fbclid_rate", 0.40) * len(meta)))))
        for it in meta:
            if id(it) not in keep:
                _drop_fbclid(it)
        tagged = [it for it in group if it["s"]["kind"] == "paid" and it["e"]["utm_campaign (HandL)"]]
        n_typo = min(len(tagged), int(round(p.get("typo_rate", 0.03) * len(group))))
        for it in r.sample(tagged, n_typo):
            e = it["e"]
            old = e["utm_campaign (HandL)"]
            bad = _typo(r, old, p["campaign_keys"])
            e["utm_campaign (HandL)"] = bad
            e["handl_landing_page (HandL)"] = _swap_param(e["handl_landing_page (HandL)"], "utm_campaign", old, bad)
            if it["same"]:
                e["utm_campaign (first touch, HandL)"] = bad
                e["landing_page (first touch, HandL)"] = e["handl_landing_page (HandL)"]
            it["typo"] = True
        cands = [it for it in group if it["e"]["utm_source (HandL)"].isalpha()]
        n_case = min(len(cands), int(round(p.get("case_rate", 0.05) * len(group))))
        for it in r.sample(cands, n_case):
            e = it["e"]
            old = e["utm_source (HandL)"]
            new = old.upper() if r.random() < 0.2 else old.capitalize()
            e["utm_source (HandL)"] = new
            e["handl_landing_page (HandL)"] = _swap_param(e["handl_landing_page (HandL)"], "utm_source", old, new)
            med = e["utm_medium (HandL)"]
            if med in ("cpc", "email", "social") and r.random() < 0.2:
                newm = "CPC" if med == "cpc" else med.capitalize()
                e["utm_medium (HandL)"] = newm
                e["handl_landing_page (HandL)"] = _swap_param(e["handl_landing_page (HandL)"], "utm_medium", med, newm)
            if it["same"]:
                e["utm_source (first touch, HandL)"] = e["utm_source (HandL)"]
                e["utm_medium (first touch, HandL)"] = e["utm_medium (HandL)"]
                e["landing_page (first touch, HandL)"] = e["handl_landing_page (HandL)"]
            it["recased"] = True


def _number(items, field, start, r):
    n = start
    for it in items:
        it["e"][field] = str(n)
        n += 1 + (1 if r.random() < 0.04 else 0)  # gaps: deleted spam entries


def _dormant(p, items, seed):
    cfg = p.get("dormant")
    if not cfg:
        return
    r = _rng(p["name"], seed, "dormant")
    for m, n in sorted(cfg["counts"].items()):
        pool = [it for it in items if it["date"].month == m and it["e"]["Form ID"] == "1"
                and it["s"]["role"] in ("organic", "direct", "social", "referral")]
        for it in r.sample(pool, min(n, len(pool))):
            e = it["e"]
            e["Form ID"] = cfg["form"]
            e["Form Title"] = p["form_titles"][cfg["form"]]
            if cfg.get("service"):
                e["Service"] = cfg["service"]
            e["Source URL"] = p["base"] + "/smile-giveaway"


# ---------------------------------------------------------------------------
# Ad platform rows (connectors AdRow shape)
# ---------------------------------------------------------------------------
def _cells(s):
    """[(ad, keyword, spend share, can produce leads)] for one paid stream."""
    ads = s["ads"]
    aw = float(sum(w for _, w in ads))
    kws = s.get("keywords") or []
    wasted = s.get("wasted") or []
    out = []
    if kws or wasted:
        ws = sum(sh for _, sh in wasted)
        kt = float(sum(w for _, w in kws)) or 1.0
        for a, w in ads:
            for k, kw_w in kws:
                out.append((a, k, (1 - ws) * (w / aw) * (kw_w / kt), True))
            for k, sh in wasted:
                out.append((a, k, sh * (w / aw), False))
    else:
        for a, w in ads:
            out.append((a, "", w / aw, True))
    return out


def _calibrate(streams, base, ratio, r, as_int, fixed_base=None):
    """Per-stream platform totals: the platform as a whole reports `ratio` x what UTM Grabber saw,
    streams with over_fixed report that multiple of fixed_base (their joinable leads), the rest
    share the remainder."""
    target = sum(base[s["id"]] for s in streams) * ratio
    fb = fixed_base if fixed_base is not None else base
    fixed = dict((s["id"], fb[s["id"]] * s["over_fixed"]) for s in streams if s.get("over_fixed"))
    rest = [s for s in streams if s["id"] not in fixed]
    weights = [base[s["id"]] * r.uniform(0.94, 1.06) + 0.01 for s in rest]
    if as_int:
        fixed = dict((k, int(round(v))) for k, v in fixed.items())
        parts = _split_exact(int(round(target)) - sum(fixed.values()), weights)
    else:
        left = max(0.0, target - sum(fixed.values()))
        wsum = sum(weights) or 1.0
        parts = [left * w / wsum for w in weights]
    out = dict(fixed)
    out.update(dict((s["id"], v) for s, v in zip(rest, parts)))
    return out


def _cap_to_clicks(rows):
    """Search platforms credit conversions to clicks: move any excess to rows with headroom."""
    excess = 0.0
    for x in rows:
        if x["conversions"] > x["clicks"]:
            excess += x["conversions"] - x["clicks"]
            x["conversions"] = float(x["clicks"])
    for x in sorted((x for x in rows if x["_ok"]), key=lambda x: x["conversions"] - x["clicks"]):
        if excess <= 0:
            break
        add = min(excess, x["clicks"] - x["conversions"])
        if add > 0:
            x["conversions"] += add
            excess -= add


def _ad_rows(p, lead_items, order_items, month, seed):
    """Daily AdRows per campaign x ad (x keyword for search). Also returns the paid clicks per cell."""
    lead_cell, lead_stream, lead_joinable = Counter(), Counter(), Counter()
    for it in lead_items:
        if it["s"]["kind"] == "paid":
            lead_cell[(it["s"]["id"], it["date"], it["ad"], it["kw"])] += 1
            lead_stream[it["s"]["id"]] += 1
            if not it.get("typo") and not it.get("stripped"):
                lead_joinable[it["s"]["id"]] += 1
    rev_cell, rev_stream = defaultdict(float), defaultdict(float)
    for it in order_items or []:
        if it["s"]["kind"] == "paid":
            v = float(it["e"]["Order Total"])
            rev_cell[(it["s"]["id"], it["date"], it["ad"], it["kw"])] += v
            rev_stream[it["s"]["id"]] += v
    by_stream = {}
    for s in p["streams"]:
        if s["kind"] != "paid" or not (s.get("spend") or {}).get(month):
            continue
        r = _rng(p["name"], seed, "adrows", s["id"], month)
        raw = []
        for d in _month_days(month):
            dw = p["spend_dow"][d.weekday()] * r.uniform(0.9, 1.1)
            for ad, kw, sh, ok in _cells(s):
                raw.append((d, ad, kw, ok, dw * sh * r.uniform(0.8, 1.2)))
        scale = s["spend"][month] / sum(x[4] for x in raw)
        rows = []
        for d, ad, kw, ok, sp in raw:
            sp = round(sp * scale, 2)
            if sp < 0.05:
                continue
            if s["platform"] == "Meta Ads":
                imps = int(sp / s["cpm"] * 1000 * r.uniform(0.9, 1.1))
                ctr = s["ctr"] * (0.35 + 0.65 * _fatigue(s, ad, d)) * r.uniform(0.85, 1.15)
                clicks = int(round(imps * ctr))
            else:
                cpc = s["cpc"] * (1.0 if ok else 0.7) * r.uniform(0.85, 1.15)
                clicks = max(1, int(round(sp / cpc)))
                imps = max(clicks, int(round(clicks / (s["ctr"] * r.uniform(0.8, 1.2)))))
            nl = lead_cell.get((s["id"], d, ad, kw), 0)
            if clicks < nl:
                clicks = nl + r.randint(0, 2)
                imps = max(imps, clicks * 12)
            rows.append({"platform": s["platform"], "campaign": s["campaign"], "ad_group": s.get("ad_group", ""),
                         "ad": ad, "keyword": kw, "date": d.isoformat(), "spend": sp, "impressions": imps,
                         "clicks": clicks, "conversions": 0.0, "conversion_value": 0.0,
                         "_k": (s["id"], d, ad, kw), "_ok": ok})
        by_stream[s["id"]] = rows
    # conversions: platforms over-report the leads UTM Grabber attributes to them
    for plat, ratio in p["over"].items():
        streams = [s for s in p["streams"] if s.get("platform") == plat and s["id"] in by_stream]
        r = _rng(p["name"], seed, "conv", plat, month)
        for sid, n in _calibrate(streams, lead_stream, ratio, r, True, lead_joinable).items():
            rows = by_stream[sid]
            tot_clicks = float(sum(x["clicks"] for x in rows)) or 1.0
            nl = max(lead_stream[sid], 1)
            w = [(lead_cell.get(x["_k"], 0) + 0.3 * nl * x["clicks"] / tot_clicks) if x["_ok"] else 0.0 for x in rows]
            for x, c in zip(rows, _alloc(r, n, w)):
                x["conversions"] = float(c)
            if plat != "Meta Ads":  # Meta's view-through conversions may exceed link clicks
                _cap_to_clicks(rows)
    # conversion_value (stores only): platform-reported purchase revenue, above WooCommerce revenue
    for plat, ratio in (p.get("value_over") or {}).items():
        streams = [s for s in p["streams"] if s.get("platform") == plat and s["id"] in by_stream]
        r = _rng(p["name"], seed, "value", plat, month)
        for sid, total in _calibrate(streams, rev_stream, ratio, r, False).items():
            rows = by_stream[sid]
            tot_clicks = float(sum(x["clicks"] for x in rows)) or 1.0
            base = rev_stream[sid] or 1.0
            w = [(rev_cell.get(x["_k"], 0.0) + 0.15 * base * x["clicks"] / tot_clicks) if x["_ok"] else 0.0
                 for x in rows]
            wsum = sum(w) or 1.0
            for x, wi in zip(rows, w):
                x["conversion_value"] = round(total * wi / wsum, 2)
    out, clicks = [], []
    for s in p["streams"]:
        for x in by_stream.get(s["id"], []):
            clicks.append((x.pop("_k"), x["clicks"]))
            x.pop("_ok")
            out.append(x)
    out.sort(key=lambda x: (x["date"], x["platform"], x["campaign"], x["ad"], x["keyword"]))
    return out, clicks


# ---------------------------------------------------------------------------
# GA4 visit rows (connectors VisitRow shape)
# ---------------------------------------------------------------------------
_ENGAGE = {"paid_search": 0.68, "paid_social": 0.47, "organic": 0.62, "ai": 0.71, "social": 0.5, "email": 0.66,
           "referral": 0.64, "direct": 0.58}
_GA4_CAMPAIGN = {"organic": "(organic)", "ai": "(referral)", "referral": "(referral)", "social": "(referral)",
                 "direct": "(direct)"}


def _stream_key(s):
    med = s.get("medium") or ("referral" if s["kind"] == "referral" else "")
    return (s["source"].lower(), med.lower() or "(not set)")


def _visit_rows(p, lead_items, clicks, month, seed):
    r = _rng(p["name"], seed, "visits", month)
    days = _month_days(month)
    cells = defaultdict(int)  # (date, source, medium, campaign, landing page) -> sessions
    kinds = {}
    # 1) paid sessions come from ad clicks (consent banners and quick bounces lose some)
    for (sid, d, ad, kw), c in clicks:
        if c <= 0:
            continue
        s = p["by_id"][sid]
        page = (s.get("page_by_ad") or {}).get(ad) or s.get("page") or "/"
        sess = int(round(c * p["session_ratio"] * r.uniform(0.92, 1.08)))
        camp = norm_key(s["campaign"])
        if s["platform"] == "Meta Ads":
            fb = int(round(sess * s.get("fb_share", 0.6) * r.uniform(0.9, 1.1)))
            parts, med, cls = [("facebook", fb), ("instagram", sess - fb)], "paid_social", "paid_social"
        else:
            parts, med, cls = [("google" if s["platform"] == "Google Ads" else "bing", sess)], "cpc", "paid_search"
        for src, n in parts:
            if n > 0:
                cells[(d, src, med, camp, page)] += n
                kinds[(src, med)] = cls
    # 2) every other channel: sessions = leads / a realistic lead rate for that channel
    leads_by_key = Counter(_join_key(it["e"]) for it in lead_items)
    by_key = {}
    for s in p["streams"]:
        if s["kind"] in ("organic", "ai", "social", "email", "referral"):
            by_key[_stream_key(s)] = s
    direct = p["by_role"]["direct"][0]
    dw = [p["dow"]["default"][d.weekday()] ** 0.6 * p["holidays"].get(d, 1.0) ** 0.5 for d in days]
    for key in sorted(leads_by_key):
        if key in kinds:
            continue
        s = by_key.get(key, direct)
        total = int(round(leads_by_key[key] / (s.get("rate", 0.015) * r.uniform(0.92, 1.08))))
        conv = s.get("pages") or p["pages"].get(s["role"]) or [("/", 1)]
        dead = list(p["dead"].get(s["role"], []))
        cw = float(sum(w for _, w in conv))
        dead_share = sum(sh for _, sh in dead)
        page_w = [(pg, (1 - dead_share) * w / cw) for pg, w in conv] + dead
        camp = s["campaigns"][month][0][0] if s["kind"] == "email" else _GA4_CAMPAIGN.get(s["kind"], "(not set)")
        if key[1] == "(not set)":
            camp = "(not set)"
        for d, dn in zip(days, _split_exact(total, [w * r.uniform(0.85, 1.15) for w in dw])):
            for (pg, _w), pn in zip(page_w, _alloc(r, dn, [w for _, w in page_w])):
                if pn > 0:
                    cells[(d, key[0], key[1], camp, pg)] += pn
        kinds[key] = s["kind"]
    # 3) GA4 key events: form submits GA4 saw (consent mode loses about 12%)
    index = {}
    for k in cells:
        index.setdefault((k[0], k[1], k[2], k[4]), k)
    ke = Counter()
    for it in lead_items:
        src, med = _join_key(it["e"])
        k = index.get((it["date"], src, med, _path(it["e"]["handl_landing_page (HandL)"])))
        if k is not None and r.random() < 0.88:
            ke[k] += 1
    rows = []
    for k in sorted(cells):
        n = cells[k]
        d, src, med, camp, pg = k
        eng = _ENGAGE.get(kinds.get((src, med)), 0.6)
        if pg.startswith("/blog/"):
            eng = 0.52
        elif pg == "/careers":
            eng = 0.74
        rows.append({"source": src, "medium": med, "campaign": camp, "landing_page": pg, "date": d.isoformat(),
                     "sessions": n, "engaged_sessions": min(n, int(round(n * eng * r.uniform(0.92, 1.08)))),
                     "users": max(1, int(round(n * r.uniform(0.82, 0.93)))),
                     "key_events": float(min(n, ke.get(k, 0)))})
    return rows


# ---------------------------------------------------------------------------
# CRM deals (connectors DealRow shape)
# ---------------------------------------------------------------------------
def _deal(r, cfg, email, e, lead_date, role, state):
    created = lead_date + _dt.timedelta(days=min(10, int(r.expovariate(1.0 / cfg["create_mean"]))))
    if created > ASOF:
        return None  # not in the CRM yet on the as-of date
    stage = _pick(r, cfg["outcomes_role"].get(role, cfg["outcomes"]))
    closed = None
    if stage != "open":
        closed = created + _dt.timedelta(days=min(30, 3 + int(r.expovariate(1.0 / cfg["close_mean"]))))
        if closed > ASOF:
            stage, closed = "open", None  # would close after the as-of date: still open today
    state["next"] += r.randint(3, 41)
    return {"deal_id": str(state["next"]), "email": email, "stage": stage, "amount": cfg["amount"](r, e),
            "created": created.isoformat(), "closed": closed.isoformat() if closed else None,
            "pipeline": cfg["pipeline"]}


def _deal_rows(p, lead_items, month, seed, taken, people, state):
    cfg = p["deal"]
    r = _rng(p["name"], seed, "deals", month)
    rows = []
    for it in lead_items:
        e = it["e"]
        email = e["Email"].strip().lower()
        if email in taken:
            continue
        if cfg.get("eligible") and e.get(cfg["eligible"][0]) not in cfg["eligible"][1]:
            continue
        taken.add(email)  # one chance per person: the CRM deal follows their first eligible lead
        role = it["s"]["role"]
        pr = cfg["p_role"].get(role, cfg["p_default"])
        if cfg.get("p_field"):
            pr *= cfg["p_field"][1].get(e.get(cfg["p_field"][0]), 1.0)
        if r.random() >= pr:
            continue
        row = _deal(r, cfg, email, e, it["date"], role, state)
        if row:
            rows.append(row)
    # phone and walk-in bookings: real deals with no form lead behind them
    days = [d for d in _month_days(month) if d <= ASOF]
    for _ in range(int(round(cfg.get("unmatched", 0) * len(rows)))):
        person = people.new()
        fake = {"Service": _pick(r, _NW_SERVICES)}  # only northwind's amount function reads it
        row = _deal(r, cfg, person["email"], fake, r.choice(days), None, state)
        if row:
            rows.append(row)
    rows.sort(key=lambda x: (x["created"], x["deal_id"]))
    return rows


# ---------------------------------------------------------------------------
# Agency rollup clients (smaller lead sets, four different trends)
# ---------------------------------------------------------------------------
_CLIENT_SPECS = [
    dict(key="copperleaf", name="Copperleaf Roofing", domain="copperleafroofing.com", entry_start=3120,
         colors={"primary": "#B4532A", "accent": "#2F6F73", "ink": "#1E1A17", "muted": "#6B625C", "surface": "#F7F1EC"},
         field=("Service", [("Roof repair", 40), ("Roof replacement", 30), ("Free inspection", 20), ("Gutters", 10)]),
         form="Free roof inspection", offer="Free Roof Inspection", ref="cedarvalehomeowners.org", area=["541", "458"],
         campaigns=[("Roof Repair - Exact", ["roof repair near me", "roof leak repair"], {8: 70, 9: 92}),
                    ("Roof Replacement - Phrase", ["roof replacement cost", "new roof estimate"], {8: 48, 9: 66}),
                    ("Storm Damage - Exact", ["storm damage roof repair", "hail damage roof"], {8: 0, 9: 88})],
         meta=("Homeowners 35 to 65 Local", {8: 36, 9: 50}),
         other={"organic": {8: 40, 9: 44}, "ai": {8: 4, 9: 8}, "referral": {8: 10, 9: 12}, "email": {8: 8, 9: 8},
                "direct": {8: 24, 9: 30}},
         strip=0.06),
    dict(key="saltmarsh", name="Saltmarsh Family Law", domain="saltmarshfamilylaw.com", entry_start=870,
         colors={"primary": "#2E4A62", "accent": "#C9A227", "ink": "#14202B", "muted": "#5E6B76", "surface": "#F2F4F6"},
         field=("Matter Type", [("Divorce", 45), ("Child custody", 30), ("Mediation", 15), ("Prenuptial agreement", 10)]),
         form="Request a consultation", offer="Confidential Consultation", ref="tidewaterbarassociation.org",
         area=["843", "854"],
         campaigns=[("Divorce Lawyer - Exact", ["divorce lawyer near me", "divorce attorney"], {8: 52, 9: 30}),
                    ("Child Custody - Phrase", ["child custody lawyer", "custody attorney"], {8: 28, 9: 20})],
         meta=("Parents 30 to 55 Local", {8: 12, 9: 8}),
         other={"organic": {8: 30, 9: 25}, "ai": {8: 3, 9: 4}, "referral": {8: 10, 9: 8}, "email": {8: 3, 9: 3},
                "direct": {8: 12, 9: 10}},
         strip=0.06),
    dict(key="bluebird", name="Bluebird Pediatric Therapy", domain="bluebirdpeds.com", entry_start=2210,
         colors={"primary": "#3B82C4", "accent": "#F4B942", "ink": "#13263A", "muted": "#5C6F82", "surface": "#EEF5FB"},
         field=("Therapy Type", [("Speech", 40), ("Occupational", 30), ("Physical", 20), ("Feeding", 10)]),
         form="New family intake", offer="Free Screening", ref="lakeshoreparentsnetwork.org", area=["616", "269"],
         campaigns=[("Speech Therapy - Phrase", ["speech therapist for kids", "pediatric speech therapy"], {8: 48, 9: 50}),
                    ("Occupational Therapy - Phrase", ["pediatric occupational therapy", "ot for kids near me"],
                     {8: 30, 9: 31})],
         meta=("Parents of toddlers Local", {8: 40, 9: 42}),
         other={"organic": {8: 38, 9: 40}, "ai": {8: 5, 9: 6}, "referral": {8: 20, 9: 21}, "email": {8: 8, 9: 8},
                "direct": {8: 16, 9: 16}},
         strip=0.5, meta_untagged=True, email_untagged=True, ref_tagged=0.0),
    dict(key="fernhill", name="Fernhill Fitness Studio", domain="fernhillfitness.com", entry_start=15400,
         colors={"primary": "#2F7D4F", "accent": "#E4572E", "ink": "#14261B", "muted": "#5F6E64", "surface": "#EFF6F1"},
         field=("Interest", [("Free class", 50), ("Membership", 30), ("Personal training", 20)]),
         form="Claim a free class", offer="Free Class Pass", ref="riverbendrunclub.org", area=["720", "303"],
         campaigns=[("Gym Near Me - Exact", ["gym near me", "fitness studio near me"], {8: 120, 9: 122}),
                    ("Personal Training - Phrase", ["personal trainer near me", "small group training"], {8: 60, 9: 62})],
         meta=("Free Class Pass Local", {8: 140, 9: 142}),
         other={"organic": {8: 80, 9: 82}, "ai": {8: 10, 9: 12}, "referral": {8: 30, 9: 30}, "email": {8: 40, 9: 40},
                "direct": {8: 50, 9: 50}, "social": {8: 30, 9: 32}},
         strip=0.06),
]
_CLIENT_PAGES = {"organic": [("/", 40), ("/services", 35), ("/contact", 25)], "ai": [("/", 50), ("/services", 50)],
                 "social": [("/", 60), ("/offer", 40)], "email": [("/offer", 60), ("/contact", 40)],
                 "referral": [("/", 70), ("/contact", 30)], "direct": [("/", 70), ("/contact", 30)]}


def _client_profile(spec):
    S = []
    for i, (camp, kws, tg) in enumerate(spec["campaigns"]):
        topic = camp.split(" - ")[0]
        S.append(dict(id="g%d" % i, kind="paid", platform="Google Ads", role="search", campaign=camp,
                      ad_group=topic, ads=[("RSA - %s" % topic, 6), ("RSA - Call Today", 4)],
                      keywords=[(k, 1) for k in kws], page="/" + norm_key(topic).replace("_", "-"), targets=tg))
    mname, mtg = spec["meta"]
    S.append(dict(id="m0", kind="paid", platform="Meta Ads", role="prospect", campaign=mname, ad_group=mname,
                  ads=[("Static - %s" % spec["offer"], 6), ("Reel - Meet the Team", 4)], page="/offer", targets=mtg,
                  fb_share=0.6, untagged=spec.get("meta_untagged", False)))
    o = spec["other"]
    S.append(dict(id="org_google", kind="organic", role="organic", source="google", medium="organic", org="Google",
                  ref="google.com", referrer="https://www.google.com/", targets=o["organic"], rate=0.02))
    S.append(dict(id="ai_chatgpt", kind="ai", role="ai", source="chatgpt.com", medium="", org="OpenAI/ChatGPT",
                  ref="chatgpt.com", referrer="https://chatgpt.com/", targets=o["ai"], rate=0.025))
    S.append(dict(id="ref", kind="referral", role="referral", source=spec["ref"], campaign="partner_listing",
                  ref=spec["ref"], referrer="https://%s/" % spec["ref"], tagged=spec.get("ref_tagged", 0.7),
                  targets=o["referral"], rate=0.035))
    S.append(dict(id="email", kind="email", role="email", source="newsletter", medium="email",
                  campaigns={8: [("monthly_newsletter", 1)], 9: [("monthly_newsletter", 1)]},
                  alt_campaign="welcome_series",
                  alt_share=0.3, contents=["cta_button", "header_link"], targets=o["email"], rate=0.045,
                  untagged=spec.get("email_untagged", False)))
    if o.get("social"):
        S.append(dict(id="soc_instagram", kind="social", role="social", source="instagram", medium="social",
                      ref="instagram.com", referrer="https://l.instagram.com/", targets=o["social"], rate=0.012))
    S.append(dict(id="direct", kind="direct", role="direct", targets=o["direct"], rate=0.015))
    fname, options = spec["field"]
    return _finalize(dict(
        name=spec["key"], domain=spec["domain"], streams=S, forms=[{"id": "1", "title": spec["form"]}],
        dow={"default": [1.0, 1.15, 1.15, 1.1, 0.95, 0.55, 0.45]},
        hours={"default": [0.05, 0.03, 0.02, 0.02, 0.03, 0.1, 0.35, 0.9, 1.5, 1.9, 2.0, 1.8, 1.6, 1.5, 1.4, 1.3,
                           1.2, 1.1, 1.05, 1.1, 1.0, 0.8, 0.45, 0.15]},
        morning_boost=1.15, holidays={_dt.date(2026, 9, 7): 0.5}, pages=_CLIENT_PAGES, dead={},
        biz=lambda r, s: ("1", {fname: _pick(r, options)}, None),
        source_url=lambda r, p, s, page, form: p["base"] + page,
        repeat_rate=0.02, strip_rate=spec["strip"], typo_rate=0.03, case_rate=0.05))


def _client(spec, seed):
    p = _client_profile(spec)
    people = _People(_rng(p["name"], seed, "people"), spec["area"])
    items = _build_items(p, _slots(p, (PRIOR_MONTH, CURRENT_MONTH), seed, "targets"), seed, people, "lead")
    _hygiene(p, items, seed, "leads")
    _number(items, "Entry ID", spec["entry_start"], _rng(p["name"], seed, "entry-ids"))
    return {"name": spec["name"],
            "brand": {"company_name": spec["name"], "logo": {"type": "text", "value": spec["name"]},
                      "colors": dict(spec["colors"])},
            "domain": spec["domain"],
            "leads": [it["e"] for it in items if it["date"].month == CURRENT_MONTH],
            "leads_prior": [it["e"] for it in items if it["date"].month == PRIOR_MONTH]}


def _clients(seed):
    if seed not in _CLIENT_CACHE:
        _CLIENT_CACHE[seed] = [_client(spec, seed) for spec in _CLIENT_SPECS]
    return _CLIENT_CACHE[seed]


# ---------------------------------------------------------------------------
# Assembly + public API
# ---------------------------------------------------------------------------
DATASETS = {
    "northwind": "Northwind Dental: local dental clinic. UTM Grabber leads (Gravity Forms), Google Ads, Meta Ads, "
                 "GA4 visits and HubSpot patient deals.",
    "harbor": "Harbor Linen Co.: home goods store. UTM Grabber leads (WPForms), WooCommerce orders, Google Ads "
              "(Search, Shopping, Performance Max), Meta Ads, Microsoft Ads, GA4 visits and HubSpot wholesale deals.",
}

_COMMON_NOTES = [
    "Every business, person, email, phone number, company and click ID here is invented. Emails use reserved "
    "example domains so no address can reach a real inbox; phone numbers use the 555 exchange.",
    "Platform names (Google Ads, Meta Ads, Microsoft Ads, GA4, HubSpot, WooCommerce, ChatGPT and the other AI "
    "assistants) appear only as data sources.",
    "Ad platform conversions are calibrated to run 18 to 32 percent above the leads UTM Grabber attributes to each "
    "platform, with one Meta prospecting campaign about 60 percent over, to show platform over-reporting.",
    "Planted hygiene problems: about 8 percent of Google Ads leads lost their UTMs to a redirect (gclid only), about "
    "5 percent of leads carry inconsistent source casing, about 3 percent carry a mistyped campaign tag, and "
    "fbclid survives on only about 40 percent of Meta leads.",
    "GA4 sessions come from ad clicks for paid traffic (about 80 to 86 percent of clicks become sessions) and from "
    "channel lead rates for everything else, so every source and medium has more sessions than leads.",
    "CRM stages reflect what was known on Oct 5, 2026: deals that would close later are still open. About 4 "
    "percent of deals are phone or walk-in bookings with no matching form lead.",
    "History (leads_history, ad_rows_history, deal_rows_history, orders_history) runs April 1 to September 30, "
    "2026, so Q2 and Q3 compare: Q2 volume sits about 12 to 14 percent below Q3, Meta's share of leads grows in "
    "Q3, organic search grows slowly and AI assistants grow fastest. GA4 visit rows cover August and September.",
]
_NOTES = {
    "northwind": [
        "Stories to find: Invisalign Consult Promo doubled after its budget doubled; Whitening Offer stalled to "
        "under half because its $99 static ad fatigued (leads fall every week while spend holds); TikTok appears "
        "as a new source in September; AI assistants grow every month.",
        "Wasted spend: the keywords free dental implants, diy teeth whitening kit and dental hygienist jobs spend "
        "real money and never produce a lead. Blog posts and the careers page get heavy traffic and almost no leads.",
        "Meta Prospecting - Lookalike New Patients over-reports conversions by about 60 percent.",
    ],
    "harbor": [
        "Ad platforms count form conversions (newsletter, quote, contact) as conversions so they compare to UTM "
        "Grabber leads. conversion_value is the platform-reported purchase revenue, which runs above the "
        "WooCommerce revenue UTM Grabber attributes to each platform.",
        "Stories to find: Catalog - Dynamic Products doubled; Search - Linen Bedding stalled to under half on the "
        "same budget; Pinterest appears as a new source in September; the Video - Slow Sunday Morning ad fatigues "
        "through September.",
        "Wasted spend: linen fabric by the yard, how to wash linen sheets and linen supply jobs spend money with no "
        "leads. Only quote and wholesale requests become HubSpot deals (B2B pipeline).",
    ],
}


def _build_dataset(name, seed, clients_seed):
    p = _finalize({"northwind": _northwind, "harbor": _harbor}[name]())
    people = _People(_rng(name, seed, "people"), p.get("area_codes"))
    lead_items = _build_items(p, _slots(p, HISTORY_MONTHS, seed, "targets"), seed, people, "lead")
    _hygiene(p, lead_items, seed, "leads")
    _dormant(p, lead_items, seed)
    _number(lead_items, "Entry ID", p["entry_start"], _rng(name, seed, "entry-ids"))
    leads_m = defaultdict(list)
    for it in lead_items:
        leads_m[it["date"].month].append(it)
    order_items = []
    if any(s.get("orders") for s in p["streams"]):
        pool = ([it["date"].toordinal() for it in lead_items],
                [{"first": it["e"]["First Name"], "last": it["e"]["Last Name"], "email": it["e"]["Email"]}
                 for it in lead_items])
        order_items = _build_items(p, _slots(p, HISTORY_MONTHS, seed, "orders"), seed, people, "order", pool)
        _hygiene(p, order_items, seed, "orders")
        _number(order_items, "Order ID", p["order_start"], _rng(name, seed, "order-ids"))
    orders_m = defaultdict(list)
    for it in order_items:
        orders_m[it["date"].month].append(it)
    ads, visits, deals = {}, {}, {}
    for m in HISTORY_MONTHS:
        ads[m], clicks = _ad_rows(p, leads_m[m], orders_m[m], m, seed)
        if m in (PRIOR_MONTH, CURRENT_MONTH):
            visits[m] = _visit_rows(p, leads_m[m], clicks, m, seed)
    taken, state = set(), {"next": p["deal_start"]}
    for m in HISTORY_MONTHS:
        deals[m] = _deal_rows(p, leads_m[m], m, seed, taken, people, state)
    cur, pri = CURRENT_MONTH, PRIOR_MONTH
    return {
        "brand": p["brand"], "domain": p["domain"], "form_label": p["form_label"], "industry": p["industry"],
        "period": {"start": _dt.date(YEAR, 9, 1), "end": _dt.date(YEAR, 9, 30), "label": "September 2026",
                   "compare_label": "August", "prior_start": _dt.date(YEAR, 8, 1),
                   "prior_end": _dt.date(YEAR, 8, 31)},
        "leads": [it["e"] for it in leads_m[cur]],
        "leads_prior": [it["e"] for it in leads_m[pri]],
        "leads_history": [it["e"] for it in lead_items],
        "orders": [it["e"] for it in orders_m[cur]],
        "orders_prior": [it["e"] for it in orders_m[pri]],
        "orders_history": [it["e"] for it in order_items],
        "ad_rows": ads[cur], "ad_rows_prior": ads[pri],
        "ad_rows_history": [x for m in HISTORY_MONTHS for x in ads[m]],
        "visit_rows": visits[cur], "visit_rows_prior": visits[pri],
        "deal_rows": deals[cur], "deal_rows_prior": deals[pri],
        "deal_rows_history": [x for m in HISTORY_MONTHS for x in deals[m]],
        "forms": [dict(f) for f in p["forms"]],
        "clients": _clients(clients_seed),
        "notes": list(_COMMON_NOTES) + list(_NOTES[name]),
    }


def list_datasets():
    """Names accepted by get_dataset(). Descriptions live in DATASETS."""
    return list(DATASETS)


def get_dataset(name, seed=None):
    """Build (once) and return the named demo dataset. Same name + seed -> identical data.

    Keys: brand, domain, form_label, industry, period, leads, leads_prior, leads_history, orders,
    orders_prior, orders_history, ad_rows, ad_rows_prior, ad_rows_history, visit_rows, visit_rows_prior,
    deal_rows, deal_rows_prior, deal_rows_history, forms, clients, notes.

    Current period = September 2026, prior = August 2026. The *_history lists cover April 1 to
    September 30 (Q2 and Q3) and contain the very same objects as the current and prior lists.
    The dict is cached and shared: treat it as read-only."""
    key = str(name or "").strip().lower()
    if key not in DATASETS:
        raise KeyError("Unknown demo dataset %r. Available: %s" % (name, ", ".join(list_datasets())))
    s = DEFAULT_SEEDS[key] if seed is None else seed
    ck = (key, s)
    if ck not in _CACHE:
        _CACHE[ck] = _build_dataset(key, s, CLIENTS_SEED if seed is None else seed)
    return _CACHE[ck]


if __name__ == "__main__":
    import time
    for nm in list_datasets():
        t0 = time.time()
        ds = get_dataset(nm)
        print("%s built in %.2fs" % (nm, time.time() - t0))
        for k, v in ds.items():
            if isinstance(v, list):
                print("  %-18s %d" % (k, len(v)))
