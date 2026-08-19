from app.core.url_normalizer import normalize_url

def test_normalize_url_basic():
    assert normalize_url("http://www.mastersportal.com/studies/1234/cs/") == "https://www.mastersportal.com/studies/1234/cs"

def test_normalize_url_strips_tracking_params():
    url = "https://www.mastersportal.com/studies/1234/cs?utm_source=google&ref=search&id=123"
    assert normalize_url(url) == "https://www.mastersportal.com/studies/1234/cs?id=123"

def test_normalize_url_empty():
    assert normalize_url("") == ""
    assert normalize_url(None) == ""
