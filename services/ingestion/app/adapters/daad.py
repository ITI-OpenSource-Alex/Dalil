from bs4 import BeautifulSoup
from app.adapters.base_playwright_adapter import BasePlaywrightAdapter

class DAADAdapter(BasePlaywrightAdapter):
    def __init__(self):
        super().__init__(
            base_url="https://www2.daad.de",
            target_url="https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/?status=1&origin=190&subjectGrps=&daad=&intention=&q=&page=1&back=1",
            source_name="daad",
            category="scholarships",
            country="Germany",
            wait_selector="body"
        )

    async def fetch_page(self, url: str) -> str:
        original_wait = self.wait_selector
        if "detail=" in url:
            self.wait_selector = "#ifa-stipendien-detail"
        try:
            return await super().fetch_page(url)
        finally:
            self.wait_selector = original_wait

    def extract_urls(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        urls = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "detail=" in href:
                full_url = href if href.startswith("http") else f"{self.base_url}{href}"
                if full_url not in urls:
                    urls.append(full_url)
        return urls

    def extract_documents(self, html: str, url: str = None) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        documents = []
        
        main_content = soup.find("main") or soup.find("div", id="main-content") or soup.find(id="content") or soup.find("div", class_="c-detail-page")
        
        if main_content:
            text_content = main_content.get_text(separator="\n", strip=True)
            documents.append({
                "source": self.source_name,
                "category": self.category,
                "country": self.country,
                "url": url or self.target_url,
                "content": text_content
            })
            
        return documents
        
    async def scrape(self) -> list[dict]:
        from app.core.robots import robot_checker
        from app.core.rate_limiter import polite_delay
        import structlog
        
        logger = structlog.get_logger(__name__)
        
        if not robot_checker.is_allowed(self.target_url):
            logger.warning("robots_disallowed", url=self.target_url)
            return []
            
        detail_urls = []
        # DAAD yields 18 per page, so 3 pages gives 54 urls
        for page_num in range(1, 4):
            page_url = self.target_url.replace("page=1", f"page={page_num}")
            await polite_delay()
            index_html = await self.fetch_page(page_url)
            urls = self.extract_urls(index_html)
            if not urls:
                break
            for u in urls:
                if u not in detail_urls:
                    detail_urls.append(u)
            if len(detail_urls) >= 50:
                break
                
        detail_urls = detail_urls[:50]
        
        documents = []
        for url in detail_urls:
            if not robot_checker.is_allowed(url):
                continue
            await polite_delay()
            try:
                detail_html = await self.fetch_page(url)
                docs = self.extract_documents(detail_html, url)
                documents.extend(docs)
            except Exception as e:
                logger.error("crawl_fetch_error", url=url, error=str(e))
                
        return documents