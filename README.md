# 🎯 ProctorAI — Interview Integrity Monitor

An AI-powered real-time cheating detection system for online interviews using Computer Vision.

---

## 📋 Features

| Feature | Description |
|---------|-------------|
| 👁️ Real-time Face Detection | Haar Cascade-based face tracking at ~2 FPS |
| 🚫 No-Face Alert | Alerts when candidate leaves the frame |
| 👥 Multi-Face Alert | Detects if another person is present |
| 🔀 Tab Switch Detection | JS-based visibility/focus tracking |
| 📊 Risk Score | Dynamic 0–100 integrity score |
| 📈 Live Timeline | 30-second rolling activity chart |
| 📥 Log Export | Download violations as CSV |
| 🎨 Dark Dashboard | Professional monitoring interface |

---

## 🚀 Setup & Run

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the application

```bash
python app.py
```

### 3. Open in browser

```
http://localhost:5000
```

> ⚠️ Allow camera access when prompted by the browser.

---

## 📁 Project Structure

```
interview_cheat_detector/
├── app.py                    # Flask backend + OpenCV logic
├── requirements.txt          # Python dependencies
├── README.md                 # This file
├── templates/
│   └── index.html            # Dashboard HTML
└── static/
    ├── css/
    │   └── style.css         # Dashboard styles
    └── js/
        └── app.js            # Frontend logic
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Main dashboard |
| `POST` | `/api/analyze` | Analyze a video frame (base64) |
| `POST` | `/api/tab_switch` | Log a tab switch event |
| `GET` | `/api/stats` | Get session stats + violations |
| `GET` | `/api/violations` | Get full violation log |
| `POST` | `/api/reset` | Reset the session |

---

## ⚙️ How It Works

1. **Browser** captures webcam frames using `getUserMedia`
2. Every 500ms, a JPEG frame is sent to `/api/analyze`
3. **Flask** decodes the frame and runs **Haar Cascade face detection**
4. Results (face count, bounding boxes) are returned to the frontend
5. Processed frame with bounding boxes is displayed
6. **JavaScript** monitors `visibilitychange` and `blur` events for tab switches
7. All violations are logged with timestamps and severity

---

## 📊 Risk Score System

| Score | Level | Meaning |
|-------|-------|---------|
| 0–19 | ✅ CLEAN | No violations |
| 20–39 | ⚠️ CAUTION | Minor activity |
| 40–69 | 🟠 HIGH RISK | Multiple violations |
| 70–100 | 🔴 CRITICAL | Severe violations |

**Scoring:**
- Critical violation (no face / multiple faces): **+10 points**
- Warning violation (tab switch): **+5 points**

---

## 🔮 Future Enhancements

- [ ] Eye gaze tracking (MediaPipe)
- [ ] Voice/audio anomaly detection
- [ ] Screen recording integration
- [ ] PDF report generation
- [ ] Candidate authentication (face ID)
- [ ] WebSocket for real-time push alerts
- [ ] Cloud storage for session logs

---

## 🛠️ Tech Stack

- **Python / Flask** — Backend server
- **OpenCV** — Face detection engine
- **Haar Cascade** — Pre-trained face classifier
- **HTML5 / CSS3** — Dashboard layout
- **Vanilla JavaScript** — Camera capture, API calls, UI updates
- **Canvas API** — Frame capture + timeline chart

---

## ⚠️ Limitations

- Detection accuracy depends on lighting and camera quality
- Front-facing camera required
- Cannot detect phone or printed cheat sheets
- Haar Cascade may miss faces at extreme angles

---

*Built for academic/demonstration purposes. Ensure compliance with privacy laws before use in production.*
