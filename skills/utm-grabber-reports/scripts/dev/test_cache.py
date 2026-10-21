"""Dev tool: check the disk cache keeps every page of a paginated get_entries pull.

    python3 scripts/dev/test_cache.py

Writes two fake get_entries pages (2 entries each) in the MCP text format to a
temp folder, caches the window with save_cached_entries(page_files, ...), then
reads it back with load_cached_superset: the whole window must return 4 entries
and a page-2-only date range must return 2. Also checks the default cache folder
can be created here (it isn't /home/claude outside claude.ai). No cache files are
written to the real cache folder.
Exit code 1 when any check fails.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import helpers

DEFAULT_DIR = helpers.CACHE_DIR  # /home/claude/... on claude.ai, the temp folder elsewhere
try:
    os.makedirs(DEFAULT_DIR, exist_ok=True)
    default_ok = os.access(DEFAULT_DIR, os.W_OK)
except OSError:
    default_ok = False

tmp = tempfile.mkdtemp()
helpers.CACHE_DIR = os.path.join(tmp, "cache")
helpers.INDEX_PATH = os.path.join(helpers.CACHE_DIR, "_index.json")  # bound at import
os.makedirs(helpers.CACHE_DIR, exist_ok=True)

LABELS = {"1": {"3": "utm_source (HandL)"}}


def page(n, entries):
    path = os.path.join(tmp, f"p{n}.txt")
    with open(path, "w") as f:
        f.write(f"Field labels: {json.dumps(LABELS)}\n"
                f"Page {n} of 2 (2 per page, 4 total matching entries).\n"
                f"Entries: {json.dumps(entries)}\n")
    return path


pages = [
    page(1, [{"form_id": "1", "date_created": "2026-10-01 09:00:00", "3": "google"},
             {"form_id": "1", "date_created": "2026-10-02 09:00:00", "3": "linkedin"}]),
    page(2, [{"form_id": "1", "date_created": "2026-10-08 09:00:00", "3": "google"},
             {"form_id": "1", "date_created": "2026-10-09 09:00:00", "3": "meta"}]),
]
window = ("acme.com", [1], "2026-10-01", "2026-10-10")

helpers.save_cached_entries(pages, *window)
whole = helpers.load_cached_superset(*window) or []
subset = helpers.load_cached_superset("acme.com", [1], "2026-10-08", "2026-10-10") or []
single = helpers.save_cached_entries(pages[0], "acme.com", [1], "2026-10-01", "2026-10-02")

checks = [
    ("default cache folder is writable on this machine", default_ok, DEFAULT_DIR),
    ("whole window returns all pages", len(whole) == 4, len(whole)),
    ("page-2 date range returns page 2", len(subset) == 2, len(subset)),
    ("cached entries keep named keys", all("utm_source (HandL)" in e for e in whole), sorted(whole[0]) if whole else None),
    ("single path still accepted", os.path.exists(single), single),
]
failed = 0
for name, ok, got in checks:
    print(f"{'PASS' if ok else 'FAIL'}  {name}  ({got})")
    failed += not ok
sys.exit(1 if failed else 0)
