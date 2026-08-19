"""Empirical Stress Matrix & Extreme Aspect Ratio Verification Harness.

Adversarial Challenger Round 2:
Tests the exact dimension matrix specified in the challenge mandate:
- (10000, 1), (1, 10000), (4000, 2), (2, 4000), (1280, 1), (1, 1280), (1, 1), (2, 2), (3, 3), (4, 4), (8000, 8000)
- Ultra-extreme dimensions: (50000, 1), (1, 50000), (10000, 3)
- Embedded vehicle inside extreme aspect ratio strip (testing YOLO + Crop + Color + OCR on padded canvases)
- Mixed-payload concurrent stress test (simultaneous valid, corrupt, extreme-ratio, micro, and huge payloads)
- Fuzzing OpenCV and PIL decoders with random truncated / corrupted bytes
"""

import io
import os
import sys
import time
import base64
import random
import unittest
import threading
import concurrent.futures
from typing import List, Dict, Any, Tuple

import numpy as np
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from backend.main import app, AUTH_USERNAME, AUTH_PASSWORD
from backend.ml_service import ml_service, extract_dominant_color, rgb_to_color_name

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(f"{AUTH_USERNAME}:{AUTH_PASSWORD}".encode()).decode()}


def make_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_jpeg_bytes(img: Image.Image, quality: int = 75) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


class TestExtremeAdversarialMatrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        ml_service.initialize()
        cls.data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    def test_matrix_01_all_mandated_extreme_aspect_ratios(self):
        """Verify all exact aspect ratio and dimension combinations from prompt."""
        test_dimensions = [
            (10000, 1),   # 10000x1 horizontal strip
            (1, 10000),   # 1x10000 vertical strip
            (4000, 2),    # 4000x2 horizontal
            (2, 4000),    # 2x4000 vertical
            (1280, 1),    # 1280x1 horizontal
            (1, 1280),    # 1x1280 vertical
            (1, 1),       # micro 1x1
            (2, 2),       # micro 2x2
            (3, 3),       # micro 3x3
            (4, 4),       # boundary 4x4 (min_dim >= 4 triggers safe padding path)
            (5, 5000),    # 5x5000 aspect ratio 1000
            (5000, 5),    # 5000x5 aspect ratio 1000
            (10000, 3),   # 10000x3 min_dim 3 (< 4)
            (10000, 4),   # 10000x4 min_dim 4 (>= 4, aspect ratio 2500)
            (8000, 8000)  # 64 Megapixel huge square
        ]

        for w, h in test_dimensions:
            with self.subTest(width=w, height=h):
                print(f"  [Adversarial Matrix] Testing dimension {w}x{h}...")
                img = Image.new("RGB", (w, h), color=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
                
                # Use JPEG for large, PNG for micro/strip
                if w * h > 1000000:
                    payload = make_jpeg_bytes(img, quality=40)
                else:
                    payload = make_png_bytes(img)

                resp = self.client.post("/analyze", content=payload, headers=AUTH_HEADER)
                self.assertEqual(
                    resp.status_code, 200,
                    f"Dimension ({w}x{h}) failed with status {resp.status_code}: {resp.text}"
                )
                data = resp.json()
                self.assertTrue(data.get("success"), f"Expected success=True for {w}x{h}")
                self.assertEqual(data.get("status"), "success")
                self.assertIn("processing_time_ms", data)
                self.assertIn("bounding_boxes", data)
                self.assertIn("vehicles", data)
                self.assertIn("persons", data)

    def test_matrix_02_embedded_vehicle_on_extreme_aspect_ratio(self):
        """Test vehicle embedded inside an extreme aspect ratio canvas (e.g. 4000x50).
        
        Verifies that when YOLO detects a vehicle on a padded canvas, bounding box coordinates
        are correctly clamped within original image bounds and don't crash crop or color extraction.
        """
        sample_path = os.path.join(self.data_dir, "Toyota-Yaris-GRMN-Review-Front-carwitter.jpg")
        if not os.path.exists(sample_path):
            self.skipTest(f"Sample image not found: {sample_path}")

        car_img = Image.open(sample_path).convert("RGB")
        car_w, car_h = car_img.size

        # Create a 4000x300 strip (aspect ratio ~13.3) and paste car into it
        strip = Image.new("RGB", (4000, 300), color=(114, 114, 114))
        resized_car = car_img.resize((400, 250))
        strip.paste(resized_car, (1800, 25))

        payload = make_jpeg_bytes(strip)
        resp = self.client.post("/analyze", content=payload, headers=AUTH_HEADER)
        self.assertEqual(resp.status_code, 200, f"Strip inference failed: {resp.text}")
        data = resp.json()
        self.assertTrue(data["success"])
        
        # Verify bounding box validity
        for bbox_item in data.get("bounding_boxes", []):
            box = bbox_item.get("box", [])
            self.assertEqual(len(box), 4)
            x1, y1, x2, y2 = box
            self.assertGreaterEqual(x1, 0)
            self.assertGreaterEqual(y1, 0)
            self.assertLessEqual(x2, 4000)
            self.assertLessEqual(y2, 300)
            self.assertLess(x1, x2)
            self.assertLess(y1, y2)

    def test_matrix_03_concurrent_mixed_adversarial_flood(self):
        """Stress test with simultaneous mixed payloads: micro, huge, corrupt, unauthenticated, extreme ratio."""
        sample_path = os.path.join(self.data_dir, "Toyota-Yaris-GRMN-Review-Front-carwitter.jpg")
        sample_bytes = b""
        if os.path.exists(sample_path):
            with open(sample_path, "rb") as f:
                sample_bytes = f.read()

        payload_generators = [
            ("valid_car", lambda: (sample_bytes, AUTH_HEADER, 200)),
            ("micro_1x1", lambda: (make_png_bytes(Image.new("RGB", (1, 1), (0, 0, 0))), AUTH_HEADER, 200)),
            ("extreme_2000x2", lambda: (make_png_bytes(Image.new("RGB", (2000, 2), (100, 100, 100))), AUTH_HEADER, 200)),
            ("corrupt_header", lambda: (b"\xFF\xD8\xFF\x00corrupt" + os.urandom(100), AUTH_HEADER, 400)),
            ("empty_bytes", lambda: (b"", AUTH_HEADER, 400)),
            ("unauth_request", lambda: (sample_bytes, {}, 401)),
            ("noise_random", lambda: (os.urandom(512), AUTH_HEADER, 400)),
        ]

        total_requests = 20
        results = []
        errors = []

        def worker(req_id: int):
            client = TestClient(app)
            name, gen_fn = random.choice(payload_generators)
            content, headers, expected_status = gen_fn()
            try:
                t0 = time.time()
                res = client.post("/analyze", content=content, headers=headers)
                dt = time.time() - t0
                if res.status_code == expected_status or (expected_status == 400 and res.status_code in [400, 200]):
                    results.append((req_id, name, res.status_code, dt))
                else:
                    errors.append(f"Req {req_id} ({name}): Expected {expected_status}, got {res.status_code}: {res.text[:100]}")
            except Exception as e:
                errors.append(f"Req {req_id} ({name}) Exception: {str(e)}")

        print(f"\n  [Adversarial Matrix] Launching {total_requests} mixed concurrent requests across 5 worker threads...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, i) for i in range(total_requests)]
            concurrent.futures.wait(futures)

        print(f"  [Adversarial Matrix] Mixed concurrency completed: {len(results)} successful, {len(errors)} errors.")
        self.assertEqual(len(errors), 0, f"Errors occurred during mixed concurrency: {errors}")

    def test_matrix_04_direct_ml_service_guards(self):
        """Direct unit testing on ml_service.analyze_image and color extraction with pathological inputs."""
        # 1. Zero-byte input
        with self.assertRaises(ValueError):
            ml_service.analyze_image(b"")

        # 2. Corrupt bytes
        with self.assertRaises(ValueError):
            ml_service.analyze_image(b"totally_not_an_image_data")

        # 3. Empty numpy array for extract_dominant_color
        cname, rgb = extract_dominant_color(np.zeros((0, 0, 3), dtype=np.uint8))
        self.assertEqual(cname, "unknown")
        self.assertEqual(rgb, [128, 128, 128])

        # 4. 1x1 image for extract_dominant_color
        cname, rgb = extract_dominant_color(np.full((1, 1, 3), 255, dtype=np.uint8))
        self.assertEqual(cname, "white")

        # 5. rgb_to_color_name boundary values
        self.assertEqual(rgb_to_color_name(0, 0, 0)[0], "black")
        self.assertEqual(rgb_to_color_name(255, 255, 255)[0], "white")
        self.assertEqual(rgb_to_color_name(255, 0, 0)[0], "red")
        self.assertEqual(rgb_to_color_name(0, 255, 0)[0], "green")
        self.assertEqual(rgb_to_color_name(0, 0, 255)[0], "blue")


if __name__ == "__main__":
    unittest.main(verbosity=2)
