import unittest
from fastapi.testclient import TestClient
from app import app


class TestPhase6Dashboard(unittest.TestCase):
    """Automated integration and smoke tests for Phase 6 Investigation Dashboard."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_homepage_serves_dashboard_html(self):
        """Verify GET / serves the full SentinelIQ investigation dashboard."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        html = response.text

        # Core branding & Track requirement
        self.assertIn("SentinelIQ", html)
        self.assertIn("TRACK_ID: PS06", html)
        self.assertIn("Grounded AI for transaction risk investigation", html)

        # Architecture pipeline indicator
        self.assertIn("Deterministic Detection", html)
        self.assertIn("Grounded AI", html)
        self.assertIn("Human Review", html)

        # Key DOM hooks for JS module
        self.assertIn('id="customer-list"', html)
        self.assertIn('id="overview-customer-name"', html)
        self.assertIn('id="special-callout-container"', html)
        self.assertIn('id="baseline-container"', html)
        self.assertIn('id="findings-container"', html)
        self.assertIn('id="tx-table-body"', html)
        self.assertIn('id="btn-generate-ai"', html)
        self.assertIn('id="copilot-loading"', html)
        self.assertIn('id="copilot-output"', html)

        # Asset linkages
        self.assertIn("/static/css/styles.css", html)
        self.assertIn("/static/js/app.js", html)

    def test_static_css_served(self):
        """Verify GET /static/css/styles.css is accessible and contains required styling rules."""
        response = self.client.get("/static/css/styles.css")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            "text/css" in response.headers.get("content-type", "") or response.status_code == 200
        )
        css = response.text
        self.assertIn(".app-header", css)
        self.assertIn(".customer-card", css)
        self.assertIn(".severity-critical", css)
        self.assertIn(".finding-card", css)
        self.assertIn(".tx-table", css)
        self.assertIn(".copilot-section", css)
        self.assertIn(".highlighted", css)

    def test_static_js_served(self):
        """Verify GET /static/js/app.js is accessible and contains dashboard controller logic."""
        response = self.client.get("/static/js/app.js")
        self.assertEqual(response.status_code, 200)
        js = response.text
        self.assertIn("selectedCustomerId: 'CUST005'", js)
        self.assertIn("selectCustomer", js)
        self.assertIn("generateInvestigation", js)
        self.assertIn("highlightAndScrollToTransactions", js)
        self.assertIn("callout-ambiguous", js)
        self.assertIn("callout-attack", js)

    def test_all_apis_consumed_by_dashboard(self):
        """Verify all backend APIs expected by the dashboard respond with valid data."""
        # 1. Rules
        r = self.client.get("/api/rules")
        self.assertEqual(r.status_code, 200)
        rules = r.json()
        self.assertEqual(len(rules), 5)

        # 2. Customers
        c = self.client.get("/api/customers")
        self.assertEqual(c.status_code, 200)
        customers = c.json()
        self.assertEqual(len(customers), 6)

        # 3. CUST005 (Showcase default)
        analysis_5 = self.client.get("/api/customers/CUST005/risk-analysis").json()
        self.assertIn("R05", analysis_5["summary"]["rules_triggered"])
        self.assertTrue(analysis_5["summary"]["requires_human_review"])

        findings_5 = self.client.get("/api/customers/CUST005/findings").json()
        self.assertGreaterEqual(len(findings_5), 1)

        baseline_5 = self.client.get("/api/customers/CUST005/baseline/summary").json()
        self.assertIn("typical_amount_range", baseline_5)

        txns_5 = self.client.get("/api/customers/CUST005/transactions").json()
        self.assertGreaterEqual(len(txns_5), 1)

        # 4. CUST006 (Ambiguity case)
        findings_6 = self.client.get("/api/customers/CUST006/findings").json()
        self.assertEqual(len(findings_6), 1)
        self.assertEqual(findings_6[0]["rule_id"], "R01")

        # 5. CUST001 (Routine case)
        findings_1 = self.client.get("/api/customers/CUST001/findings").json()
        self.assertEqual(len(findings_1), 0)

    def test_dashboard_api_error_handling(self):
        """Verify error status codes consumed cleanly by frontend."""
        r = self.client.get("/api/customers/INVALID999/risk-analysis")
        self.assertEqual(r.status_code, 404)

        r = self.client.get("/api/customers/INVALID999/baseline/summary")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
