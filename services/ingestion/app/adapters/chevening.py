from bs4 import BeautifulSoup
from app.adapters.base_adapter import BaseAdapter


class CheveningAdapter(BaseAdapter):
    def __init__(self):
        super().__init__(
            base_url="https://www.chevening.org",
            target_url="https://www.chevening.org/scholarships/who-can-apply/",
            source_name="chevening",
            category="scholarships",
            country="UK"
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