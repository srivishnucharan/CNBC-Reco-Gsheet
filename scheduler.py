"""
Market Hours Scheduler (IST Timezone).
Automates ingestion at the completion of each CNBC Awaaz show window.
"""

import time
import logging
from typing import Optional
from datetime import datetime
import pytz
import schedule
from pipeline import CNBCPipeline
from telegram_bot import TelegramNotifier, TelegramCommandBot

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")
notifier = TelegramNotifier()

# Predefined schedule execution map (IST)
SCHEDULE_JOBS = [
    {
        "time": "09:00",
        "duration_mins": 25,
        "segment_name": "Spotlight Stocks & Chart GPT-1",
        "description": "Spotlight Stocks, Chart GPT-1, Index Levels"
    },
    {
        "time": "09:20",
        "duration_mins": 20,
        "segment_name": "Pehla Sauda & Chart GPT-2",
        "description": "Chart GPT-2, Pehla Sauda (Opening Market Calls)"
    },
    {
        "time": "10:20",
        "duration_mins": 60,
        "segment_name": "Cash Calls & Sasta Option",
        "description": "Cash Calls, Sasta Option, Chart Ka Chamatkar"
    },
    {
        "time": "14:45",
        "duration_mins": 20,
        "segment_name": "Trade Recommendations",
        "description": "Mid-market & Afternoon Trade Recommendations"
    },
    {
        "time": "15:25",
        "duration_mins": 25,
        "segment_name": "BTST & STBT",
        "description": "Closing BTST (Buy Today Sell Tomorrow) / STBT Calls"
    }
]


def is_market_day() -> bool:
    """Checks if today is a weekday (Monday = 0 to Friday = 4) in IST."""
    now_ist = datetime.now(IST)
    return now_ist.weekday() < 5  # Mon-Fri


def execute_job(pipeline: CNBCPipeline, job_config: dict):
    """
    Executes a single scheduled extraction job.
    """
    now_ist = datetime.now(IST)
    if not is_market_day():
        logger.info(f"Skipping job {job_config['segment_name']}: Weekend ({now_ist.strftime('%A')}).")
        return

    logger.info(f"=== [IST {now_ist.strftime('%H:%M:%S')}] Executing Scheduled Job: {job_config['segment_name']} ===")
    logger.info(f"Description: {job_config['description']}")

    try:
        calls, inserted, skipped = pipeline.process_live_segment(
            segment_name=job_config["segment_name"],
            duration_minutes=job_config["duration_mins"]
        )
        logger.info(
            f"=== Job Finished: {job_config['segment_name']} -> {len(calls)} extracted, "
            f"{inserted} inserted into Sheets, {skipped} skipped duplicates ==="
        )
        # Send Telegram notification on successful run
        notifier.send_run_summary(
            segment_name=job_config["segment_name"],
            calls=calls,
            inserted=inserted,
            skipped=skipped
        )
    except Exception as e:
        logger.error(f"Error during scheduled execution of {job_config['segment_name']}: {e}", exc_info=True)
        notifier.send_run_summary(
            segment_name=job_config["segment_name"],
            calls=[],
            inserted=0,
            skipped=0,
            error_msg=str(e)
        )


def start_scheduler(pipeline: Optional[CNBCPipeline] = None):
    """
    Registers all daily market jobs and starts the scheduler daemon with Telegram bot commands.
    """
    if pipeline is None:
        pipeline = CNBCPipeline()

    # Start Telegram on-demand command listener in background
    bot = TelegramCommandBot(pipeline=pipeline, scheduler=schedule)
    bot.start()

    logger.info("Initializing CNBC Awaaz Market Scheduler...")
    logger.info(f"Current IST Time: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S %Z')}")

    for job in SCHEDULE_JOBS:
        trigger_time = job["time"]
        logger.info(f"Registered Job: {trigger_time} IST -> '{job['segment_name']}' (trailing {job['duration_mins']} mins)")
        schedule.every().day.at(trigger_time).do(execute_job, pipeline=pipeline, job_config=job)

    logger.info("Scheduler running in background. Waiting for next market trigger...")
    while True:
        schedule.run_pending()
        time.sleep(10)

