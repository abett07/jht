from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import logging

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, func as sqlfunc
from sqlalchemy.orm import sessionmaker

from . import models, scraper
from . import matcher
from .matching.embeddings import embed_text
from .matching.cache import cached_embed
from .resume_parser import parse_resume_file
from .email_finder import find_recruiter_email
from .email_draft import generate_email
from .emailer import send_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine)

app = FastAPI(title="Job Hunting Toolkit API")

# CORS — allow Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

models.Base.metadata.create_all(bind=engine)


def _migrate_add_columns():
    """Best-effort migration: add new columns to existing tables without Alembic."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "jobs" in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns("jobs")}
        new_cols = {
            "url": "VARCHAR",
            "description": "TEXT",
            "reject": "BOOLEAN DEFAULT 0",
            "reject_reason": "VARCHAR",
        }
        with engine.begin() as conn:
            for col, col_type in new_cols.items():
                if col not in existing:
                    try:
                        conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {col} {col_type}"))
                        logger.info("Added column jobs.%s", col)
                    except Exception as e:
                        logger.debug("Column jobs.%s may already exist: %s", col, e)


_migrate_add_columns()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/jobs")
def list_jobs():
    session = SessionLocal()
    try:
        jobs = session.query(models.Job).order_by(models.Job.created_at.desc()).all()
        return [job.as_dict() for job in jobs]
    finally:
        session.close()


@app.post("/jobs/{job_id}/send")
def send_job_email(job_id: int):
    session = SessionLocal()
    try:
        job = session.query(models.Job).filter(models.Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if not job.recruiter_email:
            raise HTTPException(status_code=400, detail="No recruiter email available for this job")

        # Try to load parsed resume from DB (most recent)
        resume = session.query(models.Resume).order_by(models.Resume.created_at.desc()).first()
        resume_json = None
        if resume:
            try:
                resume_json = json.loads(resume.parsed_json)
            except Exception:
                resume_json = None

        # Draft email using LLM or fallback
        subj, body = generate_email(job.as_dict(), resume_json, None)

        # Append portfolio link
        portfolio = os.getenv("PORTFOLIO_URL", "")
        if portfolio:
            body += f"\n\nPortfolio: {portfolio}"

        # Attach resume if available
        attachments = []
        resume_file = os.getenv("RESUME_PATH")
        if resume_file and os.path.exists(resume_file):
            attachments.append(resume_file)

        sent = send_email(job.recruiter_email, subj, body, attachments=attachments or None)
        if sent:
            job.email_sent = True
            session.add(job)
            session.commit()
        return {"sent": bool(sent)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error sending email for job %d: %s", job_id, e)
        raise HTTPException(status_code=500, detail="Internal error sending email")
    finally:
        session.close()


@app.post("/jobs/{job_id}/followup")
def send_followup(job_id: int):
    """Send a follow-up email for a job that already had initial outreach."""
    from .followup import generate_followup, should_followup
    session = SessionLocal()
    try:
        job = session.query(models.Job).filter(models.Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if not job.email_sent:
            raise HTTPException(status_code=400, detail="Initial email not sent yet")
        if job.followup_sent:
            raise HTTPException(status_code=400, detail="Follow-up already sent")
        if not job.recruiter_email:
            raise HTTPException(status_code=400, detail="No recruiter email")

        # Load resume
        resume = session.query(models.Resume).order_by(models.Resume.created_at.desc()).first()
        resume_json = json.loads(resume.parsed_json) if resume and resume.parsed_json else None

        subj, body = generate_followup(job.as_dict(), resume_json)
        attachments = []
        resume_file = os.getenv("RESUME_PATH")
        if resume_file and os.path.exists(resume_file):
            attachments.append(resume_file)

        sent = send_email(job.recruiter_email, subj, body, attachments=attachments or None)
        if sent:
            job.followup_sent = True
            session.add(job)
            session.commit()
        return {"sent": bool(sent)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error sending follow-up for job %d: %s", job_id, e)
        raise HTTPException(status_code=500, detail="Internal error sending follow-up")
    finally:
        session.close()


@app.get("/stats")
def stats():
    """Dashboard stats: counts of jobs, emails sent, follow-ups, etc."""
    session = SessionLocal()
    try:
        total = session.query(models.Job).count()
        emailed = session.query(models.Job).filter(models.Job.email_sent == True).count()
        followed_up = session.query(models.Job).filter(models.Job.followup_sent == True).count()
        avg_score = 0
        row = session.query(sqlfunc.avg(models.Job.match_score)).first()
        if row and row[0]:
            avg_score = round(float(row[0]), 1)
        return {"total_jobs": total, "emails_sent": emailed, "followups_sent": followed_up, "avg_match_score": avg_score}
    finally:
        session.close()


@app.post("/scrape")
def run_scrape():
    # Load / parse resume (from RESUME_PATH env) if available
    resume_path = os.getenv("RESUME_PATH")
    resume_json = None
    resume_embedding = None
    session = SessionLocal()
    try:
        if resume_path and os.path.exists(resume_path):
            parsed = parse_resume_file(resume_path)
            resume_json = parsed
            resume_text = json.dumps(parsed)
            resume_embedding = cached_embed(resume_text, embed_text)
            # persist resume cache
            r = models.Resume(name=parsed.get("name"), parsed_json=json.dumps(parsed), embedding=json.dumps(resume_embedding))
            session.add(r)
            session.commit()
            logger.info("Resume parsed and cached: %s", parsed.get("name"))

        items = scraper.scrape_jobs()
        added = 0
        for it in items:
            # dedupe by URL first, then by title+company composite key
            url = it.get("url")
            exists = None
            if url:
                exists = session.query(models.Job).filter(models.Job.url == url).first()
            if not exists:
                exists = session.query(models.Job).filter(
                    models.Job.title == it.get("title"),
                    models.Job.company == it.get("company"),
                ).first()
            if exists:
                continue

            job = models.Job(
                title=it.get("title"),
                company=it.get("company"),
                location=it.get("location", ""),
                url=it.get("url"),
                description=it.get("description", ""),
                match_score=None,
                recruiter_email=None,
                applied=False,
                email_sent=False,
                followup_sent=False,
            )
            session.add(job)
            session.commit()

            # compute embedding for job and cache
            job_text = " ".join(filter(None, [it.get("title", ""), it.get("company", ""), it.get("description", "")]))
            try:
                emb = cached_embed(job_text, embed_text)
                job.embedding = json.dumps(emb)
            except Exception:
                job.embedding = None

            # compute match score
            try:
                score_res = matcher.score_job(it, resume_json, resume_embedding)
                job.match_score = score_res.get("match_score")
                job.reject = score_res.get("reject", False)
                job.reject_reason = score_res.get("reject_reason")
            except Exception as e:
                logger.warning("Scoring failed for %s: %s", it.get("title"), e)
                job.match_score = None

            # attempt to find recruiter email (pass company name, not job title)
            try:
                recruiter = find_recruiter_email(it.get("company"))
                job.recruiter_email = recruiter
            except Exception as e:
                logger.warning("Email finder failed for %s: %s", it.get("company"), e)
                job.recruiter_email = None

            session.add(job)
            session.commit()
            added += 1

        return {"added": added}
    except Exception as e:
        logger.error("Scrape endpoint error: %s", e)
        raise HTTPException(status_code=500, detail="Internal error during scrape")
    finally:
        session.close()
