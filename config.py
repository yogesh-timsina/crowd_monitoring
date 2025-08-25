import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///crowd.db")
    YOLO_MODEL = os.getenv("YOLO_MODEL", "")
    CROWD_LIMIT = int(os.getenv("CROWD_LIMIT", "25"))
    ABNORMAL_SPEED_THRESH = float(os.getenv("ABNORMAL_SPEED_THRESH", "8.5"))

class EmailConfig:
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASS = os.getenv("SMTP_PASS", "")
    FROM_ADDR = os.getenv("FROM_ADDR", "alerts@example.com")
    TO_ADDRS = os.getenv("TO_ADDRS", "").split(",") if os.getenv("TO_ADDRS") else []

class MultiCam:
    CAMERAS = [c.strip() for c in os.getenv("CAMERAS", "0").split(",") if c.strip()]
    CROWD_LIMITS = os.getenv("CROWD_LIMITS", "")  # json or "30,40,..."

class Alerts:
    ALERT_COOLDOWN_SEC = int(os.getenv("ALERT_COOLDOWN_SEC", "60"))
    CLIP_DIR = os.getenv("CLIP_DIR", "clips")
    CLIP_SEC = int(os.getenv("CLIP_SEC", "10"))
    CLIP_POST_SEC = int(os.getenv("CLIP_POST_SEC", "5"))

class SMSConfig:
    TWILIO_SID = os.getenv("TWILIO_SID", "")
    TWILIO_TOKEN = os.getenv("TWILIO_TOKEN", "")
    TWILIO_FROM = os.getenv("TWILIO_FROM", "")
    SMS_TO = os.getenv("SMS_TO", "")
