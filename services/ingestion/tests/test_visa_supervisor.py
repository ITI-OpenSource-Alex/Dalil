import asyncio
import sys

sys.path.insert(0, "D:/ITI/Graduation Project/GOA/services/ingestion")
from app.adapters.visa_supervisor import Verdict, deterministic_checks, supervise


class FakeBlock:
    def __init__(self, text):
        self.text = text


class FakeResp:
    def __init__(self, text, stop="end_turn"):
        self.content = [FakeBlock(text)]
        self.stop_reason = stop


class FakeAnthropic:
    def __init__(self, payload=None, raise_=False, stop="end_turn"):
        self.messages = self
        self._p = payload
        self._r = raise_
        self._s = stop

    async def create(self, **kw):
        if self._r:
            raise RuntimeError("provider down")
        return FakeResp(self._p or "", self._s)


REQ = (
    "Student visa requirements for applicants in Egypt. Supporting documents "
    "required: passport, proof of funds, blocked account. How to apply. " * 12
)
NEWS = (
    "Press release: the agency begins operations today. News from the "
    "newsroom about the new authority. " * 12
)
UAE = (
    "Student visa requirements for Emirati applicants in the United Arab "
    "Emirates. Documents required, proof of funds. " * 12
)


async def main():
    ok = 0
    total = 0

    def check(name, cond):
        nonlocal ok, total
        total += 1
        ok += bool(cond)
        print(("  ok   " if cond else "  FAIL ") + name)

    # Deterministic layer
    p, f = deterministic_checks(
        url="https://ind.nl/en",
        page_text=REQ,
        country="Netherlands",
        issuing_body="IND",
    )
    check("requirements page passes cheap checks", "mentions_requirements" in p)
    p, f = deterministic_checks(
        url="https://x.gov.pt/news",
        page_text=NEWS,
        country="Portugal",
        issuing_body="AIMA",
    )
    check("news page flagged as news", any("reads_as_news" in x for x in f))
    p, f = deterministic_checks(
        url="https://vfs/norway/uae/",
        page_text=UAE,
        country="Norway",
        issuing_body="UDI",
    )
    check("other nationality detected", "addresses_another_nationality" in f)

    good = '{"is_requirements_page":true,"serves_egyptian_applicants":true,"mentions_financial_requirement":true,"financial_amount_present":true,"confidence":0.93,"reason":"official checklist"}'
    low = '{"is_requirements_page":true,"serves_egyptian_applicants":null,"mentions_financial_requirement":true,"financial_amount_present":true,"confidence":0.40,"reason":"unsure"}'
    notreq = '{"is_requirements_page":false,"serves_egyptian_applicants":null,"mentions_financial_requirement":false,"financial_amount_present":false,"confidence":0.9,"reason":"press release"}'

    r = await supervise(
        FakeAnthropic(good),
        "m",
        url="https://ind.nl/en",
        page_text=REQ,
        country="Netherlands",
        issuing_body="IND",
    )
    check("clean source ACCEPTs", r.verdict is Verdict.ACCEPT and r.usable)

    r = await supervise(
        FakeAnthropic(good),
        "m",
        url="https://vfs/norway/uae/",
        page_text=UAE,
        country="Norway",
        issuing_body="UDI",
    )
    check(
        "wrong nationality REJECTs even when model says accept",
        r.verdict is Verdict.REJECT,
    )

    r = await supervise(
        FakeAnthropic(notreq),
        "m",
        url="https://x.gov.pt/news",
        page_text=NEWS,
        country="Portugal",
        issuing_body="AIMA",
    )
    check("news page REJECTs", r.verdict is Verdict.REJECT)

    r = await supervise(
        FakeAnthropic(low),
        "m",
        url="https://ind.nl/en",
        page_text=REQ,
        country="Netherlands",
        issuing_body="IND",
    )
    check(
        "low confidence goes to REVIEW not accept",
        r.verdict is Verdict.REVIEW and not r.usable,
    )

    r = await supervise(
        FakeAnthropic(raise_=True),
        "m",
        url="https://ind.nl/en",
        page_text=REQ,
        country="Netherlands",
        issuing_body="IND",
    )
    check(
        "unavailable supervisor REVIEWs, never accepts",
        r.verdict is Verdict.REVIEW and not r.usable,
    )

    r = await supervise(
        FakeAnthropic(good, stop="max_tokens"),
        "m",
        url="https://ind.nl/en",
        page_text=REQ,
        country="Netherlands",
        issuing_body="IND",
    )
    check("truncated response REVIEWs", r.verdict is Verdict.REVIEW)

    r = await supervise(
        FakeAnthropic(good),
        "m",
        url="https://ind.nl/en",
        page_text="short",
        country="Netherlands",
        issuing_body="IND",
    )
    check("empty page REJECTs without a model call", r.verdict is Verdict.REJECT)

    print(f"\n{ok}/{total} passed")
    return 0 if ok == total else 1


sys.exit(asyncio.run(main()))
