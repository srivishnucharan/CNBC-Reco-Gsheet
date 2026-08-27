"""
Direct Google OAuth Helper that generates and prints the exact clickable URL.
"""

import os
import sys

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def main():
    credentials_file = "credentials.json"
    token_file = "token.json"

    if not os.path.exists(credentials_file):
        print(f"ERROR: '{credentials_file}' not found.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(
        credentials_file,
        scopes=SCOPES
    )

    print("AUTH_SERVER_STARTING", flush=True)
    creds = flow.run_local_server(
        port=0,
        open_browser=True,
        success_message="Authentication successful! You may return to the terminal."
    )

    with open(token_file, "w") as token:
        token.write(creds.to_json())

    print("AUTH_SUCCESSFUL", flush=True)

if __name__ == "__main__":
    main()
