import json
import os
from datetime import datetime, timezone, timedelta

MAIN_HEARTBEAT = "/opt/greenhouse/heartbeat.json"
MQTT_HEARTBEAT = "/opt/greenhouse/mqtt_heartbeat.json"
WEATHER_HEARTBEAT = "/opt/greenhouse/weather_heartbeat.json"

CAMERA_BASE = "/opt/greenhouse/data/camera"

# Thresholds (seconds)
THRESHOLDS = {
    "main": 60,
    "mqtt": 60,
    "weather": 600,
    "camera": 120
}

def read_timestamp(path):
    """Return datetime or None."""
    try:
        with open(path, "r") as f:
            data = json.load(f)
            ts = data.get("last_update")
            if not ts:
                return None
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except:
        return None

def status_from_timestamp(ts, max_age_sec):
    """Return OK, STALE, or MISSING."""
    if ts is None:
        return "MISSING"
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    if age <= max_age_sec:
        return "OK"
    return "STALE"

def get_camera_status(gh_id):
    """Check camera heartbeat for a specific greenhouse."""
    hb_path = os.path.join(CAMERA_BASE, gh_id, "last_frame.txt")
    ts = read_timestamp(hb_path)
    return status_from_timestamp(ts, THRESHOLDS["camera"])

def get_health_summary(greenhouses):
    """Return a full health summary for all systems."""
    summary = {}

    # Main loop
    main_ts = read_timestamp(MAIN_HEARTBEAT)
    summary["main_loop"] = status_from_timestamp(main_ts, THRESHOLDS["main"])

    # MQTT
    mqtt_ts = read_timestamp(MQTT_HEARTBEAT)
    summary["mqtt"] = status_from_timestamp(mqtt_ts, THRESHOLDS["mqtt"])

    # Weather
    weather_ts = read_timestamp(WEATHER_HEARTBEAT)
    summary["weather"] = status_from_timestamp(weather_ts, THRESHOLDS["weather"])

    # Cameras (per greenhouse)
    cam_status = {}
    for gh_id in greenhouses:
        cam_status[gh_id] = get_camera_status(gh_id)
    summary["cameras"] = cam_status

    return summary
