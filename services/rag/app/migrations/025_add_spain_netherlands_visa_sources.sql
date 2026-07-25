-- GOA-109 (re-scoped): add Spain and the Netherlands — both verified live through the
-- ingestion adapter's own fetch path and both publishing monetary figures.
--
-- Spain (7 programs in the catalog, the largest uncovered country). The MAEC national
-- consular page is parameterised per country (scco=Egipto) and states the requirement
-- as a multiple of IPREM, which is the legally authoritative form: 100% IPREM/month for
-- the student plus percentages per accompanying family member. Note the Cairo post lives
-- under /Embajadas/ rather than /Consulados/, and the /Consulados/elcairo/ path that
-- earlier attempts assumed simply does not exist.
--
-- Netherlands: IND's required-amounts table publishes the study norm directly
-- (EUR 2,337.00 / 2,523.96 observed). ind.nl/en/income-requirements-study explains the
-- rule but carries no figure, so the amounts table is the correct target — a concrete
-- example of why a source must be verified to publish an amount, not merely to describe
-- the requirement.
--
-- Not added, and why (all fail the fetch gate rather than the design):
--   migri.fi (Finland, 4 programs) - 403 to httpx, Playwright times out
--   france-visas.gouv.fr (France, 5) - 403; campusfrance.org pages carry no figure
--   studyinitaly.esteri.it (Italy, 5)  - 404; ambcairo.esteri.it fetch fails
--   irishimmigration.ie (Ireland, 3)   - 403
-- These need either a browser profile that survives bot protection or dynamic discovery
-- from the site root; both are tracked in the ticket.

INSERT INTO visa_sources (country, visa_type, issuing_body, source_url, fetch_method)
VALUES
    ('Spain', 'Student Visa', 'Spain MAEC Consular Services',
     'https://www.exteriores.gob.es/es/ServiciosAlCiudadano/Paginas/Servicios-consulares.aspx?scco=Egipto&scd=140&scca=Visados&scs=Visados+Nacionales+-+Visado+de+estudios',
     'httpx'),
    ('Netherlands', 'Residence Permit (Study)', 'Immigration and Naturalisation Service (IND)',
     'https://ind.nl/en/required-amounts-income-requirements',
     'httpx')
ON CONFLICT DO NOTHING;
