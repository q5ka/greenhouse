import datetime

import state as st


def presence_allows_irrigation(gh_id: str, gh_cfg: dict) -> bool:
  gh = st.greenhouses[gh_id]
  presence = gh["state"]["presence"]
  if presence == 0:
    return True

  cfg = gh_cfg.get("presence", {})
  cooldown = cfg.get("cooldown_minutes", 10)
  last_change = gh["presence_last_change"]
  if last_change is None:
    return False

  minutes = (datetime.datetime.utcnow() - last_change).total_seconds() / 60.0
  return minutes >= cooldown
