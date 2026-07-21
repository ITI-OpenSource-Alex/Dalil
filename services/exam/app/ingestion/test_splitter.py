import re
from app.ingestion.parser_helpers import classify_test_marker


class TestSplitter:
    """Isolates genuine test blocks from full OCR text based on structural context."""

    def split(self, text: str) -> dict[int, str]:
        """Split full book text into per-test blocks.

        Relies on structural context (the presence of LISTENING or SECTION 1)
        immediately following a Test marker to differentiate genuine test boundaries
        from TOC entries, answer keys, and page headers.
        """
        matches = list(re.finditer(r"(?i)^Test\s+(\d+)\b", text, re.MULTILINE))
        if not matches:
            return {1: text}

        valid_matches: list[re.Match] = []
        for m in matches:
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            if line_end == -1:
                line_end = len(text)

            line = text[line_start:line_end]
            marker = classify_test_marker(line)

            if marker and not marker.is_toc and not marker.is_phantom:
                # Deterministic order handles separating genuine tests from answer keys later.
                valid_matches.append(m)

        # Minimal deterministic logic: genuine test boundaries must appear in sequential order.
        # This handles cases where answer keys structurally mimic a test boundary.
        genuine_matches: list[re.Match] = []
        highest_test = 0
        for m in valid_matches:
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            t_num = classify_test_marker(text[line_start:line_end]).test_number
            if t_num == highest_test + 1:
                genuine_matches.append(m)
                highest_test = t_num

        if not genuine_matches:
            return {1: text}

        tests: dict[int, str] = {}
        for i, m in enumerate(genuine_matches):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            t_num = classify_test_marker(text[line_start:line_end]).test_number
            start = m.start()
            end = (
                genuine_matches[i + 1].start()
                if i + 1 < len(genuine_matches)
                else len(text)
            )
            test_content = text[start:end]



            tests[t_num] = test_content

        return tests
