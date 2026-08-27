"""
Gemini Multimodal LLM Extraction Service.
Transcribes and extracts structured trade setups from CNBC Awaaz Hindi/Hinglish broadcast audio.
Uses the official Google GenAI SDK (google-genai) with Pydantic JSON schema enforcement.
"""

import os
import logging
from typing import Optional, List
from datetime import datetime
from google import genai
from google.genai import types
from schema import StockCall, StockCallsBatch

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are a senior Indian stock market analyst and expert financial transcriptionist.
Your task is to analyze the CNBC Awaaz Hindi/Hinglish market broadcast audio or transcript and extract every single stock trading recommendation, investment pick, options call, futures call, and index level setup given by anchors (e.g., Anuj Singhal) and guest analysts (e.g., Prakash Gaba, Kunal Bothra, Mitessh Thakkar, Ashwani Gujral, etc.).

### Show Segments & Call Types:
- "Pehla Sauda" (Early morning opening trades)
- "Spotlight Stocks" / "Top 20 Stocks"
- "Cash Calls" (Equity buy/sell recommendations)
- "Sasta Option" / "Option Strategy" (Call/Put options e.g. 'TATA MOTORS 1050 CE')
- "Chart Ka Chamatkar" / "Chart GPT"
- "Final Trade" / "BTST" / "STBT" (Closing / Overnight trades)
- "Trade Recommendation" / "Index Level"

### Extraction Rules:
- **current_date**: Exact timestamp in 'YYYY-MM-DD HH:MM:SS' format ({CURRENT_TIMESTAMP}).
- **call_type**: The segment name or recommendation type.
- **stock_name**: Official NSE symbol or derivative name (e.g. 'RELIANCE', 'TATA MOTORS', 'NIFTY 24500 CE', 'BANKNIFTY 51000 PE').
- **cmp**: Current market price or entry level if mentioned (float or null).
- **target_1**: Primary target price (float or null).
- **target_2**: Secondary target price (float or null).
- **stop_loss**: Stop loss price (float or null).
- **instrument_type**: 'Cash', 'Futures', or 'Options'.
- **analyst_name**: Analyst or speaker name if recognized (optional).
- **remarks**: Rationale or holding timeframe (optional).
"""


FALLBACK_MODELS = ["gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash-lite"]


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

        current_date = date_str or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prompt = EXTRACTION_SYSTEM_PROMPT.format(CURRENT_TIMESTAMP=current_date)
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
            
            # Ensure current_date is stamped
            for call in batch.calls:
                if not call.current_date:
                    call.current_date = current_date
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

        current_date = date_str or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prompt = EXTRACTION_SYSTEM_PROMPT.format(CURRENT_TIMESTAMP=current_date)
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
        return batch.calls
