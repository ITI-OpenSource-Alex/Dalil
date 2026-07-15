from bs4 import BeautifulSoup
from app.adapters.base_adapter import BaseAdapter

class IELTSOrgAdapter(BaseAdapter):
    def __init__(self):
        super().__init__(
            base_url="https://ielts.org",
            target_url="https://ielts.org/take-a-test/your-results/ielts-scoring-in-detail",
            source_name="ielts_org",
            category="language_requirements",
            country="Global"
        )

    def extract_documents(self, html: str, url: str = None) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        documents = []
        
        main_content = soup.find("main")
        
        if main_content:
            text_content = main_content.get_text(separator="\n", strip=True)
            documents.append({
                "source": self.source_name,
                "category": self.category,
                "country": self.country,
                "url": self.target_url,
                "content": text_content
            })
            
        return documents