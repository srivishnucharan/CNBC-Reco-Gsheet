"""
CNBC Awaaz Automated Market Call Parser - CLI & Entry Point.
"""

import sys
import argparse
import logging
from pipeline import CNBCPipeline
from scheduler import start_scheduler

# Configure rich logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("CNBC-Main")


def main():
    parser = argparse.ArgumentParser(
        description="Automated Market Call Parser (CNBC Awaaz to Google Sheets)"
    )

    parser.add_argument(
        "--test-auth",
        action="store_true",
        help="Test connections to Google Sheets and Gemini API."
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Start the background scheduler daemon for IST market hours."
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Path to a local audio file (.mp3, .wav, .m4a) to parse."
    )
    parser.add_argument(
        "--url",
        type=str,
        help="YouTube video URL to download and parse."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Trigger an immediate live stream capture and extraction."
    )
    parser.add_argument(
        "--segment",
        type=str,
        default="Trade Recommendation",
        help="Show segment name (e.g., 'Sasta Option', 'Pehla Sauda', 'Chart Ka Chamatkar')."
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=25,
        help="Trailing duration in minutes to capture for live extraction (default: 25)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract calls and display in terminal without writing to Google Sheets."
    )

    args = parser.parse_args()

    # Route Actions
    if args.test_auth:
        pipeline = CNBCPipeline()
        logger.info("Running connection tests...")
        success = pipeline.test_connections()
        if success:
            logger.info("ALL SYSTEMS OPERATIONAL: Google Sheets & Gemini API connected successfully!")
        else:
            logger.error("Connection test failed. Please check logs above.")
            sys.exit(1)

    elif args.schedule:
        pipeline = CNBCPipeline()
        logger.info("Starting automated market hours daemon...")
        start_scheduler(pipeline)

    elif args.file:
        pipeline = CNBCPipeline()
        logger.info(f"Processing local audio file: {args.file}")
        calls, inserted, skipped = pipeline.process_audio_file(
            audio_path=args.file,
            segment_name=args.segment,
            dry_run=args.dry_run
        )
        print(f"\nResult: {len(calls)} calls extracted, {inserted} inserted, {skipped} duplicates skipped.")

    elif args.url:
        pipeline = CNBCPipeline()
        logger.info(f"Processing YouTube URL: {args.url}")
        calls, inserted, skipped = pipeline.process_video_url(
            video_url=args.url,
            segment_name=args.segment,
            duration_minutes=args.duration
        )
        print(f"\nResult: {len(calls)} calls extracted, {inserted} inserted, {skipped} duplicates skipped.")

    elif args.live:
        pipeline = CNBCPipeline()
        logger.info(f"Running on-demand live extraction for '{args.segment}' ({args.duration} mins)...")
        calls, inserted, skipped = pipeline.process_live_segment(
            segment_name=args.segment,
            duration_minutes=args.duration
        )
        print(f"\nResult: {len(calls)} calls extracted, {inserted} inserted, {skipped} duplicates skipped.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
