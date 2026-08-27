"""
Target Schema Definition for CNBC Awaaz Market Call Parser.
Strictly adheres to the 8-column Google Sheets contract.
"""

from typing import Optional, List, Any
from pydantic import BaseModel, Field
from datetime import datetime


class StockCall(BaseModel):
    """
    Represents a single trading call/recommendation from CNBC Awaaz.
    """
    current_date: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        description="Date and time of the recommendation in YYYY-MM-DD HH:MM:SS format."
    )
    call_type: str = Field(
        default="Trade Recommendation",
        description="The show segment or call category (e.g. 'Pehla Sauda', 'Sasta Option', 'Chart Ka Chamatkar', 'BTST', 'Spotlight Stocks', 'Cash Calls')."
    )
    stock_name: str = Field(
        ...,
        description="NSE Ticker or Option/Futures identifier (e.g., 'RELIANCE', 'TATA MOTORS 1050 CE', 'SAIL', 'NIFTY 24500 CE')."
    )
    cmp: Optional[float] = Field(
        default=None,
        description="Current Market Price / Recommended entry price at the time of call. null if not mentioned."
    )
    target_1: Optional[float] = Field(
        default=None,
        description="Primary price target objective."
    )
    target_2: Optional[float] = Field(
        default=None,
        description="Secondary target price objective, if mentioned."
    )
    stop_loss: Optional[float] = Field(
        default=None,
        description="Strict stop loss / invalidation price level."
    )
    instrument_type: str = Field(
        default="Cash",
        description="Type of financial instrument: 'Cash', 'Futures', or 'Options'."
    )
    analyst_name: Optional[str] = Field(
        default=None,
        description="Name of the market analyst who gave the call (optional metadata)."
    )
    remarks: Optional[str] = Field(
        default=None,
        description="Brief context or reasoning (optional metadata)."
    )

    def to_sheet_row(self) -> List[Any]:
        """
        Converts the call into an 8-column list strictly matching Google Sheets:
        [Current Date, Call Type, Stock Name, CMP, Target 1, Target 2, Stop Loss, Instrument Type]
        """
        return [
            str(self.current_date),
            str(self.call_type),
            str(self.stock_name).upper().strip(),
            self.cmp if self.cmp is not None else "-",
            self.target_1 if self.target_1 is not None else "-",
            self.target_2 if self.target_2 is not None else "-",
            self.stop_loss if self.stop_loss is not None else "-",
            str(self.instrument_type)
        ]

    def deduplication_key(self) -> str:
        """
        Unique key to prevent inserting duplicate calls on the same date.
        """
        date_str = str(self.current_date).strip()[:10]
        t1 = self.target_1 if self.target_1 is not None else "-"
        sl = self.stop_loss if self.stop_loss is not None else "-"
        return f"{date_str}|{self.call_type}|{self.stock_name.upper().strip()}|{t1}|{sl}"


class StockCallsBatch(BaseModel):
    """
    Container for multiple extracted calls from a segment audio chunk.
    """
    calls: List[StockCall] = Field(
        default_factory=list,
        description="List of all stock/index recommendations extracted from the broadcast."
    )
