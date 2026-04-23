import json
from datetime import datetime, timezone
import os

def write_heartbeat(path: str):
    """Write an ISO timestamp to a heartbeat file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"last_update": datetime.now(timezone.utc).isoformat()}, f)
