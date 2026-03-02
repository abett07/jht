from .gmail_sender import send_message


def send_email(to_email, subject, body, attachments=None):
    """Send email using Gmail API integration (see `GMAIL_CREDENTIALS_PATH`)."""
    return send_message(to_email, subject, body, attachments)
