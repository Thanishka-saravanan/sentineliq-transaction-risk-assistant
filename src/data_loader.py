import csv
import json
import os
import re
from typing import Dict, List, Optional
from src.models import Customer, RiskRuleDefinition, Transaction

# Base paths relative to this file
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CUSTOMERS_FILE = os.path.join(DATA_DIR, "customers", "customers.json")
TRANSACTIONS_FILE = os.path.join(DATA_DIR, "transactions", "transactions.csv")
RISK_POLICY_FILE = os.path.join(DATA_DIR, "rules", "risk_policy.md")


def get_customers_file_path() -> str:
    return CUSTOMERS_FILE


def get_transactions_file_path() -> str:
    return TRANSACTIONS_FILE


def get_risk_policy_file_path() -> str:
    return RISK_POLICY_FILE


def load_all_customers() -> List[Customer]:
    """Loads all synthetic customer profiles from customers.json."""
    if not os.path.exists(CUSTOMERS_FILE):
        raise FileNotFoundError(f"Customers file not found at: {CUSTOMERS_FILE}")

    with open(CUSTOMERS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    customers = [Customer(**item) for item in data]
    return customers


def load_customer_by_id(customer_id: str) -> Optional[Customer]:
    """Retrieves a single customer by customer_id (e.g. CUST001)."""
    clean_id = customer_id.strip().upper()
    for customer in load_all_customers():
        if customer.customer_id.upper() == clean_id:
            return customer
    return None


def load_all_transactions() -> List[Transaction]:
    """Loads all transactions from transactions.csv and validates them."""
    if not os.path.exists(TRANSACTIONS_FILE):
        raise FileNotFoundError(f"Transactions file not found at: {TRANSACTIONS_FILE}")

    transactions: List[Transaction] = []
    seen_ids = set()

    with open(TRANSACTIONS_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            txn = Transaction(
                transaction_id=row["transaction_id"].strip(),
                customer_id=row["customer_id"].strip(),
                date=row["date"].strip(),
                time=row["time"].strip(),
                description=row["description"].strip(),
                payee=row["payee"].strip(),
                amount=float(row["amount"].strip()),
                channel=row["channel"].strip(),
            )
            if txn.transaction_id in seen_ids:
                raise ValueError(f"Duplicate transaction ID detected: {txn.transaction_id}")
            seen_ids.add(txn.transaction_id)
            transactions.append(txn)

    return sort_transactions_chronologically(transactions)


def sort_transactions_chronologically(transactions: List[Transaction]) -> List[Transaction]:
    """Sorts transactions chronologically by (date, time, transaction_id)."""
    return sorted(transactions, key=lambda t: (t.date, t.time, t.transaction_id))


def load_transactions_for_customer(customer_id: str) -> List[Transaction]:
    """Loads and returns all transactions for a specific customer, sorted chronologically."""
    clean_id = customer_id.strip().upper()
    all_txns = load_all_transactions()
    customer_txns = [t for t in all_txns if t.customer_id.upper() == clean_id]
    return sort_transactions_chronologically(customer_txns)


def validate_transactions(transactions: List[Transaction]) -> bool:
    """Validates uniqueness of transaction IDs and basic integrity."""
    seen = set()
    for t in transactions:
        if t.transaction_id in seen:
            raise ValueError(f"Duplicate transaction ID found: {t.transaction_id}")
        seen.add(t.transaction_id)
        if t.amount <= 0:
            raise ValueError(f"Non-positive amount for {t.transaction_id}: {t.amount}")
    return True


def load_risk_policy_text() -> str:
    """Loads the raw risk policy markdown document."""
    if not os.path.exists(RISK_POLICY_FILE):
        raise FileNotFoundError(f"Risk policy document not found at: {RISK_POLICY_FILE}")

    with open(RISK_POLICY_FILE, "r", encoding="utf-8") as f:
        return f.read()


def load_risk_rules() -> List[RiskRuleDefinition]:
    """Parses individual rule definitions (R01 through R05) from the risk policy document."""
    content = load_risk_policy_text()
    rules: List[RiskRuleDefinition] = []

    # Regex pattern to capture Rule R01 through R05 blocks
    pattern = r"### Rule (R0[1-5]) — (.*?)\n(.*?)(?=\n### Rule R0|\n## Conclusion|\Z)"
    matches = re.findall(pattern, content, re.DOTALL)

    for rule_id, title, block in matches:
        title = title.strip()

        # Helper to extract bullet fields
        def extract_field(field_name: str) -> str:
            m = re.search(rf"- \*\*{field_name}\*\*:(.*?)(?=\n- \*\*|\n\n|\Z)", block, re.DOTALL)
            return m.group(1).strip() if m else ""

        purpose = extract_field("Purpose")
        criteria = extract_field("Detection Criteria")
        severity = extract_field("Severity Guidance")
        action = extract_field("Investigator Action Guidance")
        limitations = extract_field("Limitations")

        # Extract evidence list
        evidence_m = re.search(r"- \*\*Evidence Required\*\*:(.*?)(?=\n- \*\*Severity|\Z)", block, re.DOTALL)
        evidence_lines = []
        if evidence_m:
            for line in evidence_m.group(1).split("\n"):
                line = line.strip()
                if line.startswith("-") or line.startswith("*"):
                    evidence_lines.append(line.lstrip("-* ").strip())

        rules.append(
            RiskRuleDefinition(
                rule_id=rule_id.strip(),
                title=title,
                purpose=purpose,
                detection_criteria=criteria,
                evidence_required=evidence_lines,
                severity_guidance=severity,
                investigator_action=action,
                limitations=limitations,
            )
        )

    # Fallback to predefined structured rules if regex yields fewer than 5
    if len(rules) < 5:
        return _default_rule_definitions()

    return rules


def _default_rule_definitions() -> List[RiskRuleDefinition]:
    """Hardcoded fallback definitions for R01 to R05 to ensure guaranteed availability."""
    return [
        RiskRuleDefinition(
            rule_id="R01",
            title="Unusually Large Transfer",
            purpose="Identify outward fund movements that are materially and statistically disparate from historical spending.",
            detection_criteria="Transaction amount exceeds 5.0x median or 4.0x mean + 2 std dev, and exceeds historical max by > 150%.",
            evidence_required=["transaction_id", "timestamp", "amount", "historical_median", "calculated_deviation"],
            severity_guidance="High if deviation > 15x median or > $15,000; Medium if 5x-15x; Low if borderline.",
            investigator_action="Verify KYC, source of funds, and contact customer via out-of-band phone channel before release.",
            limitations="May trigger on legitimate major purchases (real estate, vehicles, medical, tuition).",
        ),
        RiskRuleDefinition(
            rule_id="R02",
            title="New Payee Payment Burst",
            purpose="Detect account takeover or authorized push payment scams via rapid payments to a newly added payee.",
            detection_criteria="At least 3 payments to newly seen payee within 2 hours or >= 2 payments totaling > $5,000 within 1 hour.",
            evidence_required=["transaction_ids", "payee", "first_seen_status", "burst_count", "total_amount", "time_window"],
            severity_guidance="High if total > $5,000 in 90 mins; Medium if $2,000-$5,000; Low if under $2,000.",
            investigator_action="Inspect payee addition timestamp, credentials change logs, and place temporary settlement hold.",
            limitations="Legitimate contractor settlements or emergency peer payments may mimic burst patterns.",
        ),
        RiskRuleDefinition(
            rule_id="R03",
            title="Odd-Hours Activity",
            purpose="Flag transactions executed during nocturnal windows contradicting the customer's proven schedule.",
            detection_criteria="Transaction between 00:00:00 and 05:00:00 where customer has < 5% historical activity during these hours.",
            evidence_required=["transaction_id", "timestamp", "amount", "customer_active_window", "deviation_ratio"],
            severity_guidance="High if > $3,000 at 01:00-04:30 AM; Medium if $500-$3,000; Low if routine subscription charge.",
            investigator_action="Differentiate automated batch debits vs manual logins; inspect device fingerprint and IP geolocations.",
            limitations="Shift workers and international travelers will naturally display nocturnal transactions.",
        ),
        RiskRuleDefinition(
            rule_id="R04",
            title="Customer Behaviour Deviation",
            purpose="Capture compound anomalies across amount, channel, payee category, and frequency.",
            detection_criteria="Multi-factor score combining amount divergence (3x-5x median), unfamiliar payee, and channel deviation.",
            evidence_required=["transaction_ids", "channel_baseline", "amount_percentiles", "multi_factor_divergence_summary"],
            severity_guidance="Medium for 2-3 dimensional shifts without catastrophic exposure; Low for borderline single-factor shifts.",
            investigator_action="Review customer communication logs and inspect preceding transaction sequence.",
            limitations="Holiday seasons, vacations, and life events naturally alter spending habits.",
        ),
        RiskRuleDefinition(
            rule_id="R05",
            title="Linked Transaction Pattern",
            purpose="Connect separate transactions that form part of a unified multi-stage attack or structuring vector.",
            detection_criteria="Nominal verification transfer ($1.00-$5.00) followed within 60 mins by rapid high-value transfers, or smurfing.",
            evidence_required=["ordered_transaction_ids", "timeline_narrative", "aggregate_monetary_exposure", "common_linkage_threads"],
            severity_guidance="Critical if test probe + off-hours drain; High if structured transfers approaching velocity limits.",
            investigator_action="Immediately quarantine account liquid balance, initiate inter-bank recall, and flag IP/device.",
            limitations="Legitimate split invoice payments or business testing can resemble linked patterns.",
        ),
    ]
