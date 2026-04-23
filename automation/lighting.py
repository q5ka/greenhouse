import datetime

import state as st
import mqtt_client as mq


def _cloud_factor(gh):
  wf = gh["weather_forecast"]
  daily = wf.get("daily", [])
  if not daily:
    return 0.0
  today = daily[0]
  clouds = today.get("clouds_avg", 0)
  return max(0.0, min(1.0, clouds / 100.0))


def run_lighting_logic(gh_id: str, gh_cfg: dict):
  gh = st.greenhouses[gh_id]
  s = gh["state"]
  brightness = s["light"]
  if brightness is None:
    return

  now = datetime.datetime.now()
  date_key = now.date().isoformat()
  if date_key not in gh["daily_light_minutes"]:
    gh["daily_light_minutes"][date_key] = 0

  if brightness > gh_cfg["lighting"]["brightness_threshold"]:
    gh["daily_light_minutes"][date_key] += 1

  base_target_minutes = gh_cfg["lighting"]["daily_target_hours"] * 60
  max_supp_hours = gh_cfg["lighting"].get("max_supplemental_hours", 6)
  cloudy_factor = _cloud_factor(gh)

  extra_minutes = int(max_supp_hours * 60 * cloudy_factor)
  target_minutes = base_target_minutes + extra_minutes

  current_minutes = gh["daily_light_minutes"][date_key]

  if current_minutes < target_minutes:
    mq.send_cmd(gh_id, "lights/cmd", "ON")
  else:
    mq.send_cmd(gh_id, "lights/cmd", "OFF")
