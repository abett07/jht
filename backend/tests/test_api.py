"""Tests for the FastAPI endpoints — specifically auto-apply routes."""
import os
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_api.db")
os.environ.setdefault("APPLICANT_FIRST_NAME", "Jane")
os.environ.setdefault("APPLICANT_LAST_NAME", "Doe")
os.environ.setdefault("APPLICANT_EMAIL", "jane@example.com")

from fastapi.testclient import TestClient
from backend.app.main import app, SessionLocal
from backend.app import models


@pytest.fixture(autouse=True)
def clean_db():
    """Reset test DB before each test."""
    models.Base.metadata.drop_all(bind=SessionLocal().get_bind())
    models.Base.metadata.create_all(bind=SessionLocal().get_bind())
    yield
    models.Base.metadata.drop_all(bind=SessionLocal().get_bind())


client = TestClient(app)


class TestHealthEndpoint:
    def test_health(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestStatsEndpoint:
    def test_stats_empty(self):
        r = client.get("/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["total_jobs"] == 0
        assert data["auto_applied"] == 0
        assert data["apply_failed"] == 0

    def test_stats_with_data(self):
        session = SessionLocal()
        job = models.Job(
            title="Dev", company="Co", auto_applied=True,
            apply_status="submitted", email_sent=False, followup_sent=False,
        )
        session.add(job)
        session.commit()
        session.close()

        r = client.get("/stats")
        data = r.json()
        assert data["total_jobs"] == 1
        assert data["auto_applied"] == 1


class TestApplySingleEndpoint:
    def test_job_not_found(self):
        r = client.post("/jobs/9999/apply")
        assert r.status_code == 404

    def test_already_applied(self):
        session = SessionLocal()
        job = models.Job(
            title="Dev", company="Co", auto_applied=True,
            email_sent=False, followup_sent=False,
        )
        session.add(job)
        session.commit()
        job_id = job.id
        session.close()

        r = client.post(f"/jobs/{job_id}/apply")
        assert r.status_code == 400
        assert "Already applied" in r.json()["detail"]

    def test_rejected_job(self):
        session = SessionLocal()
        job = models.Job(
            title="Dev", company="Co", reject=True,
            email_sent=False, followup_sent=False,
        )
        session.add(job)
        session.commit()
        job_id = job.id
        session.close()

        r = client.post(f"/jobs/{job_id}/apply")
        assert r.status_code == 400
        assert "rejected" in r.json()["detail"].lower()

    @patch("backend.app.main.apply_to_job")
    def test_successful_apply(self, mock_apply):
        mock_apply.return_value = {
            "status": "submitted",
            "method": "generic",
            "ats_detected": None,
            "error": None,
        }

        session = SessionLocal()
        job = models.Job(
            title="Dev", company="Co", url="https://example.com/apply",
            email_sent=False, followup_sent=False,
        )
        session.add(job)
        session.commit()
        job_id = job.id
        session.close()

        r = client.post(f"/jobs/{job_id}/apply")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "submitted"

        # Verify DB was updated
        session = SessionLocal()
        job = session.query(models.Job).filter(models.Job.id == job_id).first()
        assert job.auto_applied is True
        assert job.apply_status == "submitted"
        assert job.applied_at is not None
        session.close()


class TestBatchApplyEndpoint:
    @patch("backend.app.main.batch_apply")
    def test_no_qualifying_jobs(self, mock_batch):
        r = client.post("/auto-apply")
        assert r.status_code == 200
        data = r.json()
        assert data["applied"] == 0
        mock_batch.assert_not_called()

    @patch("backend.app.main.batch_apply")
    def test_batch_apply_with_results(self, mock_batch):
        mock_batch.return_value = [
            {"status": "submitted", "method": "generic", "ats_detected": None, "error": None},
        ]

        session = SessionLocal()
        job = models.Job(
            title="Dev", company="Co", url="https://example.com/apply",
            match_score=80.0, email_sent=False, followup_sent=False,
        )
        session.add(job)
        session.commit()
        session.close()

        r = client.post("/auto-apply")
        assert r.status_code == 200
        data = r.json()
        assert data["applied"] == 1


class TestJobsListEndpoint:
    def test_list_empty(self):
        r = client.get("/jobs")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_with_auto_apply_fields(self):
        session = SessionLocal()
        job = models.Job(
            title="Dev", company="Co",
            auto_applied=True, apply_status="submitted",
            apply_method="linkedin", ats_detected="greenhouse",
            email_sent=False, followup_sent=False,
        )
        session.add(job)
        session.commit()
        session.close()

        r = client.get("/jobs")
        data = r.json()
        assert len(data) == 1
        assert data[0]["auto_applied"] is True
        assert data[0]["apply_status"] == "submitted"
        assert data[0]["apply_method"] == "linkedin"
        assert data[0]["ats_detected"] == "greenhouse"
