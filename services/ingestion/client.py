import logging
import requests
from config import settings

logger = logging.getLogger('ingestion_worker.client')

def get_headers() -> dict:
    """Returns headers required to communicate with RAG service internal endpoints."""
    return {
         "Content-Type": "application/json",
        "X-Internal-Api-Key": settings.internal_api_key
    }

def fetch_visa_sources() -> list[dict]:
    """
    Fetches the active visa source config rows (GOA-116) from the RAG service.
    The generic VisaSourceAdapter crawls whatever this returns instead of shipping one
    bespoke scraper class per embassy site. Returns a list of dicts matching the
    VisaSource schema. Raises on transport/HTTP failure so the caller marks the whole
    adapter failed rather than silently crawling nothing.
    """

    url = f"{settings.rag_service_url}/internal/visa-sources"
    headers = get_headers()

    try:
        logger.info("Fetching visa sources from RAG service at %s", url)
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.json().get("sources", [])
        logger.error(
            "RAG visa-sources endpoint failed with status %d: %s",
            response.status_code,
            response.text,
        )
        response.raise_for_status()
    except Exception as e:
        logger.error("Failed to connect to RAG visa-sources endpoint: %s", str(e))
        raise e


def check_existing_chunks(ids: list[str]) -> list[str]:
    """
    Calls the RAG service's check-existing endpoint to determine which document
    chunk IDs are already present in the database.
    Returns a list of IDs (as strings) that already exist.
    """
     
    if not ids:
        return []
     
    url = f"{settings.rag_service_url}/internal/documents/check-existing"
    headers = get_headers()
    payload = {"ids": ids}

    try:
        logger.info("Checking existence of %d chunks at %s", len(ids), url)
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get("existing_ids", [])
        else:
            logger.error("RAG check-existing endpoint failed with status %d: %s", response.status_code, response.text)
            response.raise_for_status()
    except Exception as e:
        logger.error("Failed to connect to RAG check-existing endpoint: %s", str(e))
        raise e


def get_document_stats() -> dict:
    """Read corpus readiness through the RAG service ownership boundary."""
    url = f"{settings.rag_service_url}/internal/documents/stats"
    response = requests.get(url, headers=get_headers(), timeout=15)
    response.raise_for_status()
    return response.json()
    
def upsert_visa_requirement(record: dict) -> dict:
    """
    Calls the RAG service's internal visa-requirements endpoint to upsert a single
    structured visa requirements record. `record` is a dict matching the
    VisaRequirementsRequest schema. Returns True if the upsert succeeded.
    """

    url = f"{settings.rag_service_url}/internal/visa-requirements"
    headers = get_headers()

    try:
        logger.info("Upserting visa requirement to RAG service at %s", url)
        response = requests.post(url, json=record, headers=headers, timeout=15)

        if response.status_code == 200:
            logger.info("Successfully upserted visa requirement to RAG database")
            return response.json()
        else:
            logger.error("RAG visa-requirements endpoint failed with status %d: %s", response.status_code, response.text)
            response.raise_for_status()
    except Exception as e:
        logger.error("Failed to connect to RAG visa-requirements endpoint: %s", str(e))
        raise e

def upsert_program_requirement(record: dict) -> dict:
    """
    Calls the RAG service's internal program-requirements endpoint to upsert a single
    structured program requirements record. `record` is a dict matching the
    ProgramRequirementsUpsertRequest schema. Returns True if the upsert succeeded.
    """

    url = f"{settings.rag_service_url}/internal/program-requirements"
    headers = get_headers()

    try:
        logger.info("Upserting program requirement to RAG service at %s", url)
        response = requests.post(url, json=record, headers=headers, timeout=15)

        if response.status_code == 200:
            logger.info("Successfully upserted program requirement to RAG database")
            return response.json()
        else:
            logger.error("RAG program-requirements endpoint failed with status %d: %s", response.status_code, response.text)
            response.raise_for_status()
    except Exception as e:
        logger.error("Failed to connect to RAG program-requirements endpoint: %s", str(e))
        raise e

def upsert_scholarship_program(record: dict) -> dict:
    """
    Calls the RAG service's internal scholarship-programs endpoint to upsert a single
    structured scholarship program record. `record` is a dict matching the
    ScholarshipProgramUpsertRequest schema. Returns True if the upsert succeeded.
    """

    url = f"{settings.rag_service_url}/internal/scholarship-programs"
    headers = get_headers()

    try:
        logger.info("Upserting scholarship program to RAG service at %s", url)
        response = requests.post(url, json=record, headers=headers, timeout=15)

        if response.status_code == 200:
            logger.info("Successfully upserted scholarship program to RAG database")
            return response.json()
        else:
            logger.error("RAG scholarship-programs endpoint failed with status %d: %s", response.status_code, response.text)
            response.raise_for_status()
    except Exception as e:
        logger.error("Failed to connect to RAG scholarship-programs endpoint: %s", str(e))
        raise e

def upsert_chunks(chunks: list[dict]) -> dict:
    """
    Calls the RAG service's internal documents endpoint to bulk upsert chunks.
    `chunks` is a list of dictionaries matching the DocumentUpsertItem schema.
    Returns True if the upsert succeeded.
    """

    if not chunks:
        return {"status": "success", "count": 0, "added": 0, "updated": 0}
    
    url = f"{settings.rag_service_url}/internal/documents"
    headers = get_headers()
    payload = {"documents": chunks}

    try:
        logger.info("Upserting %d chunks to RAG service at %s", len(chunks), url)
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        
        if response.status_code == 200:
            logger.info("Successfully upserted %d chunks to RAG database", len(chunks))
            return response.json()
        else:
            logger.error("RAG documents upsert endpoint failed with status %d: %s", response.status_code, response.text)
            response.raise_for_status()
    except Exception as e:
        logger.error("Failed to connect to RAG documents upsert endpoint: %s", str(e))
        raise e


def touch_visa_requirement(sources: list[dict]) -> bool:
    """
    Calls the RAG service's internal /internal/visa-requirements/touch endpoint
    to refresh last_verified_at for unchanged visa sources.
    `sources` is a list of dicts carrying country, visa_type, and issuing_body.
    """
    if not sources:
        return True

    url = f"{settings.rag_service_url}/internal/visa-requirements/touch"
    headers = get_headers()

    try:
        logger.info("Sending touch request for %d sources to RAG service at %s", len(sources), url)
        response = requests.post(url, json=sources, headers=headers, timeout=15)
        if response.status_code == 200:
            logger.info("Successfully touched %d visa requirement rows", len(sources))
            return True
        else:
            logger.warning("RAG touch endpoint returned status %d: %s", response.status_code, response.text)
            return False
    except Exception as e:
        logger.warning("Failed to connect to RAG touch endpoint: %s", str(e))
        return False


def delete_documents_by_source_url(source_url: str) -> int:
    """Remove lower-tier chunks so a richer Tier 2 document replaces them."""
    url = f"{settings.rag_service_url}/internal/documents"
    try:
        response = requests.delete(
            url,
            params={"source_url": source_url},
            headers=get_headers(),
            timeout=15,
        )
        response.raise_for_status()
        return int(response.json().get("deleted", 0))
    except Exception as e:
        logger.error("Failed to delete existing chunks for %s: %s", source_url, e)
        raise
