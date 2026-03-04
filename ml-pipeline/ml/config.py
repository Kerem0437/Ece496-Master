import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def _expand(p: str) -> str:
    return os.path.expanduser(p) if p else p

@dataclass(frozen=True)
class Settings:
    # MQTT
    mqtt_host: str = os.getenv("MQTT_HOST", "192.168.56.108")
    mqtt_port: int = int(os.getenv("MQTT_PORT", "1883"))
    mqtt_topic: str = os.getenv("MQTT_TOPIC", "demo/496/chat")
    mqtt_tls: bool = os.getenv("MQTT_TLS", "true").lower() == "true"
    cert_dir: str = _expand(os.getenv("CERT_DIR", "~/certs"))
    mqtt_hmac_key: str = os.getenv("MQTT_HMAC_KEY", "")

    # Influx
    influx_url: str = os.getenv("INFLUX_URL", "http://127.0.0.1:8086")
    influx_org: str = os.getenv("INFLUX_ORG", "ECE496")
    influx_bucket: str = os.getenv("INFLUX_BUCKET", "capstone")
    influx_measurement: str = os.getenv("INFLUX_MEASUREMENT", "mqtt_sensor")
    influx_query_token: str = os.getenv("INFLUX_QUERY_TOKEN", "")
    influx_write_token: str = os.getenv("INFLUX_WRITE_TOKEN", "")

    # ML
    ml_version: str = os.getenv("ML_VERSION", "lstm_v1.0.0")
    seq_len: int = int(os.getenv("SEQ_LEN", "60"))
    resample_rule: str = os.getenv("RESAMPLE_RULE", "1min")
    gap_split_min: int = int(os.getenv("GAP_SPLIT_MIN", "5"))
    min_points: int = int(os.getenv("MIN_POINTS", "30"))
    thresh_normal: float = float(os.getenv("THRESH_NORMAL", "0.30"))
    thresh_suspicious: float = float(os.getenv("THRESH_SUSPICIOUS", "0.70"))

SETTINGS = Settings()
