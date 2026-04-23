import datetime
import smtplib
from email.mime.text import MIMEText

import state as st
import health as health_mod

_last_alerts = {}
ALERT_COOLDOWN_MINUTES = 15


def _should_send(key: str) -> bool:
  now = datetime.datetime.utcnow()
  last = _last_alerts.get(key)
  if last is None:
    _last_alerts[key] = now
    return True
  delta = (now - last).total_seconds() / 60.0
  if delta >= ALERT_COOLDOWN_MINUTES:
    _last_alerts[key] = now
    return True
  return False


def _send_email(subject: str, body: str, gh_cfg: dict):
  email_cfg = gh_cfg.get("notifications", {}).get("email", {})
  if not email_cfg.get("enabled", False):
    return
  to_addr = email_cfg.get("to")
  if not to_addr:
    return

  smtp_cfg = email_cfg.get("smtp", {})
  host = smtp_cfg.get("host")
  port = smtp_cfg.get("port", 587)
  user = smtp_cfg.get("user")
  password = smtp_cfg.get("password")
  use_tls = smtp_cfg.get("use_tls", True)

  if not host or not user or not password:
    return

  msg = MIMEText(body)
  msg["Subject"] = subject
  msg["From"] = user
  msg["To"] = to_addr

  try:
    server = smtplib.SMTP(host, port, timeout=10)
    if use_tls:
      server.starttls()
    server.login(user, password)
    server.sendmail(user, [to_addr], msg.as_string())
    server.quit()
  except Exception as e:
    print("Email send failed:", e)


def _send_sms(message: str, gh_cfg: dict):
  sms_cfg = gh_cfg.get("notifications", {}).get("sms", {})
  if not sms_cfg.get("enabled", False):
    return
  to_number = sms_cfg.get("to")
  if not to_number:
    return
  print(f"[SMS to {to_number}] {message}")


def _notify(key: str, subject: str, body: str, gh_cfg: dict):
  if not _should_send(key):
    return
  _send_email(subject, body, gh_cfg)
  _send_sms(f"{subject}: {body}", gh_cfg)


def check_and_notify(gh_id: str, gh_cfg: dict):
  h = health_mod.get_health(gh_id)
  gh = st.greenhouses[gh_id]
  s = gh["state"]

  if not h["overall"]["mqtt_ok"]:
    _notify(f"{gh_id}_mqtt_down", f"{gh_id} MQTT Down", "MQTT connection appears to be down.", gh_cfg)

  if not h["overall"]["sensors_fresh"]:
    _notify(f"{gh_id}_sensors_stale", f"{gh_id} Sensors Stale", "Sensor data appears stale.", gh_cfg)

  if not h["overall"]["vents_ok"]:
    _notify(f"{gh_id}_vent_fault", f"{gh_id} Vent Fault", f"Vent faults: {h['vents']}", gh_cfg)

  if not h["overall"]["irrigation_ok"]:
    _notify(f"{gh_id}_irrigation_fault", f"{gh_id} Irrigation Fault", f"Irrigation faults: {h['irrigation']}", gh_cfg)

  if not h["overall"]["db_ok"]:
    _notify(f"{gh_id}_db_queue", f"{gh_id} DB Queue Large", f"DB queue length: {h['storage']['queue_length']}", gh_cfg)

  ct = gh_cfg.get("climate_thresholds", {})
  ir = gh_cfg.get("irrigation", {})
  presence_cfg = gh_cfg.get("presence", {})

  for label, val in [("Zone 1", s["t_z1"]), ("Zone 2", s["t_z2"]), ("Outside", s["t_out"])]:
    if val is None:
      continue
    if val <= ct.get("temp_low_critical", -999):
      _notify(f"{gh_id}_temp_low_{label}", f"{gh_id} Critical Low Temp: {label}", f"{val}°F", gh_cfg)
    if val >= ct.get("temp_high_critical", 999):
      _notify(f"{gh_id}_temp_high_{label}", f"{gh_id} Critical High Temp: {label}", f"{val}°F", gh_cfg)

  for label, val in [("Zone 1", s["h_z1"]), ("Zone 2", s["h_z2"]), ("Outside", s["h_out"])]:
    if val is None:
      continue
    if val <= ct.get("humidity_low_critical", -999):
      _notify(f"{gh_id}_hum_low_{label}", f"{gh_id} Critical Low Humidity: {label}", f"{val}%", gh_cfg)
    if val >= ct.get("humidity_high_critical", 999):
      _notify(f"{gh_id}_hum_high_{label}", f"{gh_id} Critical High Humidity: {label}", f"{val}%", gh_cfg)

  low_crit = ir.get("moisture_low_critical", -999)
  high_crit = ir.get("moisture_high_critical", 999)
  for i, m in enumerate(s["moisture"]):
    if m is None:
      continue
    zone_label = f"Zone {i+1}"
    if m <= low_crit:
      _notify(f"{gh_id}_moist_low_{zone_label}", f"{gh_id} Critical Low Moisture: {zone_label}", str(m), gh_cfg)
    if m >= high_crit:
      _notify(f"{gh_id}_moist_high_{zone_label}", f"{gh_id} Critical High Moisture: {zone_label}", str(m), gh_cfg)

  warn_minutes = presence_cfg.get("warning_minutes", 30)
  crit_minutes = presence_cfg.get("critical_minutes", 120)
  if gh["presence_current"] == 1 and gh["presence_last_change"] is not None:
    minutes = (datetime.datetime.utcnow() - gh["presence_last_change"]).total_seconds() / 60.0
    if minutes >= crit_minutes:
      _notify(f"{gh_id}_presence_crit", f"{gh_id} Presence Critical", f"{minutes:.1f} minutes", gh_cfg)
    elif minutes >= warn_minutes:
      _notify(f"{gh_id}_presence_warn", f"{gh_id} Presence Warning", f"{minutes:.1f} minutes", gh_cfg)
