"""
MCP retry helpers.

When MCP calls fail (5xx, timeout, truncation, unexpected empty), the right
behavior is: try once more with conservative params, then fall back to the
user — don't loop silently.

Usage pattern in conversation (Claude's flow):

    try:
        entries = <call MCP get_entries with limit=1500>
    except Exception as first_err:
        # Retry once with smaller limit
        try:
            entries = <call MCP get_entries with limit=750>
        except Exception as second_err:
            # Both failed — tell the user in their language
            <respond: "your site didn't respond just now — want me to try
             one more time, or pause and come back to it?">
            # Wait for user confirmation before third attempt

This module provides the constants + helpers that make that pattern
consistent across recipes.
"""


# How many entries to ask for on first try
PRIMARY_LIMIT = 1500

# Retry limit when first try fails/truncates
RETRY_LIMIT = 750

# After how long to consider a call "timed out" conceptually (MCP itself
# doesn't expose timeouts, this is a signal Claude uses to interpret behavior)
CONCERNING_WAIT_SECONDS = 30


def is_suspicious_empty(entries, expected_min=5):
    """
    Return True if the entries list is small enough to be suspicious —
    e.g. 0 entries returned when we'd expect more. Signals a retry is warranted.

    Calibrate `expected_min` to context: for a 30-day monthly review on an
    established site, expect at least 5 entries. For a 7-day query on a new
    site, 1-2 is fine.
    """
    if entries is None:
        return True
    if not isinstance(entries, list):
        return True
    return len(entries) < expected_min


def is_truncated(response_dict):
    """
    Check an MCP response dict for signs of truncation (e.g. the response
    hits the limit exactly, suggesting more data exists).

    MCP sometimes reports truncation via a `next_cursor` or `has_more` field.
    If those aren't present, hitting the limit exactly (e.g. 1500 entries)
    is a strong heuristic that there's more data on the server.
    """
    if not isinstance(response_dict, dict):
        return False
    if response_dict.get('has_more'):
        return True
    if response_dict.get('next_cursor'):
        return True
    entries = response_dict.get('entries', [])
    if isinstance(entries, list) and len(entries) >= PRIMARY_LIMIT:
        return True
    return False


# Friendly user-facing strings for failure cases
FRIENDLY_RETRY_PROMPT = (
    "Your site didn't respond on that one. Want me to try once more, "
    "or pause and come back to it?"
)

FRIENDLY_PERMANENT_FAIL = (
    "I can't reach your site right now. Try again in a few minutes, "
    "or check the UTM Grabber plugin is active in your WordPress admin."
)
