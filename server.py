import json
import asyncio
import threading
from fastapi import FastAPI, Body, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from fastapi import FastAPI, Body, Query, HTTPException
import uvicorn
from camera_manager import CameraManager
import state as st
import storage
import mqtt_client as mq
from automation.vent import run_vent_logic
from automation.irrigation import run_irrigation_logic, irrigation_step
from automation.lighting import run_lighting_logic
from presence import presence_allows_irrigation
import health
import notifications
import weather
import time
from heartbeat import write_heartbeat
from health_monitor import get_health_summary
CONFIG_PATH = "/opt/greenhouse/config.json"

HEARTBEAT_PATH = "/opt/greenhouse/data/heartbeat.json"

with open("config.json") as f:
  config = json.load(f)

for gh_id, gh_cfg in config["greenhouses"].items():
    st.init_greenhouse_state(gh_id, gh_cfg)


def _rain_expected(gh_id: str, gh_cfg: dict) -> bool:
  wl = gh_cfg.get("weather_logic", {})
  rain_pop_threshold = wl.get("rain_pop_threshold", 0.6)
  wf = st.greenhouses[gh_id]["weather_forecast"]
  next_24h = wf.get("next_24h", [])
  for item in next_24h:
    if item["pop"] >= rain_pop_threshold:
      return True
  return False


async def automation_loop():
    while True:
        # Update main heartbeat
        write_heartbeat(HEARTBEAT_PATH)

        # Run automation every 10 seconds
        await asyncio.sleep(10)

        for gh_id, gh_cfg in config["greenhouses"].items():
            gh = st.greenhouses[gh_id]

            # Weather update heartbeat is inside weather.update_weather()
            weather.update_weather(gh_id, gh_cfg)

            run_vent_logic(gh_id, gh_cfg)

            rain_soon = _rain_expected(gh_id, gh_cfg)

            if presence_allows_irrigation(gh_id, gh_cfg) and gh["irrigation_sm"]["state"] == "IDLE":
                run_irrigation_logic(gh_id, gh_cfg, rain_soon)

            irrigation_step(gh_id, gh_cfg)
            run_lighting_logic(gh_id, gh_cfg)
            notifications.check_and_notify(gh_id, gh_cfg)


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
def dashboard():
  with open("static/dashboard.html") as f:
    return f.read()


@app.get("/api/state")
def get_state(gh: str = Query("main")):
  gh_cfg = config["greenhouses"][gh]
  gh_state = st.greenhouses[gh]
  return {
    "gh_id": gh,
    "gh_name": gh_cfg.get("name", gh),
    **gh_state["state"],
    "irrigation_sm": gh_state["irrigation_sm"],
    "daily_light_minutes": gh_state["daily_light_minutes"],
    "config": gh_cfg,
    "mqtt_connected": gh_state["mqtt_connected"],
    "vent_faults": gh_state["vent_faults"],
    "irrigation_faulted_zones": list(gh_state["irrigation_sm"]["faulted_zones"]),
    "weather": gh_state["weather_forecast"]
  }


@app.get("/api/health")
def api_health(gh: str = Query("main")):
  return health.get_health(gh)


@app.get("/api/config")
def api_get_config(gh: str = Query("main")):
    gh_cfg = config["greenhouses"].get(gh)
    if not gh_cfg:
        raise HTTPException(status_code=404, detail="Unknown greenhouse")
    return gh_cfg

@app.post("/api/config")
def api_set_config(gh: str, body: dict):
    if gh not in config["greenhouses"]:
        raise HTTPException(status_code=404, detail="Unknown greenhouse")
    config["greenhouses"][gh] = body
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
    global camera_manager
    camera_manager = CameraManager(config)
    return {"status": "ok"}


@app.get("/api/history")
def api_history(key: str, hours: int = 24):
  return storage.get_history(key, hours)

@app.get("/api/capabilities")
def api_capabilities(gh: str = Query("main")):
    gh_cfg = config["greenhouses"][gh]
    return {
        "gh_id": gh,
        "name": gh_cfg.get("name", gh),
        "capabilities": gh_cfg.get("capabilities", {})
    }


@app.post("/api/vent/{zone}/cmd")
def vent_cmd(zone: int, body: dict = Body(...), gh: str = Query("main")):
  cmd = body.get("cmd", "").upper()
  if zone not in [1, 2]:
    return {"status": "error"}
  mq.send_cmd(gh, f"climate/vents/zone{zone}/cmd", cmd)
  return {"status": "ok"}


@app.post("/api/irrigation/{zone}/cmd")
def irrigation_cmd(zone: int, body: dict = Body(...), gh: str = Query("main")):
  z = zone - 1
  if z < 0 or z > 7:
    return {"status": "error"}
  cmd = body.get("cmd", "").upper()
  if cmd == "WATER_ONCE":
    duration = int(body.get("duration", 60))
    from automation.irrigation import irrigation_start_sequence
    irrigation_start_sequence(gh, z, duration)
  elif cmd in ["ON", "OFF", "AUTO"]:
    mq.send_cmd(gh, f"irrigation/zone{zone}/cmd", cmd)
  return {"status": "ok"}


@app.post("/api/lights/cmd")
def lights_cmd(body: dict = Body(...), gh: str = Query("main")):
  cmd = body.get("cmd", "").upper()
  if cmd in ["ON", "OFF"]:
    mq.send_cmd(gh, "lights/cmd", cmd)
  return {"status": "ok"}


@app.get("/api/camera/live")
def api_camera_live(gh: str = Query("main")):
    cc = camera_manager.configs.get(gh)
    if not cc or not cc.enabled:
        raise HTTPException(status_code=404, detail="Camera not enabled")

    import requests

    def stream():
        url = camera_manager._stream_url(cc)
        with requests.get(url, stream=True) as r:
            for chunk in r.iter_content(chunk_size=1024):
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(stream(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/camera/timelapse/list")
def api_camera_timelapse_list(gh: str, date: str):
    files = camera_manager.list_timelapse(gh, date)
    return {"files": files}


@app.get("/api/camera/timelapse/frame")
def api_camera_timelapse_frame(gh: str, path: str):
    data = camera_manager.get_timelapse_frame(gh, path)
    if not data:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(content=data, media_type="image/jpeg")


@app.get("/api/camera/motion/list")
def api_camera_motion_list(gh: str):
    files = camera_manager.list_motion(gh)
    return {"files": files}


@app.get("/api/camera/motion/video")
def api_camera_motion_video(gh: str, path: str):
    normalized_path = camera_manager._validate_rel_media_path(path, (".mp4",))
    if not normalized_path:
        raise HTTPException(status_code=400, detail="Invalid path")
    data = camera_manager.get_motion_video(gh, normalized_path)
    if not data:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(content=data, media_type="video/mp4")


@app.get("/api/health/full")
def api_health_full():
    gh_ids = list(config["greenhouses"].keys())
    return get_health_summary(gh_ids)
  

def start_asyncio_loop():
  asyncio.run(automation_loop())


mq.start()
threading.Thread(target=start_asyncio_loop, daemon=True).start()

if __name__ == "__main__":
  uvicorn.run(app, host="0.0.0.0", port=8000)
