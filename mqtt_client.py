import threading
import paho.mqtt.client as mqtt
import datetime
import time
import storage
import state as st

from heartbeat import write_heartbeat
MQTT_HEARTBEAT = "/opt/greenhouse/data/mqtt_heartbeat.json"

MQTT_BROKER = "192.168.1.100"
MQTT_PORT = 1883

client = mqtt.Client()


def encode_vent_state_numeric(gh_id: str, vent_name: str, state_str: str):
  mapping = {"STOPPED": 0, "CLOSING": 1, "OPENING": 2}
  val = mapping.get(state_str.upper(), 0)
  storage.enqueue_sensor(f"greenhouse/{gh_id}/climate/{vent_name}/state_numeric", val)


def on_connect(client, userdata, flags, rc):
  client.subscribe("greenhouse/+/+#")


def on_disconnect(client, userdata, rc):
  pass


def on_message(client, userdata, msg):
  topic = msg.topic
  payload = msg.payload.decode()

  # Update MQTT heartbeat on ANY message
  write_heartbeat(MQTT_HEARTBEAT)

  parts = topic.split("/")
  if len(parts) < 3 or parts[0] != "greenhouse":
    return

  gh_id = parts[1]
  st.init_greenhouse_state(gh_id)
  gh = st.greenhouses[gh_id]
  st.mark_mqtt_message(gh_id)

  try:
    v = float(payload)
    storage.enqueue_sensor(topic, v)
  except:
    pass

  s = gh["state"]

  if "climate" in parts:
    if topic.endswith("zone1/temperature"): s["t_z1"] = float(payload)
    if topic.endswith("zone1/humidity"):    s["h_z1"] = float(payload)
    if topic.endswith("zone2/temperature"): s["t_z2"] = float(payload)
    if topic.endswith("zone2/humidity"):    s["h_z2"] = float(payload)
    if topic.endswith("outside/temperature"): s["t_out"] = float(payload)
    if topic.endswith("outside/humidity"):    s["h_out"] = float(payload)
    if topic.endswith("light"): s["light"] = int(payload)

    if topic.endswith("presence"):
      val = int(payload)
      s["presence"] = val
      st.update_presence(gh_id, val)

    if topic.endswith("vents/zone1/state"):
      s["vent1_state"] = payload
      gh["vent_last_state_change"][1] = datetime.datetime.utcnow()
      encode_vent_state_numeric(gh_id, "vent1", payload)

    if topic.endswith("vents/zone2/state"):
      s["vent2_state"] = payload
      gh["vent_last_state_change"][2] = datetime.datetime.utcnow()
      encode_vent_state_numeric(gh_id, "vent2", payload)

    if topic.endswith("lights/state"):
      s["lights_state"] = payload

  if "irrigation" in parts:
    for i in range(8):
      if topic.endswith(f"zone{i+1}/moisture"):
        s["moisture"][i] = int(payload)
      if topic.endswith(f"zone{i+1}/valve_state"):
        s["valve_state"][i] = payload


client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message


def _mqtt_connect_loop():
    while True:
        try:
            print(f"MQTT: trying to connect to {MQTT_BROKER}:{MQTT_PORT}")
            client.connect(MQTT_BROKER, MQTT_PORT)
            client.loop_start()
            print("MQTT: connected")
            return
        except Exception as e:
            print(f"MQTT: connection failed: {e}. Retrying in 5 seconds")
            time.sleep(5)

def start():
    t = threading.Thread(target=_mqtt_connect_loop, daemon=True)
    t.start()


def send_cmd(gh_id: str, topic_suffix: str, payload: str):
  client.publish(f"greenhouse/{gh_id}/{topic_suffix}", payload)
