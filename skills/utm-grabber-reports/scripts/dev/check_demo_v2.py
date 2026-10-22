"""
Sanity checks for scripts/demo_data_v2.py.

    python3 scripts/dev/check_demo_v2.py

Loads both demo datasets, prints the numbers every consistency rule depends on
(with PASS / FAIL flags), then renders the v2 monthly recipe against each one
and validates it. Exit code 1 when any check fails.
"""
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import demo_data_v2 as dd  # noqa: E402
from connectors import (join_ads_to_leads, join_deals_to_leads, join_visits_to_leads, lead_campaign,  # noqa: E402
                        lead_platform, norm_key, normalize_orders)
from helpers import classify_traffic_source, compute_hygiene_counts, get_field  # noqa: E402

FAILS = []
AI_SOURCES = {"chatgpt.com", "perplexity.ai", "gemini.google.com", "claude.ai", "copilot.microsoft.com"}
AI_LABELS = {"OpenAI/ChatGPT", "Perplexity", "Gemini", "Claude", "Copilot"}
SEARCH = {"google", "bing", "duckduckgo", "yahoo"}
AD_PLATFORMS = ("Google Ads", "Meta Ads", "Microsoft Ads")


def check(ok, label):
    print("  [%s] %s" % ("PASS" if ok else "FAIL", label))
    if not ok:
        FAILS.append(label)


def pct(a, b):
    return 100.0 * a / b if b else 0.0


def head(title):
    print("\n== %s %s" % (title, "=" * max(0, 70 - len(title))))


def digest(obj):
    return hashlib.md5(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def month_of(e):
    return int(get_field(e, "Date Created", "date")[5:7])


def rate_class(src, med):
    if (src, med) == ("(direct)", "(none)"):
        return "direct", 1.0, 2.0
    if med == "cpc":
        return "paid search", 4.0, 9.0
    if med == "paid_social":
        return "paid social", 1.0, 3.0
    if src in AI_SOURCES:
        return "organic (AI)", 1.0, 3.0
    if med == "organic" and src in SEARCH:
        return "organic", 1.0, 3.0
    if med == "email":
        return "email", 3.0, 6.0
    if med == "referral":
        return "referral", 2.0, 5.0
    return "organic social", 0.5, 3.0


# ---------------------------------------------------------------------------
def check_dataset(name):
    dd._CACHE.clear()
    dd._CLIENT_CACHE.clear()
    t0 = time.time()
    ds = dd.get_dataset(name)
    secs = time.time() - t0
    leads, prior, hist = ds["leads"], ds["leads_prior"], ds["leads_history"]
    head("%s (%s)" % (name.upper(), ds["brand"]["company_name"]))
    check(secs < 3.0, "built in %.2fs (< 3s; coordinator limit 4s)" % secs)
    check(dd.get_dataset(name) is ds, "second call returns the cached object")
    check(sorted(ds) == sorted(["brand", "domain", "form_label", "industry", "period", "leads", "leads_prior",
                                "leads_history", "orders", "orders_prior", "orders_history", "ad_rows",
                                "ad_rows_prior", "ad_rows_history", "visit_rows", "visit_rows_prior", "deal_rows",
                                "deal_rows_prior", "deal_rows_history", "forms", "clients", "notes"]),
          "top-level keys exactly as specified (incl. orders/ad_rows/deal_rows history)")

    head("counts per key")
    for k, v in ds.items():
        if isinstance(v, list):
            print("  %-18s %6d" % (k, len(v)))
    print("  period: %s" % {k: str(v) for k, v in ds["period"].items()})

    # volumes ----------------------------------------------------------------
    lo, hi = (900, 1300) if name == "northwind" else (500, 800)
    check(lo <= len(leads) <= hi, "September leads %d within %d to %d" % (len(leads), lo, hi))
    change = pct(len(leads) - len(prior), len(prior))
    check(8 <= abs(change) <= 20, "September vs August leads %+.1f%% (8 to 20%% different)" % change)
    for cur_k, pri_k, hist_k in (("leads", "leads_prior", "leads_history"), ("orders", "orders_prior", "orders_history"),
                                 ("ad_rows", "ad_rows_prior", "ad_rows_history"),
                                 ("deal_rows", "deal_rows_prior", "deal_rows_history")):
        hist_ids = set(id(x) for x in ds[hist_k])
        same = all(id(x) in hist_ids for x in ds[cur_k] + ds[pri_k])
        check(same, "%s and %s are the same objects inside %s" % (cur_k, pri_k, hist_k))
    by_m = Counter(month_of(e) for e in hist)
    print("  history by month: %s" % dict(sorted(by_m.items())))
    check(min(e["Date Created"] for e in hist) >= "2026-04-01" and max(e["Date Created"] for e in hist) < "2026-10-01",
          "leads_history spans April 1 to September 30")
    check(all(by_m[m] < by_m[m + 1] for m in range(4, 9)), "history trends up month over month (Apr to Sep)")
    q2 = [e for e in hist if month_of(e) in (4, 5, 6)]
    q3 = [e for e in hist if month_of(e) in (7, 8, 9)]
    below = pct(len(q3) - len(q2), len(q3))
    check(8 <= below <= 15, "Q2 leads %d sit %.1f%% below Q3 %d (8 to 15%%)" % (len(q2), below, len(q3)))

    def chan(e):
        plat = lead_platform(e)
        if plat in AD_PLATFORMS:
            return plat
        org = get_field(e, "organic_source_str (HandL)")
        if org in AI_LABELS:
            return "AI assistants"
        if org:
            return "Organic search"
        return classify_traffic_source(e)
    c2, c3 = Counter(chan(e) for e in q2), Counter(chan(e) for e in q3)
    growth = {}
    for k in sorted(set(c2) | set(c3)):
        growth[k] = pct(c3[k] - c2[k], c2[k]) if c2[k] else None
        print("    %-15s Q2 %5d (%4.1f%%)  Q3 %5d (%4.1f%%)  growth %s" % (
            k, c2[k], pct(c2[k], len(q2)), c3[k], pct(c3[k], len(q3)),
            "new" if growth[k] is None else "%+.0f%%" % growth[k]))
    total_g = pct(len(q3) - len(q2), len(q2))
    meta_shift = pct(c3["Meta Ads"], len(q3)) - pct(c2["Meta Ads"], len(q2))
    check(meta_shift >= 2, "paid social (Meta) share grows Q2 to Q3 by %+.1f pts" % meta_shift)
    check(0 < growth["Organic search"] < total_g, "organic search grows slowly (%+.0f%% vs total %+.0f%%)" % (
        growth["Organic search"], total_g))
    fastest = max((k for k in growth if growth[k] is not None and c2[k] >= 20), key=lambda k: growth[k])
    check(fastest == "AI assistants", "AI assistants grow fastest (%+.0f%%; fastest channel: %s)" % (
        growth["AI assistants"], fastest))
    ids = [e["Entry ID"] for e in hist]
    check(len(set(ids)) == len(ids), "Entry IDs unique")

    head("leads by traffic_source (classify_traffic_source)")
    for label, rows in (("Sep", leads), ("Aug", prior)):
        c = Counter(classify_traffic_source(e) for e in rows)
        print("  %s: %s" % (label, ", ".join("%s %d (%.0f%%)" % (k, v, pct(v, len(rows))) for k, v in c.most_common())))

    head("leads by platform (connectors.lead_platform)")
    plat_leads = {}
    for label, rows in (("Sep", leads), ("Aug", prior)):
        c = Counter(lead_platform(e) or "(none)" for e in rows)
        plat_leads[label] = c
        print("  %s: %s" % (label, ", ".join("%s %d" % (k, v) for k, v in c.most_common())))

    head("spend by platform")
    spend = {}
    for label, rows in (("Sep", ds["ad_rows"]), ("Aug", ds["ad_rows_prior"])):
        c = defaultdict(float)
        for r in rows:
            c[r["platform"]] += r["spend"]
        spend[label] = c
        print("  %s: %s | total $%s" % (label, ", ".join("%s $%s" % (k, format(int(v), ",")) for k, v in sorted(c.items())),
                                       format(int(sum(c.values())), ",")))
    lo, hi = (25000, 30000) if name == "northwind" else (35000, 45000)
    for label in ("Sep", "Aug"):
        tot = sum(spend[label].values())
        check(lo <= tot <= hi, "%s total spend $%s within $%s to $%s" % (label, format(int(tot), ","),
                                                                         format(lo, ","), format(hi, ",")))
    keys = set(next(iter([ds["ad_rows"]]))[0].keys())
    check(keys == {"platform", "campaign", "ad_group", "ad", "keyword", "date", "spend", "impressions", "clicks",
                   "conversions", "conversion_value"}, "AdRow keys exact")

    head("platform conversions vs UTM Grabber leads (rule 2)")
    for label, rows in (("Sep", ds["ad_rows"]), ("Aug", ds["ad_rows_prior"])):
        conv = defaultdict(float)
        for r in rows:
            conv[r["platform"]] += r["conversions"]
        for plat in sorted(conv):
            n = plat_leads[label].get(plat, 0)
            over = pct(conv[plat] - n, n)
            check(18 <= over <= 32, "%s %-13s reported %5d vs %4d UTMG leads: %+.1f%% (18 to 32%%)" % (
                label, plat, conv[plat], n, over))
    joined = join_ads_to_leads(ds["ad_rows"], leads)
    for g in joined:
        if g["platform"] == "Meta Ads" and g["spend"]:
            print("    Meta campaign %-40s conv %4d leads %4d  over %+.0f%%" % (
                g["campaign"], g["platform_conversions"], g["leads"], pct(g["platform_conversions"] - g["leads"], g["leads"])))
    for m in range(4, 10):
        mrows = [r for r in ds["ad_rows_history"] if int(r["date"][5:7]) == m]
        mleads = Counter(lead_platform(e) for e in hist if month_of(e) == m)
        conv = defaultdict(float)
        for r in mrows:
            conv[r["platform"]] += r["conversions"]
        ratios = dict((pl, pct(conv[pl] - mleads[pl], mleads[pl])) for pl in conv)
        check(all(18 <= v <= 32 for v in ratios.values()), "history month %d over-reporting %s" % (
            m, ", ".join("%s %+.1f%%" % (k, v) for k, v in sorted(ratios.items()))))
    worst = max((g for g in joined if g["platform"] == "Meta Ads" and g["spend"] and g["leads"]),
                key=lambda g: g["platform_conversions"] / float(g["leads"]))
    w_over = pct(worst["platform_conversions"] - worst["leads"], worst["leads"])
    check(50 <= w_over <= 75, "worst Meta campaign %r over-reports %+.0f%% (about 60%%)" % (worst["campaign"], w_over))

    head("join_ads_to_leads (rule 1)")
    camp_keys = set((r["platform"], norm_key(r["campaign"])) for r in ds["ad_rows"])
    tagged_paid = [e for e in leads if lead_platform(e) in AD_PLATFORMS and lead_campaign(e)]
    matched = [e for e in tagged_paid if (lead_platform(e), norm_key(lead_campaign(e))) in camp_keys]
    print("  campaign groups: %d (%d with spend)" % (len(joined), sum(1 for g in joined if g["spend"])))
    for g in joined[:8]:
        print("    %-13s %-38s spend $%8.2f leads %4d cpl %s" % (g["platform"], g["campaign"][:38], g["spend"],
                                                                g["leads"], g["cpl"]))
    check(pct(len(matched), len(tagged_paid)) > 85, "%d of %d tagged paid leads matched a campaign row (%.1f%%, > 85%%)" % (
        len(matched), len(tagged_paid), pct(len(matched), len(tagged_paid))))
    ad_keys = set((norm_key(r["campaign"]), norm_key(r["ad"])) for r in ds["ad_rows"])
    content_ok = [e for e in matched if (norm_key(lead_campaign(e)), norm_key(get_field(e, "utm_content (HandL)"))) in ad_keys]
    check(len(content_ok) == len(matched), "utm_content matches an ad in that campaign for %d of %d matched leads" % (
        len(content_ok), len(matched)))
    kw_by_camp = defaultdict(set)
    for r in ds["ad_rows"]:
        if r["keyword"]:
            kw_by_camp[norm_key(r["campaign"])].add(r["keyword"])
    terms = [e for e in matched if get_field(e, "utm_term (HandL)")]
    term_ok = [e for e in terms if get_field(e, "utm_term (HandL)") in kw_by_camp[norm_key(lead_campaign(e))]]
    check(len(term_ok) == len(terms), "utm_term is one of the campaign's keywords for %d of %d search leads" % (
        len(term_ok), len(terms)))
    by_level = join_ads_to_leads(ds["ad_rows"], leads, level="ad")
    print("  ad-level groups: %d" % len(by_level))

    head("wasted spend (rule 4)")
    lead_terms = Counter((norm_key(lead_campaign(e)), get_field(e, "utm_term (HandL)")) for e in leads)
    kw_spend = defaultdict(float)
    kw_conv = defaultdict(float)
    for r in ds["ad_rows"]:
        if r["keyword"]:
            kw_spend[(norm_key(r["campaign"]), r["keyword"])] += r["spend"]
            kw_conv[(norm_key(r["campaign"]), r["keyword"])] += r["conversions"]
    wasted = [(k, v) for k, v in kw_spend.items() if v > 100 and lead_terms.get(k, 0) == 0]
    for (c, kw), v in sorted(wasted, key=lambda x: -x[1]):
        print("    %-30s %-28s $%7.2f  leads 0  platform conv %d" % (c, kw, v, kw_conv[(c, kw)]))
    check(2 <= len(wasted) <= 4, "%d keywords spend over $100 with zero leads (2 to 4)" % len(wasted))

    head("fatiguing Meta ad (rule 4)")
    fat = [s for s in dd._finalize({"northwind": dd._northwind, "harbor": dd._harbor}[name]())["streams"]
           if s.get("fatigue")][0]
    ad_key = norm_key(fat["fatigue"]["ad"])
    wk_leads, wk_spend, wk_clicks = Counter(), defaultdict(float), Counter()
    for e in leads:
        if norm_key(get_field(e, "utm_content (HandL)")) == ad_key:
            wk_leads[(int(e["Date Created"][8:10]) - 1) // 7] += 1
    for r in ds["ad_rows"]:
        if r["ad"] == fat["fatigue"]["ad"]:
            w = (int(r["date"][8:10]) - 1) // 7
            wk_spend[w] += r["spend"]
            wk_clicks[w] += r["clicks"]
    weeks = [0, 1, 2, 3]
    print("  %s / %s" % (fat["campaign"], fat["fatigue"]["ad"]))
    for w in weeks:
        print("    week %d: leads %3d  clicks %5d  spend $%7.2f" % (w + 1, wk_leads[w], wk_clicks[w], wk_spend[w]))
    check(all(wk_leads[w] >= wk_leads[w + 1] for w in weeks[:-1]) and wk_leads[0] >= 2 * max(1, wk_leads[3]),
          "leads drop week over week")
    sp = [wk_spend[w] for w in weeks]
    check(max(sp) / min(sp) < 1.25, "spend holds (weekly max/min %.2f)" % (max(sp) / min(sp)))

    head("join_visits_to_leads by source / medium")
    vr = join_visits_to_leads(ds["visit_rows"], leads)
    bad = []
    for row in sorted(vr, key=lambda x: -x["sessions"]):
        src, med = row["key"]
        cls, lo_r, hi_r = rate_class(src, med)
        rate = row["lead_rate"]
        ok = row["sessions"] > row["leads"] and rate is not None and lo_r <= rate <= hi_r
        if not ok:
            bad.append(row["key"])
        print("    %-28s %-12s sessions %6d leads %4d rate %5.2f%%  %-14s %s" % (
            src, med, row["sessions"], row["leads"], rate or 0, cls, "" if ok else "<-- out of range"))
    check(not bad, "every source/medium has sessions > leads and a lead rate inside its channel range")
    vkeys = set(ds["visit_rows"][0].keys())
    check(vkeys == {"source", "medium", "campaign", "landing_page", "date", "sessions", "engaged_sessions", "users",
                    "key_events"}, "VisitRow keys exact")
    check(len(ds["visit_rows"]) <= 6000 and len(ds["visit_rows_prior"]) <= 6000, "visit rows under 6,000 per period")
    head("join_visits_to_leads by landing page")
    lp = sorted(join_visits_to_leads(ds["visit_rows"], leads, by="landing_page"), key=lambda x: -x["sessions"])
    for row in lp[:12]:
        print("    %-44s sessions %6d leads %4d rate %5.2f%%" % (row["key"], row["sessions"], row["leads"],
                                                               row["lead_rate"] or 0))
    dead = [row for row in lp[:10] if row["lead_rate"] is not None and row["lead_rate"] < 0.1]
    check(2 <= len(dead) <= 3, "%d top-10 traffic pages with almost no leads: %s" % (
        len(dead), ", ".join(r["key"] for r in dead)))
    check(all(row["sessions"] > row["leads"] for row in lp), "every landing page has sessions > leads")

    head("join_deals_to_leads")
    for label, drows, lrows in (("Sep", ds["deal_rows"], leads), ("Aug", ds["deal_rows_prior"], prior)):
        m, um = join_deals_to_leads(drows, lrows)
        st = Counter(d["stage"] for d in drows)
        print("  %s: %d deals, %d matched, %d unmatched (phone or walk-in) | won %d (%.0f%%) lost %d (%.0f%%) open %d "
              "(%.0f%%) | deals per lead %.1f%% | won revenue $%s" % (
                  label, len(drows), len(m), len(um), st["won"], pct(st["won"], len(drows)), st["lost"],
                  pct(st["lost"], len(drows)), st["open"], pct(st["open"], len(drows)), pct(len(drows), len(lrows)),
                  format(int(sum(d["amount"] for d in drows if d["stage"] == "won")), ",")))
        check(pct(len(m), len(drows)) >= 94, "%s deal emails match lead emails exactly (%.1f%% matched)" % (
            label, pct(len(m), len(drows))))
        target = (40, 50) if name == "northwind" else (6, 10)
        check(target[0] <= pct(len(m), len(lrows)) <= target[1], "%s matched deals are %.1f%% of leads (%d to %d%%)" % (
            label, pct(len(m), len(lrows)), target[0], target[1]))
        lags_ok = True
        for x in m:
            ld = dt.date(*map(int, x["lead"]["Date Created"][:10].split("-")))
            cr = dt.date(*map(int, x["deal"]["created"].split("-")))
            if not 0 <= (cr - ld).days <= 10:
                lags_ok = False
            if x["deal"]["closed"]:
                cl = dt.date(*map(int, x["deal"]["closed"].split("-")))
                if not 3 <= (cl - cr).days <= 30 or cl > dd.ASOF:
                    lags_ok = False
        check(lags_ok, "%s created 0 to 10 days after the lead, closed 3 to 30 days after creation, never after %s" % (
            label, dd.ASOF))
        if name == "northwind":
            rng_ok = all(dd._NW_AMOUNTS[x["lead"]["Service"]][0] <= x["deal"]["amount"] <= dd._NW_AMOUNTS[x["lead"]["Service"]][1]
                         for x in m)
            check(rng_ok, "%s deal amounts inside each service's range" % label)
            by_ft = Counter(x["first_touch"] for x in m if x["deal"]["stage"] == "won")
            print("    won deals by first touch: %s" % dict(by_ft.most_common()))
        else:
            check(all(1500 <= d["amount"] <= 12000 for d in drows), "%s wholesale deal amounts $1,500 to $12,000" % label)
    dkeys = set(ds["deal_rows"][0].keys())
    check(dkeys == {"deal_id", "email", "stage", "amount", "created", "closed", "pipeline"}, "DealRow keys exact")

    if ds["orders"]:
        head("WooCommerce orders (normalize_orders)")
        for label, rows in (("Sep", ds["orders"]), ("Aug", ds["orders_prior"])):
            no = normalize_orders(rows)
            done = [o for o in no if o["status"] == "completed"]
            rev = sum(o["total"] for o in done)
            st = Counter(o["status"] for o in no)
            print("  %s: %d orders %s | completed revenue $%s | AOV $%.2f | min $%.2f max $%.2f" % (
                label, len(no), dict(st), format(int(rev), ","), rev / max(1, len(done)),
                min(o["total"] for o in no), max(o["total"] for o in no)))
            check(600 <= len(no) <= 900, "%s orders %d within 600 to 900" % (label, len(no)))
            check(60 <= rev / max(1, len(done)) <= 220, "%s AOV inside $60 to $220" % label)
            by_plat = defaultdict(float)
            for e, o in zip(rows, no):
                by_plat[lead_platform(e) or "(none)"] += o["total"]
            ad = ds["ad_rows"] if label == "Sep" else ds["ad_rows_prior"]
            val = defaultdict(float)
            for r in ad:
                val[r["platform"]] += r["conversion_value"]
            for plat in AD_PLATFORMS:
                print("    %-13s WooCommerce revenue $%9s  platform-reported value $%9s  (%+.0f%%)" % (
                    plat, format(int(by_plat[plat]), ","), format(int(val[plat]), ","),
                    pct(val[plat] - by_plat[plat], by_plat[plat])))
        keys_needed = {"Order ID", "Order Total", "Order Status", "Billing Email", "Date Created", "Products",
                       "utm_source (HandL)", "utm_source (first touch, HandL)"}
        check(all(keys_needed <= set(e) for e in ds["orders"]), "order entries carry the order + HandL fields")
        lead_emails = set(e["Email"] for e in hist)
        print("  orders by known lead emails: %.0f%%" % pct(sum(1 for e in ds["orders"] if e["Billing Email"] in lead_emails),
                                                        len(ds["orders"])))
    else:
        check(ds["orders"] == [] and ds["orders_prior"] == [], "no orders for a lead-gen business")

    head("hygiene (rule 3)")
    for label, rows in (("Sep", leads), ("Aug", prior)):
        print("  %s compute_hygiene_counts: %s" % (label, compute_hygiene_counts(rows)))
        g = [e for e in rows if lead_platform(e) == "Google Ads"]
        stripped = [e for e in g if get_field(e, "gclid (HandL)") and not get_field(e, "utm_source (HandL)")]
        check(6 <= pct(len(stripped), len(g)) <= 10, "%s Google Ads leads with gclid but no UTMs: %d of %d (%.1f%%, about 8%%)" % (
            label, len(stripped), len(g), pct(len(stripped), len(g))))
        cased = [e for e in rows if get_field(e, "utm_source (HandL)") != get_field(e, "utm_source (HandL)").lower()]
        check(4 <= pct(len(cased), len(rows)) <= 6, "%s inconsistent source casing: %d (%.1f%%, about 5%%) e.g. %s" % (
            label, len(cased), pct(len(cased), len(rows)), sorted(set(get_field(e, "utm_source (HandL)") for e in cased))[:5]))
        valid = set(norm_key(r["campaign"]) for r in ds["ad_rows"] + ds["ad_rows_prior"])
        typos = [e for e in rows if lead_platform(e) in AD_PLATFORMS and lead_campaign(e)
                 and norm_key(lead_campaign(e)) not in valid]
        check(2.5 <= pct(len(typos), len(rows)) <= 3.5, "%s campaign tags matching no ad campaign: %d (%.1f%%, about 3%%) e.g. %s" % (
            label, len(typos), pct(len(typos), len(rows)), sorted(set(lead_campaign(e) for e in typos))[:4]))
        meta = [e for e in rows if lead_platform(e) == "Meta Ads"]
        fb = [e for e in meta if get_field(e, "fbclid (HandL)")]
        check(33 <= pct(len(fb), len(meta)) <= 47, "%s fbclid on %d of %d Meta leads (%.1f%%, about 40%%)" % (
            label, len(fb), len(meta), pct(len(fb), len(meta))))

    head("first touch vs last touch, AI assistants, devices, timing")
    def touch(e, ft):
        if ft:
            f = ("utm_source (first touch, HandL)", "utm_medium (first touch, HandL)", "utm_campaign (first touch, HandL)",
                 "traffic_source (first touch, HandL)")
        else:
            f = ("utm_source (HandL)", "utm_medium (HandL)", "utm_campaign (HandL)", "traffic_source (HandL)")
        return tuple(get_field(e, k).lower() for k in f)
    diff = [e for e in leads if touch(e, True) != touch(e, False)]
    check(30 <= pct(len(diff), len(leads)) <= 40, "first touch differs from last touch for %.1f%% of leads (about 35%%)" % (
        pct(len(diff), len(leads))))
    flows = Counter((get_field(e, "traffic_source (first touch, HandL)"), classify_traffic_source(e)) for e in diff)
    print("  top first -> last flows: %s" % ", ".join("%s->%s %d" % (a, b, n) for (a, b), n in flows.most_common(6)))
    ai_share = {}
    for m in (6, 7, 8, 9):
        rows = [e for e in hist if month_of(e) == m]
        ai_share[m] = pct(sum(1 for e in rows if get_field(e, "organic_source_str (HandL)") in AI_LABELS), len(rows))
    print("  AI assistant share by month: %s" % ", ".join("%d: %.1f%%" % (m, v) for m, v in sorted(ai_share.items())))
    check(3 <= ai_share[9] <= 6 and 3 <= ai_share[8] <= 6, "AI assistants 3 to 6%% of leads in Aug and Sep")
    check(ai_share[6] < ai_share[7] < ai_share[8] < ai_share[9], "AI share grows month over month")
    ai_c = Counter(get_field(e, "organic_source_str (HandL)") for e in leads if get_field(e, "organic_source_str (HandL)") in AI_LABELS)
    print("  Sep AI split: %s" % dict(ai_c.most_common()))
    dev = Counter()
    for e in leads:
        ua = e["user_agent (HandL)"]
        dev["iPhone" if "iPhone" in ua else "Android" if "Android" in ua else "Windows" if "Windows" in ua else "Mac"] += 1
    print("  devices: %s" % ", ".join("%s %.0f%%" % (k, pct(v, len(leads))) for k, v in dev.most_common()))
    check(abs(pct(dev["iPhone"], len(leads)) - 45) <= 5 and abs(pct(dev["Android"], len(leads)) - 20) <= 4,
          "device mix near iPhone 45 / Android 20 / Windows 20 / Mac 15")
    wd = Counter(dt.datetime.strptime(e["Date Created"], "%Y-%m-%d %H:%M:%S").strftime("%a") for e in leads)
    hr = Counter(int(e["Date Created"][11:13]) for e in leads)
    print("  by weekday: %s" % ", ".join("%s %d" % (d, wd[d]) for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]))
    print("  peak hours: %s" % ", ".join("%02d:00 %d" % (h, n) for h, n in hr.most_common(5)))
    evening = sum(n for h, n in hr.items() if 18 <= h <= 23)
    weekend = wd["Sat"] + wd["Sun"]
    print("  evening (6pm to midnight) %.0f%%, weekend %.0f%%" % (pct(evening, len(leads)), pct(weekend, len(leads))))
    if name == "northwind":
        check(max(wd, key=wd.get) in ("Tue", "Wed", "Thu") and max(hr, key=hr.get) in (9, 10, 11),
              "Tue to Thu mornings peak")
    else:
        check(pct(weekend, len(leads)) > 2 / 7.0 * 100 and pct(evening, len(leads)) > 30,
              "evenings and weekends stronger than average")

    head("period-over-period stories")
    cs = Counter(lead_campaign(e).lower() for e in leads if lead_campaign(e))
    cp = Counter(lead_campaign(e).lower() for e in prior if lead_campaign(e))
    doubled = [(c, cp[c], cs[c]) for c in cs if cp.get(c, 0) >= 10 and cs[c] >= 1.8 * cp[c]]
    stalled = [(c, cp[c], cs[c]) for c in cp if cp[c] >= 10 and cs.get(c, 0) < 0.5 * cp[c]]
    print("  doubled: %s" % doubled)
    print("  stalled: %s" % stalled)
    ss = Counter(get_field(e, "utm_source (HandL)").lower() for e in leads if get_field(e, "utm_source (HandL)"))
    sp_ = Counter(get_field(e, "utm_source (HandL)").lower() for e in prior if get_field(e, "utm_source (HandL)"))
    new_src = [(s, n) for s, n in ss.items() if n >= 5 and not sp_.get(s)]
    print("  new sources: %s" % new_src)
    check(len(doubled) >= 1 and len(stalled) >= 1 and len(new_src) >= 1,
          "one campaign doubles, one stalls under half, one new source")

    head("forms, people, strings")
    fc = Counter(e["Form ID"] for e in leads)
    print("  forms: %s | Sep entries per form %s" % ([f["title"] for f in ds["forms"]], dict(fc)))
    if name == "northwind":
        dormant = [f for f in ds["forms"] if fc.get(f["id"], 0) < 5]
        check(len(dormant) == 1, "exactly one dormant form (< 5 entries): %s" % [f["title"] for f in dormant])
    emails = [e["Email"] for e in hist]
    check(all(x == x.lower() for x in emails), "emails lowercase")
    people = {}
    clash = 0
    for e in hist:
        p = (e["First Name"], e["Last Name"])
        if e["Email"] in people and people[e["Email"]] != p:
            clash += 1
        people[e["Email"]] = p
    check(clash == 0, "one person per email")
    reps = sum(n - 1 for n in Counter(emails).values() if n > 1)
    print("  repeat submissions: %d (%.1f%% of history)" % (reps, pct(reps, len(hist))))
    strings = [0]

    def walk(o):
        if isinstance(o, str):
            if u"\u2014" in o:
                strings[0] += 1
        elif isinstance(o, dict):
            for k, v in o.items():
                walk(k)
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)
    walk(ds)
    check(strings[0] == 0, "no em dashes in any string")
    return ds


def check_clients(ds):
    head("agency clients")
    for c in ds["clients"]:
        cur, pri = c["leads"], c["leads_prior"]
        cov = compute_hygiene_counts(cur)["coverage_pct"]
        ch = pct(len(cur) - len(pri), len(pri))
        print("  %-28s %-26s Sep %4d  Aug %4d  %+5.0f%%  fully tagged %3d%%" % (c["name"], c["domain"], len(cur),
                                                                              len(pri), ch, cov))
        check(80 <= len(cur) <= 600 and 80 <= len(pri) <= 600, "%s lead counts within 80 to 600" % c["name"])
        check(sorted(c) == ["brand", "domain", "leads", "leads_prior", "name"], "%s keys exact" % c["name"])
    chg = [pct(len(c["leads"]) - len(c["leads_prior"]), len(c["leads_prior"])) for c in ds["clients"]]
    cov = [compute_hygiene_counts(c["leads"])["coverage_pct"] for c in ds["clients"]]
    check(max(chg) >= 40 and min(chg) <= -20 and min(cov) <= 35 and any(abs(x) <= 5 for x in chg),
          "one growing fast, one declining, one with terrible UTM coverage, one steady")


def check_determinism():
    head("determinism (fresh processes, different PYTHONHASHSEED)")
    for name in dd.list_datasets():
        dd._CACHE.clear()
        dd._CLIENT_CACHE.clear()
        here = digest(dd.get_dataset(name))
        code = ("import sys; sys.path.insert(0, %r); import demo_data_v2 as d, hashlib, json; "
                "print(hashlib.md5(json.dumps(d.get_dataset(%r), sort_keys=True, default=str).encode('utf-8')).hexdigest())"
                % (SCRIPTS, name))
        outs = [subprocess.check_output([sys.executable, "-c", code],
                                        env=dict(os.environ, PYTHONHASHSEED=s)).decode().strip() for s in ("1", "987")]
        check(outs[0] == outs[1] == here, "%s identical across runs (%s)" % (name, here[:12]))
        other = digest(dd.get_dataset(name, seed=12345)["leads"])
        check(other != digest(dd.get_dataset(name)["leads"]), "%s a different seed gives different data" % name)


def check_recipe(name):
    head("v2 monthly recipe: %s" % name)
    from recipes_v2 import get_recipe
    from validate_v2 import validate
    ds = dd.get_dataset(name)
    s = get_recipe("monthly")(ds["leads"], ds["leads_prior"], brand_profile=ds["brand"], customer_domain=ds["domain"],
                              form_label=ds["form_label"])
    errs = validate(s)
    print("  validate(): %s" % errs)
    print("  headline: %s" % s["sections"][0]["title"])
    check(errs == [], "%s monthly summary validates clean" % name)


if __name__ == "__main__":
    nw = check_dataset("northwind")
    hb = check_dataset("harbor")
    check_clients(nw)
    check(digest(nw["clients"]) == digest(hb["clients"]), "both datasets carry the same agency client list")
    check_determinism()
    check_recipe("northwind")
    check_recipe("harbor")
    print("\n%d check(s) failed" % len(FAILS) if FAILS else "\nAll checks passed")
    for f in FAILS:
        print("  FAIL: " + f)
    sys.exit(1 if FAILS else 0)
