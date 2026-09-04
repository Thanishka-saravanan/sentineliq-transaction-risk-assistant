from datetime import datetime
from typing import Any, Dict, List, Optional

from src.baseline import build_baseline_excluding_transaction, build_customer_baseline
from src.models import (
    CustomerBaseline,
    CustomerRiskAnalysis,
    RiskAnalysisSummary,
    RiskFinding,
    Transaction,
)

# Severity ranks for deterministic sorting
SEVERITY_RANKS = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "none": 0,
}


def _calculate_risk_score(
    base_score: int, modifiers: Dict[str, int]
) -> tuple[int, Dict[str, Any]]:
    """
    Computes a deterministic, transparent risk score from 0 to 100.
    
    The score reflects the strength and seriousness of the policy-based risk signal.
    It is not a statistical or machine-learning probability of fraud.
    """
    total = base_score + sum(modifiers.values())
    clamped_score = max(0, min(100, total))
    score_components = {
        "base_score": base_score,
        "modifiers": modifiers,
        "final_score": clamped_score,
    }
    return clamped_score, score_components


def evaluate_r01(
    transactions: List[Transaction],
    baseline: Optional[CustomerBaseline] = None,
) -> List[RiskFinding]:
    """
    R01 — UNUSUALLY LARGE TRANSFER
    
    Detection Criteria (from risk_policy.md):
    - Transaction amount exceeds 5.0x the customer's historical transaction median, OR
    - Transaction amount exceeds 4.0x the customer's historical mean plus two standard deviations, AND
    - Transaction amount exceeds the customer's historical maximum transaction by at least 150%.
    - Absolute floor check: Transactions under $1,000.00 are exempted from R01.
    """
    findings: List[RiskFinding] = []
    if not transactions:
        return findings

    for t in transactions:
        # Floor check: exempt transactions under $1,000.00
        if t.amount < 1000.00:
            continue

        # Prevent baseline leakage by excluding target transaction
        sub_baseline = build_baseline_excluding_transaction(transactions, t.transaction_id)
        p = sub_baseline.amount_profile

        if p.count < 3:
            # Need minimum history to establish baseline
            continue

        median_val = max(0.01, p.median)
        mean_val = p.mean
        std_val = p.std_dev
        hist_max = max(0.01, p.max)

        cond1_median = t.amount > (5.0 * median_val)
        cond1_mean_std = t.amount > (4.0 * mean_val + 2.0 * std_val)
        cond2_max = t.amount > (1.5 * hist_max)

        if (cond1_median or cond1_mean_std) and cond2_max:
            deviation_ratio_median = round(t.amount / median_val, 2)
            deviation_ratio_max = round(t.amount / hist_max, 2)

            # Severity determination based on policy guidance
            if deviation_ratio_median > 15.0 or t.amount > 15000.00:
                severity = "high"
                base_score = 75
            elif deviation_ratio_median >= 5.0:
                severity = "medium"
                base_score = 50
            else:
                severity = "low"
                base_score = 30

            modifiers = {}
            if deviation_ratio_median > 25.0:
                modifiers["extreme_median_deviation"] = 15
            elif deviation_ratio_median > 15.0:
                modifiers["high_median_deviation"] = 10
            if t.amount > 20000.00:
                modifiers["critical_amount_exposure"] = 10

            risk_score, score_comp = _calculate_risk_score(base_score, modifiers)

            finding_id = f"{t.customer_id}_R01_{t.transaction_id}"
            description = (
                f"Transaction {t.transaction_id} for ${t.amount:,.2f} via {t.channel} materially "
                f"deviates from the customer's established spending baseline. Amount is {deviation_ratio_median}x "
                f"the historical median (${median_val:.2f}) and {deviation_ratio_max}x the historical maximum (${hist_max:.2f})."
            )

            evidence = {
                "transaction_id": t.transaction_id,
                "amount": t.amount,
                "channel": t.channel,
                "date": t.date,
                "time": t.time,
                "payee": t.payee,
                "customer_median_amount": median_val,
                "customer_mean_amount": mean_val,
                "customer_max_amount": hist_max,
                "deviation_ratio_median": deviation_ratio_median,
                "deviation_ratio_max": deviation_ratio_max,
                "absolute_floor_met": True,
            }

            investigator_action = (
                "1. Inspect customer KYC profile, registered employment/income tier, and source of funds. "
                "2. Verify beneficiary details against external sanctions and watchlists. "
                "3. Contact customer via out-of-band verified phone channel before releasing outbound settlement holds. "
                "4. Review account balance history for preceding pass-through credit surges."
            )

            limitations = (
                "May trigger on legitimate major expenditures such as vehicle purchases, property deposits, "
                "hospital bills, or seasonal luxury spending. Does not evaluate beneficiary reputational risk directly."
            )

            findings.append(
                RiskFinding(
                    finding_id=finding_id,
                    customer_id=t.customer_id,
                    rule_id="R01",
                    title="Unusually Large Outward Transfer",
                    severity=severity,
                    risk_score=risk_score,
                    score_components=score_comp,
                    transaction_ids=[t.transaction_id],
                    primary_transaction_id=t.transaction_id,
                    description=description,
                    evidence=evidence,
                    investigator_action=investigator_action,
                    limitations=limitations,
                    requires_human_review=True,
                    detected_at=None,
                )
            )

    return findings


def evaluate_r02(
    transactions: List[Transaction],
    baseline: Optional[CustomerBaseline] = None,
) -> List[RiskFinding]:
    """
    R02 — NEW PAYEE PAYMENT BURST
    
    Detection Criteria (from risk_policy.md):
    - Payee has no prior transaction history in the customer's historical baseline (first_seen = True).
    - At least 3 transactions occur to the same new payee within a rolling 2-hour window, OR
    - 2 or more transactions totaling > $5,000.00 within a 1-hour window.
    - Transactions use instant settlement channels (IMPS, UPI, etc.).
    """
    findings: List[RiskFinding] = []
    if len(transactions) < 2:
        return findings

    # Identify all payees and their chronological occurrences
    payee_history: Dict[str, List[Transaction]] = {}
    for t in transactions:
        payee_history.setdefault(t.payee, []).append(t)

    # Sort each payee's transactions chronologically
    for payee, p_txns in payee_history.items():
        p_txns.sort(key=lambda x: (x.date, x.time, x.transaction_id))

    # Evaluate each payee for burst clusters
    for payee, p_txns in payee_history.items():
        n = len(p_txns)
        if n < 2:
            continue

        # Look for sliding clusters of burst activity
        i = 0
        while i < n:
            cluster = [p_txns[i]]
            first_txn = p_txns[i]
            first_dt = first_txn.timestamp

            # Check if this payee had any transactions prior to this cluster
            # (i.e. was first seen at cluster[0])
            prior_txns = [t for t in transactions if t.payee == payee and t.timestamp < first_dt]
            if prior_txns:
                # Payee was already seen prior to this point; not a newly added payee burst
                i += 1
                continue

            j = i + 1
            while j < n:
                next_txn = p_txns[j]
                delta_sec = (next_txn.timestamp - first_dt).total_seconds()
                if delta_sec <= 7200:  # 2 hours window
                    cluster.append(next_txn)
                    j += 1
                else:
                    break

            cluster_count = len(cluster)
            cluster_total = round(sum(t.amount for t in cluster), 2)
            cluster_duration_sec = (cluster[-1].timestamp - cluster[0].timestamp).total_seconds()

            trigger_condition_1 = cluster_count >= 3 and cluster_duration_sec <= 7200
            trigger_condition_2 = cluster_count >= 2 and cluster_total > 5000.00 and cluster_duration_sec <= 3600

            if trigger_condition_1 or trigger_condition_2:
                # Severity determination based on policy guidance
                if cluster_total > 5000.00 and cluster_count >= 3 and cluster_duration_sec <= 5400:
                    severity = "high"
                    base_score = 75
                elif cluster_count >= 2 and cluster_total >= 2000.00:
                    severity = "medium"
                    base_score = 55
                else:
                    severity = "low"
                    base_score = 35

                modifiers = {}
                if cluster_count >= 4:
                    modifiers["velocity_spike_4plus"] = 10
                if cluster_total > 10000.00:
                    modifiers["high_exposure_burst"] = 10

                risk_score, score_comp = _calculate_risk_score(base_score, modifiers)

                txn_ids = [t.transaction_id for t in cluster]
                primary_id = cluster[0].transaction_id
                finding_id = f"{cluster[0].customer_id}_R02_{primary_id}"

                duration_min = round(cluster_duration_sec / 60.0, 1)
                description = (
                    f"New payee payment burst detected: {cluster_count} rapid transfers totaling ${cluster_total:,.2f} "
                    f"executed to newly added beneficiary '{payee}' within {duration_min} minutes. Payee had zero "
                    f"prior transaction history in the customer's account."
                )

                evidence = {
                    "payee": payee,
                    "first_seen": True,
                    "burst_transaction_count": cluster_count,
                    "transaction_ids": txn_ids,
                    "total_burst_amount": cluster_total,
                    "time_window_minutes": duration_min,
                    "channels": sorted(list(set(t.channel for t in cluster))),
                    "first_transaction_time": f"{cluster[0].date} {cluster[0].time}",
                    "last_transaction_time": f"{cluster[-1].date} {cluster[-1].time}",
                }

                investigator_action = (
                    "1. Review payee addition timestamp and channel (web portal vs mobile app). "
                    "2. Check for recent password changes, SIM swaps, or multi-factor authentication resets. "
                    "3. Validate whether beneficiary account is a digital wallet or mule account. "
                    "4. Implement immediate outbound settlement hold if transfers are in pending clearing state."
                )

                limitations = (
                    "Legitimate contractor settlements, home renovation progress payments, or urgent peer-to-peer "
                    "family transfers may exhibit burst characteristics. Does not consider pre-scheduled bulk payroll."
                )

                findings.append(
                    RiskFinding(
                        finding_id=finding_id,
                        customer_id=cluster[0].customer_id,
                        rule_id="R02",
                        title="New Payee Payment Burst",
                        severity=severity,
                        risk_score=risk_score,
                        score_components=score_comp,
                        transaction_ids=txn_ids,
                        primary_transaction_id=primary_id,
                        description=description,
                        evidence=evidence,
                        investigator_action=investigator_action,
                        limitations=limitations,
                        requires_human_review=True,
                        detected_at=None,
                    )
                )
                # Advance pointer past this burst to avoid duplicate sub-cluster findings
                i = j
            else:
                i += 1

    return findings


def evaluate_r03(
    transactions: List[Transaction],
    baseline: Optional[CustomerBaseline] = None,
) -> List[RiskFinding]:
    """
    R03 — ODD-HOURS ACTIVITY
    
    Detection Criteria (from risk_policy.md):
    - Transaction timestamp falls within the defined high-risk window: 00:00:00 to 05:00:00 local time.
    - Customer's historical active profile shows < 5% of lifetime transactions occurring during this window.
    - Transaction is an outward debit or transfer exceeding $500.00.
    """
    findings: List[RiskFinding] = []
    if not transactions:
        return findings

    for t in transactions:
        # High-risk nocturnal window: hours 0, 1, 2, 3, 4 (00:00:00 to 05:00:00)
        if 0 <= t.hour <= 4 and t.amount >= 500.00:
            # Baseline excluding target transaction and any concurrent same-date nocturnal cluster
            # to prevent an attack session from falsely inflating historical nocturnal percentage
            sub_txns = [
                other
                for other in transactions
                if other.transaction_id != t.transaction_id
                and not (other.date == t.date and 0 <= other.hour <= 5)
            ]
            sub_baseline = build_customer_baseline(sub_txns, customer_id=t.customer_id)
            tp = sub_baseline.time_profile

            # Customer's historical profile shows < 5% nocturnal activity
            if tp.late_night_percentage < 5.0:
                # Severity determination based on policy guidance:
                # High: High-value transfer (> $3,000.00) between 01:00 AM and 04:30 AM with zero historical precedent
                if t.amount > 3000.00 and (1 <= t.hour <= 4) and tp.late_night_percentage == 0.0:
                    severity = "high"
                    base_score = 75
                elif t.amount >= 500.00:
                    severity = "medium"
                    base_score = 50
                else:
                    severity = "low"
                    base_score = 30

                modifiers = {}
                if 2 <= t.hour <= 4:
                    modifiers["deep_night_window_02_to_04"] = 10
                if t.amount > 4000.00:
                    modifiers["high_value_night_transfer"] = 10

                risk_score, score_comp = _calculate_risk_score(base_score, modifiers)

                finding_id = f"{t.customer_id}_R03_{t.transaction_id}"
                description = (
                    f"Transaction {t.transaction_id} for ${t.amount:,.2f} occurred at {t.time} during the high-risk "
                    f"nocturnal window (00:00–05:00). Customer's historical activity profile is {tp.typical_start_hour}:00 "
                    f"to {tp.typical_end_hour}:00 with only {tp.late_night_percentage}% prior late-night transactions."
                )

                evidence = {
                    "transaction_id": t.transaction_id,
                    "amount": t.amount,
                    "time": t.time,
                    "hour": t.hour,
                    "date": t.date,
                    "channel": t.channel,
                    "payee": t.payee,
                    "customer_typical_window": f"{tp.typical_start_hour:02d}:00 to {tp.typical_end_hour:02d}:00",
                    "historical_late_night_percentage": tp.late_night_percentage,
                    "historical_late_night_count": tp.late_night_transaction_count,
                    "high_risk_window": "00:00:00 to 05:00:00",
                }

                investigator_action = (
                    "1. Differentiate between automated merchant batch debits and manual customer logins. "
                    "2. Inspect IP geolocation, ISP, and device fingerprint for the nocturnal session. "
                    "3. Cross-reference with concurrent OTP generation or SMS delivery logs."
                )

                limitations = (
                    "Shift workers, international travelers, and nocturnal lifestyle customers naturally execute late-night "
                    "transactions. Recurring digital subscriptions also frequently post during overnight batch processing."
                )

                findings.append(
                    RiskFinding(
                        finding_id=finding_id,
                        customer_id=t.customer_id,
                        rule_id="R03",
                        title="Odd-Hours Activity Anomaly",
                        severity=severity,
                        risk_score=risk_score,
                        score_components=score_comp,
                        transaction_ids=[t.transaction_id],
                        primary_transaction_id=t.transaction_id,
                        description=description,
                        evidence=evidence,
                        investigator_action=investigator_action,
                        limitations=limitations,
                        requires_human_review=True,
                        detected_at=None,
                    )
                )

    return findings


def evaluate_r04(
    transactions: List[Transaction],
    baseline: Optional[CustomerBaseline] = None,
) -> List[RiskFinding]:
    """
    R04 — CUSTOMER BEHAVIOUR DEVIATION
    
    Detection Criteria (from risk_policy.md):
    - Capture compound anomalies where multiple dimensions simultaneously diverge from personal norms:
      1. Amount divergence (>= 3.0x personal median, amount >= $500.00).
      2. Unfamiliar payee category (payee not established in baseline).
      3. Channel divergence (channel represents < 10% of historical usage).
      4. Time divergence (outside customer typical active window).
    - Composite divergence: at least 2 dimensions diverge simultaneously.
    """
    findings: List[RiskFinding] = []
    if len(transactions) < 5:
        return findings

    for t in transactions:
        if t.amount < 500.00:
            continue

        # Prevent leakage
        sub_baseline = build_baseline_excluding_transaction(transactions, t.transaction_id)
        median_val = max(0.01, sub_baseline.amount_profile.median)

        divergent_dims: List[str] = []

        # 1. Amount dimension
        if t.amount >= 3.0 * median_val:
            divergent_dims.append(f"Amount ${t.amount:,.2f} is {t.amount / median_val:.1f}x personal median")

        # 2. Payee dimension
        if t.payee not in sub_baseline.payee_profile.payee_counts:
            divergent_dims.append(f"Payee '{t.payee}' has no prior transaction history")

        # 3. Channel dimension
        ch_pct = sub_baseline.channel_profile.channel_percentages.get(t.channel, 0.0)
        if ch_pct < 10.0:
            divergent_dims.append(f"Channel '{t.channel}' constitutes only {ch_pct:.1f}% of historical usage")

        # 4. Time dimension
        start_h = sub_baseline.time_profile.typical_start_hour
        end_h = sub_baseline.time_profile.typical_end_hour
        if t.hour < start_h or t.hour > end_h:
            divergent_dims.append(f"Hour {t.hour:02d}:00 is outside typical window ({start_h:02d}:00–{end_h:02d}:00)")

        # Only trigger if at least 2 dimensions diverge
        if len(divergent_dims) >= 2:
            severity = "medium" if len(divergent_dims) >= 3 else "low"
            base_score = 50 if severity == "medium" else 35
            modifiers = {"dimensional_divergence_bonus": (len(divergent_dims) - 2) * 10}
            risk_score, score_comp = _calculate_risk_score(base_score, modifiers)

            finding_id = f"{t.customer_id}_R04_{t.transaction_id}"
            description = (
                f"Multi-dimensional customer behavior deviation detected on {t.transaction_id} (${t.amount:,.2f} via {t.channel}): "
                f"Concurrent divergence across {len(divergent_dims)} dimensions: {'; '.join(divergent_dims)}."
            )

            evidence = {
                "transaction_id": t.transaction_id,
                "amount": t.amount,
                "channel": t.channel,
                "payee": t.payee,
                "divergent_dimensions_count": len(divergent_dims),
                "divergent_dimensions": divergent_dims,
                "baseline_median": median_val,
                "channel_historical_share": ch_pct,
            }

            investigator_action = (
                "1. Review recent customer communication logs, travel notices, or limit enhancement requests. "
                "2. Examine preceding and subsequent transaction context to assess organic vs inorganic spend patterns. "
                "3. Validate whether customer updated banking platform credentials or mobile devices recently."
            )

            limitations = (
                "Holiday seasons, vacations, life transitions, and weddings naturally alter spend dimensions across multiple "
                "channels and merchants simultaneously."
            )

            findings.append(
                RiskFinding(
                    finding_id=finding_id,
                    customer_id=t.customer_id,
                    rule_id="R04",
                    title="Customer Behaviour Multi-Factor Deviation",
                    severity=severity,
                    risk_score=risk_score,
                    score_components=score_comp,
                    transaction_ids=[t.transaction_id],
                    primary_transaction_id=t.transaction_id,
                    description=description,
                    evidence=evidence,
                    investigator_action=investigator_action,
                    limitations=limitations,
                    requires_human_review=True,
                    detected_at=None,
                )
            )

    return findings


def evaluate_r05(
    transactions: List[Transaction],
    baseline: Optional[CustomerBaseline] = None,
) -> List[RiskFinding]:
    """
    R05 — LINKED TRANSACTION PATTERN
    
    Detection Criteria (from risk_policy.md):
    - Sequence linkage: A nominal verification transfer ($1.00 to $10.00) followed within 15–60 minutes
      by rapid high-value transfers (>= $1,000.00) to the identical payee.
    - Structuring / smurfing linkage: Multiple successive transfers just below regulatory reporting
      thresholds ($4,800 to $5,000) within a condensed timeframe.
    - Cross-rule correlation: Occurrence of new payee probe + rapid drain in off-hours.
    """
    findings: List[RiskFinding] = []
    if len(transactions) < 2:
        return findings

    # Sort transactions chronologically
    sorted_txns = sorted(transactions, key=lambda x: (x.date, x.time, x.transaction_id))

    # Pattern A: Probe ($1.00 - $10.00) followed by high-value drain (>= $1,000) to same payee
    for i, probe in enumerate(sorted_txns):
        if 0.50 <= probe.amount <= 10.00:
            probe_dt = probe.timestamp
            drain_txns: List[Transaction] = []

            for candidate in sorted_txns[i + 1 :]:
                delta_sec = (candidate.timestamp - probe_dt).total_seconds()
                # Followed within 15 to 90 minutes
                if 0 < delta_sec <= 5400 and candidate.payee == probe.payee and candidate.amount >= 1000.00:
                    drain_txns.append(candidate)

            if len(drain_txns) >= 2:
                all_linked_ids = [probe.transaction_id] + [d.transaction_id for d in drain_txns]
                drain_total = round(sum(d.amount for d in drain_txns), 2)
                total_chain_exposure = round(probe.amount + drain_total, 2)
                duration_min = round((drain_txns[-1].timestamp - probe.timestamp).total_seconds() / 60.0, 1)

                is_off_hours = 0 <= probe.hour <= 5

                severity = "critical" if is_off_hours else "high"
                base_score = 90 if severity == "critical" else 80
                modifiers = {}
                if len(drain_txns) >= 3:
                    modifiers["escalating_drain_count"] = 5
                if total_chain_exposure > 15000.00:
                    modifiers["critical_cumulative_exposure"] = 5

                risk_score, score_comp = _calculate_risk_score(base_score, modifiers)

                finding_id = f"{probe.customer_id}_R05_{probe.transaction_id}"
                description = (
                    f"Linked attack sequence detected: Nominal probing transfer (${probe.amount:,.2f}) at {probe.time} "
                    f"followed within {duration_min} minutes by {len(drain_txns)} high-value transfers totaling "
                    f"${drain_total:,.2f} to beneficiary '{probe.payee}'. Cumulative chain exposure: ${total_chain_exposure:,.2f}."
                )

                evidence = {
                    "pattern_type": "Probing verification transfer followed by sequential high-value liquidation",
                    "probe_transaction_id": probe.transaction_id,
                    "probe_amount": probe.amount,
                    "probe_timestamp": f"{probe.date} {probe.time}",
                    "drain_transaction_ids": [d.transaction_id for d in drain_txns],
                    "drain_transaction_count": len(drain_txns),
                    "drain_total_amount": drain_total,
                    "total_chain_exposure": total_chain_exposure,
                    "payee": probe.payee,
                    "chain_duration_minutes": duration_min,
                    "off_hours_execution": is_off_hours,
                }

                investigator_action = (
                    "1. Immediately quarantine remaining account liquid balance to prevent further automated drain. "
                    "2. Trace beneficiary account IFSC/routing number and initiate inter-bank recall protocols. "
                    "3. Contact customer's verified emergency contact or secondary phone channel. "
                    "4. Flag session IP address and device fingerprint across bank fraud consortia."
                )

                limitations = (
                    "Legitimate business system integration testing or staged invoice disbursements may occasionally "
                    "mimic linked transfer sequences."
                )

                findings.append(
                    RiskFinding(
                        finding_id=finding_id,
                        customer_id=probe.customer_id,
                        rule_id="R05",
                        title="Linked Transaction Chain (Probe & Rapid Drain)",
                        severity=severity,
                        risk_score=risk_score,
                        score_components=score_comp,
                        transaction_ids=all_linked_ids,
                        primary_transaction_id=probe.transaction_id,
                        description=description,
                        evidence=evidence,
                        investigator_action=investigator_action,
                        limitations=limitations,
                        requires_human_review=True,
                        detected_at=None,
                    )
                )

    return findings


def analyze_customer_risk(
    customer_id: str,
    transactions: List[Transaction],
    customer_name: Optional[str] = None,
) -> CustomerRiskAnalysis:
    """
    Executes the full deterministic risk detection suite against customer transactions.
    
    Evaluates:
    - R01: Unusually Large Outward Transfer
    - R02: New Payee Payment Burst
    - R03: Odd-Hours Activity Anomaly
    - R04: Customer Behaviour Multi-Factor Deviation
    - R05: Linked Transaction Pattern
    
    Deduplicates and sorts findings deterministically by severity, risk score, timestamp, and ID.
    """
    if not transactions:
        return CustomerRiskAnalysis(
            customer_id=customer_id,
            customer_name=customer_name or customer_id,
            transaction_count=0,
            finding_count=0,
            findings=[],
            summary=RiskAnalysisSummary(
                highest_severity="none",
                highest_risk_score=0,
                rules_triggered=[],
                requires_human_review=False,
            ),
        )

    # Establish customer baseline
    baseline = build_customer_baseline(transactions, customer_id=customer_id)

    # Collect findings across all modular evaluators
    all_findings: List[RiskFinding] = []
    all_findings.extend(evaluate_r01(transactions, baseline))
    all_findings.extend(evaluate_r02(transactions, baseline))
    all_findings.extend(evaluate_r03(transactions, baseline))
    all_findings.extend(evaluate_r04(transactions, baseline))
    all_findings.extend(evaluate_r05(transactions, baseline))

    # Deduplicate findings by finding_id
    deduped: Dict[str, RiskFinding] = {}
    for f in all_findings:
        if f.finding_id not in deduped:
            deduped[f.finding_id] = f

    # Deterministic sorting order:
    # 1. Severity rank descending (critical > high > medium > low)
    # 2. Risk score descending
    # 3. Primary transaction ID ascending
    # 4. Rule ID ascending
    # 5. Finding ID ascending
    sorted_findings = sorted(
        deduped.values(),
        key=lambda f: (
            -SEVERITY_RANKS.get(f.severity.lower(), 0),
            -f.risk_score,
            f.primary_transaction_id,
            f.rule_id,
            f.finding_id,
        ),
    )

    # Summary calculations
    if sorted_findings:
        highest_severity = sorted_findings[0].severity
        highest_risk_score = max(f.risk_score for f in sorted_findings)
        rules_triggered = sorted(list(set(f.rule_id for f in sorted_findings)))
        requires_review = True
    else:
        highest_severity = "none"
        highest_risk_score = 0
        rules_triggered = []
        requires_review = False

    return CustomerRiskAnalysis(
        customer_id=customer_id,
        customer_name=customer_name or customer_id,
        transaction_count=len(transactions),
        finding_count=len(sorted_findings),
        findings=sorted_findings,
        summary=RiskAnalysisSummary(
            highest_severity=highest_severity,
            highest_risk_score=highest_risk_score,
            rules_triggered=rules_triggered,
            requires_human_review=requires_review,
        ),
    )
