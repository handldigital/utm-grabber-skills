"""
Cross-platform v2 recipes: UTM Grabber leads joined to ad spend (Google Ads, Meta
Ads, Microsoft Ads ...), Google Analytics 4 sessions, CRM deals (HubSpot,
Salesforce, Pipedrive) and store orders (WooCommerce).

    full-funnel       sessions -> leads -> deals -> customers -> revenue, by channel
    true-roas         which ads brought customers: cost per lead, customers, ROAS per ad
    conversion-truth  what ad platforms report vs the leads your forms actually got
    traffic-to-lead   traffic that visits but never converts (channels and pages)
    pipeline          close rate, revenue and days to close by first-touch channel
    wasted-spend      search terms and ads that spend without bringing leads

Same pattern as core.build_monthly:
  1. Guard empty input -> common.empty_report(). Fewer than 10 leads, or the one
     source a report cannot work without is missing -> a short, honest version.
  2. Every number comes from the rows passed in. A source that is not connected is
     never estimated: its stage, column or chart is dropped and the notes say
     "Connect X to add Y".
  3. Outcome-first headline with exactly one *accent*.
  4. Every report ends with a notes section (sources, window, how rows were
     matched, match rates) before the closing.

Connector rows may be raw connector payloads or already normalized (the
normalizers in connectors.py are applied here; orders are detected either way).
"""
import datetime as _dt
import re
from collections import Counter, OrderedDict, defaultdict
from statistics import median

try:  # Python 3
    from urllib.parse import parse_qs, urlparse
except ImportError:  # pragma: no cover
    from urlparse import parse_qs, urlparse

from .common import (MINUS, daily_counts, empty_report, entry_dt, first_touch, get_field, last_touch,
                     lead_campaign, lead_content, lead_email, lead_platform, lead_term, meta, money, n, norm_key, pct,
                     period_label, period_name, prior_name, safe_div, share, span, sources_meta, stat)
from connectors import (normalize_ad_rows, normalize_deal_rows, normalize_orders,  # noqa: E402
                        normalize_visit_rows)

MIN_LEADS = 10          # below this a report switches to its short, honest version
MAX_ROWS = 12           # table rows
AD_PLATFORMS = ("Google Ads", "Meta Ads", "Microsoft Ads", "LinkedIn Ads", "TikTok Ads")
SEARCH_PLATFORMS = ("Google Ads", "Microsoft Ads")
NON_PAID = ("Organic", "Social", "Referral", "Direct")
NO_LEAD = "No form lead"
OTHER_PAID = "Other paid"
_ONE_DAY = _dt.timedelta(days=1)

# ---------------------------------------------------------------------------
# text and number helpers
# ---------------------------------------------------------------------------
_BAD = {"None": "none", "NaN": "n/a", "null": "empty", "undefined": "not set"}


def _safe(s, limit=None):
    """User data -> display text: no em or en dashes, no stray accents, no literal None."""
    s = re.sub(r"\s+", " ", str(s if s is not None else "")).strip()
    s = re.sub("\\s*[\u2014\u2013]\\s*", " - ", s).replace("*", "")
    s = re.sub(r"\b(None|NaN|null|undefined)\b", lambda mm: _BAD[mm.group(1)], s)
    if limit and len(s) > limit:
        s = s[:limit - 1].rstrip(" -,.") + "…"
    return s


def _pl(k, word, many=None):
    return "%s %s" % (n(k), word if k == 1 else (many or word + "s"))


def _money(v, decimals=None):
    """common.money, but a zero reads '$0' instead of '$0.00'."""
    if v is not None and abs(v) < 0.005:
        return "$0"
    return money(v, decimals)


def _cap(s):
    s = str(s or "")
    return s[:1].upper() + s[1:]


def _md(d):
    return "%s %d" % (d.strftime("%b"), d.day)


def _days(start, end):
    return (end - start).days + 1 if start and end else 0


def _kick(name, start, end):
    p = period_label(start, end)
    return "%s · %s" % (name, p) if p else name


def _in_period(start, end):
    """'in September', 'in the last 30 days', 'this week'."""
    if start and end and start == end:
        return "on %s" % _md(start)
    nm = period_name(start, end)
    if nm == "This week":
        return "this week"
    if nm == "This period":
        return "in this period"
    if nm.startswith("The "):
        return "in t" + nm[1:]
    return "in " + nm


def _lead_in(start, end):
    """Sentence opener: 'September' / 'The last 30 days'."""
    return period_name(start, end)


def _x(v):
    """ROAS as a multiple: 3.14 -> '3.1x'."""
    return "–" if v is None else ("%.1fx" % v)


def _per1(v):
    """ROAS as money back per dollar: 3.14 -> '$3.14'."""
    return "–" if v is None else "$%.2f" % v


def _date(v):
    if not v:
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    m = re.match(r"(\d{4})-?(\d{2})-?(\d{2})", str(v))
    if not m:
        return None
    try:
        return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _range_text(dates):
    ds = sorted(d for d in dates if d)
    if not ds:
        return ""
    return period_label(ds[0], ds[-1]) if ds[0] != ds[-1] else "%s, %d" % (_md(ds[0]), ds[0].year)


def _kpi(label, value, cur=None, prev=None, kind="pct", good="up", spark=None, source=None, note=None, unit_fmt=None):
    """stat() without a misleading 'New' pill when the prior value is zero or missing."""
    if prev is None or cur is None or (kind == "pct" and not prev):
        return stat(label, value, good=good, spark=spark, source=source, note=note)
    return stat(label, value, cur, prev, kind=kind, good=good, spark=spark, source=source, note=note,
                unit_fmt=unit_fmt)


def _spark(vals):
    """8 to 30 points, oldest first: daily values, folded into weeks for long windows."""
    vals = [v for v in (vals or [])]
    if len(vals) > 31:
        vals = [sum(vals[i:i + 7]) for i in range(0, len(vals), 7)]
    if len(vals) < 8 or not any(vals):
        return None
    return [round(v, 2) if isinstance(v, float) else v for v in vals]


def _median(vals):
    vals = [v for v in vals if v is not None]
    return median(vals) if vals else None


# ---------------------------------------------------------------------------
# connector rows -> normalized rows
# ---------------------------------------------------------------------------
_PLATFORM_ALIASES = (
    ("Google Ads", ("google", "googleads", "adwords", "googleadwords", "googlecpc", "googlesearch", "gads", "youtube",
                    "youtubeads", "dv360")),
    ("Microsoft Ads", ("bing", "bingads", "microsoft", "microsoftads", "msads", "microsoftadvertising")),
    ("Meta Ads", ("facebook", "fb", "instagram", "ig", "meta", "metaads", "facebookads", "instagramads",
                  "audiencenetwork", "messenger")),
    ("LinkedIn Ads", ("linkedin", "linkedinads")),
    ("TikTok Ads", ("tiktok", "tiktokads")),
)


def _canon_platform(s):
    k = norm_key(s).replace("_", "")
    if not k:
        return None
    for name, aliases in _PLATFORM_ALIASES:
        if k in aliases or k == norm_key(name).replace("_", ""):
            return name
    return None


def _named(r):
    """GAQL-style rows nest names ({"campaign": {"name": ...}}); lift them so the normalizer reads text."""
    fix = {}
    for k in ("campaign", "ad_group", "ad", "adset", "keyword"):
        v = r.get(k)
        if isinstance(v, dict):
            fix[k] = v.get("name") or v.get("text") or ""
    return dict(r, **fix) if fix else r


def _ads(rows):
    """Normalized AdRow list with canonical platform names (normalize_ad_rows is idempotent)."""
    if not rows:
        return []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            nr = normalize_ad_rows([_named(r)])[0]
        except Exception:
            continue
        nr["platform"] = _canon_platform(nr.get("platform")) or _safe(nr.get("platform") or "Ads", 24)
        out.append(nr)
    return out


def _visits(rows):
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        try:
            out.extend(normalize_visit_rows([r]))
        except Exception:
            continue
    return out


def _deals(rows):
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        try:
            out.extend(normalize_deal_rows([r]))
        except Exception:
            continue
    return out


_PAID_STATUS = {"completed", "complete", "processing", "paid", "succeeded", "success", "settled", "fulfilled"}


def _orders(rows):
    """Raw WooCommerce entries or normalized OrderRows -> OrderRows with a _paid flag."""
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if "total" in r and ("traffic_source" in r or "source" in r) and "Order Total" not in r:
            o = dict(r)
        else:
            try:
                nn = normalize_orders([r])
            except Exception:
                nn = []
            if not nn:
                continue
            o = nn[0]
        st = str(o.get("status") or "completed").lower().replace("wc-", "").strip()
        o["_paid"] = st in _PAID_STATUS
        try:
            o["total"] = float(o.get("total") or 0.0)
        except (TypeError, ValueError):
            o["total"] = 0.0
        out.append(o)
    return out


# ---------------------------------------------------------------------------
# channels: one row key for leads, sessions, deals and orders
# ---------------------------------------------------------------------------
_PAID_MEDIUMS = {"cpc", "ppc", "paid", "paid_search", "paidsearch", "paid-search", "paid_social", "paidsocial",
                 "paid-social", "cpm", "cpv", "display", "paid_video"}
_SOCIAL_MEDIUMS = {"social", "organic_social", "social-network", "social_network", "social-media", "social_media", "sm"}
_EMAIL_MEDIUMS = {"email", "e-mail", "newsletter", "mail"}
_REFERRAL_MEDIUMS = {"referral", "partner", "affiliate"}
_SEARCH = {"google", "bing", "duckduckgo", "yahoo", "ecosia", "brave", "baidu", "yandex", "search.brave.com"}
_SOCIAL_SOURCES = {"facebook", "instagram", "tiktok", "pinterest", "linkedin", "twitter", "x", "t.co", "youtube",
                   "reddit", "threads", "snapchat", "fb", "ig", "lnkd.in", "m.facebook.com", "l.facebook.com",
                   "lm.facebook.com", "facebook.com", "instagram.com", "linkedin.com", "pinterest.com",
                   "youtube.com", "reddit.com", "tiktok.com", "threads.net", "x.com", "twitter.com"}
_AI_SOURCES = ("chatgpt", "openai", "perplexity", "gemini", "claude.ai", "copilot", "bard", "you.com", "phind")


def _plat(e):
    """The ad platform behind a lead (or an order / pseudo entry), else None."""
    p = lead_platform(e)
    return p if p in AD_PLATFORMS else None


def _lead_row(e):
    """Lead -> 'Google Ads' / 'Meta Ads' / ... or its UTM Grabber channel (last touch)."""
    p = _plat(e)
    if p:
        return p
    ch = last_touch(e)
    return OTHER_PAID if ch == "Paid" else (ch if ch in NON_PAID else "Direct")


def _source_platform(base):
    """'google' / 'm.facebook.com' / 'bing' -> the ad platform, else None."""
    p = _canon_platform(base)
    if p:
        return p
    for part in base.split("."):
        p = _canon_platform(part)
        if p:
            return p
    return None


def _visit_row(v):
    """GA4 session source / medium -> the same row keys, mirroring UTM Grabber's channel rules
    (AI assistants count as Organic, email as Referral, organic social as Social)."""
    src = str(v.get("source") or "").strip().lower()
    med = str(v.get("medium") or "").strip().lower()
    base = src.split("/")[0]
    if base.startswith("www."):
        base = base[4:]
    if med in _PAID_MEDIUMS:
        return _source_platform(base) or OTHER_PAID
    if base in ("(direct)", "direct", "") and med in ("(none)", "(not set)", "none", ""):
        return "Direct"
    if med in _SOCIAL_MEDIUMS or base in _SOCIAL_SOURCES:
        return "Social"
    if any(a in base for a in _AI_SOURCES):
        return "Organic"
    if med == "organic" or base in _SEARCH:
        return "Organic"
    if med in _EMAIL_MEDIUMS or med in _REFERRAL_MEDIUMS:
        return "Referral"
    return "Direct" if base in ("(not set)", "(direct)") else "Referral"


def _order_pseudo(o):
    return {"utm_source": o.get("source", ""), "utm_medium": o.get("medium", ""), "utm_campaign": o.get("campaign", ""),
            "utm_content": o.get("content", ""), "gclid": o.get("gclid", ""), "fbclid": o.get("fbclid", ""),
            "traffic_source": o.get("traffic_source", "")}


def _order_row(o):
    return _lead_row(_order_pseudo(o))


def _query(url):
    try:
        q = parse_qs(urlparse(str(url or "")).query)
    except Exception:
        return {}
    return {k.lower(): (v[0] if v else "") for k, v in q.items()}


def _has_first_touch(e):
    return bool(get_field(e, "utm_source (first touch, HandL)", "utm_medium (first touch, HandL)",
                          "traffic_source (first touch, HandL)", "landing_page (first touch, HandL)",
                          "first_utm_source", "first_traffic_source"))


def _ft_row(e):
    """First-touch row key, with the ad platform split out when the first visit shows it
    (first-touch UTMs, or a click ID on the first landing page)."""
    if not _has_first_touch(e):
        return _lead_row(e)
    src = get_field(e, "utm_source (first touch, HandL)", "first_utm_source (HandL)", "first_utm_source").lower()
    med = get_field(e, "utm_medium (first touch, HandL)", "first_utm_medium (HandL)", "first_utm_medium").lower()
    q = _query(get_field(e, "landing_page (first touch, HandL)"))
    if not src and not med:
        src, med = (q.get("utm_source") or "").lower(), (q.get("utm_medium") or "").lower()
    ch = first_touch(e)
    pseudo = {"utm_source": src, "utm_medium": med, "gclid": q.get("gclid") or q.get("wbraid") or q.get("gbraid") or "",
              "fbclid": q.get("fbclid") or "", "msclkid": q.get("msclkid") or ""}
    if ch == "Paid" or med in _PAID_MEDIUMS or pseudo["gclid"] or pseudo["msclkid"]:
        return _plat(pseudo) or OTHER_PAID
    return ch if ch in NON_PAID else "Direct"


# ---------------------------------------------------------------------------
# joins
# ---------------------------------------------------------------------------
def _person_index(*lists):
    """email -> the person's earliest form submission across the lists given (first list wins ties)."""
    idx = {}
    for li, lst in enumerate(lists):
        for e in lst or []:
            em = lead_email(e)
            if not em:
                continue
            d = entry_dt(e)
            cur = idx.get(em)
            if cur is None:
                idx[em] = (li, d, e)
            elif cur[0] == li and d and (cur[1] is None or d < cur[1]):
                idx[em] = (li, d, e)
    return {k: (v[2], v[0]) for k, v in idx.items()}


def _match_deals(deals, idx):
    """[(deal, lead or None, list index or None)] by lowercase email."""
    out = []
    for d in deals:
        hit = idx.get(d.get("email") or "")
        out.append((d, hit[0] if hit else None, hit[1] if hit else None))
    return out


def _window(leads, *row_lists):
    ds = [d.date() for d in (entry_dt(e) for e in leads or []) if d]
    for rows in row_lists:
        for r in rows or []:
            d = _date(r.get("date"))
            if d:
                ds.append(d)
    if not ds:
        return None, None
    return min(ds), max(ds)


def _daily(rows, start, end, key, date_key="date"):
    if not start or not end:
        return []
    c = defaultdict(float)
    for r in rows or []:
        d = _date(r.get(date_key))
        if d and start <= d <= end:
            c[d] += float(r.get(key) or 0)
    out, d = [], start
    while d <= end:
        out.append(round(c.get(d, 0.0), 2))
        d += _ONE_DAY
    return out


def _chips(pairs):
    """[(display name, detail)] -> meta.sources via connectors.sources_meta."""
    keys = {"UTM Grabber": "utmg", "Google Ads": "google_ads", "Meta Ads": "meta_ads", "Microsoft Ads": "microsoft_ads",
            "LinkedIn Ads": "linkedin_ads", "Google Analytics 4": "ga4", "HubSpot": "hubspot",
            "Salesforce": "salesforce", "Pipedrive": "pipedrive", "WooCommerce": "woocommerce", "Stripe": "stripe"}
    od = OrderedDict()
    for name, detail in pairs:
        if detail:
            od[keys.get(name, name)] = detail
    return sources_meta(**od)


def _spend_by_platform(ads):
    c = Counter()
    for r in ads:
        c[r["platform"]] += r.get("spend", 0.0) or 0.0
    return Counter({k: round(v, 2) for k, v in c.items()})


def _crm(kw, deal_rows):
    """The CRM's name for copy and chips: crm_name= wins, then a hint in raw rows, then HubSpot."""
    name = kw.get("crm_name") or kw.get("crm")
    if name:
        return _safe(name, 24)
    for r in (deal_rows or [])[:5]:
        if not isinstance(r, dict):
            continue
        ks = " ".join(r.keys()).lower()
        if "stagename" in ks or "opportunity" in ks:
            return "Salesforce"
        if "add_time" in ks or "won_time" in ks or "person_email" in ks:
            return "Pipedrive"
    return "HubSpot"


def _join_list(items, last="and"):
    items = [x for x in items if x]
    if len(items) <= 1:
        return "".join(items)
    return "%s %s %s" % (", ".join(items[:-1]), last, items[-1])


def _by_impact(recs):
    """Recommendations in priority order: High, then Medium, then Low impact (stable within a level)."""
    rank = {"High": 0, "Medium": 1, "Low": 2}
    return sorted(recs, key=lambda r: rank.get(r.get("impact"), 3))


def _short(m, kicker, title, why_title, why_body, stats=None, extra=None, close_title="", close_body=None,
           bits=None, notes=None):
    """Short, honest report for thin data or a missing source: what we saw, why it stops, what to do."""
    secs = [{"type": "title-block", "kicker": kicker, "title": title, "meta_bits": [b for b in (bits or []) if b]}]
    if stats and 2 <= len(stats) <= 6:
        secs.append({"type": "stat-strip", "stats": stats})
    secs.append({"type": "insight-card", "kicker": "Why this report is short", "title": why_title,
                 "body": why_body, "tone": "neutral"})
    secs.extend(extra or [])
    if notes:
        secs.append({"type": "notes", "items": notes})
    close = {"type": "closing", "kicker": "Next step", "title": close_title}
    if close_body:
        close["body"] = close_body
    secs.append(close)
    return {"meta": m, "sections": secs}


def _setup(leads, prior, brand_profile, customer_name, customer_domain, compare_label, prepared_by, prepared_for):
    leads = list(leads or [])
    prior = list(prior or [])
    pstart, pend = span(prior) if prior else (None, None)
    m = meta(brand_profile, customer_name, customer_domain,
             compare_label=compare_label or (prior_name(pstart, pend) if prior else "last period"),
             prepared_by=prepared_by, prepared_for=prepared_for)
    return leads, prior, m


def _bits(*items):
    return [b for b in items if b]


def _plat_short(p):
    return {"Google Ads": "Google", "Meta Ads": "Meta", "Microsoft Ads": "Microsoft", "LinkedIn Ads": "LinkedIn",
            "TikTok Ads": "TikTok"}.get(p, p)


def _plat_source(plats):
    plats = [p for p in plats if p]
    if not plats:
        return None
    if len(plats) == 1:
        return plats[0]
    if len(plats) == 2:
        return "%s + %s" % (_plat_short(plats[0]), _plat_short(plats[1]))
    return "%d ad platforms" % len(plats)


def _roas_delta(cur, prev):
    """ROAS change as '+0.4x' (Flat under 0.05x)."""
    out = {"good": "up"}
    if cur is None or prev is None:
        return out
    d = cur - prev
    if abs(d) < 0.05:
        out.update(delta_label="Flat", delta_direction="flat")
    else:
        out.update(delta_label="%s%.1fx" % ("+" if d > 0 else MINUS, abs(d)),
                   delta_direction="up" if d > 0 else "down")
    return out


def _compact(v):
    """9,999 / 11.6K / 1.2M for chart notes."""
    if v is None:
        return "–"
    if abs(v) >= 1e6:
        return ("%.1fM" % (v / 1e6)).replace(".0M", "M")
    if abs(v) >= 1e4:
        return ("%.1fK" % (v / 1e3)).replace(".0K", "K")
    return n(v)


def _rate(v):
    """Lead rate with a decimal below 10%."""
    return "–" if v is None else pct(v, 1 if v < 10 else 0)


# ---------------------------------------------------------------------------
# FULL-FUNNEL PERFORMANCE (flagship cross-platform monthly)
# ---------------------------------------------------------------------------
def build_full_funnel(leads, prior=None, ad_rows=None, ad_rows_prior=None, visit_rows=None, visit_rows_prior=None,
                      deal_rows=None, deal_rows_prior=None, orders=None, orders_prior=None, brand_profile=None,
                      customer_name=None, customer_domain="", compare_label=None, form_label=None, prepared_by=None,
                      prepared_for=None, **kw):
    """Sessions -> leads -> deals -> customers -> revenue, by channel, with spend and ROAS where connected."""
    name = "Full-funnel performance"
    leads, prior, m = _setup(leads, prior, brand_profile, customer_name, customer_domain, compare_label,
                             prepared_by, prepared_for)
    if not leads:
        return empty_report(name, m)
    ads, ads_p = _ads(ad_rows), _ads(ad_rows_prior)
    vis, vis_p = _visits(visit_rows), _visits(visit_rows_prior)
    deals, deals_p = _deals(deal_rows), _deals(deal_rows_prior)
    ords, ords_p = _orders(orders), _orders(orders_prior)
    crm = _crm(kw, deal_rows)
    store = _safe(kw.get("store_name") or "WooCommerce", 24)
    history = list(kw.get("history") or kw.get("leads_history") or [])
    start, end = _window(leads, ads, vis)
    period = period_label(start, end)
    kicker = _kick(name, start, end)
    days = _days(start, end)
    when = _in_period(start, end)
    has_prior = len(prior) >= MIN_LEADS
    vs = m["compare_label"]

    spend_p = _spend_by_platform(ads)
    spend = round(sum(spend_p.values()), 2)
    has_ads = spend > 0
    plats = [k for k, v in spend_p.most_common() if v > 0]
    sessions = sum(v["sessions"] for v in vis)
    has_vis = sessions > 0
    rev_src = "deals" if deals else ("orders" if ords else None)
    cust_label = "Orders" if rev_src == "orders" else "Customers"
    cust_word = "orders" if rev_src == "orders" else "customers"
    rev_name = crm if rev_src == "deals" else store
    total = len(leads)

    chips = [("UTM Grabber", _pl(total, "lead"))]
    for p in plats:
        chips.append((p, "%s spend" % _money(spend_p[p])))
    if has_vis:
        chips.append(("Google Analytics 4", "%s sessions" % n(sessions)))
    if deals:
        chips.append((crm, _pl(len(deals), "deal")))
    if ords:
        chips.append((store, _pl(sum(1 for o in ords if o["_paid"]), "order")))
    m["sources"] = _chips(chips)

    missing = []
    if not has_ads:
        missing.append("Connect your Google Ads or Meta Ads to add spend, ROAS and cost per customer.")
    if not has_vis:
        missing.append("Connect Google Analytics 4 to add sessions and lead rates.")
    if not rev_src:
        missing.append("Connect HubSpot, Salesforce or Pipedrive (or your WooCommerce store) to add customers and revenue.")

    if total < MIN_LEADS:
        stats = [stat("Leads", n(total), source="UTM Grabber")]
        if has_ads:
            stats.append(stat("Ad spend", _money(spend), source=_plat_source(plats)))
        if has_vis:
            stats.append(stat("Sessions", n(sessions), source="GA4"))
        if len(stats) < 2:
            stats.append(stat("Days covered", n(days)))
        return _short(m, kicker, "Only %s so far: too few to read a *funnel*." % _pl(total, "lead"),
                      "A funnel needs at least %d *leads*." % MIN_LEADS,
                      ["With %s, one more lead moves every rate in the funnel by %s points or more." % (
                          _pl(total, "lead"), n(round(100.0 / max(total, 1)))),
                       "Widen the date range, or run this again once more submissions arrive."],
                      stats=stats, close_title="Next: widen the *date range* and run this again.",
                      bits=_bits(customer_domain, form_label, "%d days" % days if days else ""),
                      notes=["Leads: %s from UTM Grabber, %s." % (_pl(total, "form submission"), period or "this period")]
                      + missing)

    # ---- per-row numbers -------------------------------------------------------------
    leads_by = Counter(_lead_row(e) for e in leads)
    sess_by = Counter()
    for v in vis:
        sess_by[_visit_row(v)] += v["sessions"]
    idx = _person_index(leads, prior, history)
    matched = _match_deals(deals, idx)
    cust_by, rev_by = Counter(), Counter()
    won_all = [(d, e, li) for d, e, li in matched if d["stage"] == "won"]
    if rev_src == "deals":
        for d, e, li in won_all:
            k = _lead_row(e) if e is not None else NO_LEAD
            cust_by[k] += 1
            rev_by[k] += d["amount"]
    elif rev_src == "orders":
        for o in ords:
            if o["_paid"]:
                k = _order_row(o)
                cust_by[k] += 1
                rev_by[k] += o["total"]
    total_cust = sum(cust_by.values())
    total_rev = sum(rev_by.values())
    paid_rev = sum(rev_by.get(k, 0.0) for k in plats)
    paid_cust = sum(cust_by.get(k, 0) for k in plats)
    paid_leads = sum(leads_by.get(k, 0) for k in plats)
    ads_tied = paid_leads > 0
    roas = safe_div(paid_rev, spend) if has_ads and rev_src and ads_tied else None
    cpc = safe_div(spend, paid_cust) if has_ads and rev_src and paid_cust else None
    cpl = safe_div(spend, paid_leads) if has_ads and paid_leads else None
    site_rate = share(total, sessions) if has_vis else None

    # funnel cohort: deals matched to this period's leads
    f_deals = [(d, e) for d, e, li in matched if e is not None and li == 0]
    f_won = [d for d, e in f_deals if d["stage"] == "won"]
    f_lost = [d for d, e in f_deals if d["stage"] == "lost"]
    f_open = [d for d, e in f_deals if d["stage"] == "open"]
    n_matched = sum(1 for d, e, li in matched if e is not None)
    n_unmatched = len(deals) - n_matched
    open_all = sum(1 for d in deals if d["stage"] == "open")
    buyers = 0
    if rev_src == "orders":
        paid_emails = set(o.get("email") for o in ords if o["_paid"] and o.get("email"))
        buyers = len(set(lead_email(e) for e in leads if lead_email(e) in paid_emails))

    # ---- prior period -----------------------------------------------------------------
    spend_pp = _spend_by_platform(ads_p)
    spend_prior = round(sum(spend_pp.values()), 2) if ads_p else None
    sessions_prior = sum(v["sessions"] for v in vis_p) if vis_p else None
    leads_prior = len(prior) if has_prior else None
    cust_prior = rev_prior = roas_prior = cpc_prior = cpl_prior = None
    if rev_src == "deals" and deals_p:
        idx_p = _person_index(prior, history, leads)
        cb, rb = Counter(), Counter()
        for d, e, li in _match_deals(deals_p, idx_p):
            if d["stage"] == "won":
                k = _lead_row(e) if e is not None else NO_LEAD
                cb[k] += 1
                rb[k] += d["amount"]
        cust_prior, rev_prior = sum(cb.values()), sum(rb.values())
        pp = [k for k, v in spend_pp.items() if v > 0]
        if spend_prior:
            roas_prior = safe_div(sum(rb.get(k, 0.0) for k in pp), spend_prior)
            pc = sum(cb.get(k, 0) for k in pp)
            cpc_prior = safe_div(spend_prior, pc) if pc else None
    elif rev_src == "orders" and ords_p:
        cb, rb = Counter(), Counter()
        for o in ords_p:
            if o["_paid"]:
                k = _order_row(o)
                cb[k] += 1
                rb[k] += o["total"]
        cust_prior, rev_prior = sum(cb.values()), sum(rb.values())
        pp = [k for k, v in spend_pp.items() if v > 0]
        if spend_prior:
            roas_prior = safe_div(sum(rb.get(k, 0.0) for k in pp), spend_prior)
            pc = sum(cb.get(k, 0) for k in pp)
            cpc_prior = safe_div(spend_prior, pc) if pc else None
    if spend_prior and has_prior:
        pl_prior = sum(1 for e in prior if _lead_row(e) in spend_pp)
        cpl_prior = safe_div(spend_prior, pl_prior) if pl_prior else None
    rate_prior = share(len(prior), sessions_prior) if sessions_prior and has_prior else None
    immature = False
    if rev_src == "deals" and deals_p:
        open_share = share(open_all, len(deals))
        open_share_p = share(sum(1 for d in deals_p if d["stage"] == "open"), len(deals_p))
        if open_share - open_share_p >= 10:
            immature = True
            cust_prior = rev_prior = roas_prior = cpc_prior = None

    # per-platform summary for copy
    pstat = []
    for p in plats:
        sp, rv, cu = spend_p[p], rev_by.get(p, 0.0), cust_by.get(p, 0)
        pstat.append({"p": p, "spend": sp, "rev": rv, "cust": cu, "leads": leads_by.get(p, 0),
                      "roas": safe_div(rv, sp) if rev_src and ads_tied else None, "cpc": safe_div(sp, cu) if cu else None,
                      "cpl": safe_div(sp, leads_by.get(p, 0)) if leads_by.get(p, 0) else None})
    ranked = sorted([x for x in pstat if x["roas"] is not None], key=lambda x: -x["roas"])

    # ---- title ----------------------------------------------------------------------------
    pn = _lead_in(start, end)
    if has_ads and not ads_tied:
        title = "Your ads spent %s %s, but no lead carried their *tags*." % (_money(spend), when)
    elif has_ads and rev_src and paid_rev > 0:
        title = "%s turned %s of ads into *%s* of revenue." % (pn, _money(spend), _money(paid_rev))
    elif has_ads and rev_src:
        title = "Your ads spent %s %s and brought no *%s* yet." % (_money(spend), when, cust_word)
    elif rev_src == "deals":
        title = "%s brought *%s* worth %s." % (pn, _pl(total_cust, "customer"), _money(total_rev))
    elif rev_src == "orders":
        title = "Your store took *%s* worth %s %s." % (_pl(total_cust, "order"), _money(total_rev), when)
    elif has_ads:
        title = "%s of ads brought *%s* %s." % (_money(spend), _pl(paid_leads, "lead"), when)
    elif has_vis:
        title = "%s sessions became *%s* %s." % (n(sessions), _pl(total, "lead"), when)
    else:
        title = "Your forms captured *%s* %s." % (_pl(total, "lead"), when)
    sub = []
    if ranked:
        b = ranked[0]
        lead = ("Ads brought %s of your %s revenue: " % (_money(paid_rev), _money(total_rev))
                if total_rev > paid_rev and paid_rev > 0 else "")
        if len(ranked) > 1:
            o = ranked[-1]
            sub.append(_cap(lead + "%s returned %s per $1 of spend, %s %s." % (
                b["p"], _per1(b["roas"]), o["p"], _per1(o["roas"]))))
        else:
            sub.append(_cap(lead + "%s returned %s per $1 of spend." % (b["p"], _per1(b["roas"]))))
    elif has_ads and cpl:
        sub.append("Leads from your ads cost %s each." % _money(cpl))
    if rev_src == "deals" and f_deals:
        dec = len(f_won) + len(f_lost)
        line = "%s of leads became a deal" % pct(share(len(f_deals), total))
        if dec:
            line += " and %s of decided deals were won" % pct(share(len(f_won), dec))
        sub.append(line + ".")
    elif rev_src == "orders":
        sub.append("%s of your form leads placed an order." % pct(share(buyers, total)))
    if has_vis and len(sub) < 2:
        sub.append("%s of sessions became a lead." % _rate(site_rate))
    if has_ads and not ads_tied:
        sub.insert(0, "Without utm_source and utm_medium or a click ID on your leads, spend can't be tied to results.")
    if not sub:
        sub.append("Connect your ad accounts, analytics and CRM to see the rest of the funnel.")
    secs = [{"type": "title-block", "kicker": kicker, "title": title, "subtitle": " ".join(sub[:2]),
             "meta_bits": _bits(customer_domain, form_label, "%d days" % days if days else "")}]

    # ---- KPIs -----------------------------------------------------------------------------
    _, lead_daily = daily_counts(leads, start, end)
    stats = []
    if has_ads:
        stats.append(_kpi("Ad spend", _money(spend), spend, spend_prior, good="neutral",
                          spark=_spark(_daily(ads, start, end, "spend")), source=_plat_source(plats)))
    if has_vis:
        stats.append(_kpi("Sessions", n(sessions), sessions, sessions_prior, spark=_spark(_daily(vis, start, end, "sessions")),
                          source="GA4"))
    stats.append(_kpi("Leads", n(total), total, leads_prior, spark=_spark(lead_daily), source="UTM Grabber"))
    if rev_src:
        note = None
        if rev_src == "deals" and open_all:
            note = "%s still open" % _pl(open_all, "deal")
        stats.append(_kpi(cust_label, n(total_cust), total_cust, cust_prior, source=rev_name, note=note))
        stats.append(_kpi("Revenue", _money(total_rev), total_rev, rev_prior, source=rev_name))
    if has_ads and rev_src and ads_tied:
        st = stat("ROAS", _x(roas), note="ad revenue / ad spend")
        if roas_prior is not None:
            st.update(_roas_delta(roas, roas_prior))
        stats.append(st)
        if cpc:
            stats.append(_kpi("Cost per customer" if rev_src == "deals" else "Cost per order", _money(cpc), cpc,
                              cpc_prior, good="down", note="ad spend / ad %s" % cust_word))
    elif has_ads and cpl:
        stats.append(_kpi("Cost per lead", _money(cpl), cpl, cpl_prior, good="down", note="spend / leads from ads"))
    if has_vis and not rev_src:
        stats.append(_kpi("Lead rate", _rate(site_rate), site_rate, rate_prior, kind="pts", note="leads / sessions"))
    if len(stats) < 3:
        ad_leads = sum(v for k, v in leads_by.items() if k in AD_PLATFORMS)
        stats.append(_kpi("Leads per day", "%.1f" % (total / float(max(days, 1))), total / float(max(days, 1)),
                          len(prior) / float(max(1, _days(*span(prior)))) if has_prior else None))
        stats.append(stat("Leads from ad platforms", n(ad_leads), note="%s of all leads" % pct(share(ad_leads, total))))
    if len(stats) > 6:
        stats = [x for x in stats if x["label"] != "Sessions"]
    if len(stats) > 4:
        for x in stats:
            x.pop("source", None)
    secs.append({"type": "stat-strip", "stats": stats[:6]})

    # ---- takeaway ---------------------------------------------------------------------------
    if rev_src and total_rev > 0:
        top_k = max(rev_by, key=lambda k: rev_by[k])
        body = ["%s: %s worth %s." % (top_k, _pl(cust_by[top_k], cust_word[:-1]), _money(rev_by[top_k]))]
        if has_ads and ads_tied and total_rev:
            others = [k for k in sorted(rev_by, key=lambda k: -rev_by[k]) if k not in plats and rev_by[k] > 0]
            names = [k.lower() if k in NON_PAID else k for k in others if k != NO_LEAD][:3]
            if NO_LEAD in others:
                names.append("deals with no form lead")
            tail = (" The other %s came from %s." % (pct(100 - share(paid_rev, total_rev)), _join_list(names))
                    if names else "")
            body.append("Your ad platforms brought %s of revenue on %s of spend.%s" % (
                pct(share(paid_rev, total_rev)), _money(spend), tail))
        tk_title = "*%s* brought %s of your revenue." % (top_k, pct(share(rev_by[top_k], total_rev)))
    else:
        top_k = max(leads_by, key=lambda k: leads_by[k])
        body = ["%s sent %s of %s leads." % (top_k, n(leads_by[top_k]), n(total))]
        if has_vis and sess_by.get(top_k):
            body.append("Its visitors became leads at %s, vs %s site-wide." % (
                _rate(share(leads_by[top_k], sess_by[top_k])), _rate(site_rate)))
        tk_title = "*%s* brought %s of your leads." % (top_k, pct(share(leads_by[top_k], total)))
    secs.append({"type": "insight-card", "kicker": "The takeaway", "title": tk_title, "body": body})

    # ---- 01 funnel ------------------------------------------------------------------------
    num = 0
    stages = []
    if has_vis:
        stages.append({"label": "Website sessions", "value": sessions, "source": "Google Analytics 4"})
    stages.append({"label": "Form leads", "value": total, "source": "UTM Grabber",
                   "conv_label": "of sessions became leads"})
    leak = None
    if rev_src == "deals":
        stages.append({"label": "Deals created", "value": len(f_deals), "source": crm,
                       "conv_label": "of leads became deals"})
        stages.append({"label": "Customers won", "value": len(f_won), "source": crm,
                       "conv_label": "of deals won so far"})
        r1 = share(len(f_deals), total)
        dec = len(f_won) + len(f_lost)
        r2 = share(len(f_won), dec) if dec else None
        if r2 is not None and r2 < r1:
            leak = ("close", r2)
        else:
            leak = ("deal", r1)
    elif rev_src == "orders":
        stages.append({"label": "Leads who bought", "value": buyers, "source": store,
                       "conv_label": "of leads placed an order"})
        leak = ("order", share(buyers, total))
    elif has_vis:
        leak = ("visit", site_rate)
    if len(stages) >= 2:
        num += 1
        secs.append({"type": "section-header", "number": "%02d" % num, "kicker": "The funnel",
                     "title": "From first visit to *customer*." if rev_src else "From visit to *lead*.",
                     "dek": "Each stage comes from the platform named under it."})
        kind, r = leak
        if kind == "deal":
            ins_t = "Only %s of leads became a *deal*." % pct(r)
            ins_b = ["%s of %s leads have no deal in your %s. That is the widest gap after the form." % (
                n(total - len(f_deals)), n(total), crm),
                "Check that every form lead reaches %s and gets a reply." % crm]
            if f_open:
                ins_b.append("%s from these leads are still open, so the won count can still grow." % _pl(len(f_open), "deal"))
        elif kind == "close":
            ins_t = "Only %s of decided deals were *won*." % pct(r)
            ins_b = ["%s were lost and %s won. %s still open." % (n(len(f_lost)), n(len(f_won)),
                                                                   _pl(len(f_open), "deal") + (" is" if len(f_open) == 1 else " are")),
                     "Find out why deals are lost before buying more leads."]
        elif kind == "order":
            ins_t = "Only %s of form leads placed an *order*." % pct(r)
            ins_b = ["%s of %s leads bought something in %s." % (n(buyers), n(total), store),
                     "Follow up new leads with an offer while their interest is fresh."]
        else:
            ins_t = "%s of sessions became a *lead*." % _rate(r)
            ins_b = ["%s of %s sessions ended without a form." % (n(sessions - total), n(sessions)),
                     "The traffic-to-lead report shows which channels and pages leak most."]
        cap = None
        if rev_src == "orders":
            n_paid = sum(1 for o in ords if o["_paid"])
            cap = ("This stage follows form leads only: most of your %s paid orders came from shoppers who never "
                   "filled in a form." % n(n_paid)) if buyers < 0.5 * n_paid else None
        if rev_src == "deals":
            cap = "Deal stages count deals matched by email to these leads: %s of %s." % (n(len(f_deals)), n(len(deals)))
            if len(deals) > len(f_deals):
                cap += " The other %s are in the totals and the channel table." % n(len(deals) - len(f_deals))
        f = {"type": "funnel", "stages": stages, "insight_kicker": "Where it leaks", "insight_title": ins_t,
             "insight_body": ins_b[:3]}
        if cap:
            f["caption"] = cap
        secs.append(f)

    # ---- 02 channels ----------------------------------------------------------------------
    keys = set(leads_by) | set(cust_by) | set(plats) | (set(k for k, v in sess_by.items() if v) if has_vis else set())
    sec_key = rev_by if rev_src else leads_by
    plat_keys = sorted([k for k in keys if k in AD_PLATFORMS or (k not in NON_PAID and k not in (OTHER_PAID, NO_LEAD))],
                       key=lambda k: (-spend_p.get(k, 0), -sec_key.get(k, 0), k))
    rest = sorted([k for k in keys if k in NON_PAID], key=lambda k: (-sec_key.get(k, 0), -leads_by.get(k, 0), k))
    order = plat_keys + rest + [k for k in (OTHER_PAID, NO_LEAD) if k in keys]
    cols = [{"key": "name", "label": "Channel", "type": "name"}]
    if has_ads:
        cols.append({"key": "spend", "label": "Ad spend", "type": "money", "align": "right"})
    if has_vis:
        cols.append({"key": "sessions", "label": "Sessions", "type": "mono-number", "align": "right"})
    cols.append({"key": "leads", "label": "Leads", "type": "bar"})
    if has_vis:
        cols.append({"key": "rate", "label": "Lead rate", "type": "pct", "align": "right"})
    if rev_src:
        cols.append({"key": "cust", "label": cust_label, "type": "mono-number", "align": "right"})
        cols.append({"key": "rev", "label": "Revenue", "type": "money", "align": "right"})
    if has_ads and rev_src and ads_tied:
        cols.append({"key": "roas", "label": "ROAS", "type": "mono-number", "align": "right"})
        cols.append({"key": "cpc", "label": "Cost per %s" % cust_word[:-1], "type": "money", "align": "right"})
    elif has_ads:
        cols.append({"key": "cpl", "label": "Cost per lead", "type": "money", "align": "right"})
    if len(cols) <= 3:
        cols.append({"key": "share", "label": "Share of leads", "type": "pct", "align": "right"})
    best_row = ranked[0]["p"] if ranked else (max(leads_by, key=lambda k: leads_by[k]) if leads_by else None)
    rows = []
    for k in order[:MAX_ROWS]:
        sp = spend_p.get(k) if k in plats else None
        se = sess_by.get(k, 0) if has_vis else None
        ld = leads_by.get(k, 0)
        cu, rv = cust_by.get(k, 0), rev_by.get(k, 0.0)
        row = {"name": k, "spend": _money(sp) if sp else "–",
               "sessions": n(se) if se else "–", "leads": {"value": ld, "label": n(ld)},
               "rate": _rate(share(ld, se)) if se else "–",
               "cust": n(cu), "rev": _money(rv) if rv else "–",
               "roas": _x(safe_div(rv, sp)) if sp and rev_src and ads_tied else "–",
               "cpc": _money(safe_div(sp, cu)) if sp and cu else "–",
               "cpl": _money(safe_div(sp, ld)) if sp and ld else "–", "share": pct(share(ld, total))}
        if k == best_row:
            row["_highlight"] = True
        if k == NO_LEAD:
            row["_muted"] = True
        rows.append(row)
    totals = {"name": "Total", "spend": _money(spend) if has_ads else "–", "sessions": n(sessions) if has_vis else "–",
              "leads": n(total), "rate": _rate(site_rate), "cust": n(total_cust), "rev": _money(total_rev),
              "roas": _x(roas), "cpc": _money(cpc) if cpc else "–", "cpl": _money(cpl) if cpl else "–",
              "share": "100%"}
    cap_bits = ["Leads count toward the channel of their form fill."]
    if has_vis:
        cap_bits.append("Sessions are grouped the same way from Google Analytics source and medium.")
    if has_ads and rev_src and ads_tied:
        cap_bits.append("ROAS and cost per %s in the Total line cover your ad platforms only." % cust_word[:-1])
    num += 1
    secs.append({"type": "section-header", "number": "%02d" % num, "kicker": "Channels",
                 "title": "Every channel, from *spend* to revenue." if (has_ads and rev_src) else
                 ("Every channel, from *visit* to lead." if has_vis else "Where your *leads* came from."),
                 "dek": "Ad platforms first, then the channels you don't pay per click for."})
    secs.append({"type": "ranked-list", "title": "Every *channel* side by side", "columns": cols, "rows": rows,
                 "totals": totals, "caption": " ".join(cap_bits)})

    # ---- 03 spend to revenue ------------------------------------------------------------------
    if has_ads and ads_tied and (rev_src or len(plats) >= 2):
        num += 1
        secs.append({"type": "section-header", "number": "%02d" % num, "kicker": "Spend to revenue" if rev_src else "Platforms",
                     "title": "What each ad *dollar* brought back." if rev_src else "Your ad platforms, *head to head*."})
        if rev_src:
            show = plats[:3]
            steps = [{"label": "Ad spend", "value": round(spend, 2), "kind": "start"}]
            for p in show:
                steps.append({"label": "%s revenue less spend" % p, "value": round(rev_by.get(p, 0.0) - spend_p[p], 2),
                              "kind": "delta"})
            if len(plats) > 3:
                rest_net = sum(rev_by.get(p, 0.0) - spend_p[p] for p in plats[3:])
                steps.append({"label": "Other platforms", "value": round(rest_net, 2), "kind": "delta"})
            steps.append({"label": "Revenue from ads", "value": round(paid_rev, 2), "kind": "total"})
            if ranked and ranked[0]["rev"] > 0:
                b = ranked[0]
                wt = "*%s* returned %s per $1." % (b["p"], _per1(b["roas"]))
                wb = ["It turned %s of spend into %s from %s." % (_money(b["spend"]), _money(b["rev"]),
                                                                  _pl(b["cust"], cust_word[:-1]))]
                for o in ranked[1:3]:
                    wb.append("%s returned %s per $1 on %s." % (o["p"], _per1(o["roas"]), _money(o["spend"])))
                losers = [x["p"] for x in ranked if x["roas"] < 1]
                if losers:
                    wb.append("%s brought back less than %s cost." % (_join_list(losers), "it" if len(losers) == 1 else "they"))
            else:
                wt = "No *%s* came from your ads yet." % cust_word
                wb = ["Your ads spent %s %s." % (_money(spend), when),
                      "Leads from ads may still close; run this again in a few weeks."]
            secs.append({"type": "chart-insight",
                         "chart": {"type": "waterfall", "steps": steps, "unit": "$"},
                         "chart_title": "From ad spend to *revenue*",
                         "caption": "Middle bars: each platform's revenue minus its own spend. Green adds, red loses.",
                         "insight_kicker": "Return on ad spend", "insight_title": wt, "insight_body": wb[:3]})
        if len(plats) >= 2:
            a, b = [x for x in pstat if x["p"] == plats[0]][0], [x for x in pstat if x["p"] == plats[1]][0]

            def _row(label, av, bv, fmt, better=None):
                r = {"label": label, "a": round(av or 0, 2), "b": round(bv or 0, 2),
                     "a_display": fmt(av) if av is not None else "–", "b_display": fmt(bv) if bv is not None else "–"}
                if better and av is not None and bv is not None and av != bv:
                    r["better"] = ("a" if av > bv else "b") if better == "up" else ("a" if av < bv else "b")
                return r
            crow = [_row("Ad spend", a["spend"], b["spend"], money)]
            if has_vis and not rev_src:
                crow.append(_row("Sessions", sess_by.get(a["p"], 0), sess_by.get(b["p"], 0), n, "up"))
            crow.append(_row("Leads", a["leads"], b["leads"], n, "up"))
            crow.append(_row("Cost per lead", a["cpl"], b["cpl"], money, "down"))
            if has_vis and not rev_src:
                crow.append(_row("Lead rate", share(a["leads"], sess_by.get(a["p"], 0)) if sess_by.get(a["p"]) else None,
                                 share(b["leads"], sess_by.get(b["p"], 0)) if sess_by.get(b["p"]) else None, _rate, "up"))
            if rev_src:
                crow.append(_row(cust_label, a["cust"], b["cust"], n, "up"))
                crow.append(_row("Cost per %s" % cust_word[:-1], a["cpc"], b["cpc"], money, "down"))
                crow.append(_row("Revenue", a["rev"], b["rev"], money, "up"))
                crow.append(_row("ROAS", a["roas"], b["roas"], _x, "up"))
            secs.append({"type": "comparison", "a": {"label": a["p"], "sub": "%s spend" % _money(a["spend"])},
                         "b": {"label": b["p"], "sub": "%s spend" % _money(b["spend"])}, "rows": crow,
                         "caption": "%s vs %s %s. A check marks the better value on each line." % (
                             a["p"], b["p"], when)})

    # ---- next steps -----------------------------------------------------------------------
    recs = []
    close = None
    big = [x for x in ranked if x["spend"] >= 300]
    if len(big) >= 2 and big[0]["cust"] >= 3 and big[0]["roas"] >= 1.5 * max(big[-1]["roas"], 0.01):
        b, w = big[0], big[-1]
        recs.append({"label": "This month", "title": "Shift budget toward *%s*" % b["p"],
                     "body": "%s returned %s per $1 of spend (%s at %s each). %s returned %s per $1. Move part of "
                             "%s's budget and compare cost per %s next month." % (
                                 b["p"], _per1(b["roas"]), _pl(b["cust"], cust_word[:-1]), _money(b["cpc"]), w["p"],
                                 _per1(w["roas"]), w["p"], cust_word[:-1]),
                     "impact": "High", "effort": "Low",
                     "metric": "%s vs %s per %s" % (_money(b["cpc"]), _money(w["cpc"]) if w["cpc"] else "no "
                                                   + cust_word[:-1], cust_word[:-1])})
        close = "Next: shift budget toward *%s*. It returned %s per $1 of spend." % (b["p"], _per1(b["roas"]))
    elif big and big[0]["cust"] >= 3 and big[0]["roas"] >= 1:
        b = big[0]
        others = ", ".join("%s %s" % (x["p"], _per1(x["roas"])) for x in big[1:3])
        recs.append({"label": "This month", "title": "Test more budget on *%s*" % b["p"],
                     "body": "It returned %s per $1 of spend (%s at %s each), the best of your ad platforms%s. "
                             "Add budget in steps and watch cost per %s." % (
                                 _per1(b["roas"]), _pl(b["cust"], cust_word[:-1]), _money(b["cpc"]),
                                 (" (%s)" % others) if others else "", cust_word[:-1]),
                     "impact": "Medium", "effort": "Low"})
    if leak and leak[0] == "deal" and total >= 20 and leak[1] < 60:
        nod = total - len(f_deals)
        recs.append({"label": "This week", "title": "Follow up every *form lead*",
                     "body": "%s of %s leads (%s) never became a deal in %s. Make sure each form submission lands "
                             "in %s and gets a reply." % (n(nod), n(total), pct(100 - leak[1]), crm, crm),
                     "impact": "High", "effort": "Low", "metric": "%s leads with no deal" % n(nod)})
        close = close or "Next: follow up the *%s leads* with no deal yet." % n(nod)
    elif leak and leak[0] == "close" and leak[1] < 50:
        recs.append({"label": "This month", "title": "Find out why deals are *lost*",
                     "body": "%s of %s decided deals were lost. Look for a pattern in the lost reasons in %s "
                             "before buying more leads." % (n(len(f_lost)), n(len(f_won) + len(f_lost)), crm),
                     "impact": "High", "effort": "Medium"})
        close = close or "Next: find out why *%s* were lost." % _pl(len(f_lost), "deal")
    if has_vis and site_rate:
        leaky = [k for k in sess_by if k != "Direct" and sess_by[k] >= 0.1 * sessions
                 and share(leads_by.get(k, 0), sess_by[k]) < 0.5 * site_rate]
        if leaky:
            k = max(leaky, key=lambda x: sess_by[x])
            recs.append({"label": "This month", "title": "Lift the lead rate of *%s*" % k,
                         "body": "It drew %s sessions (%s of all) but only %s, a %s lead rate vs %s site-wide. "
                                 "The traffic-to-lead report shows which pages to fix." % (
                                     n(sess_by[k]), pct(share(sess_by[k], sessions)), _pl(leads_by.get(k, 0), "lead"),
                                     _rate(share(leads_by.get(k, 0), sess_by[k])), _rate(site_rate)),
                         "impact": "Medium", "effort": "Medium"})
    if deals and n_unmatched and share(n_unmatched, len(deals)) >= 5:
        recs.append({"label": "This month", "title": "Capture the source of *%s*" % _pl(n_unmatched, "deal"),
                     "body": "%s of %s deals in %s match no form submission, so their source is unknown. Ask new "
                             "customers how they found you, or route calls through a tracked number." % (
                                 n(n_unmatched), n(len(deals)), crm),
                     "impact": "Medium", "effort": "Low"})
    if has_ads and not ads_tied:
        recs.insert(0, {"label": "This week", "title": "Tag every ad with *UTM parameters*",
                        "body": "Your ads spent %s, but no lead carried their tags or click IDs. Add utm_source, "
                                "utm_medium and utm_campaign to every ad URL (Google Ads auto-tagging adds the gclid)." % _money(spend),
                        "impact": "High", "effort": "Low"})
        close = "Next: tag every ad with *UTM parameters*. %s of spend can't be tied to a lead." % _money(spend)
    if not rev_src:
        recs.append({"label": "Next", "title": "Connect your *CRM*",
                     "body": "Connect HubSpot, Salesforce or Pipedrive to this chat and the funnel adds deals, "
                             "customers, revenue and ROAS.", "impact": "High", "effort": "Low"})
        close = close or "Next: connect your *CRM* to see which leads became customers."
    elif not has_ads:
        recs.append({"label": "Next", "title": "Connect your *ad accounts*",
                     "body": "Connect Google Ads or Meta Ads to this chat and every channel gets spend, ROAS and "
                             "cost per %s." % cust_word[:-1], "impact": "High", "effort": "Low"})
    elif not has_vis:
        recs.append({"label": "Next", "title": "Connect *Google Analytics 4*",
                     "body": "Sessions add the top of the funnel: how many visits each channel needs per lead.",
                     "impact": "Medium", "effort": "Low"})
    if len(recs) < 2:
        tk = max(sec_key, key=lambda k: sec_key[k]) if sec_key else None
        if tk:
            recs.append({"label": "Ongoing", "title": "Keep *%s* funded" % tk,
                         "body": "It brought %s of your %s. Protect it before testing new channels." % (
                             pct(share(sec_key[tk], sum(sec_key.values()))), "revenue" if rev_src else "leads"),
                         "impact": "Medium", "effort": "Low"})
    if len(recs) < 2:
        recs.append({"label": "Ongoing", "title": "Run this report *monthly*",
                     "body": "The same funnel each month shows whether a fix moved the right stage.",
                     "impact": "Low", "effort": "Low"})
    num += 1
    secs.append({"type": "section-header", "number": "%02d" % num, "kicker": "Next steps", "title": "What to do *next*."})
    secs.append({"type": "recommendations", "items": _by_impact(recs)[:4]})

    # ---- notes ------------------------------------------------------------------------------
    notes = ["Leads: %s in UTM Grabber, %s. Each counts toward the channel of its form fill; an ad platform when "
             "utm_source and utm_medium or a click ID (gclid, fbclid, msclkid) show one." % (
                 _pl(total, "form submission"), period)]
    if has_ads:
        notes.append("Ad spend: %s from %s, %s." % (_money(spend), _join_list(plats),
                                                     _range_text(_date(r.get("date")) for r in ads)))
    if has_vis:
        notes.append("Sessions: %s from Google Analytics 4, %s, grouped into the same channels by session source "
                     "and medium (AI assistants count as Organic, email as Referral)." % (
                         n(sessions), _range_text(_date(v.get("date")) for v in vis)))
    if deals:
        notes.append("Deals: %s from your %s, created %s. %s (%s) matched a form lead by email; %s match no form lead. "
                     "Customers are won deals; revenue is their amount." % (
                         n(len(deals)), crm, _range_text(_date(d.get("created")) for d in deals) or "in this window",
                         n(n_matched), pct(share(n_matched, len(deals))), n(n_unmatched)))
    if ords:
        notes.append("Orders: %s paid orders from %s worth %s, each credited by the UTM tags it carries." % (
            n(sum(1 for o in ords if o["_paid"])), store, _money(sum(o["total"] for o in ords if o["_paid"]))))
        if deals:
            notes.append("Customers and revenue here come from %s; the revenue report covers store orders." % crm)
    if has_ads and rev_src and ads_tied:
        notes.append("ROAS: revenue from %s that came through an ad platform, divided by that platform's spend." % cust_word)
    if has_ads and not ads_tied:
        notes.append("No lead carried an ad platform's utm_source and utm_medium or a click ID, so spend is shown but "
                     "not tied to leads or revenue.")
    notes.extend(missing)
    if has_prior or spend_prior or sessions_prior or deals_p or ords_p:
        notes.append("Changes compare %s with %s." % (period, vs))
    if immature:
        notes.append("%s, revenue and ROAS are not compared with %s: %s of this period's deals are still open, "
                     "so the totals can still grow." % (cust_label, vs, pct(share(open_all, len(deals)))))
    secs.append({"type": "notes", "items": notes})

    # ---- closing ----------------------------------------------------------------------------
    if not close:
        tk = max(sec_key, key=lambda k: sec_key[k]) if sec_key else "your best channel"
        close = "Next: feed *%s*. It brought %s of your %s." % (
            tk, pct(share(sec_key.get(tk, 0), sum(sec_key.values()) or 1)), "revenue" if rev_src else "leads")
    summ = [{"value": n(total), "label": "Leads"}]
    if rev_src:
        summ.append({"value": n(total_cust), "label": cust_label})
        summ.append({"value": _money(total_rev), "label": "Revenue"})
    if has_ads and rev_src and ads_tied:
        summ.append({"value": _x(roas), "label": "ROAS"})
    elif has_ads:
        summ.append({"value": _money(spend), "label": "Ad spend"})
        if cpl:
            summ.append({"value": _money(cpl), "label": "Cost per lead"})
    if has_vis and len(summ) < 4:
        summ.insert(0, {"value": n(sessions), "label": "Sessions"})
    if len(summ) < 3:
        ad_leads = sum(v for k, v in leads_by.items() if k in AD_PLATFORMS)
        top_l = max(leads_by, key=lambda k: leads_by[k])
        summ += [{"value": n(ad_leads), "label": "From ad platforms"},
                 {"value": pct(share(leads_by[top_l], total)), "label": "From %s" % top_l}]
    bullets = []
    for x in (ranked or pstat)[:2]:
        if rev_src:
            bullets.append("%s: %s spend, %s, %s." % (x["p"], _money(x["spend"]), _pl(x["cust"], cust_word[:-1]),
                                                       _money(x["rev"]) + " revenue"))
        else:
            bullets.append("%s: %s spend, %s at %s each." % (x["p"], _money(x["spend"]), _pl(x["leads"], "lead"),
                                                              _money(x["cpl"])))
    if rev_src == "deals" and f_deals:
        bullets.append("%s of leads became a deal; %s are still open." % (pct(share(len(f_deals), total)),
                                                                        n(len(f_open))))
    elif has_vis:
        bullets.append("%s of sessions became a lead." % _rate(site_rate))
    secs.append({"type": "closing", "kicker": "The funnel in one line", "title": close, "summary_stats": summ[:4],
                 "bullets": bullets[:3]})
    return {"meta": m, "sections": secs}



# ---------------------------------------------------------------------------
# TRUE ROAS: which ads actually brought customers
# ---------------------------------------------------------------------------
def _ad_agg(ads):
    """(platform, campaign key, ad key) -> spend, clicks, impressions, platform conversions."""
    agg = OrderedDict()
    for r in ads:
        k = (r["platform"], norm_key(r.get("campaign")), norm_key(r.get("ad") or ""))
        g = agg.get(k)
        if g is None:
            g = agg[k] = {"key": k, "platform": r["platform"], "campaign": r.get("campaign") or "",
                          "ad": r.get("ad") or "", "spend": 0.0, "clicks": 0, "impressions": 0, "conv": 0.0,
                          "leads": 0, "cust": 0, "rev": 0.0, "lost": 0, "open": 0}
        g["spend"] += r.get("spend") or 0.0
        g["clicks"] += r.get("clicks") or 0
        g["impressions"] += r.get("impressions") or 0
        g["conv"] += r.get("conversions") or 0.0
    camp = defaultdict(list)
    for k in agg:
        camp[k[1]].append(k)
    return agg, camp


def _lev(a, b, cap=3):
    """Levenshtein distance, stopping early once it passes `cap`."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


_FUZZY = {}


def _fuzzy_campaign(ck, keys):
    """A mistyped campaign tag -> the one campaign key it is clearly meant to be, else None.
    Rule: at most two letters off the campaign name, or off its start when the tag is a shortened
    name (8+ letters), and no other campaign equally close."""
    if len(ck) < 5 or not keys:
        return None
    memo = (ck, keys)
    if memo in _FUZZY:
        return _FUZZY[memo]
    best, best_d, tie = None, 99, False
    for c in keys:
        d = _lev(ck, c, 2)
        if len(ck) >= 8 and len(c) > len(ck):
            d = min(d, _lev(ck, c[:len(ck)], 2))
        if d < best_d:
            best, best_d, tie = c, d, False
        elif d == best_d:
            tie = True
    out = best if best_d <= 2 and not tie else None
    if len(_FUZZY) > 5000:
        _FUZZY.clear()
    _FUZZY[memo] = out
    return out


def _match_ad(plat, campaign, content, camp_idx):
    """(ad key or None, (platform, campaign key) or None): utm_campaign to the campaign name,
    then utm_content to an ad inside it (case and punctuation ignored; a tag one or two letters
    off a campaign name counts for that campaign)."""
    ck = norm_key(campaign)
    if not ck:
        return None, None
    if ck not in camp_idx:
        keys = tuple(sorted(k for k, v in camp_idx.items() if v and (not plat or any(x[0] == plat for x in v))))
        ck = _fuzzy_campaign(ck, keys) or ck
    cands = camp_idx.get(ck) or []
    if plat:
        same = [k for k in cands if k[0] == plat]
        if same:
            cands = same
    if not cands:
        return None, None
    ak = norm_key(content)
    if ak:
        for k in cands:
            if k[2] == ak:
                return k, k[:2]
    if len(cands) == 1 and cands[0][2] == "":
        return cands[0], cands[0][:2]          # campaign-level rows: the campaign stands in for its ads
    return None, cands[0][:2]


def _fold_groups(points, k=3, other="Other platforms"):
    """Matrix groups: at most k (the k-1 biggest + one 'other')."""
    sizes = Counter()
    for p in points:
        sizes[p["group"]] += p.get("size") or 1
    keep = [g for g, _ in sizes.most_common()]
    if len(keep) <= k:
        return points
    keep = set(keep[:k - 1])
    for p in points:
        if p["group"] not in keep:
            p["group"] = other
    return points


def _ad_labels(items, limit=40):
    """Display names; an ad name used in two campaigns gets its campaign added."""
    base = []
    for g in items:
        base.append(_safe(g["ad"], limit) if g["ad"] else _safe(g["campaign"] or "(no campaign)", limit - 10) + " (all ads)")
    c = Counter(base)
    out = []
    for g, b in zip(items, base):
        if c[b] > 1 and g["ad"]:
            b = _safe("%s (%s)" % (g["ad"], g["campaign"]), limit + 14)
        out.append(b)
    return out


def _short_label(s, k=26):
    return _safe(s, k)


def build_true_roas(leads, ad_rows=None, deal_rows=None, orders=None, prior=None, ad_rows_prior=None,
                    brand_profile=None, customer_name=None, customer_domain="", compare_label=None, form_label=None,
                    prepared_by=None, prepared_for=None, **kw):
    """Which ads brought customers: spend, leads, cost per lead, customers, revenue and ROAS per ad."""
    name = "Which ads brought customers"
    leads, prior, m = _setup(leads, prior, brand_profile, customer_name, customer_domain, compare_label,
                             prepared_by, prepared_for)
    if not leads:
        return empty_report(name, m)
    ads, ads_p = _ads(ad_rows), _ads(ad_rows_prior)
    deals, ords = _deals(deal_rows), _orders(orders)
    crm = _crm(kw, deal_rows)
    store = _safe(kw.get("store_name") or "WooCommerce", 24)
    history = list(kw.get("history") or kw.get("leads_history") or [])
    start, end = _window(leads, ads)
    period = period_label(start, end)
    kicker = _kick(name, start, end)
    days = _days(start, end)
    when = _in_period(start, end)
    has_prior = len(prior) >= MIN_LEADS
    spend_p = _spend_by_platform(ads)
    spend = round(sum(spend_p.values()), 2)
    plats = [k for k, v in spend_p.most_common() if v > 0]
    rev_src = "deals" if deals else ("orders" if ords else None)
    cust_word = "orders" if rev_src == "orders" else "customers"
    cust_one = cust_word[:-1]
    cust_label = _cap(cust_word)
    bits = _bits(customer_domain, form_label, "%d days" % days if days else "")

    chips = [("UTM Grabber", _pl(len(leads), "lead"))]
    for p in plats:
        chips.append((p, "%s spend" % _money(spend_p[p])))
    if deals:
        chips.append((crm, _pl(len(deals), "deal")))
    if ords:
        chips.append((store, _pl(sum(1 for o in ords if o["_paid"]), "order")))
    m["sources"] = _chips(chips)

    if spend <= 0:
        by = Counter(_plat(e) for e in leads if _plat(e))
        rows = []
        for i, (p, c) in enumerate(by.most_common(6)):
            top = Counter(_safe(lead_content(e), 36) for e in leads if _plat(e) == p and lead_content(e)).most_common(1)
            rows.append({"rank": str(i + 1), "platform": p, "leads": {"value": c, "label": n(c)},
                         "top": top[0][0] if top else "–"})
        extra = []
        if rows:
            extra.append({"type": "ranked-list", "title": "*Leads* your ads sent",
                          "columns": [{"key": "rank", "label": "#", "type": "rank"},
                                      {"key": "platform", "label": "Platform", "type": "platform"},
                                      {"key": "leads", "label": "Leads", "type": "bar"},
                                      {"key": "top", "label": "Top ad (utm_content)", "type": "source"}],
                          "rows": rows, "caption": "Platforms recognized from utm_source, utm_medium and click IDs."})
        paid = sum(by.values())
        return _short(m, kicker, "UTM Grabber tied %s to your ads. Connect *ad spend* to price them." % _pl(paid, "lead"),
                      "Return on ad spend needs your *spend*.",
                      ["Spend, cost per lead and ROAS come only from your ad accounts, and none are connected yet.",
                       "Connect Google Ads or Meta Ads to this chat and this report ranks every ad by the %s it "
                       "brought. Until then, the ad creative report ranks your ads by leads." % cust_word],
                      stats=[stat("Leads", n(len(leads))), stat("Leads from ads", n(paid))], extra=extra,
                      close_title="Next: connect *Google Ads* or Meta Ads and run this again.", bits=bits,
                      notes=["Leads: %s from UTM Grabber, %s." % (_pl(len(leads), "form submission"), period),
                             "Ad spend is not connected, so no cost or return is shown."])

    agg, camp_idx = _ad_agg(ads)
    lead_info = {}
    plat_leads = Counter()
    for e in leads:
        p = _plat(e)
        k, ck = _match_ad(p, lead_campaign(e), lead_content(e), camp_idx)
        pf = p or (ck[0] if ck else None)
        if k:
            agg[k]["leads"] += 1
        if pf:
            plat_leads[pf] += 1
        lead_info[id(e)] = (k, ck, pf)
    paid_leads = sum(plat_leads.get(p, 0) for p in plats)
    lead_plats = [p for p in plat_leads if p not in plats]
    n_ad_paid = sum(1 for e in leads if lead_info[id(e)][0] is not None and lead_info[id(e)][2] in plats)
    n_typo_paid = sum(1 for e in leads if lead_info[id(e)][1] is not None and lead_info[id(e)][2] in plats
                      and norm_key(lead_campaign(e)) != lead_info[id(e)][1][1])
    n_camp_paid = sum(1 for e in leads if lead_info[id(e)][0] is None and lead_info[id(e)][1] is not None
                      and lead_info[id(e)][2] in plats)

    plat_cust, plat_rev = Counter(), Counter()
    won_total = won_to_ads = won_to_ad = 0
    if rev_src == "deals":
        idx = _person_index(leads, prior, history)
        for d, e, _li in _match_deals(deals, idx):
            if d["stage"] == "won":
                won_total += 1
            if e is None:
                continue
            info = lead_info.get(id(e))
            if info is None:
                p = _plat(e)
                k, ck = _match_ad(p, lead_campaign(e), lead_content(e), camp_idx)
                info = (k, ck, p or (ck[0] if ck else None))
            k, ck, pf = info
            if d["stage"] == "won":
                if pf in plats:
                    won_to_ads += 1
                    plat_cust[pf] += 1
                    plat_rev[pf] += d["amount"]
                if k:
                    won_to_ad += 1
                    agg[k]["cust"] += 1
                    agg[k]["rev"] += d["amount"]
            elif d["stage"] == "open":
                if k:
                    agg[k]["open"] += 1
            elif k:
                agg[k]["lost"] += 1
    elif rev_src == "orders":
        for o in ords:
            if not o["_paid"]:
                continue
            won_total += 1
            p = _plat(_order_pseudo(o))
            k, ck = _match_ad(p, o.get("campaign"), o.get("content"), camp_idx)
            pf = p or (ck[0] if ck else None)
            if pf in plats:
                won_to_ads += 1
                plat_cust[pf] += 1
                plat_rev[pf] += o["total"]
            if k:
                won_to_ad += 1
                agg[k]["cust"] += 1
                agg[k]["rev"] += o["total"]
    paid_rev = sum(plat_rev.get(p, 0.0) for p in plats)
    paid_cust = sum(plat_cust.get(p, 0) for p in plats)
    cpl = safe_div(spend, paid_leads) if paid_leads else None
    roas = safe_div(paid_rev, spend) if rev_src else None

    items = [g for g in agg.values() if g["spend"] > 0]
    for g, lab in zip(items, _ad_labels(items)):
        g["name"] = lab
        g["cpl"] = safe_div(g["spend"], g["leads"]) if g["leads"] else None
        g["roas"] = safe_div(g["rev"], g["spend"]) if rev_src else None
        g["cpc"] = safe_div(g["spend"], g["cust"]) if g["cust"] else None
    level_word = "ad" if any(g["ad"] for g in items) else "campaign"
    min_spend = max(50.0, 0.01 * spend)

    # prior period (spend and leads; customers only when prior deals are passed)
    spend_prior = round(sum(r["spend"] for r in ads_p), 2) if ads_p else None
    pl_prior = None
    if ads_p and has_prior:
        pp = set(r["platform"] for r in ads_p if r["spend"] > 0)
        camp_p = _ad_agg(ads_p)[1]
        pl_prior = 0
        for e in prior:
            p = _plat(e)
            ck = _match_ad(p, lead_campaign(e), lead_content(e), camp_p)[1]
            if (p or (ck[0] if ck else None)) in pp:
                pl_prior += 1
    cpl_prior = safe_div(spend_prior, pl_prior) if spend_prior and pl_prior else None

    if paid_leads < MIN_LEADS:
        rows = []
        for i, g in enumerate(sorted(items, key=lambda x: -x["spend"])[:MAX_ROWS]):
            rows.append({"rank": str(i + 1), "name": g["name"], "platform": g["platform"], "spend": _money(g["spend"]),
                         "leads": {"value": g["leads"], "label": n(g["leads"])}})
        extra = [{"type": "ranked-list", "title": "Your ads by *spend*",
                  "columns": [{"key": "rank", "label": "#", "type": "rank"},
                              {"key": "name", "label": _cap(level_word), "type": "name"},
                              {"key": "platform", "label": "Platform", "type": "platform"},
                              {"key": "spend", "label": "Spend", "type": "money", "align": "right"},
                              {"key": "leads", "label": "Leads", "type": "bar"}], "rows": rows}] if rows else []
        why = ["Your ads spent %s %s, and UTM Grabber tied %s to them." % (_money(spend), when, _pl(paid_leads, "lead")),
               "With so few, one lead swings any ad's cost per lead, so we list the ads without ranking them."]
        if paid_leads == 0:
            why = ["Your ads spent %s %s, but no lead carried their utm_source and utm_medium or a click ID." % (
                _money(spend), when),
                "Tag every ad's final URL with UTM parameters (or keep auto-tagging on) and run this again."]
        return _short(m, kicker, ("Only %s came from your ads: too few to rank *ads*." % _pl(paid_leads, "lead"))
                      if paid_leads else "No lead could be tied to your *ads* yet.",
                      "Ad rankings need at least %d *leads*." % MIN_LEADS, why,
                      stats=[stat("Ad spend", _money(spend)), stat("Leads from ads", n(paid_leads))], extra=extra,
                      close_title="Next: rerun this once your ads pass *%d leads*." % MIN_LEADS, bits=bits,
                      notes=["Ad spend: %s from %s, %s." % (_money(spend), _join_list(plats), period),
                             "Leads are matched to ads by utm_campaign (campaign name), then utm_content (ad name)."])

    # ---- title ------------------------------------------------------------------------------
    metric = "rev" if rev_src and paid_rev > 0 else "leads"
    ranked_ads = sorted(items, key=lambda g: (-g[metric], g["spend"]))
    tot_metric = sum(g[metric] for g in items)
    k_half, cum = 0, 0.0
    for g in ranked_ads:
        if tot_metric <= 0:
            break
        k_half += 1
        cum += g[metric]
        if cum >= 0.5 * tot_metric:
            break
    half_spend = sum(g["spend"] for g in ranked_ads[:k_half])
    what = "ad revenue" if metric == "rev" else "ad leads"
    if k_half == 1:
        title = "*%s* alone brought %s of your %s." % (ranked_ads[0]["name"], pct(share(ranked_ads[0][metric], tot_metric)), what)
    elif k_half:
        title = "*%d of your %d %ss* brought half of your %s." % (k_half, len(items), level_word, what)
    else:
        title = "No lead could be tied to a single *%s* yet." % level_word
    sub = []
    if not k_half:
        sub.append("%s leads came from your ad platforms, but none carried a utm_campaign and utm_content that match "
                   "an %s in your accounts." % (n(paid_leads), level_word) if level_word == "ad" else
                   "%s leads came from your ad platforms, but none carried a utm_campaign that matches a campaign in "
                   "your accounts." % n(paid_leads))
    if k_half:
        sub.append("Together they spent %s, %s of your %s ad spend." % (_money(half_spend), pct(share(half_spend, spend)),
                                                                          _money(spend)))
    best = None
    if rev_src:
        pool = [g for g in items if g["cust"] >= 3 and g["spend"] >= min_spend] or \
               [g for g in items if g["cust"] >= 1 and g["spend"] >= min_spend]
        if pool:
            best = max(pool, key=lambda g: g["roas"])
            sub.append("%s returned the most: %s per $1 of spend." % (best["name"], _per1(best["roas"])))
        elif paid_rev <= 0:
            sub.append("None of the leads from your ads has become a %s yet." % cust_one)
    else:
        sub.append("Revenue is not connected, so this report stops at cost per lead (%s on average)." % _money(cpl))
    secs = [{"type": "title-block", "kicker": kicker, "title": title, "subtitle": " ".join(sub[:2]),
             "meta_bits": bits}]

    # ---- KPIs -------------------------------------------------------------------------------
    stats = [_kpi("Ad spend", _money(spend), spend, spend_prior, good="neutral",
                  spark=_spark(_daily(ads, start, end, "spend")), source=_plat_source(plats)),
             _kpi("Leads from ads", n(paid_leads), paid_leads, pl_prior if has_prior else None, source="UTM Grabber"),
             _kpi("Cost per lead", _money(cpl), cpl, cpl_prior, good="down", note="spend / leads from ads")]
    if rev_src:
        stats.append(stat(cust_label, n(paid_cust), note="from your ads"))
        stats.append(stat("Revenue", _money(paid_rev), note="from your ads"))
        stats.append(stat("ROAS", _x(roas), note="revenue / spend"))
    else:
        clicks = sum(g["clicks"] for g in items)
        stats.append(stat("Clicks", n(clicks), note="%s per lead" % ("%.1f" % (clicks / float(paid_leads)) if paid_leads else "–")))
    if len(stats) > 4:
        for x in stats:
            x.pop("source", None)
    secs.append({"type": "stat-strip", "stats": [x for x in stats if x][:6]})

    # ---- takeaway ---------------------------------------------------------------------------
    losers = []
    if rev_src:
        losers = sorted([g for g in items if g["spend"] >= min_spend and g["roas"] is not None and g["roas"] < 1],
                        key=lambda g: -(g["spend"] - g["rev"]))
    if best and losers:
        w = losers[0]
        tk_t = "*%s* returned %s per $1 of spend." % (best["name"], _per1(best["roas"]))
        tk_b = ["It spent %s and brought %s worth %s." % (_money(best["spend"]), _pl(best["cust"], cust_one),
                                                          _money(best["rev"])),
                "At the other end, %s spent %s for %s worth %s: %s per $1." % (
                    w["name"], _money(w["spend"]), _pl(w["cust"], cust_one), _money(w["rev"]), _per1(w["roas"]))]
    elif best:
        tk_t = "*%s* returned %s per $1 of spend." % (best["name"], _per1(best["roas"]))
        tk_b = ["It spent %s and brought %s worth %s." % (_money(best["spend"]), _pl(best["cust"], cust_one), _money(best["rev"]))]
        if roas is not None:
            tk_b.append("Across all your ads: %s per $1." % _per1(roas))
    else:
        lead_items = [g for g in items if g["leads"] >= 5] or [g for g in items if g["leads"]]
        cheap = min(lead_items, key=lambda g: g["cpl"]) if lead_items else max(items, key=lambda g: g["leads"])
        dear = max(lead_items, key=lambda g: g["cpl"]) if lead_items else cheap
        if cheap is not dear and cheap["cpl"] and dear["cpl"]:
            tk_t = "Your leads cost from *%s* to %s, depending on the %s." % (_money(cheap["cpl"]), _money(dear["cpl"]),
                                                                            level_word)
            tk_b = ["%s: %s at %s each." % (cheap["name"], _pl(cheap["leads"], "lead"), _money(cheap["cpl"])),
                    "%s: %s at %s each. Your average is %s." % (dear["name"], _pl(dear["leads"], "lead"),
                                                                 _money(dear["cpl"]), _money(cpl))]
        else:
            tk_t = "*%s* brings leads at %s each." % (cheap["name"], _money(cheap["cpl"]))
            tk_b = ["It spent %s for %s; your average is %s per lead." % (
                _money(cheap["spend"]), _pl(cheap["leads"], "lead"), _money(cpl))]
    secs.append({"type": "insight-card", "kicker": "The takeaway", "title": tk_t, "body": tk_b})

    # ---- 01 the map -------------------------------------------------------------------------
    num = 1
    pts, full = [], {}
    for g in items:
        if g["leads"] > 0:
            pts.append({"label": _short_label(g["name"]), "x": g["leads"], "y": round(g["cpl"], 2),
                        "size": round(g["spend"], 2), "group": g["platform"]})
            full[id(pts[-1])] = g["name"]
    no_lead = [g for g in items if g["leads"] == 0]
    if len(pts) >= 3:
        pts = _fold_groups(pts)
        xr = median([p["x"] for p in pts])
        yr = round(cpl, 2) if cpl else median([p["y"] for p in pts])
        scale = [p for p in pts if p["x"] >= xr and p["y"] <= yr]
        fix = [p for p in pts if p["x"] < xr and p["y"] > yr]
        if scale:
            b = max(scale, key=lambda p: p["x"])
            mt = "*%s* brings the most leads below your average cost." % full[id(b)]
            mb = ["%s leads at %s each, vs %s on average." % (n(b["x"]), _money(b["y"]), _money(yr))]
        else:
            b = min(pts, key=lambda p: p["y"])
            mt = "*%s* has your cheapest leads." % full[id(b)]
            mb = ["%s leads at %s each, vs %s on average." % (n(b["x"]), _money(b["y"]), _money(yr))]
        if fix:
            f = max(fix, key=lambda p: p["y"])
            mb.append("%s is the priciest: %s leads at %s each." % (full[id(f)], n(f["x"]), _money(f["y"])))
        if no_lead:
            mb.append("%s spent %s with no leads, so %s not on the map." % (
                _pl(len(no_lead), level_word), _money(sum(g["spend"] for g in no_lead)),
                "it is" if len(no_lead) == 1 else "they are"))
        secs.append({"type": "section-header", "number": "%02d" % num, "kicker": "The map",
                     "title": "Every %s by leads and *cost per lead*." % level_word,
                     "dek": "Bubble size is spend. The lines mark the median leads per %s and your average cost "
                            "per lead." % level_word})
        secs.append({"type": "matrix", "chart_title": "Leads vs *cost per lead*", "points": pts,
                     "x_label": "Leads", "y_label": "Cost per lead", "y_unit": "$", "x_ref": xr, "y_ref": yr,
                     "quadrants": {"tl": "Fix or cut", "tr": "Scale with care", "bl": "Hidden gems", "br": "Scale now"},
                     "insight_kicker": "Read the map", "insight_title": mt, "insight_body": mb[:3]})
        num += 1

    # ---- 02 ads that paid off ------------------------------------------------------------------
    top = ranked_ads[:10]
    cols = [{"key": "rank", "label": "#", "type": "rank"},
            {"key": "name", "label": _cap(level_word), "type": "name"},
            {"key": "platform", "label": "Platform", "type": "platform"},
            {"key": "spend", "label": "Spend", "type": "money", "align": "right"},
            {"key": "leads", "label": "Leads", "type": "bar"}]
    if rev_src:
        cols += [{"key": "cust", "label": cust_label, "type": "mono-number", "align": "right"},
                 {"key": "rev", "label": "Revenue", "type": "money", "align": "right"},
                 {"key": "roas", "label": "ROAS", "type": "badge"}]
    else:
        cols += [{"key": "cpl", "label": "Cost per lead", "type": "money", "align": "right"},
                 {"key": "status", "label": "Status", "type": "badge"}]
    rows = []
    for i, g in enumerate(top):
        row = {"rank": str(i + 1), "name": g["name"], "platform": g["platform"], "spend": _money(g["spend"]),
               "leads": {"value": g["leads"], "label": n(g["leads"])}, "cust": n(g["cust"]),
               "rev": _money(g["rev"]) if g["rev"] else "–", "cpl": _money(g["cpl"]) if g["cpl"] else "–"}
        if rev_src:
            r_ = g["roas"] or 0.0
            tone = "good" if roas and r_ >= roas else ("warn" if r_ >= 1 else "bad")
            row["roas"] = {"label": _x(r_), "tone": tone}
        else:
            if not g["leads"]:
                row["status"] = {"label": "No leads", "tone": "bad"}
            elif cpl and g["cpl"] <= 0.8 * cpl:
                row["status"] = {"label": "Scale", "tone": "good"}
            elif cpl and g["cpl"] >= 1.5 * cpl:
                row["status"] = {"label": "Costly", "tone": "warn"}
            else:
                row["status"] = {"label": "Steady", "tone": "neutral"}
        if i == 0:
            row["_highlight"] = True
        rows.append(row)
    tcap = "%s of %s ranked by %s." % (_pl(len(top), level_word), n(len(items)), "revenue" if metric == "rev" else "leads")
    if rev_src:
        tcap += " ROAS pill: green at or above your average (%s), amber from 1x, red below 1x." % _x(roas)
    secs.append({"type": "section-header", "number": "%02d" % num, "kicker": "Winners",
                 "title": ("The %ss that brought *%s*." % (level_word, cust_word)) if rev_src else
                 ("The %ss that brought *leads*." % level_word)})
    secs.append({"type": "ranked-list", "title": "Top %ss by *%s*" % (level_word, "revenue" if metric == "rev" else "leads"),
                 "columns": cols, "rows": rows, "caption": tcap})
    num += 1

    # ---- 03 spend that didn't pay back ----------------------------------------------------------
    if rev_src:
        weak = [g for g in items if g["spend"] >= min_spend and (g["cust"] == 0 or (g["roas"] is not None and g["roas"] < 1))]
        weak.sort(key=lambda g: -(g["spend"] - g["rev"]))
    else:
        weak = sorted(no_lead, key=lambda g: -g["spend"])
    if weak:
        wrows = []
        for i, g in enumerate(weak[:8]):
            if not g["leads"]:
                badge = {"label": "No leads", "tone": "bad"}
            elif rev_src and not g["cust"] and g["open"]:
                badge = {"label": "%s open" % _pl(g["open"], "deal"), "tone": "warn"}
            elif rev_src and not g["cust"]:
                badge = {"label": "No %s" % cust_word, "tone": "bad"}
            else:
                badge = {"label": "Under 1x", "tone": "warn"}
            wrows.append({"rank": str(i + 1), "name": g["name"], "platform": g["platform"],
                          "camp": _safe(g["campaign"], 30), "spend": _money(g["spend"]),
                          "leads": {"value": g["leads"], "label": n(g["leads"])},
                          "cpl": _money(g["cpl"]) if g["cpl"] else "–", "cust": n(g["cust"]),
                          "rev": _money(g["rev"]) if g["rev"] else "–", "status": badge})
        wcols = [{"key": "rank", "label": "#", "type": "rank"},
                 {"key": "name", "label": _cap(level_word), "type": "name"},
                 {"key": "camp", "label": "Campaign", "type": "source"},
                 {"key": "spend", "label": "Spend", "type": "money", "align": "right"},
                 {"key": "leads", "label": "Leads", "type": "bar"},
                 {"key": "cpl", "label": "Cost per lead", "type": "money", "align": "right"}]
        if rev_src:
            wcols += [{"key": "rev", "label": "Revenue", "type": "money", "align": "right"}]
        wcols.append({"key": "status", "label": "Status", "type": "badge"})
        lost_sp = sum(g["spend"] for g in weak)
        lost_back = sum(g["rev"] for g in weak)
        secs.append({"type": "section-header", "number": "%02d" % num, "kicker": "Leaks",
                     "title": ("Spend that didn't *pay back*." if rev_src else "Spend that brought no *leads*."),
                     "dek": ("%s spent %s and brought back %s." % (_pl(len(weak), level_word), _money(lost_sp),
                                                                   _money(lost_back))) if rev_src else
                     ("%s spent %s without a single lead." % (_pl(len(weak), level_word), _money(lost_sp)))})
        secs.append({"type": "ranked-list", "title": "Where the *money* leaked", "columns": wcols, "rows": wrows,
                     "caption": ("%ss with at least %s of spend and no %s, or less than $1 back per $1." % (
                         _cap(level_word), _money(min_spend), cust_word)) if rev_src else
                     "%ss with spend and no lead matched to them." % _cap(level_word)})
        num += 1

    # ---- 04 by platform ----------------------------------------------------------------------
    pinfo = []
    for p in plats:
        sp = spend_p[p]
        pinfo.append({"p": p, "spend": sp, "leads": plat_leads.get(p, 0), "cust": plat_cust.get(p, 0),
                      "rev": plat_rev.get(p, 0.0), "cpl": safe_div(sp, plat_leads.get(p, 0)) if plat_leads.get(p) else None,
                      "cpc": safe_div(sp, plat_cust.get(p, 0)) if plat_cust.get(p) else None,
                      "roas": safe_div(plat_rev.get(p, 0.0), sp) if rev_src else None})
    if len(pinfo) >= 2:
        secs.append({"type": "section-header", "number": "%02d" % num, "kicker": "Platforms",
                     "title": ("ROAS by *platform*." if rev_src else "Cost per lead by *platform*."),
                     "dek": "Every lead and %s your ads brought, not only the ones tied to one ad." % cust_one
                     if rev_src else "Every lead your ads brought, not only the ones tied to one ad."})
        if len(pinfo) == 2:
            a, b = pinfo

            def _r(label, av, bv, f, better=None):
                r = {"label": label, "a": round(av or 0, 2), "b": round(bv or 0, 2),
                     "a_display": f(av) if av is not None else "–", "b_display": f(bv) if bv is not None else "–"}
                if better and av is not None and bv is not None and av != bv:
                    r["better"] = ("a" if av > bv else "b") if better == "up" else ("a" if av < bv else "b")
                return r
            crow = [_r("Spend", a["spend"], b["spend"], money), _r("Leads", a["leads"], b["leads"], n, "up"),
                    _r("Cost per lead", a["cpl"], b["cpl"], money, "down")]
            if rev_src:
                crow += [_r(cust_label, a["cust"], b["cust"], n, "up"),
                         _r("Cost per %s" % cust_one, a["cpc"], b["cpc"], money, "down"),
                         _r("Revenue", a["rev"], b["rev"], money, "up"), _r("ROAS", a["roas"], b["roas"], _x, "up")]
            secs.append({"type": "comparison", "a": {"label": a["p"], "sub": "%s spend" % _money(a["spend"])},
                         "b": {"label": b["p"], "sub": "%s spend" % _money(b["spend"])}, "rows": crow,
                         "caption": "%s vs %s %s. A check marks the better value on each line." % (a["p"], b["p"], when)})
        else:
            key = "roas" if rev_src else "cpl"
            order_p = sorted(pinfo, key=lambda x: -(x[key] or 0) if rev_src else (x[key] or 1e9))
            vals = [round(x[key] or 0, 2) for x in order_p]
            bt = order_p[0]
            secs.append({"type": "chart-insight",
                         "chart": {"type": "bar-horizontal", "labels": [x["p"] for x in order_p], "values": vals,
                                   "unit": "x" if rev_src else "$", "highlight": 0, "show_share": False,
                                   "notes": ["%s spend" % _money(x["spend"]) for x in order_p]},
                         "caption": ("Revenue per $1 of spend, by platform." if rev_src else "Cost per lead, by platform."),
                         "insight_kicker": "Best platform",
                         "insight_title": ("*%s* returned %s per $1." % (bt["p"], _per1(bt["roas"]))) if rev_src else
                         ("*%s* has your cheapest leads." % bt["p"]),
                         "insight_body": ["%s spent %s for %s." % (x["p"], _money(x["spend"]),
                                                                    _pl(x["cust"], cust_one) if rev_src else _pl(x["leads"], "lead"))
                                          for x in order_p[:3]]})
        num += 1

    # ---- next steps -----------------------------------------------------------------------------
    recs = []
    close = None
    movers = []
    if rev_src:
        movers = [g for g in weak if g["leads"] and not (g["cust"] == 0 and g["open"])] if weak else []
    if best and movers and movers[0] is not best:
        w = movers[0]
        recs.append({"label": "This month", "title": "Move %s from *%s*" % (_money(w["spend"]), _short_label(w["name"], 40)),
                     "body": "It spent %s for %s and %s (%s back, %s per $1). Put that budget behind %s, which "
                             "returned %s per $1 on %s." % (
                                 _money(w["spend"]), _pl(w["leads"], "lead"), _pl(w["cust"], cust_one), _money(w["rev"]),
                                 _per1(w["roas"]), best["name"], _per1(best["roas"]), _money(best["spend"])),
                     "impact": "High", "effort": "Low", "metric": "%s per $1 vs %s" % (_per1(best["roas"]), _per1(w["roas"]))})
        close = "Next: move %s from *%s* to %s." % (_money(w["spend"]), _short_label(w["name"], 40),
                                                     _short_label(best["name"], 40))
        if len(movers) > 1 and movers[1] is not best:
            w2 = movers[1]
            recs.append({"label": "This month", "title": "Cut back *%s*" % _short_label(w2["name"], 40),
                         "body": "It spent %s for %s and %s worth %s: %s per $1." % (
                             _money(w2["spend"]), _pl(w2["leads"], "lead"), _pl(w2["cust"], cust_one), _money(w2["rev"]),
                             _per1(w2["roas"])),
                         "impact": "Medium", "effort": "Low"})
    if rev_src and roas:
        vol = [g for g in items if g["cust"] >= 5 and g["roas"] is not None and g["roas"] >= roas and g is not best]
        if vol:
            v = max(vol, key=lambda g: (g["cust"], g["roas"]))
            recs.append({"label": "This month", "title": "Raise the budget on *%s*" % _short_label(v["name"], 40),
                         "body": "It brought %s worth %s on %s of spend (%s), and leads at %s each vs %s on "
                                 "average." % (_pl(v["cust"], cust_one), _money(v["rev"]), _money(v["spend"]),
                                               _x(v["roas"]), _money(v["cpl"]), _money(cpl)),
                         "impact": "High", "effort": "Low"})
    zero = [g for g in items if g["leads"] == 0 and g["spend"] >= min_spend]
    if zero:
        z = max(zero, key=lambda g: g["spend"])
        recs.append({"label": "This week", "title": "Pause *%s*" % _short_label(z["name"], 40),
                     "body": "It spent %s %s and no lead carried its tags. Check its final URL first: a missing "
                             "utm_content looks the same as no leads." % (_money(z["spend"]), when),
                     "impact": "High", "effort": "Low", "metric": "%s back to work" % _money(z["spend"])})
        close = close or "Next: pause *%s*. It spent %s with no leads." % (_short_label(z["name"], 40), _money(z["spend"]))
    waiting = [g for g in items if rev_src and g["cust"] == 0 and g["open"] and g["spend"] >= min_spend]
    if waiting:
        g = max(waiting, key=lambda x: x["spend"])
        recs.append({"label": "In two weeks", "title": "Recheck *%s*" % _short_label(g["name"], 40),
                     "body": "It spent %s and has no %s yet, but %s from its leads are still open. Judge it once "
                             "they close." % (_money(g["spend"]), cust_one, _pl(g["open"], "deal")),
                     "impact": "Medium", "effort": "Low"})
    if best and not close:
        recs.append({"label": "This month", "title": "Give *%s* more budget" % _short_label(best["name"], 40),
                     "body": "It returned %s per $1 of spend (%s worth %s). Raise its budget in steps and watch "
                             "cost per %s." % (_per1(best["roas"]), _pl(best["cust"], cust_one), _money(best["rev"]), cust_one),
                     "impact": "High", "effort": "Low"})
        close = "Next: give *%s* more budget. It returned %s per $1." % (_short_label(best["name"], 40), _per1(best["roas"]))
    if rev_src and len(pinfo) >= 2:
        rp = sorted([x for x in pinfo if x["spend"] >= 300 and x["roas"] is not None], key=lambda x: -x["roas"])
        if len(rp) >= 2 and rp[0]["cust"] >= 3 and rp[0]["roas"] >= 1.5 * max(rp[-1]["roas"], 0.01):
            recs.append({"label": "This month", "title": "Shift budget toward *%s*" % rp[0]["p"],
                         "body": "%s returned %s per $1, %s %s." % (rp[0]["p"], _per1(rp[0]["roas"]), rp[-1]["p"],
                                                                     _per1(rp[-1]["roas"])),
                         "impact": "Medium", "effort": "Low"})
    if paid_leads and share(n_camp_paid, paid_leads) >= 10:
        recs.append({"label": "This month", "title": "Tag every ad with *utm_content*",
                     "body": "%s of %s leads from your ads matched a campaign but not an ad, so their ad's return is "
                             "unknown. Meta fills it with {{ad.name}}; in Google Ads add it to each ad's final URL." % (
                                 n(n_camp_paid), n(paid_leads)),
                     "impact": "Medium", "effort": "Low"})
    if not rev_src:
        lead_items = [g for g in items if g["leads"] >= 5]
        if lead_items and cpl:
            c = min(lead_items, key=lambda g: g["cpl"])
            d = max(lead_items, key=lambda g: g["cpl"])
            if c["cpl"] <= 0.6 * cpl:
                recs.append({"label": "This month", "title": "Feed *%s*" % _short_label(c["name"], 40),
                             "body": "Its %s cost %s each, vs %s across your ads. Raise its budget in steps and watch "
                                     "cost per lead." % (_pl(c["leads"], "lead"), _money(c["cpl"]), _money(cpl)),
                             "impact": "High", "effort": "Low"})
            if d is not c and d["cpl"] >= 2 * cpl and d["spend"] >= min_spend:
                recs.append({"label": "This month", "title": "Cut back *%s*" % _short_label(d["name"], 40),
                             "body": "Its %s cost %s each, %.1f times your average. Lower its budget or bid until "
                                     "revenue shows it earns that." % (_pl(d["leads"], "lead"), _money(d["cpl"]),
                                                                       d["cpl"] / cpl),
                             "impact": "Medium", "effort": "Low"})
        recs.append({"label": "Next", "title": "Connect your *CRM*",
                     "body": "Connect HubSpot, Salesforce or Pipedrive (or your WooCommerce store) and this report adds "
                             "customers, revenue and ROAS for every ad.", "impact": "High", "effort": "Low"})
        if not close:
            lead_items = [g for g in items if g["leads"] >= 5]
            if lead_items:
                c = min(lead_items, key=lambda g: g["cpl"])
                close = "Next: feed *%s*. Its leads cost %s each." % (_short_label(c["name"], 40), _money(c["cpl"]))
            else:
                close = "Next: connect your *CRM* to see which ads brought %s." % cust_word
    if len(recs) < 2:
        recs.append({"label": "Ongoing", "title": "Run this check *monthly*",
                     "body": "Deals keep closing after the month ends. A monthly rerun credits them to the ads that "
                             "brought them.", "impact": "Low", "effort": "Low"})
    secs.append({"type": "section-header", "number": "%02d" % num, "kicker": "Next steps", "title": "What to do *next*."})
    secs.append({"type": "recommendations", "items": _by_impact(recs)[:4]})

    # ---- notes --------------------------------------------------------------------------------
    notes = ["Ad spend: %s from %s, %s, across %s with spend." % (
        _money(spend), _join_list(plats), _range_text(_date(r.get("date")) for r in ads), _pl(len(items), level_word))]
    notes.append("Leads are matched to ads by utm_campaign (the campaign name), then utm_content (the ad name), "
                 "ignoring case and punctuation (%s tags one or two letters off counted for the closest campaign). "
                 "Of %s leads from your ads, %s (%s) matched an ad, %s only a campaign, and %s no campaign." % (
                     n(n_typo_paid), n(paid_leads), n(n_ad_paid), pct(share(n_ad_paid, paid_leads)), n(n_camp_paid),
                     n(paid_leads - n_ad_paid - n_camp_paid)))
    if rev_src == "deals":
        notes.append("%s: won deals from your %s, matched to leads by email. %s of %s won deals came from your ads; "
                     "%s could be tied to one ad." % (cust_label, crm, n(won_to_ads), n(won_total), n(won_to_ad)))
    elif rev_src == "orders":
        notes.append("Orders: %s paid orders from %s, matched to ads by the utm_campaign and utm_content each order "
                     "carries. %s came from your ads; %s could be tied to one ad." % (
                         n(won_total), store, n(won_to_ads), n(won_to_ad)))
    else:
        notes.append("Revenue is not connected. Connect HubSpot, Salesforce or Pipedrive, or WooCommerce, to add "
                     "customers, revenue and ROAS.")
    notes.append("Cost per lead = spend / leads. ROAS = revenue / spend." if rev_src else "Cost per lead = spend / leads.")
    if lead_plats:
        notes.append("Leads from %s are not priced: spend for %s is not connected." % (
            _join_list(lead_plats), "it" if len(lead_plats) == 1 else "them"))
    if has_prior and spend_prior:
        notes.append("Changes compare %s with %s." % (period, m["compare_label"]))
    secs.append({"type": "notes", "items": notes})

    summ = [{"value": _money(spend), "label": "Ad spend"}, {"value": n(paid_leads), "label": "Leads from ads"}]
    if rev_src:
        summ += [{"value": _money(paid_rev), "label": "Revenue from ads"}, {"value": _x(roas), "label": "ROAS"}]
    else:
        summ.append({"value": _money(cpl), "label": "Cost per lead"})
    bullets = []
    if best:
        bullets.append("Best: %s, %s per $1 on %s." % (best["name"], _per1(best["roas"]), _money(best["spend"])))
    if weak and rev_src:
        bullets.append("%s spent %s and brought back %s." % (_pl(len(weak), level_word), _money(sum(g["spend"] for g in weak)),
                                                             _money(sum(g["rev"] for g in weak))))
    elif no_lead:
        bullets.append("%s spent %s with no leads." % (_pl(len(no_lead), level_word), _money(sum(g["spend"] for g in no_lead))))
    if k_half:
        bullets.append("%s of your %ss brought half of your %s." % (n(k_half), level_word, what))
    secs.append({"type": "closing", "kicker": "The ads in one line", "title": close, "summary_stats": summ[:4],
                 "bullets": bullets[:3]})
    return {"meta": m, "sections": secs}



# ---------------------------------------------------------------------------
# CONVERSION TRUTH: what ad platforms report vs the leads your forms got
# ---------------------------------------------------------------------------
_CLICK_IDS = (("Google Ads", "gclid", ("gclid (HandL)", "gclid", "wbraid (HandL)", "gbraid (HandL)"),
               "Google Ads offline conversion import matches a lead to its click with it."),
              ("Meta Ads", "fbclid", ("fbclid (HandL)", "fbclid"),
               "Meta uses it to match a lead you send back to its ad click."),
              ("Microsoft Ads", "msclkid", ("msclkid (HandL)", "msclkid"),
               "Microsoft Ads offline conversion import needs it."))


def _over(rep, real):
    """Over-reported share: (reported - real) / real, as a percent."""
    return None if not real else 100.0 * (rep - real) / real


def _signed_pct(v):
    if v is None:
        return "–"
    r = int(round(v))
    return "%s%d%%" % ("+" if r > 0 else (MINUS if r < 0 else ""), abs(r))


def _truth_badge(rep, real):
    if rep <= 0 and real > 0:
        return {"label": "Not tracked", "tone": "warn"}
    if real <= 0 and rep > 0:
        return {"label": "No real leads", "tone": "bad"}
    if rep + real < 8:
        return {"label": "Low volume", "tone": "neutral"}
    o = _over(rep, real)
    if o is None:
        return {"label": "–", "tone": "neutral"}
    if abs(o) <= 10:
        return {"label": "Matches", "tone": "good"}
    if o > 40:
        return {"label": "Far over", "tone": "bad"}
    if o > 10:
        return {"label": "Over-reports", "tone": "warn"}
    return {"label": "Under-reports", "tone": "neutral"}


def build_conversion_truth(leads, ad_rows=None, prior=None, ad_rows_prior=None, brand_profile=None, customer_name=None,
                           customer_domain="", compare_label=None, form_label=None, prepared_by=None,
                           prepared_for=None, **kw):
    """Platform-reported conversions vs the leads UTM Grabber actually captured, per platform and campaign."""
    name = "Ad platforms vs reality"
    leads, prior, m = _setup(leads, prior, brand_profile, customer_name, customer_domain, compare_label,
                             prepared_by, prepared_for)
    if not leads:
        return empty_report(name, m)
    ads, ads_p = _ads(ad_rows), _ads(ad_rows_prior)
    start, end = _window(leads, ads)
    period = period_label(start, end)
    kicker = _kick(name, start, end)
    days = _days(start, end)
    when = _in_period(start, end)
    has_prior = len(prior) >= MIN_LEADS
    vs = m["compare_label"]
    bits = _bits(customer_domain, form_label, "%d days" % days if days else "")
    spend_p = _spend_by_platform(ads)
    rep_by = Counter()
    for r in ads:
        rep_by[r["platform"]] += r.get("conversions") or 0.0
    plats = [p for p in sorted(set(spend_p) | set(rep_by), key=lambda x: (-rep_by[x], -spend_p[x], x))
             if spend_p[p] > 0 or rep_by[p] > 0]
    chips = [("UTM Grabber", _pl(len(leads), "lead"))]
    for p in plats:
        chips.append((p, "%s conversions" % n(round(rep_by[p]))))
    m["sources"] = _chips(chips)

    by_lead = Counter(_plat(e) for e in leads if _plat(e))
    if not plats:
        rows = [{"platform": p, "real": {"value": c, "label": n(c)}} for p, c in by_lead.most_common(6)]
        extra = [{"type": "ranked-list", "title": "Leads your forms got from *ads*",
                  "columns": [{"key": "platform", "label": "Platform", "type": "platform"},
                              {"key": "real", "label": "Leads", "type": "bar"}], "rows": rows}] if rows else []
        return _short(m, kicker, "Your forms got %s from ads. Connect your ad accounts to *compare*." % _pl(
            sum(by_lead.values()), "lead"),
                      "The comparison needs your *ad platforms*.",
                      ["This report puts what Google Ads or Meta Ads say they converted next to the leads your forms "
                       "actually got.", "Connect Google Ads or Meta Ads to this chat and run it again."],
                      stats=[stat("Leads", n(len(leads))), stat("Leads from ads", n(sum(by_lead.values())))],
                      extra=extra, close_title="Next: connect *Google Ads* or Meta Ads and run this again.", bits=bits,
                      notes=["Leads: %s from UTM Grabber, %s." % (_pl(len(leads), "form submission"), period)])
    if sum(rep_by.values()) <= 0:
        return _short(m, kicker, "Your ad accounts report no *conversions* to compare.",
                      "There is nothing to *compare* yet.",
                      ["The ad data connected for %s has spend and clicks but zero conversions." % _join_list(plats),
                       "Ask for the conversions metric with the ad data (Google Ads: metrics.conversions; Meta Ads: "
                       "results or leads), or set up conversion tracking in the platform."],
                      stats=[stat("Leads from ads", n(sum(by_lead.get(p, 0) for p in plats))),
                             stat("Ad spend", _money(sum(spend_p.values())))],
                      close_title="Next: add *conversions* to your ad data and run this again.", bits=bits,
                      notes=["Ad data: %s, %s." % (_join_list(plats), period)])

    agg, camp_idx = _ad_agg(ads)
    camp = OrderedDict()
    for k, g in agg.items():
        c = camp.setdefault(k[:2], {"platform": g["platform"], "campaign": g["campaign"], "rep": 0.0, "spend": 0.0,
                                    "real": 0})
        c["rep"] += g["conv"]
        c["spend"] += g["spend"]
    real_by = Counter()
    no_tag, bad_tag, typo = Counter(), Counter(), Counter()
    tag_ex = Counter()
    for e in leads:
        p = _plat(e)
        k, ck = _match_ad(p, lead_campaign(e), lead_content(e), camp_idx)
        pf = p or (ck[0] if ck else None)
        if pf not in plats:
            continue
        real_by[pf] += 1
        if ck and ck in camp:
            camp[ck]["real"] += 1
            if norm_key(lead_campaign(e)) != ck[1]:
                typo[pf] += 1
                tag_ex[_safe(lead_campaign(e), 30)] += 1
        elif lead_campaign(e):
            bad_tag[pf] += 1
            tag_ex[_safe(lead_campaign(e), 30)] += 1
        else:
            no_tag[pf] += 1
    rep_total = sum(rep_by[p] for p in plats)
    real_total = sum(real_by[p] for p in plats)
    over_total = _over(rep_total, real_total)

    if real_total < MIN_LEADS:
        return _short(m, kicker, ("Only %s came from your ads: too few to check your *platforms*." % _pl(real_total, "lead"))
                      if real_total else "No lead could be tied to your *ad platforms* yet.",
                      "The check needs at least %d *leads* from ads." % MIN_LEADS,
                      ["Your ad platforms reported %s conversions %s; your forms got %s from those platforms." % (
                          n(round(rep_total)), when, _pl(real_total, "lead")),
                       ("With so few leads, one more swings the gap by %s points or more. Widen the date range." % n(
                           round(100.0 / max(real_total, 1)))) if real_total else
                       "No lead carried those platforms' utm_source and utm_medium or a click ID. Tag every ad URL "
                       "(Google Ads auto-tagging adds the gclid) and run this again."],
                      stats=[stat("Platforms reported", n(round(rep_total))), stat("Your forms got", n(real_total))],
                      close_title=("Next: widen the *date range* and run this again." if real_total else
                                   "Next: tag every ad with *UTM parameters* and run this again."), bits=bits,
                      notes=["Reported: conversions from %s, %s." % (_join_list(plats), period)])

    # prior period
    over_p, rep_p_total, real_p_total = None, None, None
    if ads_p and has_prior:
        rp = Counter()
        for r in ads_p:
            rp[r["platform"]] += r.get("conversions") or 0.0
        camp_p = _ad_agg(ads_p)[1]
        rl = 0
        for e in prior:
            pp = _plat(e)
            ck = _match_ad(pp, lead_campaign(e), lead_content(e), camp_p)[1]
            if (pp or (ck[0] if ck else None)) in plats:
                rl += 1
        rep_p_total, real_p_total = sum(rp[p] for p in plats), rl
        over_p = _over(rep_p_total, real_p_total)

    pinfo = []
    for p in plats:
        pinfo.append({"p": p, "rep": rep_by[p], "real": real_by[p], "over": _over(rep_by[p], real_by[p]),
                      "spend": spend_p[p]})
    worst_p = max([x for x in pinfo if x["over"] is not None] or pinfo, key=lambda x: (x["over"] or 0))
    camps = [c for c in camp.values() if c["rep"] > 0 or c["real"] > 0]
    for c in camps:
        c["over"] = _over(c["rep"], c["real"])
        c["name"] = _safe(c["campaign"] or "(no campaign name)", 40)
    big_camps = [c for c in camps if c["real"] >= 10 and c["over"] is not None]
    worst_c = max(big_camps, key=lambda c: c["over"]) if big_camps else None

    # ---- title ------------------------------------------------------------------------------
    gap = rep_total - real_total
    if over_total is not None and over_total >= 5:
        title = "Your ad platforms counted *%s* your forms never got." % _pl(int(round(gap)), "conversion")
    elif over_total is not None and over_total <= -5:
        title = "Your forms got *%s* more than your ad platforms counted." % _pl(int(round(-gap)), "lead")
    else:
        title = "Your ad platforms and your forms *agree* within %s." % pct(abs(over_total or 0))
    sub = []
    for x in pinfo[:2]:
        sub.append("%s reported %s for %s real leads (%s)" % (x["p"], n(round(x["rep"])), n(x["real"]), _signed_pct(x["over"])))
    subtitle = "; ".join(sub) + "."
    if worst_c and worst_c["over"] >= 40:
        subtitle += " %s is furthest off at %s." % (worst_c["name"], _signed_pct(worst_c["over"]))
    secs = [{"type": "title-block", "kicker": kicker, "title": title, "subtitle": subtitle, "meta_bits": bits}]

    # ---- 01 the gap ---------------------------------------------------------------------------
    secs.append({"type": "section-header", "number": "01", "kicker": "The gap",
                 "title": "What your platforms *reported*, and what arrived.",
                 "dek": "Platform conversions from your ad accounts; leads from your forms, as UTM Grabber saw them."})
    tone = "good" if abs(over_total or 0) <= 10 else ("bad" if (over_total or 0) > 40 else "warn")
    items = [{"kicker": "Platforms said", "value": n(round(rep_total)), "title": "conversions reported",
              "body": ", ".join("%s %s" % (x["p"], n(round(x["rep"]))) for x in pinfo[:3]) + "."},
             {"kicker": "Your forms got", "value": n(real_total), "title": "leads from those ads",
              "body": ", ".join("%s %s" % (x["p"], n(x["real"])) for x in pinfo[:3]) + "."},
             {"kicker": "Over-reported" if (over_total or 0) >= 0 else "Under-reported",
              "value": _signed_pct(over_total), "title": "more than real" if (over_total or 0) >= 0 else "fewer than real",
              "tone": tone,
              "body": ("%s: %s." % (vs, _signed_pct(over_p))) if over_p is not None else
              "%s counted for every real lead." % ("%.2f" % (rep_total / float(real_total)))}]
    secs.append({"type": "callouts", "items": items})
    steps = [{"label": "Reported by your ad platforms", "value": round(rep_total), "kind": "start"}]
    for x in pinfo[:4]:
        steps.append({"label": "%s %s" % (x["p"], "overcount" if x["rep"] >= x["real"] else "undercount"),
                      "value": -int(round(x["rep"] - x["real"])), "kind": "delta"})
    if len(pinfo) > 4:
        steps.append({"label": "Other platforms", "value": -int(round(sum(x["rep"] - x["real"] for x in pinfo[4:]))),
                      "kind": "delta"})
    steps.append({"label": "Leads your forms got", "value": real_total, "kind": "total"})
    wt = "*%s* over-reports the most: %s." % (worst_p["p"], _signed_pct(worst_p["over"])) if (worst_p["over"] or 0) > 10 \
        else "Every platform is within *10%%* of your real leads."
    wb = ["%s reported %s conversions; your forms got %s leads from it." % (worst_p["p"], n(round(worst_p["rep"])),
                                                                           n(worst_p["real"]))]
    if worst_p["spend"] and worst_p["rep"] and worst_p["real"]:
        wb.append("It shows %s per conversion; the real cost per lead is %s." % (
            _money(worst_p["spend"] / worst_p["rep"]), _money(worst_p["spend"] / worst_p["real"])))
    for x in pinfo:
        if x is not worst_p:
            wb.append("%s: %s reported, %s real (%s)." % (x["p"], n(round(x["rep"])), n(x["real"]), _signed_pct(x["over"])))
            break
    secs.append({"type": "chart-insight", "chart": {"type": "waterfall", "steps": steps},
                 "chart_title": "From reported to *real*",
                 "caption": "Red bars: conversions a platform counted that never reached your forms.",
                 "insight_kicker": "By platform", "insight_title": wt, "insight_body": wb[:3]})

    # ---- 02 campaigns ------------------------------------------------------------------------
    camps.sort(key=lambda c: (-c["rep"], -c["real"]))
    extra_rows = []
    for p in plats:
        if bad_tag[p]:
            extra_rows.append({"name": "Tag matches no campaign", "platform": p, "rep": "–",
                               "real": {"value": bad_tag[p], "label": n(bad_tag[p])}, "over": "–", "cpl": "–",
                               "status": {"label": "Fix tags", "tone": "warn"}, "_muted": True})
        if no_tag[p]:
            extra_rows.append({"name": "No campaign tag", "platform": p, "rep": "–",
                               "real": {"value": no_tag[p], "label": n(no_tag[p])}, "over": "–", "cpl": "–",
                               "status": {"label": "Add UTMs", "tone": "warn"}, "_muted": True})
    extra_rows = extra_rows[:3]
    rows = []
    for c in camps[:MAX_ROWS - len(extra_rows)]:
        rows.append({"name": c["name"], "platform": c["platform"], "rep": n(round(c["rep"])),
                     "real": {"value": c["real"], "label": n(c["real"])}, "over": _signed_pct(c["over"]),
                     "cpl": _money(c["spend"] / c["real"]) if c["real"] and c["spend"] else "–",
                     "status": _truth_badge(c["rep"], c["real"])})
        if worst_c is c:
            rows[-1]["_highlight"] = True
    rows.extend(extra_rows)
    secs.append({"type": "section-header", "number": "02", "kicker": "By campaign",
                 "title": "Which *campaigns* count leads that never came.",
                 "dek": "Reported conversions next to real leads, campaign by campaign."})
    secs.append({"type": "ranked-list", "title": "Reported vs real, by *campaign*",
                 "columns": [{"key": "name", "label": "Campaign", "type": "name"},
                             {"key": "platform", "label": "Platform", "type": "platform"},
                             {"key": "rep", "label": "Reported", "type": "mono-number", "align": "right"},
                             {"key": "real", "label": "Real leads", "type": "bar"},
                             {"key": "over", "label": "Over-reported", "type": "mono-number", "align": "right"},
                             {"key": "status", "label": "Status", "type": "badge"}],
                 "rows": rows,
                 "totals": {"name": "Total", "platform": "", "rep": n(round(rep_total)), "real": n(real_total),
                            "over": _signed_pct(over_total), "status": ""},
                 "caption": "Status: Matches within 10%, Over-reports from 10% to 40%, Far over above 40%. "
                            "The grey lines are real leads no campaign could claim."})

    # ---- 03 click IDs --------------------------------------------------------------------------
    sc = []
    cid = {}
    for p, idname, fields, why in _CLICK_IDS:
        pl_leads = [e for e in leads if (_plat(e) or None) == p]
        if p not in plats or not pl_leads:
            continue
        k = sum(1 for e in pl_leads if get_field(e, *fields))
        v = share(k, len(pl_leads))
        cid[p] = (v, k, len(pl_leads), idname)
        st = "pass" if v >= 90 else ("warn" if v >= 60 else "fail")
        sc.append({"label": "%s click ID (%s) on %s leads" % (p.split(" ")[0], idname, p), "value": pct(v), "status": st,
                   "detail": "%s of %s carry one. %s" % (n(k), n(len(pl_leads)), why)})
    ad_leads = [e for e in leads if (_plat(e) or None) in plats]
    if ad_leads:
        k = sum(1 for e in ad_leads if lead_email(e))
        v = share(k, len(ad_leads))
        sc.append({"label": "Email on leads from ads", "value": pct(v), "status": "pass" if v >= 95 else ("warn" if v >= 70 else "fail"),
                   "detail": "%s of %s. Google's enhanced conversions and Meta also match a lead on its hashed email." % (
                       n(k), n(len(ad_leads)))})
    if sc:
        secs.append({"type": "section-header", "number": "03", "kicker": "Ready to send back",
                     "title": "Can your real leads go back to the *platforms*?",
                     "dek": "To bid on real leads, each platform needs a way to match a lead to its click."})
        secs.append({"type": "scorecard", "title": "Click ID *capture*", "items": sc})

    # ---- next steps ------------------------------------------------------------------------------
    recs = []
    over_plats = [x for x in pinfo if (x["over"] or 0) > 10]
    if over_plats:
        w = max(over_plats, key=lambda x: x["over"])
        others = [x["p"] for x in over_plats if x is not w]
        recs.append({"label": "This month", "title": "Send real leads back to *%s*" % w["p"],
                     "body": "It reported %s conversions for %s real leads (%s), so its bidding learns from "
                             "conversions that never reached you. Import your UTM Grabber leads%s; UTM Grabber Premium "
                             "can send them for you.%s" % (
                                 n(round(w["rep"])), n(w["real"]), _signed_pct(w["over"]),
                                 " as server-side conversions" if w["p"] == "Meta Ads" else
                                 (" as offline conversions" if w["p"] in SEARCH_PLATFORMS else ""),
                                 (" Do the same for %s." % _join_list(others)) if others else ""),
                     "impact": "High", "effort": "Medium",
                     "metric": "%s conversions with no lead behind them" % n(int(round(w["rep"] - w["real"])))})
    if worst_c and worst_c["over"] >= 25:
        c = worst_c
        body = "It reported %s conversions; your forms got %s (%s)." % (n(round(c["rep"])), n(c["real"]),
                                                                     _signed_pct(c["over"]))
        if c["spend"]:
            body += " Its real cost per lead is %s, not the %s per conversion the platform shows." % (
                _money(c["spend"] / c["real"]), _money(c["spend"] / c["rep"]))
        recs.append({"label": "This week", "title": "Judge *%s* on real leads" % _safe(c["campaign"], 40), "body": body,
                     "impact": "High", "effort": "Low"})
    weak_id = [(p, v) for p, v in cid.items() if v[0] < 80]
    if weak_id:
        p, (v, k, tot, idname) = min(weak_id, key=lambda x: x[1][0])
        recs.append({"label": "This month", "title": "Keep the *%s* on %s leads" % (idname, p),
                     "body": "Only %s of %s leads (%s of %s) kept it. Check that redirects and form pages keep URL "
                             "parameters, so more leads can be matched when you send them back." % (
                                 pct(v), p, n(k), n(tot)),
                     "impact": "Medium", "effort": "Low"})
    n_typo, n_bad, n_none = sum(typo.values()), sum(bad_tag.values()), sum(no_tag.values())
    um = n_bad + n_none
    if n_typo + n_bad and share(n_typo + n_bad, real_total) >= 3:
        exs = ", ".join(x for x, _ in tag_ex.most_common(2))
        body = "%s leads from your ads carried a mistyped campaign tag%s." % (
            n(n_typo + n_bad), (" (for example %s)" % exs) if exs else "")
        if n_typo:
            body += (" %s were close enough to count for the right campaign here, but anywhere else they show up as "
                     "separate campaigns." % n(n_typo))
        recs.append({"label": "This month", "title": "Fix the *mistyped campaign tags*",
                     "body": body + " The UTM hygiene audit lists every one.", "impact": "Medium", "effort": "Low"})
    if len(recs) < 2:
        recs.append({"label": "Ongoing", "title": "Use form leads as your *source of truth*",
                     "body": "Judge cost per lead on the leads UTM Grabber captured, not on platform conversions.",
                     "impact": "Medium", "effort": "Low"})
    secs.append({"type": "section-header", "number": "04" if sc else "03", "kicker": "Next steps",
                 "title": "What to do *next*."})
    secs.append({"type": "recommendations", "items": _by_impact(recs)[:4]})

    notes = ["Reported: conversions from %s, %s, as each platform counts them (its own attribution window and "
             "conversion actions)." % (_join_list(plats), _range_text(_date(r.get("date")) for r in ads)),
             "Real: %s form submissions UTM Grabber captured in the same window from those platforms, recognized by "
             "utm_source and utm_medium or a click ID." % n(real_total),
             "Campaigns match when utm_campaign equals the campaign name, ignoring case and punctuation; %s tags "
             "one or two letters off counted for the closest campaign. %s leads from your ads matched no campaign "
             "(%s had no campaign tag)." % (n(n_typo), n(um), n(n_none)),
             "Over-reported = (reported - real) / real."]
    if over_p is not None:
        notes.append("%s: your platforms reported %s for %s real leads (%s)." % (
            _cap(vs), n(round(rep_p_total)), n(real_p_total), _signed_pct(over_p)))
    secs.append({"type": "notes", "items": notes})
    if over_plats:
        close = "Next: send real leads back to *%s*. It over-reported by %s." % (
            max(over_plats, key=lambda x: x["over"])["p"], pct(max(x["over"] for x in over_plats)))
    elif weak_id:
        close = "Next: keep the *click ID* on every ad lead before you send leads back."
    else:
        close = "Next: keep judging ads on *real leads*. Your platforms are close to the truth."
    secs.append({"type": "closing", "kicker": "The truth in one line", "title": close,
                 "summary_stats": [{"value": n(round(rep_total)), "label": "Reported"},
                                   {"value": n(real_total), "label": "Real leads"},
                                   {"value": _signed_pct(over_total), "label": "Over-reported"}] +
                                  ([{"value": _signed_pct(worst_c["over"]), "label": "Worst campaign"}] if worst_c else []),
                 "bullets": ["%s: %s reported, %s real." % (x["p"], n(round(x["rep"])), n(x["real"])) for x in pinfo[:3]]})
    return {"meta": m, "sections": secs}



# ---------------------------------------------------------------------------
# TRAFFIC TO LEAD: traffic that visits but never converts
# ---------------------------------------------------------------------------
_NOT_LEAD_PAGE = re.compile(r"(^|/)(careers?|jobs?|join-our-team|join-us|hiring|employment|privacy|privacy-policy|"
                            r"terms|terms-of-service|terms-and-conditions|legal|cookies?|cookie-policy|login|log-in|"
                            r"signin|sign-in|account|my-account|cart|checkout|thank-you|thanks|confirmation|404|"
                            r"wp-admin|wp-login)(/|$|\.)", re.I)
_CONTENT_PAGE = re.compile(r"(^|/)(blog|news|articles?|guides?|resources|learn|insights|posts?|stories|faq|help|"
                           r"library|tips|recipes|podcast)(/|$)", re.I)
_KIND_LABEL = {"content": "Blog and guides", "site": "Site pages", "not": "Not lead pages"}
_ORGANIC_SRC = {"google": "google", "bing": "bing", "duckduckgo": "duckduckgo", "yahoo": "yahoo", "ecosia": "ecosia",
                "brave": "search.brave.com", "openai/chatgpt": "chatgpt.com", "chatgpt": "chatgpt.com",
                "perplexity": "perplexity.ai", "gemini": "gemini.google.com", "claude": "claude.ai",
                "copilot": "copilot.microsoft.com"}


def _url_path(url):
    u = re.sub(r"^[a-z][a-z0-9+.\-]*://[^/]+", "", str(url or "").strip(), flags=re.I)
    u = u.split("?")[0].split("#")[0].strip()
    if not u or u == "/":
        return "/"
    return (u.rstrip("/") or "/").lower()


def _page_kind(path):
    if _NOT_LEAD_PAGE.search(path or ""):
        return "not"
    if _CONTENT_PAGE.search(path or ""):
        return "content"
    return "site"


def _lead_page(e):
    """The landing page of the visit that ended in the form (first-touch page, then form page, as fallbacks)."""
    u = get_field(e, "handl_landing_page (HandL)", "landing_page (HandL)", "landing_page (first touch, HandL)",
                  "Source URL", "source_url")
    return _url_path(u) if u else None


def _domain(s):
    d = re.sub(r"^https?://", "", str(s or "").strip().lower()).split("/")[0]
    return d[4:] if d.startswith("www.") else d


def _lead_sm(e):
    """(source, medium) the way Google Analytics would group the lead's visit, and how we knew:
    'tag' (UTM tags), 'inferred' (click ID, search engine or referring site) or 'none' (direct)."""
    src = get_field(e, "utm_source (HandL)", "utm_source").strip().lower()
    med = get_field(e, "utm_medium (HandL)", "utm_medium").strip().lower()
    if src or med:
        return (src or "(not set)", med or "(not set)"), "tag"
    if get_field(e, "gclid (HandL)", "gclid", "wbraid (HandL)", "gbraid (HandL)"):
        return ("google", "cpc"), "inferred"
    if get_field(e, "msclkid (HandL)", "msclkid"):
        return ("bing", "cpc"), "inferred"
    org = get_field(e, "organic_source_str (HandL)").strip().lower()
    if org:
        s2 = _ORGANIC_SRC.get(org)
        if s2:
            return (s2, "organic" if s2 in _SEARCH or s2 == "search.brave.com" else "referral"), "inferred"
    ref = _domain(get_field(e, "handl_ref_domain (HandL)", "referrer (HandL)"))
    if ref:
        if any(x in ref for x in ("google.", "bing.", "duckduckgo.", "yahoo.")):
            return (ref.split(".")[0] if not ref.startswith("search.") else ref, "organic"), "inferred"
        return (ref, "referral"), "inferred"
    return ("(direct)", "(none)"), "none"


def _sm_label(k):
    return "%s / %s" % (k[0], k[1])


def build_traffic_to_lead(leads, visit_rows=None, prior=None, visit_rows_prior=None, brand_profile=None,
                          customer_name=None, customer_domain="", compare_label=None, form_label=None,
                          prepared_by=None, prepared_for=None, **kw):
    """Google Analytics sessions vs UTM Grabber leads by channel, source / medium and landing page."""
    name = "Traffic that never converts"
    leads, prior, m = _setup(leads, prior, brand_profile, customer_name, customer_domain, compare_label,
                             prepared_by, prepared_for)
    if not leads:
        return empty_report(name, m)
    vis, vis_p = _visits(visit_rows), _visits(visit_rows_prior)
    start, end = _window(leads, vis)
    period = period_label(start, end)
    kicker = _kick(name, start, end)
    days = _days(start, end)
    when = _in_period(start, end)
    has_prior = len(prior) >= MIN_LEADS
    bits = _bits(customer_domain, form_label, "%d days" % days if days else "")
    sessions = sum(v["sessions"] for v in vis)
    total = len(leads)
    m["sources"] = _chips([("UTM Grabber", _pl(total, "lead")),
                           ("Google Analytics 4", ("%s sessions" % n(sessions)) if sessions else "")])

    if sessions <= 0:
        by = Counter(_lead_row(e) for e in leads)
        rows = [{"name": k, "leads": {"value": v, "label": n(v)}, "share": pct(share(v, total))}
                for k, v in by.most_common(8)]
        return _short(m, kicker, "Your forms got %s. Connect *analytics* to see the visits that didn't convert." % _pl(total, "lead"),
                      "Lead rates need your *sessions*.",
                      ["This report divides leads by visits, page by page and channel by channel, and visits come "
                       "from Google Analytics 4, which is not connected yet.",
                       "Connect Google Analytics 4 to this chat and run this again. Until then, the landing page "
                       "report ranks your pages by leads."],
                      stats=[stat("Leads", n(total)), stat("Channels", n(len(by)))],
                      extra=[{"type": "ranked-list", "title": "Leads by *channel*",
                              "columns": [{"key": "name", "label": "Channel", "type": "name"},
                                          {"key": "leads", "label": "Leads", "type": "bar"},
                                          {"key": "share", "label": "Share", "type": "pct", "align": "right"}],
                              "rows": rows}],
                      close_title="Next: connect *Google Analytics 4* and run this again.", bits=bits,
                      notes=["Leads: %s from UTM Grabber, %s." % (_pl(total, "form submission"), period)])
    if total < MIN_LEADS:
        return _short(m, kicker, "Only %s against %s sessions: too few to judge *lead rates*." % (
            _pl(total, "lead"), n(sessions)),
                      "Lead rates need at least %d *leads*." % MIN_LEADS,
                      ["With %s, one more lead moves a page's lead rate more than its traffic does." % _pl(total, "lead"),
                       "Widen the date range, or run this again once more submissions arrive."],
                      stats=[stat("Sessions", n(sessions)), stat("Leads", n(total)),
                             stat("Lead rate", _rate(share(total, sessions)))],
                      close_title="Next: widen the *date range* and run this again.", bits=bits,
                      notes=["Sessions: %s from Google Analytics 4, %s." % (n(sessions), period)])

    site_rate = share(total, sessions)
    # ---- channels -----------------------------------------------------------------------
    ch_s, ch_l = Counter(), Counter(_lead_row(e) for e in leads)
    for v in vis:
        ch_s[_visit_row(v)] += v["sessions"]
    # ---- source / medium ----------------------------------------------------------------
    sm_s = Counter()
    for v in vis:
        sm_s[(v["source"] or "(not set)", v["medium"] or "(not set)")] += v["sessions"]
    sm_l, how = Counter(), Counter()
    for e in leads:
        k, h = _lead_sm(e)
        sm_l[k] += 1
        how[h] += 1
    # ---- pages --------------------------------------------------------------------------
    pg_s, pg_eng = Counter(), Counter()
    for v in vis:
        pth = _url_path(v.get("landing_page")) if v.get("landing_page") else None
        if pth:
            pg_s[pth] += v["sessions"]
            pg_eng[pth] += v.get("engaged_sessions") or 0
    pg_l = Counter()
    no_page = 0
    for e in leads:
        pth = _lead_page(e)
        if pth:
            pg_l[pth] += 1
        else:
            no_page += 1
    has_pages = bool(pg_s)
    min_s = max(100, int(round(0.01 * sessions)))
    thr = min(site_rate / 4.0, 1.0)
    pages = []
    for pth, se in pg_s.items():
        ld = pg_l.get(pth, 0)
        pages.append({"path": pth, "sessions": se, "leads": ld, "rate": share(ld, se), "kind": _page_kind(pth),
                      "eng": share(pg_eng.get(pth, 0), se) if pg_eng.get(pth) else None})
    pages.sort(key=lambda x: -x["sessions"])
    leaks = [x for x in pages if x["sessions"] >= min_s and x["rate"] < thr and x["kind"] != "not"]
    skipped = [x for x in pages if x["sessions"] >= min_s and x["rate"] < thr and x["kind"] == "not"]
    leak_s = sum(x["sessions"] for x in leaks)
    leak_l = sum(x["leads"] for x in leaks)
    orphan = sum(c for pth, c in pg_l.items() if pth not in pg_s) if has_pages else 0

    # prior
    sessions_p = sum(v["sessions"] for v in vis_p) if vis_p else None
    rate_p = share(len(prior), sessions_p) if sessions_p and has_prior else None
    eng = sum(v.get("engaged_sessions") or 0 for v in vis)
    eng_p = sum(v.get("engaged_sessions") or 0 for v in vis_p) if vis_p else 0

    ch_rows = [k for k in ch_s if ch_s[k] >= max(1, 0.01 * sessions)]
    ch_rows.sort(key=lambda k: -share(ch_l.get(k, 0), ch_s[k]))
    best_ch = ch_rows[0] if ch_rows else None
    big_ch = [k for k in ch_rows if ch_s[k] >= 0.05 * sessions]
    worst_ch = big_ch[-1] if big_ch else (ch_rows[-1] if ch_rows else None)

    # ---- title ------------------------------------------------------------------------------
    if leaks:
        if len(leaks) == 1:
            title = "*%s* drew %s sessions and %s." % (_safe(leaks[0]["path"], 44), n(leak_s), _pl(leak_l, "lead"))
        else:
            title = "*%d busy pages* drew %s sessions and %s." % (len(leaks), n(leak_s), _pl(leak_l, "lead"))
    elif best_ch:
        title = "%s of your sessions became leads; *%s* converts best." % (_rate(site_rate), best_ch)
    else:
        title = "%s of your sessions became *leads*." % _rate(site_rate)
    sub = ["Site-wide, %s of %s sessions became a lead." % (_rate(site_rate), n(sessions))]
    if best_ch and worst_ch and best_ch != worst_ch:
        sub.append("%s turns %s of visits into leads; %s %s." % (
            best_ch, _rate(share(ch_l.get(best_ch, 0), ch_s[best_ch])), worst_ch,
            _rate(share(ch_l.get(worst_ch, 0), ch_s[worst_ch]))))
    secs = [{"type": "title-block", "kicker": kicker, "title": title, "subtitle": " ".join(sub), "meta_bits": bits}]

    _, ldaily = daily_counts(leads, start, end)
    stats = [_kpi("Sessions", n(sessions), sessions, sessions_p, spark=_spark(_daily(vis, start, end, "sessions")),
                  source="GA4"),
             _kpi("Leads", n(total), total, len(prior) if has_prior else None, spark=_spark(ldaily), source="UTM Grabber"),
             _kpi("Lead rate", _rate(site_rate), site_rate, rate_p, kind="pts", note="leads / sessions")]
    if has_pages:
        stats.append(stat("Sessions on leaking pages", n(leak_s), good="down",
                          note="%s of all sessions" % pct(share(leak_s, sessions))))
    if eng:
        er = share(eng, sessions)
        stats.append(_kpi("Engaged sessions", pct(er), er, share(eng_p, sessions_p) if eng_p and sessions_p else None,
                          kind="pts", note="of all sessions"))
    secs.append({"type": "stat-strip", "stats": stats[:5]})

    # ---- 01 channels --------------------------------------------------------------------------
    secs.append({"type": "section-header", "number": "01", "kicker": "By channel",
                 "title": "Which *channels* turn visits into leads.",
                 "dek": "Leads divided by sessions, with sessions grouped the way UTM Grabber groups leads."})
    show = ch_rows[:8]
    if show:
        ib = []
        if best_ch and worst_ch and best_ch != worst_ch:
            rb, rw = share(ch_l.get(best_ch, 0), ch_s[best_ch]), share(ch_l.get(worst_ch, 0), ch_s[worst_ch])
            if rw > 0:
                ib.append("That is %.1f times %s's %s." % (rb / rw, worst_ch, _rate(rw)))
            ib.append("%s drew %s sessions, %s of all, for %s." % (
                worst_ch, n(ch_s[worst_ch]), pct(share(ch_s[worst_ch], sessions)), _pl(ch_l.get(worst_ch, 0), "lead")))
        secs.append({"type": "chart-insight",
                     "chart": {"type": "bar-horizontal", "labels": show,
                               "values": [round(share(ch_l.get(k, 0), ch_s[k]), 2) for k in show], "unit": "%",
                               "highlight": 0, "show_share": False,
                               "notes": ["%s sessions, %s leads" % (_compact(ch_s[k]), _compact(ch_l.get(k, 0)))
                                         for k in show]},
                     "caption": "Lead rate by channel. Site-wide: %s." % _rate(site_rate),
                     "insight_kicker": "Best and worst",
                     "insight_title": "*%s* turns %s of visits into leads." % (
                         best_ch, _rate(share(ch_l.get(best_ch, 0), ch_s[best_ch]))),
                     "insight_body": ib[:3] or ["It is your best-converting channel %s." % when]})
    sm_rows = []
    for k, se in sm_s.most_common(MAX_ROWS):
        ld = sm_l.get(k, 0)
        r = share(ld, se)
        if ld == 0 and se >= min_s:
            badge = {"label": "No leads", "tone": "bad"}
        elif r >= site_rate:
            badge = {"label": "Above average", "tone": "good"}
        elif r >= site_rate / 2:
            badge = {"label": "Below average", "tone": "neutral"}
        else:
            badge = {"label": "Leaks", "tone": "warn"}
        sm_rows.append({"sm": _safe(_sm_label(k), 44), "ch": _visit_row({"source": k[0], "medium": k[1]}),
                        "sessions": {"value": se, "label": n(se)}, "leads": n(ld), "rate": _rate(r), "status": badge})
    secs.append({"type": "ranked-list", "title": "Sessions and leads by *source*",
                 "columns": [{"key": "sm", "label": "Source / medium", "type": "source"},
                             {"key": "ch", "label": "Channel", "type": "text"},
                             {"key": "sessions", "label": "Sessions", "type": "bar"},
                             {"key": "leads", "label": "Leads", "type": "mono-number", "align": "right"},
                             {"key": "rate", "label": "Lead rate", "type": "pct", "align": "right"},
                             {"key": "status", "label": "Status", "type": "badge"}],
                 "rows": sm_rows,
                 "caption": "Top %s of %s source / medium pairs by sessions. Above average means at or above the "
                            "site-wide %s." % (n(len(sm_rows)), n(len(sm_s)), _rate(site_rate))})

    # ---- 02 pages ----------------------------------------------------------------------------
    num = 2
    if has_pages:
        top = pages[:15]
        pts = [{"label": _safe(x["path"], 30), "x": x["sessions"], "y": round(x["rate"], 2), "size": x["sessions"],
                "group": _KIND_LABEL[x["kind"]]} for x in top]
        gem = None
        med_s = median([x["sessions"] for x in top]) if top else 0
        gems = [x for x in top if x["sessions"] <= med_s and x["leads"] >= 5 and x["rate"] >= 1.5 * site_rate and x["kind"] != "not"]
        if gems:
            gem = max(gems, key=lambda x: x["rate"])
        secs.append({"type": "section-header", "number": "%02d" % num, "kicker": "Landing pages",
                     "title": "Pages that get visits but no *leads*.",
                     "dek": "Each page's sessions in Google Analytics next to the leads whose visit started there. "
                            "Bubble size is sessions."})
        if len(pts) >= 3:
            if leaks:
                L = leaks[0]
                mt = "*%s* is your biggest leak." % _safe(L["path"], 40)
                mb = ["%s sessions, %s." % (n(L["sessions"]), _pl(L["leads"], "lead"))]
            else:
                mt = "No busy page *leaks*."
                mb = ["Every page with %s or more sessions converts at a quarter of your site average or better." % n(min_s)]
            if gem:
                mb.append("Hidden gem: %s converts %s of visits, %.1f times your average, with fewer sessions than "
                          "most of your top pages." % (gem["path"], _rate(gem["rate"]), gem["rate"] / site_rate))
            if skipped:
                mb.append("%s %s no leads, as expected for %s." % (
                    _join_list([x["path"] for x in skipped[:2]]), "gets" if len(skipped) == 1 else "get",
                    "that kind of page" if len(skipped) == 1 else "those pages"))
            secs.append({"type": "matrix", "chart_title": "Sessions vs *lead rate* by page", "points": _fold_groups(pts),
                         "x_label": "Sessions", "y_label": "Lead rate", "y_unit": "%",
                         "x_ref": med_s, "y_ref": round(site_rate, 2),
                         "quadrants": {"tl": "Needs traffic", "tr": "Stars", "bl": "Quiet", "br": "Leaks"},
                         "insight_kicker": "Read the map", "insight_title": mt, "insight_body": mb[:3]})
        lrows = []
        for x in [p_ for p_ in pages if p_["sessions"] >= min_s and p_["rate"] < site_rate / 2][:MAX_ROWS]:
            if x["kind"] == "not":
                badge = {"label": "Not a lead page", "tone": "neutral"}
            elif x["rate"] < thr:
                badge = {"label": "Add a call to action" if x["kind"] == "content" else "Add a form", "tone": "bad"}
            else:
                badge = {"label": "Below half", "tone": "warn"}
            row = {"page": _safe(x["path"], 52), "sessions": {"value": x["sessions"], "label": n(x["sessions"])},
                   "leads": n(x["leads"]), "rate": _rate(x["rate"]),
                   "eng": pct(x["eng"]) if x["eng"] is not None else "–", "fix": badge}
            if x["kind"] == "not":
                row["_muted"] = True
            lrows.append(row)
        if lrows:
            cols = [{"key": "page", "label": "Landing page", "type": "source"},
                    {"key": "sessions", "label": "Sessions", "type": "bar"},
                    {"key": "leads", "label": "Leads", "type": "mono-number", "align": "right"},
                    {"key": "rate", "label": "Lead rate", "type": "pct", "align": "right"}]
            if any(x["eng"] is not None for x in pages):
                cols.append({"key": "eng", "label": "Engaged", "type": "pct", "align": "right"})
            cols.append({"key": "fix", "label": "Fix", "type": "badge"})
            secs.append({"type": "ranked-list", "title": "*Traffic* that never converts", "columns": cols, "rows": lrows,
                         "caption": "Pages with %s or more sessions and under half your site-wide lead rate (%s). "
                                    "A page leaks below %s." % (n(min_s), _rate(site_rate), _rate(thr))})
        num += 1

    # ---- next steps ----------------------------------------------------------------------------
    recs = []
    close = None
    for i, L in enumerate(leaks[:2]):
        verb = "Add a call to action to" if L["kind"] == "content" else "Add a form to"
        if i == 0:
            recs.append({"label": "This week", "title": "%s *%s*" % (verb, _safe(L["path"], 44)),
                         "body": "It drew %s sessions (%s of all) and %s. Put a short form or a clear next step near "
                                 "the top, and link to your best-converting page." % (
                                     n(L["sessions"]), pct(share(L["sessions"], sessions)), _pl(L["leads"], "lead")),
                         "impact": "High", "effort": "Low",
                         "metric": "%s sessions, %s" % (n(L["sessions"]), _pl(L["leads"], "lead"))})
            close = "Next: %s *%s*. It drew %s sessions and %s." % (verb[0].lower() + verb[1:], _safe(L["path"], 44),
                                                                   n(L["sessions"]), _pl(L["leads"], "lead"))
        else:
            recs.append({"label": "This month", "title": "Do the same on *%s*" % _safe(L["path"], 44),
                         "body": "%s sessions, %s." % (n(L["sessions"]), _pl(L["leads"], "lead")),
                         "impact": "Medium", "effort": "Low"})
    if has_pages and gem:
        recs.append({"label": "This month", "title": "Send more traffic to *%s*" % _safe(gem["path"], 44),
                     "body": "It turns %s of visits into leads, %.1f times your site average, but gets %s sessions, "
                             "fewer than most of your top pages. Point ads and internal links at it." % (
                                 _rate(gem["rate"]), gem["rate"] / site_rate, n(gem["sessions"])),
                     "impact": "Medium", "effort": "Low"})
    fixable = [k for k in big_ch if k != "Direct" and ch_s[k] >= 0.1 * sessions
               and share(ch_l.get(k, 0), ch_s[k]) < site_rate / 2]
    if fixable:
        worst_fix = fixable[-1]
        recs.append({"label": "This month", "title": "Fix where *%s* visitors land" % worst_fix,
                     "body": "%s sessions turned into %s, a %s lead rate. Send that traffic to pages with a form "
                             "instead of articles or the home page." % (
                                 n(ch_s[worst_fix]), _pl(ch_l.get(worst_fix, 0), "lead"),
                                 _rate(share(ch_l.get(worst_fix, 0), ch_s[worst_fix]))),
                     "impact": "Medium", "effort": "Medium"})
    dead = [(k, se) for k, se in sm_s.items() if se >= min_s and not sm_l.get(k)]
    ghost = [(k, c) for k, c in sm_l.items() if c >= 3 and k not in sm_s and k != ("(direct)", "(none)")]
    if dead or ghost:
        if ghost:
            k, c = max(ghost, key=lambda x: x[1])
            body = "%s leads arrived tagged %s, a source / medium your analytics never recorded. Use the same " \
                   "utm_source and utm_medium names everywhere so both tools agree." % (n(c), _sm_label(k))
            ttl = "Line up your *UTM names*"
        else:
            k, se = max(dead, key=lambda x: x[1])
            body = "Analytics shows %s sessions from %s but no lead carries that source. Check that links from it " \
                   "keep their UTM tags all the way to the form." % (n(se), _sm_label(k))
            ttl = "Check tagging on *%s*" % _safe(_sm_label(k), 40)
        recs.append({"label": "This month", "title": ttl, "body": body, "impact": "Medium", "effort": "Low"})
    if not close:
        if best_ch:
            close = "Next: send more visitors through *%s*. It converts %s of sessions." % (
                best_ch, _rate(share(ch_l.get(best_ch, 0), ch_s[best_ch])))
        else:
            close = "Next: keep your best pages *fed*."
    if len(recs) < 2:
        recs.append({"label": "Ongoing", "title": "Check lead rates *monthly*",
                     "body": "A page that stops converting shows up here weeks before it shows up in total leads.",
                     "impact": "Low", "effort": "Low"})
    secs.append({"type": "section-header", "number": "%02d" % num, "kicker": "Next steps", "title": "What to do *next*."})
    secs.append({"type": "recommendations", "items": _by_impact(recs)[:4]})

    notes = ["Sessions: %s from Google Analytics 4, %s, by session source / medium%s." % (
        n(sessions), _range_text(_date(v.get("date")) for v in vis), " and landing page" if has_pages else ""),
        "Leads: %s from UTM Grabber, matched by the same source / medium. %s carried UTM tags; %s without tags were "
        "placed by click ID, search engine or referring site, as analytics does; %s count as direct." % (
            n(total), n(how["tag"]), n(how["inferred"]), n(how["none"]))]
    if has_pages:
        notes.append("A lead's page is where the visit that ended in the form began. A page leaks when it has %s or "
                     "more sessions and a lead rate under %s, a quarter of your site-wide %s." % (
                         n(min_s), _rate(thr), _rate(site_rate)))
        notes.append("Careers, legal, login, cart and thank-you pages are shown but never counted as leaks.")
        if orphan or no_page:
            notes.append("%s leads started on a page analytics shows no sessions for, and %s had no landing page." % (
                n(orphan), n(no_page)))
    if has_prior and sessions_p:
        notes.append("Changes compare %s with %s." % (period, m["compare_label"]))
    secs.append({"type": "notes", "items": notes})
    summ = [{"value": n(sessions), "label": "Sessions"}, {"value": n(total), "label": "Leads"},
            {"value": _rate(site_rate), "label": "Lead rate"}]
    if has_pages:
        summ.append({"value": n(leak_s), "label": "Sessions on leaking pages"})
    bullets = []
    if leaks:
        bullets.append("%s leaking %s: %s." % (n(len(leaks)), "page" if len(leaks) == 1 else "pages",
                                               _join_list([x["path"] for x in leaks[:3]])))
    if best_ch:
        bullets.append("Best channel: %s at %s." % (best_ch, _rate(share(ch_l.get(best_ch, 0), ch_s[best_ch]))))
    if worst_ch and worst_ch != best_ch:
        bullets.append("Weakest big channel: %s at %s." % (worst_ch, _rate(share(ch_l.get(worst_ch, 0), ch_s[worst_ch]))))
    secs.append({"type": "closing", "kicker": "The traffic in one line", "title": close, "summary_stats": summ[:4],
                 "bullets": bullets[:3]})
    return {"meta": m, "sections": secs}



# ---------------------------------------------------------------------------
# PIPELINE: close rate, revenue and days to close by first-touch channel
# ---------------------------------------------------------------------------
def _deal_days(d):
    a, b = _date(d.get("created")), _date(d.get("closed"))
    if a and b and b >= a:
        return (b - a).days
    return None


def _pipe_agg(pairs, keyfn):
    agg = OrderedDict()
    for d, e in pairs:
        k = keyfn(e) if e is not None else NO_LEAD
        g = agg.setdefault(k, {"k": k, "deals": 0, "won": 0, "lost": 0, "open": 0, "rev": 0.0, "days": [],
                               "open_amt": 0.0})
        g["deals"] += 1
        g[d["stage"]] += 1
        if d["stage"] == "won":
            g["rev"] += d.get("amount") or 0.0
            dd = _deal_days(d)
            if dd is not None:
                g["days"].append(dd)
        elif d["stage"] == "open":
            g["open_amt"] += d.get("amount") or 0.0
    for g in agg.values():
        dec = g["won"] + g["lost"]
        g["close"] = share(g["won"], dec) if dec else None
        g["dec"] = dec
        g["avg"] = safe_div(g["rev"], g["won"]) if g["won"] else None
        g["med_days"] = _median(g["days"])
    return agg


def build_pipeline(leads, deal_rows=None, ad_rows=None, prior=None, deal_rows_prior=None, brand_profile=None,
                   customer_name=None, customer_domain="", compare_label=None, form_label=None, prepared_by=None,
                   prepared_for=None, **kw):
    """CRM deals joined to leads by email: close rate, won revenue, deal size and days to close by first touch."""
    name = "Close rate by first touch"
    leads, prior, m = _setup(leads, prior, brand_profile, customer_name, customer_domain, compare_label,
                             prepared_by, prepared_for)
    if not leads:
        return empty_report(name, m)
    deals, deals_p = _deals(deal_rows), _deals(deal_rows_prior)
    ads = _ads(ad_rows)
    crm = _crm(kw, deal_rows)
    history = list(kw.get("history") or kw.get("leads_history") or [])
    start, end = _window(leads, ads)
    period = period_label(start, end)
    kicker = _kick(name, start, end)
    days = _days(start, end)
    vs = m["compare_label"]
    bits = _bits(customer_domain, form_label, "%d days" % days if days else "")
    spend_p = _spend_by_platform(ads)
    plats = [k for k, v in spend_p.most_common() if v > 0]
    chips = [("UTM Grabber", _pl(len(leads), "lead"))]
    if deals:
        chips.append((crm, _pl(len(deals), "deal")))
    for p in plats:
        chips.append((p, "%s spend" % _money(spend_p[p])))
    m["sources"] = _chips(chips)

    if not deals:
        ft = Counter(_ft_row(e) for e in leads)
        rows = [{"name": k, "leads": {"value": v, "label": n(v)}, "share": pct(share(v, len(leads)))}
                for k, v in ft.most_common(8)]
        return _short(m, kicker, "Your forms got %s. Connect your *CRM* to see which ones close." % _pl(len(leads), "lead"),
                      "Close rates need your *deals*.",
                      ["Close rate, revenue and days to close come from deals in your CRM, matched to leads by email.",
                       "Connect HubSpot, Salesforce or Pipedrive to this chat and run this again. Below is where your "
                       "leads first found you, so the report has a head start."],
                      stats=[stat("Leads", n(len(leads))), stat("First-touch channels", n(len(ft)))],
                      extra=[{"type": "ranked-list", "title": "Leads by *first touch*",
                              "columns": [{"key": "name", "label": "First touch", "type": "name"},
                                          {"key": "leads", "label": "Leads", "type": "bar"},
                                          {"key": "share", "label": "Share", "type": "pct", "align": "right"}],
                              "rows": rows}],
                      close_title="Next: connect *HubSpot* or your CRM and run this again.", bits=bits,
                      notes=["Leads: %s from UTM Grabber, %s." % (_pl(len(leads), "form submission"), period)])

    idx = _person_index(leads, prior, history)
    matched = _match_deals(deals, idx)
    pairs = [(d, e) for d, e, _li in matched]
    mpairs = [(d, e) for d, e in pairs if e is not None]
    n_un = len(pairs) - len(mpairs)
    if len(mpairs) < MIN_LEADS:
        head = ("Only %s matched a form lead: too few to compare *channels*." % _pl(len(mpairs), "deal")
                if mpairs else "No *CRM deals* matched a form lead yet.")
        return _short(m, kicker, head,
                      "Close rates need at least %d *matched deals*." % MIN_LEADS,
                      ["%s of %s deals in your %s share an email with a UTM Grabber lead." % (
                          n(len(mpairs)), n(len(deals)), crm),
                       "Make sure the CRM stores the email from the form, widen the date range, and run this again."],
                      stats=[stat("Deals", n(len(deals))), stat("Matched to a lead", n(len(mpairs)))],
                      close_title="Next: widen the *date range* and run this again.", bits=bits,
                      notes=["Deals are matched to leads by lowercase email."])

    direct = sum(1 for d, e in mpairs if _ft_row(e) == "Direct" and _lead_row(e) == "Direct")
    if share(direct, len(mpairs)) >= 90:
        return _short(m, kicker, "%s matched a form lead, but those leads carry no *source*." % _pl(len(mpairs), "deal"),
                      "Channels need a *source* on each lead.",
                      ["%s of %s matched deals came from leads with no UTM tags, click ID or referrer, so every one "
                       "counts as Direct." % (n(direct), n(len(mpairs))),
                       "Check that UTM Grabber is active on every form page, then run this again."],
                      stats=[stat("Deals", n(len(deals))), stat("Matched to a lead", n(len(mpairs)))],
                      close_title="Next: check *UTM Grabber* is on every form, then run this again.", bits=bits,
                      notes=["Deals are matched to leads by lowercase email."])
    ft = _pipe_agg(pairs, _ft_row)
    lt = _pipe_agg(pairs, _lead_row)
    tot = _pipe_agg([(d, e if e is None else 0) for d, e in pairs], lambda _e: "All")
    T = list(tot.values())
    T_all = {"deals": len(deals), "won": sum(g["won"] for g in T), "lost": sum(g["lost"] for g in T),
             "open": sum(g["open"] for g in T), "rev": sum(g["rev"] for g in T),
             "days": [x for g in T for x in g["days"]], "open_amt": sum(g["open_amt"] for g in T)}
    T_all["dec"] = T_all["won"] + T_all["lost"]
    T_all["close"] = share(T_all["won"], T_all["dec"]) if T_all["dec"] else None
    T_all["avg"] = safe_div(T_all["rev"], T_all["won"]) if T_all["won"] else None
    T_all["med_days"] = _median(T_all["days"])
    no_ft = sum(1 for d, e in mpairs if not _has_first_touch(e))

    # prior period
    P = None
    immature = False
    if deals_p:
        idx_p = _person_index(prior, history, leads)
        pp = _match_deals(deals_p, idx_p)
        pw = [d for d, _e, _li in pp if d["stage"] == "won"]
        w = len(pw)
        l_ = sum(1 for d, _e, _li in pp if d["stage"] == "lost")
        rv = sum(d["amount"] for d in pw)
        dd = [x for x in (_deal_days(d) for d in pw) if x is not None]
        P = {"deals": len(deals_p), "won": w, "rev": rv, "close": share(w, w + l_) if w + l_ else None,
             "avg": safe_div(rv, w) if w else None, "med_days": _median(dd),
             "open_share": share(sum(1 for d in deals_p if d["stage"] == "open"), len(deals_p))}
        if share(T_all["open"], len(deals)) - P["open_share"] >= 10:
            immature = True

    # channel lists
    rows_ft = [g for g in ft.values() if g["k"] != NO_LEAD]
    rows_ft.sort(key=lambda g: (-g["deals"], g["k"]))
    min_dec = max(10, int(round(0.05 * sum(g["dec"] for g in rows_ft))))
    big = [g for g in rows_ft if g["dec"] >= min_dec and g["close"] is not None]
    best = max(big, key=lambda g: g["close"]) if big else None
    top_rev = max(rows_ft, key=lambda g: g["rev"]) if rows_ft else None
    m_rev = sum(g["rev"] for g in rows_ft)

    # ---- title ------------------------------------------------------------------------------
    if best and T_all["close"] is not None and best["close"] - T_all["close"] >= 5:
        title = "Leads whose first visit came from *%s* close %s of decided deals." % (best["k"], pct(best["close"]))
    elif top_rev and m_rev:
        title = "*%s* first touches brought %s of won revenue." % (top_rev["k"], pct(share(top_rev["rev"], m_rev)))
    else:
        title = "%s from your forms, *%s* won so far." % (_pl(len(mpairs), "deal"), n(T_all["won"]))
    sub = "%s deals, %s won so far (%s of decided deals), worth %s." % (
        n(len(deals)), n(T_all["won"]), pct(T_all["close"]) if T_all["close"] is not None else "–", _money(T_all["rev"]))
    if T_all["open"]:
        sub += " %s still open." % (_pl(T_all["open"], "deal") + (" is" if T_all["open"] == 1 else " are"))
    secs = [{"type": "title-block", "kicker": kicker, "title": title, "subtitle": sub, "meta_bits": bits}]

    def pv(key):
        return None if (P is None or (immature and key in ("won", "rev", "med_days"))) else P.get(key)
    stats = [_kpi("Deals", n(len(deals)), len(deals), pv("deals"), source=crm),
             _kpi("Won", n(T_all["won"]), T_all["won"], pv("won"),
                  note="%s still open" % n(T_all["open"]) if T_all["open"] else None),
             _kpi("Close rate", pct(T_all["close"]) if T_all["close"] is not None else "–", T_all["close"], pv("close"),
                  kind="pts", note="won / decided deals"),
             _kpi("Won revenue", _money(T_all["rev"]), T_all["rev"], pv("rev")),
             _kpi("Average deal", _money(T_all["avg"]) if T_all["avg"] else "–", T_all["avg"], pv("avg"))]
    if T_all["med_days"] is not None:
        stats.append(_kpi("Days to close", n(T_all["med_days"]), T_all["med_days"], pv("med_days"), good="down",
                          note="median, won deals"))
    if len(stats) > 4:
        for x in stats:
            x.pop("source", None)
    secs.append({"type": "stat-strip", "stats": stats[:6]})

    # takeaway: who opens vs who closes
    diffs = []
    for k in set(g["k"] for g in rows_ft) | set(k for k in lt if k != NO_LEAD):
        a = ft.get(k, {}).get("rev", 0.0)
        b = lt.get(k, {}).get("rev", 0.0)
        diffs.append((k, a, b))
    opener = max(diffs, key=lambda x: x[1] - x[2]) if diffs else None
    closer = max(diffs, key=lambda x: x[2] - x[1]) if diffs else None
    if opener and opener[1] - opener[2] > 0.02 * max(m_rev, 1):
        k, a, b = opener
        tk_t = "*%s* starts more won revenue than it gets credit for." % k
        tk_b = ["As the first touch it started %s of won revenue (%s); as the last touch it gets %s." % (
            _money(a), pct(share(a, m_rev)), _money(b))]
        if closer and closer[0] != k and closer[2] > closer[1]:
            tk_b.append("%s is the opposite: %s on last touch, %s on first." % (closer[0], _money(closer[2]),
                                                                                 _money(closer[1])))
    else:
        k = top_rev["k"] if top_rev else "Direct"
        tk_t = "*%s* leads both first and last touch revenue." % k
        tk_b = ["First touch and last touch tell the same story this period."]
    secs.append({"type": "insight-card", "kicker": "The takeaway", "title": tk_t, "body": tk_b})

    # ---- 01 flow ------------------------------------------------------------------------------
    keep = [g["k"] for g in rows_ft[:5]]
    if len(rows_ft) > 6:
        fold = set(g["k"] for g in rows_ft[5:])
    else:
        keep = [g["k"] for g in rows_ft]
        fold = set()
    links = Counter()
    for d, e in mpairs:
        k = _ft_row(e)
        if k in fold:
            k = "Other"
        links[(k, {"won": "Won", "lost": "Lost", "open": "Open"}[d["stage"]])] += 1
    secs.append({"type": "section-header", "number": "01", "kicker": "First touch to outcome",
                 "title": "Where your *deals* started, and how they ended.",
                 "dek": "Every deal matched to a form lead, by the channel of that person's first visit."})
    secs.append({"type": "flow", "chart_title": "First touch to *outcome*", "left_title": "First touch",
                 "right_title": "Outcome", "links": [{"from": a, "to": b, "value": v} for (a, b), v in links.items()],
                 "left_order": keep + (["Other"] if fold else []), "right_order": ["Won", "Open", "Lost"],
                 "caption": "%s of %s deals matched a form lead by email." % (n(len(mpairs)), n(len(deals)))})
    cols = [{"key": "name", "label": "First touch", "type": "name"},
            {"key": "deals", "label": "Deals", "type": "bar"},
            {"key": "won", "label": "Won", "type": "mono-number", "align": "right"},
            {"key": "close", "label": "Close rate", "type": "pct", "align": "right"},
            {"key": "rev", "label": "Won revenue", "type": "money", "align": "right"},
            {"key": "avg", "label": "Average deal", "type": "money", "align": "right"}]
    if T_all["med_days"] is not None:
        cols.append({"key": "days", "label": "Days to close", "type": "mono-number", "align": "right"})
    first_cust = {g["k"]: g["won"] for g in rows_ft}
    if plats:
        cols.append({"key": "cpc", "label": "Ad cost per customer", "type": "money", "align": "right"})
    rows = []
    tab = rows_ft[:MAX_ROWS - (1 if n_un else 0)]
    if n_un:
        tab = tab + [ft[NO_LEAD]]
    for g in tab:
        row = {"name": g["k"], "deals": {"value": g["deals"], "label": n(g["deals"])}, "won": n(g["won"]),
               "close": pct(g["close"]) if g["close"] is not None else "–", "rev": _money(g["rev"]) if g["rev"] else "–",
               "avg": _money(g["avg"]) if g["avg"] else "–",
               "days": n(g["med_days"]) if g["med_days"] is not None else "–",
               "cpc": _money(spend_p[g["k"]] / g["won"]) if g["k"] in plats and g["won"] else "–"}
        if best is not None and g is best:
            row["_highlight"] = True
        if g["k"] == NO_LEAD:
            row["_muted"] = True
        rows.append(row)
    totals = {"name": "Total", "deals": n(len(deals)), "won": n(T_all["won"]),
              "close": pct(T_all["close"]) if T_all["close"] is not None else "–", "rev": _money(T_all["rev"]),
              "avg": _money(T_all["avg"]) if T_all["avg"] else "–",
              "days": n(T_all["med_days"]) if T_all["med_days"] is not None else "–",
              "cpc": _money(sum(spend_p[p] for p in plats) / sum(first_cust.get(p, 0) for p in plats))
              if plats and sum(first_cust.get(p, 0) for p in plats) else "–"}
    secs.append({"type": "ranked-list", "title": "Close rate by *first touch*", "columns": cols, "rows": rows,
                 "totals": totals,
                 "caption": "Close rate counts won and lost deals; open deals are left out.%s" % (
                     " Ad cost per customer divides each platform's spend by the customers whose first visit came "
                     "from it." if plats else "")})

    # ---- 02 first vs last ------------------------------------------------------------------------
    keys = sorted(set(k for k, a, b in diffs), key=lambda k: -max(ft.get(k, {}).get("rev", 0.0), lt.get(k, {}).get("rev", 0.0)))[:6]
    crow = []
    for k in keys:
        a, b = ft.get(k, {}).get("rev", 0.0), lt.get(k, {}).get("rev", 0.0)
        if a or b:
            crow.append({"label": k, "a": round(a, 2), "b": round(b, 2), "a_display": _money(a) if a else "–",
                         "b_display": _money(b) if b else "–"})
    if len(crow) >= 2:
        secs.append({"type": "section-header", "number": "02", "kicker": "First vs last touch",
                     "title": "Who starts the journeys that *close*.",
                     "dek": "The same won revenue, credited two ways."})
        secs.append({"type": "comparison", "a": {"label": "First touch", "sub": "started the journey"},
                     "b": {"label": "Last touch", "sub": "brought the form fill"}, "rows": crow,
                     "caption": "Won revenue from deals with a form lead, by channel. Each deal counts once on each "
                                "side, so both columns add up to %s." % _money(m_rev)})

    # ---- next steps ------------------------------------------------------------------------------
    recs = []
    close = None
    if opener and opener[1] - opener[2] > 0.02 * max(m_rev, 1):
        k, a, b = opener
        recs.append({"label": "This month", "title": "Judge *%s* on first touch" % k,
                     "body": "It started %s of won revenue but gets %s on last touch. Cutting it on last-touch numbers "
                             "would cut the journeys it starts." % (_money(a), _money(b)),
                     "impact": "High", "effort": "Low"})
        close = "Next: judge *%s* on first touch. It started %s of won revenue." % (k, pct(share(a, m_rev)))
    if best and T_all["close"] is not None and best["close"] - T_all["close"] >= 5:
        recs.append({"label": "This month", "title": "Feed *%s*" % best["k"],
                     "body": "Its leads close at %s vs %s overall, at %s per deal." % (
                         pct(best["close"]), pct(T_all["close"]), _money(best["avg"])),
                     "impact": "High", "effort": "Medium"})
        close = close or "Next: feed *%s*. Its leads close at %s." % (best["k"], pct(best["close"]))
    if T_all["open"]:
        as_of = max([x for x in (_date(d.get("closed")) for d in deals) if x] +
                    [x for x in (_date(d.get("created")) for d in deals) if x] or [end])
        stale = [d for d in deals if d["stage"] == "open" and _date(d.get("created"))
                 and (as_of - _date(d.get("created"))).days > 14]
        body = "%s worth %s are still open." % (_pl(T_all["open"], "deal"), _money(T_all["open_amt"])) if T_all["open_amt"] \
            else "%s are still open." % _pl(T_all["open"], "deal")
        if stale:
            body += " %s of them were created more than 14 days before %s." % (n(len(stale)), _md(as_of))
        recs.append({"label": "This week", "title": "Follow up the *%s*" % _pl(T_all["open"], "open deal"),
                     "body": body + " Give each one a dated next step in %s." % crm, "impact": "High", "effort": "Low"})
        close = close or "Next: follow up the *%s* in %s." % (_pl(T_all["open"], "open deal"), crm)
    slow = [g for g in rows_ft if g["won"] >= 5 and g["med_days"] is not None]
    if T_all["med_days"] is not None and len(slow) >= 2:
        s_ = max(slow, key=lambda g: g["med_days"])
        if s_["med_days"] >= T_all["med_days"] + 3:
            recs.append({"label": "This month", "title": "Speed up *%s* deals" % s_["k"],
                         "body": "They take %s days to close (median) vs %s overall. Send those leads a faster first "
                                 "reply or a booking link." % (n(s_["med_days"]), n(T_all["med_days"])),
                         "impact": "Medium", "effort": "Low"})
    if plats:
        pc = [(p, spend_p[p] / first_cust[p]) for p in plats if first_cust.get(p)]
        if len(pc) >= 2:
            pc.sort(key=lambda x: x[1])
            if pc[-1][1] >= 1.3 * pc[0][1]:
                recs.append({"label": "This month", "title": "Shift budget toward *%s*" % pc[0][0],
                             "body": "Customers whose first visit came from %s cost %s each in ad spend; from %s, %s." % (
                                 pc[0][0], _money(pc[0][1]), pc[-1][0], _money(pc[-1][1])),
                             "impact": "Medium", "effort": "Low"})
    if n_un and share(n_un, len(deals)) >= 5:
        recs.append({"label": "This month", "title": "Capture the source of *%s*" % _pl(n_un, "deal"),
                     "body": "%s of %s deals match no form lead, so their first touch is unknown. Ask new customers how "
                             "they found you, or use a tracked phone number." % (n(n_un), n(len(deals))),
                     "impact": "Medium", "effort": "Low"})
    if len(recs) < 2:
        recs.append({"label": "Ongoing", "title": "Rerun this as deals *close*",
                     "body": "Open deals keep closing after the month ends; a rerun in two weeks firms up every close rate.",
                     "impact": "Low", "effort": "Low"})
    if not close:
        close = "Next: rerun this as the *open deals* close."
    secs.append({"type": "section-header", "number": "03" if len(crow) >= 2 else "02", "kicker": "Next steps",
                 "title": "What to do *next*."})
    secs.append({"type": "recommendations", "items": _by_impact(recs)[:4]})

    notes = ["Deals: %s from your %s, created %s. %s (%s) matched a form lead by email; %s match no form lead." % (
        n(len(deals)), crm, _range_text(_date(d.get("created")) for d in deals) or "in this window", n(len(mpairs)),
        pct(share(len(mpairs), len(deals))), n(n_un)),
        "First touch is the channel of the person's first recorded visit (UTM Grabber's first-touch fields), with "
        "ad platforms split out when that visit shows one; last touch is the visit that ended in the form.",
        "Close rate = won / (won + lost). Days to close = close date minus create date, won deals only."]
    if no_ft:
        notes.append("%s matched leads had no first-touch data, so their last touch stands in." % n(no_ft))
    if plats:
        notes.append("Ad spend: %s from %s, %s." % (_money(sum(spend_p.values())), _join_list(plats),
                                                     _range_text(_date(r.get("date")) for r in ads)))
    if P is not None:
        notes.append("Changes compare %s with %s." % (period, vs))
        if immature:
            notes.append("Won deals, revenue and days to close are not compared with %s: %s of this period's deals "
                         "are still open." % (vs, pct(share(T_all["open"], len(deals)))))
    secs.append({"type": "notes", "items": notes})
    summ = [{"value": n(len(deals)), "label": "Deals"}, {"value": n(T_all["won"]), "label": "Won"},
            {"value": pct(T_all["close"]) if T_all["close"] is not None else "–", "label": "Close rate"},
            {"value": _money(T_all["rev"]), "label": "Won revenue"}]
    bullets = []
    if best:
        bullets.append("Best close rate: %s at %s on %s decided deals." % (best["k"], pct(best["close"]), n(best["dec"])))
    if top_rev:
        bullets.append("Most won revenue by first touch: %s, %s." % (top_rev["k"], _money(top_rev["rev"])))
    if T_all["open"]:
        bullets.append("%s still open." % (_pl(T_all["open"], "deal") + (" is" if T_all["open"] == 1 else " are")))
    secs.append({"type": "closing", "kicker": "The pipeline in one line", "title": close, "summary_stats": summ,
                 "bullets": bullets[:3]})
    return {"meta": m, "sections": secs}



# ---------------------------------------------------------------------------
# WASTED SPEND: search terms and ads that spend without bringing leads
# ---------------------------------------------------------------------------
_NONBUYER = re.compile(r"(?<![a-z0-9])(jobs?|careers?|hiring|salary|salaries|employment|internships?|free|diy|"
                       r"how to|how do i|what is|what are|definition|meaning|courses?|training|school|degree|"
                       r"certification|pdf|templates?|wiki|reddit)(?![a-z0-9])", re.I)


def _term_norm(s):
    s = re.sub(r"[\[\]\"+]", " ", str(s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def _waste_badge(g, avg_cpl, big_spend):
    if g["leads"] == 0:
        if _NONBUYER.search(g["term"] or ""):
            return {"label": "Add negative", "tone": "bad"}, "intent"
        if g["conv"] > 0:
            return {"label": "Fix landing page", "tone": "warn"}, "page"
        if g["clicks"] >= 10:
            return {"label": "Add negative", "tone": "bad"}, "noconv"
        return {"label": "Watch", "tone": "neutral"}, "early"
    if avg_cpl and g["spend"] >= big_spend and g["spend"] / g["leads"] >= 2.5 * avg_cpl:
        return {"label": "Watch", "tone": "neutral"}, "costly"
    return None, None


def build_wasted_spend(leads, ad_rows=None, brand_profile=None, customer_name=None, customer_domain="",
                       compare_label=None, form_label=None, prepared_by=None, prepared_for=None, **kw):
    """Search terms and ads with spend but zero (or very few) leads, with the fix for each."""
    name = "Wasted spend finder"
    leads, _prior, m = _setup(leads, kw.get("prior"), brand_profile, customer_name, customer_domain, compare_label,
                              prepared_by, prepared_for)
    if not leads:
        return empty_report(name, m)
    ads = _ads(ad_rows)
    start, end = _window(leads, ads)
    period = period_label(start, end)
    kicker = _kick(name, start, end)
    days = _days(start, end)
    when = _in_period(start, end)
    bits = _bits(customer_domain, form_label, "%d days" % days if days else "")
    spend_p = _spend_by_platform(ads)
    spend = round(sum(spend_p.values()), 2)
    plats = [k for k, v in spend_p.most_common() if v > 0]
    chips = [("UTM Grabber", _pl(len(leads), "lead"))]
    for p in plats:
        chips.append((p, "%s spend" % _money(spend_p[p])))
    m["sources"] = _chips(chips)

    if spend <= 0:
        paid = [e for e in leads if _plat(e)]
        termed = [e for e in paid if lead_term(e)]
        return _short(m, kicker, "Connect your *ad accounts* to find spend that brings no leads.",
                      "Wasted spend needs your *spend*.",
                      ["This report puts every search term and ad with spend next to the leads it brought, and spend "
                       "comes only from your ad accounts.",
                       "Connect Google Ads or Microsoft Ads (and Meta Ads for ads without keywords) and run this again. "
                       "Until then, the keyword report ranks the %s keyword leads UTM Grabber already has." % n(len(termed))],
                      stats=[stat("Leads from ads", n(len(paid))), stat("With a keyword", n(len(termed)))],
                      close_title="Next: connect *Google Ads* and run this again.", bits=bits,
                      notes=["Leads: %s from UTM Grabber, %s." % (_pl(len(leads), "form submission"), period)])

    agg, camp_idx = _ad_agg(ads)
    kw_rows = [r for r in ads if r.get("keyword") and r["spend"] > 0]
    kw_camp_keys = set((r["platform"], norm_key(r["campaign"])) for r in kw_rows)
    search_leads = []
    for e in leads:
        ck = _match_ad(_plat(e), lead_campaign(e), "", camp_idx)[1]
        if lead_term(e) or (ck in kw_camp_keys) or (ck is None and _plat(e) in SEARCH_PLATFORMS):
            search_leads.append(e)
    termed = [e for e in search_leads if lead_term(e)]
    term_cov = share(len(termed), len(search_leads)) if search_leads else 0.0
    kw_mode = bool(kw_rows) and bool(termed)

    # keyword groups
    groups = OrderedDict()
    kw_campaigns = set()
    if kw_mode:
        for r in kw_rows:
            k = (r["platform"], norm_key(r["campaign"]), _term_norm(r["keyword"]))
            g = groups.setdefault(k, {"platform": r["platform"], "campaign": r["campaign"], "term": _safe(r["keyword"], 60),
                                      "spend": 0.0, "clicks": 0, "impr": 0, "conv": 0.0, "leads": 0})
            g["spend"] += r["spend"]
            g["clicks"] += r["clicks"]
            g["impr"] += r["impressions"]
            g["conv"] += r["conversions"]
            kw_campaigns.add(k[:2])
        by_term = defaultdict(list)
        for k in groups:
            by_term[k[2]].append(k)
        for e in termed:
            t = _term_norm(lead_term(e))
            cands = by_term.get(t) or []
            if not cands:
                continue
            p = _plat(e)
            if p:
                same_p = [k for k in cands if k[0] == p]
                cands = same_p or cands
            ck = _match_ad(p, lead_campaign(e), "", camp_idx)[1]
            pick = [k for k in cands if ck and k[:2] == ck]
            k = pick[0] if pick else (cands[0] if len(cands) == 1 else max(cands, key=lambda x: groups[x]["spend"]))
            groups[k]["leads"] += 1
    # ads without keyword rows (Meta, display, or every ad when keywords can't be judged)
    ad_items = []
    for k, g in agg.items():
        if g["spend"] <= 0:
            continue
        if kw_mode and k[:2] in kw_campaigns:
            continue
        ad_items.append(g)
    for e in leads:
        p = _plat(e)
        k, ck = _match_ad(p, lead_campaign(e), lead_content(e), camp_idx)
        if k and k in agg and (not kw_mode or k[:2] not in kw_campaigns):
            agg[k]["leads"] += 1
    ad_names = _ad_labels(ad_items)
    for g, nm in zip(ad_items, ad_names):
        g["name"] = nm

    kws = list(groups.values())
    for g in kws:
        g["spend"] = round(g["spend"], 2)
    kw_spend = round(sum(r["spend"] for r in kw_rows), 2) if kw_mode else 0.0
    kw_leads = sum(g["leads"] for g in kws)
    avg_cpl = safe_div(kw_spend, kw_leads) if kw_leads else None
    big_spend = max(100.0, 0.02 * kw_spend) if kws else 0
    flagged = []
    for g in kws:
        b, why = _waste_badge(g, avg_cpl, big_spend)
        if b:
            g["badge"], g["why"] = b, why
            flagged.append(g)
    zero_kw = [g for g in kws if g["leads"] == 0]
    zero_ads = [g for g in ad_items if g["leads"] == 0]
    ad_spend_all = sum(g["spend"] for g in ad_items)
    ad_leads_all = sum(g["leads"] for g in ad_items)
    ad_avg = safe_div(ad_spend_all, ad_leads_all) if ad_leads_all else None
    costly_ads = [g for g in ad_items if g["leads"] and ad_avg and g["spend"] >= max(100.0, 0.02 * ad_spend_all)
                  and g["spend"] / g["leads"] >= 2.5 * ad_avg]
    wasted_kw = sum(g["spend"] for g in zero_kw)
    wasted_ads = sum(g["spend"] for g in zero_ads)
    wasted = round(wasted_kw + wasted_ads, 2)
    level_word = "ad" if any(g["ad"] for g in ad_items) else "campaign"


    n_paid = sum(1 for e in leads if _plat(e))
    if n_paid < MIN_LEADS:
        return _short(m, kicker, ("Only %s came from your ads: too few to call spend *wasted*." % _pl(n_paid, "lead"))
                      if n_paid else "No lead could be tied to your *ads* yet.",
                      "This check needs at least %d *leads* from ads." % MIN_LEADS,
                      ["Your ads spent %s %s. With so few leads, most terms and ads have none yet, and that says "
                       "more about volume than waste." % (_money(spend), when),
                       "Widen the date range to 60 or 90 days and run this again."] if n_paid else
                      ["Your ads spent %s %s, but no lead carried their utm_source and utm_medium or a click ID, so "
                       "every term and ad would look wasted." % (_money(spend), when),
                       "Tag every ad URL (Google Ads auto-tagging adds the gclid) and run this again."],
                      stats=[stat("Ad spend", _money(spend)), stat("Leads from ads", n(n_paid))],
                      close_title=("Next: widen the *date range* and run this again." if n_paid else
                                   "Next: tag every ad with *UTM parameters* and run this again."), bits=bits,
                      notes=["Ad spend: %s from %s, %s." % (_money(spend), _join_list(plats), period)])

    # ---- title + hero ------------------------------------------------------------------------
    parts = []
    if zero_kw:
        parts.append(_pl(len(zero_kw), "search term"))
    if zero_ads:
        parts.append(_pl(len(zero_ads), level_word))
    if wasted > 0:
        title = "*%s* of ad spend brought no leads." % _money(wasted)
        hero_label = "%s of your %s ad spend %s went to %s with no lead." % (
            pct(share(wasted, spend), 1 if share(wasted, spend) < 10 else 0), _money(spend), when, _join_list(parts))
    elif kw_mode:
        title = "Every search term and %s with spend brought at least one *lead*." % level_word
        hero_label = "Nothing in your %s of ad spend %s went to a term or %s with zero leads." % (_money(spend), when, level_word)
    else:
        title = "Every %s with spend brought at least one *lead*." % level_word
        hero_label = "Nothing in your %s of ad spend %s went to %s with zero leads." % (_money(spend), when,
                                                                                        "an " + level_word if level_word == "ad" else "a " + level_word)
    top_w = max(zero_kw + zero_ads, key=lambda g: g["spend"]) if (zero_kw or zero_ads) else None
    sub = []
    if top_w:
        nm = ("\"%s\"" % top_w["term"]) if top_w in zero_kw else top_w["name"]
        sub.append("%s alone spent %s with no leads." % (_cap(nm), _money(top_w["spend"])))
    if kw_mode and avg_cpl:
        sub.append("Search terms that did bring leads averaged %s per lead." % _money(avg_cpl))
    elif not kw_mode and kw_rows:
        sub.append("No lead carried a keyword, so this report works at the %s level." % level_word)
    secs = [{"type": "title-block", "kicker": kicker, "title": title, "subtitle": " ".join(sub[:2]), "meta_bits": bits},
            {"type": "hero-number", "kicker": "Spend that brought no leads", "value": _money(wasted) if wasted else "$0",
             "label": hero_label}]
    stats = []
    if kw_mode:
        stats += [stat("Search term spend", _money(kw_spend), source=_plat_source([p for p in plats if p in SEARCH_PLATFORMS])),
                  stat("Terms with spend", n(len(kws))),
                  stat("Terms with no leads", n(len(zero_kw)), good="down",
                       note="%s of term spend" % pct(share(wasted_kw, kw_spend)) if kw_spend else None),
                  stat("Cost per keyword lead", _money(avg_cpl) if avg_cpl else "–", good="down",
                       note="%s keyword leads" % n(kw_leads))]
    if ad_items:
        stats.append(stat("%ss with no leads" % _cap(level_word), n(len(zero_ads)), good="down",
                          note="of %s with spend" % _pl(len(ad_items), level_word)))
    if len(stats) < 2:
        stats.insert(0, stat("Ad spend", _money(spend), source=_plat_source(plats)))
    if len(stats) > 4:
        for x in stats:
            x.pop("source", None)
    secs.append({"type": "stat-strip", "stats": stats[:5]})
    if kw_mode and term_cov < 60:
        secs.append({"type": "insight-card", "kicker": "Read this first", "tone": "warn",
                     "title": "Only %s of search leads carried a *keyword*." % pct(term_cov),
                     "body": ["%s of %s leads from search ads arrived without utm_term, so some terms here may have "
                              "brought leads we can't see." % (n(len(search_leads) - len(termed)), n(len(search_leads))),
                              "Add utm_term={keyword} to the tracking template in Google Ads and Microsoft Ads."]})

    # ---- 01 search terms -----------------------------------------------------------------------
    num = 0
    if kw_mode:
        num += 1
        flagged.sort(key=lambda g: (g["leads"] > 0, -g["spend"]))
        rows = []
        for g in flagged[:MAX_ROWS]:
            rows.append({"term": g["term"], "camp": _safe(g["campaign"], 32), "spend": _money(g["spend"]),
                         "clicks": n(g["clicks"]), "leads": n(g["leads"]),
                         "cpl": _money(g["spend"] / g["leads"]) if g["leads"] else "–", "action": g["badge"]})
        secs.append({"type": "section-header", "number": "%02d" % num, "kicker": "Search terms",
                     "title": "The search terms that *spent* without leads.",
                     "dek": "Every term with spend and no lead, then terms whose leads cost %s times your average or more." % "2.5"})
        if rows:
            secs.append({"type": "ranked-list", "title": "*Search terms* to fix",
                         "columns": [{"key": "term", "label": "Search term", "type": "source"},
                                     {"key": "camp", "label": "Campaign", "type": "text"},
                                     {"key": "spend", "label": "Spend", "type": "money", "align": "right"},
                                     {"key": "clicks", "label": "Clicks", "type": "mono-number", "align": "right"},
                                     {"key": "leads", "label": "Leads", "type": "mono-number", "align": "right"},
                                     {"key": "cpl", "label": "Cost per lead", "type": "money", "align": "right"},
                                     {"key": "action", "label": "Action", "type": "badge"}],
                         "rows": rows,
                         "caption": "Add negative: no leads and no platform conversions, or words like jobs, free or "
                                    "how to. Fix landing page: the platform counted conversions but no form came "
                                    "through. Watch: too few clicks to judge, or leads at %s+ each." % (
                                        _money(2.5 * avg_cpl) if avg_cpl else "a high cost")})
        else:
            secs.append({"type": "insight-card", "kicker": "Search terms", "tone": "good",
                         "title": "Every search term with spend brought *leads*.",
                         "body": ["%s terms spent %s and each brought at least one lead at a reasonable cost." % (
                             n(len(kws)), _money(kw_spend))]})

    # ---- 02 by campaign -----------------------------------------------------------------------
    by_camp = Counter()
    camp_spend = Counter()
    for g in kws:
        camp_spend[_safe(g["campaign"], 36)] += g["spend"]
    for g in ad_items:
        camp_spend[_safe(g["campaign"], 36)] += g["spend"]
    for g in zero_kw + zero_ads:
        by_camp[_safe(g["campaign"], 36)] += g["spend"]
    if by_camp:
        num += 1
        top = by_camp.most_common(8)
        tc, tv = top[0]
        secs.append({"type": "section-header", "number": "%02d" % num, "kicker": "By campaign",
                     "title": "Where the *waste* sits.", "dek": "Spend on terms and %ss with no leads, by campaign." % level_word})
        tb = ["That is %s of the campaign's %s." % (pct(share(tv, camp_spend[tc])), _money(camp_spend[tc]))]
        cnt = [g for g in zero_kw + zero_ads if _safe(g["campaign"], 36) == tc]
        tb.append("It comes from %s." % _join_list([("\"%s\"" % g["term"]) if g in zero_kw else g["name"]
                                                       for g in sorted(cnt, key=lambda x: -x["spend"])[:3]]))
        secs.append({"type": "chart",
                     "chart": {"type": "bar-horizontal", "labels": [c for c, _ in top], "values": [round(v, 2) for _, v in top],
                               "unit": "$", "highlight": 0, "show_share": False,
                               "notes": ["%s of its spend" % pct(share(v, camp_spend[c])) for c, v in top]},
                     "chart_title": "Spend with no leads, by *campaign*",
                     "caption": "Each bar is spend on terms and %ss in that campaign that brought no lead." % level_word})
        secs.append({"type": "insight-card", "kicker": "The biggest leak", "tone": "warn",
                     "title": "*%s* wasted %s." % (tc, _money(tv)), "body": tb})
    if zero_ads or costly_ads:
        rows = []
        for g in sorted(zero_ads, key=lambda x: -x["spend"])[:8] + sorted(costly_ads, key=lambda x: -x["spend"])[:4]:
            rows.append({"name": g["name"], "platform": g["platform"], "camp": _safe(g["campaign"], 30),
                         "spend": _money(g["spend"]), "clicks": n(g["clicks"]), "leads": n(g["leads"]),
                         "cpl": _money(g["spend"] / g["leads"]) if g["leads"] else "–",
                         "action": {"label": "Pause", "tone": "bad"} if not g["leads"] else {"label": "Watch", "tone": "neutral"}})
        secs.append({"type": "ranked-list",
                     "title": ("%ss with spend and no *leads*" % _cap(level_word)) if zero_ads else
                     ("%ss with very costly *leads*" % _cap(level_word)),
                     "columns": [{"key": "name", "label": _cap(level_word), "type": "name"},
                                 {"key": "platform", "label": "Platform", "type": "platform"},
                                 {"key": "spend", "label": "Spend", "type": "money", "align": "right"},
                                 {"key": "clicks", "label": "Clicks", "type": "mono-number", "align": "right"},
                                 {"key": "leads", "label": "Leads", "type": "mono-number", "align": "right"},
                                 {"key": "cpl", "label": "Cost per lead", "type": "money", "align": "right"},
                                 {"key": "action", "label": "Action", "type": "badge"}],
                     "rows": rows[:MAX_ROWS],
                     "caption": "Matched by utm_campaign and utm_content. Check a paused-looking %s's final URL first: "
                                "a missing utm_content looks the same as no leads." % level_word})

    # ---- next steps ------------------------------------------------------------------------------
    recs = []
    close = None
    negs = [g for g in flagged if g["badge"]["label"] == "Add negative"]
    if negs:
        nsp = sum(g["spend"] for g in negs)
        recs.append({"label": "This week", "title": "Add %s *negative %s*" % (n(len(negs)), "keyword" if len(negs) == 1 else "keywords"),
                     "body": "%s spent %s with no leads. Add %s as %s at the campaign level." % (
                         _cap(_join_list(["\"%s\"" % g["term"] for g in negs[:3]])) + (" and %d more" % (len(negs) - 3) if len(negs) > 3 else ""),
                         _money(nsp), "them" if len(negs) > 1 else "it", "phrase-match negatives" if len(negs) > 1 else "a phrase-match negative"),
                     "impact": "High", "effort": "Low", "metric": "%s back to work" % _money(nsp)})
        close = "Next: add %s *negative %s*. %s spent %s with no leads." % (
            n(len(negs)), "keyword" if len(negs) == 1 else "keywords", "It" if len(negs) == 1 else "They", _money(nsp))
    pages = [g for g in flagged if g["badge"]["label"] == "Fix landing page"]
    if pages:
        g = max(pages, key=lambda x: x["spend"])
        recs.append({"label": "This week", "title": "Fix the landing page for *\"%s\"*" % _safe(g["term"], 40),
                     "body": "It spent %s and %s counted %s conversions, but no form lead came through. Check the "
                             "page's form and that the ad URL keeps its UTM tags." % (
                                 _money(g["spend"]), g["platform"], n(round(g["conv"]))),
                     "impact": "High", "effort": "Low"})
        close = close or "Next: fix the landing page for *\"%s\"*. It spent %s with no form leads." % (
            _safe(g["term"], 40), _money(g["spend"]))
    if zero_ads:
        z = max(zero_ads, key=lambda x: x["spend"])
        recs.append({"label": "This week", "title": "Pause *%s*" % _safe(z["name"], 40),
                     "body": "It spent %s %s and no lead carried its tags. Check its final URL first: a missing "
                             "utm_content looks the same as no leads." % (_money(z["spend"]), when),
                     "impact": "High", "effort": "Low", "metric": "%s back to work" % _money(z["spend"])})
        close = close or "Next: pause *%s*. It spent %s with no leads." % (_safe(z["name"], 40), _money(z["spend"]))
    watch = [g for g in flagged if g["badge"]["label"] == "Watch" and g["leads"]]
    if watch:
        g = max(watch, key=lambda x: x["spend"])
        recs.append({"label": "This month", "title": "Lower the bid on *\"%s\"*" % _safe(g["term"], 40),
                     "body": "%s %s, %.1f times your average keyword lead (%s)." % (
                         ("Its %s cost" % _pl(g["leads"], "lead")) if g["leads"] > 1 else "Its only lead cost",
                         ("%s each" % _money(g["spend"] / g["leads"])) if g["leads"] > 1 else _money(g["spend"]),
                         (g["spend"] / g["leads"]) / avg_cpl, _money(avg_cpl)),
                     "impact": "Medium", "effort": "Low"})
    if kw_mode and term_cov < 90:
        recs.append({"label": "This month", "title": "Pass every keyword in *utm_term*",
                     "body": "%s of %s search leads arrived without one, so their search term is unknown. Add "
                             "utm_term={keyword} to your tracking template." % (
                                 n(len(search_leads) - len(termed)), n(len(search_leads))),
                     "impact": "Medium", "effort": "Low"})
    elif not kw_mode and kw_rows:
        recs.append({"label": "This week", "title": "Pass the keyword in *utm_term*",
                     "body": "Your Google Ads data has keywords, but no lead carried one, so search terms can't be "
                             "judged. Add utm_term={keyword} to the tracking template.",
                     "impact": "High", "effort": "Low"})
    if len(recs) < 2:
        pool = [g for g in kws if g["leads"] >= 5] or [g for g in ad_items if g["leads"] >= 5]
        if pool:
            c = min(pool, key=lambda g: g["spend"] / g["leads"])
            nm = ("\"%s\"" % c["term"]) if c in kws else c["name"]
            recs.append({"label": "This month", "title": "Keep *%s* funded" % _safe(nm, 40),
                         "body": "It brought %s at %s each, the lowest cost of any %s with 5 or more leads." % (
                             _pl(c["leads"], "lead"), _money(c["spend"] / c["leads"]),
                             "search term" if c in kws else level_word),
                         "impact": "Medium", "effort": "Low"})
    if len(recs) < 2:
        recs.append({"label": "Ongoing", "title": "Review search terms *weekly*" if kw_rows else "Rerun this check *monthly*",
                     "body": "New search terms appear every week. A short weekly review keeps waste from building up."
                     if kw_rows else "A monthly check catches an ad that stops bringing leads before it costs a quarter.",
                     "impact": "Low", "effort": "Low"})
    if not close:
        close = ("Next: review your search terms *weekly* to keep waste at zero." if kw_rows else
                 "Next: rerun this check *monthly* to keep waste at zero.")
    num += 1
    secs.append({"type": "section-header", "number": "%02d" % num, "kicker": "Next steps", "title": "What to do *next*."})
    secs.append({"type": "recommendations", "items": _by_impact(recs)[:4]})

    notes = ["Ad spend: %s from %s, %s." % (_money(spend), _join_list(plats), _range_text(_date(r.get("date")) for r in ads))]
    if kw_mode:
        notes.append("Search terms: %s with spend. Leads are matched by utm_term within the same campaign (case, quotes "
                     "and match-type symbols ignored); %s of %s search leads (%s) carried a keyword." % (
                         n(len(kws)), n(len(termed)), n(len(search_leads)), pct(term_cov)))
        notes.append("Add negative: no leads and no platform conversions after 10 or more clicks, or a word that signals "
                     "no intent to buy (jobs, free, diy, how to, course and similar).")
    if ad_items:
        notes.append("%ss without keywords (%s) are matched to leads by utm_campaign, then utm_content." % (
            _cap(level_word), _join_list(sorted(set(g["platform"] for g in ad_items)))))
    notes.append("Wasted spend counts only terms and %ss with zero leads; costly terms are flagged Watch but not "
                 "counted." % level_word)
    secs.append({"type": "notes", "items": notes})
    summ = [{"value": _money(wasted), "label": "Spend with no leads"},
            {"value": pct(share(wasted, spend), 1 if share(wasted, spend) < 10 else 0), "label": "Share of ad spend"}]
    if kw_mode:
        summ.append({"value": n(len(zero_kw)), "label": "Terms with no leads"})
        if avg_cpl:
            summ.append({"value": _money(avg_cpl), "label": "Cost per keyword lead"})
    elif ad_items:
        summ.append({"value": n(len(zero_ads)), "label": "%ss with no leads" % _cap(level_word)})
    bullets = []
    for g in sorted(zero_kw, key=lambda x: -x["spend"])[:2]:
        bullets.append("\"%s\": %s, %s clicks, no leads." % (g["term"], _money(g["spend"]), n(g["clicks"])))
    if zero_ads:
        bullets.append("%s spent %s with no leads." % (_pl(len(zero_ads), level_word), _money(wasted_ads)))
    secs.append({"type": "closing", "kicker": "The waste in one line", "title": close, "summary_stats": summ[:4],
                 "bullets": bullets[:3]})
    return {"meta": m, "sections": secs}


REGISTRY = {
    "full-funnel": build_full_funnel, "funnel": build_full_funnel, "full-funnel-performance": build_full_funnel,
    "true-roas": build_true_roas, "roas": build_true_roas, "ad-roi": build_true_roas, "which-ads": build_true_roas,
    "spend-to-revenue": build_true_roas,
    "conversion-truth": build_conversion_truth, "platform-vs-reality": build_conversion_truth,
    "over-reporting": build_conversion_truth, "reconciliation": build_conversion_truth,
    "traffic-to-lead": build_traffic_to_lead, "traffic-leaks": build_traffic_to_lead,
    "visits-no-leads": build_traffic_to_lead, "conversion-rate": build_traffic_to_lead,
    "pipeline": build_pipeline, "close-rate": build_pipeline, "crm-pipeline": build_pipeline,
    "deals-by-source": build_pipeline, "pipeline-by-source": build_pipeline,
    "wasted-spend": build_wasted_spend, "wasted": build_wasted_spend, "zero-lead-spend": build_wasted_spend,
    "negative-keywords": build_wasted_spend,
}
