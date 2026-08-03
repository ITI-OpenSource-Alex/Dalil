import urllib.parse

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "sp", "gclid", "fbclid", "_ga"
}

def normalize_url(url: str) -> str:
    """Canonical URL normalizer for boundary deduplication.

    - Forces https scheme
    - Strips trailing slashes
    - Lowercases hostname
    - Strips common tracking/session query parameters
    """
    if not url:
        return ""
    
    parsed = urllib.parse.urlparse(url.strip())
    
    # Scheme
    scheme = "https" if parsed.scheme in ("http", "https") else parsed.scheme
    
    # Netloc (hostname)
    netloc = parsed.netloc.lower()
    
    # Path (strip trailing slash except root)
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
        
    # Query parameters
    if parsed.query:
        query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        filtered_pairs = [(k, v) for k, v in query_pairs if k.lower() not in _TRACKING_PARAMS]
        filtered_pairs.sort(key=lambda x: x[0])
        query = urllib.parse.urlencode(filtered_pairs)
    else:
        query = ""
        
    normalized = urllib.parse.urlunparse((scheme, netloc, path, parsed.params, query, ""))
    return normalized
