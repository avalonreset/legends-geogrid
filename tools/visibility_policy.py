"""Keep a Maps viewport experiment distinct from an origin-based visibility study."""


def validate_visibility_policy(settings, policy=None, diagnostic=None):
    if settings.get("search_this_area") is False:
        return
    policy = policy or {}
    diagnostic = diagnostic or {}
    if (policy.get("intent") == "viewport"
            and str(policy.get("rationale") or "").strip()):
        return
    if (str(diagnostic.get("purpose") or "").strip()
            and str(diagnostic.get("source_scan") or "").strip()):
        return
    raise ValueError(
        "Viewport-restricted Maps collection can create rectangular rank cutoffs. "
        "Use search_this_area=false for origin-based visibility, calibrate the zoom, "
        "and preserve changed controls in a separate run. An intentional viewport "
        "study requires collection_policy.intent='viewport' and a rationale."
    )
