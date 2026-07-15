# GOA-086 Official Source Investigation

## Executive Summary

This is a read-only production-readiness investigation. No adapter, test, or
configuration file was changed.

The nine adapters are structurally wired to the correct shared transport base
classes, but their source selection is not production-ready. Eight begin at a
homepage or generic portal, and the two hostnames used for APS Cairo and the
Italian Embassy adapter could not be resolved by the live HTTP checker.

The repository's established convention is to use either a specific content
page (`IELTSOrgAdapter`, `CheveningAdapter`) or a deliberately selected landing
page that discovers constrained detail pages (`DAADAdapter`) or a current PDF
(`StipendiumHungaricumAdapter`). It is not to use a site homepage as a
requirements source.

Confirmed final decisions:

| Adapter | Target/source decision | Pattern | Confidence |
|---|---|---|---|
| German Embassy Cairo | Official study-visa article, then its current English leaflet PDF | StipendiumHungaricum | High |
| APS Cairo | No verified official APS Cairo source found; current host does not resolve | None can be selected without guessing | Low |
| Campus France Egypt | Official Egypt application-procedure article | IELTS | High |
| UKVI Egypt | Official GOV.UK Student visa landing page and its official detail pages | DAAD | High |
| VFS Global Egypt | Verified destination portals, not the generic Egypt selector | DAAD | Medium |
| Fintiba Sperrkonto | Official Fintiba blocked-account article | IELTS | High |
| Czech Embassy Cairo | Official study long-term visa article | IELTS | High |
| Spain Visa Egypt | Official Embassy Cairo National Visas landing page, then its study-visa detail link | DAAD | Medium |
| Italy Embassy Cairo | Official Italian Cultural Institute Cairo study-visa article | IELTS | High |

HTTP-status note: `200` and `404` below were obtained by direct read-only HTTP
checks on 2026-07-15. `403` means the official server rejected the checker; it
does **not** mean the source is absent. `DNS failure` means the hostname could
not be resolved by the checker. Search-index text is identified explicitly and
is not represented as a successful HTTP fetch.

## Per Adapter Investigation

### GermanEmbassyCairoAdapter

#### Step 1 - Current implementation

- Implementation: `services/ingestion/app/adapters/german_embassy_cairo.py`
- `target_url`: `https://kairo.diplo.de`
- Base class: `BaseAdapter`
- Current source type: HTML only.
- Strategy: fetch one homepage; parse `main`, then `#content`, then `body`; use
  all `h2`/`h3` sections and regexes to produce structured records. It does not
  discover the embassy's current leaflet PDF.

#### Step 2 - Official pages investigated

| URL | Why investigated | HTTP status | Relevant |
|---|---|---:|---|
| https://kairo.diplo.de/eg-de/service/05-visaeinreise/2573252-2573252 | Embassy article titled `Studium`; candidate landing source | 200 | Yes |
| https://kairo.diplo.de/resource/blob/2573898/a82d6a8709a01047d704f86112ec24a5/250210-studium-englisch-data.pdf | Current English leaflet linked by that article | 200 | Yes |

#### Step 3 - Verified fields

| Field | Present | Evidence | Exact URL |
|---|---|---|---|
| Required documents | Present | Current official leaflet is explicitly linked as `Leaflet Study Visa for Germany` | https://kairo.diplo.de/eg-de/service/05-visaeinreise/2573252-2573252 |
| Processing time | Present | The official leaflet states a normal processing period | https://kairo.diplo.de/resource/blob/2573898/a82d6a8709a01047d704f86112ec24a5/250210-studium-englisch-data.pdf |
| Proof of funds / blocked account | Present | Official study-visa leaflet is the requirements source; no amount is asserted here without PDF field extraction | https://kairo.diplo.de/resource/blob/2573898/a82d6a8709a01047d704f86112ec24a5/250210-studium-englisch-data.pdf |
| APS | NOT FOUND | Not confirmed from the investigated article/leaflet metadata | Same PDF |
| Appointment URL | Present | Article/leaflet directs applicants to the embassy's application-channel information | https://kairo.diplo.de/eg-de/service/05-visaeinreise/2573252-2573252 |
| Fee | NOT FOUND | No fee value was verified in this investigation | Same PDF |

#### Steps 4 and 5 - Pattern and target

**StipendiumHungaricum Pattern.** The stable official article links a dated,
current requirements PDF. The PDF URL contains a changing resource identifier
and date/version component, so hardcoding it would become stale.

`https://kairo.diplo.de/eg-de/service/05-visaeinreise/2573252-2573252`

↓ discover the currently linked English study leaflet dynamically

↓ parse the PDF

Closest repository precedent: `StipendiumHungaricumAdapter` dynamically finds
its authoritative PDF and uses the inherited binary fetch helper.

### APSCairoAdapter

#### Step 1 - Current implementation

- Implementation: `services/ingestion/app/adapters/aps_cairo.py`
- `target_url`: `https://www.aps-cairo.org`
- Base class: `BaseAdapter`
- Current source type: assumed HTML.
- Strategy: one-page generic heading/body extraction; no discovery.

#### Step 2 - Official pages investigated

| URL | Why investigated | HTTP status | Relevant |
|---|---|---:|---|
| https://www.aps-cairo.org | Current adapter target, checked for an official APS source | DNS failure | No verified source |
| https://www.daad-egypt.org/en/ | Official DAAD Egypt site, checked for an APS Cairo procedure source | Search-index content inspected; no APS procedure found | No |
| https://kairo.diplo.de/eg-de/service/05-visaeinreise/2573252-2573252 | Official German mission study source, checked for APS Cairo referral | 200 | No APS source verified |

#### Step 3 - Verified fields

| Field | Present | Evidence | Exact URL |
|---|---|---|---|
| APS certificate procedure | NOT FOUND | No verified official APS Cairo source was located | N/A |
| Required documents | NOT FOUND | No verified official APS Cairo source was located | N/A |
| Processing time | NOT FOUND | No verified official APS Cairo source was located | N/A |
| Fee | NOT FOUND | No verified official APS Cairo source was located | N/A |
| Interview | NOT FOUND | No verified official APS Cairo source was located | N/A |
| Appointment URL | NOT FOUND | No verified official APS Cairo source was located | N/A |

#### Steps 4 and 5 - Pattern and target

**No pattern can be selected without guessing.** The current domain does not
resolve, and no alternate official APS Cairo procedure source was verified.

**No target URL decision is evidence-supported.** This adapter must remain
unconfigured for live ingestion until the project owner supplies a verified
official APS Cairo source.

Closest repository precedent: none. This is a source-verification blocker, not
a reason to invent a DAAD or Embassy source.

### CampusFranceEgyptAdapter

#### Step 1 - Current implementation

- Implementation: `services/ingestion/app/adapters/campus_france_egypt.py`
- `target_url`: `https://eg.campusfrance.org`
- Base class: `BaseAdapter`
- Current source type: HTML.
- Strategy: generic page extraction plus ordered-list step counting.

#### Step 2 - Official pages investigated

| URL | Why investigated | HTTP status | Relevant |
|---|---|---:|---|
| https://www.egypte.campusfrance.org/en/campus-france-egypt-application-procedure | Official Egypt-specific Études en France procedure | 200 | Yes |

#### Step 3 - Verified fields

| Field | Present | Evidence | Exact URL |
|---|---|---|---|
| Pre-registration | Present | Article says the Études en France platform manages procedures up to visa application | https://www.egypte.campusfrance.org/en/campus-france-egypt-application-procedure |
| Required documents | Present | Article lists identity, academic, language, and experience documents | Same URL |
| Interview | Present | Article's six steps include an invitation to interview at Cairo or Alexandria | Same URL |
| Fee | Present | Article says Campus France provides payment details after file verification; no numeric fee is asserted | Same URL |
| Appointment / platform URL | Present | Article links the Études en France platform | Same URL |
| Proof of funds | NOT FOUND | No proof-of-funds requirement was verified in the article | Same URL |
| Processing time | NOT FOUND | No processing-time commitment was verified | Same URL |

#### Steps 4 and 5 - Pattern and target

**IELTS Pattern.** One official, Egypt-specific content article contains the
procedure and required document information.

Target: `https://www.egypte.campusfrance.org/en/campus-france-egypt-application-procedure`

Closest repository precedent: `IELTSOrgAdapter` - one topic-specific page,
single document extraction.

### UKVISAEgyptAdapter

#### Step 1 - Current implementation

- Implementation: `services/ingestion/app/adapters/uk_visa_egypt.py`
- `target_url`: `https://www.gov.uk`
- Base class: `BaseAdapter`
- Current source type: HTML.
- Strategy: scrape the GOV.UK homepage as one document. No child-page discovery.

#### Step 2 - Official pages investigated

| URL | Why investigated | HTTP status | Relevant |
|---|---|---:|---|
| https://www.gov.uk/student-visa | Canonical Student visa journey | 200 | Yes |
| https://www.gov.uk/student-visa/documents-you-must-provide | Official required-documents child page | 200 | Yes |
| https://www.gov.uk/student-visa/money | Official financial-requirements child page | 200 | Yes |
| https://visa.vfsglobal.com/egy/en/gbr | Egypt-to-UK application-centre portal | 403 | Yes; direct checker access denied |

#### Step 3 - Verified fields

| Field | Present | Evidence | Exact URL |
|---|---|---|---|
| Required documents | Present | Dedicated GOV.UK child page exists in official journey | https://www.gov.uk/student-visa/documents-you-must-provide |
| Proof of funds | Present | Dedicated official `money` child page | https://www.gov.uk/student-visa/money |
| Processing time | Present | Canonical journey links application/decision information | https://www.gov.uk/student-visa |
| Appointment / VAC | Present | GOV.UK says applicants may need a visa application centre; Egypt-specific VFS partner portal exists but returned 403 to checker | https://visa.vfsglobal.com/egy/en/gbr |
| Centre addresses | NOT FOUND | Not extracted from the accessible GOV.UK pages in this investigation | N/A |
| Fee | NOT FOUND | Not asserted without opening the official fee tool for the relevant applicant circumstances | N/A |
| APS | NOT FOUND | No APS requirement verified in UKVI sources | N/A |

#### Steps 4 and 5 - Pattern and target

**DAAD Pattern.** The canonical official landing page intentionally links the
official documents, money, application, and eligibility detail pages. Scraping
the homepage is incorrect; scraping only one child page would be incomplete.

Landing page: `https://www.gov.uk/student-visa`

↓ discover only the official `/student-visa/` child pages needed for the
ticket's fields

↓ scrape each detail page

Closest repository precedent: `DAADAdapter` - selected landing page, constrained
detail URL discovery, one document per detail page.

### VFSGlobalEgyptAdapter

#### Step 1 - Current implementation

- Implementation: `services/ingestion/app/adapters/vfs_global_egypt.py`
- `target_url`: `https://visa.vfsglobal.com/egy/en`
- Base class: `BasePlaywrightAdapter`
- Current source type: rendered HTML.
- Strategy: scrape a generic Egypt selector; find links by matching a hard-coded
  country list in link text/URLs; parse generic headings. It does not start from
  a verified list of destination portals and it returns one multi-country outer
  document.

#### Step 2 - Official pages investigated

| URL | Why investigated | HTTP status | Relevant |
|---|---|---:|---|
| https://visa.vfsglobal.com/egy/en | Current generic Egypt selector | 403 | Yes; direct checker access denied |
| https://visa.vfsglobal.com/egy/en/gbr | Official Egypt-to-UK portal | 403 | Yes; identifies VFS as UKVI partner in official indexed content |
| https://visa.vfsglobal.com/egy/en/ita | Official Egypt-to-Italy portal | Search-index content inspected; direct country-page family returned 403 | Yes |
| https://visa.vfsglobal.com/egy/en/ita/visa-type | Italy visa-type portal, checked for requirements categories | 403 | Yes; indexed official content says it exposes documents, fees, and processing time |

#### Step 3 - Verified fields

| Field | Present | Evidence | Exact URL |
|---|---|---|---|
| Destination-specific visa type | Present | Official Italy portal exposes a visa-type selector | https://visa.vfsglobal.com/egy/en/ita/visa-type |
| Required documents | Present | Official indexed portal text states visa-type pages expose documents required | Same URL |
| Processing time | Present | Official indexed portal text states visa-type pages expose processing times | Same URL |
| Fee | Present | Official indexed portal text states visa-type pages expose fees | Same URL |
| Appointment URL | Present | Destination portals are the official application-centre channel | https://visa.vfsglobal.com/egy/en/gbr |
| Centre addresses | NOT FOUND | Not fetched from a destination detail page because of 403 | N/A |
| Proof of funds | NOT FOUND | Cannot be asserted until a specific destination/visa-type page is read | N/A |
| APS / Declaration of Value / pre-registration | NOT FOUND | These are destination-specific and were not verified on generic VFS pages | N/A |

#### Steps 4 and 5 - Pattern and target

**DAAD Pattern.** VFS is a multi-destination portal. The generic selector is a
landing page, not a requirements document; each verified destination portal is
a detail source.

Landing page: `https://visa.vfsglobal.com/egy/en`

↓ discover only a maintained allow-list of official Egypt destination portals

↓ scrape each destination's visa-type/detail pages

Closest repository precedent: `DAADAdapter`. The current country-name heuristic
is not sufficiently constrained: it omits verified destinations such as the UK
and can follow unrelated external links.

### FintibaSperrkontoAdapter

#### Step 1 - Current implementation

- Implementation: `services/ingestion/app/adapters/fintiba_sperrkonto.py`
- `target_url`: `https://fintiba.com`
- Base class: `BasePlaywrightAdapter`
- Current source type: rendered HTML.
- Strategy: scrape the product homepage and extract broad text/regex matches.

#### Step 2 - Official pages investigated

| URL | Why investigated | HTTP status | Relevant |
|---|---|---:|---|
| https://www.fintiba.com/blocked-account-germany | Official English blocked-account product and FAQ page | 200 | Yes |

#### Step 3 - Verified fields

| Field | Present | Evidence | Exact URL |
|---|---|---|---|
| Blocked account | Present | Article defines and explains the German blocked account | https://www.fintiba.com/blocked-account-germany |
| Proof of funds | Present | Article says the account is proof of financial means for German visa applicants | Same URL |
| Required documents | Present | Article says a valid passport is required to open the account | Same URL |
| Setup fee | Present, but dynamic | Article exposes a setup-fee field; do not store a numeric value unless rendered source supplies one | Same URL |
| Processing / opening time | Present | Article describes online opening and confirmation steps | Same URL |
| Egyptian debit acceptance | NOT FOUND | No Egypt-specific card-acceptance statement was verified | Same URL |
| Sponsor letter | NOT FOUND | No sponsor-letter rule was verified | Same URL |
| Appointment / centre address | NOT FOUND | Provider's online product page does not provide a visa-centre appointment process | Same URL |

#### Steps 4 and 5 - Pattern and target

**IELTS Pattern.** The dedicated official product page contains the provider
facts; a landing-page crawl is unnecessary.

Target: `https://www.fintiba.com/blocked-account-germany`

Closest repository precedent: `IELTSOrgAdapter`.

### CzechEmbassyCairoAdapter

#### Step 1 - Current implementation

- Implementation: `services/ingestion/app/adapters/czech_embassy_cairo.py`
- `target_url`: `https://www.mzv.cz/cairo`
- Base class: `BaseAdapter`
- Current source type: HTML.
- Strategy: scrape the embassy homepage with generic heading/body extraction.

#### Step 2 - Official pages investigated

| URL | Why investigated | HTTP status | Relevant |
|---|---|---:|---|
| https://mzv.gov.cz/cairo/en/visa_and_consular_information/long_term_visa/study_long_term_visa_to_the_czech/index.html | Embassy's dedicated Study Long-Term Visa article | 200 | Yes |

#### Step 3 - Verified fields

| Field | Present | Evidence | Exact URL |
|---|---|---|---|
| Required documents | Present | Article gives passport, photos, and document-preparation requirements | https://mzv.gov.cz/cairo/en/visa_and_consular_information/long_term_visa/study_long_term_visa_to_the_czech/index.html |
| Proof of funds | Present | Article links the Czech MFA's official financial-means supporting-document guidance | Same URL |
| Processing time | Present | Article says the study long-term visa may take up to 60 days | Same URL |
| Appointment URL | Present | Article instructs applicants to book and links the long-term appointment section | Same URL |
| Fee | Present | Article states payment method and links the Embassy fee section | Same URL |
| Interview | NOT FOUND | No interview requirement was verified | Same URL |
| APS / blocked account / Declaration of Value | NOT FOUND | Not stated in the investigated source | Same URL |

#### Steps 4 and 5 - Pattern and target

**IELTS Pattern.** This one official article contains the applicable process and
links its authoritative supplements.

Target: `https://mzv.gov.cz/cairo/en/visa_and_consular_information/long_term_visa/study_long_term_visa_to_the_czech/index.html`

Closest repository precedent: `IELTSOrgAdapter`.

### SpainVisaEgyptAdapter

#### Step 1 - Current implementation

- Implementation: `services/ingestion/app/adapters/spain_visa_egypt.py`
- `target_url`: `https://www.exteriores.gob.es/consulados/elcairo`
- Base class: `BaseAdapter`
- Current source type: HTML.
- Strategy: one generic homepage parse. The path identifies a Consulate, while
  the official Cairo mission is under the Embassy path.

#### Step 2 - Official pages investigated

| URL | Why investigated | HTTP status | Relevant |
|---|---|---:|---|
| https://www.exteriores.gob.es/Embajadas/elcairo/en/Paginas/index.aspx | Official Embassy Cairo site, checked to correct the current path | 403 | Yes; direct checker access denied |
| https://exteriores.gob.es/Embajadas/elcairo/en/ServiciosConsulares/Paginas/Consular/Visados-nacionales-Informacion-general.aspx | Official National Visas landing page | 403 | Yes; official indexed content states study over 90 days requires a national visa |
| https://www.exteriores.gob.es/Embajadas/elcairo/es/ServiciosConsulares/Paginas/index.aspx?scca=Visados&scco=Egipto&scd=140&scs=Visados%20Nacionales%20-%20Visado%20de%20estudios | Candidate official study-visa detail route | 403 | Relevance not content-verified; do not use as final target |

#### Step 3 - Verified fields

| Field | Present | Evidence | Exact URL |
|---|---|---|---|
| National visa / study applicability | Present | National-visa landing page says stays over 90 days for study require a national visa | https://exteriores.gob.es/Embajadas/elcairo/en/ServiciosConsulares/Paginas/Consular/Visados-nacionales-Informacion-general.aspx |
| Required documents | NOT FOUND | The accessible official evidence did not expose the Cairo study-visa checklist | N/A |
| Proof of funds | NOT FOUND | Not verified on Cairo official source | N/A |
| Processing time | NOT FOUND | Not verified on Cairo official source | N/A |
| Fee | NOT FOUND | Not asserted from historical fee PDFs | N/A |
| Appointment URL | NOT FOUND | The Cairo study-visa detail content was access-restricted | N/A |
| Interview / APS / blocked account / Declaration of Value / pre-registration | NOT FOUND | Not verified on Cairo official source | N/A |

#### Steps 4 and 5 - Pattern and target

**DAAD Pattern.** The official Embassy National Visas page is the verified
landing source, and the required student-visa checklist must be discovered from
that Embassy page. A direct study detail URL has not been content-verified and
must not be fabricated.

Landing page: `https://exteriores.gob.es/Embajadas/elcairo/en/ServiciosConsulares/Paginas/Consular/Visados-nacionales-Informacion-general.aspx`

↓ discover the official Embassy Cairo Study Visa detail link dynamically

↓ scrape that detail page

Closest repository precedent: `DAADAdapter`.

### ItalyEmbassyCairoAdapter

#### Step 1 - Current implementation

- Implementation: `services/ingestion/app/adapters/italy_embassy_cairo.py`
- `target_url`: `https://ambcairo.esteri.it`
- Base class: `BaseAdapter`
- Current source type: assumed HTML.
- Strategy: generic homepage/body extraction with a special Declaration of Value
  list-item split.

#### Step 2 - Official pages investigated

| URL | Why investigated | HTTP status | Relevant |
|---|---|---:|---|
| https://ambcairo.esteri.it | Current target | DNS failure | No; hostname is not verified |
| https://iiccairo.esteri.it/it/lingua-e-cultura/studiare-in-italia/visto-per-studio-v-s-u-o-v-n/ | Official Italian Cultural Institute Cairo study-visa procedure | 200 | Yes |
| https://visa.vfsglobal.com/egy/en/ita | Official Egypt-to-Italy VFS portal | Search-index content inspected | Yes |
| https://visa.vfsglobal.com/one-pager/italy/egypt/english/pdf/study-long-requirements.pdf | Official Egypt-to-Italy long-study checklist PDF | 403 | Yes; direct checker access denied |

#### Step 3 - Verified fields

| Field | Present | Evidence | Exact URL |
|---|---|---|---|
| Required documents | Present | Official Cairo article lists visa form, photos, passport, acceptance, insurance, accommodation, and financial evidence | https://iiccairo.esteri.it/it/lingua-e-cultura/studiare-in-italia/visto-per-studio-v-s-u-o-v-n/ |
| Proof of funds | Present | Article lists student/sponsor bank statements and sponsor employment evidence | Same URL |
| Declaration of Value | Present | Article describes when it is required and the document process | Same URL |
| Pre-registration | Present | Article requires university pre-registration through Universitaly | Same URL |
| Appointment URL | Present | Article directs applicants to the official appointment provider after the required stage | Same URL |
| Fee | NOT FOUND | No fee was asserted from this article; separate Embassy/VFS fee pages should be treated as separate sources | Same URL |
| Processing time | NOT FOUND | No processing-time commitment was verified | Same URL |
| Interview | NOT FOUND | No interview requirement was verified in the selected article | Same URL |

#### Steps 4 and 5 - Pattern and target

**IELTS Pattern.** The official Italian Cultural Institute Cairo article is one
Egypt-specific study-visa procedure source and contains the fields that make
this adapter distinctive, including pre-registration and Declaration of Value.

Target: `https://iiccairo.esteri.it/it/lingua-e-cultura/studiare-in-italia/visto-per-studio-v-s-u-o-v-n/`

Closest repository precedent: `IELTSOrgAdapter`.

## Evidence Tables

The preceding per-adapter tables are the field-level evidence tables required
for this investigation. A `NOT FOUND` cell means the field was not verified
from the selected official source; it is not a claim that the rule does not
exist elsewhere.

## Ticket Conflicts

### TICKET CONFLICT DETECTED - APS Cairo source

- Requirement: GOA-086 expects `APSCairoAdapter` to produce APS certificate
  requirements, documents, processing time, and fee where stated.
- Evidence: the configured `https://www.aps-cairo.org` host did not resolve;
  no alternate official APS Cairo procedure source was verified from official
  German Embassy or DAAD Egypt sources.
- Conflict: the ticket requires a live adapter for data whose official Egypt
  source has not been identified. Selecting another source would be fabrication.
- Project-owner decision required: provide a verified official APS Cairo URL or
  confirm the authoritative organization/source.

### TICKET CONFLICT DETECTED - unverified source-specific fields

- Requirement: the ticket names fields such as processing time, fees,
  proof-of-funds details, Egyptian debit acceptance, interview, and centre
  addresses across the adapter set.
- Evidence: several selected official pages do not state all of those fields;
  specifically Campus France does not expose proof-of-funds/processing time,
  Fintiba does not expose Egyptian debit acceptance, and the accessible Spain
  and VFS pages did not yield all destination-specific details.
- Conflict: those fields cannot be populated as universal adapter outputs from
  the selected official pages.
- Project-owner decision required: retain nullable/not-found behavior, or
  supply additional official sources for each missing field. This report does
  not redesign the ticket.

### TICKET CONFLICT DETECTED - Italy current hostname

- Requirement: `ItalyEmbassyCairoAdapter` should scrape Italy Egypt-specific
  visa information.
- Evidence: `https://ambcairo.esteri.it` did not resolve; the verified official
  Italian Cairo study source is on `iiccairo.esteri.it`.
- Conflict: the implementation's configured host cannot be used as a production
  source.
- Project-owner decision required: approve the verified Institute article as
  the source or provide a different official Embassy page.

## Final URL Decisions

| Adapter | Final target decision |
|---|---|
| German Embassy Cairo | `https://kairo.diplo.de/eg-de/service/05-visaeinreise/2573252-2573252` -> dynamically discover current English PDF |
| APS Cairo | No evidence-supported target; blocked pending owner confirmation |
| Campus France Egypt | `https://www.egypte.campusfrance.org/en/campus-france-egypt-application-procedure` |
| UKVI Egypt | `https://www.gov.uk/student-visa` -> discover official `/student-visa/` child pages |
| VFS Global Egypt | `https://visa.vfsglobal.com/egy/en` -> discover only maintained verified destination portals |
| Fintiba Sperrkonto | `https://www.fintiba.com/blocked-account-germany` |
| Czech Embassy Cairo | `https://mzv.gov.cz/cairo/en/visa_and_consular_information/long_term_visa/study_long_term_visa_to_the_czech/index.html` |
| Spain Visa Egypt | `https://exteriores.gob.es/Embajadas/elcairo/en/ServiciosConsulares/Paginas/Consular/Visados-nacionales-Informacion-general.aspx` -> discover official Study Visa detail page |
| Italy Embassy Cairo | `https://iiccairo.esteri.it/it/lingua-e-cultura/studiare-in-italia/visto-per-studio-v-s-u-o-v-n/` |

## Recommended Scraping Pattern

| Adapter | Exactly one pattern | Why |
|---|---|---|
| German Embassy Cairo | StipendiumHungaricum Pattern | Current requirements are published through a stable article and versioned leaflet PDF |
| APS Cairo | No decision | No verified official source exists in the investigation evidence |
| Campus France Egypt | IELTS Pattern | One Egypt-specific procedure article contains the relevant process |
| UKVI Egypt | DAAD Pattern | Official Student visa landing page links distinct official field pages |
| VFS Global Egypt | DAAD Pattern | A landing selector leads to destination-specific portals and visa-type pages |
| Fintiba Sperrkonto | IELTS Pattern | One dedicated official product/FAQ article |
| Czech Embassy Cairo | IELTS Pattern | One dedicated Embassy study-visa article |
| Spain Visa Egypt | DAAD Pattern | Verified Embassy national-visa landing page must locate the study detail page |
| Italy Embassy Cairo | IELTS Pattern | One official Cairo study-visa procedure article contains the core evidence |

## Cross-Repository Pattern Comparison

All existing concrete adapters were reviewed:

| Existing adapter | Architecture | Closest use in this investigation |
|---|---|---|
| `IELTSOrgAdapter` | Specific topic page; parse one main-content document | Campus France, Fintiba, Czech, Italy |
| `CheveningAdapter` | Specific topic page; parse one main-content document | Same single-content-page family |
| `DAADAdapter` | Selected landing/search page -> constrained detail URLs -> detail documents | UKVI, VFS, Spain |
| `MastersPortalAdapter` | Landing page -> discover profile pages | Supports the principle of explicit, constrained discovery rather than homepage scraping |
| `StipendiumHungaricumAdapter` | Landing page -> dynamically discover authoritative PDF -> parse PDF | German Embassy Cairo |
| `StudyInPolandAdapter` | Specific page with content-node fallback | Does not justify using a homepage as the target |

The shared base classes also already provide the correct HTTP client, retries,
robots check, and delay behavior. This investigation does not recommend new
transport logic; it identifies source selection and source-specific extraction
as the production-readiness gaps.

## Confidence Assessment

| Adapter | Confidence | Basis |
|---|---|---|
| German Embassy Cairo | High | Direct 200 article and directly linked current English PDF |
| APS Cairo | Low | Current hostname fails DNS and no substitute official source verified |
| Campus France Egypt | High | Direct 200 official Egypt procedure page |
| UKVI Egypt | High | Direct 200 canonical GOV.UK journey and official child pages |
| VFS Global Egypt | Medium | Official destination portals verified through official indexed content, but direct checker is blocked by 403 and destination coverage must be maintained |
| Fintiba Sperrkonto | High | Direct 200 dedicated official product page |
| Czech Embassy Cairo | High | Direct 200 Embassy study-visa page |
| Spain Visa Egypt | Medium | Correct official Embassy landing page identified, but direct content access was blocked by 403 and the study detail link was not content-verified |
| Italy Embassy Cairo | High | Direct 200 official Italian Cultural Institute Cairo study-visa procedure page; original configured hostname fails DNS |

## Final Verification Pass

Verification performed on 2026-07-15. This pass rechecked only the conclusions
and URLs already documented in this report. It did not search for additional
adapters or introduce additional candidate sources.

### GermanEmbassyCairoAdapter

1. Other candidate rejected: the configured `https://kairo.diplo.de` is the
   mission homepage, not the study-visa requirements content; the dated PDF is
   rejected as a hardcoded target because the Embassy can replace it.
2. Selected source is better: the `Studium` article is the stable official
   content landing page and currently links the English study-visa leaflet.
3. Possible missed official page: a more specific application-provider page
   may exist, but it would not replace the Embassy's authoritative checklist.
4. Change risk: high for the linked PDF; lower for the article path.
5. More stable landing page: the selected `Studium` article is the stable
   landing page and is preferable to its versioned PDF URL.
6. Production-review decision: unchanged.

**VERIFIED** - direct recheck returned HTTP 200 for the selected article.

### APSCairoAdapter

1. Other candidate rejected: no alternate URL was accepted because no official
   APS Cairo procedure page was verified. DAAD Egypt and the German Embassy
   study page are not evidence of an APS Cairo procedure source.
2. Selected source is better: no source is selected; this is preferable to
   falsely treating an unresolved hostname as official.
3. Possible missed official page: yes. The evidence is insufficient to rule
   one out, which is why confidence remains Low.
4. Change risk: complete; a future project-owner-provided official source could
   change the conclusion.
5. More stable landing page: cannot be determined without a verified official
   organization or URL.
6. Production-review decision: unchanged; I would block live source
   configuration rather than guess.

**VERIFIED** - the configured hostname still fails DNS resolution.

### CampusFranceEgyptAdapter

1. Other candidate rejected: `https://eg.campusfrance.org` is not the verified
   Egypt procedure article and the root does not isolate the required process.
2. Selected source is better: it is the official Egypt article and contains
   the procedure, documents, platform, payment-stage, and interview evidence.
3. Possible missed official page: the site has related articles and PDFs, but
   none is needed to replace this complete procedure page.
4. Change risk: moderate; yearly dates and document lists can change.
5. More stable landing page: the selected permanent article path is more stable
   than a dated brochure PDF or a site root.
6. Production-review decision: unchanged.

**VERIFIED** - direct recheck returned HTTP 200.

### UKVISAEgyptAdapter

1. Other candidate rejected: `https://www.gov.uk` is a general homepage; an
   individual child page is incomplete for all ticket fields; the VFS UK portal
   is an application-centre source rather than UKVI's canonical rule source.
2. Selected source is better: the official `student-visa` journey owns and
   links the authoritative documents, money, and application detail pages.
3. Possible missed official page: yes, GOV.UK may add child pages, which is why
   the conclusion is landing-page discovery rather than a fixed child-page set.
4. Change risk: moderate; child pages and fees change.
5. More stable landing page: the selected canonical journey is the stable
   landing page.
6. Production-review decision: unchanged.

**VERIFIED** - direct recheck returned HTTP 200.

### VFSGlobalEgyptAdapter

1. Other candidate rejected: a single destination portal cannot represent all
   VFS Egypt destinations; the generic selector alone is not a requirements
   page; an unbounded country-name link heuristic is not sufficiently safe.
2. Selected source is better: the official Egypt selector is the correct
   landing point for discovery, provided discovery is limited to a maintained
   allow-list of verified destination portals.
3. Possible missed official page: yes. VFS destination coverage can change and
   requires periodic operational verification.
4. Change risk: high; VFS routing, content, and bot controls change often.
5. More stable landing page: no single destination page is more stable for a
   multi-country adapter; the generic Egypt landing page remains correct.
6. Production-review decision: unchanged, with Medium confidence and an
   explicit maintained allow-list requirement.

**VERIFIED** - direct recheck still returns HTTP 403; this confirms an access
restriction, not a replacement source.

### FintibaSperrkontoAdapter

1. Other candidate rejected: `https://fintiba.com` is a broad homepage and may
   vary by locale; support articles are narrower and do not replace the product
   overview.
2. Selected source is better: the blocked-account article is the official,
   English, topic-specific page covering the product and German visa context.
3. Possible missed official page: related support pages exist, but they do not
   supersede the selected primary product page.
4. Change risk: moderate; fees and amounts are commercially and legally
   changeable.
5. More stable landing page: the selected semantic product slug is more stable
   than the homepage.
6. Production-review decision: unchanged.

**VERIFIED** - direct recheck returned HTTP 200.

### CzechEmbassyCairoAdapter

1. Other candidate rejected: `https://www.mzv.cz/cairo` is an embassy homepage;
   linked PDF supplements are narrower than the official Study Long-Term Visa
   article.
2. Selected source is better: it directly states the study process, documents,
   processing period, appointments, and links official supporting guidance.
3. Possible missed official page: supporting financial-means and fee pages
   exist, but they supplement rather than replace the selected article.
4. Change risk: moderate; fees and supporting-document rules can change.
5. More stable landing page: the selected semantic embassy article is the
   stable source page.
6. Production-review decision: unchanged.

**VERIFIED** - direct recheck returned HTTP 200.

### SpainVisaEgyptAdapter

1. Other candidate rejected: the configured `/consulados/elcairo` route is not
   the verified Embassy Cairo path; the unverified guessed study-detail route
   remains rejected because its content was not accessible.
2. Selected source is better: the Embassy Cairo National Visas page is an
   official mission landing source and establishes study's national-visa scope.
3. Possible missed official page: yes. The inaccessible official Study Visa
   detail page may contain the full checklist; this is why confidence remains
   Medium and discovery is required.
4. Change risk: moderate to high; the Embassy can rearrange page links and the
   current checker receives 403 responses.
5. More stable landing page: the selected Embassy National Visas landing page
   is more defensible than an unverified deep URL.
6. Production-review decision: unchanged.

**VERIFIED** - direct recheck still returns HTTP 403; no new source was
substituted without evidence.

### ItalyEmbassyCairoAdapter

1. Other candidate rejected: `https://ambcairo.esteri.it` is rejected because
   it does not resolve; VFS is an application-centre source and does not replace
   the official Cairo study-procedure article.
2. Selected source is better: the Italian Cultural Institute Cairo is an
   official `esteri.it` organization and its specific study-visa page documents
   the Egypt procedure, Universitaly, Declaration of Value, documents, and
   appointment stage.
3. Possible missed official page: yes. Embassy and provider fee/checklist pages
   may supplement this source, but none was verified as a better primary
   procedure page.
4. Change risk: moderate; study cycles, provider links, and document rules can
   change.
5. More stable landing page: the selected semantic study-procedure article is
   more stable than the non-resolving configured hostname or a dated checklist
   PDF.
6. Production-review decision: unchanged.

**VERIFIED** - direct recheck returned HTTP 200 for the selected official
article, while the configured hostname still fails DNS resolution.
