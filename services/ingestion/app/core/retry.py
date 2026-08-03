import httpx
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError


class PageFetchError(Exception):
    """A page was served with an HTTP error status.

    Playwright does not raise on 4xx/5xx -- page.goto() returns the error page's
    body just like any other document. Without this, a 403 block page reaches
    extract_urls(), yields no links, and the run reports "success, 0 documents":
    indistinguishable from a source whose catalog is genuinely empty. See
    BUG-010a, where DAAD was blocked at the IP level for an entire sprint while
    every summary said success.
    """

    def __init__(self, url: str, status_code: int):
        self.url = url
        self.status_code = status_code
        super().__init__(f"HTTP {status_code} fetching {url}")


def is_transient_httpx_error(e: Exception) -> bool:
    """Returns True if the exception is a transient network or 5xx/429 error."""
    if isinstance(e, httpx.RequestError):
        return True # Disconnects, timeouts
    if isinstance(e, httpx.HTTPStatusError):
        # 429 Too Many Requests, or any 5xx Server Error
        return e.response.status_code == 429 or e.response.status_code >= 500
    return False


# Decorator for httpx adapters
with_httpx_backoff = retry(
    retry=retry_if_exception(is_transient_httpx_error),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(4),
    reraise=True
)

def is_transient_playwright_error(e: Exception) -> bool:
    """Retry browser/network faults and rate-limited or server-side statuses.

    A 403/404 is a settled answer, not a blip -- retrying it three times with
    backoff only slows the run down and makes the eventual log noisier.
    """
    if isinstance(e, (PlaywrightError, PlaywrightTimeoutError)):
        return True
    if isinstance(e, PageFetchError):
        return e.status_code == 429 or e.status_code >= 500
    return False


# Decorator for Playwright adapters
with_playwright_backoff = retry(
    retry=retry_if_exception(is_transient_playwright_error),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True
)