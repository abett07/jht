"""SMTP-ping email verification.

Connects to the MX server for the domain and issues RCPT TO to check
whether the mailbox exists. Many servers reject or silently accept all,
so this is a best-effort check.
"""
import smtplib
import logging
from typing import Optional

try:
    import dns.resolver
    _HAS_DNS = True
except ImportError:
    _HAS_DNS = False

logger = logging.getLogger(__name__)


def _get_mx(domain: str) -> Optional[str]:
    if not _HAS_DNS:
        logger.debug("dnspython not installed — MX lookup unavailable")
        return None
    try:
        answers = dns.resolver.resolve(domain, "MX")
        records = sorted(answers, key=lambda r: r.preference)
        return str(records[0].exchange).rstrip(".")
    except Exception as e:
        logger.debug("MX lookup failed for %s: %s", domain, e)
        return None


def smtp_verify(email: str, timeout: int = 10) -> bool:
    """Verify email via SMTP RCPT TO handshake.

    Returns True if the server accepted the RCPT TO command (250/251).
    Returns False on rejection, timeout, or error.
    """
    if "@" not in email:
        return False
    domain = email.split("@", 1)[1]
    mx = _get_mx(domain)
    if not mx:
        return False

    try:
        smtp = smtplib.SMTP(timeout=timeout)
        smtp.connect(mx, 25)
        smtp.helo("verify.local")
        smtp.mail("noreply@verify.local")
        code, _ = smtp.rcpt(email)
        smtp.quit()
        return code in (250, 251)
    except Exception as e:
        logger.debug("SMTP verify failed for %s: %s", email, e)
        return False
