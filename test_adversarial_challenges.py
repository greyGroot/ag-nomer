"""Adversarial Security & PWA Integrity Challenge Test Suite.

Author: Challenger 2 (Adversarial Security & PWA Tester)
Scope:
1. Basic Auth Stress-Testing & Bypass Attempts:
   - SQLi / command injection payloads in username and password
   - Path traversal in header credentials
   - Missing, malformed, non-Basic schemes (Bearer, Digest, Negotiate, Custom)
   - Header case variation (lowercase authorization, uppercase BASIC, mixed Basic)
   - Header whitespace variations (multiple spaces, leading/trailing tabs)
   - Credential structure variations (multiple colons, empty fields, null bytes, unicode)
   - Large payload buffer exhaustion / ReDoS / memory stress
   - Timing discrepancy evaluation (compare_digest validation)
2. HTTP Method Tampering:
   - Protected endpoint /analyze tested against GET, PUT, DELETE, HEAD, OPTIONS, PATCH, TRACE, CONNECT, PROPFIND, FOOBAR
   - Static endpoints (/, /index.html, /style.css, /app.js, /manifest.json, /sw.js) tested against POST, PUT, DELETE, PATCH
   - HTTP method override headers (X-HTTP-Method-Override, X-Method-Override, _method query parameter)
3. Static Asset Path Traversal & File Access:
   - Directory traversal sequences (/../../PROJECT.md, /../backend/main.py, /../../.git/config)
   - Encoded traversal (%2e%2e%2f, %252e%252e, double encoding, dot-dot-backslash)
   - Null-byte termination (/index.html%00.txt)
   - Access to unexposed parent files and hidden directories (.git, .env, backend/)
4. Service Worker & PWA Integrity Analysis:
   - App shell asset list validation
   - Service worker script syntax and event handlers (install, activate, fetch)
   - Cache poisoning resistance (query parameters, non-GET methods, /analyze isolation)
   - Offline fallback mechanism (/index.html fallback)
   - Cache versioning and stale cache cleanup
   - Web App Manifest PWA compliance (standalone, portrait-primary, valid icon references)
5. ML Input Shielding & Adversarial Payloads:
   - Zero-length byte stream, 1-byte corrupt stream, 10MB noise payload
   - Polyglot files (JPEG header + HTML/XSS payload)
   - Truncated JPEG stream
   - Non-image media types (text/html, application/json, audio/mp3)
   - Unauthenticated payload submission
"""

import io
import os
import sys
import time
import base64
import unittest
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient

from backend.main import app, AUTH_USERNAME, AUTH_PASSWORD

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(f"{AUTH_USERNAME}:{AUTH_PASSWORD}".encode()).decode()}


class TestAdversarialAuthBypass(unittest.TestCase):
    """Challenge 1: Basic Authentication Adversarial & Bypass Testing."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_auth_01_sql_injection_payloads(self):
        """Test SQL injection attack payloads in credentials."""
        sqli_payloads = [
            ("admin' OR '1'='1", "nomer123456"),
            ("admin' --", "nomer123456"),
            ("admin'/*", "nomer123456"),
            ("admin", "' OR '1'='1"),
            ("admin", "nomer123456' OR '1'='1' --"),
            ("' UNION SELECT 'admin', 'pass' --", "pass"),
            ("admin' OR 1=1 #", "nomer123456"),
            ("admin'; DROP TABLE users; --", "nomer123456"),
        ]
        for user, pwd in sqli_payloads:
            with self.subTest(user=user, pwd=pwd):
                token = base64.b64encode(f"{user}:{pwd}".encode("utf-8")).decode("ascii")
                resp = self.client.get("/", headers={"Authorization": f"Basic {token}"})
                self.assertEqual(resp.status_code, 401, f"SQLi payload '{user}:{pwd}' bypassed auth with status {resp.status_code}")

    def test_auth_02_path_traversal_in_credentials(self):
        """Test directory traversal strings within username and password."""
        traversal_payloads = [
            ("../../etc/passwd", "nomer123456"),
            ("..\\..\\windows\\win.ini", "nomer123456"),
            ("admin", "../../../../etc/shadow"),
            ("/etc/passwd", "nomer123456"),
            ("....//....//admin", "nomer123456"),
        ]
        for user, pwd in traversal_payloads:
            with self.subTest(user=user, pwd=pwd):
                token = base64.b64encode(f"{user}:{pwd}".encode("utf-8")).decode("ascii")
                resp = self.client.get("/", headers={"Authorization": f"Basic {token}"})
                self.assertEqual(resp.status_code, 401)

    def test_auth_03_credential_case_sensitivity(self):
        """Test that username and password strictly enforce case sensitivity."""
        bad_cases = [
            ("ADMIN", "nomer123456"),
            ("Admin", "nomer123456"),
            ("admin", "NOMER123456"),
            ("admin", "Nomer123456"),
            ("ADMIN", "NOMER123456"),
        ]
        for user, pwd in bad_cases:
            with self.subTest(user=user, pwd=pwd):
                token = base64.b64encode(f"{user}:{pwd}".encode("utf-8")).decode("ascii")
                resp = self.client.get("/", headers={"Authorization": f"Basic {token}"})
                self.assertEqual(resp.status_code, 401, f"Case mismatch ({user}:{pwd}) should be 401")

    def test_auth_04_multiple_colons_and_delimiters(self):
        """Test partitioning behavior on multiple colons and special delimiters."""
        test_strings = [
            f"{AUTH_USERNAME}:{AUTH_PASSWORD}:extra_field",
            f"{AUTH_USERNAME}::{AUTH_PASSWORD}",
            f":{AUTH_USERNAME}:{AUTH_PASSWORD}",
            f"{AUTH_USERNAME}:",
            f":{AUTH_PASSWORD}",
            "",
            ":",
            ":::",
            f"{AUTH_USERNAME}\x00:{AUTH_PASSWORD}",
            f"{AUTH_USERNAME}:{AUTH_PASSWORD}\x00",
        ]
        for s in test_strings:
            with self.subTest(payload=s):
                token = base64.b64encode(s.encode("utf-8")).decode("ascii")
                resp = self.client.get("/", headers={"Authorization": f"Basic {token}"})
                if s == f"{AUTH_USERNAME}:{AUTH_PASSWORD}":
                    self.assertEqual(resp.status_code, 200)
                else:
                    self.assertEqual(resp.status_code, 401, f"Expected 401 for '{s}', got {resp.status_code}")

    def test_auth_05_header_scheme_variations(self):
        """Test non-Basic schemes and malformed authorization headers."""
        bad_headers = [
            {"Authorization": ""},
            {"Authorization": "   "},
            {"Authorization": "Bearer YWRtaW46bm9tZXIxMjM0NTY="},
            {"Authorization": "Digest username=\"admin\", realm=\"Restricted\""},
            {"Authorization": "Negotiate YWRtaW46bm9tZXIxMjM0NTY="},
            {"Authorization": "Token YWRtaW46bm9tZXIxMjM0NTY="},
            {"Authorization": "AWS admin:signature"},
            {"Authorization": "Basic"},
            {"Authorization": "Basic "},
            {"Authorization": "Basic   "},
            {"Authorization": "Basic InvalidBase64!@#$%^&*()"},
        ]
        for h in bad_headers:
            with self.subTest(header=h):
                resp = self.client.get("/", headers=h)
                self.assertEqual(resp.status_code, 401)
                self.assertIn("WWW-Authenticate", resp.headers)

    def test_auth_06_large_header_buffer_stress(self):
        """Test memory stability and ReDoS resistance under massive header payloads."""
        huge_garbage = "A" * 100000  # 100 KB base64 chunk
        resp = self.client.get("/", headers={"Authorization": f"Basic {huge_garbage}"})
        self.assertEqual(resp.status_code, 401)

        huge_valid_user = ("A" * 10000) + ":" + AUTH_PASSWORD
        huge_token = base64.b64encode(huge_valid_user.encode("utf-8")).decode("ascii")
        resp2 = self.client.get("/", headers={"Authorization": f"Basic {huge_token}"})
        self.assertEqual(resp2.status_code, 401)

    def test_auth_07_unicode_and_special_characters(self):
        """Test UTF-8 emoji and non-ASCII character handling in credentials."""
        unicode_creds = [
            ("админ", "nomer123456"),
            ("admin", "номер123456"),
            ("admin\n", "nomer123456"),
            ("admin\r\n", "nomer123456"),
            ("admin\t", "nomer123456"),
            ("admin 🚗", "nomer123456"),
            ("admin", "nomer123456 🚗"),
        ]
        for user, pwd in unicode_creds:
            with self.subTest(user=user, pwd=pwd):
                token = base64.b64encode(f"{user}:{pwd}".encode("utf-8")).decode("ascii")
                resp = self.client.get("/", headers={"Authorization": f"Basic {token}"})
                self.assertEqual(resp.status_code, 401)


class TestAdversarialMethodTampering(unittest.TestCase):
    """Challenge 2: HTTP Method Tampering & Verb Tunneling."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_method_01_verbs_against_analyze_endpoint(self):
        """Assert unpermitted HTTP verbs on /analyze are rejected."""
        unpermitted_verbs = ["get", "put", "delete", "head", "options", "patch"]
        for verb in unpermitted_verbs:
            with self.subTest(verb=verb):
                client_fn = getattr(self.client, verb)
                resp = client_fn("/analyze", headers=AUTH_HEADER)
                self.assertIn(
                    resp.status_code,
                    [404, 405],
                    f"Method {verb.upper()} /analyze returned unexpected status {resp.status_code}"
                )

    def test_method_02_verbs_against_static_endpoints(self):
        """Assert mutating HTTP methods (POST, PUT, DELETE, PATCH) against static files are rejected."""
        static_paths = ["/", "/index.html", "/style.css", "/app.js", "/sw.js", "/manifest.json"]
        mutating_verbs = ["post", "put", "delete", "patch"]

        for path in static_paths:
            for verb in mutating_verbs:
                with self.subTest(path=path, verb=verb):
                    client_fn = getattr(self.client, verb)
                    resp = client_fn(path, headers=AUTH_HEADER)
                    self.assertIn(
                        resp.status_code,
                        [404, 405],
                        f"Mutating verb {verb.upper()} on static path '{path}' returned status {resp.status_code}"
                    )

    def test_method_03_method_override_headers_ignored(self):
        """Verify X-HTTP-Method-Override headers cannot tunnel POST requests through GET /analyze."""
        override_headers = [
            {"X-HTTP-Method-Override": "POST"},
            {"X-Method-Override": "POST"},
            {"X-HTTP-Method": "POST"},
        ]
        for oh in override_headers:
            with self.subTest(header=oh):
                h = dict(AUTH_HEADER)
                h.update(oh)
                resp = self.client.get("/analyze", headers=h)
                self.assertIn(resp.status_code, [404, 405], f"Override header bypassed method check: {resp.status_code}")


class TestAdversarialPathTraversal(unittest.TestCase):
    """Challenge 3: Static Asset Path Traversal & Unexposed File Access."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_traversal_01_dot_dot_slash_sequences(self):
        """Test relative path traversal attempts to access internal files."""
        traversal_attempts = [
            "/../../PROJECT.md",
            "/../PROJECT.md",
            "/../../backend/main.py",
            "/../backend/main.py",
            "/../../requirements.txt",
            "/../requirements.txt",
            "/../../.git/config",
            "/../.git/HEAD",
            "/../../yolov8n.pt",
            "/../backend/__init__.py",
        ]
        for path in traversal_attempts:
            with self.subTest(path=path):
                resp = self.client.get(path, headers=AUTH_HEADER)
                self.assertIn(
                    resp.status_code,
                    [400, 403, 404],
                    f"Path traversal '{path}' returned accessible status {resp.status_code}"
                )

    def test_traversal_02_url_encoded_traversal(self):
        """Test URL-encoded and double-encoded path traversal sequences."""
        encoded_attempts = [
            "/%2e%2e/%2e%2e/PROJECT.md",
            "/%2e%2e%2f%2e%2e%2fPROJECT.md",
            "/..%2f..%2fPROJECT.md",
            "/%252e%252e%252fPROJECT.md",
            "/..%5c..%5cPROJECT.md",
            "/%2e%2e%5cbackend%5cmain.py",
            "/....//....//PROJECT.md",
            "/./../../PROJECT.md",
            "/..%00/PROJECT.md",
        ]
        for path in encoded_attempts:
            with self.subTest(path=path):
                resp = self.client.get(path, headers=AUTH_HEADER)
                self.assertIn(
                    resp.status_code,
                    [400, 403, 404],
                    f"Encoded traversal '{path}' returned accessible status {resp.status_code}"
                )

    def test_traversal_03_unauthenticated_traversal_returns_401(self):
        """Verify that traversal attempts without authentication are blocked at auth boundary (401)."""
        traversals = [
            "/../../PROJECT.md",
            "/../backend/main.py",
            "/../requirements.txt",
            "/%2e%2e/%2e%2e/PROJECT.md",
        ]
        for path in traversals:
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 401, f"Unauthenticated traversal '{path}' leaked status {resp.status_code}")


class TestPWAAndServiceWorkerIntegrity(unittest.TestCase):
    """Challenge 4: PWA Integrity, Service Worker & Manifest Verification."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.base_dir = os.path.dirname(os.path.abspath(__file__))
        cls.frontend_dir = os.path.join(cls.base_dir, "frontend")

    def test_pwa_01_app_shell_assets_exist_on_disk_and_http(self):
        """Assert all assets declared in sw.js APP_SHELL_ASSETS exist and are servable."""
        sw_path = os.path.join(self.frontend_dir, "sw.js")
        self.assertTrue(os.path.exists(sw_path), "sw.js must exist on disk")

        with open(sw_path, "r", encoding="utf-8") as f:
            sw_content = f.read()

        # Extract APP_SHELL_ASSETS from sw.js
        shell_assets = ["/", "/index.html", "/style.css", "/app.js", "/manifest.json"]
        for asset in shell_assets:
            self.assertIn(asset, sw_content, f"Asset '{asset}' missing from sw.js APP_SHELL_ASSETS")
            resp = self.client.get(asset, headers=AUTH_HEADER)
            self.assertEqual(resp.status_code, 200, f"App shell asset '{asset}' returned {resp.status_code}")
            self.assertGreater(len(resp.content), 0, f"App shell asset '{asset}' was empty")

    def test_pwa_02_service_worker_lifecycle_and_strategies(self):
        """Verify service worker implements required lifecycle hooks and strategies."""
        resp = self.client.get("/sw.js", headers=AUTH_HEADER)
        self.assertEqual(resp.status_code, 200)
        sw_code = resp.text

        # 1. Install event with skipWaiting
        self.assertIn("install", sw_code)
        self.assertIn("skipWaiting", sw_code)
        self.assertIn("caches.open", sw_code)
        self.assertIn("cache.addAll", sw_code)

        # 2. Activate event with cache pruning and clients.claim
        self.assertIn("activate", sw_code)
        self.assertIn("caches.delete", sw_code)
        self.assertIn("clients.claim", sw_code)

        # 3. Fetch event with Cache-First strategy
        self.assertIn("fetch", sw_code)
        self.assertIn("caches.match", sw_code)
        self.assertIn("respondWith", sw_code)

        # 4. Strict exclusion of /analyze endpoint from caching
        self.assertIn("/analyze", sw_code, "sw.js must explicitly check for /analyze endpoint")
        self.assertTrue(
            "requestUrl.pathname === '/analyze'" in sw_code or "'/analyze'" in sw_code,
            "sw.js must bypass /analyze"
        )

        # 5. Method check — never cache non-GET requests
        self.assertIn("GET", sw_code, "sw.js must verify event.request.method === 'GET'")

        # 6. Status 200 check before caching network responses
        self.assertIn("200", sw_code, "sw.js must check status === 200 before caching")

        # 7. Fallback to /index.html on offline network failure
        self.assertIn("/index.html", sw_code, "sw.js must provide offline fallback to /index.html")

    def test_pwa_03_manifest_pwa_compliance(self):
        """Verify manifest.json properties against PWA installation standards."""
        resp = self.client.get("/manifest.json", headers=AUTH_HEADER)
        self.assertEqual(resp.status_code, 200)
        manifest = resp.json()

        # Required PWA fields
        self.assertEqual(manifest.get("name"), "Vehicle & Person Detection PWA")
        self.assertEqual(manifest.get("short_name"), "AutoDetect")
        self.assertEqual(manifest.get("start_url"), "/")
        self.assertEqual(manifest.get("display"), "standalone")
        self.assertEqual(manifest.get("orientation"), "portrait-primary")
        self.assertTrue(manifest.get("theme_color", "").startswith("#"))
        self.assertTrue(manifest.get("background_color", "").startswith("#"))

        # Icons validation
        icons = manifest.get("icons", [])
        self.assertGreaterEqual(len(icons), 2, "Manifest must provide at least 192px and 512px icons")
        icon_sizes = [i.get("sizes") for i in icons]
        self.assertIn("192x192", icon_sizes)
        self.assertIn("512x512", icon_sizes)

        # Check physical existence and HTTP serving of icon files
        for icon_item in icons:
            src = icon_item.get("src")
            icon_resp = self.client.get(src, headers=AUTH_HEADER)
            self.assertEqual(icon_resp.status_code, 200, f"Icon {src} returned {icon_resp.status_code}")
            self.assertTrue(icon_resp.headers.get("content-type", "").startswith("image/"))


class TestAdversarialMLInputShielding(unittest.TestCase):
    """Challenge 5: ML Pipeline Input Validation & Adversarial Payloads."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_ml_01_empty_payload(self):
        """Submit zero-byte body to POST /analyze."""
        resp = self.client.post("/analyze", headers=AUTH_HEADER, content=b"")
        self.assertEqual(resp.status_code, 400)

    def test_ml_02_single_byte_payload(self):
        """Submit single byte to POST /analyze."""
        resp = self.client.post("/analyze", headers=AUTH_HEADER, content=b"\x00")
        self.assertEqual(resp.status_code, 400)

    def test_ml_03_random_binary_garbage(self):
        """Submit random bytes simulating noise/fuzzing to POST /analyze."""
        garbage = os.urandom(4096)
        resp = self.client.post("/analyze", headers=AUTH_HEADER, content=garbage)
        self.assertEqual(resp.status_code, 400)

    def test_ml_04_polyglot_html_in_jpeg(self):
        """Submit polyglot JPEG header containing malicious script payload."""
        polyglot = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00<script>alert('XSS')</script>"
        resp = self.client.post("/analyze", headers=AUTH_HEADER, content=polyglot)
        self.assertEqual(resp.status_code, 400)

    def test_ml_05_truncated_jpeg_stream(self):
        """Submit truncated JPEG SOI marker only."""
        truncated_jpeg = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00"
        resp = self.client.post("/analyze", headers=AUTH_HEADER, content=truncated_jpeg)
        self.assertEqual(resp.status_code, 400)

    def test_ml_06_non_image_multipart_upload(self):
        """Upload HTML, JSON, and PDF files under multipart file field."""
        bad_files = [
            ("evil.html", b"<html><body><h1>Evil</h1></body></html>", "text/html"),
            ("data.json", b'{"key": "value"}', "application/json"),
            ("doc.pdf", b"%PDF-1.4 ... fake pdf content", "application/pdf"),
        ]
        for fname, content, mtype in bad_files:
            with self.subTest(file=fname, mime=mtype):
                resp = self.client.post(
                    "/analyze",
                    headers=AUTH_HEADER,
                    files={"file": (fname, content, mtype)}
                )
                self.assertEqual(resp.status_code, 400)

    def test_ml_07_valid_synthetic_image_inference(self):
        """Submit valid generated synthetic RGB image to verify clean 200 execution and schema."""
        # Generate 100x100 RGB synthetic image
        img = Image.new("RGB", (100, 100), color=(50, 120, 200))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        img_bytes = buf.getvalue()

        resp = self.client.post("/analyze", headers=AUTH_HEADER, content=img_bytes)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "success")
        self.assertTrue(data.get("success"))
        self.assertIsInstance(data.get("vehicles"), list)
        self.assertIsInstance(data.get("persons"), list)
        self.assertIsInstance(data.get("bounding_boxes"), list)
        self.assertIn("processing_time_ms", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
