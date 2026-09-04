from collections import Counter
from datetime import datetime
import math
from typing import Dict, List, Optional
import numpy as np

from src.models import (
    AmountProfile,
    ChannelProfile,
    CustomerBaseline,
    CustomerBaselineSummary,
    FrequencyProfile,
    PayeeProfile,
    TimeProfile,
    Transaction,
    TypicalAmountRange,
    UsualTransactionHours,
)


def _compute_amount_profile(amounts: List[float]) -> AmountProfile:
    """Computes deterministic statistical amount distribution."""
    count = len(amounts)
    if count == 0:
        return AmountProfile(
            count=0,
            total=0.0,
            mean=0.0,
            median=0.0,
            min=0.0,
            max=0.0,
            std_dev=0.0,
            q1=0.0,
            q3=0.0,
            iqr=0.0,
            typical_lower_bound=0.0,
            typical_upper_bound=0.0,
        )

    total = round(float(sum(amounts)), 2)
    mean_val = round(float(np.mean(amounts)), 2)
    median_val = round(float(np.median(amounts)), 2)
    min_val = round(float(min(amounts)), 2)
    max_val = round(float(max(amounts)), 2)

    if count > 1:
        # Sample standard deviation (ddof=1)
        std_val = round(float(np.std(amounts, ddof=1)), 2)
    else:
        std_val = 0.0

    q1_val = round(float(np.percentile(amounts, 25)), 2)
    q3_val = round(float(np.percentile(amounts, 75)), 2)
    iqr_val = round(max(0.0, q3_val - q1_val), 2)

    lower_bound = max(0.0, round(q1_val - 1.5 * iqr_val, 2))
    upper_bound = round(q3_val + 1.5 * iqr_val, 2)

    return AmountProfile(
        count=count,
        total=total,
        mean=mean_val,
        median=median_val,
        min=min_val,
        max=max_val,
        std_dev=std_val,
        q1=q1_val,
        q3=q3_val,
        iqr=iqr_val,
        typical_lower_bound=lower_bound,
        typical_upper_bound=upper_bound,
    )


def _compute_time_profile(transactions: List[Transaction]) -> TimeProfile:
    """Computes deterministic temporal distribution metrics."""
    # Initialize 24-hour buckets
    hourly_counts: Dict[str, int] = {f"{h:02d}": 0 for h in range(24)}

    if not transactions:
        return TimeProfile(
            hourly_counts=hourly_counts,
            earliest_hour=0,
            latest_hour=0,
            median_hour=0,
            common_hours=[],
            typical_start_hour=0,
            typical_end_hour=0,
            late_night_transaction_count=0,
            late_night_percentage=0.0,
        )

    hours: List[int] = []
    late_night_count = 0

    for t in transactions:
        h = t.hour
        hours.append(h)
        hourly_counts[f"{h:02d}"] += 1
        if 0 <= h <= 5:  # 00:00 to 05:59 window
            late_night_count += 1

    total_count = len(transactions)
    earliest = min(hours)
    latest = max(hours)
    median_h = int(round(float(np.median(hours))))

    # Common hours: sorted by count descending, then hour ascending
    active_hours = [(h, hourly_counts[f"{h:02d}"]) for h in range(24) if hourly_counts[f"{h:02d}"] > 0]
    active_hours.sort(key=lambda x: (-x[1], x[0]))
    common_hours = [h for h, _ in active_hours]

    # Typical activity window: 10th and 90th percentiles of historical hours
    if total_count >= 5:
        start_h = int(np.percentile(hours, 10))
        end_h = int(np.percentile(hours, 90))
    else:
        start_h = earliest
        end_h = latest

    if start_h > end_h:
        start_h, end_h = end_h, start_h

    late_night_pct = round((late_night_count / total_count) * 100.0, 2)

    return TimeProfile(
        hourly_counts=hourly_counts,
        earliest_hour=earliest,
        latest_hour=latest,
        median_hour=median_h,
        common_hours=common_hours,
        typical_start_hour=start_h,
        typical_end_hour=end_h,
        late_night_transaction_count=late_night_count,
        late_night_percentage=late_night_pct,
    )


def _compute_channel_profile(transactions: List[Transaction]) -> ChannelProfile:
    """Computes deterministic banking channel usage distribution."""
    if not transactions:
        return ChannelProfile(
            channel_counts={},
            channel_percentages={},
            common_channels=[],
            primary_channel="",
        )

    counts = Counter(t.channel for t in transactions)
    # Sort deterministically: count desc, channel name asc
    sorted_channels = sorted(counts.items(), key=lambda x: (-x[1], x[0]))

    total = len(transactions)
    channel_counts = {ch: count for ch, count in sorted_channels}
    channel_percentages = {ch: round((count / total) * 100.0, 2) for ch, count in sorted_channels}
    common_channels = [ch for ch, _ in sorted_channels]
    primary_channel = common_channels[0] if common_channels else ""

    return ChannelProfile(
        channel_counts=channel_counts,
        channel_percentages=channel_percentages,
        common_channels=common_channels,
        primary_channel=primary_channel,
    )


def _compute_payee_profile(transactions: List[Transaction]) -> PayeeProfile:
    """Computes deterministic payee interaction profile."""
    if not transactions:
        return PayeeProfile(
            unique_payee_count=0,
            payee_counts={},
            most_frequent_payees=[],
            payee_percentages={},
        )

    counts = Counter(t.payee for t in transactions)
    # Sort deterministically: 1. count descending, 2. payee name ascending
    sorted_payees = sorted(counts.items(), key=lambda x: (-x[1], x[0]))

    total = len(transactions)
    payee_counts = {p: count for p, count in sorted_payees}
    payee_percentages = {p: round((count / total) * 100.0, 2) for p, count in sorted_payees}
    most_frequent = [p for p, _ in sorted_payees[:5]]

    return PayeeProfile(
        unique_payee_count=len(counts),
        payee_counts=payee_counts,
        most_frequent_payees=most_frequent,
        payee_percentages=payee_percentages,
    )


def _compute_frequency_profile(transactions: List[Transaction]) -> FrequencyProfile:
    """Computes deterministic transaction frequency and velocity metrics."""
    count = len(transactions)
    if count == 0:
        return FrequencyProfile(
            transaction_count=0,
            active_days=0,
            date_range_days=0,
            transactions_per_active_day=0.0,
            transactions_per_calendar_day=0.0,
            transactions_per_week=0.0,
        )

    dates = [datetime.strptime(t.date, "%Y-%m-%d") for t in transactions]
    unique_dates = set(dates)
    active_days = len(unique_dates)

    min_date = min(dates)
    max_date = max(dates)
    date_range_days = (max_date - min_date).days + 1

    txns_per_active = round(count / active_days, 2) if active_days > 0 else 0.0
    txns_per_calendar = round(count / date_range_days, 2) if date_range_days > 0 else 0.0
    txns_per_week = round((count / date_range_days) * 7.0, 2) if date_range_days > 0 else 0.0

    return FrequencyProfile(
        transaction_count=count,
        active_days=active_days,
        date_range_days=date_range_days,
        transactions_per_active_day=txns_per_active,
        transactions_per_calendar_day=txns_per_calendar,
        transactions_per_week=txns_per_week,
    )


def build_customer_baseline(
    transactions: List[Transaction], customer_id: Optional[str] = None
) -> CustomerBaseline:
    """
    Constructs a complete, deterministic customer baseline behavioral profile.
    
    Contains:
    - Amount profile (mean, median, Q1, Q3, IQR, typical bounds)
    - Time profile (hourly counts, median hour, active window, late-night metrics)
    - Channel profile (counts, percentages, primary channel)
    - Payee profile (unique count, sorted frequencies, percentages)
    - Frequency profile (active days, calendar span, velocity)
    """
    # Infer customer_id from transactions if not passed explicitly
    if not customer_id:
        if transactions:
            customer_id = transactions[0].customer_id
        else:
            customer_id = "UNKNOWN"

    amounts = [t.amount for t in transactions]

    return CustomerBaseline(
        customer_id=customer_id,
        generated_at=None,  # Strictly None for reproducibility and determinism
        amount_profile=_compute_amount_profile(amounts),
        time_profile=_compute_time_profile(transactions),
        channel_profile=_compute_channel_profile(transactions),
        payee_profile=_compute_payee_profile(transactions),
        frequency_profile=_compute_frequency_profile(transactions),
    )


def build_baseline_for_history(
    transactions: List[Transaction], customer_id: Optional[str] = None
) -> CustomerBaseline:
    """Alias for building customer baseline from historical records."""
    return build_customer_baseline(transactions, customer_id=customer_id)


def build_baseline_excluding_transaction(
    transactions: List[Transaction],
    transaction_id: str,
    customer_id: Optional[str] = None,
) -> CustomerBaseline:
    """
    Constructs a customer baseline excluding a specific target transaction.
    
    Prevents self-influence / data leakage when evaluating whether that target
    transaction is an anomaly relative to historical behavior.
    """
    filtered = [t for t in transactions if t.transaction_id != transaction_id]
    return build_customer_baseline(filtered, customer_id=customer_id)


def build_baseline_summary(baseline: CustomerBaseline) -> CustomerBaselineSummary:
    """Produces a concise, human-readable summary of the customer baseline."""
    return CustomerBaselineSummary(
        customer_id=baseline.customer_id,
        transaction_count=baseline.amount_profile.count,
        typical_amount=baseline.amount_profile.median,
        typical_amount_range=TypicalAmountRange(
            lower=baseline.amount_profile.typical_lower_bound,
            upper=baseline.amount_profile.typical_upper_bound,
        ),
        usual_transaction_hours=UsualTransactionHours(
            start=baseline.time_profile.typical_start_hour,
            end=baseline.time_profile.typical_end_hour,
        ),
        common_channels=baseline.channel_profile.common_channels,
        frequent_payees=baseline.payee_profile.most_frequent_payees,
    )
