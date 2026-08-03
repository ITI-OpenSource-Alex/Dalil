from bs4 import BeautifulSoup

from app.adapters.base_adapter import BaseAdapter
from app.adapters.scholarship_extraction import extract_degree_level
from app.core.content_hash import compute_content_hash


class CheveningAdapter(BaseAdapter):
    # Unlike DAAD, this adapter targets a single named programme rather than
    # crawling a catalogue of detail pages, so the programme's identity is a
    # property of the target URL, not something to parse out of the body text.
    SCHOLARSHIP_NAME = "Chevening Scholarship"
    PROVIDER = "Chevening"

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
            effective_url = url or self.target_url
            doc = {
                "source": self.source_name,
                "category": self.category,
                "country": self.country,
                "url": effective_url,
                "content": text_content
            }
            record = self._extract_scholarship(text_content, effective_url)
            doc["scholarship_programs"] = [record] if record else []
            documents.append(doc)

        return documents

    def _extract_scholarship(self, text_content: str, url: str) -> dict | None:
        """Builds the single scholarship_programs record this source describes.

        Deliberately narrow. The live page states the degree level ("a one-year
        master's degree at a UK university") and nothing else in machine-readable
        form: the award value and the eligibility criteria both live behind links
        to separate pages, and the deadline is given as prose ("Applications ...
        are now closed") with no date. Those fields stay None rather than guessed.

        In particular this does NOT run the generic "Who can apply?" section scan
        that DAAD uses. That heading appears here inside the page's "In this
        section" navigation block, so the scan would happily collect "Application
        timeline", "Find a course" and "FAQs" as eligibility criteria -- plausible
        looking rows that are pure navigation chrome. An empty eligibility dict is
        the honest answer; see the follow-up note in the BUG-010 handoff about
        fetching /scholarships/eligibility/ as a second page.
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
            "min_gpa": None,
            "min_ielts": None,
        }
        record["content_hash"] = compute_content_hash(record)
        return record
