import os
import sys
import time
import logging
import threading
import requests
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
import pytz
from dotenv import load_dotenv

from schema import StockCall

load_dotenv()
logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1Dvoo6EOgVnj-TgIZSq-Ir_VN2QOh0rAxPK1Ocp6siOU")
GSHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"


class TelegramNotifier:
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id and self.api_url)

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.is_configured:
            logger.warning("Telegram bot credentials not configured, skipping message.")
            return False

        try:
            resp = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True
                },
                timeout=15
            )
            if resp.status_code == 200:
                return True
            else:
                logger.error(f"Failed to send Telegram message: {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")
            return False

    def send_run_summary(
        self,
        segment_name: str,
        calls: List[StockCall],
        inserted: int,
        skipped: int,
        duration_seconds: Optional[float] = None,
        error_msg: Optional[str] = None
    ) -> bool:
        now_ist = datetime.now(IST).strftime("%d %b %Y, %I:%M:%S %p IST")

        if error_msg:
            msg = (
                f"⚠️ <b>CNBC Tracker Run Failed</b>\n\n"
                f"<b>Segment:</b> {segment_name}\n"
                f"<b>Time:</b> {now_ist}\n"
                f"<b>Error:</b> <code>{error_msg}</code>\n\n"
                f"<i>System will retry on next schedule.</i>"
            )
            return self.send_message(msg)

        # Header
        lines = [
            f"📊 <b>CNBC Awaaz Run Completed</b>",
            f"<b>Segment:</b> {segment_name}",
            f"<b>Time:</b> {now_ist}",
            f"<b>Extracted:</b> {len(calls)} calls | <b>Added:</b> {inserted} new ({skipped} skipped duplicates)\n"
        ]

        if not calls:
            lines.append("<i>No stock trading calls found in this segment buffer.</i>")
        else:
            lines.append("<b>📈 Extracted Recommendations:</b>")
            for idx, c in enumerate(calls, 1):
                badge = "🟢" if c.call_type == "BUY" else ("🔴" if c.call_type == "SELL" else "🟡")
                t1 = f"₹{c.target_1:,.2f}" if c.target_1 else "-"
                t2 = f", T2: ₹{c.target_2:,.2f}" if c.target_2 else ""
                sl = f"₹{c.stop_loss:,.2f}" if c.stop_loss else "-"
                cmp_str = f"₹{c.cmp:,.2f}" if c.cmp else "-"
                analyst = c.analyst_name or "CNBC Analyst"
                inst = f" [{c.instrument_type}]" if c.instrument_type and c.instrument_type != "CASH" else ""

                card = (
                    f"{idx}. {badge} <b>{c.stock_name}</b>{inst} - <b>{c.call_type}</b>\n"
                    f"   • CMP: {cmp_str} | T1: {t1}{t2} | SL: {sl}\n"
                    f"   • Analyst: {analyst}"
                )
                lines.append(card)

        lines.append(f"\n🔗 <a href='{GSHEET_URL}'>View Google Sheet</a>")
        return self.send_message("\n".join(lines))


class TelegramCommandBot:
    """
    Listens for Telegram commands (/run, /status, /today, /help) in background.
    """
    def __init__(self, pipeline=None, scheduler=None):
        self.notifier = TelegramNotifier()
        self.pipeline = pipeline
        self.scheduler = scheduler
        self.last_update_id = 0
        self.running = False
        self._thread = None
        self._lock = threading.Lock()

    def start(self):
        if not self.notifier.is_configured:
            logger.warning("Telegram bot credentials missing, command bot listener not started.")
            return

        self.running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="TelegramBotPollThread")
        self._thread.start()
        logger.info("Telegram Command Bot listener started.")

    def stop(self):
        self.running = False

    def _poll_loop(self):
        while self.running:
            try:
                updates = self._get_updates()
                for u in updates:
                    self._handle_update(u)
            except Exception as e:
                logger.error(f"Error in Telegram poll loop: {e}")
            time.sleep(2)

    def _get_updates(self) -> List[Dict[str, Any]]:
        try:
            params = {"offset": self.last_update_id + 1, "timeout": 5}
            resp = requests.get(f"{self.notifier.api_url}/getUpdates", params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    res = data.get("result", [])
                    if res:
                        self.last_update_id = res[-1]["update_id"]
                    return res
        except Exception:
            pass
        return []

    def _handle_update(self, update: Dict[str, Any]):
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return

        chat = msg.get("chat", {})
        chat_id = str(chat.get("id"))
        # Only respond to authorized chat_id
        if chat_id != str(self.notifier.chat_id):
            logger.warning(f"Ignored unauthorized message from chat_id: {chat_id}")
            return

        text = msg.get("text", "").strip()
        if not text:
            return

        cmd = text.split()[0].lower()
        logger.info(f"Received Telegram command: {cmd}")

        if cmd in ["/start", "/help"]:
            self._cmd_help()
        elif cmd in ["/status", "/health"]:
            self._cmd_status()
        elif cmd in ["/run", "/extract"]:
            threading.Thread(target=self._cmd_run, daemon=True).start()
        elif cmd in ["/today", "/latest"]:
            self._cmd_today()
        else:
            self.notifier.send_message(
                f"Unknown command: <code>{text}</code>\nSend /help to see available commands."
            )

    def _cmd_help(self):
        help_text = (
            "🤖 <b>CNBC Awaaz Market Call Bot Commands</b>\n\n"
            "• <code>/run</code> or <code>/extract</code> — 🚀 Trigger an immediate live market extraction run\n"
            "• <code>/status</code> — ⏱ Check daemon health & next schedule times\n"
            "• <code>/today</code> — 📋 View today's extracted calls\n"
            "• <code>/help</code> — ℹ️ Show this menu\n\n"
            f"🔗 <a href='{GSHEET_URL}'>Open Live Google Sheet</a>"
        )
        self.notifier.send_message(help_text)

    def _cmd_status(self):
        now_ist = datetime.now(IST).strftime("%d %b %Y, %I:%M:%S %p IST")
        sched_info = (
            "• 09:00 IST - Opening Trade / Sectoral Setup\n"
            "• 09:20 IST - Top 20 Stock Picks\n"
            "• 10:20 IST - Cash Calls & Sasta Option\n"
            "• 14:45 IST - Closing Trade Recommendations\n"
            "• 15:25 IST - BTST & STBT Calls"
        )
        msg = (
            f"🟢 <b>CNBC Tracker Daemon: Active & Running</b>\n\n"
            f"<b>Current Time:</b> {now_ist}\n"
            f"<b>Timezone:</b> Asia/Kolkata (IST)\n\n"
            f"<b>Daily Scheduled Jobs:</b>\n{sched_info}\n\n"
            f"🔗 <a href='{GSHEET_URL}'>Google Sheet Link</a>"
        )
        self.notifier.send_message(msg)

    def _cmd_today(self):
        msg = (
            f"📋 <b>Today's Market Calls</b>\n\n"
            f"All morning, mid-session, and closing calls have been updated in your Google Sheet.\n\n"
            f"👉 <a href='{GSHEET_URL}'>Click here to open Google Sheet</a>"
        )
        self.notifier.send_message(msg)

    def _cmd_run(self):
        if not self._lock.acquire(blocking=False):
            self.notifier.send_message("⏳ An extraction run is already in progress. Please wait a moment.")
            return

        self.notifier.send_message("🚀 <b>On-Demand Extraction Started!</b> Ingesting latest stream audio and parsing market calls with Gemini...")
        try:
            from pipeline import CNBCPipeline
            pipeline = self.pipeline or CNBCPipeline()
            calls, ins, skp = pipeline.process_live_segment(
                segment_name="On-Demand Telegram Request",
                duration_minutes=25
            )
            self.notifier.send_run_summary(
                segment_name="On-Demand Telegram Request",
                calls=calls,
                inserted=ins,
                skipped=skp
            )
        except Exception as e:
            logger.error(f"On-demand run failed: {e}")
            self.notifier.send_run_summary(
                segment_name="On-Demand Telegram Request",
                calls=[],
                inserted=0,
                skipped=0,
                error_msg=str(e)
            )
        finally:
            self._lock.release()
