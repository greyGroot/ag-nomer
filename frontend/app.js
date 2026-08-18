/**
 * AutoDetect POC — Frontend Application Logic
 * PWA Video Stream Capture, Overlay Canvas Rendering, and Live API Synchronization
 */

(function () {
  'use strict';

  // Constants & Configuration
  const CAPTURE_INTERVAL_MS = 1500; // 1.5s interval required by specification
  const ANALYZE_ENDPOINT = '/analyze';
  const BASIC_AUTH_CREDENTIALS = btoa('admin:nomer123456');

  // DOM Elements
  const video = document.getElementById('camera-feed');
  const overlayCanvas = document.getElementById('overlay-canvas');
  const overlayCtx = overlayCanvas.getContext('2d');
  const jsonOutput = document.getElementById('json-output');
  const cameraAlert = document.getElementById('camera-alert');
  const scanningReticle = document.getElementById('scanning-reticle');
  const btnToggleCam = document.getElementById('btn-toggle-cam');
  const btnManualScan = document.getElementById('btn-manual-scan');
  const btnInstallPwa = document.getElementById('btn-install-pwa');
  const btnCopyJson = document.getElementById('btn-copy-json');
  const fileInput = document.getElementById('file-input');
  const fpsBadge = document.getElementById('fps-badge');
  const connStatus = document.getElementById('conn-status');

  // HUD Metric Counters
  const valVehicles = document.getElementById('val-vehicles');
  const valPersons = document.getElementById('val-persons');
  const valPlates = document.getElementById('val-plates');
  const valColors = document.getElementById('val-colors');

  // Runtime State
  let stream = null;
  let intervalTimer = null;
  let isAnalyzing = false;
  let isStreamActive = false;
  let deferredPrompt = null;

  // Offscreen Canvas for Frame Extraction
  const offscreenCanvas = document.createElement('canvas');
  const offscreenCtx = offscreenCanvas.getContext('2d');

  /**
   * Display Alert in Camera Viewport
   */
  function showAlert(msg) {
    if (cameraAlert) {
      cameraAlert.textContent = msg;
      cameraAlert.classList.remove('hidden');
    }
  }

  /**
   * Hide Alert
   */
  function hideAlert() {
    if (cameraAlert) {
      cameraAlert.classList.add('hidden');
    }
  }

  /**
   * Synchronize overlay canvas internal pixel resolution to video stream resolution
   */
  function syncCanvasDimensions() {
    if (video.videoWidth && video.videoHeight) {
      overlayCanvas.width = video.videoWidth;
      overlayCanvas.height = video.videoHeight;
      offscreenCanvas.width = video.videoWidth;
      offscreenCanvas.height = video.videoHeight;
    }
  }

  /**
   * Initialize Camera Stream with facingMode: "environment"
   */
  async function initCamera() {
    showAlert('Accessing camera (environment / rear)...');
    try {
      const constraints = {
        audio: false,
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1280 },
          height: { ideal: 720 }
        }
      };

      stream = await navigator.mediaDevices.getUserMedia(constraints);
      video.srcObject = stream;
      
      video.onloadedmetadata = () => {
        video.play();
        syncCanvasDimensions();
        hideAlert();
        isStreamActive = true;
        btnToggleCam.querySelector('.btn-text').textContent = 'Pause Camera';
        if (scanningReticle) scanningReticle.classList.add('active');
        startAnalysisLoop();
      };
    } catch (err) {
      console.warn('Strict facingMode constraint failed, attempting fallback...', err);
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        video.srcObject = stream;
        video.onloadedmetadata = () => {
          video.play();
          syncCanvasDimensions();
          hideAlert();
          isStreamActive = true;
          btnToggleCam.querySelector('.btn-text').textContent = 'Pause Camera';
          if (scanningReticle) scanningReticle.classList.add('active');
          startAnalysisLoop();
        };
      } catch (fallbackErr) {
        console.error('Camera initialization failed:', fallbackErr);
        showAlert(`Camera access unavailable: ${fallbackErr.message || fallbackErr.name}. You can use "Upload Image" to test.`);
      }
    }
  }

  /**
   * Stop / Toggle Camera
   */
  function stopCamera() {
    stopAnalysisLoop();
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
      stream = null;
    }
    video.srcObject = null;
    isStreamActive = false;
    btnToggleCam.querySelector('.btn-text').textContent = 'Start Camera';
    if (scanningReticle) scanningReticle.classList.remove('active');
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
  }

  /**
   * Periodic Analysis Loop (1.5s / 1500ms Interval)
   */
  function startAnalysisLoop() {
    if (intervalTimer) clearInterval(intervalTimer);
    captureAndAnalyzeFrame();
    intervalTimer = setInterval(captureAndAnalyzeFrame, CAPTURE_INTERVAL_MS);
  }

  function stopAnalysisLoop() {
    if (intervalTimer) {
      clearInterval(intervalTimer);
      intervalTimer = null;
    }
  }

  /**
   * Extract video frame, send via POST /analyze with Basic Auth, and process results
   */
  async function captureAndAnalyzeFrame() {
    if (isAnalyzing || !isStreamActive || video.paused || video.ended || !video.videoWidth) {
      return;
    }

    isAnalyzing = true;
    syncCanvasDimensions();

    // 1. Draw current video frame to offscreen canvas
    offscreenCtx.drawImage(video, 0, 0, offscreenCanvas.width, offscreenCanvas.height);

    // 2. Export frame as JPEG Blob and send to backend
    offscreenCanvas.toBlob(async (blob) => {
      if (!blob) {
        isAnalyzing = false;
        return;
      }

      await sendFrameBlob(blob);
      isAnalyzing = false;
    }, 'image/jpeg', 0.85);
  }

  /**
   * Send Image Blob to POST /analyze endpoint with Basic Auth
   */
  async function sendFrameBlob(blob) {
    const formData = new FormData();
    formData.append('file', blob, 'capture.jpg');

    const startTime = performance.now();

    try {
      const response = await fetch(ANALYZE_ENDPOINT, {
        method: 'POST',
        headers: {
          'Authorization': 'Basic ' + BASIC_AUTH_CREDENTIALS
        },
        body: formData
      });

      const latencyMs = Math.round(performance.now() - startTime);
      if (fpsBadge) fpsBadge.textContent = `⚡ ${latencyMs} ms`;

      if (!response.ok) {
        throw new Error(`HTTP ${response.status} (${response.statusText})`);
      }

      const data = await response.json();

      // Render detections on overlay canvas
      renderBoundingBoxes(data);

      // Update HUD metrics and JSON view
      updateHUDAndJSON(data);
      if (connStatus) {
        connStatus.textContent = '● Online';
        connStatus.className = 'status-badge status-online';
      }
    } catch (err) {
      console.error('Frame analysis request failed:', err);
      if (connStatus) {
        connStatus.textContent = '▲ Error';
        connStatus.className = 'status-badge';
        connStatus.style.color = '#ef4444';
      }
      if (jsonOutput) {
        jsonOutput.textContent = `// Analysis Error (${new Date().toLocaleTimeString()}):\n${err.message}`;
      }
    }
  }

  /**
   * Render computer vision bounding boxes, colors, and license plates on overlay canvas
   */
  function renderBoundingBoxes(data) {
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

    if (!data) return;

    const vehicles = data.vehicles || [];
    const persons = data.persons || [];

    // 1. Render Vehicles (Cyan)
    vehicles.forEach((veh) => {
      const box = veh.box || veh.bounding_box;
      if (!box || box.length < 4) return;

      const [x1, y1, x2, y2] = box;
      const width = x2 - x1;
      const height = y2 - y1;

      // Draw Cyan vehicle rectangle
      overlayCtx.strokeStyle = '#06b6d4';
      overlayCtx.lineWidth = Math.max(3, Math.round(overlayCanvas.width / 280));
      overlayCtx.strokeRect(x1, y1, width, height);

      // Label details
      const clsName = veh.label || veh.class || 'car';
      const colorName = veh.color || (veh.dominant_color ? veh.dominant_color.name : '');
      const plateText = veh.plate || (veh.license_plate ? veh.license_plate.text : '');

      let label = `🚗 ${clsName.toUpperCase()}`;
      if (colorName) label += ` | ${colorName}`;
      if (plateText) label += ` | 🏷️ ${plateText}`;

      drawLabel(overlayCtx, label, x1, y1 - 6, '#06b6d4', '#0f172a');
    });

    // 2. Render Persons (Emerald)
    persons.forEach((person) => {
      const box = person.box || person.bounding_box;
      if (!box || box.length < 4) return;

      const [x1, y1, x2, y2] = box;
      const width = x2 - x1;
      const height = y2 - y1;

      // Draw Emerald person rectangle
      overlayCtx.strokeStyle = '#10b981';
      overlayCtx.lineWidth = Math.max(3, Math.round(overlayCanvas.width / 280));
      overlayCtx.strokeRect(x1, y1, width, height);

      const conf = person.confidence ? ` ${Math.round(person.confidence * 100)}%` : '';
      drawLabel(overlayCtx, `🧍 Person${conf}`, x1, y1 - 6, '#10b981', '#0f172a');
    });
  }

  /**
   * Helper to draw high-contrast label badges on canvas
   */
  function drawLabel(ctx, text, x, y, bgColor, textColor) {
    const fontSize = Math.max(13, Math.round(overlayCanvas.width / 42));
    ctx.font = `bold ${fontSize}px sans-serif`;
    const textMetrics = ctx.measureText(text);
    const paddingX = 7;
    const paddingY = 4;
    const textWidth = textMetrics.width;
    const textHeight = fontSize;

    let drawY = y - textHeight - paddingY;
    if (drawY < 0) drawY = y + textHeight + paddingY + 8;

    // Draw background badge
    ctx.fillStyle = bgColor;
    ctx.fillRect(x, drawY, textWidth + paddingX * 2, textHeight + paddingY * 2);

    // Draw text
    ctx.fillStyle = textColor;
    ctx.fillText(text, x + paddingX, drawY + textHeight);
  }

  /**
   * Update Summary HUD counters and Raw JSON output
   */
  function updateHUDAndJSON(data) {
    if (jsonOutput) {
      jsonOutput.textContent = JSON.stringify(data, null, 2);
    }

    const vehicleCount = data.vehicle_count ?? (data.vehicles?.length || 0);
    const personCount = data.person_count ?? (data.persons?.length || 0);
    const primaryColor = data.car_color || (data.vehicles && data.vehicles[0]?.color) || '—';
    const primaryPlate = data.plate_number || (data.vehicles && data.vehicles[0]?.plate) || '—';

    if (valVehicles) valVehicles.textContent = vehicleCount;
    if (valPersons) valPersons.textContent = personCount;
    if (valColors) valColors.textContent = primaryColor || '—';
    if (valPlates) valPlates.textContent = primaryPlate || '—';
  }

  /**
   * Handle Manual File Upload for Desktop / Offline testing
   */
  if (fileInput) {
    fileInput.addEventListener('change', async (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;

      showAlert('Processing uploaded image...');
      stopAnalysisLoop();

      // Load image into offscreen canvas and draw
      const img = new Image();
      const objectUrl = URL.createObjectURL(file);
      img.onload = async () => {
        URL.revokeObjectURL(objectUrl);
        overlayCanvas.width = img.width;
        overlayCanvas.height = img.height;
        offscreenCanvas.width = img.width;
        offscreenCanvas.height = img.height;

        offscreenCtx.drawImage(img, 0, 0);
        hideAlert();

        await sendFrameBlob(file);
      };
      img.src = objectUrl;
    });
  }

  // Event Listeners
  if (btnToggleCam) {
    btnToggleCam.addEventListener('click', () => {
      if (isStreamActive) {
        stopCamera();
      } else {
        initCamera();
      }
    });
  }

  if (btnManualScan) {
    btnManualScan.addEventListener('click', () => {
      if (isStreamActive) {
        captureAndAnalyzeFrame();
      } else if (fileInput) {
        fileInput.click();
      }
    });
  }

  if (btnCopyJson && jsonOutput) {
    btnCopyJson.addEventListener('click', () => {
      navigator.clipboard.writeText(jsonOutput.textContent)
        .then(() => {
          btnCopyJson.textContent = 'Copied!';
          setTimeout(() => { btnCopyJson.textContent = 'Copy JSON'; }, 1500);
        })
        .catch(() => {});
    });
  }

  // PWA Install Prompt
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    if (btnInstallPwa) {
      btnInstallPwa.classList.remove('hidden');
      btnInstallPwa.addEventListener('click', async () => {
        if (deferredPrompt) {
          deferredPrompt.prompt();
          const { outcome } = await deferredPrompt.userChoice;
          if (outcome === 'accepted') {
            btnInstallPwa.classList.add('hidden');
          }
          deferredPrompt = null;
        }
      });
    }
  });

  // Service Worker Registration
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js')
        .then(reg => console.log('ServiceWorker registered:', reg.scope))
        .catch(err => console.warn('ServiceWorker registration failed:', err));
    });
  }

  // Auto-start camera if permissions already granted or on load
  window.addEventListener('DOMContentLoaded', () => {
    initCamera();
  });

})();
