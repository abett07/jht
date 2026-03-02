"""Follow-up email management.

Sends a follow-up email 3 days after the initial outreach if no reply detected.
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def generate_followup(job: dict, resume_json: Optional[dict] = None) -> tuple:
    """Generate a follow-up email (subject, body) for a job."""
    company = job.get("company", "your company")
    title = job.get("title", "the open role")
    subject = f"Following up: {title} at {company}"
    portfolio = os.getenv("PORTFOLIO_URL", "")
    portfolio_line = f"\n\nPortfolio: {portfolio}" if portfolio else ""
    body = (
        f"Hi,\n\n"
        f"I wanted to follow up on my previous email regarding the {title} position at {company}. "
        f"I remain very interested and believe my OKTA DFIR experience, AI forensic tooling, "
        f"and SIEM + EDR expertise make me a strong fit.\n\n"
        f"Would you have 15 minutes for a quick call this week?{portfolio_line}\n\n"
        f"Best regards"
    )
    return subject, body


def should_followup(job_row, days: int = 3) -> bool:
    """Check whether enough time has passed since initial email for a follow-up."""
    if not job_row.email_sent:
        return False
    if job_row.followup_sent:
        return False
    if job_row.created_at is None:
        return False
    now = datetime.utcnow()
    created = job_row.created_at
    if hasattr(created, "replace"):
        created = created.replace(tzinfo=None)
    return (now - created) >= timedelta(days=days)
