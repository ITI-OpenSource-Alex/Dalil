# GOA-030 — catalogue readiness

**Measured 2026-08-11** against the live `rag_db` on the local docker-compose
stack, before any journey ran.

## Why this report exists

GOA-030's acceptance criteria are not satisfiable against demo data. Journey 1
requires matches "backed by a real MastersPortal row with a non-null source
URL"; Journey 2 requires a visa answer that "cites the fetched official
government, embassy, or consular URL"; and the Definition of Done states that
"program, visa, and document rows are **not** inserted directly by the test".

So the catalogue had to be measured before the journeys could mean anything.

## What the last audit found, and what is true now

The 2026-08-09 frontend audit (`reports/frontend-e2e-ux-audit-2026-08-09.md`)
recorded the catalogue as a blocker:

> The live catalogue is demo data: 12 seeded programmes, zero RAG documents, and
> no ingested tables.

That is no longer the state. The MastersPortal (GOA-111) and visa (GOA-108/109/110)
ingestion handoffs have since run against this stack.

| Metric | Audit, 2026-08-09 | Measured, 2026-08-11 |
|---|---|---|
| `program_requirements` total | 12 | **3,805** |
| …of which non-seed (`source_url` not `goa.internal`) | 0 | **3,793** |
| Computer Science rows | 9 | **2,082** |
| Engineering rows | **0** | **1,720** |
| `documents` (RAG chunks) | 0 | **3,979** |
| `visa_requirements` | 0 | **19** |
| `visa_sources` active | 9 (config only) | **35** |

Every non-seed programme row carries a `www.mastersportal.com` source URL and a
`last_scraped_at`. Every `visa_requirements` row carries `extraction_evidence`,
which is the guard that the model quoted a fetched page rather than answering
from memory.

**No ingestion run was performed as part of GOA-030.** The data was already
present; this report measures it rather than producing it. That is worth stating
plainly, because the ticket's DoD anticipated the run being necessary and it was
not.

## Country coverage (top 12 by programme count)

| Country | Programmes | Visa data |
|---|---|---|
| United Kingdom | 1,777 | — |
| Germany | 311 | ✅ ×2 (EU portal, Fintiba blocked account) |
| Ireland | 172 | ✅ |
| Netherlands | 170 | ✅ |
| Italy | 156 | ✅ |
| France | 148 | ✅ |
| Sweden | 140 | — |
| Spain | 111 | — |
| Finland | 98 | ✅ |
| Austria | 74 | ✅ |
| Belgium | 71 | ✅ |
| Portugal | 68 | — |

## Visa sources actually ingested

19 rows across 18 countries, all with evidence quotes:

- **17** from `home-affairs.ec.europa.eu` — the European Commission's EU
  Immigration Portal
- **1** from `studyinromania.gov.ro` — Romanian government
- **1** from `www.fintiba.com` — German blocked-account provider

The first two are unambiguously "official government"; the Fintiba row is a
commercial provider of a legally-required instrument, and Journey 1 treats it as
supporting evidence rather than as the official source. Journey 2 requires a
government/embassy/consular host specifically, and excludes aggregators.

## The defect this measurement exposed

The data being present did **not** mean it was reachable. A Germany student-visa
question through the real chat path returned four MastersPortal programme pages
and **zero visa documents**, even though the correct EU-portal chunk scores
0.854 — the highest similarity in the entire corpus.

`documents_embedding_idx` is IVFFlat with `lists=100`, and `rag_ivfflat_probes`
shipped at **1**, so every production query scanned roughly 1% of the index.
With 3,903 university chunks against 19 visa chunks, the visa cluster was never
probed.

Full measurement in [GOA-030-probes-sweep.json](GOA-030-probes-sweep.json),
harness in `perf/rag_probes_bench.py`:

| probes | recall@5 | visa recall | programme recall | p50 ms | p95 ms |
|---|---|---|---|---|---|
| **1** (shipped) | 0.40 | **0.25** | 1.00 | 1949.2 | 4570.3 |
| 5 | 0.90 | 0.88 | 1.00 | 1873.9 | 2250.8 |
| **10** (now default) | **1.00** | **1.00** | 1.00 | **1805.0** | **2149.7** |
| 20 | 1.00 | 1.00 | 1.00 | 2028.3 | 2773.6 |
| 50 | 1.00 | 1.00 | 1.00 | 2206.2 | 2686.0 |

There is no trade-off: 10 beats 1 on recall **and** on latency. 10 is
`sqrt(lists)`, pgvector's documented guidance.

GOA-137 had measured dense Recall@10 = 1.00 on the frozen eval corpus and
correctly concluded no gain was available there. That measurement does not
generalise — the frozen corpus is small enough that one cluster covers it, so it
*cannot* express this failure. The live catalogue can.

After the fix, the same question through the Gateway with no override headers
cites `home-affairs.ec.europa.eu` (3 chunks) plus Fintiba, and end-to-end chat
latency for that query dropped from **101s to 34s**.

## Reproducing

```bash
docker compose exec -T postgres psql -U goa -d rag_db -c "
  SELECT
    (SELECT count(*) FROM program_requirements) AS programs,
    (SELECT count(*) FROM program_requirements
       WHERE source_url NOT LIKE '%goa.internal%') AS non_seed,
    (SELECT count(*) FROM documents) AS documents,
    (SELECT count(*) FROM visa_requirements) AS visa_reqs;"
```

```bash
python perf/rag_probes_bench.py --out perf/reports/GOA-030-probes-sweep.json
```
