from abc import ABC, abstractmethod
from langchain_core.documents import Document


class SourceAdapter(ABC):
    @abstractmethod
    def scrape(self, url: str) -> list[Document]:
        """Scrape the given URL and return a list of Documents."""
        pass


class TestFixtureAdapter(SourceAdapter):
    def scrape(self, url: str) -> list[Document]:
        """Returns 10 hardcoded sample documents for local development and testing."""
        return [
            Document(
                page_content="Germany Student Visa requires proof of financial resources (Blocked Account) of at least 11,208 EUR per year. The visa is issued by the German Federal Foreign Office.",
                metadata={"source_url": "https://goa.app/germany-student-visa", "category": "visa"}
            ),
            Document(
                page_content="Canada Study Permit requires a Guaranteed Investment Certificate (GIC) of 20,635 CAD as proof of financial support. Application is processed by IRCC.",
                metadata={"source_url": "https://goa.app/canada-study-permit", "category": "visa"}
            ),
            Document(
                page_content="Australia Student Visa (Subclass 500) requires a minimum of 24,505 AUD per year to cover living costs. The Department of Home Affairs manages applications.",
                metadata={"source_url": "https://goa.app/australia-subclass-500", "category": "visa"}
            ),
            Document(
                page_content="International students in Germany are allowed to work 120 full days or 240 half days per year. No separate work permit is required.",
                metadata={"source_url": "https://goa.app/germany-working-rights", "category": "visa"}
            ),
            Document(
                page_content="The Technical University of Munich (TUM) offers various English-taught Master's programs. A minimum ECTS of 180 and a GPA equivalent to 2.5 in the German system are typically required.",
                metadata={"source_url": "https://goa.app/tum-master-admission", "category": "education"}
            ),
            Document(
                page_content="University of Toronto requires an IELTS score of at least 6.5 with no band below 6.0 for most undergraduate and graduate admissions.",
                metadata={"source_url": "https://goa.app/utoronto-ielts-requirements", "category": "education"}
            ),
            Document(
                page_content="The DAAD Scholarship in Germany provides monthly stipends of 934 EUR for master's students and 1,200 EUR for doctoral candidates, covering travel and health insurance.",
                metadata={"source_url": "https://goa.app/daad-scholarship-info", "category": "scholarship"}
            ),
            Document(
                page_content="The Vanier Canada Graduate Scholarships offer 50,000 CAD per year for three years for highly qualified doctoral students studying in Canada.",
                metadata={"source_url": "https://goa.app/vanier-scholarship-canada", "category": "scholarship"}
            ),
            Document(
                page_content="To apply for a student visa in France, you must provide proof of minimum monthly resources of 615 EUR. This can be in the form of a scholarship, bank guarantee, or sponsor.",
                metadata={"source_url": "https://goa.app/france-student-visa-resources", "category": "visa"}
            ),
            Document(
                page_content="The University of Melbourne offers the Graduate Research Scholarship, which provides a full fee offset, a living allowance of 37,000 AUD per year, and relocation grants.",
                metadata={"source_url": "https://goa.app/unimelb-graduate-scholarship", "category": "scholarship"}
            )
        ]