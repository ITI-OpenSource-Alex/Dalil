import json
import structlog
from app.core.database import db

logger = structlog.get_logger("rag_service.visa_finance")

_VISA_FINANCE_CACHE: dict[str, list[dict]] = {}

def clear_visa_finance_cache():
    _VISA_FINANCE_CACHE.clear()

async def get_student_visa_finance(country: str, conn=None) -> list[dict]:
    """Fetch all student visa rows for a country and render financial items (memoized per country)."""
    if country in _VISA_FINANCE_CACHE:
        return _VISA_FINANCE_CACHE[country]

    query = """
        SELECT country, visa_type, issuing_body, proof_of_funds, source_url, last_verified_at
        FROM visa_requirements
        -- No visa_type filter. Every row here derives from visa_sources, which IS the
        -- student-visa source registry, so the filter was redundant — and actively
        -- harmful: real visa types are 'Blocked Account' (Germany), 'Residence Permit
        -- (Studies)' (Sweden) and 'Residence Permit (Study)' (Netherlands), none of
        -- which match ILIKE '%student%'. Only the UK's 'Student Visa' did, so three of
        -- four countries' proof-of-funds data was invisible to /score and /match.
        WHERE country = $1
          AND proof_of_funds IS NOT NULL
        ORDER BY issuing_body
    """
    
    close_conn = False
    if conn is None:
        if db.pool is None:
            return []
        conn = await db.pool.acquire()
        close_conn = True
        
    try:
        rows = await conn.fetch(query, country)
        items = []
        for r in rows:
            pof = r["proof_of_funds"]
            if isinstance(pof, str):
                pof = json.loads(pof)
            
            if not pof or not isinstance(pof, dict):
                continue
                
            pathways = pof.get("pathways", [])
            messages = []
            for p in pathways:
                ptype = p.get("pathway", "")
                amounts_str = []
                for amt in p.get("amounts", []):
                    val = amt.get("amount")
                    curr = amt.get("currency", "")
                    per = amt.get("period", "")
                    qual = f" ({amt['qualifier']})" if amt.get("qualifier") else ""
                    amounts_str.append(f"{val} {curr} {per}{qual}")

                # Proof-of-funds is the requirement Egyptian applicants must plan months
                # ahead for, so a pathway with no published figure and no accepted
                # evidence is not actionable — it produced items reading "requires proof
                # of financial proof via self_funded", which tells the student nothing.
                # Skip it and let the source's URL be fixed to a page that has amounts.
                if not amounts_str and not p.get("accepted_evidence"):
                    logger.warning(
                        "visa_pathway_without_amounts",
                        country=r["country"],
                        issuing_body=r["issuing_body"],
                        pathway=ptype,
                        source_url=r["source_url"],
                    )
                    continue

                amt_desc = ", ".join(amounts_str) if amounts_str else "documented financial evidence"
                messages.append(f"requires proof of {amt_desc} via {ptype}")

            # No actionable pathway left -> emit no item at all, rather than a
            # contentless one. GOA-108: absent facts stay absent.
            if not messages:
                continue

            summary_msg = f"{r['visa_type']} ({r['issuing_body']}) " + "; ".join(messages)
            
            items.append({
                "type": "informational",
                "country": r["country"],
                "issuing_body": r["issuing_body"],
                "message": summary_msg,
                "source_url": r["source_url"],
                "last_verified_at": r["last_verified_at"].isoformat() if r["last_verified_at"] else None,
            })
        _VISA_FINANCE_CACHE[country] = items
        return items
    except Exception as e:
        logger.error("Failed to fetch student visa finance", country=country, error=str(e))
        return []
    finally:
        if close_conn:
            await db.pool.release(conn)
