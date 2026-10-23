from .reaction_normalizer import normalize_surface_form


def normalize_indication(raw_indication: str | None) -> str | None:
    """`drugindication` is, like `reactionmeddrapt`, typically a MedDRA term string -- same
    surface-form normalization applies, with the same hierarchy-unavailable caveat."""
    if not raw_indication:
        return None
    normalized = normalize_surface_form(raw_indication)
    return normalized or None
