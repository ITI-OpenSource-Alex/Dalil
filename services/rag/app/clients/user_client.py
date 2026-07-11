import os
import httpx
import structlog
from typing import Optional
logger = structlog.get_logger("rag_service.user_client")


class UserServiceUnavailable(Exception):
    pass

async def get_user_profile(user_id: str) -> Optional[dict]:
    base_url = os.getenv("USER_SERVICE_URL", "http://user-service:8081")
    api_key = os.getenv("INTERNAL_API_KEY")
    url = f"{base_url}/users/{user_id}"
    headers = {"x-internal-api-key": api_key}


    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=5.0)
            
            if response.status_code == 200:
                user_data = response.json()
                profile = user_data.get("profile")
                if not profile:
                    return None
                    
                # Clean mapping into our internal schema representation
                return {
                    "userId": user_data["id"],
                    "degreeLevel": profile.get("degreeLevel"),
                    "gpa": profile.get("gpa"),
                    "ieltsScore": profile.get("ieltsScore"),
                    "targetCountries": profile.get("targetCountries", []),
                    "fieldOfStudy": profile.get("fieldOfStudy"),
                    "ects": profile.get("ects"),
                    "workExperienceYears": profile.get("workExperienceYears", 0),
                    "extracurricularsScore": profile.get("extracurricularsScore", 0),
                    "gpaScale": profile.get("gpaScale", "100"),
                    "citizenship": None # Not yet provided by User Service
                }
            elif response.status_code == 404:
                return None
            else:
                logger.error(f"User service returned {response.status_code}")
                raise UserServiceUnavailable(f"User service returned {response.status_code}")
                
    except httpx.RequestError as e:
        logger.error(f"Connection to User Service failed: {str(e)}")
        # Explicit 503 distinction so we don't accidentally treat outages as 404s!
        raise UserServiceUnavailable("User Service is currently unavailable.")