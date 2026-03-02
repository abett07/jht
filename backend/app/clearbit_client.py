"""Clearbit Enrichment API integration for recruiter discovery."""
import os
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def find_person_clearbit(email: str) -> Optional[dict]:
    """Enrich an email address using Clearbit Person API.

    Returns dict with keys: name, title, company, linkedin, etc.
    Requires CLEARBIT_KEY env variable.
    """
    key = os.getenv("CLEARBIT_KEY")
    if not key:
        return None

    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(
                "https://person.clearbit.com/v2/people/find",
                params={"email": email},
                headers={"Authorization": f"Bearer {key}"},
            )
            if r.status_code == 200:
                data = r.json()
                return {
                    "name": data.get("name", {}).get("fullName"),
                    "title": data.get("employment", {}).get("title"),
                    "company": data.get("employment", {}).get("name"),
                    "linkedin": data.get("linkedin", {}).get("handle"),
                    "email": email,
                }
            return None
    except Exception as e:
        logger.warning("Clearbit lookup failed for %s: %s", email, e)
        return None


def search_company_clearbit(domain: str) -> Optional[dict]:
    """Retrieve company info using Clearbit Company API.

    Requires CLEARBIT_KEY env variable.
    """
    key = os.getenv("CLEARBIT_KEY")
    if not key:
        return None

    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(
                "https://company.clearbit.com/v2/companies/find",
                params={"domain": domain},
                headers={"Authorization": f"Bearer {key}"},
            )
            if r.status_code == 200:
                return r.json()
            return None
    except Exception as e:
        logger.warning("Clearbit company lookup failed for %s: %s", domain, e)
        return None
