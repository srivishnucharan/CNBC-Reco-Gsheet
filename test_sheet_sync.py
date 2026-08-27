"""
Test end-to-end synchronization to Google Sheets via Webhook.
"""

from schema import StockCall
from sheets import SheetsManager
from dotenv import load_dotenv

load_dotenv()

def main():
    print("Testing Google Sheets sync via Webhook...")
    manager = SheetsManager()

    sample_calls = [
        StockCall(
            current_date="2026-08-26",
            call_type="Sasta Option",
            stock_name="TATA STEEL 150 CE",
            cmp=4.5,
            target_1=8.0,
            target_2=11.0,
            stop_loss=2.0,
            instrument_type="Options"
        ),
        StockCall(
            current_date="2026-08-26",
            call_type="Chart Ka Chamatkar",
            stock_name="SAIL",
            cmp=134.0,
            target_1=146.0,
            target_2=None,
            stop_loss=128.0,
            instrument_type="Cash"
        )
    ]

    inserted, skipped = manager.append_calls(sample_calls)
    print(f"RESULT: Inserted {inserted} calls, Skipped {skipped} duplicates.")

if __name__ == "__main__":
    main()
