"""Original Pillow artwork and optional Discord media delivery."""

# Operation Snowfall v2.9.0a - optional presentation-only artwork.
try:
    from .snowverhaul import activate as _activate_snowverhaul
    _activate_snowverhaul()
except Exception:
    import logging as _snowverhaul_logging
    _snowverhaul_logging.getLogger(__name__).exception(
        'Snowverhaul failed to activate; the original renderer remains available')
