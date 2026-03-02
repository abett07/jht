from .matching.embeddings import embed_text, cosine_similarity
import re


# --- F1 STEM OPT visa constraint filters ---
# Jobs containing these phrases are rejected because an F1 OPT holder
# cannot satisfy them.
REJECT_PHRASES = [
    # Citizenship / permanent residency requirements
    "us citizen only",
    "u.s. citizen only",
    "united states citizen",
    "must be a us citizen",
    "must be a u.s. citizen",
    "us persons only",
    "u.s. persons only",
    "green card required",
    "permanent resident only",
    "permanent resident not eligible",
    "citizenship required",
    # Security clearance (requires citizenship)
    "security clearance required",
    "must have security clearance",
    "active clearance required",
    "ts/sci required",
    "top secret clearance",
    "secret clearance required",
    # Sponsorship unavailable (critical for F1 OPT)
    "no visa sponsorship",
    "not able to sponsor",
    "unable to sponsor",
    "cannot sponsor",
    "will not sponsor",
    "does not sponsor",
    "do not sponsor",
    "sponsorship is not available",
    "sponsorship not available",
    "not eligible for sponsorship",
    "without sponsorship",
    "must be authorized to work in the u.s. without",
    "must be authorized to work in the united states without",
    "no sponsorship available",
    "no immigration sponsorship",
    "not offer sponsorship",
    "doesn't sponsor",
]

# Locations outside the USA — reject if the job is clearly non-US
NON_US_INDICATORS = [
    "canada only",
    "uk only",
    "europe only",
    "india only",
    "australia only",
    "remote - uk",
    "remote - canada",
    "remote - europe",
    "remote - india",
    "remote - australia",
]


def _check_rejects(text: str):
    low = text.lower()
    for p in REJECT_PHRASES:
        if p in low:
            return True, f"visa-ineligible: {p}"
    for p in NON_US_INDICATORS:
        if p in low:
            return True, f"non-US location: {p}"
    return False, None


def _skill_overlap(job_text: str, resume_json: dict):
    skills = resume_json.get("skills", []) if resume_json else []
    job_low = job_text.lower()
    count = 0
    for s in skills:
        if not s:
            continue
        if s.lower() in job_low:
            count += 1
    return count


def score_job(job: dict, resume_json: dict, resume_embedding: list | None = None) -> dict:
    """Compute a match score for a job given a parsed resume.

    Returns dict: {match_score: float, reject: bool, reject_reason: str|None}
    """
    # Build plain text representations
    job_text = " ".join(
        filter(None, [job.get("title", ""), job.get("company", ""), job.get("description", ""), job.get("location", "")])
    )
    resume_text = ""
    if resume_json:
        parts = [resume_json.get("name", "")]
        if resume_json.get("skills"):
            parts.append("skills: " + ", ".join(resume_json.get("skills")))
        if resume_json.get("experiences"):
            for e in resume_json.get("experiences")[:5]:
                parts.append(e.get("raw", "") + " " + " ".join(e.get("details", [])))
        resume_text = " ".join(parts)

    # Check rejection phrases
    reject, reason = _check_rejects(job_text)
    if reject:
        return {"match_score": 0.0, "reject": True, "reject_reason": reason}

    # Embedding-based similarity
    emb_job = embed_text(job_text)
    if resume_embedding is None:
        emb_resume = embed_text(resume_text)
    else:
        emb_resume = resume_embedding
    sim = cosine_similarity(emb_job, emb_resume)
    base_score = sim * 100.0

    # Skill overlap bonus
    skill_hits = _skill_overlap(job_text, resume_json or {})
    skill_bonus = min(30.0, skill_hits * 10.0)

    score = min(100.0, base_score + skill_bonus)

    # Additional simple rules: if job mentions DFIR/OKTA and resume lists OKTA/DFIR, add small boost
    jlow = job_text.lower()
    rskills = [s.lower() for s in (resume_json.get("skills") or [])]
    if ("dfir" in jlow or "okta" in jlow) and ("okta" in rskills or "dfir" in rskills):
        score = min(100.0, score + 5.0)

    return {"match_score": float(score), "reject": False, "reject_reason": None}

