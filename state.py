import datetime

greenhouses = {}  # gh_id -> state bundle


def init_greenhouse_state(gh_id: str, gh_cfg: dict):
    if gh_id in greenhouses:
        return

    caps = gh_cfg.get("capabilities", {})

    vents = caps.get("vents", 0)
    zones = caps.get("irrigation_zones", 0)

    greenhouses[gh_id] = {
        "state": {
            "t_z1": None, "h_z1": None,
            "t_z2": None, "h_z2": None,
            "t_out": None, "h_out": None,
            "light": None,
            "presence": 0 if caps.get("has_presence", False) else None,
            "moisture": [None] * zones,
            "valve_state": ["OFF"] * zones,
            "vent_states": ["STOPPED"] * vents,
            "lights_state": "OFF" if caps.get("has_lighting", False) else None
        },

        "daily_light_minutes": {},
        "irrigation_sm": {
            "state": "IDLE",
            "zone": None,
            "start_time": None,
            "duration": None,
            "post_wait_sec": 60,
            "vent_close_timeout_sec": 120,
            "valve_off_timeout_sec": 300,
            "faulted_zones": set()
        },

        "presence_last_change": None,
        "presence_current": 0 if caps.get("has_presence", False) else None,

        "vent_last_cmd": {i+1: None for i in range(vents)},
        "vent_last_state_change": {i+1: None for i in range(vents)},
        "vent_faults": {i+1: False for i in range(vents)},

        "mqtt_connected": False,
        "last_mqtt_message_time": None,

        "weather_forecast": {
            "updated": None,
            "next_24h": [],
            "daily": [],
            "error": None
        }
    }


def update_presence(gh_id: str, new_val: int):
  gh = greenhouses[gh_id]
  if new_val != gh["presence_current"]:
    gh["presence_current"] = new_val
    gh["presence_last_change"] = datetime.datetime.utcnow()


def mark_mqtt_message(gh_id: str):
  gh = greenhouses[gh_id]
  gh["last_mqtt_message_time"] = datetime.datetime.utcnow()
