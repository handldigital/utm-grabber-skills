"""
Demo data — synthetic UTM Grabber form submissions for demo mode.

When a user picks "See a sample report (no setup needed)" from the welcome
flow, Claude calls `get_demo_current()` / `get_demo_prior()` from this module
instead of hitting MCP. Produces 300+ realistic entries so demo reports look
full-quality (not like a canned 5-row screenshot).

Generation is deterministic (seeded by date hash) and disk-cached — cycling
through multiple demo report types in one session regenerates the same entries
once, then reuses them.

The data mimics the MCP `get_entries` response shape — same field names,
same UTM conventions — so demo entries can flow through the same recipes
as real data.
"""
import json
import os
import random
import tempfile
import datetime as _dt

_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'utm-grabber-demo-cache')


def _cached(tag, start_date, days, base_per_day):
    """Return cached entries for this (tag, start, days) or generate + cache."""
    fname = f"demo_{tag}_{start_date.isoformat()}_{days}d_{base_per_day}.json"
    path = os.path.join(_CACHE_DIR, fname)
    try:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError):
        pass
    entries = _generate_period(start_date, days, base_per_day=base_per_day)
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(entries, f)
    except OSError:
        pass
    return entries


_SOURCES = [
    ('google', 'cpc',        ['brand_search', 'generic_search', 'competitor_search', 'remarketing']),
    ('facebook', 'paidsocial', ['retargeting_q2', 'lookalike_prospecting', 'spring_sale']),
    ('linkedin', 'cpc',      ['enterprise_awareness', 'demo_request_ic', 'webinar_signup']),
    ('bing', 'cpc',          ['brand_search', 'generic_search']),
    ('google', 'organic',    [None]),
    ('linkedin', 'organic',  [None]),
    (None, 'referral',       [None]),
    (None, 'direct',         [None]),
    ('newsletter', 'email',  ['weekly_digest', 'product_announcement']),
    ('youtube', 'video',     ['product_walkthrough']),
]

_LANDING_PAGES = [
    '/attribution-software',
    '/wordpress-utm-tracking',
    '/features',
    '/pricing',
    '/blog/utm-best-practices',
    '/blog/attribution-errors',
    '/',
    '/compare-utmgrabber-vs-hubspot',
]

_COMPANIES = [
    'Acme Marketing', 'BlueSky Digital', 'Crescent Agency', 'Delta Growth',
    'Element Partners', 'Foxtrot Media', 'Garden Labs', 'Harbor Group',
    'Indigo Strategies', 'Juniper Consulting', 'Kestrel Digital', 'Lattice Agency',
    'Meridian Marketing', 'Northpoint Media', 'Oakridge Group', 'Prairie Agency',
    'Quartz Digital', 'Ridgeline Partners', 'Sage Agency', 'Terrace Media',
]

_CRMS = [
    'Salesforce', 'HubSpot', 'Pipedrive', 'Zoho', 'ActiveCampaign',
    'Salesforce', 'HubSpot', 'HubSpot', 'Pipedrive', 'None',  # weighted
]

_SPENDS = [
    '<$1,000/mo', '$1,000-$5,000/mo', '$5,000-$25,000/mo',
    '$25,000-$100,000/mo', '$100,000+/mo',
    '$5,000-$25,000/mo', '$25,000-$100,000/mo',  # weighted mid-to-high
]

_TIMEFRAMES = [
    'This week', 'This month', 'Next 30 days', 'Next 60 days',
    'Next quarter', 'Exploring options',
]


def _build_entry(i, date, source, medium, campaign, is_new=False):
    """Build a single synthetic entry in MCP-style field shape."""
    company = random.choice(_COMPANIES)
    landing = random.choice(_LANDING_PAGES)
    first = random.choice(['alex', 'jordan', 'sam', 'taylor', 'casey', 'morgan', 'riley', 'drew', 'pat', 'robin', 'avery', 'cameron'])
    last = random.choice(['chen', 'rivera', 'patel', 'oconnor', 'kim', 'nelson', 'brooks', 'hayes', 'cole', 'diaz', 'singh', 'ford'])
    email = f"{first}.{last}@{company.lower().replace(' ', '')}.com"
    entry = {
        'Date Created': date.isoformat() + 'Z',
        'Form ID': str(random.choice([3, 3, 3, 4, 7])),  # mostly form 3
        'First Name': first.capitalize(),
        'Last Name': last.capitalize(),
        'Work Email': email,
        'Email Address': email,
        'Company Name': company,
        'CRM Platform': random.choice(_CRMS) if random.random() > 0.15 else '',
        'Monthly Ad Spend': random.choice(_SPENDS) if random.random() > 0.2 else '',
        'Desired Timeframe': random.choice(_TIMEFRAMES) if random.random() > 0.25 else '',
        'Source URL': f'https://demo1.utmgrabber.com{landing}',
        'utm_source (HandL)': source if random.random() > 0.1 else '',  # 10% dropout
        'utm_medium (HandL)': medium if random.random() > 0.08 else '',
        'utm_campaign (HandL)': campaign if campaign and random.random() > 0.15 else '',
        'utm_content (HandL)': random.choice(['hero_cta', 'nav_signup', 'footer_cta', 'blog_cta', '']),
        'utm_term (HandL)': random.choice(['wordpress attribution', 'utm tracking', 'form analytics', '']) if medium == 'cpc' else '',
        'handl_landing_page (HandL)': f'https://demo1.utmgrabber.com{landing}',
    }
    if is_new:
        entry['gclid (HandL)'] = 'EAIaIQobChMI' + ''.join(random.choices('abcdef0123456789', k=20)) if source == 'google' else ''
    return entry


def _generate_period(start_date, days, base_per_day=16):
    """Generate entries across a period with realistic variance + weekly dips."""
    random.seed(hash(start_date.isoformat()) & 0xFFFF)
    entries = []
    idx = 0
    for d in range(days):
        date = start_date + _dt.timedelta(days=d)
        # Weekly seasonality: Sat/Sun get ~40% of weekday volume
        weekday = date.weekday()
        multiplier = 0.4 if weekday >= 5 else 1.0
        # Daily variance ±25%
        daily_count = int(base_per_day * multiplier * random.uniform(0.75, 1.25))
        for _ in range(daily_count):
            source, medium, campaigns = random.choice(_SOURCES)
            campaign = random.choice(campaigns)
            hour = random.randint(7, 21)
            minute = random.randint(0, 59)
            ts = _dt.datetime(date.year, date.month, date.day, hour, minute)
            entries.append(_build_entry(idx, ts, source, medium, campaign))
            idx += 1
    return entries


def get_demo_current():
    """Return ~490 synthetic entries for the 'current' 30-day period."""
    end = _dt.date(2026, 4, 20)
    start = end - _dt.timedelta(days=29)
    return _cached('current', start, 30, 16)


def get_demo_prior():
    """Return ~478 synthetic entries for the 'prior' 30-day period."""
    end = _dt.date(2026, 3, 21)
    start = end - _dt.timedelta(days=29)
    return _cached('prior', start, 30, 15)


if __name__ == '__main__':
    cur = get_demo_current()
    pri = get_demo_prior()
    print(f"Demo current: {len(cur)} entries")
    print(f"Demo prior:   {len(pri)} entries")
    print(f"Sample entry: {cur[0]}")
