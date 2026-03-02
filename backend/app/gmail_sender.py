import os
import json
import base64
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List

from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _load_credentials() -> Credentials:
    path = os.getenv("GMAIL_CREDENTIALS_PATH")
    if not path or not os.path.exists(path):
        raise RuntimeError("GMAIL_CREDENTIALS_PATH not set or file missing")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # service account
    if data.get("type") == "service_account":
        # Service accounts cannot send as a user unless domain-wide delegation is configured.
        creds = ServiceAccountCredentials.from_service_account_file(path, scopes=SCOPES)
        # Optionally delegate to user via env GMAIL_DELEGATE
        delegate_to = os.getenv("GMAIL_DELEGATE")
        if delegate_to:
            creds = creds.with_subject(delegate_to)
        return creds

    # assume this is a user-authorized credentials file (token.json style)
    try:
        creds = Credentials.from_authorized_user_file(path, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds
    except Exception as e:
        raise RuntimeError("Unable to load Gmail credentials: %s" % e)


def _build_message(to: str, subject: str, body: str, attachments: Optional[List[str]] = None) -> dict:
    if attachments:
        msg = MIMEMultipart()
        msg.attach(MIMEText(body, "plain"))
        for path in attachments:
            try:
                with open(path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename=\"{os.path.basename(path)}\"")
                msg.attach(part)
            except Exception:
                continue
    else:
        msg = MIMEText(body)

    msg["to"] = to
    msg["from"] = os.getenv("GMAIL_FROM", "me")
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw}


def send_message(to: str, subject: str, body: str, attachments: Optional[List[str]] = None) -> bool:
    creds = _load_credentials()
    service = build("gmail", "v1", credentials=creds)
    msg = _build_message(to, subject, body, attachments)
    try:
        service.users().messages().send(userId="me", body=msg).execute()
        return True
    except Exception as e:
        logger.error("Gmail send failed to %s: %s", to, e)
        return False
