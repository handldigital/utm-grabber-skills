"""
UTM Grabber skill helpers.
Pre-built functions used by every report's transformation pipeline.

USAGE from a report transformation script:
    import sys
    sys.path.insert(0, '/mnt/skills/user/utm-grabber-reports/scripts')
    from helpers import (
        load_entries_from_mcp_result,
        classify_traffic_source,
        compute_hygiene,
        compute_period_delta,
        compute_channel_mix,
        compute_source_leaderboard,
        compute_campaign_leaderboard,
        normalize_url,
        format_delta_pill,
    )
"""

import json
import re
from collections import Counter
from datetime import datetime, timedelta


# ==============================================================
# Loading MCP results
# ==============================================================

def load_entries_from_mcp_result(filepath):
    """
    The MCP's get_entries returns text with prose + a JSON array. This extracts
    the JSON array and returns a list of entry dicts.
    """
    with open(filepath) as f:
        raw = json.load(f)

    # MCP wraps the result in a text block
    if isinstance(raw, list) and raw and 'text' in raw[0]:
        text = raw[0]['text']
    else:
        text = raw

    # Find the JSON array within the text
    m = re.search(r'\[\s*\{', text)
    if not m:
        return []
    json_start = m.start()
    json_text = text[json_start:]
    return json.loads(json_text)


def get_field(entry, *candidates, default=''):
    """
    MCP entry field names vary slightly. Try multiple keys, return first match.
    Strips whitespace and lowercases on return.
    """
    for key in candidates:
        if key in entry and entry[key] not in (None, ''):
            return str(entry[key]).strip()
    return default


# ==============================================================
# Traffic source classification
# ==============================================================

PAID_MEDIUMS = {'cpc', 'ppc', 'paid', 'paid_search', 'paid_social', 'paidsocial'}
SOCIAL_MEDIUMS = {'social', 'organic_social'}
EMAIL_MEDIUMS = {'email', 'newsletter', 'e-mail'}
REFERRAL_MEDIUMS = {'referral', 'partner'}
SEARCH_ENGINES = {'google', 'bing', 'duckduckgo', 'yahoo', 'ecosia', 'brave'}


def classify_traffic_source(entry):
    """
    Given an entry dict, return one of: Paid, Organic, Social, Referral, Direct.

    Uses the MCP's own classification when available (traffic_source field);
    falls back to rules based on utm_medium, click IDs, and referrer.
    """
    # Prefer MCP's own classification
    classified = get_field(entry, 'traffic_source (HandL)', 'traffic_source', default='').lower()
    if classified in ('paid', 'organic', 'social', 'referral', 'direct'):
        return classified.capitalize()

    medium = get_field(entry, 'utm_medium (HandL)', 'utm_medium').lower()
    source = get_field(entry, 'utm_source (HandL)', 'utm_source').lower()
    gclid = get_field(entry, 'gclid (HandL)', 'gclid')
    fbclid = get_field(entry, 'fbclid (HandL)', 'fbclid')
    msclkid = get_field(entry, 'msclkid (HandL)', 'msclkid')
    referrer = get_field(entry, 'referrer (first touch, HandL)', 'referrer')

    # Click IDs = paid
    if gclid or msclkid:
        return 'Paid'
    if fbclid and medium in PAID_MEDIUMS:
        return 'Paid'
    if fbclid:
        return 'Social'

    # Medium-based
    if medium in PAID_MEDIUMS:
        return 'Paid'
    if medium in SOCIAL_MEDIUMS:
        return 'Social'
    if medium in EMAIL_MEDIUMS:
        return 'Referral'
    if medium in REFERRAL_MEDIUMS:
        return 'Referral'

    # Source-based fallback
    if source in SEARCH_ENGINES:
        return 'Organic'

    # Referrer-based fallback
    if referrer:
        return 'Referral'

    return 'Direct'


# ==============================================================
# UTM hygiene scoring
# ==============================================================

def compute_hygiene(entry):
    """
    Returns one of: 'fully_tagged', 'partially_tagged', 'untagged_paid',
                    'untagged_referrer', 'direct'
    """
    source = get_field(entry, 'utm_source (HandL)', 'utm_source')
    medium = get_field(entry, 'utm_medium (HandL)', 'utm_medium')
    campaign = get_field(entry, 'utm_campaign (HandL)', 'utm_campaign')
    gclid = get_field(entry, 'gclid (HandL)', 'gclid')
    fbclid = get_field(entry, 'fbclid (HandL)', 'fbclid')
    msclkid = get_field(entry, 'msclkid (HandL)', 'msclkid')
    referrer = get_field(entry, 'referrer (first touch, HandL)', 'referrer')

    if source and medium and campaign:
        return 'fully_tagged'
    if source or medium or campaign:
        return 'partially_tagged'
    if gclid or fbclid or msclkid:
        return 'untagged_paid'  # CRITICAL: paid click but no tagging
    if referrer:
        return 'untagged_referrer'
    return 'direct'


def compute_hygiene_counts(entries):
    counts = Counter(compute_hygiene(e) for e in entries)
    total = len(entries)
    return {
        'total': total,
        'fully_tagged': counts.get('fully_tagged', 0),
        'partially_tagged': counts.get('partially_tagged', 0),
        'untagged_paid': counts.get('untagged_paid', 0),
        'untagged_referrer': counts.get('untagged_referrer', 0),
        'direct': counts.get('direct', 0),
        'coverage_pct': round(100 * counts.get('fully_tagged', 0) / total) if total else 0,
    }


# ==============================================================
# Period-over-period deltas
# ==============================================================

def compute_period_delta(current, prior):
    """
    Given two numeric values, return a dict with label/direction ready for the
    template's delta pill.

    direction: 'up', 'down', 'flat', 'neutral'
    label: the human string like '+12% vs last period' or 'no change'
    """
    if prior == 0 and current == 0:
        return {'label': 'no activity either period', 'direction': 'flat'}
    if prior == 0 and current > 0:
        return {'label': f'+{current} (new)', 'direction': 'up'}
    if current == 0 and prior > 0:
        return {'label': '−100% vs last period', 'direction': 'down'}

    delta = current - prior
    pct = (delta / prior) * 100

    if abs(pct) < 3:
        return {'label': 'flat vs last period', 'direction': 'flat'}

    sign = '+' if pct > 0 else '−'
    direction = 'up' if pct > 0 else 'down'
    return {
        'label': f'{sign}{abs(pct):.0f}% vs last period',
        'direction': direction,
    }


def compute_percentage_point_delta(current_pct, prior_pct):
    """For percentage metrics (paid share, UTM coverage, etc.)."""
    delta = current_pct - prior_pct
    if abs(delta) < 2:
        return {'label': 'flat vs last period', 'direction': 'flat'}
    sign = '+' if delta > 0 else '−'
    direction = 'up' if delta > 0 else 'down'
    return {
        'label': f'{sign}{abs(delta):.0f}pt vs last period',
        'direction': direction,
    }


# ==============================================================
# Aggregation helpers
# ==============================================================

def compute_channel_mix(entries):
    """Returns labels + percentages for the channel mix donut chart."""
    classifications = [classify_traffic_source(e) for e in entries]
    counts = Counter(classifications)
    total = len(entries)
    buckets = ['Paid', 'Organic', 'Direct', 'Social', 'Referral']
    return {
        'labels': buckets,
        'values': [round(100 * counts.get(b, 0) / total) if total else 0 for b in buckets],
    }


def compute_source_leaderboard(entries, top_n=8):
    """Returns labels + values for the top N UTM sources by lead count."""
    sources = [get_field(e, 'utm_source (HandL)', 'utm_source').lower() for e in entries]
    sources = [s for s in sources if s]  # drop empty
    counts = Counter(sources).most_common(top_n)
    if not counts:
        return {'labels': [], 'values': []}
    labels, values = zip(*counts)
    return {
        'labels': [l.capitalize() for l in labels],
        'values': list(values),
    }


def compute_campaign_leaderboard(entries, top_n=8):
    """Returns labels + values for the top N UTM campaigns by lead count."""
    campaigns = [get_field(e, 'utm_campaign (HandL)', 'utm_campaign').lower() for e in entries]
    campaigns = [c for c in campaigns if c]
    counts = Counter(campaigns).most_common(top_n)
    if not counts:
        return {'labels': [], 'values': []}
    labels, values = zip(*counts)
    # Clean campaign names: replace underscores with spaces, title case
    cleaned = [l.replace('_', ' ').title() for l in labels]
    return {'labels': cleaned, 'values': list(values)}


def compute_daily_volume(entries):
    """Returns dict with dates (sorted), values, peak, and lowest day."""
    dates = Counter()
    for e in entries:
        date_str = get_field(e, 'Date Created')[:10]  # YYYY-MM-DD
        if date_str:
            dates[date_str] += 1

    if not dates:
        return {'dates': [], 'values': [], 'peak_day': '', 'peak_value': 0,
                'lowest_day': '', 'lowest_value': 0, 'daily_avg': 0}

    sorted_dates = sorted(dates.items())
    date_labels = [d for d, _ in sorted_dates]
    values = [v for _, v in sorted_dates]

    peak_idx = values.index(max(values))
    lowest_idx = values.index(min(values))

    # Format date labels as "Mar 19"
    formatted_labels = [datetime.strptime(d, '%Y-%m-%d').strftime('%b %d') for d in date_labels]

    return {
        'dates': formatted_labels,
        'values': values,
        'peak_day': formatted_labels[peak_idx],
        'peak_value': values[peak_idx],
        'lowest_day': formatted_labels[lowest_idx],
        'lowest_value': values[lowest_idx],
        'daily_avg': round(sum(values) / len(values), 1),
    }


def compute_form_field_distribution(entries, field_name, top_n=5):
    """For form fields like 'Primary Goal', 'CRM Platform', etc."""
    values = [get_field(e, field_name) for e in entries]
    values = [v for v in values if v]
    counts = Counter(values).most_common(top_n)
    if not counts:
        return {'labels': [], 'values': []}
    labels, vals = zip(*counts)
    return {'labels': list(labels), 'values': list(vals)}


# ==============================================================
# URL normalization
# ==============================================================

def normalize_url(url):
    """Strip query strings, fragments, trailing slashes for grouping."""
    if not url:
        return ''
    url = url.split('?')[0].split('#')[0].rstrip('/')
    return url


def group_by_normalized_url(entries, url_field='Source URL'):
    """Returns Counter of normalized URLs."""
    return Counter(
        normalize_url(get_field(e, url_field))
        for e in entries
        if get_field(e, url_field)
    )


# ==============================================================
# Multi-touch (first vs last)
# ==============================================================

def compute_channel_breakdown(entries, top_n_sources=6):
    """
    Returns a sources × mediums matrix for a stacked bar chart.
    Shows which mediums each source uses.
    """
    from collections import defaultdict
    # Count top sources
    source_counts = Counter(
        get_field(e, 'utm_source (HandL)', 'utm_source').lower()
        for e in entries
        if get_field(e, 'utm_source (HandL)', 'utm_source')
    )
    top_sources = [s for s, _ in source_counts.most_common(top_n_sources)]
    if not top_sources:
        return {'sources': [], 'mediums': [], 'matrix': []}

    # Find all mediums used by these sources
    medium_set = set()
    for e in entries:
        s = get_field(e, 'utm_source (HandL)', 'utm_source').lower()
        if s in top_sources:
            m = get_field(e, 'utm_medium (HandL)', 'utm_medium').lower()
            if m:
                medium_set.add(m)
    mediums = sorted(medium_set)
    if not mediums:
        return {'sources': [s.capitalize() for s in top_sources], 'mediums': [], 'matrix': []}

    # Build matrix: source × medium
    matrix = [[0] * len(mediums) for _ in top_sources]
    for e in entries:
        s = get_field(e, 'utm_source (HandL)', 'utm_source').lower()
        m = get_field(e, 'utm_medium (HandL)', 'utm_medium').lower()
        if s in top_sources and m in mediums:
            si = top_sources.index(s)
            mi = mediums.index(m)
            matrix[si][mi] += 1

    return {
        'sources': [s.capitalize() for s in top_sources],
        'mediums': mediums,
        'matrix': matrix,
    }


def compute_multi_touch(entries):
    """Returns first-touch vs last-touch classification counts."""
    categories = ['Paid', 'Organic', 'Social', 'Referral', 'Direct']
    first_counts = Counter()
    last_counts = Counter()

    for e in entries:
        # Last touch = standard classify
        last_counts[classify_traffic_source(e)] += 1

        # First touch = use first-touch field when present
        first_entry = dict(e)
        first_entry['utm_source (HandL)'] = get_field(e, 'utm_source (first touch, HandL)')
        first_entry['utm_medium (HandL)'] = get_field(e, 'utm_medium (first touch, HandL)')
        first_entry['traffic_source (HandL)'] = get_field(e, 'traffic_source (first touch, HandL)')
        first_counts[classify_traffic_source(first_entry)] += 1

    return {
        'categories': categories,
        'first_touch': [first_counts.get(c, 0) for c in categories],
        'last_touch': [last_counts.get(c, 0) for c in categories],
    }


# ==============================================================
# Formatting helpers for the template
# ==============================================================

def format_delta_pill(current, prior, is_percentage=False):
    """Convenience wrapper: picks the right delta function."""
    if is_percentage:
        return compute_percentage_point_delta(current, prior)
    return compute_period_delta(current, prior)


def format_date_range(start_date_str, end_date_str):
    """Given YYYY-MM-DD strings, return 'March 19 – April 18, 2026' style."""
    start = datetime.strptime(start_date_str, '%Y-%m-%d')
    end = datetime.strptime(end_date_str, '%Y-%m-%d')
    if start.year == end.year:
        return f"{start.strftime('%B %-d')} – {end.strftime('%B %-d, %Y')}"
    return f"{start.strftime('%B %-d, %Y')} – {end.strftime('%B %-d, %Y')}"


# =============================================================
# Session-level MCP caching
# =============================================================
# When Claude pulls entries from the MCP during a conversation, cache them on disk.
# Follow-up questions in the same session reuse the cache instead of re-pulling.
# This dramatically speeds up "run the report, then ask a follow-up question" flows.

import hashlib
import os
import time

CACHE_DIR = '/home/claude/cache/mcp-entries'
INDEX_PATH = os.path.join(CACHE_DIR, '_index.json')
CACHE_TTL_SECONDS = 14400  # 4 hours — UTM data isn't live-critical; longer TTL cuts repeat pulls


def _cache_key(customer_domain, form_ids, start_date, end_date):
    """Build a stable cache key for an MCP pull."""
    parts = [
        (customer_domain or '').strip().lower(),
        ','.join(sorted(str(f) for f in (form_ids or []))),
        (start_date or '').strip(),
        (end_date or '').strip(),
    ]
    raw = '|'.join(parts)
    short = hashlib.sha1(raw.encode()).hexdigest()[:12]
    # Human-readable prefix + hash so cache contents are browseable
    readable = (customer_domain or 'unknown').replace('/', '_')
    return f"{readable}_{short}"


def cache_path(customer_domain, form_ids, start_date, end_date):
    """Return the disk path where a given MCP pull would be cached."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{_cache_key(customer_domain, form_ids, start_date, end_date)}.json")


def _load_index():
    """Load the cache index (maps filename → metadata). Returns {} if missing."""
    try:
        with open(INDEX_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_index(index):
    """Persist the cache index. Silently ignores write failures (cache is best-effort)."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(INDEX_PATH, 'w') as f:
            json.dump(index, f, separators=(',', ':'))
    except OSError:
        pass


def load_cached_entries(customer_domain, form_ids, start_date, end_date, max_age_seconds=CACHE_TTL_SECONDS):
    """
    Exact-match cache hit: returns entries if a pull for this exact window exists and is fresh.
    For the Q&A "subset of cached range" case, use `load_cached_superset` instead.
    """
    path = cache_path(customer_domain, form_ids, start_date, end_date)
    if not os.path.exists(path):
        return None
    age = time.time() - os.path.getmtime(path)
    if age > max_age_seconds:
        return None
    try:
        return load_entries_from_mcp_result(path)
    except Exception:
        return None


def load_cached_superset(customer_domain, form_ids, start_date, end_date, max_age_seconds=CACHE_TTL_SECONDS):
    """
    Find any fresh cached pull whose date range ENCLOSES the requested range
    (for the same domain and form_ids), and return its entries filtered to
    the requested window. Returns None if no superset exists.

    Enables the hot Q&A path: after a monthly report pulls 30 days, a follow-up
    "how many LinkedIn leads last week?" reuses the cached 30-day pull instead
    of hitting MCP again.

    Also covers exact-match (cache range == request range), so callers can use
    this helper alone without chaining to `load_cached_entries`.
    """
    index = _load_index()
    if not index:
        return None
    req_forms = sorted(str(f) for f in (form_ids or []))
    req_domain = (customer_domain or '').strip().lower()
    req_start = (start_date or '').strip()
    req_end = (end_date or '').strip()

    candidates = []
    for fname, meta in index.items():
        if (meta.get('domain') or '').strip().lower() != req_domain:
            continue
        if meta.get('form_ids') != req_forms:
            continue
        if not (meta.get('start', '') <= req_start and meta.get('end', '') >= req_end):
            continue
        path = os.path.join(CACHE_DIR, fname)
        if not os.path.exists(path):
            continue
        if time.time() - os.path.getmtime(path) > max_age_seconds:
            continue
        candidates.append((path, meta))

    if not candidates:
        return None

    # Prefer the tightest enclosing range (smallest superset → less to filter)
    candidates.sort(key=lambda c: (c[1].get('end', ''), c[1].get('start', '')))
    path, _meta = candidates[0]
    try:
        entries = load_entries_from_mcp_result(path)
    except Exception:
        return None
    return _filter_entries_by_date(entries, req_start, req_end)


def _filter_entries_by_date(entries, start_date, end_date):
    """Filter entries to those with Date Created ∈ [start_date, end_date] (inclusive, YYYY-MM-DD lex compare)."""
    if not start_date and not end_date:
        return entries
    out = []
    for e in entries:
        raw = e.get('Date Created') or e.get('date_created') or ''
        d = str(raw)[:10]  # YYYY-MM-DD prefix
        if start_date and d < start_date:
            continue
        if end_date and d > end_date:
            continue
        out.append(e)
    return out


def save_cached_entries(raw_mcp_result_path, customer_domain, form_ids, start_date, end_date):
    """
    Copy a fresh MCP result file to the cache directory and register the range
    in the index so `load_cached_superset` can find it later.
    """
    import shutil
    target = cache_path(customer_domain, form_ids, start_date, end_date)
    shutil.copyfile(raw_mcp_result_path, target)

    index = _load_index()
    index[os.path.basename(target)] = {
        'domain': (customer_domain or '').strip().lower(),
        'form_ids': sorted(str(f) for f in (form_ids or [])),
        'start': (start_date or '').strip(),
        'end': (end_date or '').strip(),
    }
    _save_index(index)
    return target


def clear_cache_for_domain(customer_domain):
    """Remove all cached entries for a given domain (e.g. when the user runs `/refresh`)."""
    if not os.path.exists(CACHE_DIR):
        return 0
    prefix = (customer_domain or 'unknown').replace('/', '_')
    removed = 0
    removed_keys = []
    for fname in os.listdir(CACHE_DIR):
        if fname.startswith(prefix + '_') and fname.endswith('.json'):
            os.remove(os.path.join(CACHE_DIR, fname))
            removed += 1
            removed_keys.append(fname)
    # Prune the index as well so stale entries don't linger
    if removed_keys:
        index = _load_index()
        for k in removed_keys:
            index.pop(k, None)
        _save_index(index)
    return removed
