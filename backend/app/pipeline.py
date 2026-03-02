"""Daily pipeline runner — designed to be called by cron.

This script runs the full daily automation:
  4:30  → Scrape jobs from all sources
  4:40  → Filter & score with matching engine
  4:45  → Find recruiter emails
  4:50  → Draft emails (LLM)
  5:00  → Send emails + follow-ups

Usage:
    python -m backend.app.pipeline
    # Or via cron: 30 4 * * * cd /workspaces/jht && python -m backend.app.pipeline >> logs/pipeline.log 2>&1
"""
import os
import sys
import json
import time
import logging
from datetime import datetime, timezone

# ensure project root on path so `python -m backend.app.pipeline` works
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.app.scraper import scrape_jobs
from backend.app.matcher import score_job
from backend.app.matching.embeddings import embed_text
from backend.app.matching.cache import cached_embed
from backend.app.email_finder import find_recruiter_email
from backend.app.email_draft import generate_email
from backend.app.emailer import send_email
from backend.app.resume_parser import parse_resume_file
from backend.app.followup import generate_followup, should_followup
from backend.app.auto_apply.engine import apply_to_job, batch_apply

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("pipeline")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine)
models.Base.metadata.create_all(bind=engine)


def _load_resume():
    path = os.getenv("RESUME_PATH")
    if not path or not os.path.exists(path):
        logger.warning("RESUME_PATH not set or file missing — matching will be limited")
        return None, None
    parsed = parse_resume_file(path)
    emb = cached_embed(json.dumps(parsed), embed_text)
    return parsed, emb


def step_scrape():
    logger.info("=== STEP 1: Scrape jobs ===")
    items = scrape_jobs()
    logger.info("Scraped %d raw items", len(items))
    return items


def step_score(items, resume_json, resume_embedding, session):
    logger.info("=== STEP 2: Score & filter ===")
    threshold = float(os.getenv("SEND_MATCH_THRESHOLD", "50.0"))
    scored = []
    for it in items:
        # dedupe
        existing = session.query(models.Job).filter(models.Job.title == it.get("title"), models.Job.company == it.get("company")).first()
        if existing:
            continue

        job_text = " ".join(filter(None, [it.get("title", ""), it.get("company", ""), it.get("description", "")]))
        emb = cached_embed(job_text, embed_text)

        result = score_job(it, resume_json, resume_embedding)
        ms = result.get("match_score", 0)
        rejected = result.get("reject", False)

        job = models.Job(
            title=it.get("title"),
            company=it.get("company"),
            location=it.get("location", ""),
            url=it.get("url"),
            description=it.get("description", ""),
            match_score=ms,
            reject=rejected,
            reject_reason=result.get("reject_reason"),
            embedding=json.dumps(emb),
            applied=False,
            email_sent=False,
            followup_sent=False,
        )
        session.add(job)
        session.commit()

        if rejected:
            logger.info("  REJECTED: %s at %s — %s", it.get("title"), it.get("company"), result.get("reject_reason"))
            continue
        if ms < threshold:
            logger.info("  BELOW THRESHOLD (%.1f): %s at %s", ms, it.get("title"), it.get("company"))
            continue

        scored.append((job, it))
        logger.info("  MATCH (%.1f): %s at %s", ms, it.get("title"), it.get("company"))

    logger.info("Qualified jobs: %d", len(scored))
    return scored


def step_find_emails(scored, session):
    logger.info("=== STEP 3: Find recruiter emails ===")
    for job, raw in scored:
        if job.recruiter_email:
            continue
        try:
            email = find_recruiter_email(raw.get("company"))
            job.recruiter_email = email
            session.add(job)
            session.commit()
            logger.info("  Email for %s: %s", raw.get("company"), email)
        except Exception as e:
            logger.warning("  Email finder failed for %s: %s", raw.get("company"), e)


def step_draft_and_send(scored, resume_json, session):
    logger.info("=== STEP 4: Draft & send emails ===")
    max_per_day = int(os.getenv("MAX_EMAILS_PER_DAY", "20"))
    resume_path = os.getenv("RESUME_PATH")
    portfolio_url = os.getenv("PORTFOLIO_URL", "")
    sent_count = 0

    for job, raw in scored:
        if sent_count >= max_per_day:
            logger.info("  Daily send limit reached (%d)", max_per_day)
            break
        if job.email_sent:
            continue
        if not job.recruiter_email:
            continue

        subj, body = generate_email(raw, resume_json)

        # Append portfolio link
        if portfolio_url:
            body += f"\n\nPortfolio: {portfolio_url}"

        # Attachments
        attachments = []
        if resume_path and os.path.exists(resume_path):
            attachments.append(resume_path)

        try:
            ok = send_email(job.recruiter_email, subj, body, attachments=attachments or None)
            if ok:
                job.email_sent = True
                session.add(job)
                session.commit()
                sent_count += 1
                logger.info("  SENT to %s for %s", job.recruiter_email, job.title)
            else:
                logger.warning("  Send failed for %s", job.recruiter_email)
        except Exception as e:
            logger.warning("  Send error for %s: %s", job.recruiter_email, e)

        # rate limit: 2s between sends
        time.sleep(2)

    logger.info("Emails sent today: %d", sent_count)


def step_auto_apply(scored, session):
    """STEP 4.5: Auto-apply to qualified jobs via board/ATS automation."""
    logger.info("=== STEP 4.5: Auto-apply ===") 
    max_per_day = int(os.getenv("MAX_APPLICATIONS_PER_DAY", "20"))
    proxy = os.getenv("PLAYWRIGHT_PROXY")
    applied = 0

    for job, raw in scored:
        if applied >= max_per_day:
            logger.info("  Daily auto-apply limit reached (%d)", max_per_day)
            break
        if job.auto_applied:
            continue
        if not job.url:
            continue

        try:
            result = apply_to_job(raw, proxy=proxy)
            job.apply_status = result.get("status")
            job.apply_method = result.get("method")
            job.ats_detected = result.get("ats_detected")
            job.apply_error = result.get("error")
            if result.get("status") == "submitted":
                job.auto_applied = True
                job.applied_at = datetime.now(timezone.utc)
                applied += 1
                logger.info("  APPLIED: %s at %s via %s", job.title, job.company, result.get("method"))
            else:
                logger.info("  SKIPPED/FAILED: %s at %s — %s", job.title, job.company, result.get("error"))
            session.add(job)
            session.commit()
        except Exception as e:
            logger.warning("  Auto-apply error for %s: %s", job.title, e)

        # rate limit between applications
        time.sleep(5)

    logger.info("Auto-applied today: %d", applied)


def step_followups(session, resume_json):
    logger.info("=== STEP 5: Follow-ups ===")
    max_per_day = int(os.getenv("MAX_EMAILS_PER_DAY", "20"))
    resume_path = os.getenv("RESUME_PATH")
    jobs = session.query(models.Job).filter(
        models.Job.email_sent == True,
        models.Job.followup_sent == False,
    ).all()

    sent = 0
    for job in jobs:
        if sent >= max_per_day:
            break
        if not should_followup(job):
            continue
        if not job.recruiter_email:
            continue

        subj, body = generate_followup(job.as_dict(), resume_json)
        attachments = [resume_path] if resume_path and os.path.exists(resume_path) else None

        try:
            ok = send_email(job.recruiter_email, subj, body, attachments=attachments)
            if ok:
                job.followup_sent = True
                session.add(job)
                session.commit()
                sent += 1
                logger.info("  FOLLOWUP sent to %s for %s", job.recruiter_email, job.title)
        except Exception as e:
            logger.warning("  Followup error for %s: %s", job.recruiter_email, e)
        time.sleep(2)

    logger.info("Follow-ups sent: %d", sent)


def run_pipeline():
    logger.info("Pipeline started at %s", datetime.now(timezone.utc).isoformat())
    session = SessionLocal()
    try:
        resume_json, resume_embedding = _load_resume()

        # Persist resume
        if resume_json:
            r = models.Resume(
                name=resume_json.get("name"),
                parsed_json=json.dumps(resume_json),
                embedding=json.dumps(resume_embedding) if resume_embedding else None,
            )
            session.add(r)
            session.commit()

        items = step_scrape()
        scored = step_score(items, resume_json, resume_embedding, session)
        step_find_emails(scored, session)
        step_draft_and_send(scored, resume_json, session)
        step_auto_apply(scored, session)
        step_followups(session, resume_json)
    except Exception as e:
        logger.error("Pipeline failed: %s", e, exc_info=True)
    finally:
        session.close()
        logger.info("Pipeline finished at %s", datetime.now(timezone.utc).isoformat())


if __name__ == "__main__":
    run_pipeline()
