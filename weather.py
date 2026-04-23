import datetime
import requests

import state as st

from heartbeat import write_heartbeat
WEATHER_HEARTBEAT = "/opt/greenhouse/weather_heartbeat.json"

UPDATE_INTERVAL_MINUTES = 30
_last_update = {}
_last_error = {}


def _should_update(gh_id: str):
  lu = _last_update.get(gh_id)
  if lu is None:
    return True
  delta = (datetime.datetime.utcnow() - lu).total_seconds() / 60.0
  return delta >= UPDATE_INTERVAL_MINUTES


def update_weather(gh_id: str, gh_cfg: dict):
  if not _should_update(gh_id):
    return

  write_heartbeat(WEATHER_HEARTBEAT)

  api_key = gh_cfg.get("weather", {}).get("api_key")
  lat = gh_cfg.get("weather", {}).get("lat")
  lon = gh_cfg.get("weather", {}).get("lon")
  if not api_key or lat is None or lon is None:
    _last_error[gh_id] = "Weather config incomplete"
    return

  url = (
    "https://api.openweathermap.org/data/2.5/forecast"
    f"?lat={lat}&lon={lon}&appid={api_key}&units=imperial"
  )

  try:
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()
  except Exception as e:
    _last_error[gh_id] = str(e)
    return

  now = datetime.datetime.utcnow()
  next_24h = []
  daily = {}

  for item in data.get("list", []):
    ts = datetime.datetime.utcfromtimestamp(item["dt"])
    if ts > now + datetime.timedelta(hours=24):
      continue

    temp = item["main"]["temp"]
    hum = item["main"]["humidity"]
    clouds = item["clouds"]["all"]
    wind = item["wind"]["speed"]
    pop = item.get("pop", 0.0)

    next_24h.append({
      "time": ts.isoformat(),
      "temp": temp,
      "humidity": hum,
      "clouds": clouds,
      "wind": wind,
      "pop": pop
    })

    day_key = ts.date().isoformat()
    if day_key not in daily:
      daily[day_key] = {
        "temp_min": temp,
        "temp_max": temp,
        "humidity_min": hum,
        "humidity_max": hum,
        "clouds_avg_sum": clouds,
        "clouds_count": 1,
        "pop_max": pop
      }
    else:
      d = daily[day_key]
      d["temp_min"] = min(d["temp_min"], temp)
      d["temp_max"] = max(d["temp_max"], temp)
      d["humidity_min"] = min(d["humidity_min"], hum)
      d["humidity_max"] = max(d["humidity_max"], hum)
      d["clouds_avg_sum"] += clouds
      d["clouds_count"] += 1
      d["pop_max"] = max(d["pop_max"], pop)

  daily_simplified = []
  for day_key, d in sorted(daily.items()):
    daily_simplified.append({
      "day": day_key,
      "temp_min": d["temp_min"],
      "temp_max": d["temp_max"],
      "humidity_min": d["humidity_min"],
      "humidity_max": d["humidity_max"],
      "clouds_avg": d["clouds_avg_sum"] / d["clouds_count"],
      "pop_max": d["pop_max"]
    })

  gh = st.greenhouses[gh_id]
  gh["weather_forecast"] = {
    "updated": datetime.datetime.utcnow().isoformat(),
    "next_24h": next_24h,
    "daily": daily_simplified,
    "error": None
  }
  _last_update[gh_id] = datetime.datetime.utcnow()
  _last_error[gh_id] = None
