"""Applicant profile — stores all personal data needed to auto-fill job applications.

Loaded from environment variables + optional JSON profile file.
"""
import os
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Default profile path
_PROFILE_PATH = os.getenv("APPLICANT_PROFILE_PATH", "applicant_profile.json")


def _load_from_file() -> Dict:
    """Load profile from JSON file if it exists."""
    path = os.getenv("APPLICANT_PROFILE_PATH", _PROFILE_PATH)
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load profile from %s: %s", path, e)
    return {}


def _load_from_env() -> Dict:
    """Build profile from environment variables."""
    return {
        "first_name": os.getenv("APPLICANT_FIRST_NAME", ""),
        "last_name": os.getenv("APPLICANT_LAST_NAME", ""),
        "email": os.getenv("APPLICANT_EMAIL", os.getenv("GMAIL_FROM", "")),
        "phone": os.getenv("APPLICANT_PHONE", ""),
        "linkedin_url": os.getenv("APPLICANT_LINKEDIN_URL", ""),
        "github_url": os.getenv("APPLICANT_GITHUB_URL", ""),
        "portfolio_url": os.getenv("PORTFOLIO_URL", ""),
        "website": os.getenv("APPLICANT_WEBSITE", os.getenv("PORTFOLIO_URL", "")),
        "address": {
            "street": os.getenv("APPLICANT_STREET", ""),
            "city": os.getenv("APPLICANT_CITY", ""),
            "state": os.getenv("APPLICANT_STATE", ""),
            "zip": os.getenv("APPLICANT_ZIP", ""),
            "country": os.getenv("APPLICANT_COUNTRY", "United States"),
        },
        "current_title": os.getenv("APPLICANT_CURRENT_TITLE", ""),
        "current_company": os.getenv("APPLICANT_CURRENT_COMPANY", ""),
        "years_experience": os.getenv("APPLICANT_YEARS_EXPERIENCE", ""),
        "education": {
            "degree": os.getenv("APPLICANT_DEGREE", ""),
            "major": os.getenv("APPLICANT_MAJOR", ""),
            "school": os.getenv("APPLICANT_SCHOOL", ""),
            "grad_year": os.getenv("APPLICANT_GRAD_YEAR", ""),
        },
        "work_authorization": os.getenv("APPLICANT_WORK_AUTH", "F1 OPT STEM"),
        "sponsorship_needed": os.getenv("APPLICANT_SPONSORSHIP_NEEDED", "yes"),
        "salary_expectation": os.getenv("APPLICANT_SALARY", ""),
        "start_date": os.getenv("APPLICANT_START_DATE", "Immediately"),
        "willing_to_relocate": os.getenv("APPLICANT_RELOCATE", "yes"),
        "gender": os.getenv("APPLICANT_GENDER", ""),
        "race_ethnicity": os.getenv("APPLICANT_RACE", ""),
        "veteran_status": os.getenv("APPLICANT_VETERAN", "No"),
        "disability_status": os.getenv("APPLICANT_DISABILITY", ""),
        "resume_path": os.getenv("RESUME_PATH", ""),
        "cover_letter_path": os.getenv("COVER_LETTER_PATH", ""),
    }


# Cached profile singleton
_profile: Optional[Dict] = None


def get_profile() -> Dict:
    """Return the merged applicant profile (file overrides env defaults)."""
    global _profile
    if _profile is not None:
        return _profile

    env_data = _load_from_env()
    file_data = _load_from_file()

    # file_data overrides env_data where present
    merged = {**env_data}
    for key, val in file_data.items():
        if isinstance(val, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **val}
        elif val:  # only override if non-empty
            merged[key] = val

    _profile = merged
    return _profile


def get_full_name() -> str:
    p = get_profile()
    return f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()


def get_cover_letter_text(job: Dict) -> str:
    """Generate a simple cover letter for the job using the profile.

    Uses OpenAI if available, else falls back to a template.
    """
    p = get_profile()
    name = get_full_name()
    company = job.get("company", "your company")
    title = job.get("title", "the open role")

    # Try LLM generation
    try:
        import openai
        if os.getenv("OPENAI_API_KEY"):
            client = openai.OpenAI()
            prompt = (
                f"Write a concise professional cover letter (150 words max) for {name} "
                f"applying to the {title} role at {company}. "
                f"Candidate has experience in: {p.get('current_title', 'the field')}. "
                f"Emphasize relevant skills and enthusiasm. "
                f"Do NOT include date, address headers, or signature block — just the letter body."
            )
            resp = client.chat.completions.create(
                model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.3,
            )
            return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.debug("LLM cover letter generation failed: %s", e)

    # Fallback template
    return (
        f"Dear Hiring Manager,\n\n"
        f"I am writing to express my strong interest in the {title} position at {company}. "
        f"With my background in {p.get('current_title', 'the field')} and hands-on experience "
        f"with OKTA, DFIR, SIEM, and EDR technologies, I am confident in my ability to "
        f"contribute effectively to your team.\n\n"
        f"I bring a proven track record of building AI-powered forensic tooling and "
        f"managing incident response operations under compliance frameworks. "
        f"I would welcome the opportunity to discuss how my skills align with your needs.\n\n"
        f"Thank you for your consideration.\n\n"
        f"Best regards,\n{name}"
    )


# Common EEO / demographic answer mappings
EEO_ANSWERS = {
    "gender": {
        "male": ["male", "man"],
        "female": ["female", "woman"],
        "non-binary": ["non-binary", "nonbinary", "non binary"],
        "prefer_not": ["prefer not", "decline"],
    },
    "veteran": {
        "yes": ["yes", "am a veteran", "protected veteran"],
        "no": ["no", "not a veteran", "am not"],
    },
    "disability": {
        "yes": ["yes", "have a disability"],
        "no": ["no", "do not have"],
        "prefer_not": ["prefer not", "decline"],
    },
}
