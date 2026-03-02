"""Apollo.io people-search API integration for recruiter discovery."""
import os
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

APOLLO_API_URL = "https://api.apollo.io/v1/mixed_people/search"


def search_apollo(company: str, title_keywords: str = "recruiter", limit: int = 3) -> list:
    """Search Apollo.io for people at `company` matching `title_keywords`.

    Returns list of dicts: {name, email, title, linkedin_url}
    Requires APOLLO_API_KEY env variable.
    """
    key = os.getenv("APOLLO_API_KEY")
    if not key:
        return []

    payload = {
        "api_key": key,
        "q_organization_name": company,
        "person_titles": [title_keywords],
        "page": 1,
        "per_page": limit,
    }

    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(APOLLO_API_URL, json=payload)
            r.raise_for_status()
            data = r.json()
            people = data.get("people") or []
            results = []
            for p in people:
                results.append({
                    "name": p.get("name") or f'{p.get("first_name", "")} {p.get("last_name", "")}'.strip(),
                    "email": p.get("email"),
                    "title": p.get("title"),
                    "linkedin_url": p.get("linkedin_url"),
                })
            return results
    except Exception as e:
        logger.warning("Apollo search failed for %s: %s", company, e)
        return []


def find_recruiter_via_apollo(company: str) -> Optional[str]:
    """Convenience: return first email found for a recruiter at `company`."""
    results = search_apollo(company, title_keywords="recruiter")
    for r in results:
        if r.get("email"):
            return r["email"]
    # try talent / HR
    for kw in ["talent acquisition", "HR", "hiring manager"]:
        results = search_apollo(company, title_keywords=kw, limit=1)
        for r in results:
            if r.get("email"):
                return r["email"]
    return None
