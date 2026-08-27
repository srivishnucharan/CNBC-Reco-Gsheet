"""
Unit & Integration tests for CNBC Awaaz Parser and Schema.
"""

from schema import StockCall, StockCallsBatch
from parser import CNBCParser
from dotenv import load_dotenv

load_dotenv()

SAMPLE_HINDI_TRANSCRIPT = """
Anchor: चलिए अब बात करते हैं आज के सस्ता ऑप्शन की। हमारे साथ एक्सपर्ट मौजूद हैं। बताइए आज का सस्ता ऑप्शन कौन सा है?
Expert: नमस्कार। आज का सस्ता ऑप्शन Tata Steel में बन रहा है। Tata Steel 150 का कॉल ऑप्शन (CE) अभी 4 रुपये 50 पैसे पर ट्रेड कर रहा है। इसमें खरीदारी की सलाह है। 
स्टॉपलॉस रखना है 2 रुपये का, और पहला टारगेट होगा 8 रुपये का। अगर मोमेंटम जारी रहा तो दूसरा टारगेट 11 रुपये तक भी जा सकता है।

Anchor: बहुत बढ़िया। Tata Steel 150 CE 4.5 पर खरीदें, SL 2, Target 8 और 11। 
अब चलते हैं आज के 'चार्ट का चमत्कार' की तरफ।
Expert 2: चार्ट का चमत्कार में मेरा पसंदीदा स्टॉक है SAIL (Steel Authority of India)। 
SAIL में 132 के लेवल पर ब्रेकआउट देखने को मिला है। करंट मार्केट प्राइस 134 रुपये है। 
134 पर खरीदारी करें, स्टॉपलॉस लगाएं 128 का, और इसका टारगेट होगा 146 रुपये। यह कैश सेगमेंट का स्टॉक है।

Anchor: ठीक है, SAIL में 134 पर खरीदारी, SL 128, Target 146।
अब एक पहला सौदा कॉल लेते हैं।
Expert 3: पहला सौदा में NIFTY 24500 Call Option खरीदें 120 पर, स्टॉपलॉस 80, पहला टारगेट 180 और दूसरा टारगेट 220।
"""


def test_pydantic_schema():
    print("--- Testing Pydantic Schema ---")
    call = StockCall(
        current_date="2026-08-26",
        call_type="Sasta Option",
        stock_name="TATA STEEL 150 CE",
        cmp=4.5,
        target_1=8.0,
        target_2=11.0,
        stop_loss=2.0,
        instrument_type="Options"
    )
    row = call.to_sheet_row()
    print("Generated 8-column row:", row)
    assert len(row) == 8
    assert row[0] == "2026-08-26"
    assert row[1] == "Sasta Option"
    assert row[2] == "TATA STEEL 150 CE"
    assert row[3] == 4.5
    assert row[4] == 8.0
    assert row[5] == 11.0
    assert row[6] == 2.0
    assert row[7] == "Options"
    print("Schema test passed!\n")


def test_gemini_transcript_extraction():
    print("--- Testing Gemini Hindi/Hinglish Extraction ---")
    parser = CNBCParser()
    calls = parser.extract_calls_from_text(
        transcript_text=SAMPLE_HINDI_TRANSCRIPT,
        expected_segment="Sasta Option"
    )

    print(f"Extracted {len(calls)} calls:")
    for idx, c in enumerate(calls, 1):
        print(f"  [{idx}] {c.call_type} | {c.stock_name} ({c.instrument_type}) | CMP: {c.cmp} | T1: {c.target_1} | T2: {c.target_2} | SL: {c.stop_loss}")
        print(f"      Sheet Row: {c.to_sheet_row()}")

    assert len(calls) >= 2, "Should have extracted at least 2 distinct calls"
    print("\nGemini Hindi Extraction test passed successfully!")


if __name__ == "__main__":
    test_pydantic_schema()
    try:
        test_gemini_transcript_extraction()
    except Exception as e:
        print(f"Note on Gemini test: {e}")
