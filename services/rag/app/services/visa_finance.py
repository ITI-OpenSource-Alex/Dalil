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
        WHERE country = $1 
          AND visa_type ILIKE '%student%' 
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
                
                amt_desc = ", ".join(amounts_str) if amounts_str else "financial proof"
                messages.append(f"requires proof of {amt_desc} via {ptype}")
            
            summary_msg = f"{r['visa_type']} ({r['issuing_body']}) " + "; ".join(messages) if messages else f"Student visa requirements apply for {country}."
            
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
