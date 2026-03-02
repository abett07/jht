"""Tests for the models module — serialization and auto-apply columns."""
import os
import pytest
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_models.db")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models import Base, Job, Resume, _serialize_value


class TestSerializeValue:
    def test_datetime(self):
        dt = datetime(2024, 1, 15, 10, 30, 0)
        assert _serialize_value(dt) == "2024-01-15T10:30:00"

    def test_string(self):
        assert _serialize_value("hello") == "hello"

    def test_none(self):
        assert _serialize_value(None) is None

    def test_int(self):
        assert _serialize_value(42) == 42

    def test_bool(self):
        assert _serialize_value(True) is True


class TestJobModel:
    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        db_path = tmp_path / "test.db"
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def test_create_job_with_auto_apply_fields(self):
        session = self.Session()
        job = Job(
            title="SWE",
            company="ACME",
            auto_applied=True,
            apply_status="submitted",
            apply_method="linkedin",
            applied_at=datetime(2024, 6, 1, 12, 0, 0),
            ats_detected="greenhouse",
            apply_error=None,
            email_sent=False,
            followup_sent=False,
        )
        session.add(job)
        session.commit()

        loaded = session.query(Job).first()
        assert loaded.auto_applied is True
        assert loaded.apply_status == "submitted"
        assert loaded.apply_method == "linkedin"
        assert loaded.ats_detected == "greenhouse"
        assert loaded.applied_at == datetime(2024, 6, 1, 12, 0, 0)
        session.close()

    def test_as_dict_includes_auto_apply_fields(self):
        session = self.Session()
        job = Job(
            title="Dev",
            company="Co",
            auto_applied=False,
            apply_status="failed",
            apply_error="No submit button",
            email_sent=False,
            followup_sent=False,
        )
        session.add(job)
        session.commit()

        d = job.as_dict()
        assert "auto_applied" in d
        assert "apply_status" in d
        assert "apply_error" in d
        assert "ats_detected" in d
        assert d["auto_applied"] is False
        assert d["apply_status"] == "failed"
        assert d["apply_error"] == "No submit button"
        session.close()

    def test_as_dict_serializes_datetime(self):
        session = self.Session()
        now = datetime(2024, 3, 15, 8, 0, 0)
        job = Job(
            title="Dev",
            company="Co",
            applied_at=now,
            email_sent=False,
            followup_sent=False,
        )
        session.add(job)
        session.commit()

        d = job.as_dict()
        assert d["applied_at"] == "2024-03-15T08:00:00"
        session.close()

    def test_default_values(self):
        session = self.Session()
        job = Job(title="Dev", company="Co", email_sent=False, followup_sent=False)
        session.add(job)
        session.commit()

        loaded = session.query(Job).first()
        assert loaded.auto_applied in (None, False)
        assert loaded.apply_status is None
        assert loaded.apply_method is None
        assert loaded.ats_detected is None
        session.close()
