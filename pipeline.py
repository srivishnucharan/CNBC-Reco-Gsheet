"""
Orchestration Pipeline coordinating Audio Fetching -> Gemini Extraction -> Google Sheets Sync.
"""

import os
import logging
from typing import Optional, List, Tuple
from dotenv import load_dotenv
from schema import StockCall
from sheets import SheetsManager
from parser import CNBCParser
from fetcher import YouTubeFetcher

load_dotenv()
logger = logging.getLogger(__name__)


class CNBCPipeline:
    def __init__(
        self,
        spreadsheet_id: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
        credentials_file: str = "credentials.json",
        token_file: str = "token.json",
        service_account_file: str = "service_account.json"
    ):
        self.spreadsheet_id = spreadsheet_id or os.getenv("SPREADSHEET_ID")
        if not self.spreadsheet_id:
            raise ValueError("SPREADSHEET_ID must be set in .env or passed to CNBCPipeline.")

        self.sheets = SheetsManager(
            spreadsheet_id=self.spreadsheet_id,
            credentials_file=credentials_file,
            token_file=token_file,
            service_account_file=service_account_file
        )

        self.parser = CNBCParser(
            api_key=gemini_api_key or os.getenv("GEMINI_API_KEY"),
            model_name=gemini_model or os.getenv("GEMINI_MODEL", "gemini-3.7-flash")
        )

        self.fetcher = YouTubeFetcher()

    def process_audio_file(
        self,
        audio_path: str,
        segment_name: Optional[str] = None,
        date_str: Optional[str] = None,
        dry_run: bool = False
    ) -> Tuple[List[StockCall], int, int]:
        """
        Extracts calls from an audio file and appends them to Google Sheets.
        Returns: (extracted_calls, inserted_count, skipped_count)
        """
        logger.info(f"=== Starting processing for audio file: {audio_path} (Segment: {segment_name}) ===")
        calls = self.parser.extract_calls_from_audio(
            audio_path=audio_path,
            expected_segment=segment_name,
            date_str=date_str
        )

        if not calls:
            logger.info("No trading setups were detected in this audio segment.")
            return [], 0, 0

        logger.info(f"Detected {len(calls)} calls:")
        for idx, c in enumerate(calls, 1):
            logger.info(
                f"  [{idx}] {c.call_type} | {c.stock_name} ({c.instrument_type}) | "
                f"CMP: {c.cmp} | Target1: {c.target_1} | Target2: {c.target_2} | SL: {c.stop_loss}"
            )

        if dry_run:
            logger.info("[DRY RUN] Skipping Google Sheets insertion.")
            return calls, 0, 0

        inserted, skipped = self.sheets.append_calls(calls)
        logger.info(f"Sync complete: {inserted} calls inserted, {skipped} duplicate calls skipped.")
        return calls, inserted, skipped

    def process_live_segment(
        self,
        segment_name: str,
        duration_minutes: int = 25,
        live_url: str = "https://www.youtube.com/@cnbcawaaz/live",
        cleanup: bool = True
    ) -> Tuple[List[StockCall], int, int]:
        """
        Ingests the trailing live audio chunk and pushes calls to Google Sheets.
        """
        logger.info(f"=== Live Segment Trigger: '{segment_name}' ({duration_minutes} mins buffer) ===")
        audio_path = self.fetcher.fetch_live_trailing_audio(
            live_url=live_url,
            duration_minutes=duration_minutes,
            output_prefix=segment_name.replace(" ", "_").lower()
        )

        try:
            return self.process_audio_file(
                audio_path=audio_path,
                segment_name=segment_name
            )
        finally:
            if cleanup and os.path.exists(audio_path):
                self.fetcher.cleanup(audio_path)

    def process_video_url(
        self,
        video_url: str,
        segment_name: Optional[str] = None,
        duration_minutes: int = 25,
        cleanup: bool = True
    ) -> Tuple[List[StockCall], int, int]:
        """
        Processes a YouTube video/stream recording using transcript (fast) or audio download.
        """
        logger.info(f"=== Processing YouTube Video URL: {video_url} ===")
        
        # 1. Attempt fast transcript extraction
        transcript = self.fetcher.fetch_transcript(video_url)
        if transcript and len(transcript.strip()) > 100:
            logger.info("Extracting market calls directly from video transcript...")
            calls = self.parser.extract_calls_from_text(
                transcript_text=transcript,
                expected_segment=segment_name
            )
            inserted, skipped = self.sheets.append_calls(calls)
            logger.info(f"Sync complete: {inserted} calls inserted, {skipped} duplicates skipped.")
            return calls, inserted, skipped

        # 2. Fallback to audio stream download and Gemini multimodal audio
        logger.info(f"Extracting calls via direct audio download ({duration_minutes} mins)...")
        audio_path = self.fetcher.download_video_audio(
            video_url=video_url,
            duration_minutes=duration_minutes
        )
        try:
            return self.process_audio_file(
                audio_path=audio_path,
                segment_name=segment_name
            )
        finally:
            if cleanup and os.path.exists(audio_path):
                self.fetcher.cleanup(audio_path)

    def test_connections(self) -> bool:
        """
        Verifies both Google Sheets connection/headers and Gemini API access.
        """
        logger.info("--- Testing Gemini API Connection ---")
        try:
            test_resp = self.parser.client.models.generate_content(
                model=self.parser.model_name,
                contents="Reply with 'GEMINI_CONNECTED' if you receive this."
            )
            logger.info(f"Gemini API Response: {test_resp.text.strip()}")
            gemini_ok = True
        except Exception as ge:
            logger.error(f"Gemini API test failed: {ge}")
            gemini_ok = False

        logger.info("--- Testing Google Sheets Connection ---")
        try:
            if self.sheets.webhook_url:
                logger.info(f"Testing Webhook at: {self.sheets.webhook_url[:40]}...")
                keys = self.sheets.get_existing_keys_via_webhook()
                logger.info(f"Google Sheets Webhook responded successfully! Existing row keys loaded: {len(keys)}")
                sheets_ok = True
            else:
                ws = self.sheets.get_worksheet()
                logger.info(f"Successfully opened Google Sheet: '{self.sheets.spreadsheet.title}' (Worksheet: '{ws.title}')")
                existing = ws.get_all_values()
                logger.info(f"Current rows in sheet: {len(existing)}")
                sheets_ok = True
        except Exception as se:
            logger.error(f"Google Sheets test failed: {se}")
            sheets_ok = False

        return gemini_ok and sheets_ok
