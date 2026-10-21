"""
Cross-platform data: normalize what other connectors return, then join it to
UTM Grabber leads.

UTM Grabber knows where every lead came from (source, medium, campaign, ad,
keyword, click ID, first touch, landing page). Other connectors the customer
has in the same AI app know the rest: Google Ads / Meta Ads / Microsoft Ads /
LinkedIn Ads know spend; Google Analytics 4 knows visits; HubSpot / Salesforce /
Pipedrive know deals; WooCommerce / Stripe know revenue. This module turns any
of those payloads into a handful of simple row shapes, and joins them to leads.

Normalized shapes (every key optional unless marked *):

    AdRow       {platform*, campaign*, ad_group, ad, keyword, date, spend*,
                 impressions, clicks, conversions, conversion_value}
    VisitRow    {source*, medium*, campaign, landing_page, date, sessions*,
                 engaged_sessions, users, key_events}
    DealRow     {email*, stage* (won|lost|open), amount, created, closed,
                 deal_id, pipeline}
    OrderRow    {order_id, email, date*, total*, status, source, medium,
                 campaign, first_source, first_medium, first_campaign,
                 traffic_source, first_traffic_source, gclid, fbclid, products}

The normalizers accept the field names the common connectors use (GAQL
`metrics.cost_micros`, Meta `spend` / `amount_spent`, GA4 `sessionSource`,
HubSpot `dealstage` / `closedate`, ...). Unknown keys are ignored.

Joins are deliberately simple and explainable, because every number in a report
must trace back to a row:
    ads    <-> leads    utm_campaign == campaign (normalized), then utm_content == ad
    visits <-> leads    (utm_source, utm_medium) == (source, medium) (normalized)
    deals  <-> leads    lowercase email
    orders <-> leads    the order's own UTM fields (WooCommerce orders carry them)
"""
import re
from collections import defaultdict

from helpers import classify_traffic_source, get_field

# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------
def norm_key(s):
    """'Brand Search - US' -> 'brand_search_us'. Used for campaign/ad matching."""
    s = str(s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def _num(v, default=0.0):
    if v is None or v == "":
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").replace("$", "").replace("€", "").replace("£", "").strip()
    try:
        return float(s)
    except ValueError:
        return default


def _pick(row, *keys, default=None):
    """First present key; supports dotted paths like 'metrics.cost_micros'."""
    for k in keys:
        cur = row
        ok = True
        for part in k.split("."):
            if isinstance(cur, dict) and part in cur and cur[part] not in (None, ""):
                cur = cur[part]
            else:
                ok = False
                break
        if ok:
            return cur
    return default


def _date(v):
    if not v:
        return None
    s = str(v)
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    if re.match(r"^\d{13}$", s):  # HubSpot epoch millis
        import datetime as _dt
        return _dt.datetime.utcfromtimestamp(int(s) / 1000).strftime("%Y-%m-%d")
    return s[:10]


# ---------------------------------------------------------------------------
# Normalizers
# ---------------------------------------------------------------------------
def normalize_ad_rows(rows, platform=None):
    """Google Ads (GAQL), Meta Ads Insights, Microsoft Ads, LinkedIn Ads -> AdRow."""
    out = []
    for r in rows or []:
        plat = platform or _pick(r, "platform", "publisher", default="Ads")
        spend = _pick(r, "spend", "cost", "amount_spent", "metrics.cost", "Cost")
        if spend is None:
            micros = _pick(r, "metrics.cost_micros", "cost_micros")
            spend = _num(micros) / 1e6 if micros is not None else 0.0
        out.append({
            "platform": plat,
            "campaign": str(_pick(r, "campaign", "campaign_name", "campaign.name", "Campaign", default="") or ""),
            "ad_group": str(_pick(r, "ad_group", "adset_name", "ad_group.name", "adgroup", default="") or ""),
            "ad": str(_pick(r, "ad", "ad_name", "ad.name", "ad_group_ad.ad.name", "creative", default="") or ""),
            "keyword": str(_pick(r, "keyword", "search_term", "ad_group_criterion.keyword.text",
                                 "search_term_view.search_term", default="") or ""),
            "date": _date(_pick(r, "date", "date_start", "segments.date", "day")),
            "spend": round(_num(spend), 2),
            "impressions": int(_num(_pick(r, "impressions", "metrics.impressions"))),
            "clicks": int(_num(_pick(r, "clicks", "metrics.clicks", "inline_link_clicks"))),
            "conversions": _num(_pick(r, "conversions", "metrics.conversions", "results", "leads")),
            "conversion_value": _num(_pick(r, "conversion_value", "metrics.conversions_value", "purchase_value")),
        })
    return out


def normalize_visit_rows(rows):
    """GA4 Data API rows -> VisitRow."""
    out = []
    for r in rows or []:
        src = _pick(r, "source", "sessionSource", "session_source", "firstUserSource", default="(direct)")
        med = _pick(r, "medium", "sessionMedium", "session_medium", "firstUserMedium", default="(none)")
        sm = _pick(r, "sessionSourceMedium", "source_medium")
        if sm and " / " in str(sm):
            src, med = [x.strip() for x in str(sm).split(" / ", 1)]
        out.append({
            "source": str(src).strip().lower(),
            "medium": str(med).strip().lower(),
            "campaign": str(_pick(r, "campaign", "sessionCampaignName", default="") or ""),
            "landing_page": str(_pick(r, "landing_page", "landingPage", "landingPagePlusQueryString", default="") or "").split("?")[0],
            "date": _date(_pick(r, "date")),
            "sessions": int(_num(_pick(r, "sessions"))),
            "engaged_sessions": int(_num(_pick(r, "engaged_sessions", "engagedSessions"))),
            "users": int(_num(_pick(r, "users", "totalUsers", "activeUsers"))),
            "key_events": _num(_pick(r, "key_events", "keyEvents", "conversions")),
        })
    return out


_WON = {"won", "closedwon", "closed_won", "closed won", "win"}
_LOST = {"lost", "closedlost", "closed_lost", "closed lost"}


def normalize_deal_rows(rows):
    """HubSpot / Salesforce / Pipedrive deals -> DealRow (stage is won|lost|open)."""
    out = []
    for r in rows or []:
        stage_raw = str(_pick(r, "stage", "dealstage", "StageName", "status", "properties.dealstage", default="open")).lower()
        if stage_raw in _WON or "won" in stage_raw:
            stage = "won"
        elif stage_raw in _LOST or "lost" in stage_raw:
            stage = "lost"
        else:
            stage = "open"
        email = _pick(r, "email", "contact_email", "Email", "person_email", "properties.email", default="")
        out.append({
            "deal_id": str(_pick(r, "deal_id", "id", "Id", default="")),
            "email": str(email or "").strip().lower(),
            "stage": stage,
            "amount": _num(_pick(r, "amount", "Amount", "value", "properties.amount")),
            "created": _date(_pick(r, "created", "createdate", "CreatedDate", "add_time", "properties.createdate")),
            "closed": _date(_pick(r, "closed", "closedate", "CloseDate", "won_time", "properties.closedate")),
            "pipeline": str(_pick(r, "pipeline", default="") or ""),
        })
    return out


def normalize_orders(entries):
    """WooCommerce orders as returned by the UTM Grabber MCP (or Stripe-like rows)."""
    out = []
    for e in entries or []:
        total = _pick(e, "total", "Order Total", "order_total", "amount", "Total")
        if total is None:
            continue
        out.append({
            "order_id": str(_pick(e, "order_id", "Order ID", "Entry ID", "id", default="")),
            "email": str(_pick(e, "email", "Billing Email", "Email", "Work Email", default="") or "").lower(),
            "date": _date(_pick(e, "date", "Order Date", "Date Created", "created")),
            "total": _num(total),
            "status": str(_pick(e, "status", "Order Status", default="completed")).lower(),
            "source": get_field(e, "utm_source (HandL)", "utm_source").lower(),
            "medium": get_field(e, "utm_medium (HandL)", "utm_medium").lower(),
            "campaign": get_field(e, "utm_campaign (HandL)", "utm_campaign"),
            "content": get_field(e, "utm_content (HandL)", "utm_content"),
            "first_source": get_field(e, "utm_source (first touch, HandL)", "first_utm_source").lower(),
            "first_medium": get_field(e, "utm_medium (first touch, HandL)", "first_utm_medium").lower(),
            "first_campaign": get_field(e, "utm_campaign (first touch, HandL)", "first_utm_campaign"),
            "traffic_source": classify_traffic_source(e),
            "first_traffic_source": get_field(e, "traffic_source (first touch, HandL)", "first_traffic_source")
            or classify_traffic_source(e),
            "gclid": get_field(e, "gclid (HandL)", "gclid"),
            "fbclid": get_field(e, "fbclid (HandL)", "fbclid"),
            "products": _pick(e, "products", "Products", "Line Items", default=""),
        })
    return out


# ---------------------------------------------------------------------------
# Lead accessors (UTM Grabber entries)
# ---------------------------------------------------------------------------
def lead_email(e):
    return get_field(e, "Work Email", "Email Address", "Email", "email", "Your Email").lower()


def lead_campaign(e):
    return get_field(e, "utm_campaign (HandL)", "utm_campaign")


def lead_content(e):
    return get_field(e, "utm_content (HandL)", "utm_content")


def lead_term(e):
    return get_field(e, "utm_term (HandL)", "utm_term")


def lead_source_medium(e):
    return (get_field(e, "utm_source (HandL)", "utm_source").lower(),
            get_field(e, "utm_medium (HandL)", "utm_medium").lower())


def lead_platform(e):
    """Best guess of the ad platform behind a lead, from source and click IDs."""
    src, med = lead_source_medium(e)
    if get_field(e, "gclid (HandL)", "gclid", "wbraid (HandL)", "gbraid (HandL)") or (src == "google" and med in ("cpc", "ppc", "paid", "paid_search")):
        return "Google Ads"
    if get_field(e, "fbclid (HandL)", "fbclid") or src in ("facebook", "instagram", "meta", "fb", "ig"):
        return "Meta Ads" if med not in ("organic", "social", "organic_social") else "Organic social"
    if get_field(e, "msclkid (HandL)", "msclkid") or (src == "bing" and med in ("cpc", "ppc")):
        return "Microsoft Ads"
    if src == "linkedin" and med in ("cpc", "paid", "paid_social", "paidsocial"):
        return "LinkedIn Ads"
    if src == "tiktok":
        return "TikTok Ads" if med in ("cpc", "ppc", "paid", "paid_social", "paidsocial", "paid-social") else "Organic social"
    return None


# ---------------------------------------------------------------------------
# Joins
# ---------------------------------------------------------------------------
def join_ads_to_leads(ad_rows, leads, level="campaign"):
    """Group spend and leads by (platform, campaign) or (platform, campaign, ad).

    Returns a list of dicts: {platform, campaign, ad, spend, clicks, impressions,
    platform_conversions, leads, lead_emails, cpl}. Leads whose campaign has no
    spend row are reported under their platform with spend 0 so nothing is hidden."""
    groups = {}

    def key_for(platform, campaign, ad):
        k = (platform, norm_key(campaign))
        if level == "ad":
            k = k + (norm_key(ad),)
        return k

    for r in ad_rows or []:
        k = key_for(r["platform"], r["campaign"], r.get("ad", ""))
        g = groups.setdefault(k, {"platform": r["platform"], "campaign": r["campaign"], "ad": r.get("ad", ""),
                                  "spend": 0.0, "clicks": 0, "impressions": 0, "platform_conversions": 0.0,
                                  "leads": 0, "lead_emails": []})
        g["spend"] += r.get("spend", 0.0)
        g["clicks"] += r.get("clicks", 0)
        g["impressions"] += r.get("impressions", 0)
        g["platform_conversions"] += r.get("conversions", 0.0)
    by_campaign = defaultdict(list)
    for k in groups:
        by_campaign[k[1]].append(k)
    for e in leads or []:
        camp = lead_campaign(e)
        plat = lead_platform(e)
        if not camp and not plat:
            continue
        ck = norm_key(camp)
        target = None
        if level == "ad":
            ak = norm_key(lead_content(e))
            cands = sorted(by_campaign.get(ck, []), key=lambda k: 0 if (plat and k[0] == plat) else 1)
            for k in cands:
                if k[2] == ak:
                    target = k
                    break
        if target is None:
            cands = by_campaign.get(ck, [])
            same = [k for k in cands if plat and k[0] == plat]
            if same:
                target = same[0] if level != "ad" else None
            elif cands:
                target = cands[0] if level != "ad" else None
        if target is None:
            if not plat:
                continue
            target = (plat, ck) + ((norm_key(lead_content(e)),) if level == "ad" else ())
            if target not in groups:
                groups[target] = {"platform": plat, "campaign": camp or "(no campaign tag)",
                                  "ad": lead_content(e) if level == "ad" else "", "spend": 0.0, "clicks": 0,
                                  "impressions": 0, "platform_conversions": 0.0, "leads": 0, "lead_emails": []}
        groups[target]["leads"] += 1
        em = lead_email(e)
        if em:
            groups[target]["lead_emails"].append(em)
    out = list(groups.values())
    for g in out:
        g["spend"] = round(g["spend"], 2)
        g["cpl"] = round(g["spend"] / g["leads"], 2) if g["leads"] and g["spend"] else None
    out.sort(key=lambda g: (-g["spend"], -g["leads"]))
    return out


def join_visits_to_leads(visit_rows, leads, by="source_medium"):
    """Sessions vs leads per (source, medium) or per landing page path."""
    sess = defaultdict(lambda: {"sessions": 0, "engaged_sessions": 0, "leads": 0})
    for v in visit_rows or []:
        if by == "landing_page":
            k = _path(v.get("landing_page"))
        else:
            k = (v["source"], v["medium"])
        sess[k]["sessions"] += v.get("sessions", 0)
        sess[k]["engaged_sessions"] += v.get("engaged_sessions", 0)
    for e in leads or []:
        if by == "landing_page":
            k = _path(get_field(e, "landing_page (first touch, HandL)", "handl_landing_page (HandL)", "Source URL"))
        else:
            src, med = lead_source_medium(e)
            if not src and not med:
                k = ("(direct)", "(none)")
            else:
                k = (src or "(not set)", med or "(not set)")
        sess[k]["leads"] += 1
    out = []
    for k, v in sess.items():
        rate = 100.0 * v["leads"] / v["sessions"] if v["sessions"] else None
        out.append(dict(key=k, **v, lead_rate=rate))
    out.sort(key=lambda r: -r["sessions"])
    return out


def _path(url):
    u = str(url or "")
    u = re.sub(r"^https?://[^/]+", "", u).split("?")[0].split("#")[0]
    if not u:
        return "/"
    return u if u == "/" else u.rstrip("/")


def join_deals_to_leads(deal_rows, leads):
    """Attach each deal to its lead by email. Returns (matched, unmatched_deals).

    matched = [{lead, deal, first_touch, last_touch}] where touches are the
    traffic-source labels (Paid / Organic / Social / Referral / Direct)."""
    by_email = {}
    for e in leads or []:
        em = lead_email(e)
        if em and em not in by_email:
            by_email[em] = e
    matched, unmatched = [], []
    for d in deal_rows or []:
        e = by_email.get(d["email"])
        if not e:
            unmatched.append(d)
            continue
        matched.append({"lead": e, "deal": d, "first_touch": first_touch_channel(e),
                        "last_touch": classify_traffic_source(e)})
    return matched, unmatched


def first_touch_channel(e):
    ft = get_field(e, "traffic_source (first touch, HandL)", "first_traffic_source (HandL)", "first_traffic_source")
    if ft:
        return ft.capitalize() if ft.lower() in ("paid", "organic", "social", "referral", "direct") else ft
    src = get_field(e, "utm_source (first touch, HandL)", "first_utm_source (HandL)", "first_utm_source")
    med = get_field(e, "utm_medium (first touch, HandL)", "first_utm_medium (HandL)", "first_utm_medium")
    if src or med:
        return classify_traffic_source({"utm_source": src, "utm_medium": med})
    return classify_traffic_source(e)


def sources_meta(**counts):
    """Build meta.sources chips: sources_meta(utmg='1,186 leads', google_ads='$18,420 spend')."""
    names = {"utmg": "UTM Grabber", "google_ads": "Google Ads", "meta_ads": "Meta Ads",
             "microsoft_ads": "Microsoft Ads", "linkedin_ads": "LinkedIn Ads", "ga4": "Google Analytics 4",
             "hubspot": "HubSpot", "salesforce": "Salesforce", "pipedrive": "Pipedrive",
             "woocommerce": "WooCommerce", "stripe": "Stripe", "search_console": "Search Console"}
    return [{"name": names.get(k, k), "detail": v} for k, v in counts.items() if v]
