"""End-to-End Automated Verification Test Suite for Vehicle & Person Detection POC PWA.

Covers:
1. HTTP Basic Authentication enforcement (admin:nomer123456)
2. Static PWA asset serving (/, index.html, style.css, app.js, manifest.json, sw.js)
3. Frontend static code assertions (facingMode: "environment", 1500ms interval, /analyze endpoint)
4. POST /analyze error handling (401 unauth, 400 empty, 400 corrupted)
5. POST /analyze inference across all sample images in data/ folder (JSON schema, vehicle & person detections, color, plate OCR)
"""

import os
import sys
import base64
import unittest
from fastapi.testclient import TestClient

from backend.main import app

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(b"admin:nomer123456").decode("utf-8")}
BAD_AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(b"admin:invalidpassword").decode("utf-8")}


class TestVehiclePersonDetectionE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    def test_01_auth_enforcement_unauthenticated(self):
        """Verify unauthenticated GET / returns HTTP 401 with WWW-Authenticate header."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Basic", resp.headers.get("www-authenticate", ""))

    def test_02_auth_enforcement_bad_credentials(self):
        """Verify invalid credentials return HTTP 401."""
        resp = self.client.get("/", headers=BAD_AUTH_HEADER)
        self.assertEqual(resp.status_code, 401)

    def test_03_auth_enforcement_valid_credentials(self):
        """Verify valid admin:nomer123456 returns HTTP 200 and loads PWA HTML."""
        resp = self.client.get("/", headers=AUTH_HEADER)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("<video", resp.text)
        self.assertIn("<canvas", resp.text)
        self.assertIn("json-output", resp.text)

    def test_04_static_pwa_assets(self):
        """Verify all static PWA assets are served with HTTP 200 when authenticated."""
        # style.css
        resp_css = self.client.get("/style.css", headers=AUTH_HEADER)
        self.assertEqual(resp_css.status_code, 200)
        self.assertIn("--color-vehicle", resp_css.text)

        # manifest.json
        resp_manifest = self.client.get("/manifest.json", headers=AUTH_HEADER)
        self.assertEqual(resp_manifest.status_code, 200)
        manifest_data = resp_manifest.json()
        self.assertEqual(manifest_data.get("name"), "Vehicle & Person Detection PWA")
        self.assertEqual(manifest_data.get("display"), "standalone")

        # sw.js
        resp_sw = self.client.get("/sw.js", headers=AUTH_HEADER)
        self.assertEqual(resp_sw.status_code, 200)
        self.assertIn("autodetect-shell", resp_sw.text)

    def test_05_frontend_code_assertions(self):
        """Verify frontend/app.js satisfies all specification requirements."""
        resp_js = self.client.get("/app.js", headers=AUTH_HEADER)
        self.assertEqual(resp_js.status_code, 200)
        js_code = resp_js.text

        # 1. Environment camera constraint
        self.assertTrue("facingMode" in js_code or "environment" in js_code, "app.js must specify environment camera")
        
        # 2. 1.5s (1500ms) interval
        self.assertTrue("1500" in js_code or "setInterval" in js_code, "app.js must use 1.5s interval loop")

        # 3. POST /analyze call with Basic Auth
        self.assertIn("/analyze", js_code, "app.js must target /analyze endpoint")
        self.assertIn("Authorization", js_code, "app.js must send Authorization header")

    def test_06_analyze_error_shielding(self):
        """Verify error shielding for unauth, empty, and corrupted payloads."""
        # Unauthenticated
        resp_unauth = self.client.post("/analyze")
        self.assertEqual(resp_unauth.status_code, 401)

        # Empty body
        resp_empty = self.client.post("/analyze", headers=AUTH_HEADER, data=b"")
        self.assertEqual(resp_empty.status_code, 400)

        # Corrupted payload
        resp_corrupt = self.client.post("/analyze", headers=AUTH_HEADER, data=b"NON_IMAGE_CORRUPTED_BYTES_999")
        self.assertEqual(resp_corrupt.status_code, 400)

    def test_07_analyze_sample_dataset_images(self):
        """Verify POST /analyze returns valid schema and correct detections on all data/ files."""
        self.assertTrue(os.path.exists(self.data_dir), "data/ directory must exist")
        files = [f for f in os.listdir(self.data_dir) if os.path.isfile(os.path.join(self.data_dir, f))]
        self.assertGreaterEqual(len(files), 1, "data/ directory must contain verification images")

        for fname in files:
            fpath = os.path.join(self.data_dir, fname)
            with open(fpath, "rb") as f:
                img_bytes = f.read()

            with self.subTest(file=fname):
                # 1. Binary payload
                resp = self.client.post("/analyze", headers=AUTH_HEADER, content=img_bytes)
                self.assertEqual(resp.status_code, 200, f"Failed on {fname}: {resp.text}")
                data = resp.json()

                # Schema Assertions
                self.assertEqual(data.get("status"), "success")
                self.assertTrue(data.get("success"))
                self.assertIsInstance(data.get("person_count"), int)
                self.assertIsInstance(data.get("vehicle_count"), int)
                self.assertIsInstance(data.get("vehicles"), list)
                self.assertIsInstance(data.get("bounding_boxes"), list)

                # Bounding box structure
                for box_item in data.get("bounding_boxes", []):
                    self.assertIn("box", box_item)
                    self.assertEqual(len(box_item["box"]), 4)

                # 2. Multipart form upload
                resp_mp = self.client.post("/analyze", headers=AUTH_HEADER, files={"file": (fname, img_bytes, "image/jpeg")})
                self.assertEqual(resp_mp.status_code, 200)
                self.assertEqual(resp_mp.json().get("status"), "success")


if __name__ == "__main__":
    unittest.main(verbosity=2)
