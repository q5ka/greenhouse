import datetime

import state as st
import mqtt_client as mq

VENT_MIN_HOLD_SEC = 60
VENT_STUCK_TIMEOUT_SEC = 180


def _can_change_vent(gh, zone, now):
  last_cmd = gh["vent_last_cmd"][zone]
  if last_cmd is None:
    return True
  return (now - last_cmd).total_seconds() >= VENT_MIN_HOLD_SEC


def _mark_vent_cmd(gh, zone, now):
  gh["vent_last_cmd"][zone] = now


def _check_vent_stuck(gh, zone, now):
  last_cmd = gh["vent_last_cmd"][zone]
  last_change = gh["vent_last_state_change"][zone]
  if last_cmd is None:
    return
  if last_change is None:
    if (now - last_cmd).total_seconds() > VENT_STUCK_TIMEOUT_SEC:
      gh["vent_faults"][zone] = True
    return
  if last_change < last_cmd and (now - last_cmd).total_seconds() > VENT_STUCK_TIMEOUT_SEC:
    gh["vent_faults"][zone] = True


def _get_weather_flags(gh, gh_cfg):
  wl = gh_cfg.get("weather_logic", {})
  hot_day_temp = wl.get("hot_day_temp", 90)
  storm_pop_threshold = wl.get("storm_pop_threshold", 0.7)
  high_wind_speed = wl.get("high_wind_speed", 20)

  wf = gh["weather_forecast"]
  next_24h = wf.get("next_24h", [])
  daily = wf.get("daily", [])

  is_hot_day = False
  storm_risk = False
  high_wind = False

  if daily:
    today = daily[0]
    if today["temp_max"] >= hot_day_temp:
      is_hot_day = True
    if today["pop_max"] >= storm_pop_threshold:
      storm_risk = True

  for item in next_24h:
    if item["wind"] >= high_wind_speed:
      high_wind = True
      break

  return {
    "is_hot_day": is_hot_day,
    "storm_risk": storm_risk,
    "high_wind": high_wind
  }


def run_vent_logic(gh_id: str, gh_cfg: dict):
  now = datetime.datetime.utcnow()
  gh = st.greenhouses[gh_id]
  s = gh["state"]

  t_out = s["t_out"]
  h_out = s["h_out"]

  irrigation_active = gh["irrigation_sm"]["state"] != "IDLE"

  wf_flags = _get_weather_flags(gh, gh_cfg)
  wl = gh_cfg.get("weather_logic", {})
  pre_cool_margin = wl.get("pre_cool_margin_deg", 2)

  for zone in [1, 2]:
    t_in = s[f"t_z{zone}"]
    h_in = s[f"h_z{zone}"]

    if t_in is None or t_out is None or h_in is None or h_out is None:
      continue

    cfg = gh_cfg["vent"][f"zone{zone}"]
    if not cfg["auto"]:
      continue
    if gh["vent_faults"][zone]:
      continue
    if not _can_change_vent(gh, zone, now):
      continue

    open_temp = cfg["open_temp"]
    close_temp = cfg["close_temp"]
    delta_out = cfg["delta_outside"]

    should_open = (t_in > open_temp and (t_in - t_out) > delta_out)
    should_open = should_open or (h_in > 80 and h_in > h_out + 5)

    should_close = (
      t_in < close_temp or
      t_out > t_in or
      irrigation_active or
      h_in < 30
    )

    if wf_flags["is_hot_day"] and not irrigation_active:
      if t_in > (open_temp - pre_cool_margin) and t_in > t_out:
        should_open = True

    if wf_flags["storm_risk"] or wf_flags["high_wind"]:
      should_open = False
      should_close = True

    if should_open and not irrigation_active:
      mq.send_cmd(gh_id, f"climate/vents/zone{zone}/cmd", "OPEN")
      _mark_vent_cmd(gh, zone, now)
    elif should_close:
      mq.send_cmd(gh_id, f"climate/vents/zone{zone}/cmd", "CLOSE")
      _mark_vent_cmd(gh, zone, now)

    _check_vent_stuck(gh, zone, now)
