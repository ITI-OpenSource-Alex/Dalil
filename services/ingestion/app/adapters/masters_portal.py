from bs4 import BeautifulSoup
from app.adapters.base_playwright_adapter import BasePlaywrightAdapter

class MastersPortalAdapter(BasePlaywrightAdapter):
    def __init__(self):
        super().__init__(
            base_url="https://www.mastersportal.com",
            # We'll use the UK country page which contains university links
            target_url="https://www.mastersportal.com/countries/1/united-kingdom.html",
            source_name="masters_portal",
            category="universities",
            country="UK",
            wait_selector="body" 
        )

    def extract_urls(self, html: str) -> list[str]:
        import re
        soup = BeautifulSoup(html, "lxml")
        urls = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r"/universities/\d+/", href) and href.startswith("http"):
                if href not in urls:
                    urls.append(href)
        return urls

    def extract_documents(self, html: str, url: str = None) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        documents = []
        
        # FIX: Target specific content wrappers to avoid navigation menus
        main_content = soup.find(id="UniversityProfile") or soup.find("main")
        
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