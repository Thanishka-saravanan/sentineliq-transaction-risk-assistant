from typing import List, Set

from src.baseline import build_baseline_summary, build_customer_baseline
from src.data_loader import (
    load_customer_by_id,
    load_risk_rules,
    load_transactions_for_customer,
)
from src.models import (
    Customer,
    CustomerBaselineSummary,
    GroundingContext,
    RiskFinding,
    RiskRuleDefinition,
    Transaction,
)
from src.risk_engine import analyze_customer_risk


def build_grounding_context(customer_id: str) -> GroundingContext:
    """
    Constructs the verified grounding context payload for a customer.
    
    Contains only verified project data:
    1. Customer Profile
    2. Behavioral Baseline Summary
    3. Deterministic Policy Findings
    4. Relevant Policy Rules (filtered strictly to triggered rules)
    5. Directly Involved Transactions (filtered strictly to transactions in findings)
    6. Regulatory Disclaimers
    """
    customer: Customer = load_customer_by_id(customer_id)
    if not customer:
        raise ValueError(f"Customer '{customer_id}' not found.")

    transactions: List[Transaction] = load_transactions_for_customer(customer_id)

    # Calculate baseline and summary
    baseline = build_customer_baseline(transactions, customer_id=customer_id)
    baseline_summary: CustomerBaselineSummary = build_baseline_summary(baseline)

    # Run deterministic risk evaluation
    analysis = analyze_customer_risk(
        customer_id=customer_id,
        transactions=transactions,
        customer_name=customer.name,
    )

    findings: List[RiskFinding] = analysis.findings
    triggered_rules: Set[str] = set(analysis.summary.rules_triggered)

    # Filter policy rules strictly to those triggered
    all_rules: List[RiskRuleDefinition] = load_risk_rules()
    relevant_rules: List[RiskRuleDefinition] = [r for r in all_rules if r.rule_id in triggered_rules]

    # Collect transaction IDs involved in findings
    involved_txn_ids: Set[str] = set()
    for f in findings:
        involved_txn_ids.update(f.transaction_ids)

    # Filter transactions strictly to involved transactions
    relevant_transactions: List[Transaction] = [
        t for t in transactions if t.transaction_id in involved_txn_ids
    ]

    # Deterministic explanatory notes
    if findings:
        rules_list_str = ", ".join(sorted(triggered_rules))
        notes = (
            f"Deterministic policy rules triggered: [{rules_list_str}]. "
            f"Total findings: {len(findings)}. Highest severity: {analysis.summary.highest_severity.upper()}. "
            f"All findings represent indicators for human fraud analyst review."
        )
    else:
        notes = (
            "No deterministic policy findings were generated for this customer. "
            "The customer's transaction history conforms to their routine baseline. "
            "Expected status: NO ATTENTION REQUIRED."
        )

    return GroundingContext(
        customer=customer,
        baseline_summary=baseline_summary,
        deterministic_findings=findings,
        relevant_policy_rules=relevant_rules,
        relevant_transactions=relevant_transactions,
        disclaimer=(
            "The system identifies activity requiring human review. A risk finding does not establish that fraud has occurred."
        ),
        notes=notes,
    )
