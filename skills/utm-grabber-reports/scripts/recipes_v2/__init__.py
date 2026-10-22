"""
v2 report recipes. RECIPES maps a routing key to a builder function.

Each module registers its builders in its own REGISTRY dict; this file merges
them. A missing module (for example while a release is being assembled) is
skipped rather than breaking every other report.
"""
import importlib

RECIPES = {}
_MODULES = ["core", "channels", "paid_media", "leads_and_forms", "planning", "cross_platform", "premium"]

for _m in _MODULES:
    try:
        mod = importlib.import_module("recipes_v2." + _m)
    except ImportError:
        continue
    RECIPES.update(getattr(mod, "REGISTRY", {}))


def get_recipe(key):
    k = str(key or "").strip().lower()
    if k not in RECIPES:
        raise KeyError("Unknown report %r. Available: %s" % (key, ", ".join(sorted(RECIPES))))
    return RECIPES[k]
