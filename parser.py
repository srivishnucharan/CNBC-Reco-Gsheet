"""
Gemini Multimodal LLM Extraction Service.
Transcribes and extracts structured trade setups from CNBC Awaaz Hindi/Hinglish broadcast audio.
Uses the official Google GenAI SDK (google-genai) with Pydantic JSON schema enforcement.
"""

import os
import logging
from typing import Optional, List
from datetime import datetime, timedelta
import pytz
from google import genai
from google.genai import types
from schema import StockCall, StockCallsBatch

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

EXTRACTION_SYSTEM_PROMPT = """You are a senior Indian stock market analyst and expert financial transcriptionist.
Your task is to analyze the CNBC Awaaz Hindi/Hinglish market broadcast audio or transcript and extract every single stock trading recommendation, investment pick, options call, futures call, and index level setup given by anchors (e.g., Anuj Singhal, Ashish Verma, Deepali Rana) and guest analysts (e.g., Prakash Gaba, Kunal Bothra, Mitessh Thakkar, Ashwani Gujral, Vikas Salunkhe, etc.).

### Show Segments & Call Types:
- "Pehla Sauda" (Early morning opening trades)
- "Spotlight Stocks" / "Top 20 Stocks"
- "Cash Calls" (Equity buy/sell recommendations)
- "Sasta Option" / "Option Strategy" (Call/Put options e.g. 'TATA MOTORS 1050 CE', 'NIFTY 24500 CE')
- "Chart Ka Chamatkar" / "Chart GPT"
- "F&O Superstar" (Futures and Options high-conviction trades)
- "Midcap Funda" / "Mahurat Pick"
- "Final Trade" / "BTST" / "STBT" (Closing / Overnight trades)
- "Trade Recommendation" / "Index Level"

### Strict Extraction Rules:
- **current_date**: Exact timestamp in 'YYYY-MM-DD HH:MM:SS' format in INDIAN STANDARD TIME (IST, UTC+05:30). Default base IST time is: {CURRENT_TIMESTAMP_IST}. All timestamps MUST be in IST (market hours between 07:00:00 and 16:00:00 IST). NEVER return UTC times.
- **call_type**: The exact segment name or recommendation type.
- **stock_name**: Official NSE symbol or derivative name (e.g. 'RELIANCE', 'DIVISLAB', 'SUPREMEIND SEP 3650 CE', 'BANKNIFTY 51000 PE').
- **cmp**: Current market price or entry level when the call was given (numeric float).
- **target_1**: Primary upside target price (or downside target for Sell/Short). ALWAYS extract if mentioned.
- **target_2**: Extended or secondary target price if a range or multiple targets are stated (e.g., 'Target 9350 and 9400' -> target_1=9350.0, target_2=9400.0).
- **stop_loss**: Strict stop loss price level (numeric float). ALWAYS extract if mentioned.
- **instrument_type**: Exactly one of 'Cash', 'Futures', or 'Options'.
- **analyst_name**: Analyst or speaker name giving the recommendation (e.g. 'Prakash Gaba', 'Kunal Bothra', 'Anuj Singhal').
- **remarks**: Technical rationale, chart pattern, support/resistance, or timeframe (e.g., 'Intraday breakout', 'Positional buy', 'Breakout on weekly charts', 'Result reaction').
"""


FALLBACK_MODELS = ["gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash-lite"]


def normalize_ist_timestamp(raw_date_str: Optional[str], default_ist_str: str) -> str:
    """Ensures timestamp is strictly in Indian Standard Time (YYYY-MM-DD HH:MM:SS)."""
    if not raw_date_str:
        return default_ist_str
    raw_date_str = raw_date_str.strip()
    try:
        dt = datetime.strptime(raw_date_str, "%Y-%m-%d %H:%M:%S")
        # If hour is < 6, it was likely extracted in UTC (e.g. 03:45 UTC -> 09:15 IST)
        if dt.hour < 6:
            dt = dt + timedelta(hours=5, minutes=30)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        return raw_date_str
    except Exception:
        return default_ist_str


class CNBCParser:
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-3.6-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Please set it in your .env file or environment."
            )
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        self.client = genai.Client(api_key=self.api_key)

    def _generate_with_fallback(self, contents: list, config: types.GenerateContentConfig):
        """
        Executes generate_content with automatic fallback to alternate models on 503 / high demand spikes.
        """
        models_to_try = [self.model_name] + [m for m in FALLBACK_MODELS if m != self.model_name]
        last_error = None

        for model in models_to_try:
            try:
                logger.info(f"Invoking Gemini model: {model}...")
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
                return response
            except Exception as e:
                err_str = str(e)
                logger.warning(f"Model {model} encountered error: {err_str[:200]}. Attempting fallback...")
                last_error = e
                import time
                time.sleep(2)

        raise last_error

    def extract_calls_from_audio(
        self,
        audio_path: str,
        expected_segment: Optional[str] = None,
        date_str: Optional[str] = None
    ) -> List[StockCall]:
        """
        Uploads audio chunk to Gemini Files API and performs structured trade extraction.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file '{audio_path}' not found.")

        current_date_ist = date_str or datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        prompt = EXTRACTION_SYSTEM_PROMPT.format(CURRENT_TIMESTAMP_IST=current_date_ist)
        if expected_segment:
            prompt += f"\nNote: This audio is specifically captured from the '{expected_segment}' broadcast window."

        uploaded_file = None
        try:
            logger.info(f"Uploading audio file '{audio_path}' to Gemini API...")
            uploaded_file = self.client.files.upload(file=audio_path)
            logger.info(f"File uploaded successfully (URI: {uploaded_file.uri}). Generating structured extraction...")

            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=StockCallsBatch,
                temperature=0.1
            )

            response = self._generate_with_fallback(
                contents=[uploaded_file, prompt],
                config=config
            )

            if not response or not response.text:
                logger.warning("Empty response received from Gemini.")
                return []

            # Parse and validate using Pydantic
            batch = StockCallsBatch.model_validate_json(response.text)
            logger.info(f"Successfully extracted {len(batch.calls)} calls from audio.")
            
            # Ensure strict IST timestamps and segment names
            for call in batch.calls:
                call.current_date = normalize_ist_timestamp(call.current_date, current_date_ist)
                if expected_segment and (not call.call_type or call.call_type == "Trade Recommendation"):
                    call.call_type = expected_segment

            return batch.calls

        except Exception as e:
            logger.error(f"Failed to extract calls from audio: {e}", exc_info=True)
            raise
        finally:
            if uploaded_file is not None:
                try:
                    logger.debug(f"Cleaning up uploaded file {uploaded_file.name} from Gemini API...")
                    self.client.files.delete(name=uploaded_file.name)
                except Exception as de:
                    logger.debug(f"Failed to delete Gemini temporary file: {de}")

    def extract_calls_from_text(
        self,
        transcript_text: str,
        expected_segment: Optional[str] = None,
        date_str: Optional[str] = None
    ) -> List[StockCall]:
        """
        Fallback extraction method for text transcripts or video closed captions.
        """
        if not transcript_text.strip():
            return []

        current_date_ist = date_str or datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        prompt = EXTRACTION_SYSTEM_PROMPT.format(CURRENT_TIMESTAMP_IST=current_date_ist)
        if expected_segment:
            prompt += f"\nNote: This segment is '{expected_segment}'."

        user_content = f"TRANSCRIPT CONTENT:\n{transcript_text}"

        logger.info("Extracting calls from transcript text via Gemini...")
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=StockCallsBatch,
            temperature=0.1
        )

        response = self._generate_with_fallback(
            contents=[prompt, user_content],
            config=config
        )

        batch = StockCallsBatch.model_validate_json(response.text)
        logger.info(f"Extracted {len(batch.calls)} calls from transcript text.")
        for call in batch.calls:
            call.current_date = normalize_ist_timestamp(call.current_date, current_date_ist)
            if expected_segment and (not call.call_type or call.call_type == "Trade Recommendation"):
                call.call_type = expected_segment
        return batch.calls
