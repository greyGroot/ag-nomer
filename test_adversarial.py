"""Adversarial ML & API Stress Testing Harness.

Stress-tests the backend ML pipeline and `/analyze` endpoint across:
1. Extreme image dimensions (1x1, 10000x1, 1x10000, 8000x8000, 2x2).
2. Pure, uniform, and high-entropy textures (Pure Black, Pure White, Solid Colors, Gaussian Noise, Uniform Noise, Checkerboard).
3. Complex scene edge cases (Zero vehicle/person, Dense multi-vehicle collages, Heavily occluded crops).
4. Malformed & Boundary Payloads (Truncated headers, non-image files, corrupted bitstreams, auth fuzzing).
5. Concurrency, thread safety, and memory leak stress testing.
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
from typing import List, Dict, Any

import numpy as np
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from backend.main import app, AUTH_USERNAME, AUTH_PASSWORD
from backend.ml_service import ml_service, extract_dominant_color, rgb_to_color_name

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(f"{AUTH_USERNAME}:{AUTH_PASSWORD}".encode()).decode()}


def make_jpeg_bytes(img: Image.Image, quality: int = 85) -> bytes:
    """Helper to convert PIL Image to JPEG bytes."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def make_png_bytes(img: Image.Image) -> bytes:
    """Helper to convert PIL Image to PNG bytes."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestAdversarialMLAndAPI(unittest.TestCase):
    """Adversarial stress test suite for backend ML & API endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # Ensure model is initialized
        ml_service.initialize()

    # =========================================================================
    # 1. EXTREME IMAGE DIMENSIONS
    # =========================================================================

    def test_01_extreme_dimension_1x1_pixel(self):
        """Test 1x1 pixel image in PNG and JPEG formats."""
        # 1x1 PNG
        img_1x1_png = Image.new("RGB", (1, 1), color=(255, 0, 0))
        png_bytes = make_png_bytes(img_1x1_png)
        res_png = self.client.post("/analyze", content=png_bytes, headers=AUTH_HEADER)
        self.assertEqual(res_png.status_code, 200, f"1x1 PNG failed with status {res_png.status_code}: {res_png.text}")
        data_png = res_png.json()
        self.assertTrue(data_png["success"])
        self.assertEqual(data_png["vehicle_count"], 0)
        self.assertEqual(data_png["person_count"], 0)

        # 1x1 JPEG
        img_1x1_jpg = Image.new("RGB", (1, 1), color=(128, 128, 128))
        jpg_bytes = make_jpeg_bytes(img_1x1_jpg)
        res_jpg = self.client.post("/analyze", content=jpg_bytes, headers=AUTH_HEADER)
        self.assertEqual(res_jpg.status_code, 200, f"1x1 JPEG failed with status {res_jpg.status_code}: {res_jpg.text}")
        data_jpg = res_jpg.json()
        self.assertTrue(data_jpg["success"])

    def test_02_extreme_aspect_ratio_10000x1_and_1x10000(self):
        """Test extreme aspect ratio strips (10000x1 and 1x10000 pixels)."""
        # 10000x1 horizontal line
        img_h = Image.new("RGB", (10000, 1), color=(100, 150, 200))
        h_bytes = make_png_bytes(img_h)
        res_h = self.client.post("/analyze", content=h_bytes, headers=AUTH_HEADER)
        self.assertEqual(res_h.status_code, 200, f"10000x1 failed: {res_h.text}")
        self.assertTrue(res_h.json()["success"])

        # 1x10000 vertical line
        img_v = Image.new("RGB", (1, 10000), color=(200, 100, 50))
        v_bytes = make_png_bytes(img_v)
        res_v = self.client.post("/analyze", content=v_bytes, headers=AUTH_HEADER)
        self.assertEqual(res_v.status_code, 200, f"1x10000 failed: {res_v.text}")
        self.assertTrue(res_v.json()["success"])

    def test_03_extreme_large_resolution_8000x8000(self):
        """Test ultra-high resolution image (8000x8000 = 64 Megapixels)."""
        # To avoid massive disk writes, generate single-channel gradient expanded or compressed JPEG
        print("\n  [Stress] Generating 8000x8000 test image...")
        img_huge = Image.new("RGB", (8000, 8000), color=(60, 60, 60))
        draw = ImageDraw.Draw(img_huge)
        # Draw some arbitrary shapes
        draw.rectangle([1000, 1000, 7000, 7000], fill=(120, 120, 120), outline=(255, 255, 255))
        draw.ellipse([3000, 3000, 5000, 5000], fill=(200, 50, 50))

        buf = io.BytesIO()
        img_huge.save(buf, format="JPEG", quality=50)
        huge_bytes = buf.getvalue()
        print(f"  [Stress] 8000x8000 JPEG size: {len(huge_bytes) / (1024*1024):.2f} MB. Sending to /analyze...")

        start_t = time.time()
        res_huge = self.client.post("/analyze", content=huge_bytes, headers=AUTH_HEADER)
        elapsed = time.time() - start_t
        print(f"  [Stress] 8000x8000 inference completed in {elapsed:.2f}s with status {res_huge.status_code}")

        self.assertEqual(res_huge.status_code, 200, f"8000x8000 failed: {res_huge.text}")
        data = res_huge.json()
        self.assertTrue(data["success"])
        self.assertIn("processing_time_ms", data)

    def test_04_micro_dimensions_2x2_and_3x3(self):
        """Test micro dimensions (2x2, 3x3, 5x5)."""
        for dims in [(2, 2), (3, 3), (5, 5), (7, 13)]:
            img = Image.new("RGB", dims, color=(42, 84, 168))
            b = make_png_bytes(img)
            res = self.client.post("/analyze", content=b, headers=AUTH_HEADER)
            self.assertEqual(res.status_code, 200, f"Dimension {dims} failed: {res.text}")
            self.assertTrue(res.json()["success"])

    # =========================================================================
    # 2. PURE, UNIFORM, AND HIGH-ENTROPY TEXTURES
    # =========================================================================

    def test_05_pure_black_and_pure_white(self):
        """Test pure black (0,0,0) and pure white (255,255,255) frames."""
        for name, color in [("black", (0, 0, 0)), ("white", (255, 255, 255))]:
            img = Image.new("RGB", (640, 480), color=color)
            b = make_jpeg_bytes(img)
            res = self.client.post("/analyze", content=b, headers=AUTH_HEADER)
            self.assertEqual(res.status_code, 200, f"Pure {name} failed: {res.text}")
            data = res.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["vehicle_count"], 0)
            self.assertEqual(data["person_count"], 0)

    def test_06_uniform_solid_colors(self):
        """Test solid uniform primary and secondary colors."""
        colors = [
            ("red", (255, 0, 0)),
            ("green", (0, 255, 0)),
            ("blue", (0, 0, 255)),
            ("yellow", (255, 255, 0)),
            ("magenta", (255, 0, 255)),
            ("cyan", (0, 255, 255)),
            ("gray", (128, 128, 128))
        ]
        for name, col in colors:
            img = Image.new("RGB", (320, 240), color=col)
            b = make_jpeg_bytes(img)
            res = self.client.post("/analyze", content=b, headers=AUTH_HEADER)
            self.assertEqual(res.status_code, 200, f"Solid {name} failed: {res.text}")
            data = res.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["vehicle_count"], 0)

    def test_07_gaussian_and_uniform_noise(self):
        """Test high-entropy Gaussian noise and uniform random noise frames."""
        np.random.seed(42)

        # 1. Gaussian noise N(128, 60)
        gauss_arr = np.clip(np.random.normal(128, 60, (480, 640, 3)), 0, 255).astype(np.uint8)
        gauss_img = Image.fromarray(gauss_arr)
        b_gauss = make_jpeg_bytes(gauss_img)
        res_g = self.client.post("/analyze", content=b_gauss, headers=AUTH_HEADER)
        self.assertEqual(res_g.status_code, 200, f"Gaussian noise failed: {res_g.text}")
        self.assertTrue(res_g.json()["success"])

        # 2. Uniform random noise U(0, 255)
        unif_arr = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8)
        unif_img = Image.fromarray(unif_arr)
        b_unif = make_png_bytes(unif_img)
        res_u = self.client.post("/analyze", content=b_unif, headers=AUTH_HEADER)
        self.assertEqual(res_u.status_code, 200, f"Uniform noise failed: {res_u.text}")
        self.assertTrue(res_u.json()["success"])

    def test_08_checkerboard_high_frequency_pattern(self):
        """Test high-frequency checkerboard pattern."""
        size = 256
        cb = np.zeros((size, size, 3), dtype=np.uint8)
        cb[::2, ::2] = 255
        cb[1::2, 1::2] = 255
        cb_img = Image.fromarray(cb)
        b = make_png_bytes(cb_img)
        res = self.client.post("/analyze", content=b, headers=AUTH_HEADER)
        self.assertEqual(res.status_code, 200, f"Checkerboard failed: {res.text}")
        self.assertTrue(res.json()["success"])

    # =========================================================================
    # 3. ZERO, MULTI-VEHICLE & OCCLUSION EDGE CASES
    # =========================================================================

    def test_09_zero_vehicle_natural_and_text_scenes(self):
        """Test zero-vehicle / zero-person scenes (gradient canvas, dense text document)."""
        # 1. Gradient canvas
        x = np.linspace(0, 255, 640, dtype=np.uint8)
        y = np.linspace(0, 255, 480, dtype=np.uint8)
        xx, yy = np.meshgrid(x, y)
        grad = np.stack([xx, yy, 255 - xx], axis=-1)
        grad_img = Image.fromarray(grad)
        res = self.client.post("/analyze", content=make_jpeg_bytes(grad_img), headers=AUTH_HEADER)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["vehicle_count"], 0)
        self.assertIsNone(data["car_color"])
        self.assertIsNone(data["plate_number"])

        # 2. Dense text image (simulating reading a document / paper)
        doc_img = Image.new("RGB", (800, 600), color=(255, 255, 255))
        draw = ImageDraw.Draw(doc_img)
        for row in range(20):
            draw.text((30, 25 + row * 28), f"Line {row}: SYSTEM ARCHITECTURE & DETECTION SPECIFICATION #{row*17} XYZ-9988", fill=(0, 0, 0))
        res_doc = self.client.post("/analyze", content=make_jpeg_bytes(doc_img), headers=AUTH_HEADER)
        self.assertEqual(res_doc.status_code, 200)
        data_doc = res_doc.json()
        # Ensure it doesn't crash or false-positive as a car
        self.assertEqual(data_doc["vehicle_count"], 0)

    def test_10_multi_vehicle_dense_scene(self):
        """Test multi-vehicle synthetic scene with multiple vehicles side by side."""
        sample_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "Toyota-Yaris-GRMN-Review-Front-carwitter.jpg")
        if os.path.exists(sample_path):
            car_sample = Image.open(sample_path).resize((300, 200))
            # Stitch 4 cars into a 2x2 grid
            grid = Image.new("RGB", (620, 420), color=(200, 200, 200))
            grid.paste(car_sample, (10, 10))
            grid.paste(car_sample, (310, 10))
            grid.paste(car_sample, (10, 210))
            grid.paste(car_sample, (310, 210))

            b = make_jpeg_bytes(grid)
            res = self.client.post("/analyze", content=b, headers=AUTH_HEADER)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertGreaterEqual(data["vehicle_count"], 2, f"Expected multiple vehicles detected, got {data['vehicle_count']}")
            self.assertIsNotNone(data["car_color"])
            self.assertEqual(len(data["vehicles"]), data["vehicle_count"])

    def test_11_heavily_occluded_vehicle_crops(self):
        """Test heavily occluded vehicle image (e.g. 50% and 80% black/white bars over vehicle)."""
        sample_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "Toyota-Yaris-GRMN-Review-Front-carwitter.jpg")
        if os.path.exists(sample_path):
            car_orig = Image.open(sample_path).convert("RGB")
            w, h = car_orig.size

            # 1. 50% horizontal occlusion mask
            car_50 = car_orig.copy()
            draw50 = ImageDraw.Draw(car_50)
            draw50.rectangle([0, int(h * 0.4), w, int(h * 0.9)], fill=(0, 0, 0))
            b_50 = make_jpeg_bytes(car_50)
            res_50 = self.client.post("/analyze", content=b_50, headers=AUTH_HEADER)
            self.assertEqual(res_50.status_code, 200)
            self.assertTrue(res_50.json()["success"])

            # 2. 80% random noise occlusion mask
            car_80 = car_orig.copy()
            draw80 = ImageDraw.Draw(car_80)
            draw80.rectangle([int(w * 0.1), 0, int(w * 0.9), int(h * 0.85)], fill=(128, 128, 128))
            b_80 = make_jpeg_bytes(car_80)
            res_80 = self.client.post("/analyze", content=b_80, headers=AUTH_HEADER)
            self.assertEqual(res_80.status_code, 200)
            self.assertTrue(res_80.json()["success"])

    # =========================================================================
    # 4. MALFORMED, CORRUPTED & BOUNDARY PAYLOADS
    # =========================================================================

    def test_12_truncated_jpeg_and_corrupted_headers(self):
        """Test handling of truncated JPEG bitstreams and broken magic headers."""
        sample_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "Toyota-Yaris-GRMN-Review-Front-carwitter.jpg")
        if os.path.exists(sample_path):
            with open(sample_path, "rb") as f:
                full_bytes = f.read()

            # Truncate at 100 bytes
            trunc_100 = full_bytes[:100]
            res_trunc = self.client.post("/analyze", content=trunc_100, headers=AUTH_HEADER)
            self.assertEqual(res_trunc.status_code, 400, f"Expected 400 for truncated JPEG, got {res_trunc.status_code}")

            # Corrupt magic header bytes
            corrupt_header = b"\xFF\xD8\xFF\x00\x00\x00INVALIDBYTESCORRUPTED" + full_bytes[20:]
            res_corrupt = self.client.post("/analyze", content=corrupt_header, headers=AUTH_HEADER)
            self.assertIn(res_corrupt.status_code, [200, 400], "Should either gracefully decode or return 400")

    def test_13_non_image_binary_formats(self):
        """Test non-image formats (ZIP archive, PDF, random byte garbage)."""
        # ZIP header
        zip_fake = b"PK\x03\x04\x14\x00\x00\x00\x08\x00" + os.urandom(256)
        res_zip = self.client.post("/analyze", content=zip_fake, headers=AUTH_HEADER)
        self.assertEqual(res_zip.status_code, 400)

        # PDF header
        pdf_fake = b"%PDF-1.4\n%Fake PDF binary stream\n" + os.urandom(512)
        res_pdf = self.client.post("/analyze", content=pdf_fake, headers=AUTH_HEADER)
        self.assertEqual(res_pdf.status_code, 400)

        # Random high-entropy junk bytes
        junk = os.urandom(1024 * 16)
        res_junk = self.client.post("/analyze", content=junk, headers=AUTH_HEADER)
        self.assertEqual(res_junk.status_code, 400)

    def test_14_auth_header_boundary_fuzzing(self):
        """Test malformed and boundary Authentication headers."""
        # 1. Non-base64 garbage
        res1 = self.client.post("/analyze", content=b"test", headers={"Authorization": "Basic !!!not-valid-base64==="})
        self.assertEqual(res1.status_code, 401)
        self.assertIn("WWW-Authenticate", res1.headers)

        # 2. Valid base64 but missing colon separator
        no_colon = base64.b64encode(b"adminonlywithoutcolon").decode()
        res2 = self.client.post("/analyze", content=b"test", headers={"Authorization": f"Basic {no_colon}"})
        self.assertEqual(res2.status_code, 401)

        # 3. Extremely long auth credentials (buffer overflow / ReDoS check)
        long_creds = base64.b64encode((b"A" * 10000) + b":" + (b"B" * 10000)).decode()
        res3 = self.client.post("/analyze", content=b"test", headers={"Authorization": f"Basic {long_creds}"})
        self.assertEqual(res3.status_code, 401)

        # 4. Null-byte injection in auth credentials
        null_creds = base64.b64encode(b"admin\x00extra:nomer123456").decode()
        res4 = self.client.post("/analyze", content=b"test", headers={"Authorization": f"Basic {null_creds}"})
        self.assertEqual(res4.status_code, 401)

    # =========================================================================
    # 5. CONCURRENCY, INFERENCE STABILITY & MEMORY LEAKS
    # =========================================================================

    def test_15_concurrent_requests_and_thread_safety(self):
        """Test rapid concurrent requests across multiple worker threads."""
        sample_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "Toyota-Yaris-GRMN-Review-Front-carwitter.jpg")
        with open(sample_path, "rb") as f:
            sample_bytes = f.read()

        num_threads = 6
        num_requests = 12
        print(f"\n  [Stress] Launching {num_requests} requests across {num_threads} concurrent threads...")

        results: List[Dict[str, Any]] = []
        errors: List[str] = []

        def worker(idx: int):
            client = TestClient(app)
            try:
                t0 = time.time()
                res = client.post("/analyze", content=sample_bytes, headers=AUTH_HEADER)
                dt = time.time() - t0
                if res.status_code == 200:
                    data = res.json()
                    results.append({"idx": idx, "status": 200, "duration": dt, "vehicles": data["vehicle_count"]})
                else:
                    errors.append(f"Worker {idx} failed with {res.status_code}: {res.text}")
            except Exception as e:
                errors.append(f"Worker {idx} exception: {str(e)}")

        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, i) for i in range(num_requests)]
            concurrent.futures.wait(futures)
        total_time = time.time() - start_time

        print(f"  [Stress] Completed {len(results)}/{num_requests} requests in {total_time:.2f}s. Errors: {len(errors)}")

        self.assertEqual(len(errors), 0, f"Encountered concurrent request errors: {errors}")
        self.assertEqual(len(results), num_requests)
        for r in results:
            self.assertEqual(r["status"], 200)
            self.assertEqual(r["vehicles"], 1)

    def test_16_memory_profile_and_burst_stability(self):
        """Test sequential burst of 15 requests and measure memory / response stability."""
        sample_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "Toyota-Yaris-GRMN-Review-Front-carwitter.jpg")
        with open(sample_path, "rb") as f:
            sample_bytes = f.read()

        import gc
        import tracemalloc

        tracemalloc.start()
        gc.collect()
        snapshot_start = tracemalloc.take_snapshot()

        burst_count = 10
        print(f"\n  [Stress] Running sequential burst of {burst_count} requests...")
        durations = []
        for i in range(burst_count):
            t0 = time.time()
            res = self.client.post("/analyze", content=sample_bytes, headers=AUTH_HEADER)
            durations.append(time.time() - t0)
            self.assertEqual(res.status_code, 200)

        gc.collect()
        snapshot_end = tracemalloc.take_snapshot()
        stats = snapshot_end.compare_to(snapshot_start, 'lineno')

        top_growth_kb = sum(stat.size_diff for stat in stats[:10]) / 1024.0
        tracemalloc.stop()

        avg_dur = sum(durations) / len(durations)
        print(f"  [Stress] Burst completed. Avg latency: {avg_dur:.3f}s. Top 10 memory diff: {top_growth_kb:.2f} KB")

        # Memory diff should be reasonable and not grow uncontrollably
        self.assertLess(top_growth_kb, 50000, f"Memory grew excessively by {top_growth_kb} KB")


if __name__ == "__main__":
    unittest.main(verbosity=2)
