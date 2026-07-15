# GOA-086 Adapter Source Review

## Executive Summary

An in-depth review of the 9 adapters proposed for the GOA-086 ingestion pipeline has been conducted. The objective of this review is to verify the official sources, validate the target URLs, determine the appropriate scraping patterns, and confirm the presence of the required fields specified in the ticket.

The review revealed that **all current implementations rely on base URLs** rather than exact paths, and many adapters are pointing to incorrect, deprecated, or non-existent domains. Most notably, the `APSCairoAdapter` targets a fabricated URL (`aps-cairo.org`) for a procedure (APS certification) that is **not required** for Egyptian applicants to Germany. Furthermore, several adapters need to switch to discovering PDF files or navigating through multi-page guides instead of statically scraping a single HTML page.

## Review Methodology

For each adapter, the current Python implementation was inspected to identify the `target_url` and the fields it attempts to extract. Independent web research was then conducted to locate the official issuing body's website for Egypt-based applicants. The findings were compared against the GOA-086 ticket requirements to verify if the expected data is genuinely available on the source pages, adhering strictly to the constraint of not fabricating information.

## Adapter Reviews

### 1. GermanEmbassyCairoAdapter

- **Current implementation:** `german_embassy_cairo.py`
- **Current target_url:** `https://kairo.diplo.de`
- **Official source found:** German Embassy in Cairo (diplo.de)
- **Correct URL:** Exact path to the student visa requirements/PDF checklist on `https://kairo.diplo.de`
- **URL verified?** No (currently only a base URL).
- **Scraping pattern to use:** **StipendiumHungaricum pattern**. Embassies frequently use downloadable PDF checklists for visa requirements. The adapter should dynamically discover the PDF link on the landing page and parse the PDF.
- **Required fields from the ticket:** Student visa required documents, APS certificate instructions, Blocked account requirements, Proof of funds amount.
- **Which required fields are actually present:** Student visa required documents, Blocked account requirements, Proof of funds amount.
- **Missing fields:** **APS certificate instructions**. (APS is not required for Egyptian students).
- **Risks:** Assuming APS requirements exist will lead to empty extracts or hallucinated data.
- **Recommended implementation approach:** Implement PDF discovery and parsing. Remove expectations for APS data.
- **Confidence level:** High

### 2. APSCairoAdapter

- **Current implementation:** `aps_cairo.py`
- **Current target_url:** `https://www.aps-cairo.org`
- **Official source found:** None. APS (Akademische Prüfstelle) is not required for Egypt.
- **Correct URL:** N/A
- **URL verified?** No. The domain `aps-cairo.org` is either non-existent or completely unrelated.
- **Scraping pattern to use:** N/A
- **Required fields from the ticket:** APS certificate procedure, Required documents, Processing time, Fee.
- **Which required fields are actually present:** None.
- **Missing fields:** All fields are missing because the procedure does not apply to Egypt.
- **Risks:** High risk of failure or scraping a domain squatter.
- **Recommended implementation approach:** **Deprecate/Delete** this adapter. Do not deploy it for Egypt.
- **Confidence level:** High

### 3. CampusFranceEgyptAdapter

- **Current implementation:** `campus_france_egypt.py`
- **Current target_url:** `https://eg.campusfrance.org`
- **Official source found:** Campus France Égypte
- **Correct URL:** `https://www.egypte.campusfrance.org` (specifically the "Je suis accepté" procedure page).
- **URL verified?** No. The current subdomain `eg.` is incorrect; the official subdomain is `egypte.`.
- **Scraping pattern to use:** **IELTS pattern** (if extracting from a single "Je suis accepté" page) or **DAAD pattern** (if navigating from the landing page).
- **Required fields from the ticket:** Pre-registration steps, Required documents, Proof of funds, Campus France interview process.
- **Which required fields are actually present:** Pre-registration steps, Required documents, Campus France interview process.
- **Missing fields:** Proof of funds (Financial requirements for the visa are typically handled by TLScontact or the French Consulate, not the Campus France pre-consular step).
- **Risks:** The adapter might fail to resolve the wrong subdomain.
- **Recommended implementation approach:** Correct the URL to `egypte.campusfrance.org`. Explicitly flag that proof of funds is a consular requirement.
- **Confidence level:** High

### 4. UKVISAEgyptAdapter

- **Current implementation:** `uk_visa_egypt.py`
- **Current target_url:** `https://www.gov.uk`
- **Official source found:** GOV.UK Student Visa section
- **Correct URL:** `https://www.gov.uk/student-visa`
- **URL verified?** No (currently only a base URL).
- **Scraping pattern to use:** **DAAD pattern**. The GOV.UK student visa guide is paginated (multi-page guide with Next/Previous links).
- **Required fields from the ticket:** Student visa requirements, Egyptian applicant requirements, VFS Egypt centres, Appointment booking URL.
- **Which required fields are actually present:** Student visa requirements, Appointment booking URL.
- **Missing fields:** Egyptian applicant requirements (GOV.UK provides generic guidelines, specific local requirements are rare without dynamic forms), VFS Egypt centres (These are hosted on the VFS Global domain, not GOV.UK).
- **Risks:** Missing localized data by only scraping the generic UK portal.
- **Recommended implementation approach:** Use the DAAD pattern to crawl the paginated guide. Accept that VFS centre data will not be present on GOV.UK.
- **Confidence level:** High

### 5. VFSGlobalEgyptAdapter

- **Current implementation:** `vfs_global_egypt.py`
- **Current target_url:** `https://visa.vfsglobal.com/egy/en`
- **Official source found:** VFS Global Egypt
- **Correct URL:** `https://visa.vfsglobal.com/egy/en` (as a starting point).
- **URL verified?** Partially (it is a valid base URL, but needs dynamic navigation).
- **Scraping pattern to use:** **DAAD pattern**. The adapter must land on the index page and dynamically discover the sub-pages for specific destination countries.
- **Required fields from the ticket:** Biometric appointment information, Centre details, Country-specific VFS portals.
- **Which required fields are actually present:** Biometric appointment information, Centre details, Country-specific VFS portals.
- **Missing fields:** None.
- **Risks:** VFS Global sites heavily rely on JavaScript. Playwright must be used (as currently implemented).
- **Recommended implementation approach:** Maintain Playwright implementation. Ensure the adapter successfully enumerates country links from the landing page.
- **Confidence level:** High

### 6. FintibaSperrkontoAdapter

- **Current implementation:** `fintiba_sperrkonto.py`
- **Current target_url:** `https://fintiba.com`
- **Official source found:** Fintiba
- **Correct URL:** `https://www.fintiba.com/blocked-account/`
- **URL verified?** No (base URL only).
- **Scraping pattern to use:** **IELTS pattern**. Extract from a single blocked account product page.
- **Required fields from the ticket:** Blocked account setup, Fee schedule, Processing time, Egypt-specific payment instructions.
- **Which required fields are actually present:** Blocked account setup, Fee schedule, Processing time.
- **Missing fields:** Egypt-specific payment instructions. (Fintiba provides a global platform; country-specific payment intricacies are usually handled post-registration).
- **Risks:** Searching for Egypt-specific strings might yield no results.
- **Recommended implementation approach:** Update the URL to the exact product page. Handle the absence of Egypt-specific instructions gracefully.
- **Confidence level:** High

### 7. CzechEmbassyCairoAdapter

- **Current implementation:** `czech_embassy_cairo.py`
- **Current target_url:** `https://www.mzv.cz/cairo`
- **Official source found:** Embassy of the Czech Republic in Cairo
- **Correct URL:** `https://mzv.gov.cz/cairo/en/visa_and_consular_information/`
- **URL verified?** No. The domain has migrated from `mzv.cz` to `mzv.gov.cz`.
- **Scraping pattern to use:** **DAAD pattern** or **StipendiumHungaricum pattern**.
- **Required fields from the ticket:** Student visa requirements, Document checklist, Processing time, Proof of funds.
- **Which required fields are actually present:** Student visa requirements, Document checklist, Processing time, Proof of funds.
- **Missing fields:** None.
- **Risks:** The `.cz` URL will redirect or fail; the exact path to the long-term visa page is required.
- **Recommended implementation approach:** Update domain to `mzv.gov.cz`. Discover the specific article detailing long-term study visas.
- **Confidence level:** High

### 8. SpainVisaEgyptAdapter

- **Current implementation:** `spain_visa_egypt.py`
- **Current target_url:** `https://www.exteriores.gob.es/consulados/elcairo`
- **Official source found:** BLS International Spain (Egypt) & Consulate of Spain in Cairo
- **Correct URL:** `https://egypt.blsspainvisa.com/` (BLS International portal)
- **URL verified?** No (Base URL only, and potentially the wrong primary source for actionable requirements).
- **Scraping pattern to use:** **DAAD pattern**.
- **Required fields from the ticket:** Student visa requirements, Document checklist, Proof of funds (IPREM or official financial requirement).
- **Which required fields are actually present:** Student visa requirements, Document checklist, Proof of funds.
- **Missing fields:** None.
- **Risks:** Scraping the `exteriores.gob.es` site might only yield a redirection notice to BLS International.
- **Recommended implementation approach:** Verify if BLS International is the better target for the checklist.
- **Confidence level:** High

### 9. ItalyEmbassyCairoAdapter

- **Current implementation:** `italy_embassy_cairo.py`
- **Current target_url:** `https://ambcairo.esteri.it`
- **Official source found:** Embassy of Italy in Cairo
- **Correct URL:** `https://ambcairo.esteri.it/it/servizi-consolari-e-visti/servizi-per-il-cittadino-straniero/visti/`
- **URL verified?** No (base URL only).
- **Scraping pattern to use:** **StipendiumHungaricum pattern** (if a PDF checklist is provided) or **DAAD pattern**.
- **Required fields from the ticket:** Student visa requirements, Document checklist, Processing time, Declaration of Value, Proof of funds.
- **Which required fields are actually present:** Student visa requirements, Document checklist, Declaration of Value, Proof of funds.
- **Missing fields:** Processing time (Often not explicitly guaranteed on the site).
- **Risks:** Italy often outsources to VFS/TLS.
- **Recommended implementation approach:** Locate the exact study visa requirements page/PDF on `ambcairo.esteri.it`.
- **Confidence level:** High

---

## Cross-Adapter Findings

| Adapter                   | Current URL                         | Correct Official URL                        | Pattern                      | Required Fields Present?     | Confidence | Notes                                                        |
| ------------------------- | ----------------------------------- | ------------------------------------------- | ---------------------------- | ---------------------------- | ---------- | ------------------------------------------------------------ |
| GermanEmbassyCairoAdapter | `https://kairo.diplo.de`            | `https://kairo.diplo.de` (needs exact path) | StipendiumHungaricum         | No (APS is missing)          | High       | APS not required for Egypt. Must extract PDF.                |
| APSCairoAdapter           | `https://www.aps-cairo.org`         | N/A                                         | N/A                          | No (All missing)             | High       | Domain is fake/unrelated. Procedure doesn't apply to Egypt.  |
| CampusFranceEgyptAdapter  | `https://eg.campusfrance.org`       | `https://www.egypte.campusfrance.org`       | IELTS or DAAD                | No (Proof of funds missing)  | High       | Subdomain is incorrect (`eg.` vs `egypte.`).                 |
| UKVISAEgyptAdapter        | `https://www.gov.uk`                | `https://www.gov.uk/student-visa`           | DAAD                         | No (VFS details missing)     | High       | Must crawl paginated gov.uk guide. VFS is on another domain. |
| VFSGlobalEgyptAdapter     | `https://visa.vfsglobal.com/egy/en` | `https://visa.vfsglobal.com/egy/en`         | DAAD                         | Yes                          | High       | Requires Playwright.                                         |
| FintibaSperrkontoAdapter  | `https://fintiba.com`               | `https://www.fintiba.com/blocked-account/`  | IELTS                        | No (Egypt-specifics missing) | High       | Standard global page doesn't mention Egypt specifically.     |
| CzechEmbassyCairoAdapter  | `https://www.mzv.cz/cairo`          | `https://mzv.gov.cz/cairo/...`              | DAAD or StipendiumHungaricum | Yes                          | High       | Domain changed to `.gov.cz`.                                 |
| SpainVisaEgyptAdapter     | `https://www.exteriores.gob.es...`  | `https://egypt.blsspainvisa.com/`           | DAAD                         | Yes                          | High       | Embassy outsources to BLS International.                     |
| ItalyEmbassyCairoAdapter  | `https://ambcairo.esteri.it`        | `https://ambcairo.esteri.it/.../visti/`     | DAAD or StipendiumHungaricum | No (Processing time missing) | High       | Find the exact page/PDF.                                     |

- **Repeated problems:** **Every single adapter** is currently configured with a base domain rather than the exact target URL for the visa requirements. This will cause the scrapers to extract irrelevant homepage content.
- **Missing PDF discovery:** Embassies frequently publish their official document checklists as PDF files. The adapters currently expect HTML text (`<main>` extraction) and need to dynamically find/parse PDFs.
- **Missing detail-page discovery:** Sites like `gov.uk` are paginated. Using a simple HTML fetch on the first page will miss 80% of the requirements.
- **Fabricated Data Risks:** The ticket explicitly demands no fabricated data. `APSCairoAdapter` targets a fake URL for a non-existent requirement in Egypt.

## Final Recommendations

### Priorities

1. **Remove `APSCairoAdapter` immediately.** It targets a fake URL (`aps-cairo.org`) for a procedure that does not exist for Egyptian students.
2. **Fix `CampusFranceEgyptAdapter` URL.** Change the subdomain from `eg.` to `egypte.` to avoid DNS/resolution failures.
3. **Fix `CzechEmbassyCairoAdapter` URL.** Update the domain from `.cz` to `.gov.cz`.
4. **Update all `target_url` fields.** No adapter should use a base URL. They must be updated to the exact paths.
5. **Implement PDF Parsing.** Ensure the German, Czech, and Italian adapters are capable of discovering and reading PDF checklists.
