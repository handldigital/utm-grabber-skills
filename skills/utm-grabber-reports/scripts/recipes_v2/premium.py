"""
Premium v2 recipes: six reports built on what UTM Grabber Premium captures
beyond the free plugin (first-touch fields, AI-assistant referrals,
WooCommerce orders, devices), plus optional CRM deal and ad spend rows.

    ai-referrals   leads from ChatGPT, Perplexity, Gemini, Claude and Copilot
    journey        first touch to last touch, and fair credit per channel
    revenue        WooCommerce revenue by channel, campaign and product
    daily-pulse    a one-page morning brief for a single day
    lead-timing    the day x hour map of when leads arrive, and on what device
    qbr            the quarter against the previous one, board-ready

Same pattern as core.build_monthly:
  1. Guard empty input -> common.empty_report(). Fewer than 10 entries -> a
     short, honest version that says why.
  2. Compute every number from the inputs (never invent one).
  3. Outcome-first headline with exactly one *accent*.
  4. Sections in reading order; each answers one question.
  5. Recommendations come from thresholds in the data, highest impact first.
  6. The closing title is a concrete next step with the number behind it.

Free-plugin data has no Premium fields. Each recipe then says plainly what
UTM Grabber Premium adds, and shows what the free fields can (utm_source tags
such as chatgpt.com, last-touch channels, timestamps).
"""
import datetime as _dt
import math
import re
from collections import Counter, defaultdict
from urllib.parse import unquote_plus

from .common import (MINUS, delta, empty_report, entry_dt, get_field, is_full_month, last_touch, lead_campaign, meta,
                     money, n, pct, period_label, period_name, pretty, prior_name, ratio, share, source_label, span,
                     stat)
from connectors import (join_deals_to_leads, lead_email, lead_platform, norm_key,  # noqa: E402
                        normalize_ad_rows, normalize_deal_rows, normalize_orders, sources_meta)
from helpers import classify_traffic_source  # noqa: E402  (common puts scripts/ on sys.path)

MIN_LEADS = 10       # below this a report switches to its short, honest version
MAX_ROWS = 12        # table rows
ONE_DAY = _dt.timedelta(days=1)
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
PREMIUM = "UTM Grabber Premium"

# ---------------------------------------------------------------------------
# text and number helpers
# ---------------------------------------------------------------------------
_BAD = {"None": "none", "NaN": "n/a", "null": "empty", "undefined": "not set"}
_NULLS = {"", "none", "null", "undefined", "nan", "n/a", "(not set)", "not set"}


def _safe(s, limit=None):
    """Data -> display text: no em or en dashes, no accent markers, no literal None/NaN."""
    s = re.sub(r"\s+", " ", str(s if s is not None else "")).strip()
    s = re.sub("\\s*[\u2014\u2013]\\s*", " - ", s).replace("*", "")
    s = re.sub(r"\b(None|NaN|null|undefined)\b", lambda mm: _BAD[mm.group(1)], s)
    if limit and len(s) > limit:
        s = s[:limit - 1].rstrip() + "…"
    return s


def _f(e, *keys):
    """First non-empty field among keys, stripped; null-like values read as empty."""
    v = get_field(e, *keys)
    return "" if v.strip().lower() in _NULLS else v.strip()


def _pl(k, word, many=None):
    return "%s %s" % (n(k), word if k == 1 else (many or word + "s"))


def _cap(s):
    return s[:1].upper() + s[1:] if s else s


def _low(s):
    """Lower-case the first letter unless the word is an acronym or a brand (ChatGPT, AI)."""
    if not s or (len(s) > 1 and s[1].isupper()):
        return s
    return s[:1].lower() + s[1:]


def _md(d):
    return "%s %d" % (d.strftime("%b"), d.day)


def _growth(cur, prev):
    return None if not prev else 100.0 * (cur - prev) / prev


def _sp(g):
    """43.2 -> '+43%', -9 -> '−9%'."""
    return "%s%d%%" % ("+" if g >= 0 else MINUS, int(round(abs(g))))


def _sn(v):
    """Signed count: +38 / −20 / 0."""
    v = int(round(v))
    return ("+" if v > 0 else (MINUS if v < 0 else "")) + n(abs(v))


def _day_rate(x):
    """Per-day rate: 37.4 / 44 / 1,250 (a trailing .0 is dropped)."""
    if x >= 100:
        return n(int(round(x)))
    s = "%.1f" % x
    return s[:-2] if s.endswith(".0") else s


def _money(v):
    """money() with whole dollars from $10 up ($68, not $68.17) and '$0' for zero."""
    if not v:
        return "$0"
    return money(v, 0) if abs(v) >= 10 else money(v)


def _plural(g):
    """Channel names like 'AI assistants' take plural verbs and pronouns."""
    return g == G_AI or g.endswith("assistants")


def _v(g, singular, plural):
    return plural if _plural(g) else singular


def _lname(label):
    """Lower-case a group label for mid-sentence use, keeping proper nouns (Google, AI)."""
    keep = ("Google", "AI ", "Bing", "Meta")
    if any(label.startswith(k) for k in keep):
        return label
    return label[:1].lower() + label[1:]


def _delta_cell(cur, prev):
    d = delta(cur, prev)
    if "delta_label" not in d:
        return {"label": "–", "direction": "flat"}
    return {"label": d["delta_label"], "direction": d["delta_direction"]}


def _badge(cur, prev):
    """Trend pill from the change vs the prior period, with a minimum volume before calling a trend."""
    if prev == 0:
        return {"label": "New", "tone": "brand"} if cur > 0 else {"label": "No leads", "tone": "neutral"}
    if cur + prev < 6:
        return {"label": "Low volume", "tone": "neutral"}
    ch = (cur - prev) / float(prev)
    if ch >= 0.15:
        return {"label": "Rising", "tone": "good"}
    if ch <= -0.5:
        return {"label": "Stalling", "tone": "bad"}
    if ch <= -0.15:
        return {"label": "Cooling", "tone": "warn"}
    return {"label": "Steady", "tone": "neutral"}


def _clock(h):
    """Hour 0-24 -> '12am', '9am', 'noon', '6pm', 'midnight'."""
    h = h % 24 if h != 24 else 24
    if h in (0, 24):
        return "midnight"
    if h == 12:
        return "noon"
    return "%d%s" % (h if h < 12 else h - 12, "am" if h < 12 else "pm")


def _hour_label(h):
    """Compact column label: 12a, 1a ... 11a, 12p, 1p ... 11p."""
    return "%d%s" % (12 if h % 12 == 0 else h % 12, "a" if h < 12 else "p")


# ---------------------------------------------------------------------------
# dates
# ---------------------------------------------------------------------------
def _day(e):
    d = entry_dt(e)
    return d.date() if d else None


def _d(v):
    """date / datetime / 'YYYY-MM-DD...' -> date (None when unreadable)."""
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    mm = re.match(r"\s*(\d{4})-(\d{2})-(\d{2})", str(v or ""))
    if not mm:
        return None
    try:
        return _dt.date(int(mm.group(1)), int(mm.group(2)), int(mm.group(3)))
    except ValueError:
        return None


def _between(entries, start, end):
    out = []
    for e in entries or []:
        d = _day(e)
        if d is not None and start <= d <= end:
            out.append(e)
    return out


def _dedupe(entries):
    seen, out = set(), []
    for e in entries:
        k = id(e)
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out


def _prev_month_start(d):
    first = d.replace(day=1)
    return (first - ONE_DAY).replace(day=1)


def _window_before(history, start, end):
    """The period just before [start, end] from a longer history: the previous calendar month for a
    calendar month, else the same number of days. Empty when the history does not reach back that far."""
    if is_full_month(start, end):
        ps, pe = _prev_month_start(start), start - ONE_DAY
    else:
        days = (end - start).days + 1
        ps, pe = start - days * ONE_DAY, start - ONE_DAY
    hs, _he = span(history)
    if not hs or hs > ps + 3 * ONE_DAY:
        return []
    return _between(history, ps, pe)


def _weeks(start, end):
    """Full 7-day windows ending on `end`, oldest first. Leftover days at the start are left out,
    so a partial week never looks like a drop."""
    if not start or not end:
        return []
    k = ((end - start).days + 1) // 7
    return [(end - _dt.timedelta(days=7 * i + 6), end - _dt.timedelta(days=7 * i)) for i in range(k - 1, -1, -1)]


def _bucket(items, weeks, date_of, value_of=None):
    """Weekly counts (or sums of value_of) over the windows from _weeks()."""
    out = [0.0 if value_of else 0] * len(weeks)
    if not weeks:
        return out
    first, last = weeks[0][0], weeks[-1][1]
    for it in items:
        d = date_of(it)
        if d is not None and first <= d <= last:
            out[(d - first).days // 7] += value_of(it) if value_of else 1
    return out


def _daily(items, start, end, date_of, value_of=None):
    """Zero-filled daily counts (or sums) for [start, end]."""
    out = [0.0 if value_of else 0] * ((end - start).days + 1)
    for it in items:
        d = date_of(it)
        if d is not None and start <= d <= end:
            out[(d - start).days] += value_of(it) if value_of else 1
    return out


def _day_labels(start, end):
    return [_md(start + i * ONE_DAY) for i in range((end - start).days + 1)]


def _as_date(v):
    if v is None or v == "":
        return None
    return _d(v)


# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------
def _host(u):
    s = str(u or "").strip().lower()
    s = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", s)
    s = s.split("/")[0].split("?")[0].split("#")[0].split(":")[0]
    return s[4:] if s.startswith("www.") else s


def _path(u):
    s = str(u or "").strip()
    if not s:
        return ""
    s = re.sub(r"^[a-z][a-z0-9+.\-]*://[^/?#]*", "", s, flags=re.I)
    s = s.split("?")[0].split("#")[0]
    if not s or s == "/":
        return "/"
    return s.rstrip("/").lower() or "/"


def _param(u, key):
    mm = re.search(r"[?&]%s=([^&#]*)" % re.escape(key), str(u or ""), re.I)
    return unquote_plus(mm.group(1)).strip() if mm else ""


def _page(e):
    """Landing page path of the converting visit (Premium field, else the form page)."""
    u = _f(e, "handl_landing_page (HandL)", "landing_page (HandL)", "Source URL", "source_url")
    return _path(u) if u else ""


def _pname(p):
    return "your home page" if p == "/" else p


# ---------------------------------------------------------------------------
# AI assistants
# ---------------------------------------------------------------------------
_AI_LIST = (
    ("ChatGPT", ("chatgpt.com", "chat.openai.com", "openai.com"), ("chatgpt", "openai")),
    ("Perplexity", ("perplexity.ai",), ("perplexity",)),
    ("Gemini", ("gemini.google.com", "bard.google.com"), ("gemini", "bard")),
    ("Claude", ("claude.ai",), ("claude",)),
    ("Copilot", ("copilot.microsoft.com", "copilot.cloud.microsoft"), ("copilot",)),
    ("DeepSeek", ("chat.deepseek.com", "deepseek.com"), ("deepseek",)),
    ("Grok", ("grok.com",), ("grok",)),
    ("Meta AI", ("meta.ai",), ()),
)
_AI_NAMES = [a[0] for a in _AI_LIST]
_TOKEN_RE = dict((nm, [re.compile(r"(^|[^a-z])%s([^a-z]|$)" % re.escape(t)) for t in toks]) for nm, _d_, toks in _AI_LIST)


def _ai_name(text):
    """'chatgpt.com', 'https://www.perplexity.ai/', 'OpenAI/ChatGPT', 'claude' -> assistant name, else None."""
    t = str(text or "").strip().lower()
    if not t or t in _NULLS:
        return None
    host = _host(t)
    for nm, domains, _toks in _AI_LIST:
        if any(host == dm or host.endswith("." + dm) for dm in domains):
            return nm
    for nm, _dm, _toks in _AI_LIST:
        if any(rx.search(t) for rx in _TOKEN_RE[nm]):
            return nm
    return None


_REFERRER_KEYS = ("Referrer", "Referer", "HTTP Referer", "HTTP Referrer", "referrer", "referer", "http_referer")


def ai_last(e):
    """(assistant, how it was detected) when the converting visit came from an AI assistant, else (None, None)."""
    for key, how in (("organic_source_str (HandL)", "organic source"), ("handl_ref_domain (HandL)", "referrer domain")):
        nm = _ai_name(_f(e, key))
        if nm:
            return nm, how
    nm = _ai_name(_f(e, "utm_source (HandL)", "utm_source"))
    if nm:
        return nm, "utm_source tag"
    for key in ("handl_landing_page (HandL)", "landing_page (HandL)", "Source URL", "source_url"):
        nm = _ai_name(_param(_f(e, key), "utm_source"))
        if nm:
            return nm, "landing page tag"
    nm = _ai_name(_f(e, *_REFERRER_KEYS))
    if nm:
        return nm, "form referrer"
    return None, None


# ---------------------------------------------------------------------------
# first touch and channel groups
# ---------------------------------------------------------------------------
_FT_KEYS = ("traffic_source (first touch, HandL)", "utm_source (first touch, HandL)", "utm_medium (first touch, HandL)",
            "utm_campaign (first touch, HandL)", "landing_page (first touch, HandL)", "referrer (first touch, HandL)",
            "first_traffic_source (HandL)", "first_utm_source (HandL)", "first_utm_medium (HandL)",
            "first_traffic_source", "first_utm_source", "first_utm_medium")
_PREMIUM_KEYS = ("organic_source_str (HandL)", "handl_ref_domain (HandL)", "user_agent (HandL)") + _FT_KEYS


def has_ft(e):
    return bool(_f(e, *_FT_KEYS))


def _premium(entries):
    """True when the entries carry any field only UTM Grabber Premium records."""
    return any(_f(e, *_PREMIUM_KEYS) for e in list(entries)[:500])


def _ft_fields(e):
    land = _f(e, "landing_page (first touch, HandL)", "first_landing_page (HandL)")
    src = _f(e, "utm_source (first touch, HandL)", "first_utm_source (HandL)", "first_utm_source") or _param(land, "utm_source")
    med = _f(e, "utm_medium (first touch, HandL)", "first_utm_medium (HandL)", "first_utm_medium") or _param(land, "utm_medium")
    ref = _f(e, "referrer (first touch, HandL)", "first_referrer (HandL)")
    traffic = _f(e, "traffic_source (first touch, HandL)", "first_traffic_source (HandL)", "first_traffic_source")
    return src, med, traffic, ref, land


def ai_first(e):
    """Assistant behind the first visit (Premium first-touch fields), else None."""
    if not has_ft(e):
        return None
    src, _med, _tr, ref, land = _ft_fields(e)
    return _ai_name(src) or _ai_name(ref) or _ai_name(_param(land, "utm_source"))


G_PSEARCH, G_PSOCIAL, G_OPAID = "Paid search", "Paid social", "Other paid"
G_OSEARCH, G_AI, G_EMAIL = "Organic search", "AI assistants", "Email"
G_OSOCIAL, G_REF, G_DIRECT = "Organic social", "Referral", "Direct"
GROUP_ORDER = [G_PSEARCH, G_PSOCIAL, G_OPAID, G_OSEARCH, G_AI, G_EMAIL, G_OSOCIAL, G_REF, G_DIRECT]
PAID_GROUPS = (G_PSEARCH, G_PSOCIAL, G_OPAID)
GROUP_DEF = {
    G_PSEARCH: "a paid click from a search engine (cpc tags or a Google or Microsoft click ID)",
    G_PSOCIAL: "a paid click from a social platform (paid social tags or a Meta click ID)",
    G_OPAID: "a paid click from any other network (display, video or another paid medium)",
    G_OSEARCH: "an unpaid visit from a search engine",
    G_AI: "a visit from an AI assistant such as ChatGPT or Perplexity",
    G_EMAIL: "an email or newsletter link", G_OSOCIAL: "an unpaid social post or profile link",
    G_REF: "a link on another website", G_DIRECT: "a typed URL, bookmark or untagged link",
}

_SOCIAL = {"facebook", "instagram", "meta", "fb", "ig", "tiktok", "linkedin", "lnkd", "twitter", "x", "t",
           "pinterest", "snapchat", "reddit", "youtube", "threads", "messenger", "nextdoor", "quora"}
_SEARCH = {"google", "bing", "duckduckgo", "yahoo", "ecosia", "brave", "baidu", "yandex", "msn", "aol",
           "startpage", "qwant"}
_EMAIL_SITES = {"newsletter", "email", "mailchimp", "klaviyo", "sendgrid", "convertkit", "activecampaign",
                "constantcontact", "mailerlite", "substack", "drip", "omnisend"}
_EMAIL_MED = {"email", "e-mail", "newsletter", "mail"}
_PAID_MED = {"cpc", "ppc", "paid", "paid_search", "paidsearch", "paid-search", "sem", "paid_social", "paidsocial",
             "paid-social", "cpm", "display", "cpv", "banner", "retargeting", "remarketing", "ads"}
_SEARCH_MED = {"cpc", "ppc", "paid_search", "paidsearch", "paid-search", "sem"}


def _site(s):
    """'l.instagram.com' -> 'instagram'; 'Google' -> 'google'; 'alderbayparents.org' -> 'alderbayparents'."""
    h = _host(s)
    if not h:
        return ""
    parts = [p for p in re.split(r"[.\s/]+", h) if p]
    for p in parts:
        if p in _SOCIAL or p in _SEARCH or p in _EMAIL_SITES:
            return p
    return parts[0] if parts else ""


def _group(src, med, traffic, ref="", org="", search_click=False, social_click=False):
    """One visit -> channel group (GROUP_ORDER)."""
    src, med = (src or "").strip().lower(), (med or "").strip().lower()
    traffic = (traffic or "").strip().capitalize()
    if _ai_name(src) or _ai_name(ref) or _ai_name(org):
        return G_AI
    site = _site(src) or _site(ref) or _site(org)
    paid = traffic == "Paid" or med in _PAID_MED or search_click or (social_click and "paid" in med)
    if paid:
        if site in _SOCIAL or "social" in med or (social_click and not search_click):
            return G_PSOCIAL
        if site in _SEARCH or search_click or med in _SEARCH_MED:
            return G_PSEARCH
        return G_OPAID
    if med in _EMAIL_MED or site in _EMAIL_SITES:
        return G_EMAIL
    if site in _SOCIAL or "social" in med or traffic == "Social" or social_click:
        return G_OSOCIAL
    if site in _SEARCH or traffic == "Organic" or med in ("organic", "seo", "organic_search"):
        return G_OSEARCH
    if traffic == "Referral" or med in ("referral", "partner", "affiliate") or src or ref:
        return G_REF
    return G_DIRECT


def lt_group(e):
    """Channel group of the converting visit (last touch)."""
    return _group(_f(e, "utm_source (HandL)", "utm_source"), _f(e, "utm_medium (HandL)", "utm_medium"),
                  classify_traffic_source(e), _f(e, "handl_ref_domain (HandL)"), _f(e, "organic_source_str (HandL)"),
                  bool(_f(e, "gclid (HandL)", "gclid", "msclkid (HandL)", "msclkid", "wbraid (HandL)", "gbraid (HandL)")),
                  bool(_f(e, "fbclid (HandL)", "fbclid", "ttclid (HandL)", "ttclid")))


def ft_group(e):
    """Channel group of the first visit (Premium first-touch fields). Call only when has_ft(e)."""
    src, med, traffic, ref, land = _ft_fields(e)
    if not traffic and (src or med):
        traffic = classify_traffic_source({"utm_source": src, "utm_medium": med})
    return _group(src, med, traffic, ref, "",
                  bool(_param(land, "gclid") or _param(land, "msclkid") or _param(land, "wbraid") or _param(land, "gbraid")),
                  bool(_param(land, "fbclid") or _param(land, "ttclid")))


def _gsort(groups, weight):
    return sorted(groups, key=lambda g: (-weight(g), GROUP_ORDER.index(g) if g in GROUP_ORDER else 99, g))


def _fold(groups_by_weight, k=6):
    """Keep the k-1 biggest groups and fold the rest into 'Other' when there are more than k."""
    if len(groups_by_weight) <= k:
        return list(groups_by_weight), {}
    keep = list(groups_by_weight[:k - 1])
    return keep, dict((g, "Other") for g in groups_by_weight[k - 1:])


# ---------------------------------------------------------------------------
# campaigns, sources, devices
# ---------------------------------------------------------------------------
def _camp(e):
    return _safe(_f(e, "utm_campaign (HandL)", "utm_campaign")).lower()


def _src(e):
    return _safe(_f(e, "utm_source (HandL)", "utm_source")).lower()


def _src_label(k):
    return _ai_name(k) or source_label(k)


def _tagged(e):
    return bool(_f(e, "utm_source (HandL)", "utm_source") and _f(e, "utm_medium (HandL)", "utm_medium")
                and _f(e, "utm_campaign (HandL)", "utm_campaign"))


def _device(e):
    ua = _f(e, "user_agent (HandL)", "User Agent", "user_agent", "HTTP User Agent").lower()
    if not ua:
        return None
    if "ipad" in ua or "tablet" in ua or ("android" in ua and "mobile" not in ua):
        return "Tablet"
    if any(k in ua for k in ("iphone", "ipod", "android", "mobile", "windows phone", "blackberry")):
        return "Mobile"
    return "Desktop"


def _find_field(entries, words, min_share=0.3):
    """The form field whose label contains one of `words` and that most entries answered."""
    c = Counter()
    sample = entries[:600]
    for e in sample:
        for k, v in e.items():
            kl = str(k).lower()
            if "utm" in kl or "handl" in kl or "date" in kl or "source" in kl:
                continue
            if any(w in kl for w in words) and str(v if v is not None else "").strip():
                c[k] += 1
    if not c:
        return None
    k, hits = c.most_common(1)[0]
    return k if hits >= max(3, min_share * len(sample)) else None


# ---------------------------------------------------------------------------
# connector rows
# ---------------------------------------------------------------------------
_REFUNDED = {"refunded"}
_VOID = {"cancelled", "canceled", "failed", "pending", "pending payment", "trash", "draft", "checkout-draft"}
_PLATFORM_KEYS = {"Google Ads": "google_ads", "Meta Ads": "meta_ads", "Microsoft Ads": "microsoft_ads",
                  "LinkedIn Ads": "linkedin_ads"}


def _ads(rows):
    try:
        return normalize_ad_rows(rows) if rows else []
    except Exception:
        return []


def _deals(rows):
    try:
        return normalize_deal_rows(rows) if rows else []
    except Exception:
        return []


def _ad_platform(name):
    k = norm_key(name).replace("_", "")
    for plat, aliases in (("Google Ads", ("google", "googleads", "adwords")),
                          ("Meta Ads", ("meta", "metaads", "facebook", "facebookads", "instagram")),
                          ("Microsoft Ads", ("microsoft", "microsoftads", "bing", "bingads")),
                          ("LinkedIn Ads", ("linkedin", "linkedinads")), ("TikTok Ads", ("tiktok", "tiktokads"))):
        if k in aliases:
            return plat
    return _safe(name) or "Ads"


def _ad_span(ads):
    ds = [x for x in (_d(r.get("date")) for r in ads) if x]
    return (min(ds), max(ds)) if ds else (None, None)


def _ads_in(ads, start, end):
    """Ad rows dated inside [start, end]; undated rows are kept (they can't be placed)."""
    out = []
    for r in ads:
        d = _d(r.get("date"))
        if d is None or start <= d <= end:
            out.append(r)
    return out


def _spend_sources(ads):
    by = Counter()
    for r in ads:
        by[_ad_platform(r.get("platform"))] += r.get("spend", 0.0)
    return [(p, v) for p, v in by.most_common() if v > 0]


def _products(v):
    """'A, B x2' / ['A', 'B'] / [{'name': 'A', 'quantity': 2}] -> [(name, qty)]."""
    out = []
    if isinstance(v, (list, tuple)):
        for it in v:
            if isinstance(it, dict):
                nm = _safe(it.get("name") or it.get("product") or it.get("title") or "")
                q = it.get("quantity") or it.get("qty") or 1
                try:
                    q = int(float(q))
                except (TypeError, ValueError):
                    q = 1
                if nm:
                    out.append((nm, max(1, q)))
            elif str(it).strip():
                out.extend(_products(str(it)))
        return out
    for part in str(v or "").split(","):
        part = _safe(part)
        if not part:
            continue
        mm = re.match(r"^(.*?)\s+[x×]\s*(\d+)$", part)
        if mm:
            out.append((mm.group(1).strip(), int(mm.group(2))))
        else:
            out.append((part, 1))
    return out


def _sales_from_orders(entries):
    """WooCommerce order entries -> sale dicts with both touches classified from the order's own fields."""
    out = []
    for e in entries or []:
        rows = normalize_orders([e])
        if not rows:
            continue
        o = rows[0]
        st = (o.get("status") or "completed").strip().lower()
        out.append({"date": _d(o.get("date")), "total": float(o.get("total") or 0.0), "status": st,
                    "refunded": st in _REFUNDED, "void": st in _VOID, "lt": lt_group(e),
                    "ft": ft_group(e) if has_ft(e) else None, "campaign": _camp(e), "source": _src(e),
                    "platform": lead_platform(e), "products": _products(o.get("products")),
                    "email": o.get("email") or "", "matched": True})
    return out


def _sales_from_deals(deal_rows, leads):
    """Won CRM deals -> sale dicts, attributed through the lead with the same email."""
    by_email = {}
    for e in leads or []:
        em = lead_email(e)
        if em and em not in by_email:
            by_email[em] = e
    out = []
    for dl in _deals(deal_rows):
        if dl.get("stage") != "won":
            continue
        e = by_email.get(dl.get("email") or "")
        # created date: the deal belongs to the period its lead came in, so periods never overlap
        out.append({"date": _d(dl.get("created")) or _d(dl.get("closed")), "total": float(dl.get("amount") or 0.0),
                    "status": "won", "refunded": False, "void": False,
                    "lt": lt_group(e) if e else "No form lead", "ft": ft_group(e) if e is not None and has_ft(e) else None,
                    "campaign": _camp(e) if e else "", "source": _src(e) if e else "",
                    "platform": lead_platform(e) if e else None, "products": [], "email": dl.get("email") or "",
                    "matched": e is not None})
    return out


# ---------------------------------------------------------------------------
# shared short versions
# ---------------------------------------------------------------------------
def _meta(brand_profile, customer_name, customer_domain, compare_label, prepared_by, prepared_for):
    return meta(brand_profile, customer_name, customer_domain, compare_label=compare_label, sources=None,
                prepared_by=prepared_by, prepared_for=prepared_for)


def _short(m, kicker, title, why_title, why_body, subtitle=None, stats=None, extra=None, close_title="",
           close_body=None, bits=None, why_kicker="Why this report is short", tone="neutral"):
    """Short, honest report: what we saw, why it is short, what to do next."""
    top = {"type": "title-block", "kicker": kicker, "title": title, "meta_bits": [b for b in (bits or []) if b]}
    if subtitle:
        top["subtitle"] = subtitle
    secs = [top]
    if stats and 2 <= len(stats) <= 6:
        secs.append({"type": "stat-strip", "stats": stats})
    secs.append({"type": "insight-card", "kicker": why_kicker, "title": why_title, "body": why_body, "tone": tone})
    secs.extend(extra or [])
    close = {"type": "closing", "kicker": "Next step", "title": close_title}
    if close_body:
        close["body"] = close_body
    secs.append(close)
    return {"meta": m, "sections": secs}


def _lead_table(entries, title, limit=9, assistant=False):
    """Up to `limit` leads, oldest first, without names or emails."""
    rows = []
    ordered = sorted(entries, key=lambda x: entry_dt(x) or _dt.datetime.min)
    for i, e in enumerate(ordered[:limit]):
        d = _day(e)
        src, med = _src(e), _safe(_f(e, "utm_medium (HandL)", "utm_medium")).lower()
        row = {"rank": str(i + 1), "date": _md(d) if d else "–",
               "sm": ("%s / %s" % (src or "(not set)", med or "(not set)")) if (src or med) else "no UTM tags",
               "page": _safe(_page(e), 34) or "–"}
        if assistant:
            nm, how = ai_last(e)
            row["who"] = nm or "–"
            row["how"] = how or "–"
        else:
            row["channel"] = lt_group(e)
        rows.append(row)
    cols = [{"key": "rank", "label": "#", "type": "rank"}, {"key": "date", "label": "Date", "type": "text"}]
    if assistant:
        cols += [{"key": "who", "label": "Assistant", "type": "name"}, {"key": "how", "label": "Found in", "type": "text"}]
    else:
        cols += [{"key": "channel", "label": "Channel", "type": "name"}]
    cols += [{"key": "sm", "label": "Source / medium", "type": "source"},
             {"key": "page", "label": "Landing page", "type": "source"}]
    cap = ("Shown without names or emails." if len(entries) <= limit else
           "The first %s of %s, shown without names or emails." % (n(limit), n(len(entries))))
    return {"type": "ranked-list", "title": title, "columns": cols, "rows": rows, "caption": cap}


def _thin(name, m, entries, period, subject="this period"):
    total = len(entries)
    m["sources"] = sources_meta(utmg=_pl(total, "lead"))
    return _short(m, "%s · %s" % (name, period) if period else name,
                  "Only %s so far: too few to read a *pattern*." % _pl(total, "lead"),
                  "This report needs at least *10 leads*.",
                  ["%s brought %s. With so few, one extra lead moves any share by %s points, so a breakdown "
                   "would be noise." % (_cap(subject), _pl(total, "lead"), n(round(100.0 / max(total, 1)))),
                   "Widen the date range, or run this again once more submissions arrive."],
                  subtitle="Here is what arrived, and what this report needs before it can rank anything.",
                  stats=[stat("Leads", n(total)), stat("Fully tagged", pct(share(sum(1 for e in entries if _tagged(e)), total)))],
                  extra=[_lead_table(entries, "The *leads* we found")] if entries else [],
                  close_title="Next: widen the *date range* and run this again. %s is too few to rank." %
                              _cap(_pl(total, "lead")),
                  close_body="Nothing is broken: the report fills itself in as submissions arrive.",
                  bits=[m.get("customer_domain"), "%s submissions" % n(total)])


def _undated(name, m, entries):
    m["sources"] = sources_meta(utmg=_pl(len(entries), "lead"))
    return _short(m, name, "We couldn't read the *dates* on these %s." % _pl(len(entries), "lead"),
                  "We need a *date* on every lead.",
                  ["Not one of the %s entries carried a readable submission date, so we can't place them in time." %
                   n(len(entries)), "Pull the entries again with the Date Created field included."],
                  close_title="Next: re-pull the leads with their *dates* and run this again.",
                  bits=[m.get("customer_domain"), "%s submissions" % n(len(entries))])


# ===========================================================================
# 1. LEADS FROM AI ASSISTANTS
# ===========================================================================
def _ai_page(e):
    """Where an AI-referred visitor landed: the converting visit's landing page, else the form page."""
    return _page(e) or "(not recorded)"


def _deal_stats(deals, leads, groups):
    """{group: (leads, customers, revenue, matched deals)}. Deals are joined to leads once, by email, so a
    person with leads in two groups is counted in one (the group of their first lead in the list)."""
    matched, _un = join_deals_to_leads(deals, leads)
    where = {}
    for gname, members in groups.items():
        for e in members:
            where[id(e)] = gname
    out = {}
    for gname, members in groups.items():
        mine = [x for x in matched if where.get(id(x["lead"])) == gname]
        won = [x for x in mine if x["deal"]["stage"] == "won"]
        out[gname] = (len(members), len(set(x["deal"]["email"] for x in won)),
                      sum(x["deal"].get("amount") or 0.0 for x in won), len(mine))
    return out


def _ai_signals(pool):
    """Form-answer quality signals for when no CRM deals are connected: (label, test) pairs."""
    out = []
    pk = _find_field(pool, ("phone", "mobile", "cell", "tel"), 0.1)
    if pk:
        out.append(("Left a phone number", lambda e, k=pk: bool(str(e.get(k) or "").strip())))
    tk = _find_field(pool, ("timeframe", "time frame", "timeline", "how soon", "urgency", "when do you"))
    if tk:
        soon = re.compile(r"\b(this week|this month|asap|immediately|right away|today|urgent|within 30|next 30|"
                          r"30 days|1 month|one month|2 weeks|two weeks)\b", re.I)
        out.append(("Ready within 30 days", lambda e, k=tk: bool(soon.search(str(e.get(k) or "")))))
    ck = _find_field(pool, ("company", "business name", "organization", "organisation"))
    if ck:
        out.append(("Named a company", lambda e, k=ck: bool(str(e.get(k) or "").strip())))
    return out


def build_ai_referrals(leads, prior=None, history=None, deal_rows=None, brand_profile=None, customer_name=None,
                       customer_domain="", compare_label=None, form_label=None, prepared_by=None, prepared_for=None,
                       **_):
    """Leads whose converting visit came from an AI assistant: how many, from which, to which pages, how good."""
    name = "Leads from AI assistants"
    leads, prior, history = list(leads or []), list(prior or []), list(history or [])
    start, end = span(leads)
    if not prior and history and start:
        prior = _window_before(history, start, end)
    pstart, pend = span(prior) if prior else (None, None)
    m = _meta(brand_profile, customer_name, customer_domain,
              compare_label or (prior_name(pstart, pend) if prior else "last period"), prepared_by, prepared_for)
    if not leads:
        return empty_report(name, m)
    if start is None:
        return _undated(name, m, leads)
    period = period_label(start, end)
    kicker = "%s · %s" % (name, period)
    total = len(leads)
    days = (end - start).days + 1
    bits = [customer_domain, form_label, "%s submissions" % n(total), _pl(days, "day")]
    cmp_ = m["compare_label"]
    if total < MIN_LEADS:
        return _thin(name, m, leads, period)

    ai = []
    for e in leads:
        nm, how = ai_last(e)
        if nm:
            ai.append((e, nm, how))
    n_ai = len(ai)
    ai_ids = set(id(e) for e, _a, _h in ai)
    premium = _premium(leads)
    deals = _deals(deal_rows)
    m["sources"] = sources_meta(utmg="%s leads" % n(total), CRM=("%s deals" % n(len(deals))) if deals else None)

    if not premium:
        return _ai_free(m, kicker, leads, ai, bits)
    if n_ai == 0:
        return _ai_none(m, kicker, leads, bits, period)

    by_ai = Counter(a for _e, a, _h in ai)
    top_ai, top_n = by_ai.most_common(1)[0]
    prior_ai = [e for e in prior if ai_last(e)[0]]
    by_ai_prior = Counter(ai_last(e)[0] for e in prior_ai)
    has_prior = len(prior) >= MIN_LEADS
    organic = [e for e in leads if last_touch(e) == "Organic" or id(e) in ai_ids]
    org_prior = [e for e in prior if last_touch(e) == "Organic" or ai_last(e)[0]]
    ai_share, ai_share_p = share(n_ai, total), (share(len(prior_ai), len(prior)) if has_prior else None)
    org_share = share(n_ai, len(organic))
    org_share_p = share(len(prior_ai), len(org_prior)) if has_prior and org_prior else None
    ft_ok = sum(1 for e in leads if has_ft(e)) >= max(5, 0.1 * total)
    started = [e for e in leads if id(e) not in ai_ids and ai_first(e)] if ft_ok else []
    started_p = [e for e in prior if not ai_last(e)[0] and ai_first(e)] if ft_ok and has_prior else []
    g = _growth(n_ai, len(prior_ai)) if has_prior and prior_ai else None
    daily_ai = _daily([e for e, _a, _h in ai], start, end, _day)

    if n_ai < MIN_LEADS:
        return _ai_few(m, kicker, leads, ai, organic, started, bits, cmp_, prior_ai if has_prior else None)

    # history: weekly trend and month-by-month growth
    pool = _dedupe(history + prior + leads)
    hs, he = span(pool)
    ai_pool = [e for e in pool if id(e) in ai_ids or ai_last(e)[0]]
    weeks = _weeks(hs, he)
    monthly = []
    if hs and he:
        cur = hs.replace(day=1)
        while cur <= he:
            nxt = (cur.replace(day=28) + 4 * ONE_DAY).replace(day=1)
            mend = nxt - ONE_DAY
            if cur >= hs and mend <= he:
                monthly.append((cur, sum(1 for e in ai_pool if cur <= (_day(e) or _dt.date.min) <= mend)))
            cur = nxt
    rising = len(monthly) >= 3 and all(monthly[i][1] < monthly[i + 1][1] for i in range(len(monthly) - 1))

    # headline
    if g is not None and g >= 3:
        headline = "*AI assistants* sent %s, %s more than %s." % (_pl(n_ai, "lead"), _sp(g).lstrip("+"), cmp_)
    elif g is not None and g <= -3:
        headline = "*AI assistants* sent %s, %s fewer than %s." % (_pl(n_ai, "lead"), _sp(g).lstrip(MINUS), cmp_)
    else:
        headline = "*AI assistants* sent %s, %s of all leads." % (_pl(n_ai, "lead"), pct(ai_share, 1 if ai_share < 10 else 0))
    sub = ["%s sent %s of them." % (top_ai, n(top_n))]
    if started:
        sub.append("AI assistants also started %s that converted through another channel." %
                   _pl(len(started), "more journey", "more journeys"))
    elif rising:
        sub.append("AI leads have grown every month since %s." % monthly[0][0].strftime("%B"))

    stats = [stat("AI leads", n(n_ai), n_ai, len(prior_ai) if has_prior and prior_ai else None, spark=daily_ai,
                  note=("%s in %s" % (n(len(prior_ai)), cmp_)) if has_prior else "from %s" % (
                      ", ".join(a for a, _v in by_ai.most_common(3)))),
             stat("Share of all leads", pct(ai_share, 1 if ai_share < 10 else 0), ai_share, ai_share_p, kind="pts",
                  note="%s of %s leads" % (n(n_ai), n(total))),
             stat("Share of organic", pct(org_share), org_share, org_share_p, kind="pts",
                  note="of %s unpaid search and AI leads" % n(len(organic)))]
    if started:
        stats.append(stat("AI-started journeys", n(len(started)), len(started),
                          len(started_p) if started_p else None,
                          note="first visit from AI, converted elsewhere"))
    secs = [{"type": "title-block", "kicker": kicker, "title": headline, "subtitle": " ".join(sub),
             "meta_bits": [b for b in bits if b]},
            {"type": "stat-strip", "stats": stats}]

    # takeaway
    body = []
    rest = by_ai.most_common()[1:3]
    if rest:
        body.append("%s follow%s with %s." % (" and ".join(a for a, _v in rest), "" if len(rest) > 1 else "s",
                                              " and ".join(n(v) for _a, v in rest)))
    if rising:
        body.append("AI leads grew every month, from %s in %s to %s in %s." % (
            n(monthly[0][1]), monthly[0][0].strftime("%B"), n(monthly[-1][1]), monthly[-1][0].strftime("%B")))
    elif g is not None:
        body.append("That is %s against %s, when assistants sent %s." % (_sp(g), cmp_, n(len(prior_ai))))
    secs.append({"type": "insight-card", "kicker": "The takeaway",
                 "title": "*%s* sent %s of your AI leads." % (top_ai, pct(share(top_n, n_ai))), "body": body})

    # 01 which assistants
    rows_ai = by_ai.most_common(6)
    chart = {"type": "bar-horizontal", "labels": [a for a, _v in rows_ai], "values": [v for _a, v in rows_ai],
             "x_title": "Leads", "highlight": 0, "total": n_ai}
    if has_prior:
        chart["notes"] = [("%s in %s" % (n(by_ai_prior.get(a, 0)), cmp_)) if by_ai_prior.get(a) else
                          "new this period" for a, _v in rows_ai]
    ins = ["%s sent %s of %s AI leads (%s)." % (top_ai, n(top_n), n(n_ai), pct(share(top_n, n_ai)))]
    if has_prior and by_ai_prior:
        movers = sorted(((a, by_ai.get(a, 0) - by_ai_prior.get(a, 0)) for a in set(by_ai) | set(by_ai_prior)),
                        key=lambda x: -abs(x[1]))
        if movers and abs(movers[0][1]) >= 3:
            a, dv = movers[0]
            ins.append("%s moved the most: %s leads against %s." % (a, _sn(dv), cmp_))
    secs.append({"type": "section-header", "number": "01", "kicker": "Which assistants",
                 "title": "Where your *AI leads* come from.",
                 "dek": "The assistant behind each converting visit, from %s's organic source and referrer fields." % PREMIUM})
    secs.append({"type": "chart-insight", "chart": chart, "caption": "AI-assistant leads by assistant",
                 "insight_kicker": "The leader",
                 "insight_title": ("*%s* sends more than the rest combined." % top_ai) if top_n * 2 > n_ai else
                 ("*%s* leads with %s." % (top_ai, _pl(top_n, "lead"))),
                 "insight_body": ins})

    # 02 trend
    if len(weeks) >= 6:
        wk = _bucket(ai_pool, weeks, _day)
        labels = [_md(w[0]) for w in weeks]
        half = len(wk) // 2
        a_, b_ = sum(wk[:half]), sum(wk[len(wk) - half:])
        if b_ > a_ * 1.15 and b_ - a_ >= 5:
            t_title = "AI referrals are *growing* week by week."
        elif b_ < a_ * 0.85 and a_ - b_ >= 5:
            t_title = "AI referrals are *slowing* down."
        else:
            t_title = "AI referrals are holding *steady*."
        cap = "AI-assistant leads per week, %s to %s. Peak of %s in the week of %s." % (
            _md(weeks[0][0]), _md(weeks[-1][1]), n(max(wk)), labels[wk.index(max(wk))])
        secs.append({"type": "section-header", "number": "02", "kicker": "The trend", "title": t_title,
                     "dek": "Weeks run to %s; a part week at the start is left out." % _md(he)})
        secs.append({"type": "chart", "chart": {"type": "line", "labels": labels, "values": wk},
                     "chart_title": "AI leads per *week*", "caption": cap})
    else:
        labels = _day_labels(start, end)
        secs.append({"type": "section-header", "number": "02", "kicker": "The trend",
                     "title": "AI leads, *day* by day.", "dek": "Pass a longer history to see the weekly trend."})
        secs.append({"type": "chart", "chart": {"type": "area", "labels": labels, "values": daily_ai},
                     "chart_title": "AI leads per *day*",
                     "caption": "%s AI leads over %s." % (n(n_ai), _pl(days, "day"))})

    # 03 landing pages
    pages = Counter(_ai_page(e) for e, _a, _h in ai)
    all_pages = Counter(_page(e) or "(not recorded)" for e in leads)
    page_ai = defaultdict(Counter)
    for e, a, _h in ai:
        page_ai[_ai_page(e)][a] += 1
    prow = []
    for i, (p, v) in enumerate(pages.most_common(8)):
        prow.append({"rank": str(i + 1), "page": _safe(p, 40), "leads": {"value": v, "label": n(v)},
                     "share": pct(share(v, n_ai)), "all": pct(share(all_pages.get(p, 0), total)),
                     "who": page_ai[p].most_common(1)[0][0], "_highlight": i == 0})
    top_page, top_page_n = pages.most_common(1)[0]
    over = [(p, share(v, n_ai) - share(all_pages.get(p, 0), total)) for p, v in pages.most_common(8) if v >= 3]
    over = sorted(over, key=lambda x: -x[1])
    cap = "Share of all leads shows how often the page converts visitors from every channel."
    if over and over[0][1] >= 5:
        cap = "%s takes %s of AI leads but %s of all leads: assistants favor it." % (
            _cap(_pname(over[0][0])), pct(share(pages[over[0][0]], n_ai)), pct(share(all_pages.get(over[0][0], 0), total)))
    secs.append({"type": "section-header", "number": "03", "kicker": "Landing pages",
                 "title": "The *pages* AI assistants send people to.",
                 "dek": "The page each AI-referred visitor landed on before filling in a form."})
    secs.append({"type": "ranked-list", "title": "Landing pages for *AI leads*",
                 "columns": [{"key": "rank", "label": "#", "type": "rank"},
                             {"key": "page", "label": "Page", "type": "source"},
                             {"key": "leads", "label": "AI leads", "type": "bar"},
                             {"key": "share", "label": "Share of AI", "type": "pct", "align": "right"},
                             {"key": "all", "label": "Share of all", "type": "pct", "align": "right"},
                             {"key": "who", "label": "Top assistant", "type": "name"}],
                 "rows": prow, "caption": cap})

    # 04 quality vs Google organic
    others = [e for e in leads if id(e) not in ai_ids]
    google = [e for e in others if lt_group(e) == G_OSEARCH and
              "google" in (_f(e, "organic_source_str (HandL)") + " " + _src(e) + " " + _f(e, "handl_ref_domain (HandL)")).lower()]
    base_label = "Google organic"
    if len(google) < MIN_LEADS:
        google = [e for e in others if lt_group(e) == G_OSEARCH]
        base_label = "Organic search"
    if len(google) < MIN_LEADS:
        google, base_label = others, "All other leads"
    ai_leads = [e for e, _a, _h in ai]
    rows_q, q_head, q_note = [], None, None

    def add(label, a, b, ad, bd, higher_better=True, gap=3.0):
        row = {"label": label, "a": round(a, 2), "b": round(b, 2), "a_display": ad, "b_display": bd}
        if abs(a - b) >= gap:
            row["better"] = "a" if (a > b) == higher_better else "b"
        rows_q.append(row)

    add("Leads", n_ai, len(google), n(n_ai), n(len(google)), gap=1e9)
    ds = _deal_stats(deals, leads, {"ai": ai_leads, "base": google}) if deals else {}
    deal_ok = bool(ds) and ds["ai"][3] >= 5 and ds["base"][3] >= 5
    if deal_ok:
        (la, ca, ra, _ma), (lb, cb, rb, _mb) = ds["ai"], ds["base"]
        cra, crb = share(ca, la), share(cb, lb)
        add("Became customers", cra, crb, pct(cra), pct(crb))
        rpl_a, rpl_b = ra / float(la), rb / float(lb)
        add("Revenue per lead", rpl_a, rpl_b, _money(rpl_a), _money(rpl_b), gap=0.05 * max(rpl_a, rpl_b, 1))
        if ca and cb:
            add("Average sale", ra / ca, rb / cb, _money(ra / ca), _money(rb / cb), gap=0.05 * max(ra / ca, rb / cb))
        if abs(rpl_a - rpl_b) >= 0.05 * max(rpl_a, rpl_b, 1):
            q_head = "Each AI lead is worth *%s*, against %s from %s." % (_money(rpl_a), _money(rpl_b), _lname(base_label))
        else:
            q_head = "AI leads are worth about the *same* as %s leads." % _lname(base_label)
        q_note = ("Customers and revenue come from %s CRM deals matched to these leads by email (each person counted "
                  "once); open deals don't count yet." % n(ds["ai"][3] + ds["base"][3]))
    else:
        for label, test in _ai_signals(leads):
            qa = share(sum(1 for e in ai_leads if test(e)), n_ai)
            qb = share(sum(1 for e in google if test(e)), len(google))
            add(label, qa, qb, pct(qa), pct(qb))
        devs_a = [d for d in (_device(e) for e in ai_leads) if d]
        devs_b = [d for d in (_device(e) for e in google) if d]
        if len(rows_q) > 1 and len(devs_a) >= 5 and len(devs_b) >= 5:
            ma, mb = share(devs_a.count("Mobile"), len(devs_a)), share(devs_b.count("Mobile"), len(devs_b))
            rows_q.append({"label": "On a phone", "a": round(ma, 1), "b": round(mb, 1), "a_display": pct(ma),
                           "b_display": pct(mb)})
        if len(rows_q) > 1:
            q_head = "How AI leads *compare* with %s." % _lname(base_label)
            q_note = ("Too few CRM deals matched these leads to compare close rates, so quality comes from form answers."
                      if deals else
                      "No CRM deals were connected, so quality comes from form answers. Connect your CRM to compare "
                      "close rates.")
    if len(rows_q) <= 1:
        q_note = ("Lead quality is not compared: %s, and the forms ask no qualifying question (phone, timeframe or "
                  "company) often enough." % ("too few CRM deals matched these leads" if deals else "no CRM deals were "
                                               "connected"))
    if len(rows_q) > 1:
        secs.append({"type": "section-header", "number": "04", "kicker": "Lead quality", "title": q_head,
                     "dek": "AI-referred leads against %s leads in the same period." % _lname(base_label)})
        secs.append({"type": "comparison", "a": {"label": "AI assistants", "sub": _pl(n_ai, "lead")},
                     "b": {"label": base_label, "sub": _pl(len(google), "lead")}, "rows": rows_q,
                     "caption": q_note or ""})
    nxt = 5 if len(rows_q) > 1 else 4

    # next steps
    lp_paths = set(p for p in all_pages if p)
    has_faq = any(re.search(r"pric|cost|faq|questions|rates|fees", p) for p in lp_paths)
    recs = [{"label": "This month", "title": "Put clear answers and prices on *%s*" % (
        "your home page" if top_page == "/" else _safe(top_page, 32)),
             "body": "%s received %s of your %s AI leads. Assistants quote pages that answer the question in "
                     "the first lines: what it costs, how long it takes, who it is for." % (
                         _cap(_pname(top_page)), n(top_page_n), n(n_ai)),
             "impact": "High", "effort": "Medium"}]
    if deal_ok:   # a quality gap is the most specific finding, so it comes right after the top page
        (la, ca, ra, _ma), (lb, cb, rb, _mb) = ds["ai"], ds["base"]
        cra, crb = share(ca, la), share(cb, lb)
        if crb - cra >= 5:
            recs.append({"label": "This month", "title": "Find out why AI leads close *less* often",
                         "body": "%s of AI leads became customers against %s from %s. Compare what the cited page "
                                 "promises with what you offer on the first call." % (pct(cra), pct(crb), _lname(base_label)),
                         "impact": "Medium", "effort": "Low"})
        elif ca and cb and ra / float(la) <= 0.6 * rb / float(lb):
            recs.append({"label": "This quarter", "title": "Point assistants at your *bigger* services",
                         "body": "AI leads bring %s each against %s from %s; their average sale is %s against %s. "
                                 "Write clear answer pages for your higher-value services so assistants cite those "
                                 "too." % (_money(ra / float(la)), _money(rb / float(lb)), _lname(base_label),
                                           _money(ra / float(ca)), _money(rb / float(cb))),
                         "impact": "High", "effort": "Medium"})
    if not has_faq:
        recs.append({"label": "This quarter", "title": "Publish a *pricing and FAQ* page",
                     "body": "Not one of the %s pages that brought leads is a pricing or FAQ page. Assistants answer "
                             "cost and how-to questions; a page with real numbers gives them something to cite." %
                             n(len(lp_paths)), "impact": "High", "effort": "Medium"})
    recs.append({"label": "Monthly", "title": "Check what *%s* says about you" % top_ai,
                 "body": "%s sent %s of %s AI leads. Ask it, and the next two assistants, your customers' top three "
                         "questions each month and note whether you are named and which page is cited." % (
                             top_ai, n(top_n), n(n_ai)), "impact": "Medium", "effort": "Low"})
    if len(started) >= 5:
        recs.append({"label": "Reporting", "title": "Credit AI for the *journeys* it starts",
                     "body": "%s more leads first found you through an AI assistant and converted later through "
                             "another channel. Count them when you judge what AI is worth." % n(len(started)),
                     "impact": "Medium", "effort": "Low"})
    secs.append({"type": "section-header", "number": "%02d" % nxt, "kicker": "Next steps",
                 "title": "Make your pages easy for *AI assistants* to cite."})
    secs.append({"type": "recommendations", "items": recs[:4]})

    how = Counter(h for _e, _a, h in ai)
    notes = ["AI leads: the converting visit came from an AI assistant (%s), read from %s's organic source and "
             "referrer domain fields and from utm_source tags such as chatgpt.com." % (", ".join(sorted(by_ai)), PREMIUM),
             "Found through: %s." % ", ".join("%s (%s)" % (h, n(v)) for h, v in how.most_common()),
             "Share of organic: AI leads divided by the %s leads whose last touch was unpaid search or an AI assistant." %
             n(len(organic))]
    if started:
        notes.append("AI-started journeys: the first visit (%s's first-touch fields) came from an AI assistant and "
                     "the lead converted later through another channel." % PREMIUM)
    if q_note:
        notes.append(q_note)
    notes.append("Some assistant apps pass no referrer, so their visits look direct. Treat these counts as a floor.")
    secs.append({"type": "notes", "title": "How we built this report", "items": notes})
    secs.append({"type": "closing", "kicker": "AI referrals in one line",
                 "title": "Next: put clear answers on *%s*. It took %s of your AI leads." % (
                     "your home page" if top_page == "/" else _safe(top_page, 32), n(top_page_n)),
                 "summary_stats": [{"value": n(n_ai), "label": "AI leads"},
                                   {"value": pct(ai_share, 1 if ai_share < 10 else 0), "label": "Share of leads"},
                                   {"value": top_ai, "label": "Top assistant"},
                                   ({"value": n(len(started)), "label": "AI-started journeys"} if started else
                                    {"value": pct(org_share), "label": "Share of organic"})],
                 "bullets": [x for x in [
                     ("%s against %s in %s." % (_pl(n_ai, "AI lead"), n(len(prior_ai)), cmp_)) if has_prior else None,
                     "%s sent the most: %s." % (top_ai, _pl(top_n, "lead")),
                     "Top page: %s, with %s." % (_safe(_pname(top_page), 40), _pl(top_page_n, "AI lead"))] if x]})
    return {"meta": m, "sections": secs}


def _ai_free(m, kicker, leads, ai, bits):
    """Free-plugin data: say what Premium adds and show what utm tags alone found."""
    total, n_ai = len(leads), len(ai)
    why = ["These entries carry no organic source or referrer domain fields. That is where %s records visits from "
           "ChatGPT, Perplexity, Gemini, Claude and Copilot." % PREMIUM,
           "We checked utm_source tags and landing page URLs instead. ChatGPT adds utm_source=chatgpt.com to most "
           "links it shows; the other assistants rarely tag theirs. We found %s this way." % _pl(n_ai, "lead")]
    stats = [stat("Leads checked", n(total)), stat("AI leads from tags", n(n_ai), good="neutral",
                                                   note="utm_source or landing page tag")]
    extra = []
    if ai:
        stats.append(stat("Share of leads", pct(share(n_ai, total), 1), good="neutral"))
        extra.append(_lead_table([e for e, _a, _h in ai], "AI leads found in *tags*", assistant=True))
        title = "UTM tags found *%s* from AI assistants." % _pl(n_ai, "lead")
        sub = "That counts only links the assistant tagged. %s sees every assistant visit, tagged or not." % PREMIUM
    else:
        title = "See which *AI assistants* send you leads."
        sub = "AI-assistant detection needs %s. Here is what UTM tags alone can show." % PREMIUM
    return _short(m, kicker, title, "AI-assistant detection needs *%s*." % PREMIUM, why, subtitle=sub,
                  stats=stats, extra=extra, bits=bits,
                  close_title="Next: turn on *%s* and run this again in 30 days." % PREMIUM,
                  close_body="Every visit from an AI assistant is then recorded on the lead, with the assistant's name "
                             "and the page it sent them to.")


def _ai_none(m, kicker, leads, bits, period):
    total = len(leads)
    organic = sum(1 for e in leads if last_touch(e) == "Organic")
    pages = Counter(_page(e) or "(not recorded)" for e in leads if last_touch(e) == "Organic")
    top = pages.most_common(1)[0] if pages else None
    why = ["%s recorded the source of all %s leads, and not one converting visit came from ChatGPT, Perplexity, "
           "Gemini, Claude or Copilot." % (PREMIUM, n(total)),
           "Assistants cite pages that answer a question plainly. Unpaid search sent %s leads%s, so the content is "
           "there to build on." % (n(organic), (", most to %s" % _pname(top[0])) if top else "")]
    page_name = ("your home page" if top[0] == "/" else _safe(top[0], 32)) if top and top[0] != "(not recorded)" \
        else "your top page"
    recs = [{"label": "This month", "title": "Add clear answers and prices to *%s*" % page_name,
             "body": "Assistants quote pages that answer the question in the first lines: what it costs, how long it "
                     "takes, who it is for.", "impact": "High", "effort": "Medium"},
            {"label": "Monthly", "title": "Ask *ChatGPT* the questions your customers ask",
             "body": "Note whether you are named and which page is cited. That shows what to fix before any lead "
                     "arrives this way.", "impact": "Medium", "effort": "Low"}]
    return _short(m, kicker, "Be the business *AI assistants* recommend next.",
                  "No *AI assistant* sent a lead %s." % ("in %s" % period if period else "this period"), why,
                  subtitle="%s found no leads from AI assistants yet. Here is how to earn the first ones." % PREMIUM,
                  stats=[stat("Leads checked", n(total)), stat("AI leads", "0", good="neutral"),
                         stat("Unpaid search leads", n(organic), good="neutral")],
                  extra=[{"type": "recommendations", "items": recs}], bits=bits,
                  close_title="Next: add clear answers to *%s* and run this again next month." % page_name,
                  close_body="This report fills in as soon as the first AI-referred lead arrives.")


def _ai_few(m, kicker, leads, ai, organic, started, bits, cmp_, prior_ai):
    total, n_ai = len(leads), len(ai)
    by_ai = Counter(a for _e, a, _h in ai)
    top_ai, top_n = by_ai.most_common(1)[0]
    top_page = Counter(_ai_page(e) for e, _a, _h in ai).most_common(1)[0][0]
    why = ["%s came from AI assistants: %s." % (_cap(_pl(n_ai, "lead")),
                                               ", ".join("%s %s" % (a, n(v)) for a, v in by_ai.most_common())),
           "Below 10 AI leads a breakdown by page or quality would be noise, so this version lists them instead."]
    if started:
        why.append("Assistants also started %s that converted through another channel." %
                   _pl(len(started), "more journey", "more journeys"))
    stats = [stat("AI leads", n(n_ai), n_ai, len(prior_ai) if prior_ai else None,
                  note=("%s in %s" % (n(len(prior_ai)), cmp_)) if prior_ai is not None else None),
             stat("Share of all leads", pct(share(n_ai, total), 1), good="neutral"),
             stat("Share of organic", pct(share(n_ai, len(organic))), good="neutral")]
    if started:
        stats.append(stat("AI-started journeys", n(len(started)), good="neutral"))
    return _short(m, kicker, "*%s* sent your first AI-assistant leads." % top_ai if top_n == n_ai else
                  "*AI assistants* sent %s this period." % _pl(n_ai, "lead"),
                  "Ten AI leads unlock the full *breakdown*.", why,
                  subtitle="%s sent %s of %s." % (top_ai, n(top_n), _pl(n_ai, "AI lead")),
                  stats=stats, extra=[_lead_table([e for e, _a, _h in ai], "Every *AI lead* this period", assistant=True)],
                  bits=bits,
                  close_title="Next: add clear answers to *%s* and watch this number." % (
                      "your home page" if top_page == "/" else _safe(top_page, 32)),
                  close_body="Assistants cite pages that answer a question plainly: price, timing, who it is for.")


# ===========================================================================
# 2. CUSTOMER JOURNEYS (first touch to last touch)
# ===========================================================================
def build_journey(leads, prior=None, deal_rows=None, orders=None, brand_profile=None, customer_name=None,
                  customer_domain="", compare_label=None, form_label=None, prepared_by=None, prepared_for=None, **_):
    """First touch to last touch: which channels open journeys, which close them, and fair credit per channel."""
    name = "Customer journeys"
    leads, prior = list(leads or []), list(prior or [])
    start, end = span(leads)
    pstart, pend = span(prior) if prior else (None, None)
    m = _meta(brand_profile, customer_name, customer_domain,
              compare_label or (prior_name(pstart, pend) if prior else "last period"), prepared_by, prepared_for)
    if not leads:
        return empty_report(name, m)
    if start is None:
        return _undated(name, m, leads)
    period = period_label(start, end)
    kicker = "%s · %s" % (name, period)
    total = len(leads)
    days = (end - start).days + 1
    bits = [customer_domain, form_label, "%s submissions" % n(total), _pl(days, "day")]
    cmp_ = m["compare_label"]
    if total < MIN_LEADS:
        return _thin(name, m, leads, period)
    J = [e for e in leads if has_ft(e)]
    nJ = len(J)
    deals = _deals(deal_rows)
    sales = [s for s in _sales_from_orders(orders) if not s["refunded"] and not s["void"]] if orders else []
    chips = {"utmg": "%s leads" % n(total)}
    if sales:
        chips["woocommerce"] = "%s orders" % n(len(sales))
    elif deals:
        chips["CRM"] = "%s deals" % n(len(deals))
    m["sources"] = sources_meta(**chips)
    if nJ < MIN_LEADS:
        return _journey_free(m, kicker, leads, nJ, bits)

    pairs = [(ft_group(e), lt_group(e)) for e in J]
    F = Counter(a for a, _b in pairs)
    L = Counter(b for _a, b in pairs)
    groups = _gsort(set(F) | set(L), lambda x: F[x] + L[x])
    switched = sum(1 for a, b in pairs if a != b)
    sw_share = share(switched, nJ)
    Jp = [e for e in prior if has_ft(e)]
    sw_prior = share(sum(1 for e in Jp if ft_group(e) != lt_group(e)), len(Jp)) if len(Jp) >= MIN_LEADS else None
    under = max(groups, key=lambda x: (F[x] - L[x], F[x]))
    over = min(groups, key=lambda x: (F[x] - L[x], -L[x]))
    top_open = max(groups, key=lambda x: (F[x], -GROUP_ORDER.index(x) if x in GROUP_ORDER else 0))
    top_close = max(groups, key=lambda x: (L[x], -GROUP_ORDER.index(x) if x in GROUP_ORDER else 0))
    closed_elsewhere = sum(1 for a, b in pairs if b == top_close and a != top_close)
    gap = F[under] - L[under]
    real_gap = gap >= 3 and gap >= 0.1 * max(L[under], 1)

    # revenue credit: orders carry their own first touch; won deals borrow the lead's
    rev_pairs, rev_src = [], None
    if sales:
        rev_pairs = [(s["ft"], s["lt"], s["total"]) for s in sales if s["ft"]]
        rev_src = "%s WooCommerce orders" % n(len(rev_pairs))
    elif deals:
        matched, _un = join_deals_to_leads([dl for dl in deals if dl.get("stage") == "won"], J)
        rev_pairs = [(ft_group(x["lead"]), lt_group(x["lead"]), x["deal"].get("amount") or 0.0) for x in matched]
        rev_src = "%s won CRM deals matched to these leads by email" % n(len(rev_pairs))
    has_rev = len(rev_pairs) >= 5 and sum(v for _a, _b, v in rev_pairs) > 0

    # headline
    if real_gap:
        headline = "*%s* %s %s but %s only %s." % (under, _v(under, "opens", "open"), _pl(F[under], "journey"),
                                                   _v(under, "closes", "close"), n(L[under]))
    else:
        headline = "Most leads *convert* on the channel that first found them."
    sub = ["%s of leads converted on a different channel than their first visit." % pct(sw_share)]
    if closed_elsewhere and top_close != under:
        sub.append("%s closed the most (%s), and %s of those started elsewhere." % (
            top_close, n(L[top_close]), n(closed_elsewhere)))
    stats = [stat("Leads traced", n(nJ), note=("every lead carries first-touch data" if nJ == total else
                                                "%s of %s leads carry first-touch data" % (n(nJ), n(total)))),
             stat("Changed channel", pct(sw_share), sw_share, sw_prior, kind="pts", good="neutral",
                  note="%s converted elsewhere" % _pl(switched, "lead")),
             stat("Top opener", top_open, good="neutral", note="%s first visits" % n(F[top_open])),
             stat("Top closer", top_close, good="neutral", note="%s converting visits" % n(L[top_close]))]
    if has_rev:
        stats.append(stat("Revenue traced", money(sum(v for _a, _b, v in rev_pairs)), good="neutral",
                          note="from %s" % (_pl(len(rev_pairs), "order") if sales else _pl(len(rev_pairs), "won deal"))))
    secs = [{"type": "title-block", "kicker": kicker, "title": headline, "subtitle": " ".join(sub),
             "meta_bits": [b for b in bits if b]},
            {"type": "stat-strip", "stats": stats}]
    if real_gap:
        body = ["%s was the first visit for %s leads and the converting visit for %s. Split 50/50 between the two "
                "touches, it earns %s." % (under, n(F[under]), n(L[under]), n(0.5 * F[under] + 0.5 * L[under]))]
        if over != under and L[over] - F[over] >= 3:
            body.append("%s %s the other way: %s %s and %s %s, so last click flatters %s." % (
                over, _v(over, "works", "work"), _v(over, "it closes", "they close"), n(L[over]),
                _v(over, "opens", "open"), n(F[over]), _v(over, "it", "them")))
        secs.append({"type": "insight-card", "kicker": "The takeaway",
                     "title": "Last click undervalues *%s* by %s." % (under, _pl(gap, "lead")), "body": body})

    # 01 paths
    keep, folded = _fold(groups, 6)
    fold = lambda x: folded.get(x, x)  # noqa: E731
    links = Counter((fold(a), fold(b)) for a, b in pairs)
    Ff, Lf = Counter(), Counter()
    for (a, b), v in links.items():
        Ff[a] += v
        Lf[b] += v
    lorder = _gsort([x for x in Ff], lambda x: Ff[x] if x != "Other" else -1)
    rorder = _gsort([x for x in Lf], lambda x: Lf[x] if x != "Other" else -1)
    secs.append({"type": "section-header", "number": "01", "kicker": "The paths",
                 "title": "How people *move* from first visit to form.",
                 "dek": "Left: the channel of each lead's first visit. Right: the visit that converted."})
    secs.append({"type": "flow", "chart_title": "From first visit to *form*", "left_title": "First visit",
                 "right_title": "Converting visit",
                 "links": [{"from": a, "to": b, "value": v} for (a, b), v in sorted(links.items(), key=lambda x: -x[1])],
                 "left_order": lorder, "right_order": rorder,
                 "caption": "%s traced leads. Bands that cross changed channel on the way.%s" % (
                     n(nJ), (" Other: %s." % ", ".join(sorted(folded))) if folded else "")})

    # 02 openers vs closers
    cats = [x for x in _gsort(set(Ff) | set(Lf), lambda x: Ff[x] + Lf[x] if x != "Other" else -1)]
    ins = ["%s opened %s journeys and closed %s." % (under, n(F[under]), n(L[under])) if real_gap else
           "No channel opens many more journeys than it closes."]
    if top_close != under:
        ins.append("%s closed %s; %s of them started on another channel." % (top_close, n(L[top_close]),
                                                                           n(closed_elsewhere)))
    secs.append({"type": "section-header", "number": "02", "kicker": "Openers vs closers",
                 "title": "Which channels *open* and which close."})
    # full width: six channel names don't fit under a chart in the narrower chart-insight slot
    secs.append({"type": "chart",
                 "chart": {"type": "bar-grouped", "labels": cats,
                           "groups": [{"label": "First touch", "values": [Ff[c] for c in cats]},
                                      {"label": "Last touch", "values": [Lf[c] for c in cats]}]},
                 "chart_title": "First touch against last touch, by *channel*",
                 "caption": "Leads credited to each channel by first touch and by last touch"})
    secs.append({"type": "insight-card", "kicker": "Openers vs closers",
                 "title": ("*%s* %s more journeys than %s credit for." % (
                     under, _v(under, "starts", "start"), _v(under, "it gets", "they get"))) if real_gap else
                 "Openers and closers are *balanced*.",
                 "body": ins})

    # 03 fair credit
    def credit_rows(fc, lc, fmt_v, total_v, hl=None):
        rows = []
        for gname in _gsort(set(fc) | set(lc), lambda x: fc.get(x, 0) + lc.get(x, 0)):
            a, b = fc.get(gname, 0), lc.get(gname, 0)
            sp_ = 0.5 * a + 0.5 * b
            diff = sp_ - b
            thr = max(0.1 * max(b, 1), 0.01 * total_v, 1)
            verdict = ({"label": "Undervalued", "tone": "brand"} if diff >= thr else
                       {"label": "Overcredited", "tone": "warn"} if -diff >= thr else
                       {"label": "Even", "tone": "neutral"})
            if abs(diff) < 0.5 and fmt_v is n:
                dcell = {"label": "0", "direction": "flat"}
            else:
                dcell = {"label": ("+" if diff > 0 else (MINUS if diff < 0 else "")) + fmt_v(abs(diff)),
                         "direction": "up" if diff > 0 else ("down" if diff < 0 else "flat")}
            rows.append({"ch": gname, "ft": {"value": a, "label": fmt_v(a)}, "lt": fmt_v(b), "split": fmt_v(sp_),
                         "diff": dcell, "verdict": verdict, "_highlight": gname == hl})
        return rows[:MAX_ROWS]

    cols = [{"key": "ch", "label": "Channel", "type": "name"},
            {"key": "ft", "label": "First touch", "type": "bar"},
            {"key": "lt", "label": "Last touch", "type": "number", "align": "right"},
            {"key": "split", "label": "50/50 split", "type": "number", "align": "right"},
            {"key": "diff", "label": "Split vs last", "type": "delta", "align": "right"},
            {"key": "verdict", "label": "Last click", "type": "badge"}]
    secs.append({"type": "section-header", "number": "03", "kicker": "Fair credit",
                 "title": "Credit per *channel*, three ways.",
                 "dek": "First touch credits the opener, last touch the closer, the 50/50 split shares each lead "
                        "between them."})
    secs.append({"type": "ranked-list", "title": "Lead credit by *channel*", "columns": cols,
                 "rows": credit_rows(F, L, n, nJ, under if real_gap else None),
                 "totals": {"ch": "Total", "ft": n(nJ), "lt": n(nJ), "split": n(nJ), "diff": "", "verdict": ""},
                 "caption": "Undervalued: the 50/50 split gives the channel more credit than last click does."})
    rev_under = None
    if has_rev:
        RF, RL = defaultdict(float), defaultdict(float)
        for a, b, v in rev_pairs:
            RF[a] += v
            RL[b] += v
        rtot = sum(v for _a, _b, v in rev_pairs)
        rev_under = max(set(RF) | set(RL), key=lambda x: RF[x] - RL[x])
        secs.append({"type": "ranked-list", "title": "Revenue credit by *channel*", "columns": cols,
                     "rows": credit_rows(RF, RL, _money, rtot, rev_under if RF[rev_under] > RL[rev_under] else None),
                     "totals": {"ch": "Total", "ft": money(rtot), "lt": money(rtot), "split": money(rtot), "diff": "",
                                "verdict": ""},
                     "caption": "Revenue from %s, credited the same three ways." % rev_src})

    # next steps
    recs = []
    if real_gap:
        to_close = Counter(b for a, b in pairs if a == under and b != under).most_common(1)
        if under in PAID_GROUPS:
            recs.append({"label": "Budget", "title": "Keep *%s* funded on first-touch numbers" % under,
                         "body": "It opened %s journeys and closed %s. %s" % (
                             n(F[under]), n(L[under]),
                             ("%s of the journeys it opened closed through %s, so cutting it would likely shrink "
                              "%s later." % (n(to_close[0][1]), _low(to_close[0][0]), _low(to_close[0][0]))) if to_close else
                             "Judge it on the journeys it starts."), "impact": "High", "effort": "Low"})
        recs.append({"label": "Reporting", "title": "Judge *%s* on first touch, not last click" % under,
                     "body": "Last click gives %s %s leads; the 50/50 split gives %s %s. Report both so budget follows "
                             "the channel that finds people." % (_v(under, "it", "them"), n(L[under]),
                                                                 _v(under, "it", "them"),
                                                                 n(0.5 * F[under] + 0.5 * L[under])),
                     "impact": "High", "effort": "Low"})
    if top_close != under and closed_elsewhere >= 5:
        recs.append({"label": "Budget", "title": "Keep *%s* as the closer, and fund its openers" % top_close,
                     "body": "It closed %s journeys; %s of them started on another channel. Its results depend on the "
                             "channels that bring people in first." % (n(L[top_close]), n(closed_elsewhere)),
                     "impact": "Medium", "effort": "Low"})
    if G_AI in F and F[G_AI] - L.get(G_AI, 0) >= 5 and under != G_AI:
        recs.append({"label": "Content", "title": "Count *AI assistants* as an opener",
                     "body": "They were the first visit for %s leads and the converting visit for %s. Pages that "
                             "answer questions clearly keep them recommending you." % (n(F[G_AI]), n(L.get(G_AI, 0))),
                     "impact": "Medium", "effort": "Medium"})
    if has_rev and rev_under and rev_under != under and RF[rev_under] > RL[rev_under]:
        recs.append({"label": "Revenue", "title": "Credit *%s* for the revenue %s" % (
            rev_under, _v(rev_under, "it finds", "they find")),
                     "body": "By first touch %s %s of revenue; last click gives %s %s." % (
                         _v(rev_under, "it found", "they found"), _money(RF[rev_under]), _v(rev_under, "it", "them"),
                         _money(RL[rev_under])), "impact": "Medium", "effort": "Low"})
    recs.append({"label": "Ongoing", "title": "Review *both touches* every month",
                 "body": "%s of leads changed channel between first visit and form. Track first and last touch side "
                         "by side so budget follows the opener too." % pct(sw_share), "impact": "Medium", "effort": "Low"})
    secs.append({"type": "section-header", "number": "04", "kicker": "Next steps",
                 "title": "Give every *channel* fair credit."})
    secs.append({"type": "recommendations", "items": recs[:4]})
    notes = ["First touch: the first visit %s recorded for the person (first-touch source, medium, referrer and "
             "landing page). Last touch: the visit that converted." % PREMIUM,
             "50/50 split: each lead gives half its credit to its first-touch channel and half to its last-touch "
             "channel; a lead that stayed on one channel gives that channel full credit.",
             "Channels: %s." % "; ".join("%s is %s" % (gname, GROUP_DEF[gname]) for gname in groups if gname in GROUP_DEF)]
    if nJ < total:
        notes.append("%s leads without first-touch data are left out." % n(total - nJ))
    if has_rev:
        notes.append("Revenue: %s." % rev_src)
    secs.append({"type": "notes", "title": "How we built this report", "items": notes})
    if real_gap:
        ctitle = "Next: judge *%s* on first touch. It opens %s journeys and closes %s." % (under, n(F[under]), n(L[under]))
    else:
        ctitle = "Next: keep *%s* strong. It closes %s of your leads." % (top_close, pct(share(L[top_close], nJ)))
    secs.append({"type": "closing", "kicker": "Journeys in one line", "title": ctitle,
                 "summary_stats": [{"value": n(nJ), "label": "Leads traced"},
                                   {"value": pct(sw_share), "label": "Changed channel"},
                                   {"value": top_open, "label": "Top opener"},
                                   {"value": top_close, "label": "Top closer"}],
                 "bullets": [x for x in [
                     ("Changed-channel share moved from %s in %s to %s." % (pct(sw_prior), cmp_, pct(sw_share)))
                     if sw_prior is not None else None,
                     ("Most undervalued by last click: %s (%s)." % (under, _sn(gap))) if real_gap else None,
                     "%s closed the most journeys: %s." % (top_close, n(L[top_close]))] if x]})
    return {"meta": m, "sections": secs}


def _journey_free(m, kicker, leads, nJ, bits):
    total = len(leads)
    L = Counter(lt_group(e) for e in leads)
    order = _gsort(L, lambda x: L[x])
    top = order[0]
    why = ["%s leads carry only last-touch data: the visit that converted. %s also records each person's first "
           "visit, so this report can show which channels open journeys and which close them." % (
               "These" if not nJ else "%s of these %s" % (n(total - nJ), n(total)), PREMIUM),
           "Until then, every channel is judged on last click, which favors the channels that close (brand search, "
           "direct) over the ones that find people."]
    chart = {"type": "chart",
             "chart": {"type": "bar-horizontal", "labels": order[:8], "values": [L[x] for x in order[:8]],
                       "x_title": "Leads", "highlight": 0, "total": total},
             "chart_title": "What last click shows *today*",
             "caption": "Leads by the channel of the converting visit."}
    return _short(m, kicker, "Trace every lead back to its *first visit*.",
                  "First-touch data needs *%s*." % PREMIUM, why,
                  subtitle="Today's data shows the last touch only: %s closes the most (%s of leads)." % (
                      top, pct(share(L[top], total))),
                  stats=[stat("Leads", n(total)), stat("With first touch", n(nJ), good="neutral"),
                         stat("Top last touch", top, good="neutral", note="%s leads" % n(L[top]))],
                  extra=[chart], bits=bits,
                  close_title="Next: turn on *%s* first-touch tracking, then run this again in 30 days." % PREMIUM,
                  close_body="New leads will carry both touches from the day it is on.")


# ===========================================================================
# 3. REVENUE BY SOURCE
# ===========================================================================
def build_revenue(orders, prior_orders=None, ad_rows=None, leads=None, deal_rows=None, brand_profile=None,
                  customer_name=None, customer_domain="", compare_label=None, form_label=None, prepared_by=None,
                  prepared_for=None, ad_rows_prior=None, deal_rows_prior=None, leads_prior=None, **_):
    """Revenue, orders and order value by channel, campaign and product; first vs last touch; ROAS."""
    name = "Revenue by source"
    sales = _sales_from_orders(orders) if orders else []
    mode = "orders"
    if not sales and deal_rows and leads:
        sales = _sales_from_deals(deal_rows, list(leads or []) + list(leads_prior or []))
        mode = "deals"
    if mode == "orders":
        sales_p = _sales_from_orders(prior_orders) if prior_orders else []
    else:
        sales_p = _sales_from_deals(deal_rows_prior, list(leads or []) + list(leads_prior or [])) if deal_rows_prior else []
    dated = [s for s in sales if s["date"]]
    start = min(s["date"] for s in dated) if dated else None
    end = max(s["date"] for s in dated) if dated else None
    pdated = [s for s in sales_p if s["date"]]
    pstart = min(s["date"] for s in pdated) if pdated else None
    pend = max(s["date"] for s in pdated) if pdated else None
    m = _meta(brand_profile, customer_name, customer_domain,
              compare_label or (prior_name(pstart, pend) if pdated else "last period"), prepared_by, prepared_for)
    if not sales:
        lead_n = len(leads or [])
        m["sources"] = sources_meta(utmg=("%s leads" % n(lead_n)) if lead_n else None)
        return _short(m, name, "Connect your store to see *revenue* by source.",
                      "Revenue needs *orders* or won deals.",
                      ["No WooCommerce orders or won CRM deals came in with this request, so there is no revenue to "
                       "credit.", "%s records the source of every WooCommerce order. Without a store, connect your "
                       "CRM so won deals can be matched to leads by email." % PREMIUM],
                      subtitle="This report credits every sale to the channel, campaign and ad behind it.",
                      why_kicker="Why this report is empty",
                      close_title="Next: connect *WooCommerce* or your CRM, then run this again.",
                      close_body="As soon as orders or won deals arrive, this report fills itself in.",
                      bits=[customer_domain])
    if start is None:
        m["sources"] = sources_meta(woocommerce=_pl(len(sales), "order") if mode == "orders" else None,
                                    CRM=_pl(len(sales), "won deal") if mode == "deals" else None)
        return _short(m, name, "We couldn't read the *dates* on these sales.", "We need a *date* on every sale.",
                      ["Not one of the %s sales carried a readable date." % n(len(sales)),
                       "Pull the orders again with their order dates."],
                      close_title="Next: re-pull the orders with their *dates* and run this again.", bits=[customer_domain])
    period = period_label(start, end)
    kicker = "%s · %s" % (name, period)
    days = (end - start).days + 1
    cmp_ = m["compare_label"]
    noun, nouns = ("order", "orders") if mode == "orders" else ("won deal", "won deals")
    good = [s for s in sales if not s["refunded"] and not s["void"]]
    refunds = [s for s in sales if s["refunded"]]
    good_p = [s for s in sales_p if not s["refunded"] and not s["void"]]
    refunds_p = [s for s in sales_p if s["refunded"]]
    rev = sum(s["total"] for s in good)
    rev_p = sum(s["total"] for s in good_p)
    has_prior = len(good_p) >= MIN_LEADS
    k = len(good)
    aov = rev / k if k else 0.0
    aov_p = rev_p / len(good_p) if good_p else None
    ads = _ads_in(_ads(ad_rows), start, end)
    spend = round(sum(r.get("spend", 0.0) for r in ads), 2)
    ads_p = _ads(ad_rows_prior)
    if pdated:
        ads_p = _ads_in(ads_p, pstart, pend)
    spend_p = round(sum(r.get("spend", 0.0) for r in ads_p), 2)
    ad_plats = set(_ad_platform(r.get("platform")) for r in ads if r.get("spend", 0) > 0)
    known = ad_plats & set(["Google Ads", "Meta Ads", "Microsoft Ads", "LinkedIn Ads", "TikTok Ads"])

    def paid_rev(rows, plats):
        if plats:
            return sum(s["total"] for s in rows if s["platform"] in plats)
        return sum(s["total"] for s in rows if s["lt"] in PAID_GROUPS)

    ad_rev = paid_rev(good, known)
    roas = ad_rev / spend if spend > 0 else None
    roas_p = (paid_rev(good_p, set(_ad_platform(r.get("platform")) for r in ads_p) & known) / spend_p
              if spend_p > 0 and has_prior else None)
    chips = {}
    if mode == "orders":
        chips["woocommerce"] = "%s orders" % n(len(sales))
    else:
        chips["utmg"] = "%s leads" % n(len(leads or []))
        chips["CRM"] = "%s won deals" % n(len(sales))
    for plat, v in _spend_sources(ads):
        chips[_PLATFORM_KEYS.get(plat, plat)] = "%s spend" % money(v)
    m["sources"] = sources_meta(**chips)
    bits = [customer_domain, form_label, _pl(len(sales), noun), _pl(days, "day")]
    if k < MIN_LEADS:
        return _revenue_thin(m, kicker, good, refunds, rev, noun, nouns, bits)

    # by channel and campaign
    by_g, cnt_g = defaultdict(float), Counter()
    for s in good:
        by_g[s["lt"]] += s["total"]
        cnt_g[s["lt"]] += 1
    gorder = _gsort(by_g, lambda x: by_g[x])
    top_g = gorder[0]
    by_c, cnt_c = defaultdict(float), Counter()
    by_cp = defaultdict(float)
    for s in good:
        by_c[s["campaign"]] += s["total"]
        cnt_c[s["campaign"]] += 1
    for s in good_p:
        by_cp[s["campaign"]] += s["total"]
    untag = by_c.get("", 0.0)
    camps = sorted([c for c in by_c if c], key=lambda c: -by_c[c])
    labels = _day_labels(start, end)
    daily_rev = _daily(good, start, end, lambda s: s["date"], lambda s: s["total"])
    daily_k = _daily(good, start, end, lambda s: s["date"])
    peak_i = max(range(len(daily_rev)), key=lambda i: daily_rev[i])

    # headline
    d = delta(rev, rev_p) if has_prior else {}
    when = end.strftime("%B") if is_full_month(start, end) else "This period"
    if d.get("delta_direction") == "up":
        headline = "%s brought *%s* in revenue, %s more than %s." % (when, money(rev), d["delta_label"].lstrip("+"), cmp_)
    elif d.get("delta_direction") == "down":
        headline = "%s brought *%s* in revenue, %s less than %s." % (when, money(rev), d["delta_label"].lstrip(MINUS), cmp_)
    elif has_prior:
        headline = "%s held revenue steady at *%s*." % (when, money(rev))
    else:
        headline = "%s brought *%s* in revenue from %s." % (when, money(rev), _pl(k, noun))
    sub = ["%s brought the most (%s)." % (top_g, pct(share(by_g[top_g], rev)))]
    if camps:
        sub.append("%s was the top campaign at %s." % (pretty(camps[0]), money(by_c[camps[0]])))
    if roas is not None:
        sub.append("Ad spend of %s returned %s in ad-click revenue." % (money(spend), ratio(roas)))

    # KPIs
    weeks7 = []
    if roas is not None and days >= 14:
        sp_daily = _daily(ads, start, end, lambda r: _d(r.get("date")), lambda r: r.get("spend", 0.0))
        rv_daily = _daily([s for s in good if (s["platform"] in known if known else s["lt"] in PAID_GROUPS)],
                          start, end, lambda s: s["date"], lambda s: s["total"])
        for i in range(6, len(sp_daily)):
            sp7 = sum(sp_daily[i - 6:i + 1])
            weeks7.append(round(sum(rv_daily[i - 6:i + 1]) / sp7, 2) if sp7 else 0.0)
    aov_spark = []
    for i in range(6, len(daily_k)):
        kk = sum(daily_k[i - 6:i + 1])
        aov_spark.append(round(sum(daily_rev[i - 6:i + 1]) / kk, 2) if kk else 0.0)
    stats = [stat("Revenue", money(rev), rev, rev_p if has_prior else None, spark=[round(x, 2) for x in daily_rev],
                  source="WooCommerce" if mode == "orders" else "CRM",
                  note=("%s in %s" % (money(rev_p), cmp_)) if has_prior else "%s a day" % money(rev / days)),
             stat(_cap(nouns), n(k), k, len(good_p) if has_prior else None, spark=daily_k,
                  note=("%s in %s" % (n(len(good_p)), cmp_)) if has_prior else "%.1f a day" % (k / float(days))),
             stat("Average %s value" % ("order" if mode == "orders" else "deal"), money(aov), aov,
                  aov_p if has_prior else None, spark=aov_spark or None)]
    if mode == "orders":
        rf = sum(s["total"] for s in refunds)
        rf_p = sum(s["total"] for s in refunds_p)
        stats.append(stat("Refunds", money(rf), rf, rf_p if has_prior else None, good="down",
                          note="%s, %s of %s" % (_pl(len(refunds), "order"),
                                                  pct(share(len(refunds), len(refunds) + k), 1), nouns)))
    if roas is not None:
        stats.append(stat("Return on ad spend", ratio(roas), roas, roas_p, kind="abs", unit_fmt=ratio,
                          spark=weeks7 or None,
                          note="%s ad-click revenue on %s spend" % (money(ad_rev), money(spend))))
    secs = [{"type": "title-block", "kicker": kicker, "title": headline, "subtitle": " ".join(sub),
             "meta_bits": [b for b in bits if b]},
            {"type": "stat-strip", "stats": stats}]
    second = gorder[1] if len(gorder) > 1 else None
    body = ["It took %s at an average of %s." % (_pl(cnt_g[top_g], noun), money(by_g[top_g] / cnt_g[top_g]))]
    if second:
        body.append("%s followed with %s (%s)." % (second, money(by_g[second]), pct(share(by_g[second], rev))))
    if untag >= 0.1 * rev:
        body.append("%s (%s) came from %s with no campaign tag." % (money(untag), pct(share(untag, rev)), nouns))
    secs.append({"type": "insight-card", "kicker": "The takeaway",
                 "title": "*%s* earned %s, %s of revenue." % (top_g, money(by_g[top_g]), pct(share(by_g[top_g], rev))),
                 "body": body})

    # 01 by channel
    rows_g = gorder[:8]
    real_g = [x for x in gorder if x != "No form lead"] or gorder
    best_aov = max([x for x in real_g if cnt_g[x] >= 5] or real_g, key=lambda x: by_g[x] / cnt_g[x])
    secs.append({"type": "section-header", "number": "01", "kicker": "By channel",
                 "title": "Where the *revenue* comes from.",
                 "dek": "Each %s credited to the channel of the visit that %s." % (
                     noun, "bought" if mode == "orders" else "became the lead")})
    secs.append({"type": "chart-insight",
                 "chart": {"type": "bar-horizontal", "labels": rows_g, "values": [round(by_g[x], 2) for x in rows_g],
                           "unit": "$", "x_title": "Revenue", "highlight": 0, "total": rev,
                           "notes": ["%s, %s avg" % (_pl(cnt_g[x], noun), money(by_g[x] / cnt_g[x])) for x in rows_g]},
                 "caption": "Revenue by last-touch channel",
                 "insight_kicker": "Order value",
                 "insight_title": "*%s* buyers spend the most: %s per %s." % (
                     best_aov, money(by_g[best_aov] / cnt_g[best_aov]), noun),
                 "insight_body": ["That is against %s across all %s." % (money(aov), nouns),
                                  "%s brought the most revenue overall: %s." % (top_g, money(by_g[top_g]))]})

    # 02 by campaign
    nxt = 2
    if camps:
        rows_c = []
        for i, c in enumerate(camps[:8]):
            v = by_c[c]
            rows_c.append({"rank": str(i + 1), "campaign": _safe(pretty(c), 40), "tag": _safe(c, 40),
                           "rev": {"value": round(v, 2), "label": money(v)}, "orders": n(cnt_c[c]),
                           "aov": money(v / cnt_c[c]), "share": pct(share(v, rev)),
                           "change": _delta_cell(v, by_cp.get(c, 0.0)) if has_prior else {"label": "–", "direction": "flat"}})
        secs.append({"type": "section-header", "number": "02", "kicker": "By campaign",
                     "title": "The *campaigns* that sold."})
        secs.append({"type": "ranked-list", "title": "Revenue by *campaign*",
                     "columns": [{"key": "rank", "label": "#", "type": "rank"},
                                 {"key": "campaign", "label": "Campaign", "type": "name"},
                                 {"key": "tag", "label": "utm_campaign", "type": "source"},
                                 {"key": "rev", "label": "Revenue", "type": "bar"},
                                 {"key": "orders", "label": _cap(nouns), "type": "number", "align": "right"},
                                 {"key": "aov", "label": "Avg value", "type": "money", "align": "right"},
                                 {"key": "share", "label": "Share", "type": "pct", "align": "right"},
                                 {"key": "change", "label": "vs %s" % cmp_, "type": "delta", "align": "right"}],
                     "rows": rows_c,
                     "caption": ("%s (%s) came from %s with no campaign tag." % (money(untag), pct(share(untag, rev)), nouns))
                     if untag else "Every %s carried a campaign tag." % noun})
        nxt = 3

    # 03 first vs last touch
    ft_sales = [s for s in good if s["ft"]]
    rf_under = None
    if len(ft_sales) >= MIN_LEADS:
        RF, RL = defaultdict(float), defaultdict(float)
        for s in ft_sales:
            RF[s["ft"]] += s["total"]
            RL[s["lt"]] += s["total"]
        cats = _gsort(set(RF) | set(RL), lambda x: max(RF[x], RL[x]))[:6]
        rf_under = max(cats, key=lambda x: RF[x] - RL[x])
        rows_cmp = [{"label": x, "a": round(RF[x], 2), "b": round(RL[x], 2), "a_display": money(RF[x]),
                     "b_display": money(RL[x])} for x in cats]
        if RF[rf_under] - RL[rf_under] >= 0.02 * rev:
            t = "*%s* %s buyers that other channels close." % (rf_under, _v(rf_under, "finds", "find"))
        else:
            t = "First and last touch credit *revenue* alike."
        secs.append({"type": "section-header", "number": "%02d" % nxt, "kicker": "First vs last touch", "title": t,
                     "dek": "The same revenue credited to the buyer's first visit (left) and to the visit that %s "
                            "(right)." % ("bought" if mode == "orders" else "became the lead")})
        secs.append({"type": "comparison", "a": {"label": "First touch", "sub": "who found the buyer"},
                     "b": {"label": "Last touch", "sub": "who closed the sale"}, "rows": rows_cmp,
                     "caption": "%s of %s with first-touch data. %s: %s by first touch, %s by last touch." % (
                         money(sum(s["total"] for s in ft_sales)), _pl(len(ft_sales), noun), rf_under,
                         money(RF[rf_under]), money(RL[rf_under]))})
        nxt += 1

    # 04 daily
    series = [{"label": "This period" if not is_full_month(start, end) else start.strftime("%B"),
               "values": [round(x, 2) for x in daily_rev]}]
    if has_prior and pstart and pend:
        dp = _daily(good_p, pstart, pend, lambda s: s["date"], lambda s: s["total"])
        aligned = dp[-len(daily_rev):] if len(dp) >= len(daily_rev) else dp + [None] * (len(daily_rev) - len(dp))
        series.append({"label": _cap(cmp_), "values": [round(x, 2) if x is not None else None for x in aligned],
                       "style": "dashed"})
    secs.append({"type": "section-header", "number": "%02d" % nxt, "kicker": "Day by day",
                 "title": "Revenue *day* by day."})
    secs.append({"type": "chart",
                 "chart": ({"type": "line-multi", "labels": labels, "series": series, "unit": "$"} if len(series) > 1
                           else {"type": "area", "labels": labels, "values": series[0]["values"], "unit": "$"}),
                 "chart_title": "Revenue per *day*",
                 "caption": "Peak of %s on %s. Average %s a day.%s" % (
                     money(daily_rev[peak_i]), labels[peak_i], money(rev / days),
                     (" Dashed: %s, day for day." % cmp_) if len(series) > 1 else "")})
    nxt += 1

    # 05 products
    with_p = [s for s in good if s["products"]]
    top_prod = None
    if mode == "orders" and len(with_p) >= max(MIN_LEADS, 0.5 * k):
        p_all = Counter()
        g_orders, g_prod = Counter(), defaultdict(Counter)
        for s in with_p:
            names = set(nm for nm, _q in s["products"])
            g_orders[s["lt"]] += 1
            for nm in names:
                p_all[nm] += 1
                g_prod[s["lt"]][nm] += 1
        top_prod = p_all.most_common(1)[0]
        rows_p, stand = [], []
        for gname in _gsort(g_orders, lambda x: g_orders[x])[:6]:
            go, gp = g_orders[gname], g_prod[gname]
            tp, tv = gp.most_common(1)[0]
            # "sells more of": the product whose share of this channel's orders is highest against its share of
            # all orders (lift), counted only with 5+ orders in the channel
            lifts = sorted([(nm, (v / float(go)) / (p_all[nm] / float(len(with_p))), v) for nm, v in gp.items() if v >= 5],
                           key=lambda x: (-x[1], -x[2]))
            lift = lifts[0] if lifts and lifts[0][1] >= 1.2 else None
            if lift and go >= 30:     # the sentence names a channel big enough for its lift to mean something
                stand.append((gname, lift))
            rows_p.append({"ch": gname, "orders": {"value": go, "label": n(go)}, "top": _safe(tp, 34),
                           "top_n": "%s, %s" % (_pl(tv, "order"), pct(share(tv, go))),
                           "lift": ("%s, %s" % (_safe(lift[0], 30), ratio(lift[1]))) if lift else "–"})
        ins_p = ""
        if stand:
            gname, (nm, lf, _cnt) = max(stand, key=lambda x: x[1][1])
            ins_p = " %s sells %s %s as often as your store overall." % (gname, _safe(nm, 34), ratio(lf))
        secs.append({"type": "section-header", "number": "%02d" % nxt, "kicker": "Products",
                     "title": "What each *channel* sells.",
                     "dek": "Products from the orders each channel brought in.%s" % ins_p})
        secs.append({"type": "ranked-list", "title": "Top *product* per channel",
                     "columns": [{"key": "ch", "label": "Channel", "type": "name"},
                                 {"key": "orders", "label": "Orders", "type": "bar"},
                                 {"key": "top", "label": "Top product", "type": "name"},
                                 {"key": "top_n", "label": "Orders with it", "type": "text", "align": "right"},
                                 {"key": "lift", "label": "Sells more of", "type": "text"}],
                     "rows": rows_p,
                     "caption": "Top product: in the most of that channel's orders. Sells more of: the product whose "
                                "share of the channel's orders is highest against its share of all orders (5+ orders)."})
        nxt += 1

    # next steps
    recs = []
    if has_prior:
        risers = sorted([c for c in camps[:15] if by_cp.get(c, 0) > 0 and by_c[c] >= 1.2 * by_cp[c] and cnt_c[c] >= 5],
                        key=lambda c: -(by_c[c] - by_cp[c]))
        fallers = sorted([c for c in by_cp if c and by_cp[c] >= 0.03 * rev_p and by_c.get(c, 0) <= 0.7 * by_cp[c]],
                         key=lambda c: -(by_cp[c] - by_c.get(c, 0)))
    else:
        risers, fallers = [], []
    if risers:
        c = risers[0]
        recs.append({"label": "This month", "title": "Put more behind *%s*" % _safe(pretty(c), 48),
                     "body": "It earned %s from %s, up from %s in %s." % (money(by_c[c]), _pl(cnt_c[c], noun),
                                                                         money(by_cp[c]), cmp_),
                     "impact": "High", "effort": "Medium"})
    if fallers:
        c = fallers[0]
        recs.append({"label": "This week", "title": "Find out why *%s* slowed" % _safe(pretty(c), 48),
                     "body": "Its revenue fell from %s in %s to %s. Look for a paused ad, a changed offer or a broken "
                             "link." % (money(by_cp[c]), cmp_, money(by_c.get(c, 0.0))),
                     "impact": "High" if by_cp[c] - by_c.get(c, 0) >= 0.05 * rev else "Medium", "effort": "Low"})
    if rf_under and RF[rf_under] - RL[rf_under] >= 0.03 * rev:
        recs.append({"label": "Reporting", "title": "Credit *%s* for the buyers %s" % (
            rf_under, _v(rf_under, "it finds", "they find")),
                     "body": "By first visit %s %s of revenue; last click gives %s only %s. Report both numbers "
                             "before you cut %s budget." % (
                                 _v(rf_under, "it found", "they found"), _money(RF[rf_under]),
                                 _v(rf_under, "it", "them"), _money(RL[rf_under]), _v(rf_under, "its", "their")),
                     "impact": "Medium", "effort": "Low"})
    if untag >= 0.15 * rev:
        recs.append({"label": "This week", "title": "Tag the links behind *untagged* %s" % nouns,
                     "body": "%s (%s) of revenue carried no campaign tag, so no campaign gets credit for it." % (
                         money(untag), pct(share(untag, rev))), "impact": "Medium", "effort": "Low"})
    if mode == "orders" and refunds and share(len(refunds), len(refunds) + k) >= 4:
        rprod = Counter(nm for s in refunds for nm in set(x for x, _q in s["products"])).most_common(1)
        recs.append({"label": "This month", "title": "Look into *refunds*",
                     "body": "%s were refunded (%s of %s), worth %s.%s" % (
                         _cap(_pl(len(refunds), "order")), pct(share(len(refunds), len(refunds) + k), 1), nouns,
                         money(sum(s["total"] for s in refunds)),
                         (" %s appears in %s of them." % (rprod[0][0], n(rprod[0][1]))) if rprod and rprod[0][1] >= 3 else ""),
                     "impact": "Medium", "effort": "Low"})
    if roas is not None and len(recs) < 4:
        recs.append({"label": "Ongoing", "title": "Hold ad spend to a *%s* floor" % ratio(roas),
                     "body": "Ads returned %s in ad-click revenue for %s spend. Pause any campaign that stays well "
                             "below that for two weeks." % (money(ad_rev), money(spend)), "impact": "Medium",
                     "effort": "Low"})
    if len(recs) < 2:
        recs.append({"label": "Ongoing", "title": "Keep *%s* funded" % top_g,
                     "body": "It brought %s of revenue (%s). Test one new offer there before moving budget." % (
                         pct(share(by_g[top_g], rev)), money(by_g[top_g])), "impact": "Medium", "effort": "Medium"})
    secs.append({"type": "section-header", "number": "%02d" % nxt, "kicker": "Next steps",
                 "title": "Where the next *dollar* should go."})
    secs.append({"type": "recommendations", "items": recs[:4]})
    notes = []
    if mode == "orders":
        notes.append("Revenue: order totals of completed and processing WooCommerce orders. Refunded orders are left "
                     "out of revenue and shown under Refunds; cancelled, failed and pending orders are left out.")
        notes.append("Channel and campaign come from the UTM Grabber fields saved on each order: last touch is the "
                     "visit that bought, first touch the person's first visit.")
    else:
        unmatched = sum(1 for s in sales if not s["matched"])
        notes.append("No WooCommerce orders were connected, so revenue comes from %s, dated by when each deal was "
                     "created and attributed through the lead with the same email.%s" % (
                         _pl(len(sales), "won CRM deal"),
                         (" %s had no form lead with the same email and show as No form lead." % n(unmatched))
                         if unmatched else ""))
    if roas is not None:
        a0, a1 = _ad_span(ads)
        notes.append("Return on ad spend: revenue from %s whose last click was an ad on %s, divided by %s spend%s." % (
            nouns, ", ".join(sorted(known)) if known else "a paid channel", money(spend),
            (" (%s)" % period_label(a0, a1)) if a0 else ""))
    else:
        notes.append("Ad spend was not connected, so return on ad spend is not shown.")
    if has_prior:
        notes.append("Changes compare with %s: %s from %s." % (cmp_, money(rev_p), _pl(len(good_p), noun)))
    secs.append({"type": "notes", "title": "How we built this report", "items": notes})
    r0 = recs[0]
    if r0["title"].startswith("Put more behind"):
        c = risers[0]
        ctitle = "Next: put more behind *%s*. It earned %s, up from %s." % (_safe(pretty(c), 48), money(by_c[c]), money(by_cp[c]))
    elif r0["title"].startswith("Find out why"):
        c = fallers[0]
        ctitle = "Next: find out why *%s* slowed. It fell from %s to %s." % (
            _safe(pretty(c), 48), money(by_cp[c]), money(by_c.get(c, 0.0)))
    elif r0["title"].startswith("Credit"):
        ctitle = "Next: credit *%s* for the buyers %s: %s by first visit." % (
            rf_under, _v(rf_under, "it finds", "they find"), _money(RF[rf_under]))
    elif r0["title"].startswith("Tag the links"):
        ctitle = "Next: tag every *link* that sells. %s of revenue carries no campaign." % pct(share(untag, rev))
    else:
        ctitle = "Next: keep *%s* funded. It brought %s of revenue." % (top_g, pct(share(by_g[top_g], rev)))
    secs.append({"type": "closing", "kicker": "Revenue in one line", "title": ctitle,
                 "summary_stats": [x for x in [{"value": money(rev), "label": "Revenue"},
                                               {"value": n(k), "label": _cap(nouns)},
                                               {"value": money(aov), "label": "Average value"},
                                               ({"value": ratio(roas), "label": "Return on ad spend"} if roas is not None
                                                else {"value": top_g, "label": "Top channel"})]],
                 "bullets": [x for x in [
                     "Busiest day: %s with %s." % (labels[peak_i], money(daily_rev[peak_i])),
                     ("Top campaign: %s with %s." % (pretty(camps[0]), money(by_c[camps[0]]))) if camps else None,
                     ("Top product: %s, in %s." % (top_prod[0], _pl(top_prod[1], "order"))) if top_prod else None] if x]})
    return {"meta": m, "sections": secs}


def _revenue_thin(m, kicker, good, refunds, rev, noun, nouns, bits):
    k = len(good)
    rows = []
    for i, s in enumerate(sorted(good, key=lambda x: x["date"] or _dt.date.min)[:9]):
        rows.append({"rank": str(i + 1), "date": _md(s["date"]) if s["date"] else "–", "channel": s["lt"],
                     "campaign": _safe(s["campaign"], 30) or "–", "total": money(s["total"])})
    return _short(m, kicker, "Only %s so far: too few to rank *channels*." % _pl(k, noun),
                  "This report needs at least *10 %s*." % nouns,
                  ["%s brought %s in revenue. With so few, one sale moves any channel's share by %s points." % (
                      _cap(_pl(k, noun)), money(rev), n(round(100.0 / max(k, 1)))),
                   "Widen the date range, or run this again once more %s arrive." % nouns],
                  subtitle="Here is every %s we found, with the channel behind it." % noun,
                  stats=[stat("Revenue", money(rev)), stat(_cap(nouns), n(k)),
                         stat("Refunds", n(len(refunds)), good="down")],
                  extra=[{"type": "ranked-list", "title": "Every *%s* this period" % noun,
                          "columns": [{"key": "rank", "label": "#", "type": "rank"},
                                      {"key": "date", "label": "Date", "type": "text"},
                                      {"key": "channel", "label": "Channel", "type": "name"},
                                      {"key": "campaign", "label": "Campaign", "type": "source"},
                                      {"key": "total", "label": "Value", "type": "money", "align": "right"}],
                          "rows": rows, "caption": "Shown without names or emails."}] if rows else [],
                  close_title="Next: widen the *date range* and run this again.", bits=bits)


# ===========================================================================
# 4. DAILY PULSE
# ===========================================================================
def _pulse_key(e):
    s = _src(e)
    return s if s else "~" + lt_group(e)


def _pulse_label(k):
    if k.startswith("~"):
        return "Direct visits" if k[1:] == G_DIRECT else "Untagged %s" % _lname(k[1:])
    return _src_label(k)


def _leads_from(c, label, rest):
    """'1 lead from X, against 2 a day' / '4 leads from X, ...' (callout titles follow a big number)."""
    return "%s from %s%s" % ("lead" if c == 1 else "leads", label, rest)


def _quiet_advice(k):
    if k.startswith("~"):
        return "Check that the links and pages behind it still work."
    if _ai_name(k):
        return "Assistant answers shift often; check it still recommends you."
    g = _group(k, "", "")
    return {G_PSEARCH: "Look for a paused ad, a spent budget or a broken link.",
            G_PSOCIAL: "Look for a paused ad, a spent budget or a broken link.",
            G_OSEARCH: "Check that its landing pages still load and rank.",
            G_OSOCIAL: "Check whether posting slowed, or a link in a post or bio broke.",
            G_EMAIL: "Check whether the email went out and its links work."}.get(
        g, "Check that the link or page that sends these visitors still works.")


def build_daily_pulse(history, as_of=None, ad_rows=None, brand_profile=None, customer_name=None, customer_domain="",
                      compare_label=None, form_label=None, prepared_by=None, prepared_for=None, **_):
    """One page for the morning: the day's leads against the trailing week, what moved, what broke."""
    name = "Daily pulse"
    history = list(history or [])
    m = _meta(brand_profile, customer_name, customer_domain, compare_label or "the 7-day average", prepared_by,
              prepared_for)
    if not history:
        return empty_report(name, m)
    dated = [e for e in history if _day(e)]
    if not dated:
        return _undated(name, m, history)
    hs = min(_day(e) for e in dated)
    he = max(_day(e) for e in dated)
    day = _as_date(as_of) or he
    today = [e for e in dated if _day(e) == day]
    t7 = [e for e in dated if day - 7 * ONE_DAY <= _day(e) <= day - ONE_DAY]
    # days of the trailing week that the data covers (a day outside the pulled range is unknown, not zero)
    covered = sum(1 for i in range(1, 8) if hs <= day - i * ONE_DAY <= he)
    last_wk = [e for e in dated if _day(e) == day - 7 * ONE_DAY]
    wd = WEEKDAYS[day.weekday()]
    kicker = "%s · %s, %s" % (name, wd, _md(day) + day.strftime(", %Y"))
    nt = len(today)
    m["sources"] = sources_meta(utmg=_pl(nt, "lead"))
    bits = [customer_domain, form_label]
    if day > he or day < hs:
        return _short(m, kicker, "Pull leads through *%s* to see the day." % _md(day),
                      "These leads stop on *%s*." % _md(he),
                      ["The leads passed in run from %s to %s, so %s, %s is outside them. A day outside the pulled "
                       "range is unknown, not zero." % (_md(hs), _md(he), wd, _md(day)),
                       "Pull the 30 days up to and including %s, then run the pulse again." % _md(day)],
                      stats=[stat("Leads pulled", n(len(dated))), stat("Last day in the data", _md(he), good="neutral")],
                      close_title="Next: pull leads through *%s* and run the pulse again." % _md(day), bits=bits)
    if covered < 3:
        return _short(m, kicker, "*%s* came in on %s." % (_cap(_pl(nt, "lead")), wd),
                      "The pulse needs the *week* before.",
                      ["The data starts on %s, leaving %s before %s to compare against." % (
                          _md(hs), "no day" if covered == 0 else _pl(covered, "day"), _md(day)),
                       "Pass the last 30 days of leads and the pulse compares the day with its trailing week."],
                      stats=[stat("Leads", n(nt)), stat("Days before it", n(covered), good="neutral")],
                      close_title="Next: pull the last *30 days* of leads and run the pulse again.", bits=bits)
    avg7 = len(t7) / float(covered)
    srcs_today = Counter(_pulse_key(e) for e in today)
    srcs_7 = Counter(_pulse_key(e) for e in t7)
    days_7 = defaultdict(set)
    for e in t7:
        days_7[_pulse_key(e)].add(_day(e))
    lo = max(hs, day - 13 * ONE_DAY)
    spark = _daily(dated, lo, day, _day)
    d = delta(nt, avg7, flat_below=5.0)
    if d.get("delta_direction") == "up":
        rel = "%s above average" % d["delta_label"].lstrip("+")
    elif d.get("delta_direction") == "down":
        rel = "%s below average" % d["delta_label"].lstrip(MINUS)
    else:
        rel = "in line with the average"
    headline = "*%s*, %s." % (_cap(_pl(nt, "lead")), rel)

    # what moved
    moves = []
    for k in set(srcs_today) | set(srcs_7):
        a = srcs_7.get(k, 0) / float(covered)
        moves.append((k, srcs_today.get(k, 0), a, srcs_today.get(k, 0) - a))
    # a move counts when it is 2+ leads and outside normal day-to-day swing for that volume (1.5 x sqrt(avg));
    # a source "went quiet" when it averages 3+ a day, sent leads on 6 of 7 days, and sent none today
    # (a zero that random swing alone produces about 1 day in 20 or less)
    risers = sorted([x for x in moves if x[3] >= 2 and x[3] >= 1.5 * math.sqrt(max(x[2], 1))], key=lambda x: -x[3])
    drops = sorted([x for x in moves if x[1] > 0 and -x[3] >= 2 and -x[3] >= 1.5 * math.sqrt(max(x[2], 1))],
                   key=lambda x: x[3])
    quiet = sorted([x for x in moves if x[1] == 0 and x[2] >= 3 and len(days_7.get(x[0], ())) >= min(6, covered)],
                   key=lambda x: -x[2])
    untagged = sum(1 for e in today if not _src(e))
    items = []
    if quiet:
        k, _c, a, _x = quiet[0]
        items.append({"kicker": "Went quiet", "value": "0", "tone": "bad" if a >= 5 else "warn",
                      "title": "leads from %s, which averages %s a day" % (_pulse_label(k), _day_rate(a))})
    if risers:
        k, c, a, _x = risers[0]
        items.append({"kicker": "Up", "value": n(c), "tone": "good",
                      "title": _leads_from(c, _pulse_label(k), ", against %s a day" % _day_rate(a))})
    if drops:
        k, c, a, _x = drops[0]
        items.append({"kicker": "Down", "value": n(c), "tone": "warn",
                      "title": _leads_from(c, _pulse_label(k), ", against %s a day" % _day_rate(a))})
    regular = [k for k, ds in days_7.items() if len(ds) >= min(5, covered) and srcs_7[k] / float(covered) >= 1]
    if not quiet and regular:
        items.append({"kicker": "Regulars", "value": "%s of %s" % (n(sum(1 for k in regular if srcs_today.get(k))),
                                                                    n(len(regular))),
                      "tone": "good", "title": "sources that send leads most days showed up"})
    if nt and len(items) < 4:
        items.append({"kicker": "Untagged", "value": pct(share(untagged, nt)),
                      "tone": "warn" if share(untagged, nt) >= 25 else "neutral",
                      "title": "of the day's leads had no UTM source (%s)" % n(untagged)})
    if len(items) < 2:
        items.append({"kicker": "Same day last week", "value": n(len(last_wk)), "tone": "neutral",
                      "title": "%s on %s, %s" % ("lead" if len(last_wk) == 1 else "leads", wd, _md(day - 7 * ONE_DAY))})

    top = srcs_today.most_common(1)[0] if srcs_today else None
    sub = []   # one short line: the page has to print on one sheet
    if top:
        sub.append("%s sent the most (%s)" % (_pulse_label(top[0]), n(top[1])))
    if quiet:
        k, _c, a, _x = quiet[0]
        sub.append("%s went quiet (0 against %s a day)" % (_pulse_label(k), _day_rate(a)))
    elif risers:
        k, c, a, _x = risers[0]
        sub.append("%s rose to %s against %s a day" % (_pulse_label(k), n(c), _day_rate(a)))
    elif regular:
        sub.append("every regular source sent leads")
    sub = ["; ".join(sub) + "."] if sub else []

    s1 = stat("Leads on %s" % wd, n(nt), nt, avg7, good="up", spark=spark,
              note="7-day average: %s" % _day_rate(avg7))
    s1["compare"] = "the 7-day average"
    stats = [s1]
    if covered >= 7:
        g = _growth(nt, len(last_wk)) if last_wk else None
        stats.append(stat("vs last %s" % wd, _sp(g) if g is not None else ("All new" if nt else "Flat"), good="neutral",
                          note="%s on %s" % (_pl(len(last_wk), "lead"), _md(day - 7 * ONE_DAY))))
    if top:
        stats.append(stat("Top source", _pulse_label(top[0]), good="neutral",
                          note="%s, %s of the day" % (_pl(top[1], "lead"), pct(share(top[1], nt)))))
    ads = _ads(ad_rows)
    sp_day = sum(r.get("spend", 0.0) for r in ads if _d(r.get("date")) == day)
    sp_7 = [sum(r.get("spend", 0.0) for r in ads if _d(r.get("date")) == day - i * ONE_DAY) for i in range(1, 8)]
    paid_today = sum(1 for e in today if lt_group(e) in PAID_GROUPS)
    if sp_day > 0:
        have = [v for v in sp_7 if v > 0]
        s4 = stat("Ad spend", money(sp_day), sp_day, (sum(have) / len(have)) if have else None, good="neutral",
                  note=("%s per paid lead" % money(sp_day / paid_today)) if paid_today else "no paid leads that day")
        s4["compare"] = "the 7-day average"
        stats.append(s4)
        for plat, v in _spend_sources([r for r in ads if _d(r.get("date")) == day]):
            m["sources"].append({"name": plat, "detail": "%s spend" % money(v)})
    else:
        stats.append(stat("Paid leads", n(paid_today), good="neutral",
                          note="%s of the day" % pct(share(paid_today, nt)) if nt else "no leads that day"))
    # as close to one printed page as the print layout allows: no meta line (the domain is in the page header),
    # no dek, no chart caption or axis label, four sources
    secs = [{"type": "title-block", "kicker": kicker, "title": headline, "subtitle": " ".join(sub),
             "meta_bits": []},
            {"type": "stat-strip", "stats": stats[:4]},
            {"type": "section-header", "number": "01", "kicker": "What moved",
             "title": "What *moved* against the usual day."},
            {"type": "callouts", "items": items[:4]}]
    if srcs_today:
        top4 = srcs_today.most_common(4)
        secs.append({"type": "chart",
                     "chart": {"type": "bar-horizontal", "labels": [_pulse_label(k) for k, _v in top4],
                               "values": [v for _k, v in top4], "highlight": 0, "total": nt,
                               "notes": ["usual %s a day" % _day_rate(srcs_7.get(k, 0) / float(covered)) for k, _v in top4]},
                     "chart_title": "Top sources of the day's *leads*"})

    recs = []
    if quiet:
        k, _c, a, _x = quiet[0]
        recs.append({"label": "Today", "title": "Check *%s* today" % _pulse_label(k),
                     "body": "It averaged %s leads a day this week and sent none on %s. %s" % (
                         _day_rate(a), wd, _quiet_advice(k)), "impact": "High" if a >= 3 else "Medium", "effort": "Low"})
    if d.get("delta_direction") == "down" and nt <= 0.7 * avg7:
        recs.append({"label": "Today", "title": "Test your top *form* this morning",
                     "body": "Leads fell to %s against %s a day. Submit a test entry and check the top ads still run." % (
                         n(nt), _day_rate(avg7)), "impact": "High", "effort": "Low"})
    if risers and len(recs) < 2:
        k, c, a, _x = risers[0]
        recs.append({"label": "Today", "title": "Find what lifted *%s*" % _pulse_label(k),
                     "body": "It sent %s against %s a day. If an ad, email or post is behind it, keep it running." % (
                         _pl(c, "lead"), _day_rate(a)), "impact": "Medium", "effort": "Low"})
    if nt and share(untagged, nt) >= 25 and len(recs) < 2:
        recs.append({"label": "This week", "title": "Tag the links behind *untagged* leads",
                     "body": "%s of %s leads (%s) had no UTM source, so they can't be credited." % (
                         n(untagged), n(nt), pct(share(untagged, nt))), "impact": "Medium", "effort": "Low"})
    if len(recs) < 2 and top:
        recs.append({"label": "Today", "title": "Keep *%s* running" % _pulse_label(top[0]),
                     "body": "It sent %s of the day's %s leads." % (n(top[1]), n(nt)), "impact": "Medium",
                     "effort": "Low"})
    if len(recs) < 2:
        recs.append({"label": "Today", "title": "Check your *forms* still submit",
                     "body": "No leads arrived on %s. Submit a test entry on your top page." % wd,
                     "impact": "High", "effort": "Low"})
    secs.append({"type": "recommendations", "items": recs[:2]})
    if quiet:
        k, _c, a, _x = quiet[0]
        ctitle = "Next: check *%s* today. It sent 0 leads against %s a day." % (_pulse_label(k), _day_rate(a))
    elif d.get("delta_direction") == "down" and nt <= 0.7 * avg7:
        ctitle = "Next: test your top *form* now. Leads fell to %s against %s a day." % (n(nt), _day_rate(avg7))
    elif risers:
        k, c, a, _x = risers[0]
        ctitle = "Next: find what lifted *%s*. It sent %s against %s a day." % (_pulse_label(k), _pl(c, "lead"),
                                                                              _day_rate(a))
    elif top:
        ctitle = "Next: keep *%s* running. It sent %s of %s leads." % (_pulse_label(top[0]), n(top[1]), n(nt))
    else:
        ctitle = "Next: submit a test entry on your top *form* today."
    secs.append({"type": "closing", "kicker": "The day in one line", "title": ctitle})
    return {"meta": m, "sections": secs}


# ===========================================================================
# 5. WHEN LEADS ARRIVE (lead timing)
# ===========================================================================
_DAYPARTS = (("Night", 0, 6), ("Morning", 6, 12), ("Afternoon", 12, 18), ("Evening", 18, 24))


def _daypart(h):
    for nm, a, b in _DAYPARTS:
        if a <= h < b:
            return nm
    return "Night"


def _office(dt_):
    return dt_.weekday() < 5 and 8 <= dt_.hour < 18


def _window_name(wd, h0, h1):
    return "%s %s to %s" % (WEEKDAYS[wd], _clock(h0), _clock(h1))


def build_lead_timing(leads, prior=None, brand_profile=None, customer_name=None, customer_domain="",
                      compare_label=None, form_label=None, prepared_by=None, prepared_for=None, **_):
    """The day x hour map of when leads arrive, paid vs organic timing, devices, and what to schedule."""
    name = "When leads arrive"
    leads, prior = list(leads or []), list(prior or [])
    start, end = span(leads)
    pstart, pend = span(prior) if prior else (None, None)
    m = _meta(brand_profile, customer_name, customer_domain,
              compare_label or (prior_name(pstart, pend) if prior else "last period"), prepared_by, prepared_for)
    if not leads:
        return empty_report(name, m)
    if start is None:
        return _undated(name, m, leads)
    period = period_label(start, end)
    kicker = "%s · %s" % (name, period)
    total = len(leads)
    days = (end - start).days + 1
    bits = [customer_domain, form_label, "%s submissions" % n(total), _pl(days, "day")]
    cmp_ = m["compare_label"]
    m["sources"] = sources_meta(utmg="%s leads" % n(total))
    if total < MIN_LEADS:
        return _thin(name, m, leads, period)
    timed = [(e, entry_dt(e)) for e in leads]
    timed = [(e, t) for e, t in timed if t]
    if sum(1 for _e, t in timed if t.hour or t.minute or t.second) < 0.1 * len(timed):
        return _short(m, kicker, "These leads carry dates but no *times*.", "Timing needs a *time* on every lead.",
                      ["Every Date Created value reads as midnight, so the entries were exported without a time of day.",
                       "Pull the entries again with the full timestamp and this report maps the hours."],
                      stats=[stat("Leads", n(total)), stat("With a time", "0", good="neutral")],
                      close_title="Next: re-pull the leads with full *timestamps*.", bits=bits)
    sample = leads[:200]
    utc = sum(1 for e in sample if str(get_field(e, "Date Created", "date_created", "Date", "date")).endswith("Z")) \
        >= 0.5 * len(sample)
    grid = [[0] * 24 for _ in range(7)]
    for _e, t in timed:
        grid[t.weekday()][t.hour] += 1
    nt = len(timed)
    # weekday counts normalized by how often each weekday occurs in the period
    occ = Counter((start + i * ONE_DAY).weekday() for i in range(days))
    per_wd = [sum(grid[w]) / float(occ.get(w, 1) or 1) for w in range(7)]
    busy_wd = max(range(7), key=lambda w: per_wd[w])
    by_hour = [sum(grid[w][h] for w in range(7)) for h in range(24)]
    peak_h = max(range(24), key=lambda h: by_hour[h])

    def win(w, h):
        return sum(grid[w][h:h + 3])

    best = max(((w, h) for w in range(7) for h in range(22)), key=lambda x: (win(*x), -x[0]))
    best_n = win(*best)
    quiet_c = [(w, h) for w in range(7) for h in range(8, 18)]
    quiet = min(quiet_c, key=lambda x: (win(*x), x[0], x[1]))
    quiet_n = win(*quiet)
    after = sum(1 for _e, t in timed if not _office(t))
    after_s = share(after, nt)
    timed_p = [t for t in (entry_dt(e) for e in prior) if t]
    after_p = share(sum(1 for t in timed_p if not _office(t)), len(timed_p)) if len(timed_p) >= MIN_LEADS else None
    devs = [(e, _device(e)) for e, _t in timed]
    devs = [(e, dv) for e, dv in devs if dv]
    has_dev = len(devs) >= max(MIN_LEADS, 0.5 * nt)
    dv_p = [dv for dv in (_device(e) for e in prior) if dv]
    mob = share(sum(1 for _e, dv in devs if dv == "Mobile"), len(devs)) if has_dev else None
    mob_p = share(dv_p.count("Mobile"), len(dv_p)) if has_dev and len(dv_p) >= MIN_LEADS else None

    best_name = _window_name(best[0], best[1], best[1] + 3)
    best_part = _daypart(best[1] + 1)
    title = "*%s %ss* bring the most leads: %s between %s and %s." % (
        WEEKDAYS[best[0]], best_part.lower(), n(best_n), _clock(best[1]), _clock(best[1] + 3))
    sub = ["%s of leads arrive outside office hours (Monday to Friday, 8am to 6pm)." % pct(after_s)]
    if has_dev:
        sub.append("%s come from phones." % pct(mob))
    stats = [stat("Leads", n(total), total, len(prior) if len(prior) >= MIN_LEADS else None,
                  spark=_daily(leads, start, end, _day)),
             stat("Busiest day", WEEKDAYS[busy_wd], good="neutral",
                  note="%s leads on an average %s" % (_day_rate(per_wd[busy_wd]), WEEKDAYS[busy_wd])),
             stat("Peak hour", "%s to %s" % (_clock(peak_h), _clock(peak_h + 1)), good="neutral",
                  note="%s of leads" % pct(share(by_hour[peak_h], nt))),
             stat("After hours", pct(after_s), after_s, after_p, kind="pts", good="neutral",
                  note="%s leads outside office hours" % n(after))]
    if has_dev:
        stats.append(stat("On a phone", pct(mob), mob, mob_p, kind="pts", good="neutral",
                          note="%s of %s leads with a device" % (n(sum(1 for _e, dv in devs if dv == "Mobile")), n(len(devs)))))
    secs = [{"type": "title-block", "kicker": kicker, "title": title, "subtitle": " ".join(sub),
             "meta_bits": [b for b in bits if b]},
            {"type": "stat-strip", "stats": stats},
            {"type": "insight-card", "kicker": "The takeaway",
             "title": "*%s* of leads arrive while the office is closed." % pct(after_s),
             "body": ["That is %s of %s leads, outside Monday to Friday, 8am to 6pm." % (n(after), n(nt)),
                      "Answer them first thing the next morning, or send an instant reply that says when you will call."]}]

    # 01 heatmap + windows
    secs.append({"type": "section-header", "number": "01", "kicker": "The week",
                 "title": "When the *week* is busiest.",
                 "dek": "Leads by day of week and hour of submission%s." % (
                     ", in UTC as recorded" if utc else ", in the site's time as recorded in Date Created")})
    # callouts first: in PowerPoint they take the section title and the heatmap keeps its own chart title
    secs.append({"type": "callouts", "items": [
        {"kicker": "Best window", "value": n(best_n), "tone": "good",
         "title": "%s on %s (%s of all)" % ("lead" if best_n == 1 else "leads", best_name, pct(share(best_n, nt)))},
        {"kicker": "Quietest daytime window", "value": n(quiet_n), "tone": "neutral",
         "title": "%s on %s" % ("lead" if quiet_n == 1 else "leads", _window_name(quiet[0], quiet[1], quiet[1] + 3))},
        {"kicker": "Busiest day", "value": _day_rate(per_wd[busy_wd]), "tone": "neutral",
         "title": "leads on an average %s, against %s a day overall" % (WEEKDAYS[busy_wd], _day_rate(nt / float(days)))},
        {"kicker": "After hours", "value": pct(after_s), "tone": "warn" if after_s >= 30 else "neutral",
         "title": "of leads arrive outside Monday to Friday, 8am to 6pm"}]})
    secs.append({"type": "heatmap", "chart_title": "Leads by day and *hour*", "rows": [w[:3] for w in WEEKDAYS],
                 "cols": [_hour_label(h) for h in range(24)], "values": grid, "low_label": "Fewer",
                 "high_label": "More",
                 "caption": "Busiest hour of the week: %s at %s, with %s." % (
                     WEEKDAYS[max(((w, h) for w in range(7) for h in range(24)), key=lambda x: grid[x[0]][x[1]])[0]],
                     _clock(max(((w, h) for w in range(7) for h in range(24)), key=lambda x: grid[x[0]][x[1]])[1]),
                     _pl(max(max(r) for r in grid), "lead"))})

    # 02 paid vs organic by daypart
    nxt = 2
    paid = [t for e, t in timed if lt_group(e) in PAID_GROUPS]
    org = [t for e, t in timed if lt_group(e) not in PAID_GROUPS]
    paid_best = None
    if len(paid) >= MIN_LEADS and len(org) >= MIN_LEADS:
        parts = [p[0] for p in _DAYPARTS]
        ps = [share(sum(1 for t in paid if _daypart(t.hour) == p), len(paid)) for p in parts]
        os_ = [share(sum(1 for t in org if _daypart(t.hour) == p), len(org)) for p in parts]
        gaps = [ps[i] - os_[i] for i in range(4)]
        gi = max(range(4), key=lambda i: abs(gaps[i]))
        side = "Paid" if gaps[gi] > 0 else "Organic"
        hi, lo_ = (ps[gi], os_[gi]) if gaps[gi] > 0 else (os_[gi], ps[gi])
        pgrid = [[0] * 24 for _ in range(7)]
        for t in paid:
            pgrid[t.weekday()][t.hour] += 1
        pb = max(((w, h) for w in range(7) for h in range(22)), key=lambda x: (sum(pgrid[x[0]][x[1]:x[1] + 3]), -x[0]))
        paid_best = (pb, sum(pgrid[pb[0]][pb[1]:pb[1] + 3]), len(paid))
        it = ("*%s* leads lean to the %s: %s against %s." % (side, parts[gi].lower(), pct(hi), pct(lo_))
              if abs(gaps[gi]) >= 3 else "Paid and organic leads keep the *same* hours.")
        secs.append({"type": "section-header", "number": "02", "kicker": "Paid vs organic",
                     "title": "When paid and organic *leads* arrive.",
                     "dek": "Paid: the converting visit was an ad click. Organic: every other lead (search, AI, social, "
                            "email, referral and direct)."})
        secs.append({"type": "chart-insight",
                     "chart": {"type": "bar-grouped", "labels": parts, "unit": "%",
                               "groups": [{"label": "Paid", "values": [round(x, 1) for x in ps]},
                                          {"label": "Organic", "values": [round(x, 1) for x in os_]}]},
                     "caption": "Share of each side's leads by time of day (night is midnight to 6am)",
                     "insight_kicker": "The difference", "insight_title": it,
                     "insight_body": ["%s paid and %s organic leads." % (n(len(paid)), n(len(org))),
                                      "Paid leads peak on %s: %s of them." % (
                                          _window_name(pb[0], pb[1], pb[1] + 3), n(paid_best[1]))]})
        nxt = 3

    # 03 devices
    if has_dev:
        dc = Counter(dv for _e, dv in devs)
        labels = [x for x in ("Mobile", "Desktop", "Tablet") if dc.get(x)]
        ev = [dv for e, dv in devs if _daypart(entry_dt(e).hour) == "Evening"]
        mo = [dv for e, dv in devs if _daypart(entry_dt(e).hour) == "Morning"]
        body = ["%s of %s leads came from a phone, %s from a desktop." % (
            n(dc.get("Mobile", 0)), n(len(devs)), n(dc.get("Desktop", 0)))]
        if len(ev) >= 5 and len(mo) >= 5:
            body.append("Phones bring %s of evening leads and %s of morning leads." % (
                pct(share(ev.count("Mobile"), len(ev))), pct(share(mo.count("Mobile"), len(mo)))))
        secs.append({"type": "section-header", "number": "%02d" % nxt, "kicker": "Devices",
                     "title": "Most leads *arrive* on %s." % ("a phone" if mob >= 50 else "a computer"),
                     "dek": "Device read from the browser's user agent, which %s saves on every lead." % PREMIUM})
        secs.append({"type": "chart-insight",
                     "chart": {"type": "doughnut", "labels": labels,
                               "values": [round(share(dc[x], len(devs)), 1) for x in labels], "unit": "%"},
                     "caption": "Share of leads by device",
                     "insight_kicker": "On the go",
                     "insight_title": "*%s* of leads come from phones." % pct(mob),
                     "insight_body": body})
        nxt += 1

    # next steps
    recs = []
    if paid_best:
        (pw, ph), pn, ptot = paid_best
        recs.append({"label": "Ads", "title": "Raise bids on *%s %ss*" % (WEEKDAYS[pw], _daypart(ph + 1).lower()),
                     "body": "Paid leads peak %s: %s of %s. Schedule budget to match, and trim bids from %s, the "
                             "quietest daytime window (%s)." % (
                                 _window_name(pw, ph, ph + 3), n(pn), n(ptot), _window_name(quiet[0], quiet[1], quiet[1] + 3),
                                 _pl(quiet_n, "lead")), "impact": "High", "effort": "Low"})
    recs.append({"label": "Phones", "title": "Staff the phones on *%s %ss*" % (WEEKDAYS[best[0]], best_part.lower()),
                 "body": "%s brings %s, %s of the period's leads in 3 of the week's 168 hours. Have someone ready "
                         "to call back within the hour." % (best_name, _pl(best_n, "lead"), pct(share(best_n, nt))),
                 "impact": "High", "effort": "Medium"})
    if after_s >= 20:
        recs.append({"label": "This week", "title": "Send an instant *reply* after hours",
                     "body": "%s of leads (%s) arrive outside Monday to Friday, 8am to 6pm. An automatic email or text "
                             "tells them when you will call." % (pct(after_s), n(after)), "impact": "Medium",
                     "effort": "Low"})
    send_h = max(6, best[1] - 1)
    recs.append({"label": "Email", "title": "Send emails at *%s* on %ss" % (_clock(send_h), WEEKDAYS[best[0]]),
                 "body": "Leads are most active %s. An email that lands just before that window meets people when "
                         "they are ready to act." % best_name, "impact": "Medium", "effort": "Low"})
    if has_dev and mob >= 60 and len(recs) < 4:
        recs.append({"label": "This month", "title": "Fill in your form on a *phone*",
                     "body": "%s of leads come from phones. Check the form fits the screen and the call button works." %
                             pct(mob), "impact": "Medium", "effort": "Low"})
    nsec = "%02d" % nxt
    secs.append({"type": "section-header", "number": nsec, "kicker": "Next steps",
                 "title": "Match your *schedule* to your leads."})
    secs.append({"type": "recommendations", "items": recs[:4]})
    notes = ["Times come from each lead's Date Created value%s. Days run Monday to Sunday." % (
        " (UTC as recorded; shift to your local time before scheduling)" if utc else ", in the site's time zone"),
             "Office hours: Monday to Friday, 8am to 6pm. Dayparts: night midnight to 6am, morning 6am to noon, "
             "afternoon noon to 6pm, evening 6pm to midnight.",
             "Windows are 3 consecutive hours on one day. Busiest day divides each weekday's leads by how many times "
             "that weekday falls in the period."]
    notes.append("Devices come from the browser user agent %s saves on each lead." % PREMIUM if has_dev else
                 "No device data on these leads: %s saves the browser user agent, which adds the phone and desktop "
                 "split." % PREMIUM)
    secs.append({"type": "notes", "title": "How we built this report", "items": notes})
    secs.append({"type": "closing", "kicker": "Timing in one line",
                 "title": "Next: staff and fund *%s %ss*. %s to %s alone brought %s." % (
                     WEEKDAYS[best[0]], best_part.lower(), _cap(_clock(best[1])), _clock(best[1] + 3),
                     _pl(best_n, "lead")),
                 "summary_stats": [x for x in [{"value": WEEKDAYS[busy_wd], "label": "Busiest day"},
                                               {"value": "%s to %s" % (_clock(peak_h), _clock(peak_h + 1)), "label": "Peak hour"},
                                               {"value": pct(after_s), "label": "After hours"},
                                               ({"value": pct(mob), "label": "On a phone"} if has_dev else None)] if x],
                 "bullets": ["Best window: %s, %s." % (best_name, _pl(best_n, "lead")),
                             "Quietest daytime window: %s, %s." % (_window_name(quiet[0], quiet[1], quiet[1] + 3),
                                                                  _pl(quiet_n, "lead"))]})
    return {"meta": m, "sections": secs}


# ===========================================================================
# 6. QUARTERLY BUSINESS REVIEW
# ===========================================================================
def _qof(d):
    return d.year, (d.month - 1) // 3 + 1


def _qbounds(y, q):
    s = _dt.date(y, 3 * (q - 1) + 1, 1)
    e = (_dt.date(y + 1, 1, 1) if q == 4 else _dt.date(y, 3 * q + 1, 1)) - ONE_DAY
    return s, e


def _coverage(entries):
    """(start, end, label, full_quarter) of a lead set, snapped to its calendar quarter when the data starts or
    ends within 3 days of the quarter's edge."""
    s, e = span(entries)
    if not s:
        return None, None, "", False
    qs = Counter(_qof(_day(x)) for x in entries if _day(x))
    (y, q), _c = qs.most_common(1)[0]
    q0, q1 = _qbounds(y, q)
    single = len(qs) == 1
    cs = q0 if single and (s - q0).days <= 3 else s
    ce = q1 if single and (q1 - e).days <= 3 else e
    if single and cs == q0:    # a window that starts mid-quarter (one month, 30 days) is not "Q3"
        label = "Q%d" % q
        full = ce == q1
    else:
        label = ""
        full = False
    return cs, ce, label, full


def _month_starts(s, e):
    out, cur = [], s.replace(day=1)
    while cur <= e:
        out.append(cur)
        cur = (cur.replace(day=28) + 4 * ONE_DAY).replace(day=1)
    return out


def build_qbr(current, prior=None, ad_rows=None, ad_rows_prior=None, deal_rows=None, deal_rows_prior=None, orders=None,
              brand_profile=None, customer_name=None, customer_domain="", compare_label=None, form_label=None,
              prepared_by=None, prepared_for=None, orders_prior=None, **_):
    """Board-ready quarter: leads, spend, cost, customers and revenue against the previous quarter."""
    name = "Quarterly business review"
    cur, pri = list(current or []), list(prior or [])
    cs, ce, qlab, qfull = _coverage(cur)
    ps, pe, plab, _pfull = _coverage(pri) if pri else (None, None, "", False)
    cmp_ = compare_label or plab or (prior_name(ps, pe) if ps else "the previous period")
    m = _meta(brand_profile, customer_name, customer_domain, cmp_, prepared_by, prepared_for)
    if not cur:
        return empty_report(name, m)
    if cs is None:
        return _undated(name, m, cur)
    total = len(cur)
    days_c = (ce - cs).days + 1
    qname = qlab or period_name(cs, ce)
    qname_mid = qname if qlab or is_full_month(cs, ce) else qname[:1].lower() + qname[1:]
    qword = "quarter" if qlab else "period"   # data that is not one calendar quarter reads as a period
    when = "%s %d" % (qlab, ce.year) if qlab else period_label(cs, ce)
    if qlab and not qfull:
        when += " to date"
    kicker = "%s · %s" % (name, when)
    bits = [customer_domain, period_label(cs, ce), "%s submissions" % n(total), _pl(days_c, "day")]
    if total < MIN_LEADS:
        return _thin(name, m, cur, when, "this %s" % qword)
    has_prior = len(pri) >= MIN_LEADS
    days_p = (pe - ps).days + 1 if has_prior else None
    lpd, lpd_p = total / float(days_c), (len(pri) / float(days_p) if has_prior else None)
    same_len = has_prior and abs(days_c - days_p) <= 3
    scale = (days_c / float(days_p)) if has_prior else 1.0    # prior counts scaled to the current length

    def vsp(pv):
        """'182 in Q2', or '140 at Q2's daily pace' when the prior period is a different length."""
        return ("%s in %s" % (n(round(pv)), cmp_)) if same_len else ("%s at %s's daily pace" % (n(round(pv)), cmp_))

    # spend and cost per paid lead, over the dates the ad rows cover
    ads_c = _ads(ad_rows)
    ads_c = _ads_in(ads_c, cs, ce) if ads_c else []
    ads_p = _ads(ad_rows_prior)
    ads_p = _ads_in(ads_p, ps, pe) if ads_p and has_prior else []
    spend_c = round(sum(r.get("spend", 0.0) for r in ads_c), 2)
    spend_p = round(sum(r.get("spend", 0.0) for r in ads_p), 2)
    a0, a1 = _ad_span(ads_c)
    a0, a1 = (a0 or cs), (a1 or ce)
    ad_partial = spend_c > 0 and (a0 > cs + 3 * ONE_DAY or a1 < ce - 3 * ONE_DAY)
    paid_in = [e for e in _between(cur, a0, a1) if lt_group(e) in PAID_GROUPS]
    cpl = spend_c / len(paid_in) if spend_c > 0 and paid_in else None
    b0, b1 = _ad_span(ads_p)
    paid_in_p = [e for e in _between(pri, b0 or ps, b1 or pe) if lt_group(e) in PAID_GROUPS] if spend_p > 0 else []
    cpl_p = spend_p / len(paid_in_p) if spend_p > 0 and paid_in_p else None
    ad_days = (a1 - a0).days + 1
    spd = spend_c / float(ad_days) if spend_c > 0 else None
    spd_p = spend_p / float(((b1 or pe) - (b0 or ps)).days + 1) if spend_p > 0 else None

    # customers and revenue: WooCommerce orders first, else won CRM deals
    sales_c = [s for s in _sales_from_orders(orders) if s["date"] and cs <= s["date"] <= ce and not s["refunded"]
               and not s["void"]] if orders else []
    sales_p = [s for s in _sales_from_orders(orders_prior) if s["date"] and not s["refunded"] and not s["void"]] \
        if orders_prior else []
    deals_c = _deals(deal_rows)
    deals_p = _deals(deal_rows_prior)
    won_c = [dl for dl in deals_c if dl.get("stage") == "won"]
    won_p = [dl for dl in deals_p if dl.get("stage") == "won"]
    if sales_c:
        dcs = [s["date"] for s in sales_c]
    else:
        dcs = [x for x in (_d(dl.get("created")) for dl in deals_c) if x]
        dcs = [x for x in dcs if cs <= x <= ce] or dcs
    # customers and revenue cover only part of the quarter when their dates start or end 4+ days inside it
    deal_partial = bool(dcs) and (min(dcs) > cs + 3 * ONE_DAY or max(dcs) < ce - 3 * ONE_DAY)
    if sales_c:
        cust_label, cust_c, cust_p = "Orders", len(sales_c), (len(sales_p) if len(sales_p) >= MIN_LEADS else None)
        rev_c = sum(s["total"] for s in sales_c)
        rev_p = sum(s["total"] for s in sales_p) if cust_p else None
        rev_src = "WooCommerce"
    elif won_c:
        cust_label, cust_c, cust_p = "New customers", len(won_c), (len(won_p) if won_p else None)
        rev_c = sum(dl.get("amount") or 0.0 for dl in won_c)
        rev_p = sum(dl.get("amount") or 0.0 for dl in won_p) if won_p else None
        rev_src = "CRM"
    else:
        cust_label, cust_c, cust_p, rev_c, rev_p, rev_src = None, 0, None, 0.0, None, None

    chips = {"utmg": "%s leads" % n(total)}
    for plat, v in _spend_sources(ads_c):
        chips[_PLATFORM_KEYS.get(plat, plat)] = "%s spend" % money(v)
    if sales_c:
        chips["woocommerce"] = "%s orders" % n(len(sales_c))
    elif deals_c:
        chips["CRM"] = "%s deals" % n(len(deals_c))
    m["sources"] = sources_meta(**chips)

    # weekly sparks across the quarter
    weeks = _weeks(cs, ce)
    wk_leads = _bucket(cur, weeks, _day)
    wk_spend = _bucket(ads_c, weeks, lambda r: _d(r.get("date")), lambda r: r.get("spend", 0.0)) if spend_c else []
    wk_paid = _bucket([e for e in cur if lt_group(e) in PAID_GROUPS], weeks, _day)
    wk_cpl = [round(s_ / p_, 2) for s_, p_ in zip(wk_spend, wk_paid) if s_ > 0 and p_] if spend_c else []
    if sales_c:
        wk_rev = _bucket(sales_c, weeks, lambda s: s["date"], lambda s: s["total"])
        wk_cust = _bucket(sales_c, weeks, lambda s: s["date"])
    else:
        wk_rev = _bucket(won_c, weeks, lambda dl: _d(dl.get("closed")) or _d(dl.get("created")),
                         lambda dl: dl.get("amount") or 0.0)
        wk_cust = _bucket(won_c, weeks, lambda dl: _d(dl.get("closed")) or _d(dl.get("created")))

    def trim(sp):
        sp = list(sp)
        while sp and not sp[0]:
            sp.pop(0)
        return [round(x, 2) for x in sp] if len(sp) >= 2 else None

    # channels and campaigns
    G = Counter(lt_group(e) for e in cur)
    Gp = Counter(lt_group(e) for e in pri) if has_prior else Counter()
    gorder = _gsort(set(G) | set(Gp), lambda x: G[x])
    camps = Counter(_camp(e) for e in cur if _camp(e))
    camps_p = Counter(_camp(e) for e in pri if _camp(e)) if has_prior else Counter()
    rates = []
    if has_prior:
        for gname in gorder:
            a, b = G[gname] / float(days_c), Gp[gname] / float(days_p)
            rates.append((gname, a, b, _growth(a, b)))
    grow = sorted([x for x in rates if x[2] > 0 and G[x[0]] >= 20], key=lambda x: -(x[1] - x[2]))
    shrink = sorted([x for x in rates if x[2] > 0 and Gp[x[0]] >= 20], key=lambda x: (x[1] - x[2]))

    # headline
    g_lpd = _growth(lpd, lpd_p) if has_prior else None
    if g_lpd is not None and abs(g_lpd) >= 3:
        more = "more" if g_lpd > 0 else "fewer"
        if same_len:
            g_tot = _growth(total, len(pri))
            headline = "%s brought *%s*, %s %s than %s." % (qname, _pl(total, "lead"), _sp(g_tot).lstrip("+" + MINUS),
                                                           "more" if g_tot > 0 else "fewer", cmp_)
        else:
            headline = "%s brought *%s*, %s %s a day than %s." % (qname, _pl(total, "lead"),
                                                                 _sp(g_lpd).lstrip("+" + MINUS), more, cmp_)
    elif has_prior:
        headline = "%s held lead flow steady at *%s* a day." % (qname, _pl(lpd, "lead") if lpd == int(lpd) else
                                                              "%s leads" % _day_rate(lpd))
    else:
        headline = "%s brought *%s* in %s." % (qname, _pl(total, "lead"), _pl(days_c, "day"))
    top = gorder[0]
    sub = ["%s sent the most leads (%s)." % (top, pct(share(G[top], total)))]
    if cpl is not None:
        sub.append("%s in ad spend bought paid leads at %s each%s." % (money(spend_c), money(cpl),
                                                                       " (%s)" % period_label(a0, a1) if ad_partial else ""))
    if cust_label and rev_c:
        sub.append("%s %s brought %s." % (n(cust_c), cust_label.lower(), money(rev_c)))
    if has_prior and not same_len:
        sub.append("%s covers %s against %s here, so we compare per-day rates." % (_cap(cmp_), _pl(days_p, "day"), n(days_c)))

    def kdelta(cur_v, prev_v):
        """Per-day comparison when the periods differ in length, else totals."""
        if prev_v is None:
            return None
        return prev_v if same_len else prev_v * scale

    stats = [stat("Leads", n(total), total, kdelta(total, len(pri)) if has_prior else None, spark=trim(wk_leads),
                  note=("%s in %s" % (n(len(pri)), cmp_)) if has_prior else "%s days" % n(days_c)),
             stat("Leads per day", _day_rate(lpd), lpd, lpd_p, note=("%s in %s" % (_day_rate(lpd_p), cmp_)) if has_prior else None)]
    if spend_c > 0:
        stats.append(stat("Ad spend", money(spend_c), spd, spd_p, good="neutral", spark=trim(wk_spend),
                          note=("%s only" % period_label(a0, a1)) if ad_partial else
                          ("%s a day" % money(spd))))
        if cpl is not None:
            stats.append(stat("Cost per paid lead", money(cpl), cpl, cpl_p, good="down", spark=trim(wk_cpl),
                              note="%s paid leads" % n(len(paid_in))))
    if cust_label:
        stats.append(stat(cust_label, n(cust_c), cust_c, kdelta(cust_c, cust_p) if cust_p and not deal_partial else None,
                          spark=trim(wk_cust), source=rev_src,
                          note=("%s only" % period_label(min(dcs), max(dcs))) if deal_partial
                          else (("%s in %s" % (n(cust_p), cmp_)) if cust_p else None)))
        if rev_c:
            stats.append(stat("Revenue", money(rev_c), rev_c, kdelta(rev_c, rev_p) if rev_p and not deal_partial else None,
                              spark=trim(wk_rev), source=rev_src,
                              note=("%s per %s" % (money(rev_c / cust_c), "order" if sales_c else "customer"))))
    stats = stats[:6]
    secs = [{"type": "title-block", "kicker": kicker, "title": headline, "subtitle": " ".join(sub),
             "meta_bits": [b for b in bits if b]},
            {"type": "stat-strip", "stats": stats}]
    if grow:
        gname, a, b, gg = grow[0]
        body = ["It went from %s to %s leads a day against %s." % (_day_rate(b), _day_rate(a), cmp_)]
        if shrink and shrink[0][1] < shrink[0][2]:
            s_ = shrink[0]
            body.append("%s fell the most: %s to %s a day." % (s_[0], _day_rate(s_[2]), _day_rate(s_[1])))
        secs.append({"type": "insight-card", "kicker": "The %s in one line" % qword,
                     "title": "*%s* grew the most, %s a day on %s." % (gname, _sp(gg), cmp_), "body": body})
    else:
        top = gorder[0]
        secs.append({"type": "insight-card", "kicker": "The %s in one line" % qword,
                     "title": "*%s* carried %s of the %s's leads." % (top, pct(share(G[top], total)), qword),
                     "body": ["%s sent %s of %s leads." % (top, n(G[top]), n(total))]})

    # 01 month by month
    months = _month_starts(cs, ce)
    cats, folded = _fold(_gsort(G, lambda x: G[x]), 6)
    if folded:
        cats = cats + ["Other"]
    mlabels, mgroups = [], []
    for ms in months:
        me = min((ms.replace(day=28) + 4 * ONE_DAY).replace(day=1) - ONE_DAY, ce)
        ms_ = max(ms, cs)
        part = ms_ != ms or me != (ms.replace(day=28) + 4 * ONE_DAY).replace(day=1) - ONE_DAY
        mlabels.append(ms.strftime("%b") + (" (%d days)" % ((me - ms_).days + 1) if part else ""))
        cnt = Counter(folded.get(lt_group(e), lt_group(e)) for e in _between(cur, ms_, me))
        mgroups.append([cnt.get(c, 0) for c in cats])
    if len(months) >= 2:
        firsts, lasts = mgroups[0], mgroups[-1]
        mv = max(range(len(cats)), key=lambda i: lasts[i] - firsts[i])
        dn = min(range(len(cats)), key=lambda i: lasts[i] - firsts[i])
        it = ("*%s* rose from %s to %s a month." % (cats[mv], n(firsts[mv]), n(lasts[mv]))
              if lasts[mv] - firsts[mv] >= 5 else "Every channel held *steady* month to month.")
        body = ["%s went from %s in %s to %s in %s." % (cats[dn], n(firsts[dn]), mlabels[0], n(lasts[dn]), mlabels[-1])] \
            if firsts[dn] - lasts[dn] >= 5 else ["No channel lost more than 4 leads a month."]
        if any("days)" in x for x in mlabels):
            body.append("Months marked with days are part months.")
        secs.append({"type": "section-header", "number": "01", "kicker": "Month by month",
                     "title": "Every *month* of the %s, by channel." % qword})
        # full width so every channel name fits under its bars
        secs.append({"type": "chart",
                     "chart": {"type": "bar-grouped", "labels": cats,
                               "groups": [{"label": mlabels[i], "values": mgroups[i]} for i in range(len(months))]},
                     "chart_title": "Leads per month, by *channel*",
                     "caption": "Leads per month by last-touch channel"})
        secs.append({"type": "insight-card", "kicker": "The movers", "title": it, "body": body})
        nxt = 2
    else:
        nxt = 1

    # 02 share shift
    if has_prior:
        shift = [(gname, share(G[gname], total) - share(Gp[gname], len(pri))) for gname in gorder]
        shift = [x for x in shift if abs(x[1]) >= 0.05][:8]
        shift.sort(key=lambda x: -x[1])
        if shift:
            up_, dn_ = shift[0], shift[-1]
            secs.append({"type": "section-header", "number": "%02d" % nxt, "kicker": "Channel mix",
                         "title": "How the *mix* moved against %s." % cmp_,
                         "dek": "%s gained the most share (%s pts); %s gave up the most (%s pts)." % (
                             up_[0], ("+%.1f" % up_[1]), dn_[0], ("%s%.1f" % (MINUS, abs(dn_[1]))))})
            secs.append({"type": "chart", "chart": {"type": "bar-diverging", "labels": [x[0] for x in shift],
                                                    "values": [round(x[1], 1) for x in shift], "good": "up"},
                         "chart_title": "Change in share of leads, in *points*",
                         "caption": "Each channel's share of %s leads minus its share of %s leads." % (qname_mid, cmp_)})
            nxt += 1

    # 03 campaigns
    rows = []
    for i, (c, v) in enumerate(camps.most_common(10)):
        pv = camps_p.get(c, 0)
        pvs = pv * scale if has_prior else 0
        rows.append({"rank": str(i + 1), "campaign": _safe(pretty(c), 40), "tag": _safe(c, 40),
                     "leads": {"value": v, "label": n(v)}, "share": pct(share(v, total)),
                     "change": _delta_cell(v, pvs) if has_prior else {"label": "–", "direction": "flat"},
                     "status": _badge(v, int(round(pvs))) if has_prior else {"label": "–", "tone": "neutral"}})
    if rows:
        secs.append({"type": "section-header", "number": "%02d" % nxt, "kicker": "Campaigns",
                     "title": "The %s's top *campaigns*." % qword})
        secs.append({"type": "ranked-list", "title": "Top *campaigns* by leads",
                     "columns": [{"key": "rank", "label": "#", "type": "rank"},
                                 {"key": "campaign", "label": "Campaign", "type": "name"},
                                 {"key": "tag", "label": "utm_campaign", "type": "source"},
                                 {"key": "leads", "label": "Leads", "type": "bar"},
                                 {"key": "share", "label": "Share", "type": "pct", "align": "right"},
                                 {"key": "change", "label": "vs %s" % cmp_, "type": "delta", "align": "right"},
                                 {"key": "status", "label": "Status", "type": "badge"}],
                     "rows": rows,
                     "caption": ("Change is per day: %s is scaled to %s days." % (cmp_, n(days_c)))
                     if has_prior and not same_len else
                     "%s of leads carried a campaign tag." % pct(share(sum(camps.values()), total))})
        nxt += 1

    # 04 wins and risks
    wins, risks = [], []
    if g_lpd is not None and g_lpd >= 5:
        wins.append({"label": "Lead flow grew", "value": _sp(g_lpd), "status": "pass",
                     "detail": "%s leads a day against %s in %s." % (_day_rate(lpd), _day_rate(lpd_p), cmp_)})
    if cpl is not None and cpl_p and cpl <= 0.95 * cpl_p:
        wins.append({"label": "Paid leads got cheaper", "value": money(cpl), "status": "pass",
                     "detail": "Down from %s per paid lead in %s." % (money(cpl_p), cmp_)})
    if grow:
        gname, a, b, gg = grow[0]
        wins.append({"label": "%s grew the most" % gname, "value": _sp(gg), "status": "pass",
                     "detail": "%s leads a day, up from %s." % (_day_rate(a), _day_rate(b))})
    rising_c = sorted([(c, v, camps_p.get(c, 0) * scale) for c, v in camps.most_common(15)
                       if has_prior and camps_p.get(c, 0) and v >= 1.25 * camps_p[c] * scale
                       and v - camps_p[c] * scale >= 10], key=lambda x: -(x[1] - x[2]))   # biggest gain first
    if rising_c:
        c, v, pv = rising_c[0]
        wins.append({"label": "%s took off" % _safe(pretty(c), 44), "value": _sp(_growth(v, pv)), "status": "pass",
                     "detail": "%s leads against %s." % (n(v), vsp(pv))})
    if cust_c and cust_p and not deal_partial and cust_c >= 1.05 * cust_p * (1 if same_len else scale):
        wins.append({"label": "%s up" % cust_label, "value": n(cust_c), "status": "pass",
                     "detail": "Against %s in %s." % (n(cust_p), cmp_)})
    if g_lpd is not None and g_lpd <= -5:
        risks.append({"label": "Lead flow fell", "value": _sp(g_lpd), "status": "fail" if g_lpd <= -15 else "warn",
                      "detail": "%s leads a day against %s in %s." % (_day_rate(lpd), _day_rate(lpd_p), cmp_)})
    if cpl is not None and cpl_p and cpl >= 1.1 * cpl_p:
        risks.append({"label": "Paid leads cost more", "value": money(cpl), "status": "warn",
                      "detail": "Up from %s per paid lead in %s." % (money(cpl_p), cmp_)})
    falling_c = sorted([(c, v, pv * scale) for c, pv in camps_p.most_common(15)
                        for v in [camps.get(c, 0)] if has_prior and pv * scale >= 20 and v <= 0.6 * pv * scale],
                       key=lambda x: x[1] - x[2])   # biggest loss first
    if falling_c:
        c, v, pv = falling_c[0]
        risks.append({"label": "%s stalled" % _safe(pretty(c), 44), "value": _sp(_growth(v, pv)), "status": "fail",
                      "detail": "%s leads against %s. Check the ad, the offer and the landing page." % (
                          n(v), vsp(pv))})
    slowed = sorted([x for x in rates if Gp[x[0]] >= 20 and x[1] <= 0.8 * x[2]], key=lambda x: x[1] - x[2])
    if slowed:
        gname, a, b, gg = slowed[0]
        risks.append({"label": "%s slowed" % gname, "value": _sp(gg), "status": "warn",
                      "detail": "%s leads a day, down from %s." % (_day_rate(a), _day_rate(b))})
    top = gorder[0]
    if share(G[top], total) >= 50:
        risks.append({"label": "One channel carries half", "value": pct(share(G[top], total)), "status": "warn",
                      "detail": "%s sends %s of leads. A single platform change would hit lead flow hard." % (
                          top, pct(share(G[top], total)))})
    untag = sum(1 for e in cur if not _src(e))
    if share(untag, total) >= 15:
        risks.append({"label": "Leads without a source", "value": pct(share(untag, total)), "status": "warn",
                      "detail": "%s leads carried no utm_source, so no channel gets credit." % n(untag)})
    # within the quarter: a top campaign whose daily rate in the last month is 40%+ below the first month
    mwin = []
    for ms in _month_starts(cs, ce):
        me = min((ms.replace(day=28) + 4 * ONE_DAY).replace(day=1) - ONE_DAY, ce)
        mwin.append((max(ms, cs), me))
    fading, part = [], False
    if len(mwin) >= 2:
        (f0, f1), (l0, l1) = mwin[0], mwin[-1]
        fd, ld = (f1 - f0).days + 1, (l1 - l0).days + 1
        full = lambda s_, e_: s_.day == 1 and (e_ + ONE_DAY).day == 1  # noqa: E731
        part = not (full(f0, f1) and full(l0, l1))
        for c, _cnt in camps.most_common(15):
            a = sum(1 for e in _between(cur, f0, f1) if _camp(e) == c)
            b = sum(1 for e in _between(cur, l0, l1) if _camp(e) == c)
            # whole months compare counts; a part month compares leads per day
            ra, rb = (a / float(fd), b / float(ld)) if part else (a, b)
            if a >= 15 and rb <= 0.6 * ra:
                fading.append((c, a, b, _growth(rb, ra)))
        fading.sort(key=lambda x: x[3])
    falling_names = set(x[0] for x in falling_c)
    for c, a, b, gg in fading[:1]:
        if c in falling_names:
            continue
        risks.append({"label": "%s faded during the %s" % (_safe(pretty(c), 44), qword), "value": _sp(gg),
                      "status": "warn",
                      "detail": "%s leads in %s, %s in %s%s. Check whether the ad or offer has worn out." % (
                          n(a), mwin[0][0].strftime("%B"), n(b), mwin[-1][0].strftime("%B"),
                          " (compared per day: part months)" if part else "")})
    if ad_partial:
        risks.append({"label": "Spend covers part of the %s" % qword, "value": n(ad_days) + " days", "status": "info",
                      "detail": "Ad rows run %s, so cost per lead uses that window only." % period_label(a0, a1)})
    held = [x for x in rates if Gp[x[0]] >= 20]
    if has_prior and held and not slowed and not any(r["status"] in ("fail", "warn") for r in risks):
        risks.append({"label": "Every channel held its pace", "value": "%s of %s" % (n(len(held)), n(len(held))),
                      "status": "info",
                      "detail": "Each channel with 20 or more leads in %s kept at least 80%% of its daily rate." % cmp_})
    risks.sort(key=lambda r: {"fail": 0, "warn": 1, "info": 2}.get(r["status"], 3))
    items = wins[:3] + risks[:3]
    if items:
        secs.append({"type": "section-header", "number": "%02d" % nxt, "kicker": "Wins and risks",
                     "title": "What went *right* and what to watch.",
                     "dek": "Wins first, then the numbers to watch next quarter."})
        secs.append({"type": "scorecard", "items": items})
        nxt += 1

    # 05 next quarter
    recs = []
    if rising_c:
        c, v, pv = rising_c[0]
        recs.append({"label": "Scale", "title": "Scale *%s* while it climbs" % _safe(pretty(c), 48),
                     "body": "It brought %s against %s. Raise its budget in steps and watch cost per lead." % (
                         _pl(v, "lead"), vsp(pv)), "impact": "High", "effort": "Medium"})
    elif grow:
        gname, a, b, gg = grow[0]
        recs.append({"label": "Scale", "title": "Put more behind *%s*" % gname,
                     "body": "It grew %s a day against %s, to %s leads a day." % (_sp(gg), cmp_, _day_rate(a)),
                     "impact": "High", "effort": "Medium"})
    if falling_c:
        c, v, pv = falling_c[0]
        recs.append({"label": "Fix", "title": "Fix or replace *%s*" % _safe(pretty(c), 48),
                     "body": "It fell to %s against %s. Refresh the ad and offer, or move its budget to what is "
                             "growing." % (_pl(v, "lead"), vsp(pv)), "impact": "High", "effort": "Medium"})
    elif fading:
        c, a, b, gg = fading[0]
        recs.append({"label": "Fix", "title": "Refresh *%s* before it fades further" % _safe(pretty(c), 48),
                     "body": "It went from %s in %s to %s in %s. Test a new ad or offer before you move its "
                             "budget." % (
                                 _pl(a, "lead"), mwin[0][0].strftime("%B"), n(b), mwin[-1][0].strftime("%B")),
                     "impact": "Medium", "effort": "Medium"})
    if share(G[top], total) >= 50:
        second = gorder[1] if len(gorder) > 1 else None
        recs.append({"label": "Protect", "title": "Build a second *channel* beside %s" % top,
                     "body": "%s carries %s of leads.%s" % (
                         top, pct(share(G[top], total)),
                         (" %s is next at %s; test one new campaign there." % (second, pct(share(G[second], total))))
                         if second else ""), "impact": "Medium", "effort": "Medium"})
    if G.get(G_AI) and Gp.get(G_AI) and G[G_AI] / float(days_c) > Gp[G_AI] / float(days_p) * 1.2:
        recs.append({"label": "Grow", "title": "Keep your pages easy for *AI assistants* to cite",
                     "body": "AI assistants sent %s this %s against %s. Clear answers, prices and FAQs keep "
                             "them coming." % (_pl(G[G_AI], "lead"), qword, vsp(Gp[G_AI] * scale)), "impact": "Medium",
                     "effort": "Medium"})
    if share(untag, total) >= 15:
        recs.append({"label": "Track", "title": "Tag every link before next *quarter*",
                     "body": "%s of leads arrived with no utm_source. Tag ads, emails and posts so every channel "
                             "gets credit." % pct(share(untag, total)), "impact": "Medium", "effort": "Low"})
    if ad_partial or (cust_label and deal_partial):
        recs.append({"label": "Track", "title": "Connect a full quarter of *spend* and sales",
                     "body": "Spend or sales here cover only part of the " + qword + ", so cost and close rates are partial. "
                             "Connect the full quarter for the next review.", "impact": "Medium", "effort": "Low"})
    if len(recs) < 2:
        recs.append({"label": "Grow", "title": "Feed *%s*, your biggest channel" % top,
                     "body": "It sent %s of the %s's leads. Test one new offer there each month." % (pct(share(G[top], total)), qword),
                     "impact": "Medium", "effort": "Medium"})
    if len(recs) < 2:
        recs.append({"label": "Review", "title": "Review this *scorecard* monthly",
                     "body": "Leads per day, cost per paid lead and the top campaigns, every month, so the next quarter "
                             "has no surprises.", "impact": "Low", "effort": "Low"})
    secs.append({"type": "section-header", "number": "%02d" % nxt, "kicker": "Next quarter",
                 "title": "The *plan* for next quarter."})
    secs.append({"type": "recommendations", "items": recs[:5]})
    notes = ["Leads: %s UTM Grabber submissions dated %s%s." % (
        n(total), period_label(cs, ce), (", against %s in %s (%s)" % (n(len(pri)), cmp_, period_label(ps, pe))) if has_prior else "")]
    if has_prior and not same_len:
        notes.append("%s covers %s and this %s %s, so changes compare per-day rates." % (
            _cap(cmp_), _pl(days_p, "day"), qword, _pl(days_c, "day")))
    notes.append("Channels use the converting visit (last touch). Paid leads are paid search, paid social and other "
                 "paid clicks.")
    if spend_c > 0:
        notes.append("Cost per paid lead: ad spend divided by paid leads over %s, the dates the ad rows cover." %
                     period_label(a0, a1))
    else:
        notes.append("Ad spend was not connected, so spend and cost per lead are not shown.")
    if sales_c:
        notes.append("Orders and revenue: completed and processing WooCommerce orders in the %s, refunds left out%s." % (
            qword, (" (orders dated %s)" % period_label(min(dcs), max(dcs))) if deal_partial else ""))
    elif cust_label:
        notes.append("New customers and revenue: won CRM deals%s." % (
            (" created %s; the rest of the %s is not in the deal rows" % (period_label(min(dcs), max(dcs)), qword))
            if deal_partial else ""))
    secs.append({"type": "notes", "title": "How we built this report", "items": notes})
    r0 = recs[0]
    if r0["title"].startswith("Scale") and rising_c:
        c, v, pv = rising_c[0]
        ctitle = "Next quarter: scale *%s*. It brought %s against %s." % (
            _safe(pretty(c), 48), _pl(v, "lead"), vsp(pv))
    elif r0["title"].startswith("Put more") and grow:
        ctitle = "Next quarter: put more behind *%s*. It grew %s a day." % (grow[0][0], _sp(grow[0][3]))
    elif r0["title"].startswith("Fix") and falling_c:
        c, v, pv = falling_c[0]
        ctitle = "Next quarter: fix *%s*. It fell to %s against %s." % (
            _safe(pretty(c), 48), _pl(v, "lead"), vsp(pv))
    elif r0["title"].startswith("Refresh") and fading:
        c, a, b, gg = fading[0]
        ctitle = "Next quarter: refresh *%s*. It fell from %s in %s to %s in %s." % (
            _safe(pretty(c), 48), _pl(a, "lead"), mwin[0][0].strftime("%B"), n(b), mwin[-1][0].strftime("%B"))
    else:
        ctitle = "Next quarter: feed *%s*. It sent %s of the %s's leads." % (top, pct(share(G[top], total)), qword)
    summ = [{"value": n(total), "label": "Leads"}, {"value": _day_rate(lpd), "label": "Leads per day"}]
    if cpl is not None:
        summ.append({"value": money(cpl), "label": "Cost per paid lead"})
    if cust_label and rev_c:
        summ.append({"value": money(rev_c), "label": "Revenue"})
    elif cust_label:
        summ.append({"value": n(cust_c), "label": cust_label})
    secs.append({"type": "closing", "kicker": "The %s in one line" % qword, "title": ctitle, "summary_stats": summ[:4],
                 "bullets": [x for x in [
                     ("%s against %s in %s." % (_pl(total, "lead"), n(len(pri)), cmp_)) if has_prior else None,
                     ("Top campaign: %s with %s." % (pretty(camps.most_common(1)[0][0]),
                                                     _pl(camps.most_common(1)[0][1], "lead"))) if camps else None,
                     "Biggest channel: %s, %s of leads." % (top, pct(share(G[top], total)))] if x]})
    return {"meta": m, "sections": secs}


REGISTRY = {
    "ai-referrals": build_ai_referrals, "ai-assistants": build_ai_referrals, "ai-search": build_ai_referrals,
    "chatgpt": build_ai_referrals, "llm-referrals": build_ai_referrals,
    "journey": build_journey, "customer-journey": build_journey, "first-to-last": build_journey,
    "multi-touch": build_journey, "attribution-paths": build_journey,
    "revenue": build_revenue, "revenue-by-source": build_revenue, "woocommerce": build_revenue,
    "sales-by-source": build_revenue,
    "daily-pulse": build_daily_pulse, "pulse": build_daily_pulse, "daily": build_daily_pulse,
    "morning-pulse": build_daily_pulse, "yesterday": build_daily_pulse,
    "lead-timing": build_lead_timing, "timing": build_lead_timing, "when": build_lead_timing,
    "dayparting": build_lead_timing, "best-time": build_lead_timing,
    "qbr": build_qbr, "quarterly": build_qbr, "quarterly-business-review": build_qbr, "board": build_qbr,
    "quarter": build_qbr,
}
