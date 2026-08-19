from abc import ABC, abstractmethod
import httpx
import structlog
from app.core.robots import robot_checker
from app.core.rate_limiter import polite_delay
from app.core.retry import with_httpx_backoff
logger = structlog.get_logger(__name__)


class BaseAdapter(ABC):
    def __init__(self, base_url: str, target_url: str, source_name: str, category: str, country: str,
                 min_delay: float = 1.0, max_delay: float = 2.0):
        self.base_url = base_url
        self.target_url = target_url
        self.source_name = source_name
        self.category = category
        self.country = country
        self.min_delay = min_delay
        self.max_delay = max_delay

    @with_httpx_backoff
    async def fetch_page(self, client: httpx.AsyncClient, url: str) -> str:
        """Standardized network fetching with backoff."""
        response = await client.get(url, timeout=15.0)
        response.raise_for_status()
        return response.text

    @with_httpx_backoff
    async def fetch_binary(self, client: httpx.AsyncClient, url: str) -> bytes:
        """Standardized network fetching for binary files (e.g., PDF) with backoff."""
        response = await client.get(url, timeout=15.0)
        response.raise_for_status()
        return response.content

    @abstractmethod
    def extract_documents(self, html: str, url: str = None) -> list[dict]:
        """Subclasses MUST implement this to parse the HTML and return documents."""
        pass

    def extract_urls(self, html: str) -> list[str]:
        """Optional method to extract detail URLs from an index page for crawling."""
        return []

    async def scrape(self) -> list[dict]:
        """The Template Method that orchestrates the scraping lifecycle."""
        if not robot_checker.is_allowed(self.target_url):
            logger.warning("robots_disallowed", url=self.target_url)
            return []
            
        async with httpx.AsyncClient() as client:
            await polite_delay(self.min_delay, self.max_delay)
            index_html = await self.fetch_page(client, self.target_url)
            
            detail_urls = self.extract_urls(index_html)
            
            if not detail_urls:
                return self.extract_documents(index_html, self.target_url)
                
            documents = []
            for url in detail_urls[:50]:
                if not robot_checker.is_allowed(url):
                    continue
                await polite_delay(self.min_delay, self.max_delay)
                try:
                    detail_html = await self.fetch_page(client, url)
                    docs = self.extract_documents(detail_html, url)
                    documents.extend(docs)
                except Exception as e:
                    logger.error("crawl_fetch_error", url=url, error=str(e))
                    
            return documents