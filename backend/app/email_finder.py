import os
import re
import httpx
import logging
from typing import Optional
from .smtp_verify import smtp_verify
from .apollo_client import find_recruiter_via_apollo
from .clearbit_client import find_person_clearbit

logger = logging.getLogger(__name__)


def _normalize_company_domain(company: str) -> Optional[str]:
    # crude heuristic: if company contains a known domain, use that; else guess by company name
    company = (company or "").strip()
    # simple domain extract
    m = re.search(r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}", company)
    if m:
        return m.group(0)
    # fallback: remove non-alpha and append .com
    s = re.sub(r"[^A-Za-z0-9]", "", company).lower()
    if not s:
        return None
    return f"{s}.com"


def _guess_emails_for_name(name: str, domain: str) -> list:
    """Given candidate name and domain, return common guessed email patterns."""
    if not name or not domain:
        return []
    parts = name.strip().split()
    if len(parts) == 1:
        first = parts[0]
        last = ""
    else:
        first = parts[0]
        last = parts[-1]
    first = re.sub(r"[^A-Za-z]", "", first).lower()
    last = re.sub(r"[^A-Za-z]", "", last).lower()
    patterns = []
    if first and last:
        patterns += [f"{first}.{last}@{domain}", f"{first}{last}@{domain}", f"{first[0]}{last}@{domain}", f"{first}@{domain}"]
    else:
        if first:
            patterns.append(f"{first}@{domain}")
    return patterns


def _hunter_verify(email: str) -> bool:
    key = os.getenv("HUNTER_API_KEY")
    if not key:
        return False
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get("https://api.hunter.io/v2/email-verifier", params={"email": email, "api_key": key})
            if r.status_code == 200:
                data = r.json()
                status = data.get("data", {}).get("status")
                return status in ("valid", "webmail")
    except Exception:
        return False
    return False


def find_recruiter_email(company: str, person_name: Optional[str] = None) -> Optional[str]:
    """Attempt to find a recruiter email for a given company and optional person name.

    Priority order:
    1. Apollo.io people search (if APOLLO_API_KEY set)
    2. Clearbit enrichment on guessed emails (if CLEARBIT_KEY set)
    3. Hunter.io domain search / verify (if HUNTER_API_KEY set)
    4. Guess common patterns and verify via SMTP ping
    5. Return first plausible unverified guess
    """
    domain = _normalize_company_domain(company)
    if not domain:
        return None

    # 1. Apollo.io
    try:
        apollo_email = find_recruiter_via_apollo(company)
        if apollo_email:
            logger.info("Apollo found recruiter email: %s", apollo_email)
            return apollo_email
    except Exception as e:
        logger.debug("Apollo search error: %s", e)

    candidates = []
    # If person_name given, start with those guesses
    if person_name:
        candidates += _guess_emails_for_name(person_name, domain)

    # Add generic recruiter / talent addresses
    candidates += [f"recruiter@{domain}", f"jobs@{domain}", f"talent@{domain}", f"careers@{domain}"]

    # de-dupe while preserving order
    seen = set()
    filtered = []
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        filtered.append(c)

    # 2. Clearbit enrichment on candidates
    for email in filtered:
        try:
            info = find_person_clearbit(email)
            if info and info.get("name"):
                logger.info("Clearbit verified: %s (%s)", email, info.get("name"))
                return email
        except Exception:
            pass

    # 3. Hunter verification
    for email in filtered:
        if _hunter_verify(email):
            logger.info("Hunter verified: %s", email)
            return email

    # 4. SMTP ping verification
    for email in filtered:
        try:
            if smtp_verify(email, timeout=8):
                logger.info("SMTP verified: %s", email)
                return email
        except Exception:
            pass

    # 5. Return first guess (unverified)
    return filtered[0] if filtered else None
