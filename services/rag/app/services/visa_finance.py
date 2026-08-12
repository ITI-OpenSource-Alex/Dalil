import json
import structlog
from app.core.database import db

logger = structlog.get_logger("rag_service.visa_finance")

_VISA_FINANCE_CACHE: dict[str, list[dict]] = {}

def clear_visa_finance_cache():
    _VISA_FINANCE_CACHE.clear()


# The extractor stores machine-shaped values -- 11904.0, "per_month",
# "self_funded". Rendering those verbatim put "11904.0 EUR per_month" in front of
# a student. These map to how the figure is actually spoken; they change
# presentation only, and an unrecognised value falls through unchanged rather
# than being dropped.
_PERIOD_WORDS = {
    "per_month": "per month",
    "per_year": "per year",
    "per_semester": "per semester",
    "per_week": "per week",
    "total": "in total",
    "one_off": "one-off",
}

_CURRENCY_SYMBOLS = {"EUR": "€", "GBP": "£", "USD": "$"}


def _format_amount(amt: dict) -> str | None:
    """Render one amount the way a student would read it.

    Returns None when there is no number: a blank figure must not render as an
    empty requirement, and the caller already treats a pathway with no amounts
    and no evidence as unusable.
    """
    value = amt.get("amount")
    if value is None:
        return None

    # Money extracted as 11904.0 is a whole number; keep decimals only when they
    # carry information.
    if isinstance(value, (int, float)):
        number = f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"
    else:
        number = str(value)

    currency = amt.get("currency") or ""
    symbol = _CURRENCY_SYMBOLS.get(currency)
    money = f"{symbol}{number}" if symbol else f"{number} {currency}".strip()

    period = _PERIOD_WORDS.get(amt.get("period") or "", amt.get("period") or "")
    qualifier = f" ({amt['qualifier']})" if amt.get("qualifier") else ""
    return f"{money} {period}{qualifier}".replace("  ", " ").strip()

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
                    rendered = _format_amount(amt)
                    if rendered:
                        amounts_str.append(rendered)

                # An official source can require sufficient funds without publishing a
                # number.  That is still a real, source-backed *informational* gap and is
                # exactly what GOA-047's walkthrough must distinguish from a zero amount.
                # Preserve its evidence quote and say explicitly that this source has no
                # figure; do not turn absence into 0 or silently prefer a commercial
                # provider just because it publishes a number.
                if not amounts_str and not p.get("accepted_evidence"):
                    notes = str(p.get("notes") or "").strip()
                    if notes:
                        messages.append(
                            f"requires {notes}; no amount is published by this source"
                        )
                        continue
                    logger.warning(
                        "visa_pathway_without_amounts",
                        country=r["country"],
                        issuing_body=r["issuing_body"],
                        pathway=ptype,
                        source_url=r["source_url"],
                    )
                    continue

                amt_desc = ", ".join(amounts_str) if amounts_str else "documented financial evidence"
                pathway_words = ptype.replace("_", "-") if ptype else ""
                messages.append(
                    f"requires proof of {amt_desc} via {pathway_words}"
                    if pathway_words
                    else f"requires proof of {amt_desc}"
                )

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
