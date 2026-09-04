import unittest
from fastapi.testclient import TestClient
from app import app
from src.baseline import (
    build_customer_baseline,
    build_baseline_excluding_transaction,
    build_baseline_summary,
)
from src.data_loader import (
    load_all_customers,
    load_transactions_for_customer,
)
from src.models import Transaction


class TestPhase3(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.customers = load_all_customers()

    def test_every_customer_baseline_can_be_generated(self):
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            baseline = build_customer_baseline(txns, customer_id=c.customer_id)
            self.assertIsNotNone(baseline)
            self.assertEqual(baseline.customer_id, c.customer_id)
            self.assertIsNone(baseline.generated_at, "generated_at must be null for determinism")

    def test_transaction_count_matches_loaded_data(self):
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            baseline = build_customer_baseline(txns, customer_id=c.customer_id)
            self.assertEqual(baseline.amount_profile.count, len(txns))
            self.assertEqual(baseline.frequency_profile.transaction_count, len(txns))

    def test_amount_statistics_validity(self):
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            amounts = [t.amount for t in txns]
            baseline = build_customer_baseline(txns, customer_id=c.customer_id)
            p = baseline.amount_profile

            self.assertAlmostEqual(p.total, sum(amounts), places=1)
            self.assertAlmostEqual(p.min, min(amounts), places=2)
            self.assertAlmostEqual(p.max, max(amounts), places=2)
            self.assertTrue(p.min <= p.median <= p.max)
            self.assertTrue(p.min <= p.mean <= p.max)
            self.assertGreaterEqual(p.std_dev, 0.0)

    def test_median_within_min_and_max(self):
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            baseline = build_customer_baseline(txns, customer_id=c.customer_id)
            p = baseline.amount_profile
            self.assertLessEqual(p.min, p.median)
            self.assertLessEqual(p.median, p.max)

    def test_q1_less_than_or_equal_to_q3(self):
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            baseline = build_customer_baseline(txns, customer_id=c.customer_id)
            self.assertLessEqual(baseline.amount_profile.q1, baseline.amount_profile.q3)

    def test_iqr_non_negative(self):
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            baseline = build_customer_baseline(txns, customer_id=c.customer_id)
            self.assertGreaterEqual(baseline.amount_profile.iqr, 0.0)

    def test_typical_range_validity(self):
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            baseline = build_customer_baseline(txns, customer_id=c.customer_id)
            p = baseline.amount_profile
            self.assertGreaterEqual(p.typical_lower_bound, 0.0)
            self.assertLessEqual(p.typical_lower_bound, p.typical_upper_bound)

    def test_channel_percentages_sum_to_approximately_100(self):
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            baseline = build_customer_baseline(txns, customer_id=c.customer_id)
            percentages = list(baseline.channel_profile.channel_percentages.values())
            total_pct = sum(percentages)
            self.assertAlmostEqual(total_pct, 100.0, delta=1.0)
            self.assertTrue(baseline.channel_profile.primary_channel in baseline.channel_profile.common_channels)

    def test_payees_sorted_deterministically(self):
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            baseline = build_customer_baseline(txns, customer_id=c.customer_id)
            payee_items = list(baseline.payee_profile.payee_counts.items())
            for i in range(len(payee_items) - 1):
                p1_name, p1_cnt = payee_items[i]
                p2_name, p2_cnt = payee_items[i + 1]
                if p1_cnt == p2_cnt:
                    self.assertLessEqual(p1_name, p2_name)
                else:
                    self.assertGreater(p1_cnt, p2_cnt)

    def test_time_profile_validity(self):
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            baseline = build_customer_baseline(txns, customer_id=c.customer_id)
            tp = baseline.time_profile
            self.assertEqual(len(tp.hourly_counts), 24)
            self.assertEqual(sum(tp.hourly_counts.values()), len(txns))
            self.assertTrue(0 <= tp.earliest_hour <= 23)
            self.assertTrue(0 <= tp.latest_hour <= 23)
            self.assertTrue(tp.earliest_hour <= tp.latest_hour)
            self.assertTrue(0 <= tp.median_hour <= 23)
            self.assertTrue(tp.typical_start_hour <= tp.typical_end_hour)

    def test_late_night_metrics_non_negative(self):
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            baseline = build_customer_baseline(txns, customer_id=c.customer_id)
            tp = baseline.time_profile
            self.assertGreaterEqual(tp.late_night_transaction_count, 0)
            self.assertGreaterEqual(tp.late_night_percentage, 0.0)
            self.assertLessEqual(tp.late_night_percentage, 100.0)

    def test_frequency_profile_no_zero_division(self):
        for c in self.customers:
            txns = load_transactions_for_customer(c.customer_id)
            baseline = build_customer_baseline(txns, customer_id=c.customer_id)
            fp = baseline.frequency_profile
            self.assertGreater(fp.active_days, 0)
            self.assertGreater(fp.date_range_days, 0)
            self.assertGreater(fp.transactions_per_active_day, 0.0)
            self.assertGreater(fp.transactions_per_calendar_day, 0.0)
            self.assertGreater(fp.transactions_per_week, 0.0)

    def test_excluding_transaction_reduces_count_by_one(self):
        txns = load_transactions_for_customer("CUST002")
        target_id = txns[-1].transaction_id
        baseline_full = build_customer_baseline(txns, customer_id="CUST002")
        baseline_excl = build_baseline_excluding_transaction(txns, target_id, customer_id="CUST002")

        self.assertEqual(
            baseline_excl.amount_profile.count,
            baseline_full.amount_profile.count - 1,
        )
        self.assertEqual(
            baseline_excl.frequency_profile.transaction_count,
            baseline_full.frequency_profile.transaction_count - 1,
        )

    def test_empty_input_handled_safely(self):
        baseline = build_customer_baseline([], customer_id="CUST_EMPTY")
        self.assertEqual(baseline.amount_profile.count, 0)
        self.assertEqual(baseline.amount_profile.total, 0.0)
        self.assertEqual(baseline.amount_profile.mean, 0.0)
        self.assertEqual(baseline.amount_profile.median, 0.0)
        self.assertEqual(baseline.frequency_profile.transactions_per_calendar_day, 0.0)
        self.assertEqual(baseline.time_profile.late_night_transaction_count, 0)

        summary = build_baseline_summary(baseline)
        self.assertEqual(summary.transaction_count, 0)
        self.assertEqual(summary.typical_amount, 0.0)

    def test_single_transaction_handled_safely(self):
        single_txn = [
            Transaction(
                transaction_id="TXN_SINGLE",
                customer_id="CUST_ONE",
                date="2024-01-01",
                time="14:30:00",
                description="Single grocery run",
                payee="FreshStore",
                amount=75.50,
                channel="UPI",
            )
        ]
        baseline = build_customer_baseline(single_txn, customer_id="CUST_ONE")
        self.assertEqual(baseline.amount_profile.count, 1)
        self.assertEqual(baseline.amount_profile.mean, 75.50)
        self.assertEqual(baseline.amount_profile.median, 75.50)
        self.assertEqual(baseline.amount_profile.min, 75.50)
        self.assertEqual(baseline.amount_profile.max, 75.50)
        self.assertEqual(baseline.amount_profile.std_dev, 0.0)
        self.assertEqual(baseline.channel_profile.primary_channel, "UPI")
        self.assertEqual(baseline.payee_profile.unique_payee_count, 1)

        summary = build_baseline_summary(baseline)
        self.assertEqual(summary.typical_amount, 75.50)

    def test_api_customer_baseline_endpoint_returns_200(self):
        response = self.client.get("/api/customers/CUST001/baseline")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["customer_id"], "CUST001")
        self.assertIn("amount_profile", data)
        self.assertIn("time_profile", data)
        self.assertIn("channel_profile", data)
        self.assertIn("payee_profile", data)
        self.assertIn("frequency_profile", data)
        self.assertIsNone(data["generated_at"])

    def test_api_customer_baseline_summary_endpoint_returns_200(self):
        response = self.client.get("/api/customers/CUST001/baseline/summary")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["customer_id"], "CUST001")
        self.assertEqual(data["transaction_count"], 26)
        self.assertIn("typical_amount", data)
        self.assertIn("typical_amount_range", data)
        self.assertIn("usual_transaction_hours", data)
        self.assertIn("common_channels", data)
        self.assertIn("frequent_payees", data)

    def test_api_invalid_customer_baseline_returns_404(self):
        response = self.client.get("/api/customers/INVALID999/baseline")
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())

        summary_resp = self.client.get("/api/customers/INVALID999/baseline/summary")
        self.assertEqual(summary_resp.status_code, 404)
        self.assertIn("not found", summary_resp.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
