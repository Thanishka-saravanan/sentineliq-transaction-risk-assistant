from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
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


class AmountProfile(BaseModel):
    count: int
    total: float
    mean: float
    median: float
    min: float
    max: float
    std_dev: float
    q1: float
    q3: float
    iqr: float
    typical_lower_bound: float
    typical_upper_bound: float


class TimeProfile(BaseModel):
    hourly_counts: Dict[str, int]
    earliest_hour: int
    latest_hour: int
    median_hour: int
    common_hours: List[int]
    typical_start_hour: int
    typical_end_hour: int
    late_night_transaction_count: int
    late_night_percentage: float


class ChannelProfile(BaseModel):
    channel_counts: Dict[str, int]
    channel_percentages: Dict[str, float]
    common_channels: List[str]
    primary_channel: str


class PayeeProfile(BaseModel):
    unique_payee_count: int
    payee_counts: Dict[str, int]
    most_frequent_payees: List[str]
    payee_percentages: Dict[str, float]


class FrequencyProfile(BaseModel):
    transaction_count: int
    active_days: int
    date_range_days: int
    transactions_per_active_day: float
    transactions_per_calendar_day: float
    transactions_per_week: float


class CustomerBaseline(BaseModel):
    customer_id: str
    generated_at: Optional[str] = None
    amount_profile: AmountProfile
    time_profile: TimeProfile
    channel_profile: ChannelProfile
    payee_profile: PayeeProfile
    frequency_profile: FrequencyProfile


class TypicalAmountRange(BaseModel):
    lower: float
    upper: float


class UsualTransactionHours(BaseModel):
    start: int
    end: int


class CustomerBaselineSummary(BaseModel):
    customer_id: str
    transaction_count: int
    typical_amount: float
    typical_amount_range: TypicalAmountRange
    usual_transaction_hours: UsualTransactionHours
    common_channels: List[str]
    frequent_payees: List[str]


class RiskFinding(BaseModel):
    finding_id: str
    customer_id: str
    rule_id: str
    title: str
    severity: str  # "low", "medium", "high", "critical"
    risk_score: int  # 0 to 100
    score_components: Dict[str, Any]
    transaction_ids: List[str]
    primary_transaction_id: str
    description: str
    evidence: Dict[str, Any]
    investigator_action: str
    limitations: str
    requires_human_review: bool = True
    detected_at: Optional[str] = None


class RiskAnalysisSummary(BaseModel):
    highest_severity: str
    highest_risk_score: int
    rules_triggered: List[str]
    requires_human_review: bool


class CustomerRiskAnalysis(BaseModel):
    customer_id: str
    customer_name: str
    transaction_count: int
    finding_count: int
    findings: List[RiskFinding]
    summary: RiskAnalysisSummary
    disclaimer: str = (
        "The system identifies activity requiring human review. A risk finding does not establish that fraud has occurred."
    )
