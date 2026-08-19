from bs4 import BeautifulSoup
from app.adapters.base_adapter import BaseAdapter


class IELTSOrgAdapter(BaseAdapter):
    # The pages this adapter ingests.
    #
    # It used to scrape one page -- ielts-scoring-in-detail -- so the corpus had
    # band descriptors and marking criteria but nothing about test *format* or
    # timing. "What is the IELTS Writing Task 2 time limit?" was therefore
    # unanswerable: top similarity 0.5645 and a correct "I don't know", while
    # "What does band 7 mean?" answered at 0.7977 off the same corpus. Retrieval
    # was healthy; coverage was the gap (BUG-012). "How long is Task 2" is a
    # question real candidates ask constantly.
    #
    # The scoring page stays first and deliberately: BaseAdapter.scrape() only
    # extracts the index page when extract_urls() returns nothing, so listing
    # detail URLs without including the original would have silently dropped the
    # coverage this adapter already had.
    CONTENT_URLS = [
        "https://ielts.org/take-a-test/your-results/ielts-scoring-in-detail",
        "https://ielts.org/take-a-test/test-types/ielts-academic-test",
        "https://ielts.org/take-a-test/test-types/ielts-general-training-test",
        "https://ielts.org/take-a-test/preparation-resources/on-test-day",
        "https://ielts.org/take-a-test/preparation-resources/sample-test-questions",
    ]

    def __init__(self):
        super().__init__(
            base_url="https://ielts.org",
            target_url=self.CONTENT_URLS[0],
            source_name="ielts_org",
            category="language_requirements",
            country="Global"
        )

    def extract_urls(self, html: str) -> list[str]:
        """Return the fixed page list rather than crawling for links.

        These are five stable, hand-picked pages, so discovery would add failure
        modes without adding coverage. Returning them here routes every page
        through scrape()'s per-URL fetch, robots check and polite delay.
        """
        return list(self.CONTENT_URLS)

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
                # Was hardcoded to self.target_url. Harmless while one page was
                # scraped; with five it would have stamped every chunk with the
                # scoring page's URL, so citations would point at a page not
                # containing the answer -- the exact complaint in BUG-052.
                "url": url or self.target_url,
                "content": text_content
            })

        return documents
