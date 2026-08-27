"""
Runs local server on port 8080 and writes token.json.
"""

import sys
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

flow = InstalledAppFlow.from_client_secrets_file(
    "credentials.json",
    scopes=SCOPES
)

creds = flow.run_local_server(
    host="localhost",
    port=8080,
    open_browser=True,
    success_message="Authentication successful! You can close this tab now."
)

with open("token.json", "w", encoding="utf-8") as f:
    f.write(creds.to_json())

print("TOKEN_SAVED_SUCCESSFULLY", flush=True)
