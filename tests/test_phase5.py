import json
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from app import app
from src.genai_service import (
    GeminiNotConfiguredError,
    GeminiServiceError,
    generate_investigation_report,
    validate_and_sanitize_investigation_result,
)
from src.investigation_context import build_grounding_context


class TestPhase5(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_grounding_context_includes_deterministic_findings(self):
        ctx = build_grounding_context("CUST002")
        self.assertEqual(ctx.customer.customer_id, "CUST002")
        self.assertGreater(len(ctx.deterministic_findings), 0)
        finding_rule_ids = {f.rule_id for f in ctx.deterministic_findings}
        self.assertIn("R01", finding_rule_ids)

    def test_context_includes_only_relevant_policy_rules(self):
        ctx = build_grounding_context("CUST002")
        # Triggered rules for CUST002 are R01 and R04
        triggered_rules = {f.rule_id for f in ctx.deterministic_findings}
        policy_rule_ids = {r.rule_id for r in ctx.relevant_policy_rules}
        self.assertEqual(triggered_rules, policy_rule_ids)
        # R02, R03, R05 should NOT be present in CUST002 context
        self.assertNotIn("R02", policy_rule_ids)
        self.assertNotIn("R03", policy_rule_ids)
        self.assertNotIn("R05", policy_rule_ids)

    def test_context_includes_linked_transaction_ids(self):
        ctx = build_grounding_context("CUST005")
        # CUST005 has a linked pattern with TXN0140 to TXN0144
        involved_ids = {t.transaction_id for t in ctx.relevant_transactions}
        for expected_id in ["TXN0140", "TXN0141", "TXN0142", "TXN0143", "TXN0144"]:
            self.assertIn(expected_id, involved_ids)

    def test_context_for_cust001_clearly_states_no_findings(self):
        ctx = build_grounding_context("CUST001")
        self.assertEqual(len(ctx.deterministic_findings), 0)
        self.assertEqual(len(ctx.relevant_transactions), 0)
        self.assertEqual(len(ctx.relevant_policy_rules), 0)
        self.assertIn("no deterministic policy findings", ctx.notes.lower())
        self.assertIn("no attention required", ctx.notes.lower())

    def test_missing_api_key_does_not_crash_app(self):
        # Health check and existing endpoints must work even without an API key
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            resp_health = self.client.get("/api/health")
            self.assertEqual(resp_health.status_code, 200)
            self.assertFalse(resp_health.json()["gemini_api_key_configured"])

            resp_cust = self.client.get("/api/customers/CUST001")
            self.assertEqual(resp_cust.status_code, 200)

            resp_rules = self.client.get("/api/rules")
            self.assertEqual(resp_rules.status_code, 200)

    def test_missing_api_key_investigation_returns_controlled_503(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            response = self.client.get("/api/customers/CUST002/investigation")
            self.assertEqual(response.status_code, 503)
            data = response.json()
            self.assertIn("not configured", data["detail"].lower())

    def test_unknown_customer_returns_404(self):
        response_inv = self.client.get("/api/customers/INVALID999/investigation")
        self.assertEqual(response_inv.status_code, 404)

        response_ctx = self.client.get("/api/customers/INVALID999/investigation/context")
        self.assertEqual(response_ctx.status_code, 404)

    def test_mocked_gemini_valid_structured_response_accepted(self):
        mock_payload = {
            "customer_id": "CUST002",
            "executive_summary": "Suspicious large outward transfer requiring review.",
            "investigation_assessment": {
                "overall_assessment": "Significant high-value deviation from historical spending.",
                "key_concerns": ["Transfer exceeds historical median by >500x"],
                "mitigating_factors": ["No prior nocturnal activity"],
                "confidence": "high",
                "requires_human_review": True,
            },
            "finding_explanations": [
                {
                    "finding_id": "CUST002_R01_TXN0054",
                    "rule_id": "R01",
                    "plain_language_explanation": "A $24,500 NEFT transfer was executed.",
                    "why_it_deviates_from_baseline": "Historical median is $42.00.",
                    "evidence_considered": ["amount", "median", "deviation_ratio_median"],
                    "mitigating_context": [],
                }
            ],
            "investigation_questions": ["Did the customer authorize this settlement?"],
            "recommended_next_steps": ["Place temporary settlement hold."],
            "limitations": ["Customer income tier not verified in transaction log."],
        }

        result = generate_investigation_report("CUST002", mock_response_text=json.dumps(mock_payload))
        self.assertEqual(result.customer_id, "CUST002")
        self.assertEqual(len(result.finding_explanations), 2)  # R01 + injected baseline R04
        self.assertTrue(result.investigation_assessment.requires_human_review)
        self.assertIn("The system identifies activity requiring human review", result.disclaimer)

    def test_invalid_finding_id_rejected_or_sanitized(self):
        ctx = build_grounding_context("CUST002")
        fake_payload = {
            "customer_id": "CUST002",
            "executive_summary": "Test summary",
            "investigation_assessment": {
                "overall_assessment": "Review required",
                "key_concerns": [],
                "mitigating_factors": [],
                "confidence": "high",
                "requires_human_review": True,
            },
            "finding_explanations": [
                {
                    "finding_id": "HALLUCINATED_FINDING_999",  # Invalid ID!
                    "rule_id": "R01",
                    "plain_language_explanation": "Fake finding",
                    "why_it_deviates_from_baseline": "None",
                    "evidence_considered": [],
                    "mitigating_context": [],
                }
            ],
        }
        res = validate_and_sanitize_investigation_result(fake_payload, ctx)
        finding_ids = [f.finding_id for f in res.finding_explanations]
        self.assertNotIn("HALLUCINATED_FINDING_999", finding_ids)
        # Genuine findings were preserved
        self.assertIn("CUST002_R01_TXN0054", finding_ids)

    def test_invented_transaction_id_not_in_findings(self):
        ctx = build_grounding_context("CUST002")
        valid_txn_ids = {t.transaction_id for t in ctx.relevant_transactions}
        self.assertIn("TXN0054", valid_txn_ids)
        self.assertNotIn("TXN9999_FAKE", valid_txn_ids)

    def test_wrong_rule_id_corrected(self):
        ctx = build_grounding_context("CUST002")
        payload_with_wrong_rule = {
            "customer_id": "CUST002",
            "finding_explanations": [
                {
                    "finding_id": "CUST002_R01_TXN0054",
                    "rule_id": "R99_WRONG",  # Wrong rule ID!
                    "plain_language_explanation": "Explanation",
                    "why_it_deviates_from_baseline": "Deviation",
                    "evidence_considered": [],
                    "mitigating_context": [],
                }
            ],
        }
        res = validate_and_sanitize_investigation_result(payload_with_wrong_rule, ctx)
        r01_expl = next(f for f in res.finding_explanations if f.finding_id == "CUST002_R01_TXN0054")
        self.assertEqual(r01_expl.rule_id, "R01", "Rule ID must be corrected to match deterministic truth")

    def test_deterministic_risk_score_unaffected_by_gemini(self):
        # Gemini output cannot modify deterministic risk scores
        from src.data_loader import load_transactions_for_customer
        from src.risk_engine import analyze_customer_risk

        txns = load_transactions_for_customer("CUST002")
        analysis = analyze_customer_risk("CUST002", txns)
        deterministic_score = analysis.summary.highest_risk_score

        # Ensure that running investigation report doesn't alter deterministic analysis
        ctx = build_grounding_context("CUST002")
        self.assertEqual(ctx.deterministic_findings[0].risk_score, deterministic_score)

    def test_disclaimer_is_always_present(self):
        ctx = build_grounding_context("CUST001")
        res = validate_and_sanitize_investigation_result({}, ctx)
        expected_disclaimer = "The system identifies activity requiring human review. A risk finding does not establish that fraud has occurred."
        self.assertEqual(res.disclaimer, expected_disclaimer)

    def test_mitigating_factors_preserved_for_ambiguous_cases(self):
        ctx = build_grounding_context("CUST006")
        ambiguous_payload = {
            "customer_id": "CUST006",
            "executive_summary": "Single elevated luxury retail transfer to known merchant.",
            "investigation_assessment": {
                "overall_assessment": "Borderline deviation during festive period.",
                "key_concerns": ["Amount $3,200 is elevated compared to historical median."],
                "mitigating_factors": [
                    "Beneficiary Tanishq Jewellers is a known payee with prior transactions",
                    "Transaction occurred during daylight business hours (16:30)",
                    "Executed via customer's primary CARD channel"
                ],
                "confidence": "medium",
                "requires_human_review": True,
            },
            "finding_explanations": [],
        }
        res = validate_and_sanitize_investigation_result(ambiguous_payload, ctx)
        self.assertGreaterEqual(len(res.investigation_assessment.mitigating_factors), 3)
        self.assertIn("known payee", res.investigation_assessment.mitigating_factors[0].lower())

    def test_api_investigation_context_endpoint_200(self):
        response = self.client.get("/api/customers/CUST002/investigation/context")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["customer"]["customer_id"], "CUST002")
        self.assertIn("baseline_summary", data)
        self.assertIn("deterministic_findings", data)
        self.assertIn("relevant_policy_rules", data)
        self.assertIn("relevant_transactions", data)


if __name__ == "__main__":
    unittest.main()
