"""
Google Sheets Integration Service.
Supports:
1. Google Apps Script Webhook (GSHEET_WEBHOOK_URL) - 100% reliable, zero OAuth blocks.
2. Service Account (service_account.json)
3. OAuth 2.0 Desktop (credentials.json / token.json)
"""

import os
import logging
from typing import List, Tuple
import requests
from dotenv import load_dotenv
from schema import StockCall

load_dotenv()

logger = logging.getLogger(__name__)

TARGET_HEADERS = [
    "Current Date",
    "Call Type",
    "Stock Name",
    "CMP",
    "Target 1",
    "Target 2",
    "Stop Loss",
    "Instrument Type"
]


class SheetsManager:
    def __init__(
        self,
        spreadsheet_id: str = None,
        webhook_url: str = None,
        credentials_file: str = "credentials.json",
        token_file: str = "token.json",
        service_account_file: str = "service_account.json"
    ):
        self.spreadsheet_id = spreadsheet_id or os.getenv("SPREADSHEET_ID")
        self.webhook_url = webhook_url or os.getenv("GSHEET_WEBHOOK_URL")
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service_account_file = service_account_file
        self.client = None
        self.spreadsheet = None
        self.worksheet = None

    def get_all_rows(self) -> List[List]:
        """
        Retrieves all current rows from the Sheet via Webhook GET request.
        """
        if not self.webhook_url:
            return []
        try:
            resp = requests.get(self.webhook_url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("rows", [])
        except Exception as e:
            logger.warning(f"Could not retrieve rows via webhook: {e}")
        return []

    def get_existing_keys_via_webhook(self) -> set:
        """
        Retrieves existing deduplication keys via Webhook GET request.
        """
        if not self.webhook_url:
            return set()
        try:
            resp = requests.get(self.webhook_url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                rows = data.get("rows", [])
                keys = set()
                for row in rows[1:]:  # skip header
                    if len(row) >= 7:
                        # Extract first 10 chars for date in case GSheets formatted as ISO timestamp
                        date = str(row[0]).strip()[:10]
                        call_type = str(row[1]).strip()
                        stock = str(row[2]).strip().upper()
                        try:
                            t1 = float(row[4])
                        except (ValueError, TypeError):
                            t1 = str(row[4]).strip()
                        try:
                            sl = float(row[6])
                        except (ValueError, TypeError):
                            sl = str(row[6]).strip()
                        keys.add(f"{date}|{call_type}|{stock}|{t1}|{sl}")
                return keys
        except Exception as e:
            logger.warning(f"Could not retrieve existing keys via webhook: {e}")
        return set()

    def append_calls_via_webhook(self, calls: List[StockCall]) -> Tuple[int, int]:
        """
        Appends calls directly via Google Apps Script Webhook.
        """
        if not calls:
            return 0, 0

        existing_keys = self.get_existing_keys_via_webhook()
        rows_to_insert = []
        skipped = 0

        for call in calls:
            key = call.deduplication_key()
            if key in existing_keys:
                logger.info(f"Skipping duplicate call: {call.stock_name} ({call.call_type})")
                skipped += 1
            else:
                rows_to_insert.append(call.to_sheet_row())
                existing_keys.add(key)

        if not rows_to_insert:
            return 0, skipped

        logger.info(f"Posting {len(rows_to_insert)} rows to Google Sheets Webhook...")
        response = requests.post(
            self.webhook_url,
            json={"rows": rows_to_insert},
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        if response.status_code == 200:
            logger.info(f"Successfully inserted {len(rows_to_insert)} calls into Google Sheet via Webhook.")
            return len(rows_to_insert), skipped
        else:
            raise RuntimeError(f"Webhook insertion failed with status {response.status_code}: {response.text}")

    def append_calls(self, calls: List[StockCall]) -> Tuple[int, int]:
        """
        Routes call insertion to Webhook or OAuth/Service Account.
        """
        if self.webhook_url:
            return self.append_calls_via_webhook(calls)

        # Fallback to gspread
        import gspread
        from google.oauth2.credentials import Credentials
        from google.oauth2 import service_account

        if os.path.exists(self.service_account_file):
            creds = service_account.Credentials.from_service_account_file(
                self.service_account_file,
                scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            )
            self.client = gspread.authorize(creds)
        elif os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(
                self.token_file,
                ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            )
            self.client = gspread.authorize(creds)
        else:
            raise FileNotFoundError(
                "No valid authentication found! Please provide GSHEET_WEBHOOK_URL in .env "
                "or service_account.json / token.json."
            )

        self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
        ws = self.spreadsheet.sheet1
        existing_values = ws.get_all_values()
        if not existing_values or len(existing_values) == 0:
            ws.insert_row(TARGET_HEADERS, index=1)

        existing_keys = set()
        if len(existing_values) > 1:
            for row in existing_values[1:]:
                if len(row) >= 7:
                    existing_keys.add(f"{row[0].strip()}|{row[1].strip()}|{row[2].strip().upper()}|{str(row[4]).strip()}|{str(row[6]).strip()}")

        rows_to_insert = []
        skipped = 0
        for call in calls:
            key = call.deduplication_key()
            if key in existing_keys:
                skipped += 1
            else:
                rows_to_insert.append(call.to_sheet_row())
                existing_keys.add(key)

        if rows_to_insert:
            ws.append_rows(rows_to_insert, value_input_option="USER_ENTERED")

        return len(rows_to_insert), skipped
