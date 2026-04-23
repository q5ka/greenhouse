import sqlite3
import datetime
import threading
import time
import os

DB_PATH = "/opt/greenhouse/data/database.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
db = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS sensors (
    timestamp TEXT,
    key TEXT,
    value REAL
)
""")
db.commit()

# Simple write queue for batching
_write_queue = []
_queue_lock = threading.Lock()
_flush_interval_sec = 5

def enqueue_sensor(key, value):
    ts = datetime.datetime.utcnow().isoformat()
    with _queue_lock:
        _write_queue.append((ts, key, float(value)))

def get_queue_length():
    with _queue_lock:
        return len(_write_queue)

def _flush_loop():
    while True:
        time.sleep(_flush_interval_sec)
        flush_queue()

def flush_queue():
    global _write_queue
    with _queue_lock:
        if not _write_queue:
            return
        batch = _write_queue
        _write_queue = []
    cur.executemany("INSERT INTO sensors VALUES (?, ?, ?)", batch)
    db.commit()

# Start background flusher
threading.Thread(target=_flush_loop, daemon=True).start()

def get_history(key: str, hours: int = 24):
    since = (datetime.datetime.utcnow() - datetime.timedelta(hours=hours)).isoformat()
    cur.execute("SELECT timestamp, value FROM sensors WHERE key=? AND timestamp>=? ORDER BY timestamp",
                (key, since))
    rows = cur.fetchall()
    return [{"t": r[0], "v": float(r[1])} for r in rows]
