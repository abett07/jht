from datetime import datetime as _dt

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _serialize_value(val):
    """JSON-safe serialization for model values."""
    if isinstance(val, _dt):
        return val.isoformat()
    return val


class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    title = Column(String)
    company = Column(String)
    location = Column(String)
    url = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    match_score = Column(Float, nullable=True)
    reject = Column(Boolean, default=False)
    reject_reason = Column(String, nullable=True)
    recruiter_email = Column(String, nullable=True)
    applied = Column(Boolean, default=False)
    email_sent = Column(Boolean, default=False)
    followup_sent = Column(Boolean, default=False)
    embedding = Column(String, nullable=True)
    # Auto-apply tracking
    auto_applied = Column(Boolean, default=False)
    apply_status = Column(String, nullable=True)  # pending|submitted|failed|skipped
    apply_method = Column(String, nullable=True)  # linkedin|indeed|dice|ats|email
    applied_at = Column(DateTime, nullable=True)
    apply_error = Column(Text, nullable=True)
    ats_detected = Column(String, nullable=True)  # greenhouse|lever|workday|icims|etc
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def as_dict(self):
        return {c.name: _serialize_value(getattr(self, c.name)) for c in self.__table__.columns}


class Resume(Base):
    __tablename__ = "resumes"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    parsed_json = Column(Text)
    embedding = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def as_dict(self):
        return {c.name: _serialize_value(getattr(self, c.name)) for c in self.__table__.columns}
