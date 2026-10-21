"""
Demo mode (v2): build any report from the bundled sample businesses, in any theme
and format, with no site connection.

    from demo_v2 import build_demo, demo_summary, REPORTS
    build_demo("monthly", "/mnt/user-data/outputs/sample-monthly.html", theme="studio")
    build_demo("full-funnel", ["out/ff.html", "out/ff.pdf", "out/ff.pptx"], theme="boardroom")

    python scripts/demo_v2.py monthly out.html [--theme ledger]

The samples are fictional (Northwind Dental: leads + Google/Meta Ads + analytics +
HubSpot deals; Harbor Linen Co.: a WooCommerce store). Every report built here says so
in its footer source line.
"""
import datetime as _dt
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# canonical keys, in catalog order
REPORTS = [
    "monthly", "weekly", "daily-pulse", "qbr", "leaderboard", "campaign-deep-dive", "paid-vs-organic",
    "anomaly", "forecast", "side-by-side", "agency-rollup",
    "audit", "lead-scorer", "lead-profile", "form-performance", "landing-page", "source-to-crm", "lead-timing",
    "ad-creative", "keyword", "budget-simulator", "revenue", "ai-referrals", "journey",
    "full-funnel", "true-roas", "conversion-truth", "traffic-to-lead", "pipeline", "wasted-spend",
]

TITLES = {
    "monthly": "Monthly performance review", "weekly": "Weekly executive summary", "daily-pulse": "Daily pulse",
    "qbr": "Quarterly business review", "leaderboard": "Campaign leaderboard",
    "campaign-deep-dive": "Campaign deep dive", "paid-vs-organic": "Paid vs organic", "anomaly": "Anomaly detector",
    "forecast": "Lead forecast", "side-by-side": "Side-by-side comparison", "agency-rollup": "Agency client rollup",
    "audit": "UTM hygiene audit", "lead-scorer": "Lead quality scorer", "lead-profile": "Lead profile",
    "form-performance": "Form performance", "landing-page": "Landing page performance",
    "source-to-crm": "Sources by CRM", "lead-timing": "When leads arrive", "ad-creative": "Ad creative performance",
    "keyword": "Keyword performance", "budget-simulator": "Budget simulator", "revenue": "Revenue by source",
    "ai-referrals": "Leads from AI assistants", "journey": "Customer journeys", "full-funnel": "Full-funnel performance",
    "true-roas": "Which ads brought customers", "conversion-truth": "Ad platforms vs reality",
    "traffic-to-lead": "Traffic that never converts", "pipeline": "Close rate by first touch",
    "wasted-spend": "Wasted spend finder",
}


def _dt_of(e):
    from recipes_v2.common import entry_dt
    return entry_dt(e)


def _between(entries, start, end):
    out = []
    for e in entries or []:
        d = _dt_of(e)
        if d and start <= d.date() <= end:
            out.append(e)
    return out


def _rows_between(rows, start, end, key="date"):
    out = []
    for r in rows or []:
        v = r.get(key) or r.get("created")
        try:
            d = _dt.datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        if start <= d <= end:
            out.append(r)
    return out


def _common(ds, theme=None):
    p = ds.get("period") or {}
    return dict(brand_profile=dict(ds["brand"], theme=theme) if theme else ds["brand"],
                customer_name=ds["brand"].get("company_name"), customer_domain=ds.get("domain", ""),
                form_label=ds.get("form_label"), compare_label=p.get("compare_label"))


def demo_summary(report, theme=None, dataset=None):
    """Build the summary dict for a report from the sample data."""
    from recipes_v2 import get_recipe
    from demo_data_v2 import get_dataset
    from connectors import lead_platform, join_deals_to_leads, lead_email
    key = report
    fn = get_recipe(key)
    ds_name = dataset or ("harbor" if key in ("revenue",) else "northwind")
    ds = get_dataset(ds_name)
    c = _common(ds, theme)
    leads, prior = ds["leads"], ds.get("leads_prior") or []
    hist = ds.get("leads_history") or (prior + leads)
    p = ds.get("period") or {}
    end = p.get("end") or max(_dt_of(e) for e in leads).date()
    if key == "weekly":
        cur = _between(hist, end - _dt.timedelta(days=6), end)
        pri = _between(hist, end - _dt.timedelta(days=13), end - _dt.timedelta(days=7))
        c["compare_label"] = "last week"
        return fn(cur, pri, **c)
    if key == "daily-pulse":
        c["compare_label"] = None
        return fn(_between(hist, end - _dt.timedelta(days=29), end), as_of=end, ad_rows=ds.get("ad_rows"), **c)
    if key == "qbr":
        q3s, q3e = _dt.date(end.year, 7, 1), _dt.date(end.year, 9, 30)
        q2s, q2e = _dt.date(end.year, 4, 1), _dt.date(end.year, 6, 30)
        c["compare_label"] = "Q2"
        ads_h = ds.get("ad_rows_history") or ds.get("ad_rows")
        deals_h = ds.get("deal_rows_history") or ds.get("deal_rows")
        return fn(_between(hist, q3s, q3e), _between(hist, q2s, q2e),
                  ad_rows=_rows_between(ads_h, q3s, q3e), ad_rows_prior=_rows_between(ads_h, q2s, q2e),
                  deal_rows=_rows_between(deals_h, q3s, q3e, "created"),
                  deal_rows_prior=_rows_between(deals_h, q2s, q2e, "created"), **c)
    if key == "campaign-deep-dive":
        from collections import Counter
        from connectors import lead_campaign
        top = Counter(lead_campaign(e).lower() for e in leads if lead_campaign(e)).most_common(1)[0][0]
        return fn(leads, top, prior=prior, **c)
    if key == "side-by-side":
        a = [e for e in leads if lead_platform(e) == "Google Ads"]
        b = [e for e in leads if lead_platform(e) == "Meta Ads"]
        return fn(a, "Google Ads", b, "Meta Ads", **c)
    if key == "agency-rollup":
        items = [{"brand_name": x["name"], "entries": x["leads"], "entries_prior": x.get("leads_prior"),
                  "domain": x.get("domain")} for x in ds.get("clients") or []]
        c["prepared_by"] = "Brightline Agency"
        return fn(items, **{k: v for k, v in c.items() if k != "form_label"})
    if key == "anomaly":
        return fn(leads, prior, **c)
    if key == "forecast":
        return fn(_between(hist, end - _dt.timedelta(days=89), end), **c)
    if key == "budget-simulator":
        return fn(leads, {"shift_from": "facebook", "shift_to": "google", "pct": 20}, ad_rows=ds.get("ad_rows"), **c)
    if key == "lead-profile":
        matched, _ = join_deals_to_leads([d for d in ds.get("deal_rows") or [] if d.get("stage") == "won"], leads)
        pick = None
        for m in matched:
            if m["first_touch"] != m["last_touch"]:
                pick = m
                break
        email = (pick or (matched[0] if matched else None) or {}).get("lead")
        email = lead_email(email) if email else lead_email(leads[0])
        return fn(hist, email, deal_rows=ds.get("deal_rows"), **c)
    if key == "source-to-crm":
        from demo_data import get_demo_current, get_demo_prior
        from recipes_v2.common import DEFAULT_BRAND
        b = dict(DEFAULT_BRAND, theme=theme) if theme else DEFAULT_BRAND
        return fn(get_demo_current(), get_demo_prior(), brand_profile=b, customer_domain="demo1.utmgrabber.com",
                  form_label="Gravity Forms")
    if key == "form-performance":
        return fn(leads, prior, forms=ds.get("forms"), **c)
    if key in ("ad-creative", "keyword"):
        return fn(leads, prior, ad_rows=ds.get("ad_rows"), **c)
    if key == "revenue":
        return fn(ds.get("orders"), ds.get("orders_prior"), ad_rows=ds.get("ad_rows"), leads=leads, **c)
    if key == "full-funnel":
        return fn(leads, prior, ad_rows=ds.get("ad_rows"), ad_rows_prior=ds.get("ad_rows_prior"),
                  visit_rows=ds.get("visit_rows"), visit_rows_prior=ds.get("visit_rows_prior"),
                  deal_rows=ds.get("deal_rows"), deal_rows_prior=ds.get("deal_rows_prior"),
                  orders=ds.get("orders") or None, orders_prior=ds.get("orders_prior") or None, **c)
    if key == "true-roas":
        return fn(leads, ad_rows=ds.get("ad_rows"), deal_rows=ds.get("deal_rows"), orders=ds.get("orders") or None,
                  prior=prior, ad_rows_prior=ds.get("ad_rows_prior"), **c)
    if key == "conversion-truth":
        return fn(leads, ad_rows=ds.get("ad_rows"), prior=prior, ad_rows_prior=ds.get("ad_rows_prior"), **c)
    if key == "traffic-to-lead":
        return fn(leads, visit_rows=ds.get("visit_rows"), prior=prior, visit_rows_prior=ds.get("visit_rows_prior"), **c)
    if key == "pipeline":
        return fn(leads, deal_rows=ds.get("deal_rows"), ad_rows=ds.get("ad_rows"), prior=prior,
                  deal_rows_prior=ds.get("deal_rows_prior"), **c)
    if key == "wasted-spend":
        return fn(leads, ad_rows=ds.get("ad_rows"), **c)
    if key in ("ai-referrals",):
        return fn(leads, prior, history=hist, deal_rows=ds.get("deal_rows"), **c)
    if key in ("journey",):
        return fn(leads, prior, deal_rows=ds.get("deal_rows"), **c)
    # monthly, leaderboard, paid-vs-organic, audit, lead-scorer, landing-page, lead-timing
    return fn(leads, prior, **c)


def build_demo(report, out, theme=None, dataset=None, paper=None):
    from build_report import build_report
    s = demo_summary(report, theme, dataset)
    m = s.setdefault("meta", {})
    srcs = m.get("sources") or []
    if not any("sample" in str(x.get("name", "")).lower() for x in srcs if isinstance(x, dict)):
        m["sources"] = srcs + [{"name": "Sample data", "detail": "fictional business"}]
    return build_report(s, out, theme=theme, paper=paper)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    theme = None
    for i, a in enumerate(sys.argv):
        if a == "--theme" and i + 1 < len(sys.argv):
            theme = sys.argv[i + 1]
            args = [x for x in args if x != theme]
    if len(args) < 2:
        print(__doc__)
        print("Reports: " + ", ".join(REPORTS))
        sys.exit(1)
    print(build_demo(args[0], args[1:], theme))
