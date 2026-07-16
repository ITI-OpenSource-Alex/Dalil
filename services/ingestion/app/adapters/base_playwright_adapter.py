from abc import ABC, abstractmethod
from playwright.async_api import async_playwright
import structlog
from app.core.robots import robot_checker
from app.core.rate_limiter import polite_delay
from app.core.retry import with_playwright_backoff
logger = structlog.get_logger(__name__)


class BasePlaywrightAdapter(ABC):
    def __init__(self, base_url: str, target_url: str, source_name: str, category: str, country: str, wait_selector: str,
                 min_delay: float = 1.0, max_delay: float = 2.0):
        self.base_url = base_url
        self.target_url = target_url
        self.source_name = source_name
        self.category = category
        self.country = country
        # The specific CSS selector we need to wait for before extracting HTML
        self.wait_selector = wait_selector
        self.min_delay = min_delay
        self.max_delay = max_delay

    @with_playwright_backoff
    async def fetch_page(self, url: str) -> str:
        """Fetches the page using a headless browser, explicitly waiting for JS to render."""
        html_content = ""
        async with async_playwright() as p:
            # Headless=True means no UI pops up
            browser = await p.chromium.launch(headless=True)
            page = page = await browser.new_page(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            )
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_timeout(2000)

            # Wait for the site's specific wrapper to populate
            if self.wait_selector:
                await page.wait_for_selector(self.wait_selector, timeout=15000)
            
            html_content = await page.content()
            await browser.close()

        return html_content

    @abstractmethod
    def extract_documents(self, html: str, url: str = None) -> list[dict]:
        """Subclasses MUST implement this to parse the HTML and return documents."""
        pass

    def extract_urls(self, html: str) -> list[str]:
        """Optional method to extract detail URLs from an index page for crawling."""
        return []

    async def scrape(self) -> list[dict]:
        """The Template Method for Playwright adapters."""
        if not robot_checker.is_allowed(self.target_url):
            logger.warning("robots_disallowed", url=self.target_url)
            return []
            
        await polite_delay(self.min_delay, self.max_delay)
        index_html = await self.fetch_page(self.target_url)
        
        detail_urls = self.extract_urls(index_html)
        if not detail_urls:
            return self.extract_documents(index_html, self.target_url)
            
        documents = []
        for url in detail_urls[:50]:
            if not robot_checker.is_allowed(url):
                continue
            await polite_delay(self.min_delay, self.max_delay)
            try:
                detail_html = await self.fetch_page(url)
                docs = self.extract_documents(detail_html, url)
                documents.extend(docs)
            except Exception as e:
                logger.error("crawl_fetch_error", url=url, error=str(e))
                
        return documents