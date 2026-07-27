from bs4 import BeautifulSoup
from app.adapters.base_adapter import BaseAdapter
import structlog
import httpx
import io
from app.adapters.scholarship_extraction import (
    GPA_RE,
    IELTS_RE,
    extract_degree_level,
    extract_numeric_field,
)
from app.core.content_hash import compute_content_hash
from app.core.robots import robot_checker
from app.core.rate_limiter import polite_delay

logger = structlog.get_logger(__name__)

class StipendiumHungaricumAdapter(BaseAdapter):
    # A single named programme, like Chevening -- the identity comes from the
    # source, not from parsing. Tempus Public Foundation is the operator named
    # throughout the Call for Applications; the programme name is the PDF's own
    # section 1 heading.
    SCHOLARSHIP_NAME = "Stipendium Hungaricum Scholarship Programme"
    PROVIDER = "Tempus Public Foundation"

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
                "content": text_content,
                # The landing page is a 400-character signpost to the real
                # document; the structured record is built from the PDF in
                # scrape() instead. The key is still present so handler.py's
                # pop() shape is uniform across adapters.
                "scholarship_programs": [],
            })

        return documents

    def _extract_scholarship(self, text_content: str, url: str) -> dict | None:
        """Builds the single scholarship_programs record for this programme from
        the Call for Applications PDF.

        degree_level is resolved with none_if_ambiguous because one call genuinely
        covers bachelor's, master's, one-tier master's and doctoral study at once.
        Earliest-occurrence scanning would stamp the whole programme "Bachelor",
        which is not a truth about it -- None is.

        award_amount and deadline stay None: the PDF states its provisions and
        its timeline under headings ("Provisions Covered by the Scholarship",
        "Application Timeline") that the generic section scanner does not
        recognise, and inventing a match for them from 82KB of extracted PDF text
        is how fabricated rows get into the table.
        """
        if not text_content.strip():
            return None

        record = {
            "name": self.SCHOLARSHIP_NAME,
            "provider": self.PROVIDER,
            "source_url": url,
            "country": self.country,
            "degree_level": extract_degree_level(
                text_content, name=None, none_if_ambiguous=True
            ),
            "award_amount": None,
            "deadline": None,
            "eligibility": {},
            "citizenship_eligible": True,
            "min_gpa": extract_numeric_field(text_content, GPA_RE),
            "min_ielts": extract_numeric_field(text_content, IELTS_RE),
        }
        record["content_hash"] = compute_content_hash(record)
        return record

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
                        
                record = self._extract_scholarship(text, pdf_url)
                docs.append({
                    "source": self.source_name,
                    "category": self.category,
                    "country": self.country,
                    "url": pdf_url,
                    "content": text,
                    "scholarship_programs": [record] if record else [],
                })
            except Exception as e:
                logger.error("pdf_fetch_error", url=pdf_url, error=str(e))
                
        return docs