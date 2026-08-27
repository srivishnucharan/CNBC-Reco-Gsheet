"""
Batch Extractor for CNBC Awaaz Market Broadcasts.
Processes key stock recommendation shows and syncs calls to Google Sheet.
"""

import os
import sys
import logging
from typing import List
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("batch_processor")

from fetcher import YouTubeFetcher
from parser import CNBCParser
from sheets import SheetsManager

TARGET_SHOWS = [
    {
        "name": "Top 20 Stock Picks (Morning)",
        "url": "https://www.youtube.com/watch?v=WsjLJY6AOxc",
        "segment": "Spotlight Stocks / Top 20 Stocks"
    },
    {
        "name": "Morning Call - Top Stocks Today",
        "url": "https://www.youtube.com/watch?v=zMuuvbCxyAE",
        "segment": "Pehla Sauda / Morning Call"
    },
    {
        "name": "First Trade Strategy & Opening Picks",
        "url": "https://www.youtube.com/watch?v=aq1OMdf8srA",
        "segment": "Pehla Sauda / Opening Trade"
    },
    {
        "name": "Final Trade & Closing Recommendations",
        "url": "https://www.youtube.com/watch?v=hmWz8jMTp-g",
        "segment": "Final Trade / BTST / STBT"
    },
    {
        "name": "Kal Ka Bazaar - Stock Picks for Tomorrow",
        "url": "https://www.youtube.com/watch?v=RAmXKXeXIX8",
        "segment": "BTST / Positional Recommendations"
    }
]


def run_batch():
    fetcher = YouTubeFetcher()
    parser = CNBCParser()
    sheets = SheetsManager()
    
    total_calls_all = []
    total_inserted = 0
    total_skipped = 0

    print("=" * 70)
    print("STARTING BATCH MARKET CALLS EXTRACTION")
    print(f"Targeting {len(TARGET_SHOWS)} key CNBC Awaaz broadcasts from today...")
    print("=" * 70)

    for i, show in enumerate(TARGET_SHOWS, 1):
        name = show["name"]
        url = show["url"]
        segment = show["segment"]

        print(f"\n[{i}/{len(TARGET_SHOWS)}] Processing show: {name}")
        print(f"URL: {url}")
        print(f"Segment: {segment}")

        # 1. Attempt automated transcript first (instant)
        transcript = fetcher.fetch_transcript(url)
        calls = []

        if transcript and len(transcript) > 100:
            print(f"-> Transcript found ({len(transcript)} chars). Extracting calls...")
            try:
                calls = parser.extract_calls_from_text(transcript, expected_segment=segment)
            except Exception as e:
                logger.error(f"Text parsing failed: {e}")

        # 2. If no calls or transcript, download audio and use multimodal Gemini
        if not calls:
            print("-> No transcript calls found. Downloading audio segment...")
            try:
                audio_path = fetcher.download_video_audio(url, duration_minutes=25)
                if audio_path and os.path.exists(audio_path):
                    print(f"-> Uploading audio '{audio_path}' ({os.path.getsize(audio_path)/1024/1024:.2f} MB) to Gemini...")
                    calls = parser.extract_calls_from_audio(audio_path, expected_segment=segment)
                    
                    # Cleanup local temp audio file
                    try:
                        os.remove(audio_path)
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Audio download/parse error: {e}")

        print(f"-> Extracted {len(calls)} calls from '{name}'.")
        for c in calls:
            print(f"   [{c.call_type}] {c.stock_name} | CMP: {c.cmp} | T1: {c.target_1} | T2: {c.target_2} | SL: {c.stop_loss} | Type: {c.instrument_type} | Time: {c.current_date}")

        if calls:
            total_calls_all.extend(calls)
            try:
                inserted, skipped = sheets.append_calls(calls)
                total_inserted += inserted
                total_skipped += skipped
                print(f"-> Google Sheet Sync: {inserted} rows inserted, {skipped} duplicate rows skipped.")
            except Exception as e:
                logger.error(f"Failed to append to Google Sheet: {e}")

    print("\n" + "=" * 70)
    print("BATCH EXTRACTION COMPLETE")
    print(f"Total Calls Extracted: {len(total_calls_all)}")
    print(f"Total Rows Inserted:  {total_inserted}")
    print(f"Total Duplicates:     {total_skipped}")
    print("=" * 70)


if __name__ == "__main__":
    run_batch()
