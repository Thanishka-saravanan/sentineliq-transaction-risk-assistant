import unittest
from fastapi.testclient import TestClient
from app import app
from src.data_loader import (
    load_all_customers,
    load_customer_by_id,
    load_all_transactions,
    load_transactions_for_customer,
    load_risk_rules,
    load_risk_policy_text,
)


class TestPhase2(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_six_customers_exist(self):
        customers = load_all_customers()
        self.assertEqual(len(customers), 6, "Expected exactly 6 customer profiles.")
        expected_ids = {"CUST001", "CUST002", "CUST003", "CUST004", "CUST005", "CUST006"}
        loaded_ids = {c.customer_id for c in customers}
        self.assertEqual(loaded_ids, expected_ids)

    def test_all_customer_scenarios_loaded(self):
        scenarios = {
            "CUST001": "Normal",
            "CUST002": "Large Transfer",
            "CUST003": "New Payee",
            "CUST004": "Odd-Hours",
            "CUST005": "Complex Linked",
            "CUST006": "Ambiguous",
        }
        for cid, keyword in scenarios.items():
            customer = load_customer_by_id(cid)
            self.assertIsNotNone(customer, f"Customer {cid} not found")
            self.assertTrue(
                keyword.lower() in customer.scenario.lower(),
                f"Expected '{keyword}' in scenario for {cid}, got '{customer.scenario}'",
            )

    def test_customer_transaction_history_depth(self):
        customers = load_all_customers()
        for c in customers:
            txns = load_transactions_for_customer(c.customer_id)
            self.assertGreaterEqual(
                len(txns), 20, f"Customer {c.customer_id} has fewer than 20 transactions ({len(txns)})"
            )
            self.assertLessEqual(
                len(txns), 40, f"Customer {c.customer_id} has more than 40 transactions ({len(txns)})"
            )

    def test_transaction_fields_and_uniqueness(self):
        all_txns = load_all_transactions()
        self.assertGreaterEqual(len(all_txns), 120)

        seen_ids = set()
        valid_channels = {"UPI", "CARD", "NEFT", "IMPS", "NET_BANKING", "CASH", "ACH"}

        for t in all_txns:
            # Unique ID
            self.assertNotIn(t.transaction_id, seen_ids, f"Duplicate transaction_id: {t.transaction_id}")
            seen_ids.add(t.transaction_id)

            # Valid customer
            self.assertTrue(t.customer_id.startswith("CUST00"))

            # Positive amount
            self.assertGreater(t.amount, 0, f"Amount must be positive for {t.transaction_id}")

            # Non-empty fields
            self.assertTrue(bool(t.date.strip()))
            self.assertTrue(bool(t.time.strip()))
            self.assertTrue(bool(t.payee.strip()))
            self.assertTrue(bool(t.description.strip()))

            # Valid channel
            self.assertIn(t.channel, valid_channels, f"Invalid channel {t.channel} in {t.transaction_id}")

    def test_chronological_sorting(self):
        customers = load_all_customers()
        for c in customers:
            txns = load_transactions_for_customer(c.customer_id)
            for i in range(len(txns) - 1):
                t1 = txns[i]
                t2 = txns[i + 1]
                self.assertLessEqual(
                    (t1.date, t1.time),
                    (t2.date, t2.time),
                    f"Transactions for {c.customer_id} not sorted: {t1.transaction_id} vs {t2.transaction_id}",
                )

    def test_risk_policy_contains_rules(self):
        policy_text = load_risk_policy_text()
        self.assertIn("The system identifies activity requiring human review.", policy_text)
        self.assertIn("A risk finding does not establish that fraud has occurred.", policy_text)

        rules = load_risk_rules()
        self.assertGreaterEqual(len(rules), 5)
        rule_ids = {r.rule_id for r in rules}
        for expected in ["R01", "R02", "R03", "R04", "R05"]:
            self.assertIn(expected, rule_ids, f"Rule {expected} missing from risk policy")

    def test_api_customers_endpoint(self):
        response = self.client.get("/api/customers")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 6)

    def test_api_single_customer_endpoint(self):
        response = self.client.get("/api/customers/CUST001")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["customer_id"], "CUST001")
        self.assertEqual(data["name"], "Priya Sharma")

    def test_api_customer_transactions_endpoint(self):
        response = self.client.get("/api/customers/CUST002/transactions")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(len(data), 20)
        # Check chronological order in API output
        for i in range(len(data) - 1):
            self.assertLessEqual((data[i]["date"], data[i]["time"]), (data[i + 1]["date"], data[i + 1]["time"]))

    def test_api_rules_endpoint(self):
        response = self.client.get("/api/rules")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(len(data), 5)
        ids = [r["rule_id"] for r in data]
        self.assertEqual(ids[:5], ["R01", "R02", "R03", "R04", "R05"])

    def test_api_invalid_customer_returns_404(self):
        response = self.client.get("/api/customers/INVALID999")
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())

        txn_response = self.client.get("/api/customers/INVALID999/transactions")
        self.assertEqual(txn_response.status_code, 404)
        self.assertIn("not found", txn_response.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
