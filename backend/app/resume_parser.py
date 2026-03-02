import re
from typing import List, Dict


EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")


def extract_emails(text: str) -> List[str]:
    return list(dict.fromkeys(EMAIL_RE.findall(text)))


def extract_phones(text: str) -> List[str]:
    phones = PHONE_RE.findall(text)
    # basic cleanup
    return [re.sub(r"\s+", " ", p).strip() for p in phones]


COMMON_SKILLS = [
    "okta",
    "dfir",
    "forensic",
    "siem",
    "edr",
    "python",
    "aws",
    "azure",
    "splunk",
    "xdr",
]


def extract_skills(text: str) -> List[str]:
    lower = text.lower()
    found = [s for s in COMMON_SKILLS if s in lower]
    return found


def parse_experience(text: str) -> List[Dict]:
    # Very small heuristic: find 'experience' section and split by lines with years
    lower = text.lower()
    idx = lower.find("experience")
    if idx == -1:
        # fallback: look for work or professional
        idx = lower.find("work experience")
    if idx == -1:
        return []

    section = text[idx:]
    lines = [l.strip() for l in section.splitlines() if l.strip()]
    exps = []
    cur = None
    for line in lines:
        # crude date detection
        if re.search(r"\b\d{4}\b", line):
            if cur:
                exps.append(cur)
            cur = {"raw": line}
        else:
            if cur:
                cur.setdefault("details", []).append(line)
    if cur:
        exps.append(cur)
    return exps


def parse_resume_text(text: str) -> Dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    name = lines[0] if lines else ""
    emails = extract_emails(text)
    phones = extract_phones(text)
    skills = extract_skills(text)
    experiences = parse_experience(text)

    return {
        "name": name,
        "emails": emails,
        "phones": phones,
        "skills": skills,
        "experiences": experiences,
    }


def parse_pdf_file(path: str) -> Dict:
    """Extract text from a PDF and parse it."""
    from pdfminer.high_level import extract_text
    text = extract_text(path)
    return parse_resume_text(text)


def parse_resume_file(path: str) -> Dict:
    """Auto-detect file type and parse. Supports .txt and .pdf"""
    if path.lower().endswith('.pdf'):
        return parse_pdf_file(path)
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    return parse_resume_text(text)
