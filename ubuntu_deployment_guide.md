# Ubuntu 24 Deployment & Testing Guide

This guide will walk you through launching the Vehicle & Person Detection POC PWA on an **Ubuntu 24** host machine and accessing it securely from your Android phone.

## 0. Code Changes Required?

**Good news!** No code changes are required. The codebase was designed to be fully cross-platform:
*   The `requirements.txt` handles OS-specific library differences automatically.
*   The API paths in `app.js` are relative (`/analyze`), so they adapt to any domain or IP.
*   The python code uses cross-platform `os.path` operations.
*   The use of `opencv-python-headless` prevents issues with missing GUI libraries on headless servers.

## 1. Prerequisites on Ubuntu 24

First, ensure you have Python 3 and a virtual environment module installed. Ubuntu 24 typically ships with Python 3.12.

Open your terminal and run:
```bash
sudo apt update
sudo apt install python3-venv python3-pip
```

*(Optional)* If you are running on a very minimal Ubuntu server installation and encounter OpenCV errors later, you may need to install glib: `sudo apt install libglib2.0-0`. 

## 2. Setup the Project

1. Copy the project folder (`ag-nomer`) to your Ubuntu 24 machine.
2. Navigate into the project folder:
   ```bash
   cd path/to/ag-nomer
   ```
3. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
4. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## 3. Launch the Backend Server

Start the FastAPI server using Uvicorn:
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
*The server is now running on `http://<your-ubuntu-ip>:8000`.*

---

## 4. The HTTPS Requirement for Android

**Important:** Modern Android browsers (like Chrome) strictly require a **Secure Context (HTTPS)** to allow access to the camera (`getUserMedia`) and to install PWAs. 

If you just connect to `http://<ubuntu-ip>:8000` from your phone on the local network, the camera will be blocked. To solve this, we will use **ngrok** to create a secure, temporary HTTPS tunnel to your Ubuntu machine.

### Step 4a: Install ngrok on Ubuntu
In a **new terminal window** (keep the FastAPI server running in the first one), install ngrok:
```bash
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
  | sudo tee /etc/apt/keyrings/ngrok.asc >/dev/null \
  && echo "deb [signed-by=/etc/apt/keyrings/ngrok.asc] https://ngrok-agent.s3.amazonaws.com buster main" \
  | sudo tee /etc/apt/sources.list.d/ngrok.list \
  && sudo apt update \
  && sudo apt install ngrok
```

### Step 4b: Start the Tunnel
Run ngrok to expose port 8000:
```bash
ngrok http 8000
```
*Note: If you haven't used ngrok before, you may need to sign up for a free account on their website and run `ngrok config add-authtoken <your-token>` first.*

Ngrok will output a Forwarding URL that looks like:
**`https://<random-string>.ngrok-free.app`**

---

## 5. Testing on your Android Phone

1. **Open Chrome** on your Android phone.
2. Enter the **HTTPS ngrok URL** provided in the previous step.
3. You will be prompted for authentication. Enter the credentials:
   *   **Username:** `admin`
   *   **Password:** `nomer123456`
4. **Camera Permissions:** The browser will ask for permission to use your camera. Tap **Allow**. The app should start showing your rear-facing camera feed.
5. **Install as PWA:** Look for the **"Install App"** button in the UI, or tap the Chrome three-dot menu in the top right and select **"Add to Home screen"**. This will install the app directly to your phone.

## 6. Parking Lot Test

Now that the app is installed and running on your phone:
1. Walk to the parking lot.
2. Launch the installed PWA from your phone's home screen.
3. Point your camera at vehicles.
4. The app will automatically capture frames every 1.5 seconds, send them back to your Ubuntu machine for YOLO/EasyOCR processing, and render the bounding boxes, colors, and license plates directly on your screen.

Enjoy testing!
