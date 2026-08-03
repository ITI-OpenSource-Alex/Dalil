from bs4 import BeautifulSoup
from app.adapters.base_adapter import BaseAdapter
import structlog

logger = structlog.get_logger(__name__)

class StudyInPolandAdapter(BaseAdapter):
    def __init__(self):
        super().__init__(
            base_url="https://nawa.gov.pl",
            target_url="https://nawa.gov.pl/en/students/foreign-students/the-banach-scholarship-programme",
            source_name="study_in_poland",
            category="scholarships",
            country="Poland"
        )

    def extract_documents(self, html: str, url: str = None) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        documents = []
        
        # Graceful degradation fallback chain
        content_node = soup.find("main") or soup.find("div", id="content") or soup.find("body")
        
        if not content_node:
            logger.error("parse_failure", url=self.target_url, reason="Could not find main content node")
            return []
            
        text_content = content_node.get_text(separator="\n", strip=True)
        documents.append({
            "source": self.source_name,
            "category": self.category,
            "country": self.country,
            "url": self.target_url,
            "content": text_content
        })
            
        return documents