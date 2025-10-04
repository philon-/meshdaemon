from __future__ import annotations
import os

# Meshtastic LAN UDP
MCAST_GRP: str = os.getenv("MESHTASTIC_MCAST_GRP", "224.0.0.69")
MCAST_PORT: int = int(os.getenv("MESHTASTIC_MCAST_PORT", "4403"))

# Node identity
MESHTASTIC_NODE_ID: str = os.getenv("MESHTASTIC_NODE_ID", "!112")
MESHTASTIC_LONG_NAME: str = os.getenv("MESHTASTIC_LONG_NAME", "VMA ROBOT")
MESHTASTIC_SHORT_NAME: str = os.getenv("MESHTASTIC_SHORT_NAME", "VMA")
MESHTASTIC_CHANNEL: str = os.getenv("MESHTASTIC_CHANNEL", "MediumFast")
MESHTASTIC_KEY: str = os.getenv("MESHTASTIC_KEY", "AQ==")  # Default key
MESHTASTIC_HOP_LIMIT: int = int(os.getenv("MESHTASTIC_HOP_LIMIT", "5"))
MESHTASTIC_MAX_BYTES = int(os.getenv("MESHTASTIC_MAX_BYTES", "200"))
MESHTASTIC_MAX_MESSAGES = int(os.getenv("MESHTASTIC_MAX_MESSAGES", "2"))

MESHTASTIC_NODEINFO_INTERVAL: int = int(os.getenv("NODEINFO_INTERVAL_SECS", "43200"))  # 43200s / 12h default

# Dedupe TTL (seconds), how long to remember "seen" messages. 
# For some sources that have long standing warnings, this means messages are repeated every TTL seconds.
SEEN_TTL_SECS: float = float(os.getenv("SEEN_TTL_SECS", "86400")) # 86400s / 24h default

# Sources
VMA_URL: str = os.getenv("VMA_URL", "https://vmaapi.sr.se/api/v3/alerts")
VMA_INTERVAL: int = int(os.getenv("VMA_INTERVAL", "60"))
VMA_GEOCODE: str = os.getenv("VMA_GEOCODE", "01")  # 01 is Stockholm

SMHI_URL: str = os.getenv("SMHI_URL", "https://opendata-download-warnings.smhi.se/ibww/api/version/1/warning.json")
SMHI_INTERVAL: int = int(os.getenv("SMHI_INTERVAL", "60"))
SMHI_GEOCODE: int = int(os.getenv("SMHI_GEOCODE", "1"))  # 1 is Stockholm, defined here https://opendata-download-warnings.smhi.se/ibww/api/version/1/metadata/area.json

HOLD_WINDOW_SECS: int = int(os.getenv("HOLD_WINDOW_SECS", "60"))  # seconds; 0 disables hold-off
INSTANCE_SALT: str | None = os.getenv("INSTANCE_SALT")  # Optional salt for hold-off, if not set uses the device MAC address
WARMUP: bool = os.getenv("WARMUP", "1") == "1"  # If true, skip sending messages for the first fetch of each source.

MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))  # perform 3 attempts
BASE_BACKOFF: int = int(os.getenv("BASE_BACKOFF", "2"))  # base backoff in seconds

MAX_RESTART_INTERVAL: int = int(os.getenv("MAX_RESTART_INTERVAL", "60"))  # restart throttling interval in seconds
RESTART_HISTORY: int = int(os.getenv("RESTART_HISTORY", "5"))  # number of restarts in the interval to trigger stop