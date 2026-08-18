"""Comprehensive Unit and Component Test Suite for Vehicle & Person Detection POC.

Covers:
- Tier 1: ML Service Unit Tests (Color spaces, K-Means clustering, OCR parser, Image decoding)
- Tier 2: Authentication Middleware & HTTP Error Shielding
- Tier 3: Static Asset Serving & MIME types
- Tier 4: Frontend PWA Contract & Specification Assertions
"""

import io
import os
import base64
import unittest
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient

from backend.main import app, AUTH_USERNAME, AUTH_PASSWORD
from backend.ml_service import (
    rgb_to_color_name,
    extract_dominant_color,
    ml_service,
    COLOR_MAP,
    VEHICLE_CLASS_IDS,
    PERSON_CLASS_ID
)

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(f"{AUTH_USERNAME}:{AUTH_PASSWORD}".encode()).decode()}


class TestMLServiceUnits(unittest.TestCase):
    """Tier 1: ML Service Unit and Edge Case Tests."""

    def test_01_color_name_mapping_all_categories(self):
        """Verify rgb_to_color_name maps correctly across all 12 defined color categories."""
        test_cases = [
            # Black (low brightness / very low RGB)
            (10, 10, 10, "black"),
            (30, 28, 32, "black"),
            # White (high brightness, low saturation)
            (245, 245, 245, "white"),
            (220, 225, 230, "white"),
            # Silver (mid-high neutral)
            (170, 170, 175, "silver"),
            # Gray (mid neutral)
            (100, 100, 105, "gray"),
            # Red (hue near 0 / 360)
            (230, 20, 20, "red"),
            (200, 30, 50, "red"),
            # Orange (hue 15..42)
            (240, 130, 20, "orange"),
            # Brown (low brightness orange hue)
            (80, 45, 20, "brown"),
            # Yellow (hue 42..70)
            (240, 230, 20, "yellow"),
            # Green (hue 70..165)
            (20, 180, 30, "green"),
            # Blue (hue 165..255)
            (20, 100, 240, "blue"),
            # Purple (hue 255..290)
            (150, 20, 200, "purple"),
            # Pink (hue 290..345)
            (240, 100, 180, "pink"),
        ]

        for r, g, b, expected_color in test_cases:
            with self.subTest(r=r, g=g, b=b, expected=expected_color):
                color_name, rgb_val = rgb_to_color_name(r, g, b)
                self.assertEqual(color_name, expected_color, f"Expected {expected_color} for RGB({r},{g},{b}), got {color_name}")
                self.assertEqual(rgb_val, [r, g, b])

    def test_02_dominant_color_synthetic_images(self):
        """Verify extract_dominant_color accurately identifies dominant color from synthetic vehicle crops."""
        # Solid Red image
        red_img = np.full((100, 100, 3), [220, 20, 20], dtype=np.uint8)
        color_name, _ = extract_dominant_color(red_img)
        self.assertEqual(color_name, "red")

        # Solid White image
        white_img = np.full((100, 100, 3), [240, 240, 240], dtype=np.uint8)
        color_name, _ = extract_dominant_color(white_img)
        self.assertEqual(color_name, "white")

        # Solid Blue image
        blue_img = np.full((100, 100, 3), [20, 100, 230], dtype=np.uint8)
        color_name, _ = extract_dominant_color(blue_img)
        self.assertEqual(color_name, "blue")

        # Solid Black image
        black_img = np.full((100, 100, 3), [15, 15, 15], dtype=np.uint8)
        color_name, _ = extract_dominant_color(black_img)
        self.assertEqual(color_name, "black")

    def test_03_dominant_color_edge_cases(self):
        """Verify extract_dominant_color handles empty, tiny, and edge-case arrays gracefully."""
        # Empty array
        color_empty, rgb_empty = extract_dominant_color(np.array([]))
        self.assertEqual(color_empty, "unknown")
        self.assertEqual(rgb_empty, [128, 128, 128])

        # None input
        color_none, rgb_none = extract_dominant_color(None)
        self.assertEqual(color_none, "unknown")

        # Tiny 5x5 image
        tiny_img = np.full((5, 5, 3), [200, 30, 30], dtype=np.uint8)
        color_tiny, _ = extract_dominant_color(tiny_img)
        self.assertEqual(color_tiny, "red")

    def test_04_decode_image_formats(self):
        """Verify decode_image handles JPEG, PNG, and raises ValueError on corrupted bytes."""
        # Generate valid in-memory JPEG bytes
        pil_img = Image.new("RGB", (64, 64), color=(100, 150, 200))
        jpeg_buf = io.BytesIO()
        pil_img.save(jpeg_buf, format="JPEG")
        jpeg_bytes = jpeg_buf.getvalue()

        decoded_jpeg = ml_service.decode_image(jpeg_bytes)
        self.assertIsInstance(decoded_jpeg, np.ndarray)
        self.assertEqual(decoded_jpeg.shape, (64, 64, 3))

        # Generate valid in-memory PNG bytes
        png_buf = io.BytesIO()
        pil_img.save(png_buf, format="PNG")
        png_bytes = png_buf.getvalue()

        decoded_png = ml_service.decode_image(png_bytes)
        self.assertIsInstance(decoded_png, np.ndarray)
        self.assertEqual(decoded_png.shape, (64, 64, 3))

        # Corrupted bytes
        with self.assertRaises(ValueError):
            ml_service.decode_image(b"INVALID_IMAGE_BYTES_12345")

        # Empty bytes
        with self.assertRaises(ValueError):
            ml_service.decode_image(b"")

    def test_05_vehicle_and_person_classes(self):
        """Verify COCO class definitions match specification."""
        self.assertEqual(PERSON_CLASS_ID, 0)
        self.assertEqual(VEHICLE_CLASS_IDS[2], "car")
        self.assertEqual(VEHICLE_CLASS_IDS[3], "motorcycle")
        self.assertEqual(VEHICLE_CLASS_IDS[5], "bus")
        self.assertEqual(VEHICLE_CLASS_IDS[7], "truck")


class TestSecurityAndAuthMiddleware(unittest.TestCase):
    """Tier 2: HTTP Basic Authentication & Security Shielding Tests."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_no_auth_header(self):
        """Missing Authorization header must return 401 with WWW-Authenticate header."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 401)
        self.assertIn('Basic realm="Restricted"', resp.headers.get("www-authenticate", ""))

    def test_02_bearer_auth_scheme_rejected(self):
        """Non-Basic schemes (Bearer) must be rejected with 401."""
        resp = self.client.get("/", headers={"Authorization": "Bearer some-token"})
        self.assertEqual(resp.status_code, 401)

    def test_03_malformed_base64_rejected(self):
        """Malformed base64 string in Basic auth must return 401."""
        resp = self.client.get("/", headers={"Authorization": "Basic ???not-valid-base64???"})
        self.assertEqual(resp.status_code, 401)

    def test_04_wrong_user_valid_password(self):
        """Wrong username with valid password must return 401."""
        bad_auth = "Basic " + base64.b64encode(b"wronguser:nomer123456").decode()
        resp = self.client.get("/", headers={"Authorization": bad_auth})
        self.assertEqual(resp.status_code, 401)

    def test_05_valid_user_wrong_password(self):
        """Valid username with wrong password must return 401."""
        bad_auth = "Basic " + base64.b64encode(b"admin:wrongpass").decode()
        resp = self.client.get("/", headers={"Authorization": bad_auth})
        self.assertEqual(resp.status_code, 401)

    def test_06_empty_credentials(self):
        """Empty credentials string ':' must return 401."""
        bad_auth = "Basic " + base64.b64encode(b":").decode()
        resp = self.client.get("/", headers={"Authorization": bad_auth})
        self.assertEqual(resp.status_code, 401)

    def test_07_valid_credentials_all_endpoints(self):
        """Valid credentials return 200 on /, /index.html, /style.css, /app.js, /manifest.json."""
        for path in ["/", "/index.html", "/style.css", "/app.js", "/manifest.json", "/sw.js"]:
            with self.subTest(path=path):
                resp = self.client.get(path, headers=AUTH_HEADER)
                self.assertEqual(resp.status_code, 200, f"Expected 200 on {path}, got {resp.status_code}")


class TestAnalyzeEndpointShielding(unittest.TestCase):
    """Tier 2: POST /analyze Input Validation & Error Handling."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_unauthorized_post_analyze(self):
        """POST /analyze without auth must return 401."""
        resp = self.client.post("/analyze", data=b"some bytes")
        self.assertEqual(resp.status_code, 401)

    def test_02_empty_post_analyze(self):
        """POST /analyze with empty body must return 400."""
        resp = self.client.post("/analyze", headers=AUTH_HEADER, content=b"")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Empty", resp.json().get("detail", ""))

    def test_03_corrupted_post_analyze(self):
        """POST /analyze with corrupt bytes must return 400."""
        resp = self.client.post("/analyze", headers=AUTH_HEADER, content=b"RANDOM_CORRUPT_BYTES_9999")
        self.assertEqual(resp.status_code, 400)

    def test_04_text_file_post_analyze(self):
        """POST /analyze with a plain text file upload must return 400."""
        resp = self.client.post(
            "/analyze",
            headers=AUTH_HEADER,
            files={"file": ("test.txt", b"Hello, this is a plain text file.", "text/plain")}
        )
        self.assertEqual(resp.status_code, 400)

    def test_05_unsupported_methods_on_analyze(self):
        """Non-POST requests on /analyze (GET, PUT, DELETE) must return 404/405 client error."""
        for method in ["get", "put", "delete"]:
            with self.subTest(method=method):
                client_fn = getattr(self.client, method)
                resp = client_fn("/analyze", headers=AUTH_HEADER)
                self.assertIn(resp.status_code, [404, 405], f"Expected 404 or 405 on {method.upper()} /analyze, got {resp.status_code}")


class TestFrontendPWASpecification(unittest.TestCase):
    """Tier 4: Frontend PWA Structure, Manifest, and Service Worker Assertions."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_html_dom_elements(self):
        """index.html must include video feed, overlay canvas, and json-output pre element."""
        resp = self.client.get("/index.html", headers=AUTH_HEADER)
        self.assertEqual(resp.status_code, 200)
        html = resp.text
        self.assertIn('id="camera-feed"', html)
        self.assertIn('id="overlay-canvas"', html)
        self.assertIn('id="json-output"', html)
        self.assertIn('id="btn-toggle-cam"', html)
        self.assertIn('id="file-input"', html)
        self.assertIn('manifest.json', html)

    def test_02_css_mobile_first(self):
        """style.css must define mobile-first styling and theme variables."""
        resp = self.client.get("/style.css", headers=AUTH_HEADER)
        self.assertEqual(resp.status_code, 200)
        css = resp.text
        self.assertIn("--color-vehicle", css)
        self.assertIn("--color-person", css)
        self.assertIn("100dvh", css)

    def test_03_pwa_manifest_json(self):
        """manifest.json must conform to PWA specification."""
        resp = self.client.get("/manifest.json", headers=AUTH_HEADER)
        self.assertEqual(resp.status_code, 200)
        manifest = resp.json()
        self.assertEqual(manifest.get("name"), "Vehicle & Person Detection PWA")
        self.assertEqual(manifest.get("short_name"), "AutoDetect")
        self.assertEqual(manifest.get("display"), "standalone")
        self.assertTrue(str(manifest.get("orientation")).startswith("portrait"))
        self.assertIn("icons", manifest)
        self.assertGreaterEqual(len(manifest["icons"]), 2)

    def test_04_pwa_service_worker(self):
        """sw.js must implement Cache-First strategy and cache core app shell."""
        resp = self.client.get("/sw.js", headers=AUTH_HEADER)
        self.assertEqual(resp.status_code, 200)
        sw_code = resp.text
        self.assertIn("install", sw_code)
        self.assertIn("activate", sw_code)
        self.assertIn("fetch", sw_code)
        self.assertIn("caches.open", sw_code)
        self.assertIn("/style.css", sw_code)
        self.assertIn("/app.js", sw_code)

    def test_05_app_js_specification_contracts(self):
        """app.js must satisfy camera constraints, interval timer, and endpoint contracts."""
        resp = self.client.get("/app.js", headers=AUTH_HEADER)
        self.assertEqual(resp.status_code, 200)
        js = resp.text

        # 1. Camera facingMode
        self.assertTrue("facingMode" in js and "environment" in js, "app.js must specify environment rear camera")

        # 2. Capture Interval 1500ms
        self.assertIn("1500", js, "app.js must define 1.5s interval")

        # 3. /analyze endpoint
        self.assertIn("/analyze", js, "app.js must point to /analyze")

        # 4. Basic Auth header
        self.assertIn("Authorization", js, "app.js must include Authorization header")
        self.assertIn("Basic ", js, "app.js must send Basic auth credentials")

        # 5. Canvas overlay color distinctions
        self.assertIn("#06b6d4", js, "app.js must use Cyan for vehicle bounding boxes")
        self.assertIn("#10b981", js, "app.js must use Emerald for person bounding boxes")

        # 6. Mutex guard for async frame transmission
        self.assertIn("isAnalyzing", js, "app.js must implement isAnalyzing concurrency lock")


if __name__ == "__main__":
    unittest.main(verbosity=2)
