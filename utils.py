import json, smtplib, ssl, time, cv2
from collections import deque
from email.mime.text import MIMEText
from email.utils import formatdate
from werkzeug.security import generate_password_hash, check_password_hash

def to_meta(d: dict) -> str:
    try:
        return json.dumps(d)
    except Exception:
        return ""

def hash_password(p: str) -> str:
    return generate_password_hash(p)

def verify_password(h: str, p: str) -> bool:
    try:
        return check_password_hash(h, p)
    except Exception:
        return False

def send_email(smtp_host, smtp_port, smtp_user, smtp_pass, from_addr, to_addrs, subject, body):
    if not smtp_host or not to_addrs:
        return False, "SMTP not configured or no recipients"
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg["Date"] = formatdate(localtime=True)
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls(context=context)
            if smtp_user:
                server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, to_addrs, msg.as_string())
        return True, "sent"
    except Exception as e:
        return False, str(e)

class CooldownClock:
    def __init__(self, seconds: float = 60.0):
        self.seconds = seconds
        self._last = {}
    def ready(self, key: str) -> bool:
        now = time.time()
        last = self._last.get(key, 0.0)
        return (now - last) >= self.seconds
    def mark(self, key: str):
        self._last[key] = time.time()

class ClipRecorder:
    # Ring buffer of frames; write MP4 clips around alert events.
    def __init__(self, seconds=10, fps=20):
        self.seconds = seconds
        self.fps = fps
        self.maxlen = int(seconds * fps)
        self.buf = deque(maxlen=self.maxlen)
        self.recording = False
        self.out = None
        self.frames_left = 0
        self.size = None

    def push(self, frame):
        h, w = frame.shape[:2]
        self.size = (w, h)
        self.buf.append(frame.copy())
        if self.recording and self.out is not None:
            self.out.write(frame)
            self.frames_left -= 1
            if self.frames_left <= 0:
                self.stop()

    def start(self, path: str, post_seconds=5):
        if self.size is None: return
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.out = cv2.VideoWriter(path, fourcc, self.fps, self.size)
        for f in list(self.buf):
            self.out.write(f)
        self.recording = True
        self.frames_left = int(post_seconds * self.fps)

    def stop(self):
        if self.out is not None:
            self.out.release()
        self.out = None
        self.recording = False
        self.frames_left = 0
