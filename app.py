import os, time, json, threading, uuid
from datetime import datetime
from typing import Dict, Any
from flask import Flask, render_template, Response, request, jsonify, redirect, url_for, flash
from flask_socketio import SocketIO
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
import cv2
import numpy as np
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user

from config import Config, EmailConfig, MultiCam, Alerts, SMSConfig
from models import Base, EventLog, CrowdSnapshot, User, AlertEvent
from utils import to_meta, send_email, hash_password, verify_password, CooldownClock, ClipRecorder
from tracker import CentroidTracker
from detector import PeopleDetector

# SMS (optional)
try:
    from twilio.rest import Client as TwilioClient
except Exception:
    TwilioClient = None

app = Flask(__name__)
app.config.from_object(Config)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# Database setup
engine = create_engine(app.config["SQLALCHEMY_DATABASE_URI"], echo=False, future=True)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)

# Auth setup
login_manager = LoginManager(app)
login_manager.login_view = "login"

class UserAdapter(UserMixin):
    def __init__(self, u: User):
        self._u = u
    def get_id(self):
        return str(self._u.id)
    @property
    def email(self): return self._u.email
    @property
    def is_admin(self): return self._u.is_admin

@login_manager.user_loader
def load_user(uid):
    with SessionLocal() as s:
        u = s.get(User, int(uid))
        return UserAdapter(u) if u else None

# Bootstrap default admin
with SessionLocal() as s:
    exists = s.execute(select(User).limit(1)).first()
    if not exists:
        admin = User(email="admin@local", password_hash=hash_password("admin"), is_admin=True)
        s.add(admin); s.commit()
        print("Created default admin: admin@local / admin")

# Parse per-camera limits
def parse_crowd_limits(default_limit:int):
    s = MultiCam.CROWD_LIMITS
    if not s:
        return {}
    try:
        if s.strip().startswith("{"):
            return json.loads(s)
        parts = [p.strip() for p in s.split(",") if p.strip()]
        return {str(i): int(v) for i, v in enumerate(parts)}
    except Exception:
        return {}

CROWD_LIMITS = parse_crowd_limits(app.config.get("CROWD_LIMIT", 25))

# Camera manager
class CameraContext:
    def __init__(self, source: str, idx: int):
        self.id = str(idx)
        self.source = source
        self.cap = self._open_source(source)
        self.detector = PeopleDetector(app.config.get("YOLO_MODEL",""))
        self.tracker = CentroidTracker(max_disappeared=15)
        self.prev_gray = None
        fps = int(self.cap.get(cv2.CAP_PROP_FPS) or 20)
        self.state = {"count": 0, "abnormal": 0, "avg_speed": 0.0, "flow_mag": 0.0, "last_frame_ts": time.time()}
        self.cooldown = CooldownClock(Alerts.ALERT_COOLDOWN_SEC)
        self.recorder = ClipRecorder(seconds=Alerts.CLIP_SEC, fps=fps)
        os.makedirs(Alerts.CLIP_DIR, exist_ok=True)

    def _open_source(self, src: str):
        try:
            n = int(src)
            cap = cv2.VideoCapture(n)
        except ValueError:
            cap = cv2.VideoCapture(src)
        return cap

cameras: Dict[str, CameraContext] = {}
for i, src in enumerate(MultiCam.CAMERAS):
    cameras[str(i)] = CameraContext(src, i)

def log_event(level, message, cam_id="0", **meta):
    with SessionLocal() as s:
        ev = EventLog(level=level, message=f"[cam {cam_id}] {message}", count=0, meta=to_meta(meta))
        s.add(ev)
        s.add(AlertEvent(cam_id=str(cam_id), type=level, message=message))
        s.commit()

def save_snapshot(cam_id: str, state: Dict[str, Any]):
    with SessionLocal() as s:
        snap = CrowdSnapshot(count=state["count"], abnormal=state["abnormal"], avg_speed=state["avg_speed"])
        s.add(snap); s.commit()

def camera_limits(cam_id: str) -> int:
    default = app.config.get("CROWD_LIMIT", 25)
    return int(CROWD_LIMITS.get(str(cam_id), default))

def email_alert(subject: str, body: str):
    send_email(
        EmailConfig.SMTP_HOST, EmailConfig.SMTP_PORT, EmailConfig.SMTP_USER, EmailConfig.SMTP_PASS,
        EmailConfig.FROM_ADDR, EmailConfig.TO_ADDRS, subject, body
    )

def sms_alert(body: str):
    if not (SMSConfig.TWILIO_SID and SMSConfig.TWILIO_TOKEN and SMSConfig.TWILIO_FROM and SMSConfig.SMS_TO and TwilioClient):
        return
    try:
        client = TwilioClient(SMSConfig.TWILIO_SID, SMSConfig.TWILIO_TOKEN)
        client.messages.create(body=body, from_=SMSConfig.TWILIO_FROM, to=SMSConfig.SMS_TO)
    except Exception as e:
        print("SMS error:", e)

def gen_frames(cam_id: str):
    ctx = cameras[cam_id]
    while True:
        ok, frame = ctx.cap.read()
        if not ok:
            time.sleep(0.25)
            ctx.cap.release()
            ctx.cap = ctx._open_source(ctx.source)
            continue

        # buffer for clip recorder
        ctx.recorder.push(frame)

        # detection
        boxes = ctx.detector.infer(frame)
        bbs = [(x1,y1,x2,y2) for (x1,y1,x2,y2,conf) in boxes]
        objects, speeds = ctx.tracker.update(bbs)
        count = len(objects)
        avg_speed = float(np.mean(list(speeds.values()))) if speeds else 0.0

        # optical flow magnitude
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        flow_mag = 0.0
        if ctx.prev_gray is not None:
            flow = cv2.calcOpticalFlowFarneback(ctx.prev_gray, gray, None, 0.5,3,15,3,5,1.2,0)
            mag, ang = cv2.cartToPolar(flow[...,0], flow[...,1])
            flow_mag = float(np.mean(mag))
        ctx.prev_gray = gray

        abnormal = int(sum(1 for v in speeds.values() if v > app.config["ABNORMAL_SPEED_THRESH"]))
        if flow_mag > (app.config["ABNORMAL_SPEED_THRESH"] * 0.25):
            abnormal = max(abnormal, 1)

        ctx.state.update({"count": count, "abnormal": abnormal, "avg_speed": avg_speed, "flow_mag": flow_mag, "last_frame_ts": time.time()})
        socketio.emit("metrics", {"cam": cam_id, **ctx.state})

        limit = camera_limits(cam_id)
        key_over = f"{cam_id}:over"
        key_abn = f"{cam_id}:abn"
        if count >= limit and ctx.cooldown.ready(key_over):
            msg = f"Crowd exceeded: {count}/{limit}"
            log_event("warning", msg, cam_id, count=count, avg_speed=avg_speed)
            email_alert("Crowd limit exceeded", f"Camera {cam_id}: {msg}")
            sms_alert(f"[Cam {cam_id}] {msg}")
            clip_name = f"clip_{cam_id}_{uuid.uuid4().hex}.mp4"
            ctx.recorder.start(os.path.join(Alerts.CLIP_DIR, clip_name), post_seconds=Alerts.CLIP_POST_SEC)
            ctx.cooldown.mark(key_over)
        if abnormal > 0 and ctx.cooldown.ready(key_abn):
            msg = f"Abnormal motion: tracks={abnormal}, flow={flow_mag:.2f}"
            log_event("info", msg, cam_id, abnormal=abnormal, flow=flow_mag)
            email_alert("Abnormal movement detected", f"Camera {cam_id}: {msg}")
            sms_alert(f"[Cam {cam_id}] {msg}")
            clip_name = f"clip_{cam_id}_{uuid.uuid4().hex}.mp4"
            ctx.recorder.start(os.path.join(Alerts.CLIP_DIR, clip_name), post_seconds=Alerts.CLIP_POST_SEC)
            ctx.cooldown.mark(key_abn)

        vis = ctx.detector.draw(frame.copy(), boxes)
        banner = f"Cam {cam_id} | Count:{count} | Abn:{abnormal} | AvgSpd:{avg_speed:.1f} | Flow:{flow_mag:.2f}"
        cv2.putText(vis, banner, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 4, cv2.LINE_AA)
        cv2.putText(vis, banner, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2, cv2.LINE_AA)

        ret, buffer = cv2.imencode('.jpg', vis)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

from flask_login import login_required

@app.get("/")
@login_required
def dashboard():
    cam_ids = list(cameras.keys())
    return render_template("dashboard.html", crowd_limit=app.config["CROWD_LIMIT"], cams=cam_ids)

@app.get("/stream/<cam_id>")
@login_required
def stream(cam_id):
    if cam_id not in cameras:
        return "Camera not found", 404
    return Response(gen_frames(cam_id), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.get("/api/snapshots/<cam_id>")
@login_required
def api_snapshots(cam_id):
    with SessionLocal() as s:
        rows = s.execute(select(CrowdSnapshot).order_by(CrowdSnapshot.id.desc()).limit(200)).scalars().all()
        rows = list(reversed(rows))
        data = [{
            "t": r.created_at.isoformat(),
            "count": r.count,
            "abnormal": r.abnormal,
            "avg_speed": r.avg_speed,
        } for r in rows]
    return jsonify(data)

@app.get("/events")
@login_required
def events():
    with SessionLocal() as s:
        rows = s.execute(select(EventLog).order_by(EventLog.id.desc()).limit(100)).scalars().all()
        data = [{
            "t": r.created_at.isoformat(),
            "level": r.level,
            "message": r.message,
        } for r in rows]
    return jsonify(data)

# --- Auth routes ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip()
        password = request.form.get("password","")
        with SessionLocal() as s:
            u = s.execute(select(User).where(User.email==email)).scalar_one_or_none()
            if u and verify_password(u.password_hash, password):
                login_user(UserAdapter(u))
                return redirect(url_for("dashboard"))
        flash("Invalid credentials", "error")
    return render_template("login.html")

@app.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

def save_snapshot(cam_id: str, state: Dict[str, Any]):
    with SessionLocal() as s:
        snap = CrowdSnapshot(count=state["count"], abnormal=state["abnormal"], avg_speed=state["avg_speed"])
        s.add(snap); s.commit()

def snapshot_worker():
    while True:
        for cam_id, ctx in cameras.items():
            save_snapshot(cam_id, ctx.state)
        time.sleep(5)

@socketio.on("connect")
def on_connect():
    for cam_id, ctx in cameras.items():
        socketio.emit("metrics", {"cam": cam_id, **ctx.state})

if __name__ == "__main__":
    thr = threading.Thread(target=snapshot_worker, daemon=True)
    thr.start()
    socketio.run(app, host="0.0.0.0", port=5000)
