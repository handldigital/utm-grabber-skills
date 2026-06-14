"""
Schema validator for UTM Grabber Attribution Reports.

Loads a summary dict (or JSON file) and verifies it has all the fields the
template expects. Use this BEFORE injecting into the template to catch
missing fields, wrong shapes, and type mismatches.

Usage:
    from validate_schema import validate_summary
    errors = validate_summary(summary_dict)
    if errors:
        for e in errors: print(f"  ! {e}")
    else:
        # Safe to inject
        ...

Returns a list of human-readable error messages. Empty list = valid.
"""
import json

SECTION_TYPES = {
    'title-block', 'stat-strip', 'section-header', 'hero-number',
    'chart', 'chart-insight', 'ranked-list', 'recommendations',
    'insight-card', 'closing'
}

CHART_TYPES = {'doughnut', 'bar-horizontal', 'bar-vertical',
               'bar-stacked', 'bar-grouped', 'line', 'area'}

DELTA_DIRECTIONS = {'up', 'down', 'flat'}

TREND_STATES = {'steady', 'rising', 'cooling', 'cold'}


def _require(d, key, ctx):
    if key not in d:
        return [f"{ctx}: missing required field '{key}'"]
    return []


def _require_list(d, key, ctx):
    errs = _require(d, key, ctx)
    if errs:
        return errs
    if not isinstance(d[key], list):
        return [f"{ctx}: '{key}' must be a list, got {type(d[key]).__name__}"]
    return []


def _validate_title_block(s, ctx):
    errs = []
    errs += _require(s, 'title', ctx)
    if 'title' in s and '*' in s['title']:
        # Check italic-accent rule: exactly one *word* pair
        asterisks = s['title'].count('*')
        if asterisks != 2:
            errs.append(f"{ctx}: title should have exactly one *italic accent* pair (found {asterisks} asterisks)")
    return errs


def _validate_stat_strip(s, ctx):
    errs = _require_list(s, 'stats', ctx)
    if errs:
        return errs
    if len(s['stats']) < 2 or len(s['stats']) > 4:
        errs.append(f"{ctx}: stats must have 2-4 items, got {len(s['stats'])}")
    for i, stat in enumerate(s['stats']):
        sc = f"{ctx}.stats[{i}]"
        errs += _require(stat, 'value', sc)
        errs += _require(stat, 'label', sc)
        if 'delta_direction' in stat and stat['delta_direction'] not in DELTA_DIRECTIONS:
            errs.append(f"{sc}: delta_direction must be one of {DELTA_DIRECTIONS}, got {stat['delta_direction']!r}")
    return errs


def _validate_hero_number(s, ctx):
    errs = []
    errs += _require(s, 'value', ctx)
    return errs


def _validate_chart_data(chart, ctx):
    errs = []
    errs += _require(chart, 'type', ctx)
    if 'type' in chart:
        t = chart['type']
        if t not in CHART_TYPES:
            errs.append(f"{ctx}: chart type '{t}' not one of {CHART_TYPES}")
            return errs
        if t in ('doughnut', 'bar-horizontal', 'bar-vertical', 'line', 'area'):
            errs += _require_list(chart, 'labels', ctx)
            errs += _require_list(chart, 'values', ctx)
            if 'labels' in chart and 'values' in chart and \
               isinstance(chart['labels'], list) and isinstance(chart['values'], list) and \
               len(chart['labels']) != len(chart['values']):
                errs.append(f"{ctx}: labels ({len(chart['labels'])}) and values ({len(chart['values'])}) length mismatch")
        elif t == 'bar-stacked':
            errs += _require_list(chart, 'labels', ctx)
            errs += _require_list(chart, 'stacks', ctx)
        elif t == 'bar-grouped':
            errs += _require_list(chart, 'labels', ctx)
            errs += _require_list(chart, 'groups', ctx)
    return errs


def _validate_chart(s, ctx):
    errs = _require(s, 'chart', ctx)
    if not errs:
        errs += _validate_chart_data(s['chart'], f"{ctx}.chart")
    return errs


def _validate_chart_insight(s, ctx):
    errs = _validate_chart(s, ctx)
    # insight_title & insight_body are strongly recommended but not strictly required
    # (template handles missing gracefully)
    if 'insight_title' in s and '*' in s['insight_title']:
        if s['insight_title'].count('*') != 2:
            errs.append(f"{ctx}: insight_title should have exactly one *italic accent* pair")
    return errs


def _validate_ranked_list(s, ctx):
    errs = _require_list(s, 'columns', ctx)
    errs += _require_list(s, 'rows', ctx)
    if errs:
        return errs
    col_keys = [c.get('key') for c in s['columns']]
    for i, c in enumerate(s['columns']):
        cc = f"{ctx}.columns[{i}]"
        errs += _require(c, 'key', cc)
        errs += _require(c, 'label', cc)
    for i, row in enumerate(s['rows'][:5]):  # Sample first 5 rows
        rc = f"{ctx}.rows[{i}]"
        if not isinstance(row, dict):
            errs.append(f"{rc}: row must be a dict")
            continue
        for ck in col_keys:
            if ck and ck not in row:
                errs.append(f"{rc}: missing key '{ck}' (required by columns)")
    return errs


def _validate_recommendations(s, ctx):
    errs = _require_list(s, 'items', ctx)
    if errs:
        return errs
    if len(s['items']) != 4:
        errs.append(f"{ctx}: items must have exactly 4 entries (renders a 2x2 grid), got {len(s['items'])}")
    for i, item in enumerate(s['items']):
        ic = f"{ctx}.items[{i}]"
        errs += _require(item, 'title', ic)
        errs += _require(item, 'body', ic)
    return errs


def _validate_insight_card(s, ctx):
    errs = []
    if 'title' in s and '*' in s['title']:
        if s['title'].count('*') != 2:
            errs.append(f"{ctx}: title should have exactly one *italic accent* pair")
    return errs


def _validate_section_header(s, ctx):
    return _require(s, 'title', ctx)


def _validate_closing(s, ctx):
    return []  # all fields optional


VALIDATORS = {
    'title-block': _validate_title_block,
    'stat-strip': _validate_stat_strip,
    'section-header': _validate_section_header,
    'hero-number': _validate_hero_number,
    'chart': _validate_chart,
    'chart-insight': _validate_chart_insight,
    'ranked-list': _validate_ranked_list,
    'recommendations': _validate_recommendations,
    'insight-card': _validate_insight_card,
    'closing': _validate_closing,
}


def validate_meta(meta):
    errs = []
    ctx = 'meta'
    if not isinstance(meta, dict):
        return [f"{ctx}: must be a dict"]
    errs += _require(meta, 'customer_domain', ctx)
    errs += _require(meta, 'skill_version', ctx)
    if 'brand_profile' in meta:
        bp = meta['brand_profile']
        errs += _require(bp, 'company_name', 'meta.brand_profile')
        if 'colors' in bp:
            for k in ('primary', 'accent', 'ink', 'muted', 'surface'):
                errs += _require(bp['colors'], k, f'meta.brand_profile.colors')
    return errs


def validate_summary(summary):
    """
    Validate a full summary dict against the template's expected schema.
    Returns a list of human-readable error strings. Empty list = valid.
    """
    errs = []
    if not isinstance(summary, dict):
        return ["summary must be a dict"]

    # Meta
    if 'meta' not in summary:
        errs.append("summary: missing required field 'meta'")
    else:
        errs += validate_meta(summary['meta'])

    # Sections
    errs += _require_list(summary, 'sections', 'summary')
    if 'sections' not in summary or not isinstance(summary.get('sections'), list):
        return errs

    section_types_seen = []
    for i, sec in enumerate(summary['sections']):
        ctx = f"sections[{i}]"
        if not isinstance(sec, dict):
            errs.append(f"{ctx}: must be a dict")
            continue
        errs += _require(sec, 'type', ctx)
        stype = sec.get('type')
        if stype and stype not in SECTION_TYPES:
            errs.append(f"{ctx}: type '{stype}' not in allowed set {SECTION_TYPES}")
            continue
        section_types_seen.append(stype)
        validator = VALIDATORS.get(stype)
        if validator:
            errs += validator(sec, f"{ctx}({stype})")

    # Structural best practices
    if section_types_seen and section_types_seen[0] != 'title-block':
        errs.append("structural: first section should be 'title-block'")
    if section_types_seen and section_types_seen[-1] != 'closing':
        errs.append("structural: last section should be 'closing'")

    return errs


def validate_summary_file(path):
    with open(path) as f:
        summary = json.load(f)
    return validate_summary(summary)


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        print("Usage: python validate_schema.py <summary.json>")
        sys.exit(1)

    errors = validate_summary_file(sys.argv[1])
    if not errors:
        print("✓ Schema valid")
        sys.exit(0)
    else:
        print(f"✗ Found {len(errors)} issue(s):")
        for e in errors:
            print(f"  • {e}")
        sys.exit(1)
