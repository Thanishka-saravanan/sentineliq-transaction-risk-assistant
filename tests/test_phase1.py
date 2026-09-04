import unittest
from fastapi.testclient import TestClient
from app import app


class TestPhase1(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_check(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["track_id"], "PS06")
        self.assertEqual(data["project"], "SentinelIQ")

    def test_homepage(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("SentinelIQ", response.text)


if __name__ == "__main__":
    unittest.main()
