"""Machine Learning & Computer Vision Service for Vehicle & Person Detection POC.

Integrates:
- YOLOv8n for real-time multi-target detection (vehicles: car, truck, bus, motorcycle; persons)
- Scikit-Learn K-Means clustering for vehicle dominant body color classification
- EasyOCR with CLAHE/contrast enhancement for license plate recognition (ALPR)
- Robust image decoding supporting JPEG, PNG, WebP, and AVIF formats
"""

import io
import re
import time
import colorsys
import numpy as np
from typing import Dict, Any, List, Optional, Tuple

try:
    import cv2
except ImportError:
    cv2 = None

try:
    from PIL import Image
    try:
        import pillow_avif
    except ImportError:
        pass
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
except ImportError:
    Image = None

from sklearn.cluster import KMeans

# Color definitions and mapping
COLOR_MAP = {
    "black": (25, 25, 25),
    "white": (240, 240, 240),
    "silver": (192, 192, 192),
    "gray": (128, 128, 128),
    "red": (220, 20, 60),
    "orange": (255, 140, 0),
    "yellow": (255, 215, 0),
    "green": (34, 139, 34),
    "blue": (30, 144, 255),
    "purple": (128, 0, 128),
    "pink": (255, 105, 180),
    "brown": (139, 69, 19)
}

# COCO Vehicle Class IDs
VEHICLE_CLASS_IDS = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck"
}

PERSON_CLASS_ID = 0


def rgb_to_color_name(r: int, g: int, b: int) -> Tuple[str, List[int]]:
    """Convert RGB centroid values to a standardized human-readable color name."""
    r_norm, g_norm, b_norm = r / 255.0, g / 255.0, b / 255.0
    h, s, v = colorsys.rgb_to_hsv(r_norm, g_norm, b_norm)
    h_deg = h * 360.0
    delta = max(r, g, b) - min(r, g, b)
    avg_val = (r + g + b) / 3.0

    # Low brightness -> Black
    if v < 0.22 or (r < 45 and g < 45 and b < 45) or (avg_val < 45):
        return "black", [int(r), int(g), int(b)]

    # Low saturation or low channel spread -> Neutral colors (White / Silver / Gray / Black)
    if s < 0.25 or delta < 35:
        if avg_val > 185:
            return "white", [int(r), int(g), int(b)]
        elif avg_val > 130:
            return "silver", [int(r), int(g), int(b)]
        elif avg_val > 65:
            return "gray", [int(r), int(g), int(b)]
        else:
            return "black", [int(r), int(g), int(b)]

    # Saturated hues
    if h_deg < 15 or h_deg >= 345:
        return "red", [int(r), int(g), int(b)]
    elif 15 <= h_deg < 42:
        if v < 0.45 or avg_val < 90:
            return "brown", [int(r), int(g), int(b)]
        return "orange", [int(r), int(g), int(b)]
    elif 42 <= h_deg < 70:
        return "yellow", [int(r), int(g), int(b)]
    elif 70 <= h_deg < 165:
        return "green", [int(r), int(g), int(b)]
    elif 165 <= h_deg < 255:
        # Sky reflection or muted bluish gray check
        if s < 0.32 and avg_val < 150 and delta < 50:
            return "gray", [int(r), int(g), int(b)]
        return "blue", [int(r), int(g), int(b)]
    elif 255 <= h_deg < 290:
        return "purple", [int(r), int(g), int(b)]
    elif 290 <= h_deg < 345:
        return "pink", [int(r), int(g), int(b)]

    return "gray", [int(r), int(g), int(b)]


def extract_dominant_color(vehicle_rgb: np.ndarray, k: int = 5) -> Tuple[str, List[int]]:
    """Extract the dominant body paint color using K-Means clustering.

    Applies ROI sub-cropping to filter out windshield glass, shadows, and tires.
    """
    if vehicle_rgb is None or vehicle_rgb.size == 0:
        return "unknown", [128, 128, 128]

    h, w, _ = vehicle_rgb.shape

    # Focus on lower-central vehicle region (avoid windshield at top, tires/ground at bottom)
    if h > 40 and w > 40:
        y1 = int(h * 0.30)
        y2 = int(h * 0.78)
        x1 = int(w * 0.18)
        x2 = int(w * 0.82)
        roi = vehicle_rgb[y1:y2, x1:x2]
        if roi.size == 0:
            roi = vehicle_rgb
    else:
        roi = vehicle_rgb

    # Resize ROI for fast, stable clustering
    target_size = (64, 64)
    if cv2 is not None:
        resized = cv2.resize(roi, target_size, interpolation=cv2.INTER_AREA)
    else:
        pil_roi = Image.fromarray(roi)
        resized = np.array(pil_roi.resize(target_size))

    pixels = resized.reshape(-1, 3).astype(np.float32)

    try:
        kmeans = KMeans(n_clusters=k, n_init=3, max_iter=50, random_state=42)
        kmeans.fit(pixels)
        centers = kmeans.cluster_centers_
        counts = np.bincount(kmeans.labels_)

        # Sort clusters by pixel count descending
        sorted_indices = np.argsort(counts)[::-1]

        # Filter out extreme dark shadow clusters if a non-shadow cluster with substantial mass exists
        best_center = centers[sorted_indices[0]]
        
        # If the top cluster is very dark shadow or sky glare, check if another substantial cluster represents the body
        for idx in sorted_indices:
            c = centers[idx]
            weight = counts[idx] / len(pixels)
            if weight >= 0.15:
                # If this cluster is clearly a rich body color or clean neutral, select it
                c_name, _ = rgb_to_color_name(int(c[0]), int(c[1]), int(c[2]))
                if c_name in ["white", "black", "silver", "red", "blue", "yellow", "green", "orange", "gray"]:
                    best_center = c
                    break

        r, g, b = int(round(best_center[0])), int(round(best_center[1])), int(round(best_center[2]))
        color_name, rgb_vals = rgb_to_color_name(r, g, b)
        return color_name, rgb_vals
    except Exception:
        # Fallback to mean color
        mean_c = np.mean(pixels, axis=0)
        r, g, b = int(mean_c[0]), int(mean_c[1]), int(mean_c[2])
        return rgb_to_color_name(r, g, b)


class MLService:
    """Singleton Machine Learning Service hosting YOLOv8 and EasyOCR."""

    def __init__(self, yolo_model_path: str = "yolov8n.pt"):
        self.yolo_model_path = yolo_model_path
        self._yolo = None
        self._ocr = None
        self._initialized = False

    def initialize(self):
        """Lazy load models on demand."""
        if self._initialized:
            return

        import torch
        from ultralytics import YOLO
        import easyocr

        use_gpu = torch.cuda.is_available()

        # Load YOLOv8n
        self._yolo = YOLO(self.yolo_model_path)

        # Load EasyOCR
        self._ocr = easyocr.Reader(['en'], gpu=use_gpu)

        # Warmup pass
        dummy = np.zeros((320, 320, 3), dtype=np.uint8)
        self._yolo.predict(source=dummy, verbose=False)

        self._initialized = True

    def decode_image(self, image_bytes: bytes) -> np.ndarray:
        """Decode raw image bytes into an RGB NumPy array with robust format handling."""
        if not image_bytes or len(image_bytes) == 0:
            raise ValueError("Empty or missing image payload")

        # 1. Try OpenCV decoding
        if cv2 is not None:
            try:
                np_arr = np.frombuffer(image_bytes, np.uint8)
                bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                if bgr is not None and bgr.size > 0:
                    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            except Exception:
                pass

        # 2. Try PIL decoding (handles AVIF, WebP, PNG, etc.)
        if Image is not None:
            try:
                pil_img = Image.open(io.BytesIO(image_bytes))
                pil_img = pil_img.convert("RGB")
                rgb = np.array(pil_img)
                if rgb is not None and rgb.size > 0:
                    return rgb
            except Exception as e:
                raise ValueError(f"Could not decode image: {str(e)}")

        raise ValueError("Could not decode image: unsupported format or corrupted bytes")

    def _ocr_license_plate(self, vehicle_crop_rgb: np.ndarray) -> Tuple[Optional[str], float, Optional[List[int]]]:
        """Perform OCR to extract license plate text from vehicle crop using EasyOCR with CLAHE."""
        if self._ocr is None or vehicle_crop_rgb is None or vehicle_crop_rgb.size == 0:
            return None, 0.0, None

        h, w, _ = vehicle_crop_rgb.shape
        candidates = []

        # Candidate 1: Lower 65% of vehicle (bumper/grille area where plates are mounted)
        if h > 40 and w > 40:
            lower_crop = vehicle_crop_rgb[int(h * 0.35):, :]
            candidates.append((lower_crop, int(h * 0.35), 0))
        
        # Candidate 2: Full vehicle crop fallback
        candidates.append((vehicle_crop_rgb, 0, 0))

        best_text = None
        best_conf = 0.0
        best_box = None
        best_score = -1.0

        for crop, y_offset, x_offset in candidates:
            if crop.size == 0:
                continue

            crop_h, crop_w, _ = crop.shape
            
            # Preprocessing: Grayscale + CLAHE + optional cubic upscaling
            if cv2 is not None:
                gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
                if crop_w < 400:
                    scale = 400.0 / crop_w
                    gray = cv2.resize(gray, (int(crop_w * scale), int(crop_h * scale)), interpolation=cv2.INTER_CUBIC)
                else:
                    scale = 1.0

                clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
                enhanced = clahe.apply(gray)
            else:
                enhanced = crop
                scale = 1.0

            try:
                ocr_results = self._ocr.readtext(enhanced, detail=1)
            except Exception:
                ocr_results = []

            for bbox, text, conf in ocr_results:
                clean_text = re.sub(r'[^A-Za-z0-9]', '', text).upper()
                
                # License plates are typically 2 to 12 alphanumeric characters
                if 2 <= len(clean_text) <= 12 and conf > 0.15:
                    # Score preference: longer strings (4-10 chars) matching plates over short country badges (e.g. "GB", "UA")
                    length_bonus = 1.5 if len(clean_text) >= 4 else (1.2 if len(clean_text) >= 3 else 0.7)
                    score = float(conf) * length_bonus

                    if score > best_score:
                        best_score = score
                        best_text = clean_text
                        best_conf = float(conf)
                        if bbox:
                            xs = [pt[0] / scale for pt in bbox]
                            ys = [pt[1] / scale for pt in bbox]
                            bx1 = int(min(xs) + x_offset)
                            by1 = int(min(ys) + y_offset)
                            bx2 = int(max(xs) + x_offset)
                            by2 = int(max(ys) + y_offset)
                            best_box = [bx1, by1, bx2, by2]

            if best_text and best_conf > 0.70 and len(best_text) >= 4:
                break

        return best_text, round(best_conf, 3), best_box

    def analyze_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """Process image frame through YOLOv8, K-Means Color, and EasyOCR plate recognition.

        Returns structured JSON compliant with PROJECT.md and survey contracts.
        """
        start_time = time.time()
        self.initialize()

        rgb_img = self.decode_image(image_bytes)
        img_h, img_w, _ = rgb_img.shape

        # Run YOLOv8 detection
        results = self._yolo.predict(source=rgb_img, conf=0.25, verbose=False)

        vehicles: List[Dict[str, Any]] = []
        persons: List[Dict[str, Any]] = []
        bounding_boxes: List[Dict[str, Any]] = []
        detections: List[Dict[str, Any]] = []

        if results and len(results) > 0:
            boxes = results[0].boxes
            for box in boxes:
                cls_id = int(box.cls[0].item())
                conf = round(float(box.conf[0].item()), 3)
                xyxy = box.xyxy[0].tolist()

                # Clamp bounding box coordinates
                x1 = max(0, min(int(round(xyxy[0])), img_w - 1))
                y1 = max(0, min(int(round(xyxy[1])), img_h - 1))
                x2 = max(0, min(int(round(xyxy[2])), img_w))
                y2 = max(0, min(int(round(xyxy[3])), img_h))

                box_coords = [x1, y1, x2, y2]

                if cls_id in VEHICLE_CLASS_IDS:
                    vehicle_label = VEHICLE_CLASS_IDS[cls_id]
                    # Crop vehicle
                    vehicle_crop = rgb_img[y1:y2, x1:x2]

                    # Dominant Color
                    color_name, rgb_val = extract_dominant_color(vehicle_crop)

                    # OCR License Plate
                    plate_text, plate_conf, plate_box = self._ocr_license_plate(vehicle_crop)

                    vehicle_data = {
                        "label": vehicle_label,
                        "class": vehicle_label,
                        "confidence": conf,
                        "box": box_coords,
                        "bounding_box": box_coords,
                        "color": color_name,
                        "dominant_color": {
                            "name": color_name,
                            "rgb": rgb_val,
                            "hex": f"#{rgb_val[0]:02x}{rgb_val[1]:02x}{rgb_val[2]:02x}"
                        },
                        "plate": plate_text,
                        "plate_confidence": plate_conf,
                        "license_plate": {
                            "text": plate_text,
                            "confidence": plate_conf,
                            "box": plate_box
                        } if plate_text else None
                    }
                    vehicles.append(vehicle_data)

                    # Consolidated bounding box entry
                    label_desc = f"{vehicle_label} ({color_name}" + (f", {plate_text})" if plate_text else ")")
                    bbox_entry = {
                        "label": label_desc,
                        "class": vehicle_label,
                        "confidence": conf,
                        "box": box_coords,
                        "color": color_name,
                        "plate": plate_text
                    }
                    bounding_boxes.append(bbox_entry)
                    detections.append(vehicle_data)

                elif cls_id == PERSON_CLASS_ID:
                    person_data = {
                        "label": "person",
                        "class": "person",
                        "confidence": conf,
                        "box": box_coords,
                        "bounding_box": box_coords
                    }
                    persons.append(person_data)
                    bounding_boxes.append(person_data)
                    detections.append(person_data)

        # Primary vehicle determination (largest bounding box area)
        primary_color: Optional[str] = None
        primary_plate: Optional[str] = None

        if vehicles:
            def box_area(v):
                b = v["box"]
                return (b[2] - b[0]) * (b[3] - b[1])

            primary_vehicle = max(vehicles, key=box_area)
            primary_color = primary_vehicle["color"]
            primary_plate = primary_vehicle["plate"]

        elapsed_ms = round((time.time() - start_time) * 1000.0, 1)

        response = {
            "status": "success",
            "success": True,
            "person_count": len(persons),
            "vehicle_count": len(vehicles),
            "car_color": primary_color,
            "plate_number": primary_plate,
            "bounding_boxes": bounding_boxes,
            "vehicles": vehicles,
            "persons": persons,
            "detections": detections,
            "summary": {
                "vehicle_count": len(vehicles),
                "person_count": len(persons),
                "license_plates": [v["plate"] for v in vehicles if v.get("plate")],
                "dominant_colors": [v["color"] for v in vehicles if v.get("color")]
            },
            "processing_time_ms": elapsed_ms
        }

        return response


# Global singleton instance
ml_service = MLService()
