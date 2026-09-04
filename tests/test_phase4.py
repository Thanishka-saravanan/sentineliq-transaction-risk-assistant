import unittest
from fastapi.testclient import TestClient
from app import app
from src.data_loader import (
    load_all_customers,
    load_transactions_for_customer,
)
from src.models import Transaction
from src.risk_engine import (
    analyze_customer_risk,
    evaluate_r01,
    evaluate_r02,
    evaluate_r03,
    evaluate_r04,
    evaluate_r05,
)


class TestPhase4(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.customers = load_all_customers()

    def test_evaluators_callable_and_deterministic(self):
        txns = load_transactions_for_customer("CUST002")
        f1 = evaluate_r01(txns)
        f2 = evaluate_r01(txns)
        self.assertEqual(len(f1), len(f2))
        self.assertEqual([f.finding_id for f in f1], [f.finding_id for f in f2])
        self.assertEqual([f.risk_score for f in f1], [f.risk_score for f in f2])

    def test_evaluators_independently_testable(self):
        dummy_txns = [
            Transaction(
                transaction_id="TXN_TEST1",
                customer_id="CUST_TEST",
                date="2024-01-01",
                time="10:00:00",
                description="Test txn 1",
                payee="Shop A",
                amount=50.00,
                channel="UPI",
            ),
            Transaction(
                transaction_id="TXN_TEST2",
                customer_id="CUST_TEST",
                date="2024-01-02",
                time="11:00:00",
                description="Test txn 2",
                payee="Shop B",
                amount=60.00,
                channel="UPI",
            ),
            Transaction(
                transaction_id="TXN_TEST3",
                customer_id="CUST_TEST",
                date="2024-01-03",
                time="12:00:00",
                description="Test txn 3",
                payee="Shop C",
                amount=55.00,
                channel="UPI",
            ),
            Transaction(
                transaction_id="TXN_TEST4",
                customer_id="CUST_TEST",
                date="2024-01-04",
                time="13:00:00",
                description="Test txn 4",
                payee="Shop D",
                amount=70.00,
                channel="UPI",
            ),
        ]
        # Independent calls should not raise exceptions
        res_r01 = evaluate_r01(dummy_txns)
        res_r02 = evaluate_r02(dummy_txns)
        res_r03 = evaluate_r03(dummy_txns)
        res_r04 = evaluate_r04(dummy_txns)
        res_r05 = evaluate_r05(dummy_txns)

        self.assertIsInstance(res_r01, list)
        self.assertIsInstance(res_r02, list)
        self.assertIsInstance(res_r03, list)
        self.assertIsInstance(res_r04, list)
        self.assertIsInstance(res_r05, list)

    def test_reproducibility_same_input_same_findings(self):
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            run1 = analyze_customer_risk(c.customer_id, txns)
            run2 = analyze_customer_risk(c.customer_id, txns)

            self.assertEqual(run1.finding_count, run2.finding_count)
            self.assertEqual(run1.summary.highest_severity, run2.summary.highest_severity)
            self.assertEqual(run1.summary.highest_risk_score, run2.summary.highest_risk_score)
            self.assertEqual(
                [f.finding_id for f in run1.findings],
                [f.finding_id for f in run2.findings],
            )

    def test_risk_scores_bounded_0_to_100(self):
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            analysis = analyze_customer_risk(c.customer_id, txns)
            for f in analysis.findings:
                self.assertGreaterEqual(f.risk_score, 0)
                self.assertLessEqual(f.risk_score, 100)
                self.assertIn("final_score", f.score_components)
                self.assertEqual(f.risk_score, f.score_components["final_score"])

    def test_finding_ids_deterministic_and_unique(self):
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            analysis = analyze_customer_risk(c.customer_id, txns)
            seen_ids = set()
            for f in analysis.findings:
                self.assertNotIn(f.finding_id, seen_ids)
                seen_ids.add(f.finding_id)
                self.assertTrue(f.finding_id.startswith(f"{c.customer_id}_"))

    def test_every_finding_has_required_policy_fields(self):
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            analysis = analyze_customer_risk(c.customer_id, txns)
            for f in analysis.findings:
                self.assertTrue(f.rule_id in {"R01", "R02", "R03", "R04", "R05"})
                self.assertIsInstance(f.evidence, dict)
                self.assertGreater(len(f.evidence), 0)
                self.assertIn(f.severity.lower(), {"low", "medium", "high", "critical"})
                self.assertTrue(bool(f.investigator_action.strip()))
                self.assertTrue(bool(f.limitations.strip()))
                self.assertTrue(f.requires_human_review is True)
                self.assertIsNone(f.detected_at, "detected_at must be null for determinism")

    def test_target_transaction_does_not_distort_own_baseline(self):
        txns = load_transactions_for_customer("CUST002")
        findings = evaluate_r01(txns)
        self.assertGreater(len(findings), 0)
        large_f = findings[0]
        # In evidence, the customer_median_amount must be the median of the OTHER transactions
        # which is ~$42, NOT skewed by the $24,500 transfer
        self.assertLess(large_f.evidence["customer_median_amount"], 100.0)

    def test_duplicate_findings_not_produced(self):
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            analysis = analyze_customer_risk(c.customer_id, txns)
            finding_ids = [f.finding_id for f in analysis.findings]
            self.assertEqual(len(finding_ids), len(set(finding_ids)))

    def test_findings_sorted_deterministically(self):
        severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            analysis = analyze_customer_risk(c.customer_id, txns)
            findings = analysis.findings
            for i in range(len(findings) - 1):
                f1 = findings[i]
                f2 = findings[i + 1]
                s1 = severity_rank.get(f1.severity.lower(), 0)
                s2 = severity_rank.get(f2.severity.lower(), 0)
                # Primary sort: severity rank desc
                if s1 != s2:
                    self.assertGreater(s1, s2)
                else:
                    # Secondary sort: risk score desc
                    self.assertGreaterEqual(f1.risk_score, f2.risk_score)

    def test_empty_input_handled_safely(self):
        analysis = analyze_customer_risk("CUST_EMPTY", [])
        self.assertEqual(analysis.transaction_count, 0)
        self.assertEqual(analysis.finding_count, 0)
        self.assertEqual(analysis.findings, [])
        self.assertEqual(analysis.summary.highest_severity, "none")
        self.assertEqual(analysis.summary.highest_risk_score, 0)
        self.assertFalse(analysis.summary.requires_human_review)

    def test_normal_customer_generates_zero_findings(self):
        txns = load_transactions_for_customer("CUST001")
        analysis = analyze_customer_risk("CUST001", txns)
        self.assertEqual(analysis.finding_count, 0)
        self.assertEqual(analysis.findings, [])
        self.assertEqual(analysis.summary.highest_severity, "none")
        self.assertFalse(analysis.summary.requires_human_review)

    def test_borderline_customer_handled_by_policy_criteria(self):
        txns = load_transactions_for_customer("CUST006")
        analysis = analyze_customer_risk("CUST006", txns)
        # CUST006 has a single $3,200 transaction to known merchant Tanishq Jewellers
        # Triggers R01 under policy mathematical thresholds, but NOT R02, R03, or R05
        rules = analysis.summary.rules_triggered
        self.assertIn("R01", rules)
        self.assertNotIn("R02", rules)
        self.assertNotIn("R03", rules)
        self.assertNotIn("R05", rules)

    def test_known_scenarios_triggered(self):
        # CUST002 -> R01
        a2 = analyze_customer_risk("CUST002", load_transactions_for_customer("CUST002"))
        self.assertIn("R01", a2.summary.rules_triggered)

        # CUST003 -> R02
        a3 = analyze_customer_risk("CUST003", load_transactions_for_customer("CUST003"))
        self.assertIn("R02", a3.summary.rules_triggered)

        # CUST004 -> R03
        a4 = analyze_customer_risk("CUST004", load_transactions_for_customer("CUST004"))
        self.assertIn("R03", a4.summary.rules_triggered)

        # CUST005 -> R05
        a5 = analyze_customer_risk("CUST005", load_transactions_for_customer("CUST005"))
        self.assertIn("R05", a5.summary.rules_triggered)

    def test_api_risk_analysis_endpoint_200(self):
        response = self.client.get("/api/customers/CUST002/risk-analysis")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["customer_id"], "CUST002")
        self.assertGreater(data["finding_count"], 0)
        self.assertIn("R01", data["summary"]["rules_triggered"])
        self.assertTrue(data["summary"]["requires_human_review"])
        self.assertIn("The system identifies activity requiring human review", data["disclaimer"])

    def test_api_findings_endpoint_200(self):
        response = self.client.get("/api/customers/CUST002/findings")
        self.assertEqual(response.status_code, 200)
        findings = response.json()
        self.assertIsInstance(findings, list)
        self.assertGreater(len(findings), 0)
        first = findings[0]
        self.assertTrue(first["finding_id"].startswith("CUST002_"))

    def test_api_single_finding_endpoint_200(self):
        resp = self.client.get("/api/customers/CUST002/findings")
        findings = resp.json()
        target_finding = findings[0]
        fid = target_finding["finding_id"]

        single_resp = self.client.get(f"/api/customers/CUST002/findings/{fid}")
        self.assertEqual(single_resp.status_code, 200)
        self.assertEqual(single_resp.json()["finding_id"], fid)

    def test_api_invalid_customer_risk_analysis_returns_404(self):
        response = self.client.get("/api/customers/INVALID999/risk-analysis")
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())

    def test_api_invalid_customer_findings_returns_404(self):
        response = self.client.get("/api/customers/INVALID999/findings")
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
