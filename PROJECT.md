# Project: Vehicle & Person Detection POC PWA

## Architecture
The system is a real-time Vehicle & Person Detection Progressive Web App (PWA) with a high-performance Python FastAPI backend integrating YOLOv8n object detection, K-Means vehicle color analysis, and EasyOCR license plate recognition.

```
[Mobile Browser / PWA Client]
       │  ▲
       │  │ HTTP Basic Auth (admin:nomer123456)
       │  │ POST /analyze (JPEG frame blob every 1.5s)
       ▼  │ JSON: {bounding_boxes, car_color, plate_number, person_count, ...}
[FastAPI Application (backend/main.py)]
       │
       ├──► Auth Middleware (BaseHTTPMiddleware / Security Scheme)
       ├──► StaticFiles Mount (frontend/ -> /)
       └──► ML Pipeline Engine (backend/ml_service.py)
              ├── YOLOv8n Object Detector (Ultralytics) -> Vehicles & Persons
              ├── Vehicle Color Extractor (Scikit-Learn K-Means in HSV/RGB)
              └── License Plate Recognizer (EasyOCR with preprocessing/CLAHE)
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Dependencies Specification | `requirements.txt` containing fastapi, uvicorn, ultralytics, easyocr, opencv-python-headless, scikit-learn, python-multipart | M1 | ORIGINAL_REQUEST §R1 |
| 2 | HTTP Basic Authentication | Enforce `admin:nomer123456` on all endpoints (`/` returns 401 without auth, 200 with auth) | M1 | ORIGINAL_REQUEST §R1, §Acceptance |
| 3 | Static Files Serving | Mount `frontend/` directory to serve PWA static assets at `/` | M1 | ORIGINAL_REQUEST §R1 |
| 4 | YOLOv8 Vehicle & Person Detection | `backend/ml_service.py` loading `yolov8n.pt` detecting cars, trucks, buses, motorcycles, persons | M1 | ORIGINAL_REQUEST §R1 |
| 5 | K-Means Dominant Vehicle Color | K-Means clustering on cropped vehicle ROI with color space mapping | M1 | ORIGINAL_REQUEST §R1 |
| 6 | EasyOCR License Plate Recognition | Crop vehicle plate region and run OCR with preprocessing | M1 | ORIGINAL_REQUEST §R1 |
| 7 | `POST /analyze` API Endpoint | Accepts multipart or raw bytes, runs ML pipeline, returns standardized JSON response | M1 | ORIGINAL_REQUEST §R1 |
| 8 | Frontend PWA HTML5 UI | `frontend/index.html` with `<video>` element, overlaid `<canvas>`, HUD badges, `<pre id="json-output">` | M2 | ORIGINAL_REQUEST §R2 |
| 9 | Mobile-First Responsive CSS | `frontend/style.css` tailored for portrait mobile layout with full-viewport canvas overlay | M2 | ORIGINAL_REQUEST §R2 |
| 10 | Real-Time Camera & Detection Loop | `frontend/app.js` using `facingMode: "environment"`, 1.5s interval frame capture, fetch `/analyze`, draw bounding boxes | M2 | ORIGINAL_REQUEST §R2 |
| 11 | PWA Manifest & Service Worker | `frontend/manifest.json` and `frontend/sw.js` for offline caching and installability | M2 | ORIGINAL_REQUEST §R2 |
| 12 | Automated Verification & E2E Tests | `test_e2e.py` verifying uvicorn lifecycle, 401/200 auth, frontend static assets, `app.js` logic, and `data/` sample detections | M3 | ORIGINAL_REQUEST §Acceptance |
| 13 | Periodic & Final Git Commits | Periodic Git commits during development and final commit upon completion | M1, M2, M3, M4 | ORIGINAL_REQUEST §2026-08-18T18:01:06Z |
| 14 | Architectural Review & Robustness Hardening | Architect review of design, structure, and edge-case handling; Challenger & Forensic Audit verification | M4 | ORIGINAL_REQUEST §Goal |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M0 | Scope Survey & Feature Inventory | Multi-explorer survey of requirements, backend, ML, frontend, and tests | None | DONE |
| M1 | Backend Service & ML Pipeline | `requirements.txt`, `backend/main.py`, `backend/ml_service.py`, Basic Auth, Git commit M1 | M0 | DONE |
| M2 | Frontend PWA Application | `frontend/index.html`, `frontend/style.css`, `frontend/app.js`, `frontend/manifest.json`, `frontend/sw.js`, Git commit M2 | M1 | DONE |
| M3 | Automated E2E & Component Test Suite | `test_e2e.py` testing auth, static serving, app.js logic, `data/` images inference, Git commit M3 | M1, M2 | DONE |
| M4 | Architectural Review, Adversarial Hardening & Forensic Audit | Architect review & refactor loop, Challenger adversarial validation, Forensic Auditor verification, Final Git commit | M3 | DONE |

## Interface Contracts

### 1. HTTP Basic Auth Contract
- Header: `Authorization: Basic YWRtaW46bm9tZXIxMjM0NTY=` (`admin:nomer123456`)
- Unauthenticated requests: HTTP 401 Unauthorized with `WWW-Authenticate: Basic realm="Restricted"`
- Authenticated requests: Processed normally

### 2. `POST /analyze` Contract
- Input: Multipart form-data with field `file` (or raw image bytes `image/jpeg`, `image/png`, `image/avif`)
- Output Format (JSON):
```json
{
  "status": "success",
  "person_count": 0,
  "car_color": "white",
  "plate_number": "53",
  "bounding_boxes": [
    {
      "label": "car",
      "confidence": 0.92,
      "box": [120, 85, 450, 320],
      "color": "white",
      "plate": "53"
    },
    {
      "label": "person",
      "confidence": 0.88,
      "box": [50, 100, 110, 290]
    }
  ],
  "vehicles": [
    {
      "label": "car",
      "confidence": 0.92,
      "box": [120, 85, 450, 320],
      "color": "white",
      "plate": "53"
    }
  ],
  "persons": [
    {
      "label": "person",
      "confidence": 0.88,
      "box": [50, 100, 110, 290]
    }
  ]
}
```

### 3. Frontend PWA Contract
- Canvas Overlay: Coordinate mapping from video aspect ratio to overlay canvas with cyan/emerald bounding boxes, vehicle color tags, and license plate badges.
- Frame capture loop: Periodic 1.5s interval with mutex (`isAnalyzing`) preventing request queuing.
- Service Worker: Cache app shell (`/`, `/index.html`, `/style.css`, `/app.js`, `/manifest.json`) on install, Cache-First strategy with network fallback.

## Code Layout
```
d:\2grow\ag-nomer/
├── backend/
│   ├── __init__.py
│   ├── main.py          # FastAPI app, Auth middleware, /analyze endpoint, StaticFiles
│   └── ml_service.py    # YOLOv8n detector, K-Means color extractor, EasyOCR plate reader
├── frontend/
│   ├── index.html       # Video feed, Canvas overlay, JSON pre tag, HUD elements
│   ├── style.css        # Mobile-first portrait styling
│   ├── app.js           # getUserMedia, frame extraction, fetch /analyze, canvas rendering
│   ├── manifest.json    # PWA web app manifest
│   └── sw.js            # PWA service worker (caching & offline)
├── data/                # Sample test images (Toyota, Beetle, wet city street, etc.)
├── test_e2e.py          # Comprehensive automated test suite
├── requirements.txt     # Python dependencies
└── PROJECT.md           # Master project index & specification
```
