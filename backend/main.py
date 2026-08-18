"""FastAPI Application for Vehicle & Person Detection POC PWA.

Provides:
- HTTP Basic Auth (admin:nomer123456) protection across all routes and static assets.
- POST /analyze endpoint accepting multipart/form-data or binary image payloads.
- Static file serving for PWA assets in frontend/ mounted at root /.
"""

import os
import sys
import base64
import secrets
import logging
from typing import Optional

from fastapi import FastAPI, Request, Response, HTTPException, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("backend.main")

# Import ML service
from backend.ml_service import ml_service

# Credentials
AUTH_USERNAME = "admin"
AUTH_PASSWORD = "nomer123456"
AUTH_REALM = "Restricted"


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Enforces HTTP Basic Authentication globally across all endpoints and static files."""

    async def dispatch(self, request: Request, call_next):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Basic "):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": f'Basic realm="{AUTH_REALM}"'},
                content="Unauthorized: Missing Basic Authentication credentials\n",
                media_type="text/plain"
            )

        try:
            encoded_creds = auth_header.split(" ", 1)[1].strip()
            decoded = base64.b64decode(encoded_creds).decode("utf-8")
            username, _, password = decoded.partition(":")

            is_valid_user = secrets.compare_digest(username, AUTH_USERNAME)
            is_valid_pass = secrets.compare_digest(password, AUTH_PASSWORD)

            if not (is_valid_user and is_valid_pass):
                return Response(
                    status_code=401,
                    headers={"WWW-Authenticate": f'Basic realm="{AUTH_REALM}"'},
                    content="Unauthorized: Invalid credentials\n",
                    media_type="text/plain"
                )
        except Exception:
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": f'Basic realm="{AUTH_REALM}"'},
                content="Unauthorized: Malformed credentials\n",
                media_type="text/plain"
            )

        return await call_next(request)


# Create FastAPI application
app = FastAPI(
    title="Vehicle & Person Detection API",
    description="Real-time Vehicle & Person Detection POC with YOLOv8 and EasyOCR",
    version="1.0.0"
)

# Attach authentication middleware
app.add_middleware(BasicAuthMiddleware)


@app.post("/analyze")
async def analyze_image_endpoint(
    request: Request,
    file: Optional[UploadFile] = File(None),
    image: Optional[UploadFile] = File(None)
):
    """Analyze an uploaded frame for vehicles, license plates, dominant color, and persons."""
    image_bytes = None

    if file is not None:
        image_bytes = await file.read()
    elif image is not None:
        image_bytes = await image.read()
    else:
        # Fallback to direct raw request body bytes
        raw_body = await request.body()
        if raw_body and len(raw_body) > 0:
            image_bytes = raw_body

    if not image_bytes or len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty or missing image payload")

    try:
        result = ml_service.analyze_image(image_bytes)
        return JSONResponse(status_code=200, content=result)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("Inference failure occurred")
        raise HTTPException(status_code=500, detail=f"Inference failure: {str(e)}")


# Determine frontend path and mount StaticFiles
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
os.makedirs(FRONTEND_DIR, exist_ok=True)

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
