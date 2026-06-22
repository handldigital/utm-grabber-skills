"""
CSV exporter for UTM Grabber entries.

Takes the raw MCP entries list and writes a flat CSV with every useful
attribution and contact field. One row per entry, one column per field.

Usage (from Python):
    from build_csv import export_entries_to_csv
    export_entries_to_csv(entries, '/mnt/user-data/outputs/leads.csv')

Usage (CLI):
    python build_csv.py <entries.json> <output.csv>
"""
import csv
import json
import os
import sys

# Column order matches what a marketer would want to see in Excel:
# who, when, where-from, what-they-told-us, technical-details.
STANDARD_COLUMNS = [
    # Identity
    'Entry ID',
    'Date Created',
    'Email Address',
    'Work Email',
    'First Name',
    'Last Name',
    'Phone Number',
    'Company Name',
    'Job Title',
    'Website',
    # Attribution — HandL UTM fields (the important ones)
    'utm_source (HandL)',
    'utm_medium (HandL)',
    'utm_campaign (HandL)',
    'utm_content (HandL)',
    'utm_term (HandL)',
    'traffic_source (HandL)',
    'traffic_source (first touch, HandL)',
    # Click IDs
    'gclid',
    'fbclid',
    'msclkid',
    # Page context
    'Source URL',
    'handl_landing_page (HandL)',
    'handl_original_ref (HandL)',
    # Lead-quality form fields (if present)
    'Monthly Ad Spend',
    'Primary Goal',
    'CRM Platform',
    'Desired Timeframe',
    'Current Setup Notes',
    # Technical
    'IP Address',
    'User Agent',
]


def _get(entry, key):
    """Robust field accessor — returns empty string for missing."""
    v = entry.get(key, '')
    return '' if v is None else str(v)


def export_entries_to_csv(entries, output_path, columns=None):
    """
    Write entries to CSV at output_path. Returns the path.

    If `columns` is None, uses STANDARD_COLUMNS but only includes those
    that appear in at least one entry (keeps the CSV clean).
    """
    if not entries:
        raise ValueError("No entries to export — CSV would be empty.")

    if columns is None:
        all_keys = set()
        for e in entries:
            all_keys.update(e.keys())
        columns = [c for c in STANDARD_COLUMNS if c in all_keys]
        # Append any entry keys we didn't anticipate (so nothing is lost)
        extras = sorted(all_keys - set(STANDARD_COLUMNS))
        # Exclude keys that start with whitespace or are very long (internal noise)
        extras = [k for k in extras if k and not k.startswith('_') and len(k) < 60]
        columns.extend(extras)

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for entry in entries:
            writer.writerow({c: _get(entry, c) for c in columns})

    return output_path


def export_entries_to_csv_from_mcp_result(mcp_result_path, output_path, columns=None):
    """Load entries from an MCP result file and export to CSV."""
    # Use the same loader as the reports pipeline
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from helpers import load_entries_from_mcp_result
    entries = load_entries_from_mcp_result(mcp_result_path)
    return export_entries_to_csv(entries, output_path, columns)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python build_csv.py <entries.json> <output.csv>")
        sys.exit(1)
    path = export_entries_to_csv_from_mcp_result(sys.argv[1], sys.argv[2])
    print(f"✓ Wrote CSV: {path}")
