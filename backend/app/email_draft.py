import os
import json
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

try:
    import openai
    _HAS_OPENAI = True
except Exception:
    _HAS_OPENAI = False


def _fallback_draft(job: dict, resume_json: dict, recruiter_name: str | None = None) -> Tuple[str, str]:
    # Simple 120-word-ish fallback email
    name = recruiter_name or job.get("company") or "Recruiter"
    subject = f"Interest: {job.get('title')} — {job.get('company')}"
    body = (
        f"Hi {name},\n\nI'm writing about the {job.get('title')} role at {job.get('company')}. "
        "I have hands-on OKTA DFIR experience, built AI forensic tooling for incident investigations, "
        "and operated SIEM + EDR stacks in production under compliance frameworks. "
        "I'm confident I can contribute immediately — brief resume attached. "
        "Can we schedule a quick 15-minute call this week?\n\nThanks,\n[Your Name]"
    )
    return subject, body


def generate_email(job: dict, resume_json: dict | None = None, recruiter_name: str | None = None) -> Tuple[str, str]:
    """Return (subject, body) for an outbound email tailored to `job` and `resume_json`.

    Uses OpenAI if configured; otherwise falls back to a deterministic template.
    """
    if _HAS_OPENAI and os.getenv("OPENAI_API_KEY"):
        prompt = (
            "You are a concise professional recruiter outreach assistant. "
            "Given a job posting and a candidate resume summary, produce an email subject and a short email body of about 120 words (concise). "
            "Include the candidate's OKTA DFIR experience, AI forensic tooling, SIEM + EDR skills, and relevant compliance frameworks. "
            "Address the recruiter by name if provided. Output JSON like: {\"subject\": \"...\", \"body\": \"...\"}.\n\n"
        )
        payload = {
            "job": job,
            "resume": resume_json,
            "recruiter_name": recruiter_name,
        }
        try:
            client = openai.OpenAI()
            resp = client.chat.completions.create(
                model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": str(payload)}],
                max_tokens=400,
                temperature=0.2,
            )
            text = resp.choices[0].message.content.strip()
            try:
                j = json.loads(text)
                return j.get("subject"), j.get("body")
            except Exception:
                # fallback: return raw as body
                return _fallback_draft(job, resume_json, recruiter_name)
        except Exception as e:
            logger.warning("OpenAI email draft failed, using fallback: %s", e)
            return _fallback_draft(job, resume_json, recruiter_name)
    else:
        return _fallback_draft(job, resume_json, recruiter_name)
