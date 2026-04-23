#!/usr/bin/env python3
import json, os, time, subprocess
from datetime import datetime, timezone

SERVICE_NAME = "greenhouse.service"

def read_timestamp(path):
    try:
        with open(path, "r") as f:
            data = json.load(f)
            return datetime.fromisoformat(data["last_update"].replace("Z", "+00:00"))
    except:
        return None

def too_old(ts, seconds):
    if ts is None:
        return True
    return (datetime.now(timezone.utc) - ts).total_seconds() > seconds

def restart_service():
    subprocess.run(["systemctl", "restart", SERVICE_NAME])

def log(msg):
    print(f"[WATCHDOG] {msg}", flush=True)

while True:
    try:
        main_ts = read_timestamp("/opt/greenhouse/heartbeat.json")
        mqtt_ts = read_timestamp("/opt/greenhouse/mqtt_heartbeat.json")
        weather_ts = read_timestamp("/opt/greenhouse/weather_heartbeat.json")

        # Camera checks
        camera_dirs = [
            "/opt/greenhouse/data/camera/main",
            "/opt/greenhouse/data/camera/little_one"
        ]

        camera_fail = False
        for d in camera_dirs:
            ts_path = os.path.join(d, "last_frame.txt")
            if os.path.exists(ts_path):
                cam_ts = read_timestamp(ts_path)
                if too_old(cam_ts, 120):
                    camera_fail = True

        if too_old(main_ts, 60):
            log("Main heartbeat stale → restarting service")
            restart_service()

        elif too_old(mqtt_ts, 60):
            log("MQTT heartbeat stale → restarting service")
            restart_service()

        elif too_old(weather_ts, 600):
            log("Weather worker stale → restarting service")
            restart_service()

        elif camera_fail:
            log("Camera worker stale → restarting service")
            restart_service()

        else:
            log("All systems healthy")

    except Exception as e:
        log(f"Watchdog error: {e}")

    time.sleep(30)
