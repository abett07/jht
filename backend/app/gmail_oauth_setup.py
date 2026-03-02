"""Gmail OAuth2 helper — interactive flow to generate token.json.

Run this script once to authorize your Gmail account:
    python -m backend.app.gmail_oauth_setup

It will open a browser, ask you to log in, and save the token to the
path specified by GMAIL_CREDENTIALS_PATH (default: gmail_token.json).
"""
import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def run_oauth_flow():
    client_secrets = os.getenv("GMAIL_CLIENT_SECRETS_PATH", "client_secret.json")
    token_path = os.getenv("GMAIL_CREDENTIALS_PATH", "gmail_token.json")

    creds = None
    # Check if we already have a valid token
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        print(f"Token already valid at {token_path}")
        return

    if creds and creds.expired and creds.refresh_token:
        print("Refreshing expired token...")
        creds.refresh(Request())
    else:
        if not os.path.exists(client_secrets):
            print(f"ERROR: Client secrets file not found: {client_secrets}")
            print("Download it from Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs")
            print("Set GMAIL_CLIENT_SECRETS_PATH env to its path.")
            return

        flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
        creds = flow.run_local_server(port=0)

    # Save token
    with open(token_path, "w") as f:
        f.write(creds.to_json())
    print(f"Token saved to {token_path}")
    print("Set GMAIL_CREDENTIALS_PATH={} in your .env".format(token_path))


if __name__ == "__main__":
    run_oauth_flow()
