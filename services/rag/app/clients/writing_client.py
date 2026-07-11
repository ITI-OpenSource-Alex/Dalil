import os
import httpx
import structlog
from typing import Optional


logger = structlog.get_logger("rag_service.writing_client")



async def get_user_cv(user_id: str) -> Optional[str]:
    base_url = os.getenv("WRITING_SERVICE_URL", "http://writing:8000")
    api_key = os.getenv("INTERNAL_API_KEY")
    
    url = f"{base_url}/internal/cv-text/{user_id}"
    headers = {"x-internal-api-key": api_key}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if data.get("hasCv"):
                    return data.get("extractedText")
                return None
            else:
                logger.warning(f"Failed to fetch CV for {user_id}: status {response.status_code}")
                return None
    except Exception as e:
        logger.error(f"Error fetching CV from Writing Service: {str(e)}")
        return None