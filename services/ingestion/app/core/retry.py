import httpx
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type, retry_if_exception
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

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

# Decorator for Playwright adapters
with_playwright_backoff = retry(
    retry=retry_if_exception_type((PlaywrightError, PlaywrightTimeoutError)),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True
)