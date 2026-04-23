import datetime

import state as st
import storage


def get_health(gh_id: str):
  gh = st.greenhouses[gh_id]

  now = datetime.datetime.utcnow()
  mqtt_ok = gh["last_mqtt_message_time"] is not None and (now - gh["last_mqtt_message_time"]).total_seconds() < 60

  sensors_fresh = mqtt_ok  # simple proxy

  vents_ok = not any(gh["vent_faults"].values())
  irrigation_ok = len(gh["irrigation_sm"]["faulted_zones"]) == 0

  queue_len = storage.get_queue_length()
  db_ok = queue_len < 1000

  return {
    "overall": {
      "mqtt_ok": mqtt_ok,
      "sensors_fresh": sensors_fresh,
      "vents_ok": vents_ok,
      "irrigation_ok": irrigation_ok,
      "db_ok": db_ok
    },
    "vents": gh["vent_faults"],
    "irrigation": list(gh["irrigation_sm"]["faulted_zones"]),
    "storage": {
      "queue_length": queue_len
    }
  }
