from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class TransactionChannel(str, Enum):
    UPI = "UPI"
    CARD = "CARD"
    NEFT = "NEFT"
    IMPS = "IMPS"
    NET_BANKING = "NET_BANKING"
    CASH = "CASH"
    ACH = "ACH"


class Customer(BaseModel):
    customer_id: str = Field(..., description="Unique customer identifier (e.g., CUST001)")
    name: str = Field(..., description="Full customer name")
    scenario: str = Field(..., description="Short scenario category name")
    description: str = Field(..., description="Detailed profile and behavioural description")

    @field_validator("customer_id", "name", "scenario", "description")
    @classmethod
    def non_empty_string(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return v.strip()


class Transaction(BaseModel):
    transaction_id: str = Field(..., description="Unique transaction ID (e.g., TXN001)")
    customer_id: str = Field(..., description="Associated customer ID")
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    time: str = Field(..., description="Time in HH:MM:SS format")
    description: str = Field(..., description="Transaction narration / description")
    payee: str = Field(..., description="Beneficiary or merchant name")
    amount: float = Field(..., gt=0, description="Transaction monetary amount (must be positive)")
    channel: str = Field(..., description="Transaction channel")

    @field_validator("transaction_id", "customer_id", "date", "time", "description", "payee")
    @classmethod
    def non_empty_string(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return v.strip()

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Transaction amount must be strictly positive (> 0)")
        return round(float(v), 2)

    @field_validator("channel")
    @classmethod
    def valid_channel(cls, v: str) -> str:
        v_upper = v.strip().upper()
        allowed = {c.value for c in TransactionChannel}
        if v_upper not in allowed:
            raise ValueError(f"Invalid channel '{v}'. Allowed channels: {', '.join(sorted(allowed))}")
        return v_upper

    @property
    def timestamp(self) -> datetime:
        """Returns parsed datetime object for chronological sorting and time calculations."""
        time_part = self.time.strip()
        if len(time_part.split(":")) == 2:
            time_part += ":00"
        return datetime.strptime(f"{self.date} {time_part}", "%Y-%m-%d %H:%M:%S")

    @property
    def hour(self) -> int:
        return self.timestamp.hour


class RiskRuleDefinition(BaseModel):
    rule_id: str
    title: str
    purpose: str
    detection_criteria: str
    evidence_required: List[str]
    severity_guidance: str
    investigator_action: str
    limitations: str
