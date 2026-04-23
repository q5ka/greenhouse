import datetime

import state as st
import mqtt_client as mq


def irrigation_start_sequence(gh_id: str, zone_index: int, duration_sec: int):
  gh = st.greenhouses[gh_id]
  sm = gh["irrigation_sm"]
  sm["state"] = "WATERING"
  sm["zone"] = zone_index
  sm["start_time"] = datetime.datetime.utcnow()
  sm["duration"] = duration_sec
  mq.send_cmd(gh_id, f"irrigation/zone{zone_index+1}/cmd", "ON")


def irrigation_step(gh_id: str, gh_cfg: dict):
  gh = st.greenhouses[gh_id]
  sm = gh["irrigation_sm"]
  if sm["state"] != "WATERING":
    return

  now = datetime.datetime.utcnow()
  elapsed = (now - sm["start_time"]).total_seconds()
  if elapsed >= sm["duration"]:
    zone = sm["zone"]
    mq.send_cmd(gh_id, f"irrigation/zone{zone+1}/cmd", "OFF")
    sm["state"] = "IDLE"


def run_irrigation_logic(gh_id: str, gh_cfg: dict, rain_soon: bool):
  if rain_soon:
    return

  gh = st.greenhouses[gh_id]
  sm = gh["irrigation_sm"]
  if sm["state"] != "IDLE":
    return

  ir = gh_cfg["irrigation"]
  s = gh["state"]

  for i in range(8):
    if not ir["auto"][i]:
      continue
    if i in sm["faulted_zones"]:
      continue
    moisture = s["moisture"][i]
    if moisture is None:
      continue
    thr = ir["thresholds"][i]
    dur = ir["durations"][i]
    if moisture < thr:
      irrigation_start_sequence(gh_id, i, dur)
      break
