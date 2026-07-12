from bs4 import BeautifulSoup
from app.adapters.base_adapter import BaseAdapter
import structlog
import httpx
import io
from app.core.robots import robot_checker
from app.core.rate_limiter import polite_delay

logger = structlog.get_logger(__name__)

class StipendiumHungaricumAdapter(BaseAdapter):
    def __init__(self):
        super().__init__(
            base_url="https://stipendiumhungaricum.hu",
            target_url="https://stipendiumhungaricum.hu/apply/",
            source_name="stipendium_hungaricum",
            category="scholarships",
            country="Hungary"
        )

    def extract_documents(self, html: str, url: str = None) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        documents = []
        
        # Target specific content containers instead of the entire body to avoid navigation chrome
        main_content = soup.find("main") or soup.find("div", class_="container--application") or soup.find("div", class_="entry-content")
        
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
        if not robot_checker.is_allowed(self.target_url):
            logger.warning("robots_disallowed", url=self.target_url)
            return []
            
        # The Hungarian government site has a known broken SSL cert chain.
        # While modern httpx sometimes handles it via SNI/certifi better than urllib,
        # we explicitly disable verify here to match the robot_checker's bypass policy.
        async with httpx.AsyncClient(verify=False) as client:
            await polite_delay()
            html = await self.fetch_page(client, self.target_url)
            docs = self.extract_documents(html, self.target_url)
            
            # Dynamically discover PDF link
            soup = BeautifulSoup(html, "lxml")
            pdf_url = None
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.endswith(".pdf") and "Call_for_Applications" in href:
                    pdf_url = href
                    break
                    
            if not pdf_url:
                logger.error("missing_pdf", url=self.target_url, reason="Could not dynamically discover the Call for Applications PDF")
                return docs
                
            if not robot_checker.is_allowed(pdf_url):
                return docs
                
            await polite_delay()
            try:
                pdf_bytes = await self.fetch_binary(client, pdf_url)
                
                # Import here to avoid polluting other adapters
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(pdf_bytes))
                text = ""
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                        
                docs.append({
                    "source": self.source_name,
                    "category": self.category,
                    "country": self.country,
                    "url": pdf_url,
                    "content": text
                })
            except Exception as e:
                logger.error("pdf_fetch_error", url=pdf_url, error=str(e))
                
        return docs