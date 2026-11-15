import unittest

from app import app


class HotspotAppTests(unittest.TestCase):
    def test_health_endpoint(self):
        response = app.test_client().get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_world_report_is_served_and_loads_hotspots(self):
        response = app.test_client().get("/hotspot_world_report.html")
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/api/hotspots?date=", response.data)
        self.assertIn(b'id="map"', response.data)
        self.assertIn(b'id="total-count"', response.data)

    def test_homepage_links_to_report(self):
        response = app.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/hotspot_world_report.html", response.data)

    def test_chat_endpoint_is_removed(self):
        response = app.test_client().post("/api/chat", json={"question": "hello"})
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
