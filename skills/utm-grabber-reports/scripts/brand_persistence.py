"""
Brand profile persistence.

Brand profiles are JSON blobs that describe a customer's visual identity
(company name, logo, color palette) + data source config (domain, form plugin,
form IDs). They need to survive across conversations so /brand isn't re-run
every session.

Storage: a single JSON blob, stringified, saved via memory_user_edits.
The blob is keyed by `profile_id` so agency users can have multiple brands.

Claude uses memory_user_edits (see the tool) to persist these — this module
just provides the serialization helpers.
"""
import json


MEMORY_PREFIX = "[utm-grabber-brand-profiles]"


def serialize_brand_profile(profile_dict):
    """
    Turn a brand profile dict into a short string suitable for memory_user_edits.
    Keeps total under 500 chars (memory_user_edits limit) by compact JSON.
    """
    # Only persist fields Claude actually needs to reload — not icon binaries etc.
    minimal = {
        'profile_id': profile_dict.get('profile_id'),
        'company_name': profile_dict.get('company_name'),
        'website': profile_dict.get('website'),
        'customer_domain': profile_dict.get('customer_domain'),
        'form_plugin': profile_dict.get('form_plugin'),
        'form_ids': profile_dict.get('form_ids'),
        'colors': profile_dict.get('colors'),
        'logo': profile_dict.get('logo') if profile_dict.get('logo', {}).get('type') != 'upload' else None,
    }
    # Strip None values to save space
    minimal = {k: v for k, v in minimal.items() if v is not None}
    payload = json.dumps(minimal, separators=(',', ':'))
    return f"{MEMORY_PREFIX} {payload}"


def deserialize_brand_profile(memory_line):
    """Parse a memory line back into a brand profile dict. Returns None if not a valid profile line."""
    if not memory_line.startswith(MEMORY_PREFIX):
        return None
    try:
        payload = memory_line[len(MEMORY_PREFIX):].strip()
        return json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return None


def find_profile_in_memories(memory_lines, profile_id=None, customer_domain=None):
    """
    Scan memory lines for a matching brand profile. If both profile_id and
    customer_domain are None, returns the first profile found.
    Returns the profile dict or None.
    """
    for line in memory_lines:
        profile = deserialize_brand_profile(line)
        if not profile:
            continue
        if profile_id and profile.get('profile_id') == profile_id:
            return profile
        if customer_domain and profile.get('customer_domain') == customer_domain:
            return profile
        if profile_id is None and customer_domain is None:
            return profile
    return None


def build_memory_edit_for_profile(profile_dict):
    """
    Returns the string Claude should pass to memory_user_edits(command='add', control=...).
    """
    return serialize_brand_profile(profile_dict)


# Usage pattern Claude should follow (documented here for reference):
#
# SAVING after /brand setup or after discovery:
#   line = build_memory_edit_for_profile(profile)
#   # Claude calls: memory_user_edits(command='add', control=line)
#
# LOADING at the start of a report:
#   # Claude calls: memory_user_edits(command='view')
#   # Returns a list of memory lines; scan them with find_profile_in_memories()
#   profile = find_profile_in_memories(memory_lines, customer_domain='example.com')
#   if profile:
#       # skip discovery — use profile['form_plugin'] and profile['form_ids']
