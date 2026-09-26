"""Small URL-equivalence rules for browser redirects and evidence labels."""

from urllib.parse import urlsplit


def same_web_origin(target, observed) -> bool:
    """Allow an exact web origin, www alias, or HTTP-to-HTTPS upgrade."""
    target_host = (target.hostname or "").lower().rstrip(".")
    observed_host = (observed.hostname or "").lower().rstrip(".")
    if not target_host or not observed_host:
        return False
    same_host = target_host == observed_host or (
        target_host.removeprefix("www.") == observed_host
        or observed_host.removeprefix("www.") == target_host
    )
    if not same_host or target.scheme not in {"http", "https"} or observed.scheme not in {"http", "https"}:
        return False
    target_port = target.port or (443 if target.scheme == "https" else 80)
    observed_port = observed.port or (443 if observed.scheme == "https" else 80)
    if target.scheme == observed.scheme:
        return target_port == observed_port
    return (
        target.scheme == "http"
        and observed.scheme == "https"
        and target_port == 80
        and observed_port == 443
    )


def is_browser_error_url(value) -> bool:
    """Recognize Chromium's internal network-error document without retaining it."""
    if not isinstance(value, str):
        return False
    try:
        return urlsplit(value[:4096]).scheme.lower() == "chrome-error"
    except ValueError:
        return False
