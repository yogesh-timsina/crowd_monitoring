# AI Crowd Monitoring & Abnormal Activity Detection

Features:
- Multi-camera selection
- OpenCV HOG person detection (no downloads)
- Real-time overlay, metrics via Socket.IO
- Optical-flow abnormality cue
- Email + optional SMS alerts (cooldown)
- Auth (Flask-Login) with default admin `admin@local / admin`
- Snapshot history + chart
- Event clips (MP4 pre/post-roll)
- Dockerfile + docker-compose

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export CAMERAS="0"   # or "0,1" or RTSP URLs
python app.py
# open http://localhost:5000  (login: admin@local / admin)
```

## Alerts
- Email: set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `FROM_ADDR`, `TO_ADDRS` (comma-separated)
- SMS (Twilio): `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_FROM`, `SMS_TO`
- Cooldown: `ALERT_COOLDOWN_SEC` (default 60s)

## Clips
- MP4 files in `clips/` (pre-roll `CLIP_SEC`, post `CLIP_POST_SEC`).

## Docker
```bash
docker compose up --build
# App on http://localhost:5000
```
