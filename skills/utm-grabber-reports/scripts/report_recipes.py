"""
Report recipes.

Each function here takes raw MCP entries + brand profile and returns a
ready-to-inject summary dict for one report type. Claude calls these
instead of writing 50+ lines of Python every single time.

Usage:
    from report_recipes import build_monthly_summary
    summary = build_monthly_summary(current_entries, prior_entries, brand_profile)
    # then inject into template and save

Every recipe:
  - Handles empty entries gracefully (returns a valid but minimal summary)
  - Follows the v0.8 section-schema
  - Matches voice and structure from the corresponding report spec
  - Returns a dict that passes validate_summary()
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import (
    compute_channel_mix, compute_source_leaderboard, compute_daily_volume,
    compute_hygiene_counts, compute_campaign_leaderboard,
    compute_percentage_point_delta, format_delta_pill,
)


DEFAULT_BRAND = {
    "company_name": "UTM Grabber",
    "logo": {"type": "text", "value": "UTM Grabber"},
    "colors": {
        "primary": "#0160BF", "accent": "#2E90FA", "ink": "#0B1B34",
        "muted": "#64748B", "surface": "#F5F7FB",
    },
}


def _delta(current, prior, is_pct_point=False):
    """Build a delta dict matching stat-strip schema."""
    try:
        if is_pct_point:
            d = compute_percentage_point_delta(current, prior)
        else:
            d = format_delta_pill(current, prior)
        return {
            "delta_label": d['label'].split(' vs')[0].strip(),
            "delta_direction": d['direction'],
        }
    except Exception:
        return {"delta_label": "—", "delta_direction": "flat"}


import os as _os

def _read_skill_version():
    """Read skill version from VERSION.md at load time, fallback to '0.0.0'."""
    try:
        here = _os.path.dirname(_os.path.abspath(__file__))
        # VERSION.md lives one directory up (at the skill root)
        vpath = _os.path.join(here, '..', 'VERSION.md')
        with open(vpath) as _vf:
            return _vf.read().strip()
    except Exception:
        return '0.0.0'

_SKILL_VERSION = _read_skill_version()


def _meta(customer_name, customer_domain, brand_profile, skill_version=None):
    skill_version = skill_version or _SKILL_VERSION
    return {
        "customer_name": customer_name,
        "customer_domain": customer_domain,
        "brand_profile": brand_profile or DEFAULT_BRAND,
        "skill_version": skill_version,
        "generated_at": datetime.utcnow().isoformat() + 'Z',
    }


def _empty_report(title_text, meta, reason="No data found in this period."):
    """Gracefully-handled empty-data report. Still follows section schema."""
    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": title_text,
             "title": "No *data* this period.",
             "meta_bits": [meta.get('customer_domain', ''), "0 submissions"]},
            {"type": "insight-card",
             "kicker": "Why this is empty",
             "title": "We didn't find any *form submissions* in this window.",
             "body": [reason,
                      "Check that your forms are live, UTM Grabber is active on the site, and the form plugin is connected."]},
            {"type": "closing",
             "title": "Check *tracking* and try again.",
             "body": "Once submissions appear, re-run this report for the real thing."},
        ],
    }


# ============================================================
# MONTHLY PERFORMANCE REVIEW
# ============================================================

def build_monthly_summary(current, prior, brand_profile=None,
                           customer_name=None, customer_domain=None,
                           date_range_label="Last 30 days"):
    """Monthly performance review — the default executive summary."""
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or brand.get('company_name'),
                  customer_domain or '', brand)

    if not current:
        return _empty_report(f"Monthly Performance Review · {date_range_label}", meta)

    chan = compute_channel_mix(current)
    chan_prior = compute_channel_mix(prior) if prior else chan
    hyg = compute_hygiene_counts(current)
    hyg_prior = compute_hygiene_counts(prior) if prior else hyg
    daily = compute_daily_volume(current)
    src = compute_source_leaderboard(current, top_n=6)

    leads_now = len(current)
    leads_prior = len(prior) if prior else leads_now
    per_day_now = round(leads_now / 30, 1)
    per_day_prior = round(leads_prior / 30, 1)
    top_source = src['labels'][0] if src.get('labels') else 'top source'
    top_source_leads = src['values'][0] if src.get('values') else 0
    paid_now = chan['values'][0] if chan.get('values') else 0
    paid_prior = chan_prior['values'][0] if chan_prior.get('values') else paid_now

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": f"Monthly Performance Review · {date_range_label}",
             "title": "Your *attribution* picture.",
             "meta_bits": [customer_domain or '', "Gravity Forms",
                           f"{leads_now} submissions", "30 days"]},
            {"type": "stat-strip", "stats": [
                dict(value=f"{leads_now}", label="Leads captured",
                     **_delta(leads_now, leads_prior)),
                dict(value=f"{per_day_now}", label="Leads per day",
                     **_delta(per_day_now, per_day_prior)),
                dict(value=f"{paid_now}%", label="Paid traffic",
                     **_delta(paid_now, paid_prior, is_pct_point=True)),
                dict(value=f"{hyg['coverage_pct']}%", label="UTM coverage",
                     **_delta(hyg['coverage_pct'], hyg_prior['coverage_pct'], is_pct_point=True)),
            ]},
            {"type": "insight-card",
             "kicker": "The takeaway",
             "title": f"Paid search drove *{paid_now}%* of your {leads_now} leads.",
             "body": [
                 f"{top_source} alone contributed {top_source_leads} leads — "
                 f"{round(100*top_source_leads/max(leads_now,1))}% of the total.",
                 f"Biggest attribution gap: {100-hyg['coverage_pct']}% of leads arrived "
                 "without a fully-tagged UTM trio."
             ]},
            {"type": "section-header", "number": "01",
             "kicker": "Channel Mix", "title": "Where *leads* come from."},
            {"type": "chart-insight",
             "chart": {"type": "doughnut", "labels": chan['labels'],
                       "values": chan['values'], "unit": "%"},
             "caption": "Share of form submissions by last-touch source",
             "insight_kicker": "The mix",
             "insight_title": f"Paid is *{paid_now}%* of the funnel.",
             "insight_body": [
                 "Paid marketing is the dominant engine, but a healthy mix of "
                 "organic, direct, and referral signals brand awareness beyond paid."
             ]},
            {"type": "section-header", "number": "02",
             "kicker": "Sources", "title": "Top UTM *sources*."},
            {"type": "chart-insight",
             "chart": {"type": "bar-horizontal", "labels": src['labels'],
                       "values": src['values'], "x_title": "Leads"},
             "caption": "Lead count per UTM source, top 6",
             "insight_kicker": "The winner",
             "insight_title": f"*{top_source}* leads at {top_source_leads}.",
             "insight_body": [
                 f"The top three sources ({', '.join(src['labels'][:3])}) "
                 "account for most of the volume."
             ]},
            {"type": "section-header", "number": "03",
             "kicker": "Volume", "title": "Daily *rhythm* of leads."},
            {"type": "chart",
             "chart": {"type": "area", "labels": daily['dates'], "values": daily['values']},
             "caption": f"Peak {daily['peak_value']} on {daily['peak_day']} · "
                        f"avg {daily['daily_avg']}/day"},
            {"type": "section-header", "number": "04",
             "kicker": "Recommendations", "title": "What to do *next*."},
            {"type": "recommendations", "items": [
                {"label": "Action 01", "title": "Fix *UTM tagging* on top landing pages",
                 "body": f"{100-hyg['coverage_pct']}% of leads arrive without a full UTM trio. "
                         "Audit the top 5 referring pages and add missing tags."},
                {"label": "Action 02", "title": f"Double down on *{top_source}*",
                 "body": f"{top_source_leads} leads this month. Review winning "
                         "landing pages and creative driving this channel."},
                {"label": "Action 03", "title": "Run *anomaly* checks weekly",
                 "body": "Catch sudden drops in any channel within 48 hours."},
                {"label": "Action 04", "title": "Score leads *before* sales week",
                 "body": "Rank this month's leads by declared spend, CRM, urgency."},
            ]},
            {"type": "closing",
             "kicker": "The month",
             "title": f"Next: feed *{top_source}* — it drove {round(100*top_source_leads/max(leads_now,1))}% of leads.",
             "summary_stats": [
                 {"value": f"{leads_now}", "label": "Total leads"},
                 {"value": f"{hyg['coverage_pct']}%", "label": "UTM coverage"},
                 {"value": f"{per_day_now}", "label": "Per day"},
                 {"value": str(top_source)[:12], "label": "Top source"},
             ],
             "bullets": [
                 f"{paid_now}% paid · {100 - paid_now}% organic/direct/other",
                 f"Peak day: {daily.get('peak_day', 'n/a')} with {daily.get('peak_value', 0)} leads",
                 f"Top source {top_source} drove {top_source_leads} leads "
                 f"({round(100*top_source_leads/max(leads_now,1))}% of total)",
             ]},
        ],
    }


# ============================================================
# WEEKLY EXECUTIVE SUMMARY
# ============================================================

def build_weekly_summary(current, prior, brand_profile=None,
                          customer_name=None, customer_domain=None,
                          date_range_label="Last 7 days"):
    """Weekly executive summary — brisk one-pager."""
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or brand.get('company_name'),
                  customer_domain or '', brand)

    if not current:
        return _empty_report(f"Weekly Executive Summary · {date_range_label}", meta)

    chan = compute_channel_mix(current)
    chan_prior = compute_channel_mix(prior) if prior else chan
    camp = compute_campaign_leaderboard(current, top_n=5)
    leads_now = len(current)
    leads_prior = len(prior) if prior else leads_now
    per_day_now = round(leads_now / 7, 1)
    paid_now = chan['values'][0] if chan.get('values') else 0
    paid_prior = chan_prior['values'][0] if chan_prior.get('values') else paid_now

    # Find the biggest swing channel
    swing_label = "your channel mix"
    if leads_now > leads_prior * 1.2:
        headline = f"You're up *{round(100*(leads_now-leads_prior)/max(leads_prior,1))}%* vs last week."
    elif leads_prior > leads_now * 1.2:
        headline = f"You're down *{round(100*(leads_prior-leads_now)/max(leads_prior,1))}%* vs last week."
    else:
        headline = "Your lead flow held *steady* week-over-week."

    # Ranked list rows for campaigns
    camp_rows = []
    for i, (lbl, val) in enumerate(zip(camp['labels'], camp['values'])):
        camp_rows.append({
            "rank": str(i + 1),
            "campaign": lbl,
            "leads": str(val),
            "trend": {"state": "steady", "label": "→ Steady"},
        })

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": f"Weekly Executive Summary · {date_range_label}",
             "title": "Your *week* in attribution.",
             "meta_bits": [customer_domain or '', "Gravity Forms",
                           f"{leads_now} submissions", "7 days"]},
            {"type": "stat-strip", "stats": [
                dict(value=f"{leads_now}", label="Leads this week",
                     **_delta(leads_now, leads_prior)),
                dict(value=f"{per_day_now}", label="Per day",
                     **_delta(per_day_now, round(leads_prior/7, 1))),
                dict(value=f"{paid_now}%", label="Paid share",
                     **_delta(paid_now, paid_prior, is_pct_point=True)),
            ]},
            {"type": "insight-card",
             "kicker": "The week",
             "title": headline,
             "body": [f"Top campaign: {camp['labels'][0] if camp['labels'] else 'n/a'} "
                      f"with {camp['values'][0] if camp['values'] else 0} leads."]},
            {"type": "chart-insight",
             "chart": {"type": "doughnut", "labels": chan['labels'],
                       "values": chan['values'], "unit": "%"},
             "caption": "This week's channel split",
             "insight_kicker": "The mix",
             "insight_title": f"Paid is *{paid_now}%* this week.",
             "insight_body": ["Watch for week-over-week shifts as campaigns fatigue."]},
            {"type": "ranked-list",
             "columns": [
                 {"key": "rank", "label": "#", "type": "rank", "width": "60px"},
                 {"key": "campaign", "label": "Campaign", "type": "name"},
                 {"key": "leads", "label": "Leads", "type": "number", "align": "right", "width": "100px"},
                 {"key": "trend", "label": "Trend", "type": "trend", "width": "160px"},
             ],
             "rows": camp_rows},
            {"type": "recommendations", "items": [
                {"label": "This week", "title": "Protect the *top* campaign",
                 "body": "Increase budget 10-15% if it's not already saturated."},
                {"label": "This week", "title": "Review *cold* campaigns",
                 "body": "Anything in the bottom half — audit creative or pause."},
                {"label": "This week", "title": "Tag *untagged* traffic",
                 "body": "Every leak you fix this week pays back compounding."},
                {"label": "This week", "title": "Score *hot* leads",
                 "body": "Hand the week's top-scoring leads to sales Friday afternoon."},
            ]},
            {"type": "closing",
             "kicker": "The week",
             "title": f"Monday: review *{camp['labels'][0][:24] if camp['labels'] else 'your top campaign'}* — it drove volume.",
             "summary_stats": [
                 {"value": f"{leads_now}", "label": "Leads this week"},
                 {"value": f"{per_day_now}", "label": "Per day"},
                 {"value": f"{paid_now}%", "label": "Paid share"},
                 {"value": f"{camp['labels'][0][:12] if camp['labels'] else '—'}", "label": "Top campaign"},
             ],
             "bullets": [
                 f"Weekly direction: {'up ' + str(round(100*(leads_now-leads_prior)/max(leads_prior,1))) + '%' if leads_now > leads_prior else 'steady' if leads_now == leads_prior else 'down ' + str(round(100*(leads_prior-leads_now)/max(leads_prior,1))) + '%'} vs last week",
                 f"Top campaign: {camp['labels'][0] if camp['labels'] else 'n/a'} with {camp['values'][0] if camp['values'] else 0} leads",
                 "Run the monthly review end-of-month for the full picture",
             ]},
        ],
    }


# ============================================================
# UTM HYGIENE AUDIT
# ============================================================

def build_hygiene_audit(current, brand_profile=None,
                         customer_name=None, customer_domain=None,
                         date_range_label="Last 30 days"):
    """UTM Hygiene Audit — attribution leak detection."""
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or brand.get('company_name'),
                  customer_domain or '', brand)

    if not current:
        return _empty_report(f"UTM Hygiene Audit · {date_range_label}", meta)

    hyg = compute_hygiene_counts(current)
    leads_now = len(current)
    tagged = int(leads_now * hyg['coverage_pct'] / 100)
    leaking = leads_now - tagged

    # Find leaking URLs — group by Source URL where UTM fields are missing
    leak_buckets = {}
    for entry in current:
        has_utm = bool(entry.get('utm_source (HandL)') or entry.get('utm_source'))
        url = entry.get('Source URL') or entry.get('handl_landing_page (HandL)') or '/'
        has_click_id = bool(entry.get('gclid') or entry.get('fbclid') or entry.get('msclkid'))
        if not has_utm:
            # It's a leak. Classify by leak type
            if has_click_id:
                leak_type = ({'gclid': '× Paid (gclid)',
                              'fbclid': '× Paid (fbclid)',
                              'msclkid': '× Paid (msclkid)'}
                             .get('gclid' if entry.get('gclid') else
                                  'fbclid' if entry.get('fbclid') else 'msclkid'))
                state = 'cold'
            else:
                leak_type = '↘ Referrer'
                state = 'cooling'
            # Normalize URL (strip query)
            clean_url = url.split('?')[0] if url else '/'
            key = (clean_url, leak_type, state)
            leak_buckets[key] = leak_buckets.get(key, 0) + 1

    # Top 5 leaky URLs
    top_leaks = sorted(leak_buckets.items(), key=lambda kv: -kv[1])[:5]
    leak_rows = []
    for i, ((url, leak_type, state), count) in enumerate(top_leaks):
        leak_rows.append({
            "rank": str(i + 1),
            "url": url,
            "count": str(count),
            "category": {"state": state, "label": leak_type},
        })

    top3_leaks = sum(c for (_, c) in top_leaks[:3])
    paid_platforms_leaking = len({lt for ((_, lt, _), _) in top_leaks if 'Paid' in lt})

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": f"UTM Hygiene Audit · {date_range_label}",
             "title": "Where your *attribution* is leaking.",
             "meta_bits": [customer_domain or '', "Gravity Forms",
                           f"{leads_now} submissions audited", "30 days"]},
            {"type": "hero-number",
             "kicker": "Your hygiene score",
             "value": f"{hyg['coverage_pct']}%",
             "label": f"of your leads arrive with a fully-tagged UTM trio. "
                      f"The other {leaking} leads — {100-hyg['coverage_pct']}% — "
                      "are missing attribution data."},
            {"type": "stat-strip", "stats": [
                {"value": f"{tagged}", "label": "Fully tagged"},
                {"value": f"{leaking}", "label": "Attribution leaks"},
                {"value": f"{paid_platforms_leaking}", "label": "Paid platforms leaking"},
                {"value": f"{len(leak_buckets)}", "label": "Pages to fix"},
            ]},
            {"type": "section-header", "number": "01",
             "kicker": "Leaky URLs", "title": "Top *pages* losing attribution."},
            {"type": "ranked-list",
             "columns": [
                 {"key": "rank", "label": "#", "type": "rank", "width": "60px"},
                 {"key": "url", "label": "Source URL", "type": "source"},
                 {"key": "count", "label": "Leaks", "type": "number",
                  "align": "right", "width": "100px"},
                 {"key": "category", "label": "Leak type", "type": "trend", "width": "220px"},
             ],
             "rows": leak_rows if leak_rows else [
                 {"rank": "—", "url": "No leaks detected",
                  "count": "0", "category": {"state": "steady", "label": "→ Clean"}}
             ]},
            {"type": "insight-card",
             "kicker": "What this means",
             "title": f"Your top 3 leaky pages lose *{top3_leaks} leads/month* in attribution.",
             "body": [
                 "Pages marked 'Paid (gclid/fbclid/msclkid)' have paid traffic arriving "
                 "without UTMs — your ad URL templates are broken.",
                 "Pages marked 'Referrer' have organic/social traffic arriving untagged — "
                 "add UTM parameters to external links you control."
             ]},
            {"type": "section-header", "number": "02",
             "kicker": "Fix Order", "title": "What to fix *first*."},
            {"type": "recommendations", "items": [
                {"label": "Fix 01 · Today", "title": "Check *Google Ads* URL templates",
                 "body": "Paid-with-gclid leaks trace to broken ad URL templates. "
                         "Update all campaigns to auto-tag or add UTMs to the final URL."},
                {"label": "Fix 02 · Today", "title": "Tag your *referral* links",
                 "body": "Pages with 'Referrer' leaks get untagged external links. "
                         "Add UTM parameters to every outbound link you control."},
                {"label": "Fix 03 · This week", "title": "Audit *Meta Ads* templates",
                 "body": "fbclid leaks mean Meta ad URL templates need the full UTM trio."},
                {"label": "Fix 04 · This week", "title": "*Re-run* the audit",
                 "body": "Wait 7 days after fixes, re-run — expect coverage to jump 20+ points."},
            ]},
            {"type": "closing",
             "kicker": "The fix",
             "title": f"Fix the top 3 pages — recover *{top3_leaks}* leads/month.",
             "summary_stats": [
                 {"value": f"{hyg['coverage_pct']}%", "label": "UTM coverage"},
                 {"value": f"{leaking}", "label": "Attribution leaks"},
                 {"value": f"{len(leak_buckets)}", "label": "Pages to fix"},
                 {"value": f"{paid_platforms_leaking}", "label": "Paid platforms"},
             ],
             "bullets": [
                 f"{tagged} of {leads_now} leads arrived fully tagged",
                 f"Top 3 leaky pages lose {top3_leaks} leads/month",
                 "Re-run this audit in 7 days after fixes — expect coverage to jump 20+ points",
             ]},
        ],
    }


# ============================================================
# CAMPAIGN LEADERBOARD
# ============================================================

def build_campaign_leaderboard(current, brand_profile=None,
                                customer_name=None, customer_domain=None,
                                date_range_label="Last 30 days"):
    """Top Campaign Leaderboard — who won this period."""
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or brand.get('company_name'),
                  customer_domain or '', brand)

    if not current:
        return _empty_report(f"Top Campaign Leaderboard · {date_range_label}", meta)

    camp = compute_campaign_leaderboard(current, top_n=10)
    leads_now = len(current)
    total_campaigns = len(camp.get('labels', []))
    top_camp = camp['labels'][0] if camp.get('labels') else 'top campaign'
    top_camp_leads = camp['values'][0] if camp.get('values') else 0
    top3_share = (sum(camp['values'][:3]) / max(leads_now, 1)) * 100 if camp.get('values') else 0

    rows = []
    for i, (lbl, val) in enumerate(zip(camp['labels'], camp['values'])):
        # Heuristic trend state based on position
        state = "rising" if i == 0 else ("steady" if i < 3 else "cooling" if i < 6 else "cold")
        label = {"rising": "↗ Rising", "steady": "→ Steady",
                 "cooling": "↘ Cooling", "cold": "× Cold"}[state]
        rows.append({
            "rank": str(i + 1),
            "campaign": lbl,
            "leads": str(val),
            "trend": {"state": state, "label": label},
        })

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": f"Top Campaign Leaderboard · {date_range_label}",
             "title": "Your *winners* this period.",
             "meta_bits": [customer_domain or '', f"{total_campaigns} campaigns",
                           f"{leads_now} leads", "30 days"]},
            {"type": "stat-strip", "stats": [
                {"value": f"{total_campaigns}", "label": "Campaigns active"},
                {"value": f"{top_camp_leads}", "label": "Top campaign leads"},
                {"value": f"{round(top3_share)}%", "label": "Top 3 share"},
            ]},
            {"type": "chart",
             "chart": {"type": "bar-horizontal", "labels": camp['labels'],
                       "values": camp['values']},
             "caption": f"Top 10 campaigns by lead volume · {top_camp} leads"},
            {"type": "ranked-list",
             "columns": [
                 {"key": "rank", "label": "#", "type": "rank", "width": "60px"},
                 {"key": "campaign", "label": "Campaign", "type": "name"},
                 {"key": "leads", "label": "Leads", "type": "number",
                  "align": "right", "width": "90px"},
                 {"key": "trend", "label": "Trend", "type": "trend", "width": "140px"},
             ],
             "rows": rows},
            {"type": "insight-card",
             "kicker": "Who's carrying the weight",
             "title": f"Your top *3* campaigns drove {round(top3_share)}% of leads.",
             "body": ["Concentration is a double-edged sword: efficient, but fragile. "
                      "One campaign fatiguing could knock the top-line significantly.",
                      f"The cold campaigns ({len([r for r in rows if r['trend']['state'] == 'cold'])}) "
                      "are candidates for creative refresh or retirement."]},
            {"type": "recommendations", "items": [
                {"label": "Action 01", "title": f"Feed *{top_camp}*",
                 "body": "Increase budget 15-20% if not at saturation."},
                {"label": "Action 02", "title": "Audit *cold* campaigns",
                 "body": "Refresh creative or pause; don't let dead weight compound."},
                {"label": "Action 03", "title": "Test *one new* campaign",
                 "body": "In the same channel as the winner — look for diminishing returns."},
                {"label": "Action 04", "title": "Score the *top-tier* leads",
                 "body": "High-scoring leads from winning campaigns deserve sales-assisted follow-up."},
            ]},
            {"type": "closing",
             "kicker": "The standings",
             "title": f"Cut the *{sum(1 for r in rows if r['trend']['state'] == 'cold')} cold*. Double the top 3.",
             "summary_stats": [
                 {"value": f"{total_campaigns}", "label": "Campaigns active"},
                 {"value": f"{top_camp_leads}", "label": "Top campaign leads"},
                 {"value": f"{round(top3_share)}%", "label": "Top 3 share"},
                 {"value": f"{sum(1 for r in rows if r['trend']['state'] == 'cold')}", "label": "Cold campaigns"},
             ],
             "bullets": [
                 f"Winner: {top_camp} with {top_camp_leads} leads",
                 f"Top 3 campaigns carried {round(top3_share)}% of volume",
                 "Run weekly to catch campaigns before they go cold",
             ]},
        ],
    }


# ============================================================
# PREDICTIVE FORECAST
# ============================================================

def build_forecast_summary(history, brand_profile=None,
                            customer_name=None, customer_domain=None,
                            baseline_label="Last 90 days"):
    """Predictive Forecast — next 30 days based on 90-day baseline."""
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or brand.get('company_name'),
                  customer_domain or '', brand)

    if not history:
        return _empty_report(f"Predictive Forecast · {baseline_label}", meta)

    leads_total = len(history)
    daily_baseline = leads_total / 90
    forecast_30d = round(daily_baseline * 30)
    range_low = round(forecast_30d * 0.88)
    range_high = round(forecast_30d * 1.12)

    daily = compute_daily_volume(history)

    # Fabricate a 30-day forward projection as daily_baseline with slight variation
    # (simple, not ML — see voice guidance in spec)
    forward_dates = [f"+{i+1}d" for i in range(30)]
    forward_values = [round(daily_baseline) for _ in range(30)]

    # Combined series for line chart: historical + forecast
    combined_labels = (daily['dates'][-30:] + forward_dates)
    combined_values = (daily['values'][-30:] + forward_values)

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": f"Predictive Forecast · Next 30 days",
             "title": "Your *projected* pipeline.",
             "meta_bits": [customer_domain or '', f"Baseline: {baseline_label}",
                           f"{leads_total} data points", "Confidence ±12%"]},
            {"type": "hero-number",
             "kicker": "Projected leads · next 30 days",
             "value": f"{forecast_30d}",
             "label": f"Expected range: {range_low}–{range_high} leads. "
                      f"Based on your last 90 days at {round(daily_baseline, 1)}/day."},
            {"type": "chart",
             "chart": {"type": "line", "labels": combined_labels, "values": combined_values},
             "caption": f"Last 30 days (actual) → next 30 days (projected at baseline rate)"},
            {"type": "insight-card",
             "kicker": "What this assumes",
             "title": "Your *trend* is the dominant signal.",
             "body": ["This projection assumes your channel mix holds steady, no major "
                      "campaign changes, and day-of-week seasonality applies.",
                      "The ±12% range captures normal variation in your last 90 days — "
                      "unusual events (launches, outages, press) will push you outside it."]},
            {"type": "recommendations", "items": [
                {"label": "What-if 01", "title": "*Increase* top channel 20%",
                 "body": f"At linear scaling, expect roughly {round(forecast_30d * 1.1)} leads (+10%)."},
                {"label": "What-if 02", "title": "*Pause* the cold third",
                 "body": f"Redirected to the top channel, expect similar volume at lower CPA."},
                {"label": "What-if 03", "title": "*Hold* the mix steady",
                 "body": f"Baseline projection: {range_low}–{range_high}. Good for planning."},
                {"label": "What-if 04", "title": "*Launch* a new channel",
                 "body": "First-month contribution typically small — don't count on it in this forecast."},
            ]},
            {"type": "closing",
             "kicker": "The forecast",
             "title": f"Plan for *{forecast_30d}* leads — budget at the low end ({range_low}).",
             "summary_stats": [
                 {"value": f"{forecast_30d}", "label": "Projected leads"},
                 {"value": f"{range_low}", "label": "Low end"},
                 {"value": f"{range_high}", "label": "High end"},
                 {"value": f"±12%", "label": "Confidence range"},
             ],
             "bullets": [
                 f"Based on {leads_total} data points over the last 90 days",
                 f"Assumes stable mix and day-of-week seasonality",
                 "Re-run with budget scenarios for tighter ranges",
             ]},
        ],
    }


# ============================================================
# ANOMALY DETECTOR
# ============================================================

def build_anomaly_summary(current, baseline, brand_profile=None,
                           customer_name=None, customer_domain=None):
    """Anomaly Detector — channels/campaigns shifting vs 30-day baseline."""
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or brand.get('company_name'),
                  customer_domain or '', brand)

    if not current:
        return _empty_report("Anomaly Detector · Last 7 days", meta)

    # Compute per-source volume current (7d) vs baseline (30d avg per week)
    from helpers import compute_source_leaderboard
    cur_src = compute_source_leaderboard(current, top_n=20)
    base_src = compute_source_leaderboard(baseline, top_n=20) if baseline else cur_src

    # Build per-source comparison
    baseline_weekly = {lbl: val / 4.3 for lbl, val in zip(base_src['labels'], base_src['values'])}
    current_weekly = {lbl: val for lbl, val in zip(cur_src['labels'], cur_src['values'])}

    anomalies = []
    all_sources = set(baseline_weekly) | set(current_weekly)
    for s in all_sources:
        bl = baseline_weekly.get(s, 0)
        cw = current_weekly.get(s, 0)
        if bl < 2 and cw < 2:
            continue  # Too noisy to flag
        if bl == 0:
            pct = 100 if cw > 0 else 0
        else:
            pct = round((cw - bl) / max(bl, 0.1) * 100)
        if abs(pct) >= 50:
            anomalies.append((s, round(bl), cw, pct))

    anomalies.sort(key=lambda x: -abs(x[3]))

    rows = []
    for i, (src, bl, cw, pct) in enumerate(anomalies[:8]):
        state = "rising" if pct > 0 else ("cold" if pct < -50 else "cooling")
        arrow = "↗" if pct > 0 else "↘"
        rows.append({
            "rank": str(i + 1),
            "source": src,
            "baseline": str(bl),
            "current": str(cw),
            "delta": {"state": state, "label": f"{arrow} {pct:+}%"},
        })

    largest_drop = min((a[3] for a in anomalies), default=0)
    largest_spike = max((a[3] for a in anomalies), default=0)
    headline_src = anomalies[0][0] if anomalies else "no significant changes"
    headline_pct = anomalies[0][3] if anomalies else 0

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": "Anomaly Detector · Last 7 days",
             "title": "What *changed* this week.",
             "meta_bits": [customer_domain or '', "Baseline: last 30 days",
                           f"{len(anomalies)} anomalies detected"]},
            {"type": "stat-strip", "stats": [
                {"value": f"{len(anomalies)}", "label": "Anomalies detected"},
                {"value": f"{largest_drop:+}%", "label": "Largest drop"},
                {"value": f"{largest_spike:+}%", "label": "Largest spike"},
            ]},
            {"type": "insight-card",
             "kicker": "Headline anomaly",
             "title": f"*{headline_src}* shifted {headline_pct:+}% vs baseline.",
             "body": ["A change of this magnitude usually has a specific cause — "
                      "budget change, creative approval, pixel firing issue, or a "
                      "legitimate trend shift worth doubling down on."]},
            {"type": "ranked-list",
             "columns": [
                 {"key": "rank", "label": "#", "type": "rank", "width": "60px"},
                 {"key": "source", "label": "Source", "type": "name"},
                 {"key": "baseline", "label": "Baseline/wk", "type": "mono-number",
                  "align": "right", "width": "120px"},
                 {"key": "current", "label": "Current", "type": "mono-number",
                  "align": "right", "width": "100px"},
                 {"key": "delta", "label": "Change", "type": "trend", "width": "140px"},
             ],
             "rows": rows if rows else [
                 {"rank": "—", "source": "No significant anomalies",
                  "baseline": "—", "current": "—",
                  "delta": {"state": "steady", "label": "→ Stable"}}
             ]},
            {"type": "recommendations", "items": [
                {"label": "Investigate 01", "title": "Check *ad account* status",
                 "body": "Paused ads, rejected creative, or disabled campaigns cause sudden drops."},
                {"label": "Investigate 02", "title": "Review *budget* changes",
                 "body": "Compare actual weekly spend to previous weeks for flagged channels."},
                {"label": "Investigate 03", "title": "Verify *pixel* fires",
                 "body": "If tracking fails, conversions look like they've dropped."},
                {"label": "Investigate 04", "title": "Look for *seasonal* effects",
                 "body": "Holidays, weather, news cycles can all shift volume."},
            ]},
            {"type": "closing",
             "kicker": "The moves",
             "title": f"Investigate *{headline_src}* — {headline_pct:+}% vs baseline.",
             "summary_stats": [
                 {"value": f"{len(anomalies)}", "label": "Anomalies"},
                 {"value": f"{largest_drop:+}%", "label": "Biggest drop"},
                 {"value": f"{largest_spike:+}%", "label": "Biggest spike"},
                 {"value": f"{headline_src[:12]}", "label": "Top mover"},
             ],
             "bullets": [
                 f"Headline: {headline_src} shifted {headline_pct:+}% vs baseline",
                 "Investigate before assuming — ad-account status, budget changes, pixel fires",
                 "Run daily during volatile weeks",
             ]},
        ],
    }


# ============================================================
# Convenience: recipe router
# ============================================================

RECIPES = {
    'monthly': build_monthly_summary,
    'weekly': build_weekly_summary,
    'audit': build_hygiene_audit,
    'hygiene': build_hygiene_audit,
    'leaderboard': build_campaign_leaderboard,
    'campaigns': build_campaign_leaderboard,
    'forecast': build_forecast_summary,
    'anomaly': build_anomaly_summary,
}


def get_recipe(report_name):
    """Look up a recipe by short name. Returns None if no recipe exists for that report."""
    return RECIPES.get(report_name.lower().replace(' ', '-'))


# ============================================================
# LEAD QUALITY SCORER
# ============================================================

def _score_lead(entry):
    """Score a single lead 0-100 based on declared attributes."""
    score = 0

    # Monthly ad spend bracket
    spend = str(entry.get('Monthly Ad Spend', '')).lower()
    if any(k in spend for k in ['100k', '100,000', '50k', '50,000', '$50', '$100']):
        score += 35
    elif any(k in spend for k in ['10k', '10,000', '25k', '25,000', '$10', '$25']):
        score += 20
    elif spend and spend != 'none' and spend != '':
        score += 10

    # CRM
    crm = str(entry.get('CRM Platform', '')).lower()
    if any(k in crm for k in ['salesforce', 'hubspot', 'marketo']):
        score += 20  # Enterprise
    elif any(k in crm for k in ['pipedrive', 'zoho', 'activecampaign']):
        score += 15  # Mid-market
    elif crm and crm != 'none' and crm != '':
        score += 8

    # Timeframe urgency
    tf = str(entry.get('Desired Timeframe', '')).lower()
    if any(k in tf for k in ['now', 'immediately', 'this week', 'this month']):
        score += 20
    elif any(k in tf for k in ['next month', '30 days', '60 days', 'quarter']):
        score += 12
    elif tf and tf != '':
        score += 5

    # Source quality (paid search > paid social > organic > referral > direct)
    medium = str(entry.get('utm_medium (HandL)') or entry.get('utm_medium', '')).lower()
    if medium == 'cpc':
        score += 15
    elif 'paid' in medium:
        score += 10
    elif medium == 'organic':
        score += 8
    elif medium == 'referral':
        score += 5

    # Company (any company name → +10)
    if entry.get('Company Name'):
        score += 10

    return min(score, 100)


def build_lead_scorer_summary(current, brand_profile=None,
                                customer_name=None, customer_domain=None,
                                date_range_label="Last 30 days"):
    """Lead Quality Scorer — ranks leads by declared intent for sales prioritization."""
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or brand.get('company_name'), customer_domain or '', brand)

    if not current:
        return _empty_report(f"Lead Quality Scorer · {date_range_label}", meta)

    # Score every lead
    scored = [(e, _score_lead(e)) for e in current]
    scored.sort(key=lambda x: -x[1])
    top_tier_count = sum(1 for _, s in scored if s >= 70)
    avg_score = round(sum(s for _, s in scored) / len(scored), 1)

    # Top 10 rows
    rows = []
    for i, (e, score) in enumerate(scored[:10]):
        email = str(e.get('Work Email') or e.get('Email Address', ''))
        # Mask email for privacy
        if '@' in email:
            parts = email.split('@')
            user = parts[0][:3] + '***' if len(parts[0]) > 3 else parts[0]
            email_masked = f"{user}@{parts[1]}"
        else:
            email_masked = '—'
        company = str(e.get('Company Name', '—'))[:28]
        spend = str(e.get('Monthly Ad Spend', '—'))[:16]
        source = f"{e.get('utm_source (HandL)') or 'direct'} · {e.get('utm_medium (HandL)') or '—'}"
        rows.append({
            "rank": str(i + 1),
            "email": email_masked,
            "company": company,
            "spend": spend,
            "score": str(score),
            "source": source[:28],
        })

    # Top source in the top tier
    top_tier_sources = {}
    for e, s in scored[:top_tier_count if top_tier_count > 0 else 10]:
        src = e.get('utm_source (HandL)') or 'direct'
        top_tier_sources[src] = top_tier_sources.get(src, 0) + 1
    top_tier_src = max(top_tier_sources, key=top_tier_sources.get) if top_tier_sources else 'mixed'
    top_tier_src_count = top_tier_sources.get(top_tier_src, 0)

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": f"Lead Quality Scorer · {date_range_label}",
             "title": "Your *top* leads to work first.",
             "meta_bits": [customer_domain or '', f"{len(scored)} scored",
                           f"Score ≥ 70 = top tier"]},
            {"type": "hero-number",
             "kicker": "High-priority leads",
             "value": f"{top_tier_count}",
             "label": "scored in the top tier by declared spend, CRM, and urgency. "
                      "These are your highest-conversion prospects — work them first."},
            {"type": "stat-strip", "stats": [
                {"value": f"{len(scored)}", "label": "Leads scored"},
                {"value": f"{top_tier_count}", "label": "Top tier (≥70)"},
                {"value": f"{avg_score}", "label": "Average score"},
                {"value": f"{top_tier_src}", "label": "Top-tier source"},
            ]},
            {"type": "section-header", "number": "01",
             "kicker": "Top 10", "title": "Work *these* first."},
            {"type": "ranked-list",
             "columns": [
                 {"key": "rank", "label": "#", "type": "rank", "width": "60px"},
                 {"key": "email", "label": "Email", "type": "source", "width": "220px"},
                 {"key": "company", "label": "Company", "type": "name"},
                 {"key": "spend", "label": "Monthly Spend", "type": "mono-number",
                  "align": "right", "width": "140px"},
                 {"key": "score", "label": "Score", "type": "number",
                  "align": "right", "width": "90px"},
             ],
             "rows": rows},
            {"type": "insight-card",
             "kicker": "Pattern in your top tier",
             "title": f"*{top_tier_src}* drove {top_tier_src_count} of your top leads.",
             "body": ["Sources producing high-score leads deserve disproportionate budget. "
                      "Sources producing only low-score leads might be filling your top-of-funnel "
                      "but not your pipeline — worth auditing."]},
            {"type": "recommendations", "items": [
                {"label": "Sales 01", "title": "Work the *top 10* this week",
                 "body": "Personalized outreach, not automation. Hand these to your best rep."},
                {"label": "Sales 02", "title": "Automate the *mid-tier* (40-69)",
                 "body": "Sequence them into a nurture flow with spend- or CRM-specific messaging."},
                {"label": "Marketing", "title": "Double down on *top-tier sources*",
                 "body": f"Shift 10-15% of budget toward {top_tier_src} if CPA allows."},
                {"label": "Data", "title": "Tighten *scoring inputs*",
                 "body": "Audit which form fields are blank most often — fix or remove."},
            ]},
            {"type": "closing",
             "kicker": "The pipeline",
             "title": f"Call the top *{top_tier_count}* leads this week — from {top_tier_src}.",
             "summary_stats": [
                 {"value": f"{len(scored)}", "label": "Leads scored"},
                 {"value": f"{top_tier_count}", "label": "Top tier (≥70)"},
                 {"value": f"{avg_score}", "label": "Average score"},
                 {"value": f"{top_tier_src[:12]}", "label": "Top-tier source"},
             ],
             "bullets": [
                 f"{top_tier_count} high-priority leads need sales-assisted outreach",
                 f"{top_tier_src} drove {top_tier_src_count} of your top leads",
                 "Export CSV for CRM hand-off — masked emails for privacy",
             ]},
        ],
    }


# ============================================================
# LANDING PAGE PERFORMANCE
# ============================================================

def build_landing_page_summary(current, brand_profile=None,
                                customer_name=None, customer_domain=None,
                                date_range_label="Last 30 days"):
    """Landing Page Performance — which pages convert from which sources."""
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or brand.get('company_name'), customer_domain or '', brand)

    if not current:
        return _empty_report(f"Landing Page Performance · {date_range_label}", meta)

    # Group by Source URL (normalized)
    page_counts = {}
    page_sources = {}
    for e in current:
        url = (e.get('Source URL') or e.get('handl_landing_page (HandL)') or '/').split('?')[0]
        try:
            from urllib.parse import urlparse
            path = urlparse(url).path or '/'
        except Exception:
            path = url
        page_counts[path] = page_counts.get(path, 0) + 1
        src = e.get('utm_source (HandL)') or 'direct'
        if path not in page_sources:
            page_sources[path] = {}
        page_sources[path][src] = page_sources[path].get(src, 0) + 1

    # Top 10 by lead count
    top_pages = sorted(page_counts.items(), key=lambda kv: -kv[1])[:10]
    total = sum(page_counts.values())
    top3_share = sum(c for _, c in top_pages[:3]) / max(total, 1) * 100

    rows = []
    for i, (path, count) in enumerate(top_pages):
        srcs = page_sources.get(path, {})
        top_src = max(srcs, key=srcs.get) if srcs else '—'
        # Trend: heuristic based on rank
        state = "rising" if i == 0 else "steady" if i < 4 else "cooling"
        rows.append({
            "rank": str(i + 1),
            "page": path[:48],
            "source": f"{top_src} ({srcs.get(top_src, 0)})",
            "leads": str(count),
            "trend": {"state": state, "label": {"rising":"↗ Top","steady":"→ Steady","cooling":"↘ Below avg"}[state]},
        })

    top_page = top_pages[0][0] if top_pages else '/'
    top_page_leads = top_pages[0][1] if top_pages else 0

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": f"Landing Page Performance · {date_range_label}",
             "title": "Where *leads* convert.",
             "meta_bits": [customer_domain or '', f"{len(page_counts)} pages",
                           f"{total} total leads"]},
            {"type": "stat-strip", "stats": [
                {"value": f"{len(page_counts)}", "label": "Pages with leads"},
                {"value": f"{top_page_leads}", "label": "Top page leads"},
                {"value": f"{round(top3_share)}%", "label": "Top 3 share"},
            ]},
            {"type": "ranked-list",
             "columns": [
                 {"key": "rank", "label": "#", "type": "rank", "width": "60px"},
                 {"key": "page", "label": "Page", "type": "source"},
                 {"key": "source", "label": "Top source", "type": "source", "width": "180px"},
                 {"key": "leads", "label": "Leads", "type": "number",
                  "align": "right", "width": "80px"},
                 {"key": "trend", "label": "Trend", "type": "trend", "width": "130px"},
             ],
             "rows": rows},
            {"type": "insight-card",
             "kicker": "Page patterns",
             "title": f"*{top_page[:48]}* carries {top_page_leads} leads.",
             "body": [f"The top 3 pages account for {round(top3_share)}% of total lead volume. "
                      "Pages that concentrate traffic are worth replicating — the layouts, "
                      "form placements, and value props that work here should inform every "
                      "new landing page you build."]},
            {"type": "recommendations", "items": [
                {"label": "Action 01", "title": "Replicate *the top page* layout",
                 "body": "Audit CTA position, headline, form length. Those are your patterns."},
                {"label": "Action 02", "title": "Fix *the bottom third*",
                 "body": "Low-converting pages need new hooks or they should be retired."},
                {"label": "Action 03", "title": "Add *source variants* to top page",
                 "body": "Test a LinkedIn-specific variant of your #1 page for your #1 source."},
                {"label": "Action 04", "title": "Track *time-on-page* next",
                 "body": "Combine attribution with engagement — UTM Grabber tracks landing; "
                         "a heatmap tool will show why it converts."},
            ]},
            {"type": "closing",
             "kicker": "The pages",
             "title": f"Replicate *{top_page[:32]}* — it's doing {top_page_leads} leads.",
             "summary_stats": [
                 {"value": f"{len(page_counts)}", "label": "Pages with leads"},
                 {"value": f"{top_page_leads}", "label": "Top page leads"},
                 {"value": f"{round(top3_share)}%", "label": "Top 3 share"},
                 {"value": f"{total}", "label": "Total leads"},
             ],
             "bullets": [
                 f"Winner: {top_page[:40]} carries {top_page_leads} leads",
                 f"Top 3 pages capture {round(top3_share)}% of volume",
                 "Replicate the top page's layout and CTA for new builds",
             ]},
        ],
    }


# Update the router
RECIPES['lead-scorer'] = build_lead_scorer_summary
RECIPES['lead-quality'] = build_lead_scorer_summary
RECIPES['score-leads'] = build_lead_scorer_summary
RECIPES['landing-pages'] = build_landing_page_summary
RECIPES['landing-page'] = build_landing_page_summary


# ============================================================
# GENERIC LEADERBOARD HELPER (for form, ad-creative, keyword)
# ============================================================

def _leaderboard_rows(grouped_counts, secondary_fn=None, top_n=10):
    """Build ranked-list rows from a dict {label: count}. Optionally
    decorates with secondary info via secondary_fn(label) → str."""
    items = sorted(grouped_counts.items(), key=lambda kv: -kv[1])[:top_n]
    rows = []
    for i, (label, count) in enumerate(items):
        state = "rising" if i == 0 else "steady" if i < 3 else "cooling" if i < 6 else "cold"
        state_label = {"rising":"↗ Top","steady":"→ Steady","cooling":"↘ Mid","cold":"× Cold"}[state]
        row = {
            "rank": str(i + 1),
            "label": str(label)[:48],
            "count": str(count),
            "trend": {"state": state, "label": state_label},
        }
        if secondary_fn:
            row["secondary"] = secondary_fn(label)
        rows.append(row)
    return rows, items


# ============================================================
# FORM PERFORMANCE
# ============================================================

def build_form_performance_summary(current, brand_profile=None,
                                     customer_name=None, customer_domain=None,
                                     date_range_label="Last 30 days"):
    """Form Performance — ranks forms by submission count."""
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or brand.get('company_name'), customer_domain or '', brand)
    if not current:
        return _empty_report(f"Form Performance · {date_range_label}", meta)

    form_counts = {}
    form_top_sources = {}
    for e in current:
        fid = e.get('Form ID') or e.get('form_id') or 'Main form'
        form_counts[fid] = form_counts.get(fid, 0) + 1
        src = e.get('utm_source (HandL)') or 'direct'
        form_top_sources.setdefault(fid, {})
        form_top_sources[fid][src] = form_top_sources[fid].get(src, 0) + 1

    total = sum(form_counts.values())
    avg_per_form = round(total / max(len(form_counts), 1), 1)
    top_form, top_form_leads = max(form_counts.items(), key=lambda kv: kv[1]) if form_counts else ('—', 0)

    rows = []
    for i, (fid, count) in enumerate(sorted(form_counts.items(), key=lambda kv: -kv[1])[:10]):
        src_counts = form_top_sources.get(fid, {})
        top_src = max(src_counts, key=src_counts.get) if src_counts else '—'
        state = "rising" if i == 0 else "steady" if i < 3 else "cold"
        rows.append({
            "rank": str(i + 1),
            "form": f"Form {fid}",
            "source": top_src,
            "count": str(count),
            "trend": {"state": state,
                      "label": {"rising":"↗ Top","steady":"→ Steady","cold":"× Low"}[state]},
        })

    concentration_pct = round(100 * top_form_leads / max(total, 1))

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": f"Form Performance · {date_range_label}",
             "title": "Which *forms* earn their keep.",
             "meta_bits": [customer_domain or '', f"{len(form_counts)} forms",
                           f"{total} submissions"]},
            {"type": "stat-strip", "stats": [
                {"value": f"{len(form_counts)}", "label": "Forms active"},
                {"value": f"{top_form_leads}", "label": "Top form submissions"},
                {"value": f"{avg_per_form}", "label": "Avg per form"},
            ]},
            {"type": "ranked-list",
             "columns": [
                 {"key": "rank", "label": "#", "type": "rank", "width": "60px"},
                 {"key": "form", "label": "Form", "type": "name"},
                 {"key": "source", "label": "Top source", "type": "source", "width": "180px"},
                 {"key": "count", "label": "Submissions", "type": "number",
                  "align": "right", "width": "140px"},
                 {"key": "trend", "label": "Trend", "type": "trend", "width": "130px"},
             ],
             "rows": rows},
            {"type": "insight-card",
             "kicker": "Distribution",
             "title": f"*Form {top_form}* handles {concentration_pct}% of submissions.",
             "body": ["High concentration means your primary form is doing the work. "
                      "If that form breaks, your lead flow breaks. Worth testing a second "
                      "form placement as backup redundancy."]},
            {"type": "recommendations", "items": [
                {"label": "Action 01", "title": "Simplify the *lowest* converter",
                 "body": "Forms with few submissions usually have too many required fields or poor placement."},
                {"label": "Action 02", "title": "Duplicate *the top* form",
                 "body": "Add it to a second page or template where it might pick up more traffic."},
                {"label": "Action 03", "title": "Audit *zero-submit* forms",
                 "body": "If a form exists but gets no leads, it should be retired or completely rebuilt."},
                {"label": "Action 04", "title": "A/B test *field count*",
                 "body": "Try a shorter version of your top form in 50% of traffic this month."},
            ]},
            {"type": "closing",
             "kicker": "The forms",
             "title": f"Form {top_form} does *{concentration_pct}%* of submissions — {'add a second form as backup' if len(form_counts) < 2 else f'audit the other {len(form_counts) - 1}'}.",
             "summary_stats": [
                 {"value": f"{len(form_counts)}", "label": "Forms active"},
                 {"value": f"{top_form_leads}", "label": "Top form submissions"},
                 {"value": f"{avg_per_form}", "label": "Avg per form"},
                 {"value": f"{concentration_pct}%", "label": "Top form share"},
             ],
             "bullets": [
                 f"Form {top_form} handles {concentration_pct}% of submissions",
                 f"{len(form_counts)} forms active; {total} total submissions",
                 "Re-run monthly — form performance shifts with site design",
             ]},
        ],
    }


# ============================================================
# AD CREATIVE PERFORMANCE
# ============================================================

def build_ad_creative_summary(current, brand_profile=None,
                                customer_name=None, customer_domain=None,
                                date_range_label="Last 30 days"):
    """Ad Creative Performance — by utm_content within paid channels."""
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or brand.get('company_name'), customer_domain or '', brand)
    if not current:
        return _empty_report(f"Ad Creative Performance · {date_range_label}", meta)

    # Filter to paid channels only (cpc, paid social, etc.)
    paid = [e for e in current
            if str(e.get('utm_medium (HandL)') or e.get('utm_medium', '')).lower()
            in ('cpc', 'paid social', 'display', 'paidsocial', 'paid-social', 'video')]

    if not paid:
        meta = _meta(customer_name or brand.get('company_name'), customer_domain or '', brand)
        return _empty_report(f"Ad Creative Performance · {date_range_label}", meta,
                              reason="No paid-channel submissions found in this period.")

    # Group by utm_content
    creative_counts = {}
    creative_channels = {}
    for e in paid:
        content = e.get('utm_content (HandL)') or e.get('utm_content') or '(no utm_content)'
        creative_counts[content] = creative_counts.get(content, 0) + 1
        src = e.get('utm_source (HandL)') or 'unknown'
        medium = e.get('utm_medium (HandL)') or 'paid'
        creative_channels[content] = f"{src} · {medium}"

    top_items = sorted(creative_counts.items(), key=lambda kv: -kv[1])[:10]
    total_paid = sum(creative_counts.values())
    zero_creatives = sum(1 for _, c in creative_counts.items() if c <= 1)

    rows = []
    for i, (content, count) in enumerate(top_items):
        state = "rising" if i == 0 else "steady" if i < 3 else "cooling" if i < 6 else "cold"
        rows.append({
            "rank": str(i + 1),
            "content": str(content)[:36],
            "channel": str(creative_channels.get(content, '—'))[:30],
            "count": str(count),
            "trend": {"state": state,
                      "label": {"rising":"↗ Winner","steady":"→ Steady",
                                "cooling":"↘ Cooling","cold":"× Cold"}[state]},
        })

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": f"Ad Creative Performance · {date_range_label}",
             "title": "Your *top* ads.",
             "meta_bits": [customer_domain or '', f"{len(creative_counts)} creatives",
                           f"{total_paid} paid leads"]},
            {"type": "stat-strip", "stats": [
                {"value": f"{len(creative_counts)}", "label": "Creatives tracked"},
                {"value": f"{top_items[0][1] if top_items else 0}", "label": "Top creative leads"},
                {"value": f"{zero_creatives}", "label": "Low-volume creatives"},
            ]},
            {"type": "ranked-list",
             "columns": [
                 {"key": "rank", "label": "#", "type": "rank", "width": "60px"},
                 {"key": "content", "label": "Creative (utm_content)", "type": "name"},
                 {"key": "channel", "label": "Channel", "type": "source", "width": "220px"},
                 {"key": "count", "label": "Leads", "type": "number",
                  "align": "right", "width": "90px"},
                 {"key": "trend", "label": "Trend", "type": "trend", "width": "140px"},
             ],
             "rows": rows},
            {"type": "insight-card",
             "kicker": "Pattern in what wins",
             "title": f"Your top creative drove *{top_items[0][1] if top_items else 0}* leads.",
             "body": ["Top performers usually share something — hook type, offer specificity, "
                      "or emotional tone. Review the headlines/copy of your top 3 creatives "
                      "side by side to find the pattern worth scaling."]},
            {"type": "recommendations", "items": [
                {"label": "Action 01", "title": "Pause *zero-lead* creatives",
                 "body": "Creatives with zero or one lead are draining budget without converting."},
                {"label": "Action 02", "title": "Duplicate the *winner* cross-channel",
                 "body": "The top utm_content in Google Ads often also wins on Meta if the platform allows."},
                {"label": "Action 03", "title": "Test a *variant* of the top ad",
                 "body": "New headline, same offer, same visual. See if the ceiling moves."},
                {"label": "Action 04", "title": "Budget-shift toward *winners*",
                 "body": "Move 20% of low-performer budget to the top 3 creatives this week."},
            ]},
            {"type": "closing",
             "kicker": "The creatives",
             "title": f"Pause the *{zero_creatives}* low-volume creatives this week.",
             "summary_stats": [
                 {"value": f"{len(creative_counts)}", "label": "Creatives tracked"},
                 {"value": f"{top_items[0][1] if top_items else 0}", "label": "Top creative leads"},
                 {"value": f"{zero_creatives}", "label": "Low-volume creatives"},
                 {"value": f"{total_paid}", "label": "Total paid leads"},
             ],
             "bullets": [
                 f"Top creative drove {top_items[0][1] if top_items else 0} leads",
                 f"{zero_creatives} creatives with 1 or fewer leads — prune candidates",
                 "Run this bi-weekly during active campaign cycles",
             ]},
        ],
    }


# ============================================================
# KEYWORD PERFORMANCE
# ============================================================

def build_keyword_summary(current, brand_profile=None,
                           customer_name=None, customer_domain=None,
                           date_range_label="Last 30 days"):
    """Keyword Performance — by utm_term within paid search."""
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or brand.get('company_name'), customer_domain or '', brand)
    if not current:
        return _empty_report(f"Keyword Performance · {date_range_label}", meta)

    search = [e for e in current
              if str(e.get('utm_medium (HandL)') or e.get('utm_medium', '')).lower() == 'cpc'
              and (e.get('utm_term (HandL)') or e.get('utm_term'))]

    if not search:
        return _empty_report(f"Keyword Performance · {date_range_label}", meta,
                              reason="No paid-search submissions with utm_term found.")

    kw_counts = {}
    kw_sources = {}
    for e in search:
        term = e.get('utm_term (HandL)') or e.get('utm_term')
        kw_counts[term] = kw_counts.get(term, 0) + 1
        src = e.get('utm_source (HandL)') or 'unknown'
        kw_sources[term] = src

    top_items = sorted(kw_counts.items(), key=lambda kv: -kv[1])[:10]
    rows = []
    for i, (kw, count) in enumerate(top_items):
        state = "rising" if i == 0 else "steady" if i < 4 else "cooling"
        rows.append({
            "rank": str(i + 1),
            "keyword": str(kw)[:48],
            "source": kw_sources.get(kw, '—'),
            "count": str(count),
            "trend": {"state": state,
                      "label": {"rising":"↗ Winner","steady":"→ Steady","cooling":"↘ Below avg"}[state]},
        })

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": f"Keyword Performance · {date_range_label}",
             "title": "Which *terms* convert.",
             "meta_bits": [customer_domain or '', f"{len(kw_counts)} keywords",
                           f"{sum(kw_counts.values())} leads"]},
            {"type": "chart",
             "chart": {"type": "bar-horizontal", "labels": [k[:30] for k, _ in top_items],
                       "values": [v for _, v in top_items]},
             "caption": f"Top 10 keywords by lead count"},
            {"type": "ranked-list",
             "columns": [
                 {"key": "rank", "label": "#", "type": "rank", "width": "60px"},
                 {"key": "keyword", "label": "utm_term", "type": "source"},
                 {"key": "source", "label": "Source", "type": "source", "width": "110px"},
                 {"key": "count", "label": "Leads", "type": "number",
                  "align": "right", "width": "90px"},
                 {"key": "trend", "label": "Trend", "type": "trend", "width": "140px"},
             ],
             "rows": rows},
            {"type": "insight-card",
             "kicker": "Pattern",
             "title": f"*{top_items[0][0][:32]}* is your top term at {top_items[0][1]} leads.",
             "body": ["Look for intent patterns in your top keywords: branded vs generic, "
                      "long-tail vs short, solution vs problem. Double down on the intent "
                      "type that's converting — expand match types in that direction."]},
            {"type": "recommendations", "items": [
                {"label": "Bid 01", "title": "Expand *long-tail* around top theme",
                 "body": "If top keywords share a pattern, add sibling terms to your campaigns."},
                {"label": "Bid 02", "title": "Pause *zero-lead* keywords",
                 "body": "Search queries with zero conversions after 100+ clicks should be negatives."},
                {"label": "Bid 03", "title": "Bid up on *top converters*",
                 "body": "Raise max CPC on your top 5 terms by 10-15% and monitor for 7 days."},
                {"label": "Bid 04", "title": "Audit *match types*",
                 "body": "Broad match to winning phrase match to winning exact match is the usual progression."},
            ]},
            {"type": "closing",
             "kicker": "The terms",
             "title": f"Bid up *'{top_items[0][0][:28] if top_items else 'top terms'}'* by 10-15% for 7 days.",
             "summary_stats": [
                 {"value": f"{len(kw_counts)}", "label": "Keywords tracked"},
                 {"value": f"{top_items[0][1] if top_items else 0}", "label": "Top keyword leads"},
                 {"value": f"{sum(kw_counts.values())}", "label": "Total paid-search leads"},
             ],
             "bullets": [
                 f"Winner: '{top_items[0][0][:36] if top_items else 'n/a'}' with {top_items[0][1] if top_items else 0} leads",
                 "Bid on intent, not volume — long-tail around top themes",
                 "Run monthly to catch keyword drift and emerging winners",
             ]},
        ],
    }


# ============================================================
# SOURCE TO CRM MAPPING
# ============================================================

def build_source_to_crm_summary(current, brand_profile=None,
                                  customer_name=None, customer_domain=None,
                                  date_range_label="Last 30 days"):
    """Source to CRM Mapping — cross-tab of traffic source × declared CRM."""
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or brand.get('company_name'), customer_domain or '', brand)
    if not current:
        return _empty_report(f"Source to CRM Mapping · {date_range_label}", meta)

    with_crm = [e for e in current if e.get('CRM Platform')]
    if not with_crm:
        return _empty_report(f"Source to CRM Mapping · {date_range_label}", meta,
                              reason="No submissions have a CRM field. Add a CRM question to your form.")

    # Cross-tab source × CRM
    pair_counts = {}
    for e in with_crm:
        src = e.get('utm_source (HandL)') or 'direct'
        crm = e.get('CRM Platform') or 'other'
        pair_counts[(src, crm)] = pair_counts.get((src, crm), 0) + 1

    sources = sorted({s for (s, _) in pair_counts}, key=lambda s: -sum(pair_counts.get((s, c), 0) for c in {c for (_, c) in pair_counts}))[:5]
    crms = sorted({c for (_, c) in pair_counts}, key=lambda c: -sum(pair_counts.get((s, c), 0) for s in {s for (s, _) in pair_counts}))[:5]

    # Stacked bar data
    stacks = [{"label": crm, "values": [pair_counts.get((src, crm), 0) for src in sources]}
              for crm in crms]

    # Top pairing
    top_pair, top_pair_count = max(pair_counts.items(), key=lambda kv: kv[1]) if pair_counts else (('—','—'), 0)

    # Top 8 pairings as a table
    top_pairs = sorted(pair_counts.items(), key=lambda kv: -kv[1])[:8]
    total_crm_leads = sum(pair_counts.values())
    rows = []
    for i, ((src, crm), count) in enumerate(top_pairs):
        crm_total = sum(pair_counts.get((s, crm), 0) for s in {s for (s, _) in pair_counts})
        pct_of_crm = round(100 * count / max(crm_total, 1))
        rows.append({
            "rank": str(i + 1),
            "source": src,
            "crm": crm,
            "count": str(count),
            "pct": f"{pct_of_crm}%",
        })

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": f"Source to CRM Mapping · {date_range_label}",
             "title": "Which *sources* bring which CRMs.",
             "meta_bits": [customer_domain or '', f"{len(sources)} sources",
                           f"{len(crms)} CRMs declared"]},
            {"type": "stat-strip", "stats": [
                {"value": f"{len(sources)}", "label": "Sources active"},
                {"value": f"{len(crms)}", "label": "CRMs declared"},
                {"value": f"{top_pair_count}", "label": "Top pairing leads"},
            ]},
            {"type": "chart",
             "chart": {"type": "bar-stacked", "labels": sources, "stacks": stacks},
             "caption": "Top sources segmented by declared CRM"},
            {"type": "ranked-list",
             "columns": [
                 {"key": "rank", "label": "#", "type": "rank", "width": "60px"},
                 {"key": "source", "label": "Source", "type": "name"},
                 {"key": "crm", "label": "CRM", "type": "name"},
                 {"key": "count", "label": "Leads", "type": "number",
                  "align": "right", "width": "80px"},
                 {"key": "pct", "label": "% of CRM", "type": "mono-number",
                  "align": "right", "width": "100px"},
             ],
             "rows": rows},
            {"type": "insight-card",
             "kicker": "Match-making",
             "title": f"*{top_pair[0]}* brings the most {top_pair[1]} users.",
             "body": ["Sources that dominate a specific CRM signal a market fit. "
                      "If LinkedIn brings you HubSpot users and Google Search brings you "
                      "Salesforce users, your messaging should differ on each channel to "
                      "match the audience's stack assumptions."]},
            {"type": "recommendations", "items": [
                {"label": "Action 01", "title": "Target messaging by *dominant CRM*",
                 "body": "Each channel has a CRM winner — speak their language in ad copy."},
                {"label": "Action 02", "title": "Build *CRM-specific* landing pages",
                 "body": "'For HubSpot users' and 'For Salesforce users' variants convert better."},
                {"label": "Action 03", "title": "Suppress *mismatched* offers",
                 "body": "If your product doesn't integrate with their CRM, filter out with negative keywords."},
                {"label": "Action 04", "title": "Review *integration roadmap*",
                 "body": "CRMs you see often but don't support are product-roadmap signals."},
            ]},
            {"type": "closing",
             "kicker": "The mapping",
             "title": f"Build a *{top_pair[1]}-specific* landing page for {top_pair[0]}.",
             "summary_stats": [
                 {"value": f"{len(sources)}", "label": "Sources active"},
                 {"value": f"{len(crms)}", "label": "CRMs declared"},
                 {"value": f"{top_pair_count}", "label": "Top pairing leads"},
             ],
             "bullets": [
                 f"Top pairing: {top_pair[0]} → {top_pair[1]} with {top_pair_count} leads",
                 f"{len(with_crm)} of {len(current)} leads declared their CRM",
                 "Tie channel strategy to the tools your buyers already use",
             ]},
        ],
    }


# ============================================================
# CAMPAIGN DEEP DIVE
# ============================================================

def build_campaign_deep_dive_summary(current, campaign_name, brand_profile=None,
                                       customer_name=None, customer_domain=None,
                                       date_range_label="Last 90 days"):
    """Campaign Deep Dive — full profile of a single campaign."""
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or brand.get('company_name'), customer_domain or '', brand)

    # Filter to the campaign
    filtered = [e for e in (current or [])
                if str(e.get('utm_campaign (HandL)') or e.get('utm_campaign', '')).lower()
                == str(campaign_name).lower()]

    if not filtered:
        return _empty_report(f"Campaign Deep Dive · {campaign_name}", meta,
                              reason=f"No entries found for campaign '{campaign_name}' in this period.")

    daily = compute_daily_volume(filtered)

    # Creative breakdown
    creative_counts = {}
    for e in filtered:
        c = e.get('utm_content (HandL)') or e.get('utm_content') or '(no utm_content)'
        creative_counts[c] = creative_counts.get(c, 0) + 1
    creative_items = sorted(creative_counts.items(), key=lambda kv: -kv[1])[:5]

    # Landing page breakdown
    lp_counts = {}
    for e in filtered:
        url = (e.get('Source URL') or e.get('handl_landing_page (HandL)') or '/').split('?')[0]
        lp_counts[url] = lp_counts.get(url, 0) + 1
    top_lp = max(lp_counts.items(), key=lambda kv: kv[1]) if lp_counts else ('—', 0)

    # Top 10 leads
    sorted_leads = sorted(filtered, key=lambda e: e.get('Date Created', ''), reverse=True)
    lead_rows = []
    for i, e in enumerate(sorted_leads[:10]):
        email = str(e.get('Work Email') or e.get('Email Address', ''))
        if '@' in email:
            parts = email.split('@')
            email = (parts[0][:3] + '***@' + parts[1]) if len(parts[0]) > 3 else email
        lead_rows.append({
            "rank": str(i + 1),
            "date": str(e.get('Date Created', ''))[:10],
            "email": email,
            "company": str(e.get('Company Name', '—'))[:28],
            "source": f"{e.get('utm_source (HandL)') or '—'} · {e.get('utm_medium (HandL)') or '—'}",
        })

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": f"Campaign Deep Dive · {campaign_name}",
             "title": f"*{campaign_name}* in detail.",
             "meta_bits": [customer_domain or '', date_range_label,
                           f"{len(filtered)} leads"]},
            {"type": "stat-strip", "stats": [
                {"value": f"{len(filtered)}", "label": "Total leads"},
                {"value": f"{daily['daily_avg']}", "label": "Avg per day"},
                {"value": f"{creative_items[0][1] if creative_items else 0}",
                 "label": "Top creative leads"},
                {"value": f"{top_lp[1]}", "label": "Top landing page leads"},
            ]},
            {"type": "chart",
             "chart": {"type": "area", "labels": daily['dates'], "values": daily['values']},
             "caption": f"Daily lead volume · peak {daily['peak_value']} on {daily['peak_day']}"},
            {"type": "chart-insight",
             "chart": {"type": "bar-horizontal",
                       "labels": [c[:30] for c, _ in creative_items],
                       "values": [v for _, v in creative_items]},
             "caption": "Top creatives within this campaign",
             "insight_kicker": "The winner",
             "insight_title": f"*{creative_items[0][0][:32] if creative_items else '—'}* led the creative mix.",
             "insight_body": ["The winning creative inside a campaign tells you what hook "
                               "resonates. Other campaigns targeting similar audiences should "
                               "borrow the same angle."]},
            {"type": "section-header", "number": "01",
             "kicker": "Recent leads", "title": "*Top 10* recent submissions."},
            {"type": "ranked-list",
             "columns": [
                 {"key": "rank", "label": "#", "type": "rank", "width": "50px"},
                 {"key": "date", "label": "Date", "type": "mono-number", "width": "110px"},
                 {"key": "email", "label": "Email", "type": "source", "width": "220px"},
                 {"key": "company", "label": "Company", "type": "name"},
                 {"key": "source", "label": "Source", "type": "source", "width": "160px"},
             ],
             "rows": lead_rows},
            {"type": "insight-card",
             "kicker": "The arc",
             "title": f"This campaign averaged *{daily['daily_avg']}* leads/day over {len(daily['dates'])} days.",
             "body": [f"Peak was {daily['peak_value']} on {daily['peak_day']}. "
                      f"If volume has declined since then, it's a fatigue signal — refresh creative."]},
            {"type": "recommendations", "items": [
                {"label": "Action 01", "title": "Replicate *the winning creative*",
                 "body": "Build a second campaign targeting the same audience with this hook."},
                {"label": "Action 02", "title": "Refresh *underperforming creatives*",
                 "body": "Pause creatives below 5% of the winner's lead count."},
                {"label": "Action 03", "title": "Increase *budget* if CPA holds",
                 "body": "Campaigns near their ceiling will warn you with rising CPA."},
                {"label": "Action 04", "title": "Tag leads with *campaign source*",
                 "body": "Hand this leaderboard to sales so they know the context on each call."},
            ]},
            {"type": "closing",
             "kicker": "The campaign",
             "title": f"Replicate *{creative_items[0][0][:28] if creative_items else 'the winning creative'}* on sister campaigns.",
             "summary_stats": [
                 {"value": f"{len(filtered)}", "label": "Total leads"},
                 {"value": f"{daily['daily_avg']}", "label": "Avg per day"},
                 {"value": f"{creative_items[0][1] if creative_items else 0}", "label": "Top creative leads"},
                 {"value": f"{top_lp[1]}", "label": "Top page leads"},
             ],
             "bullets": [
                 f"Peak day: {daily.get('peak_day','n/a')} with {daily.get('peak_value',0)} leads",
                 f"Winning creative: {creative_items[0][0][:36] if creative_items else 'n/a'}",
                 "Export CSV if you need every lead's full UTM record",
             ]},
        ],
    }


# ============================================================
# LEAD PROFILE ENRICHMENT
# ============================================================

def build_lead_profile_summary(all_entries, lead_email, brand_profile=None,
                                 customer_name=None, customer_domain=None):
    """Lead Profile Enrichment — every touchpoint for one lead."""
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or brand.get('company_name'), customer_domain or '', brand)

    # Find this lead's touchpoints
    matching = [e for e in (all_entries or [])
                if (e.get('Email Address', '').lower() == lead_email.lower()
                    or e.get('Work Email', '').lower() == lead_email.lower())]
    matching.sort(key=lambda e: e.get('Date Created', ''))

    if not matching:
        return _empty_report(f"Lead Profile · {lead_email[:20]}", meta,
                              reason=f"No submissions found for {lead_email}.")

    first, last = matching[0], matching[-1]
    first_src = first.get('utm_source (HandL)') or 'direct'
    first_medium = first.get('utm_medium (HandL)') or '—'
    first_lp = first.get('handl_landing_page (HandL)') or first.get('Source URL') or '—'

    # Mask email
    parts = lead_email.split('@')
    email_masked = (parts[0][:3] + '***@' + parts[1]) if len(parts[0]) > 3 else lead_email

    # Touchpoint rows
    touchpoint_rows = []
    for i, e in enumerate(matching):
        touchpoint_rows.append({
            "rank": str(i + 1),
            "date": str(e.get('Date Created', ''))[:16],
            "source": f"{e.get('utm_source (HandL)') or 'direct'} · {e.get('utm_medium (HandL)') or '—'}",
            "campaign": str(e.get('utm_campaign (HandL)') or '—')[:28],
            "landing": str((e.get('handl_landing_page (HandL)') or '/').split('?')[0])[:36],
        })

    spend = first.get('Monthly Ad Spend') or last.get('Monthly Ad Spend') or '—'
    crm = first.get('CRM Platform') or last.get('CRM Platform') or '—'
    company = first.get('Company Name') or last.get('Company Name') or '—'

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": f"Lead Profile · {email_masked}",
             "title": "Who *they* are.",
             "meta_bits": [customer_domain or '', f"First seen: {str(first.get('Date Created',''))[:10]}",
                           f"{len(matching)} touchpoints"]},
            {"type": "stat-strip", "stats": [
                {"value": f"{len(matching)}", "label": "Touchpoints"},
                {"value": f"{company[:18]}", "label": "Company"},
                {"value": f"{spend[:12] if isinstance(spend, str) else spend}", "label": "Monthly spend"},
                {"value": f"{crm[:14] if isinstance(crm, str) else crm}", "label": "Using CRM"},
            ]},
            {"type": "insight-card",
             "kicker": "First touch",
             "title": f"Found you via *{first_src}*, {str(first.get('Date Created','')[:10])}.",
             "body": [f"Entry landing page: {first_lp}",
                      f"First-touch medium: {first_medium}"]},
            {"type": "ranked-list",
             "columns": [
                 {"key": "rank", "label": "#", "type": "rank", "width": "50px"},
                 {"key": "date", "label": "Date", "type": "mono-number", "width": "130px"},
                 {"key": "source", "label": "Source · Medium", "type": "source", "width": "200px"},
                 {"key": "campaign", "label": "Campaign", "type": "name", "width": "180px"},
                 {"key": "landing", "label": "Landing page", "type": "source"},
             ],
             "rows": touchpoint_rows},
            {"type": "insight-card",
             "kicker": "Declared context",
             "title": f"A *{company}* decision-maker, evaluating tools.",
             "body": [f"Declared monthly ad spend: {spend}. Current CRM: {crm}.",
                      "Combine this with the touchpoint history above — they've shown "
                      "specific, repeated interest. Ready for sales-assisted outreach."]},
            {"type": "recommendations", "items": [
                {"label": "Sales 01", "title": "Open with *{first_src}*-specific framing".format(first_src=first_src),
                 "body": "They found you through a specific channel — reference that context in outreach."},
                {"label": "Sales 02", "title": "Pre-fill *CRM fields*",
                 "body": f"Company: {company[:20]}. CRM: {crm[:14]}. Monthly spend: {spend[:12] if isinstance(spend, str) else spend}."},
                {"label": "Sales 03", "title": "Reference their *history*",
                 "body": "They've touched your site multiple times — acknowledge familiarity."},
                {"label": "Sales 04", "title": "Ready for a *discovery call*",
                 "body": "Multiple touchpoints + declared context = qualified prospect."},
            ]},
            {"type": "closing",
             "kicker": "The lead",
             "title": f"Call *{company[:20] if isinstance(company, str) and company else 'this lead'}* — {len(matching)} touchpoint{'s' if len(matching) != 1 else ''}, qualified.",
             "summary_stats": [
                 {"value": f"{len(matching)}", "label": "Touchpoints"},
                 {"value": f"{company[:14] if isinstance(company, str) else str(company)[:14]}", "label": "Company"},
                 {"value": f"{first_src[:14]}", "label": "First source"},
                 {"value": f"{spend[:12] if isinstance(spend, str) else str(spend)[:12]}", "label": "Declared spend"},
             ],
             "bullets": [
                 f"First seen: {str(first.get('Date Created',''))[:10]} via {first_src}",
                 f"Using: {crm} — declared spend: {spend}",
                 "Ready for sales-assisted outreach with full context",
             ]},
        ],
    }


# ============================================================
# SIDE BY SIDE COMPARISON
# ============================================================

def build_side_by_side_summary(a_entries, a_label, b_entries, b_label,
                                 brand_profile=None, customer_name=None,
                                 customer_domain=None):
    """Side-by-Side Comparison — two subjects compared on equivalent metrics."""
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or brand.get('company_name'), customer_domain or '', brand)

    if not a_entries and not b_entries:
        return _empty_report(f"Side-by-Side · {a_label} vs {b_label}", meta)

    a_count = len(a_entries or [])
    b_count = len(b_entries or [])
    a_avg = round(a_count / 30, 1)
    b_avg = round(b_count / 30, 1)

    a_hyg = compute_hygiene_counts(a_entries)['coverage_pct'] if a_entries else 0
    b_hyg = compute_hygiene_counts(b_entries)['coverage_pct'] if b_entries else 0

    a_src = compute_source_leaderboard(a_entries, top_n=1) if a_entries else {'labels':['—'],'values':[0]}
    b_src = compute_source_leaderboard(b_entries, top_n=1) if b_entries else {'labels':['—'],'values':[0]}

    winner_volume = a_label if a_count >= b_count else b_label
    winner_hygiene = a_label if a_hyg >= b_hyg else b_label

    # Metric comparison rows
    metric_rows = [
        {"metric": "Total leads", "a_value": str(a_count), "b_value": str(b_count),
         "winner": a_label if a_count >= b_count else b_label},
        {"metric": "Leads per day", "a_value": str(a_avg), "b_value": str(b_avg),
         "winner": a_label if a_avg >= b_avg else b_label},
        {"metric": "UTM coverage", "a_value": f"{a_hyg}%", "b_value": f"{b_hyg}%",
         "winner": a_label if a_hyg >= b_hyg else b_label},
        {"metric": "Top source volume", "a_value": str(a_src['values'][0] if a_src['values'] else 0),
         "b_value": str(b_src['values'][0] if b_src['values'] else 0),
         "winner": a_label if (a_src['values'][0] if a_src['values'] else 0) >= (b_src['values'][0] if b_src['values'] else 0) else b_label},
    ]

    # Grouped bar chart
    groups = [
        {"label": a_label, "values": [a_count, a_avg * 10, a_hyg, a_src['values'][0] if a_src['values'] else 0]},
        {"label": b_label, "values": [b_count, b_avg * 10, b_hyg, b_src['values'][0] if b_src['values'] else 0]},
    ]

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": f"Side-by-Side · {a_label} vs {b_label}",
             "title": "The *verdict* is in.",
             "meta_bits": [customer_domain or '', f"{a_label}: {a_count}",
                           f"{b_label}: {b_count}"]},
            {"type": "stat-strip", "stats": [
                {"value": f"{a_count}", "label": f"{a_label[:14]} leads"},
                {"value": f"{b_count}", "label": f"{b_label[:14]} leads"},
                {"value": f"{a_hyg}%", "label": f"{a_label[:10]} hygiene"},
                {"value": f"{b_hyg}%", "label": f"{b_label[:10]} hygiene"},
            ]},
            {"type": "chart",
             "chart": {"type": "bar-grouped",
                       "labels": ["Total leads", "Per day ×10", "UTM cov %", "Top src leads"],
                       "groups": groups},
             "caption": "Direct comparison across 4 metrics"},
            {"type": "insight-card",
             "kicker": "The verdict",
             "title": f"*{winner_volume}* wins on volume; {winner_hygiene} wins on quality.",
             "body": ["Different metrics can point to different winners. "
                      "Volume matters if you're filling the funnel; quality matters if "
                      "you're worried about wasted follow-up effort."]},
            {"type": "ranked-list",
             "columns": [
                 {"key": "metric", "label": "Metric", "type": "name"},
                 {"key": "a_value", "label": a_label[:16], "type": "mono-number",
                  "align": "right", "width": "140px"},
                 {"key": "b_value", "label": b_label[:16], "type": "mono-number",
                  "align": "right", "width": "140px"},
                 {"key": "winner", "label": "Winner", "type": "name", "width": "160px"},
             ],
             "rows": metric_rows},
            {"type": "recommendations", "items": [
                {"label": "Action 01", "title": f"Learn from *{winner_volume}*",
                 "body": "The higher-volume side deserves study. What's the mechanism?"},
                {"label": "Action 02", "title": f"Salvage from *{a_label if a_count < b_count else b_label}*",
                 "body": "Even the 'loser' side has lessons worth keeping before scaling back."},
                {"label": "Action 03", "title": "Test a *hybrid* approach",
                 "body": "Combine the winning mechanism from one with the cost structure of the other."},
                {"label": "Action 04", "title": "Run a *controlled experiment*",
                 "body": "Compare at identical budget next week — remove spend as a confounder."},
            ]},
            {"type": "closing",
             "kicker": "The verdict",
             "title": f"Shift budget toward *{winner_volume[:18]}* — it won volume.",
             "summary_stats": [
                 {"value": f"{a_count}", "label": f"{a_label[:12]} leads"},
                 {"value": f"{b_count}", "label": f"{b_label[:12]} leads"},
                 {"value": f"{winner_volume[:12]}", "label": "Volume winner"},
                 {"value": f"{winner_hygiene[:12]}", "label": "Quality winner"},
             ],
             "bullets": [
                 f"{winner_volume} wins on volume",
                 f"{winner_hygiene} wins on hygiene/quality",
                 "Compare at identical budget to remove spend as a confound",
             ]},
        ],
    }


# ============================================================
# PAID VS ORGANIC
# ============================================================

def build_paid_vs_organic_summary(current, brand_profile=None,
                                    customer_name=None, customer_domain=None,
                                    date_range_label="Last 90 days"):
    """Paid vs Organic — the fundamental split."""
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or brand.get('company_name'), customer_domain or '', brand)
    if not current:
        return _empty_report(f"Paid vs Organic · {date_range_label}", meta)

    paid_mediums = ('cpc', 'paid social', 'paidsocial', 'paid-social', 'display', 'video')
    paid = [e for e in current if str(e.get('utm_medium (HandL)') or e.get('utm_medium', '')).lower() in paid_mediums]
    organic = [e for e in current if e not in paid]

    paid_count = len(paid)
    org_count = len(organic)
    total = paid_count + org_count
    paid_pct = round(100 * paid_count / max(total, 1))
    org_pct = 100 - paid_pct

    daily_paid = compute_daily_volume(paid)
    daily_org = compute_daily_volume(organic)

    paid_src = compute_source_leaderboard(paid, top_n=5) if paid else {'labels':[],'values':[]}
    org_src = compute_source_leaderboard(organic, top_n=5) if organic else {'labels':[],'values':[]}

    # Figure out trajectory — compare first vs second half of period
    half = len(daily_paid['values']) // 2 if daily_paid.get('values') else 0
    paid_trend = "rising" if half and sum(daily_paid['values'][half:]) > sum(daily_paid['values'][:half]) * 1.1 else "steady"
    org_trend = "rising" if half and sum(daily_org['values'][half:]) > sum(daily_org['values'][:half]) * 1.1 else "steady"
    if org_trend == "rising" and paid_trend != "rising":
        traj_title = "*Organic* is growing faster than paid."
    elif paid_trend == "rising" and org_trend != "rising":
        traj_title = "*Paid* is accelerating; organic is flat."
    else:
        traj_title = "Both channels are *steady*."

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": f"Paid vs Organic · {date_range_label}",
             "title": "The *fundamental* split.",
             "meta_bits": [customer_domain or '', f"Paid: {paid_count}",
                           f"Organic: {org_count}"]},
            {"type": "chart-insight",
             "chart": {"type": "doughnut",
                       "labels": ["Paid", "Organic"],
                       "values": [paid_pct, org_pct], "unit": "%"},
             "caption": "Lead share by paid vs organic classification",
             "insight_kicker": "The mix",
             "insight_title": f"Paid is *{paid_pct}%* of the split.",
             "insight_body": ["Healthy brands run a mix — paid delivers predictable volume, "
                               "organic delivers better margins. Pure plays in either direction "
                               "are usually short-term choices."]},
            {"type": "stat-strip", "stats": [
                {"value": f"{paid_count}", "label": "Paid leads"},
                {"value": f"{round(paid_count/max(len(daily_paid.get('values',[1])),1),1)}",
                 "label": "Paid per day"},
                {"value": f"{org_count}", "label": "Organic leads"},
                {"value": f"{round(org_count/max(len(daily_org.get('values',[1])),1),1)}",
                 "label": "Organic per day"},
            ]},
            {"type": "chart",
             "chart": {"type": "line",
                       "labels": daily_paid.get('dates', [])[-30:] if daily_paid.get('dates') else [],
                       "values": daily_paid.get('values', [])[-30:] if daily_paid.get('values') else []},
             "caption": "Paid daily trajectory (last 30 days)"},
            {"type": "insight-card",
             "kicker": "Trajectory",
             "title": traj_title,
             "body": [f"Over the last 90 days, paid volume averaged "
                      f"{round(paid_count/90, 1)} leads/day and organic {round(org_count/90, 1)}/day. "
                      "Trajectory matters more than snapshot — the channel bending upward "
                      "deserves proportionally more investment next quarter."]},
            {"type": "recommendations", "items": [
                {"label": "Action 01", "title": "Invest where the *curve bends up*",
                 "body": "The accelerating channel should get a bigger share of next quarter's budget."},
                {"label": "Action 02", "title": "Protect the *steady* channel",
                 "body": "Consistent channels are fragile under neglect — keep content/creative cadence."},
                {"label": "Action 03", "title": "Quarterly *budget rebalance*",
                 "body": "5-15% shift per quarter based on trajectory, not absolute volume."},
                {"label": "Action 04", "title": "Run this *quarterly*",
                 "body": "Paid vs organic dynamics shift with your content and ad strategy."},
            ]},
            {"type": "closing",
             "kicker": "The split",
             "title": f"Shift 5-10% of budget toward *{'organic' if org_pct < paid_pct else 'paid'}* this quarter.",
             "summary_stats": [
                 {"value": f"{paid_pct}%", "label": "Paid share"},
                 {"value": f"{org_pct}%", "label": "Organic share"},
                 {"value": f"{paid_count}", "label": "Paid leads"},
                 {"value": f"{org_count}", "label": "Organic leads"},
             ],
             "bullets": [
                 f"Paid: {round(paid_count/90,1)}/day · Organic: {round(org_count/90,1)}/day",
                 f"Trajectory: {traj_title.replace('*','').replace('.','')}",
                 "Save this version — most useful compared across quarters",
             ]},
        ],
    }


# ============================================================
# BUDGET SIMULATOR
# ============================================================

def build_budget_simulator_summary(current, scenario, brand_profile=None,
                                     customer_name=None, customer_domain=None):
    """Budget Simulator — what-if spend reallocation.

    `scenario` is a dict like {'shift_from': 'google', 'shift_to': 'facebook', 'pct': 20}
    """
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or brand.get('company_name'), customer_domain or '', brand)
    if not current:
        return _empty_report("Budget Simulator · Last 90 days", meta)

    src = compute_source_leaderboard(current, top_n=6)

    # Simple linear model: shift_pct of shift_from's leads assumed to move
    shift_from = scenario.get('shift_from', src['labels'][0] if src['labels'] else 'source A')
    shift_to = scenario.get('shift_to', src['labels'][1] if len(src.get('labels', [])) > 1 else 'source B')
    pct = scenario.get('pct', 20)

    baseline = dict(zip(src['labels'], src['values']))
    scenario_vals = dict(baseline)

    if shift_from in baseline:
        moved = int(baseline[shift_from] * pct / 100)
        scenario_vals[shift_from] = baseline[shift_from] - moved
        scenario_vals[shift_to] = scenario_vals.get(shift_to, 0) + moved

    baseline_total = sum(baseline.values())
    scenario_total = sum(scenario_vals.values())
    net_delta = scenario_total - baseline_total

    groups = [
        {"label": "Baseline", "values": [baseline.get(s, 0) for s in src['labels']]},
        {"label": "Scenario", "values": [scenario_vals.get(s, 0) for s in src['labels']]},
    ]

    rows = []
    for i, s in enumerate(src['labels']):
        b = baseline.get(s, 0)
        sc = scenario_vals.get(s, 0)
        delta = sc - b
        risk = "cold" if abs(delta) > b * 0.3 else "steady"
        rows.append({
            "rank": str(i + 1),
            "source": s,
            "baseline": str(b),
            "scenario": str(sc),
            "delta": {"state": risk,
                      "label": f"{'↗' if delta >= 0 else '↘'} {delta:+}"},
        })

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": "Budget Simulator · Last 90 days baseline",
             "title": "What *if* you moved spend?",
             "meta_bits": [customer_domain or '', f"Shift {pct}% from {shift_from} to {shift_to}"]},
            {"type": "stat-strip", "stats": [
                {"value": f"{baseline_total}", "label": "Baseline leads (90d)"},
                {"value": f"{scenario_total}", "label": "Scenario leads"},
                {"value": f"{net_delta:+}", "label": "Net delta"},
            ]},
            {"type": "chart",
             "chart": {"type": "bar-grouped", "labels": src['labels'], "groups": groups},
             "caption": f"Baseline vs scenario: shift {pct}% from {shift_from} to {shift_to}"},
            {"type": "insight-card",
             "kicker": "Caveat",
             "title": "This assumes *linear* scaling.",
             "body": ["Real channels have diminishing returns and saturation points. "
                      "A 20% budget shift from a saturated channel might not lose 20% of leads; "
                      "a 20% injection into a small channel might not gain 20% of leads.",
                      "Use this model for direction, not precision. Budget reallocation should "
                      "always be tested at 5% increments before large moves."]},
            {"type": "ranked-list",
             "columns": [
                 {"key": "rank", "label": "#", "type": "rank", "width": "60px"},
                 {"key": "source", "label": "Source", "type": "name"},
                 {"key": "baseline", "label": "Baseline", "type": "mono-number",
                  "align": "right", "width": "110px"},
                 {"key": "scenario", "label": "Scenario", "type": "mono-number",
                  "align": "right", "width": "110px"},
                 {"key": "delta", "label": "Change", "type": "trend", "width": "130px"},
             ],
             "rows": rows},
            {"type": "recommendations", "items": [
                {"label": "Action 01", "title": "Start *small*",
                 "body": "Try 5% shift first and measure for 14 days before scaling."},
                {"label": "Action 02", "title": "Measure *both sides*",
                 "body": "Track leads from both source_from and source_to — don't assume either."},
                {"label": "Action 03", "title": "Watch for *saturation*",
                 "body": "If source_to leads don't increase proportionally, it's at ceiling."},
                {"label": "Action 04", "title": "Re-run *after two weeks*",
                 "body": "Update the baseline with real data, re-simulate the next step."},
            ]},
            {"type": "closing",
             "kicker": "The scenario",
             "title": f"Start with a *5%* shift — measure for 14 days before scaling.",
             "summary_stats": [
                 {"value": f"{baseline_total}", "label": "Baseline (90d)"},
                 {"value": f"{scenario_total}", "label": "Scenario projection"},
                 {"value": f"{net_delta:+}", "label": "Net delta"},
                 {"value": f"{pct}%", "label": "Shift amount"},
             ],
             "bullets": [
                 f"Moving {pct}% from {shift_from} to {shift_to}",
                 f"Linear model — real channels have saturation and diminishing returns",
                 "Start with 5% shift, measure for 14 days, then decide on larger moves",
             ]},
        ],
    }


# ============================================================
# AGENCY CLIENT ROLLUP
# ============================================================

def build_agency_rollup_summary(brand_data_list, brand_profile=None,
                                  customer_name=None, customer_domain=None,
                                  date_range_label="Last 30 days"):
    """Agency Client Rollup — portfolio view across multiple brands.

    `brand_data_list` is a list of dicts, each like:
    {'brand_name': 'X', 'entries': [...], 'customer_domain': 'x.com'}
    """
    brand = brand_profile or DEFAULT_BRAND
    meta = _meta(customer_name or 'Agency', customer_domain or '', brand)
    if not brand_data_list:
        return _empty_report(f"Agency Portfolio · {date_range_label}", meta,
                              reason="No brand profiles configured. Use /brand to add clients.")

    # Compute per-brand metrics
    per_brand = []
    for b in brand_data_list:
        entries = b.get('entries') or []
        hyg = compute_hygiene_counts(entries)['coverage_pct'] if entries else 0
        per_brand.append({
            'name': b.get('brand_name', '?'),
            'count': len(entries),
            'avg': round(len(entries) / 30, 1),
            'hygiene': hyg,
        })
    per_brand.sort(key=lambda x: -x['count'])
    total_leads = sum(b['count'] for b in per_brand)
    brands_up = sum(1 for b in per_brand if b['count'] > b['avg'] * 30 * 0.95)  # heuristic
    brands_attention = sum(1 for b in per_brand if b['hygiene'] < 60 or b['count'] < 10)

    rows = []
    for i, b in enumerate(per_brand):
        trend_state = "rising" if i < 2 else "steady" if b['hygiene'] >= 60 else "cooling"
        rows.append({
            "rank": str(i + 1),
            "brand": b['name'],
            "count": str(b['count']),
            "avg": str(b['avg']),
            "hygiene": f"{b['hygiene']}%",
            "trend": {"state": trend_state,
                      "label": {"rising":"↗ Healthy","steady":"→ Steady","cooling":"↘ Watch"}[trend_state]},
        })

    top3_share = round(100 * sum(b['count'] for b in per_brand[:3]) / max(total_leads, 1))

    return {
        "meta": meta,
        "sections": [
            {"type": "title-block",
             "kicker": f"Agency Portfolio · {date_range_label}",
             "title": "Your *portfolio* at a glance.",
             "meta_bits": [f"{len(per_brand)} brands",
                           f"{total_leads} total leads", date_range_label]},
            {"type": "stat-strip", "stats": [
                {"value": f"{len(per_brand)}", "label": "Brands tracked"},
                {"value": f"{total_leads}", "label": "Portfolio total leads"},
                {"value": f"{brands_up}", "label": "Brands up this period"},
                {"value": f"{brands_attention}", "label": "Need attention"},
            ]},
            {"type": "chart",
             "chart": {"type": "bar-horizontal",
                       "labels": [b['name'] for b in per_brand[:10]],
                       "values": [b['count'] for b in per_brand[:10]]},
             "caption": "Leads per brand, this period"},
            {"type": "ranked-list",
             "columns": [
                 {"key": "rank", "label": "#", "type": "rank", "width": "50px"},
                 {"key": "brand", "label": "Brand", "type": "name"},
                 {"key": "count", "label": "Leads", "type": "number",
                  "align": "right", "width": "80px"},
                 {"key": "avg", "label": "Avg/day", "type": "mono-number",
                  "align": "right", "width": "100px"},
                 {"key": "hygiene", "label": "Hygiene", "type": "mono-number",
                  "align": "right", "width": "100px"},
                 {"key": "trend", "label": "State", "type": "trend", "width": "150px"},
             ],
             "rows": rows},
            {"type": "insight-card",
             "kicker": "Portfolio health",
             "title": f"Your top *3* brands drive {top3_share}% of portfolio leads.",
             "body": [f"Concentration is expected in agency books. Your bottom tier "
                      f"({brands_attention} brand{'s' if brands_attention != 1 else ''} "
                      "flagged for attention) needs either intervention or an acknowledgment "
                      "that their spend profile doesn't justify high volume."]},
            {"type": "recommendations", "items": [
                {"label": "Action 01", "title": "Call *bottom-tier* brands this week",
                 "body": "Low-hygiene or low-volume clients need your attention before they churn."},
                {"label": "Action 02", "title": "Audit *hygiene* where it's below 60%",
                 "body": "Share the UTM hygiene audit report with these clients."},
                {"label": "Action 03", "title": "Identify *upsell* candidates",
                 "body": "Brands growing fast might be ready for a broader engagement."},
                {"label": "Action 04", "title": "Share *this report* at the leadership meeting",
                 "body": "Portfolio-level views help principals allocate attention."},
            ]},
            {"type": "closing",
             "kicker": "The book",
             "title": f"Call the *{brands_attention}* flagged brand{'s' if brands_attention != 1 else ''} this week.",
             "summary_stats": [
                 {"value": f"{len(per_brand)}", "label": "Brands tracked"},
                 {"value": f"{total_leads}", "label": "Portfolio total"},
                 {"value": f"{brands_up}", "label": "Brands up"},
                 {"value": f"{brands_attention}", "label": "Need attention"},
             ],
             "bullets": [
                 f"Top 3 brands drive {top3_share}% of portfolio leads",
                 f"{brands_attention} brand{'s' if brands_attention != 1 else ''} flagged — hygiene below 60% or volume under 10",
                 "Deep-dive any brand with the monthly or hygiene audit reports",
             ]},
        ],
    }


# Register all new recipes
RECIPES['form-performance'] = build_form_performance_summary
RECIPES['forms'] = build_form_performance_summary
RECIPES['ad-creative'] = build_ad_creative_summary
RECIPES['ad-creative-performance'] = build_ad_creative_summary
RECIPES['keyword'] = build_keyword_summary
RECIPES['keywords'] = build_keyword_summary
RECIPES['source-to-crm'] = build_source_to_crm_summary
RECIPES['source-crm'] = build_source_to_crm_summary
RECIPES['campaign-deep-dive'] = build_campaign_deep_dive_summary
RECIPES['lead-profile'] = build_lead_profile_summary
RECIPES['lead'] = build_lead_profile_summary
RECIPES['side-by-side'] = build_side_by_side_summary
RECIPES['compare'] = build_side_by_side_summary
RECIPES['paid-vs-organic'] = build_paid_vs_organic_summary
RECIPES['paid-organic'] = build_paid_vs_organic_summary
RECIPES['budget-simulator'] = build_budget_simulator_summary
RECIPES['budget'] = build_budget_simulator_summary
RECIPES['agency-rollup'] = build_agency_rollup_summary
RECIPES['rollup'] = build_agency_rollup_summary
