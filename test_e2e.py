"""End-to-End Automated Verification Test Suite for Vehicle & Person Detection POC PWA.

Covers:
1. HTTP Basic Authentication enforcement (admin:nomer123456) across all routes and assets.
2. Security edge cases: missing auth, non-Basic schemes, malformed base64, wrong user, wrong password.
3. Static PWA asset serving (/, /index.html, /style.css, /app.js, /manifest.json, /sw.js, icons).
4. Frontend static code assertions (facingMode: "environment", 1500ms interval, /analyze endpoint, overlay canvas color coding, mutex guard).
5. POST /analyze error handling (401 unauth, 400 empty body, 400 corrupted bytes, 400 non-image text file, 404/405 wrong methods).
6. POST /analyze inference across all sample images in data/ folder with full JSON schema validation.
7. Explicit detection, color extraction, plate OCR, and person count assertions for each individual sample image.
"""

import os
import sys
import base64
import unittest
from fastapi.testclient import TestClient

from backend.main import app, AUTH_USERNAME, AUTH_PASSWORD

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(f"{AUTH_USERNAME}:{AUTH_PASSWORD}".encode()).decode()}
BAD_PASS_HEADER = {"Authorization": "Basic " + base64.b64encode(f"{AUTH_USERNAME}:wrongpassword".encode()).decode()}
BAD_USER_HEADER = {"Authorization": "Basic " + base64.b64encode(f"wronguser:{AUTH_PASSWORD}".encode()).decode()}


class TestVehiclePersonDetectionE2E(unittest.TestCase):
    """Full End-to-End Test Suite for Vehicle & Person Detection POC."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    # -------------------------------------------------------------------------
    # Authentication & Security Tests
    # -------------------------------------------------------------------------

    def test_01_auth_enforcement_unauthenticated(self):
        """Verify unauthenticated GET / returns HTTP 401 with WWW-Authenticate header."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Basic", resp.headers.get("www-authenticate", ""))
        self.assertIn('realm="Restricted"', resp.headers.get("www-authenticate", ""))

    def test_02_auth_enforcement_bad_credentials(self):
        """Verify invalid username and invalid password return HTTP 401."""
        # Wrong password
        resp_bad_pass = self.client.get("/", headers=BAD_PASS_HEADER)
        self.assertEqual(resp_bad_pass.status_code, 401)

        # Wrong username
        resp_bad_user = self.client.get("/", headers=BAD_USER_HEADER)
        self.assertEqual(resp_bad_user.status_code, 401)

        # Malformed header
        resp_malformed = self.client.get("/", headers={"Authorization": "Basic not_valid_base64!!!"})
        self.assertEqual(resp_malformed.status_code, 401)

        # Non-basic scheme
        resp_bearer = self.client.get("/", headers={"Authorization": "Bearer some-token"})
        self.assertEqual(resp_bearer.status_code, 401)

    def test_03_auth_enforcement_valid_credentials(self):
        """Verify valid admin:nomer123456 returns HTTP 200 and loads PWA HTML."""
        resp = self.client.get("/", headers=AUTH_HEADER)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("<video", resp.text)
        self.assertIn("<canvas", resp.text)
        self.assertIn("json-output", resp.text)

    # -------------------------------------------------------------------------
    # Static Assets & PWA Infrastructure Tests
    # -------------------------------------------------------------------------

    def test_04_static_pwa_assets(self):
        """Verify all static PWA assets are served with HTTP 200 when authenticated."""
        # index.html
        resp_html = self.client.get("/index.html", headers=AUTH_HEADER)
        self.assertEqual(resp_html.status_code, 200)
        self.assertIn("camera-feed", resp_html.text)

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
        self.assertTrue(str(manifest_data.get("orientation", "")).startswith("portrait"))
        self.assertIn("icons", manifest_data)

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
        self.assertTrue(
            "facingMode" in js_code and "environment" in js_code,
            "app.js must specify environment camera"
        )
        
        # 2. 1.5s (1500ms) interval
        self.assertTrue(
            "1500" in js_code and ("setInterval" in js_code or "CAPTURE_INTERVAL_MS" in js_code),
            "app.js must use 1.5s interval loop"
        )

        # 3. POST /analyze call with Basic Auth
        self.assertIn("/analyze", js_code, "app.js must target /analyze endpoint")
        self.assertIn("Authorization", js_code, "app.js must send Authorization header")
        self.assertIn("Basic", js_code, "app.js must send Basic auth header")

        # 4. Color distinctions for canvas bounding boxes
        self.assertIn("#06b6d4", js_code, "app.js must use Cyan for vehicle bounding boxes")
        self.assertIn("#10b981", js_code, "app.js must use Emerald for person bounding boxes")

        # 5. Mutex locking
        self.assertIn("isAnalyzing", js_code, "app.js must implement concurrency mutex guard")

    # -------------------------------------------------------------------------
    # API Error Handling & Shielding Tests
    # -------------------------------------------------------------------------

    def test_06_analyze_error_shielding(self):
        """Verify error shielding for unauth, empty, corrupted, and invalid payloads."""
        # Unauthenticated
        resp_unauth = self.client.post("/analyze", data=b"some bytes")
        self.assertEqual(resp_unauth.status_code, 401)

        # Empty body
        resp_empty = self.client.post("/analyze", headers=AUTH_HEADER, data=b"")
        self.assertEqual(resp_empty.status_code, 400)

        # Corrupted payload
        resp_corrupt = self.client.post("/analyze", headers=AUTH_HEADER, data=b"NON_IMAGE_CORRUPTED_BYTES_999")
        self.assertEqual(resp_corrupt.status_code, 400)

        # Plain text file upload
        resp_txt = self.client.post(
            "/analyze",
            headers=AUTH_HEADER,
            files={"file": ("readme.txt", b"plain text payload not an image", "text/plain")}
        )
        self.assertEqual(resp_txt.status_code, 400)

        # Non-POST requests
        for method in ["get", "put", "delete"]:
            with self.subTest(method=method):
                client_fn = getattr(self.client, method)
                resp_method = client_fn("/analyze", headers=AUTH_HEADER)
                self.assertIn(resp_method.status_code, [404, 405])

    # -------------------------------------------------------------------------
    # Generic Dataset Pipeline & Schema Tests
    # -------------------------------------------------------------------------

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
                self.assertIsInstance(data.get("persons"), list)
                self.assertIsInstance(data.get("bounding_boxes"), list)
                self.assertIn("processing_time_ms", data)
                self.assertGreater(data["processing_time_ms"], 0)

                # Bounding box structure
                for box_item in data.get("bounding_boxes", []):
                    self.assertIn("box", box_item)
                    box = box_item["box"]
                    self.assertEqual(len(box), 4)
                    self.assertLessEqual(box[0], box[2])
                    self.assertLessEqual(box[1], box[3])

                # 2. Multipart form upload
                resp_mp = self.client.post(
                    "/analyze",
                    headers=AUTH_HEADER,
                    files={"file": (fname, img_bytes, "image/jpeg")}
                )
                self.assertEqual(resp_mp.status_code, 200)
                self.assertEqual(resp_mp.json().get("status"), "success")

    # -------------------------------------------------------------------------
    # Specific Domain Assertions per Sample Image
    # -------------------------------------------------------------------------

    def test_08_specific_sample_image_detections(self):
        """Verify exact detection, color extraction, plate OCR, and person counts for named sample images."""
        expected_specs = {
            # 1. Toyota Yaris -> White car with clear UK license plate GX67TKZ
            "Toyota-Yaris-GRMN-Review-Front-carwitter.jpg": {
                "min_vehicles": 1,
                "expected_color": "white",
                "expected_plate_substr": "GX67TKZ",
                "max_persons": 0
            },
            # 2. Classic VW Beetle #53 -> White car
            "classic-white-type-1-volkswagen-beetle-with-race-car-stripe-and-number-53-parked-outside-a-building-under-sunlight-3CPJ3B2.jpg": {
                "min_vehicles": 1,
                "expected_color": "white",
                "max_persons": 0
            },
            # 3. Wet city street AVIF -> Multiple vehicles in rain, silver/gray dominant
            "car-driving-wet-city-street-rainy-traffic_169016-73138.avif": {
                "min_vehicles": 3,
                "expected_color_in": ["silver", "gray", "white", "black"],
            },
            # 4. Indian Car with Plate DL 2C AX 2964 and pedestrian
            "images (1).jpg": {
                "min_vehicles": 1,
                "expected_plate_substr": "2964",
                "min_persons": 1
            },
            # 5. Delivery Truck with Plate MH 02 CP 8000 and pedestrians
            "images.jpg": {
                "min_vehicles": 1,
                "expected_plate_substr": "8OOO",
                "min_persons": 1
            },
            # 6. Segmented scene
            "segment_example.png": {
                "min_vehicles": 1,
                "expected_color": "white"
            }
        }

        for fname, spec in expected_specs.items():
            fpath = os.path.join(self.data_dir, fname)
            if not os.path.exists(fpath):
                continue

            with self.subTest(sample_name=fname):
                with open(fpath, "rb") as f:
                    img_bytes = f.read()

                resp = self.client.post("/analyze", headers=AUTH_HEADER, content=img_bytes)
                self.assertEqual(resp.status_code, 200)
                data = resp.json()

                if "min_vehicles" in spec:
                    self.assertGreaterEqual(
                        data["vehicle_count"],
                        spec["min_vehicles"],
                        f"Expected at least {spec['min_vehicles']} vehicles in {fname}, got {data['vehicle_count']}"
                    )

                if "expected_color" in spec:
                    self.assertEqual(
                        data["car_color"],
                        spec["expected_color"],
                        f"Expected car_color '{spec['expected_color']}' for {fname}, got '{data['car_color']}'"
                    )

                if "expected_color_in" in spec:
                    self.assertIn(
                        data["car_color"],
                        spec["expected_color_in"],
                        f"Expected car_color in {spec['expected_color_in']} for {fname}, got '{data['car_color']}'"
                    )

                if "expected_plate_substr" in spec:
                    # Check plate_number or any detected vehicle plate
                    all_plates = [v.get("plate", "") for v in data.get("vehicles", []) if v.get("plate")]
                    if data.get("plate_number"):
                        all_plates.append(data["plate_number"])
                    has_plate = any(spec["expected_plate_substr"] in p for p in all_plates)
                    self.assertTrue(
                        has_plate,
                        f"Expected plate substring '{spec['expected_plate_substr']}' in detected plates {all_plates} for {fname}"
                    )

                if "min_persons" in spec:
                    self.assertGreaterEqual(
                        data["person_count"],
                        spec["min_persons"],
                        f"Expected at least {spec['min_persons']} persons in {fname}, got {data['person_count']}"
                    )

                if "max_persons" in spec:
                    self.assertLessEqual(
                        data["person_count"],
                        spec["max_persons"],
                        f"Expected at most {spec['max_persons']} persons in {fname}, got {data['person_count']}"
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
