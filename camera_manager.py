# camera_manager.py
import os
import io
import time
import threading
import datetime
from typing import Dict, Optional, List
import requests
import cv2
import numpy as np
from heartbeat import write_heartbeat

class CameraConfig:
    def __init__(self, gh_id: str, cfg: dict):
        self.gh_id = gh_id
        self.enabled = cfg.get("enabled", False)
        self.esp32_ip = cfg.get("esp32_ip")
        self.mode = cfg.get("mode", "live")
        self.snapshot_interval = cfg.get("snapshot_interval", 60)
        self.motion_sensitivity = cfg.get("motion_sensitivity", 0.25)
        self.record_duration = cfg.get("record_duration", 10)
        self.storage_path = cfg.get("storage_path", f"./data/camera/{gh_id}")
        self.use_pir_mqtt = cfg.get("use_pir_mqtt", True)
        self.use_software_motion = cfg.get("use_software_motion", True)

        os.makedirs(os.path.join(self.storage_path, "timelapse"), exist_ok=True)
        os.makedirs(os.path.join(self.storage_path, "motion"), exist_ok=True)

    def has_mode(self, name: str) -> bool:
        return name in self.mode


class CameraManager:
    def _safe_join_under(self, base_dir: str, user_path: str) -> Optional[str]:
        base_real = os.path.realpath(base_dir)
        target_real = os.path.realpath(os.path.join(base_real, user_path))
        try:
            if os.path.commonpath([base_real, target_real]) != base_real:
                return None
        except ValueError:
            return None
        return target_real
    def __init__(self, config: Dict[str, dict]):
        self.configs: Dict[str, CameraConfig] = {}
        self.timelapse_threads: Dict[str, threading.Thread] = {}
        self.motion_threads: Dict[str, threading.Thread] = {}
        self.stop_flags: Dict[str, threading.Event] = {}
        self.last_frame: Dict[str, Optional[bytes]] = {}
        self.lock = threading.Lock()

        for gh_id, gh_cfg in config.get("greenhouses", {}).items():
            caps = gh_cfg.get("capabilities", {})
            if not caps.get("has_camera", False):
                continue
            cam_cfg = gh_cfg.get("camera", {})
            cc = CameraConfig(gh_id, cam_cfg)
            if not cc.enabled or not cc.esp32_ip:
                continue
            self.configs[gh_id] = cc
            self.stop_flags[gh_id] = threading.Event()
            self.last_frame[gh_id] = None

        for gh_id, cc in self.configs.items():
            if cc.has_mode("timelapse"):
                t = threading.Thread(target=self._timelapse_worker, args=(gh_id,), daemon=True)
                t.start()
                self.timelapse_threads[gh_id] = t
            if cc.has_mode("motion"):
                t = threading.Thread(target=self._motion_worker, args=(gh_id,), daemon=True)
                t.start()
                self.motion_threads[gh_id] = t

    def stop(self):
        for ev in self.stop_flags.values():
            ev.set()

    def _snapshot_url(self, cc: CameraConfig) -> str:
        return f"http://{cc.esp32_ip}/capture"

    def _stream_url(self, cc: CameraConfig) -> str:
        return f"http://{cc.esp32_ip}:81/stream"

    def _fetch_snapshot(self, gh_id: str) -> Optional[bytes]:
        cc = self.configs.get(gh_id)
        if not cc:
            return None
        try:
            r = requests.get(self._snapshot_url(cc), timeout=5)
            if r.status_code == 200:
                frame = r.content
                write_heartbeat(f"/opt/greenhouse/data/camera/{gh_id}/last_frame.txt")
                with self.lock:
                    self.last_frame[gh_id] = frame
                return frame
        except Exception:
            return None
        return None

    def get_last_frame(self, gh_id: str) -> Optional[bytes]:
        with self.lock:
            return self.last_frame.get(gh_id)

    def _timelapse_worker(self, gh_id: str):
        cc = self.configs[gh_id]
        while not self.stop_flags[gh_id].is_set():
            now = datetime.datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H%M%S")
            frame = self._fetch_snapshot(gh_id)
            if frame:
                day_dir = os.path.join(cc.storage_path, "timelapse", date_str)
                os.makedirs(day_dir, exist_ok=True)
                path = os.path.join(day_dir, f"{time_str}.jpg")
                try:
                    with open(path, "wb") as f:
                        f.write(frame)
                except Exception:
                    pass
            time.sleep(max(1, cc.snapshot_interval))

    def _motion_worker(self, gh_id: str):
        cc = self.configs[gh_id]
        prev_gray = None
        fps = 5
        interval = 1.0 / fps
        while not self.stop_flags[gh_id].is_set():
            frame_bytes = self._fetch_snapshot(gh_id)
            if not frame_bytes:
                time.sleep(interval)
                continue
            np_arr = np.frombuffer(frame_bytes, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_GRAYSCALE)
            if img is None:
                time.sleep(interval)
                continue

            if prev_gray is None:
                prev_gray = img
                time.sleep(interval)
                continue

            diff = cv2.absdiff(prev_gray, img)
            _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            motion_score = float(np.sum(thresh)) / (thresh.shape[0] * thresh.shape[1] * 255.0)

            prev_gray = img

            if cc.use_software_motion and motion_score > cc.motion_sensitivity:
                self._record_clip(gh_id, cc, fps=fps)

            time.sleep(interval)

    def handle_pir_motion(self, gh_id: str):
        cc = self.configs.get(gh_id)
        if not cc or not cc.use_pir_mqtt:
            return
        self._record_clip(gh_id, cc, fps=5)

    def _record_clip(self, gh_id: str, cc: CameraConfig, fps: int = 5):
        duration = cc.record_duration
        frames: List[np.ndarray] = []
        start = time.time()
        while time.time() - start < duration:
            frame_bytes = self._fetch_snapshot(gh_id)
            if not frame_bytes:
                time.sleep(1.0 / fps)
                continue
            np_arr = np.frombuffer(frame_bytes, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if img is not None:
                frames.append(img)
            time.sleep(1.0 / fps)

        if not frames:
            return

        h, w, _ = frames[0].shape
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H%M%S")
        day_dir = os.path.join(cc.storage_path, "motion", date_str)
        os.makedirs(day_dir, exist_ok=True)
        path = os.path.join(day_dir, f"{time_str}.mp4")

        try:
            out = cv2.VideoWriter(path, fourcc, fps, (w, h))
            for f in frames:
                out.write(f)
            out.release()
        except Exception:
            pass

    def list_timelapse(self, gh_id: str, date_str: str) -> List[str]:
        cc = self.configs.get(gh_id)
        if not cc:
            return []
        base_dir = os.path.join(cc.storage_path, "timelapse")
        day_dir = self._safe_join_under(base_dir, date_str)
        if not day_dir or not os.path.isdir(day_dir):
            return []
        files = sorted(os.listdir(day_dir))
        safe_rel_prefix = os.path.relpath(day_dir, os.path.realpath(base_dir))
        return [os.path.join(safe_rel_prefix, f) for f in files if f.lower().endswith(".jpg")]

    def get_timelapse_frame(self, gh_id: str, rel_path: str) -> Optional[bytes]:
        cc = self.configs.get(gh_id)
        if not cc:
            return None
        if not rel_path:
            return None
        normalized_rel = os.path.normpath(rel_path).replace("\\", "/")
        if (
            os.path.isabs(normalized_rel)
            or normalized_rel.startswith("../")
            or normalized_rel == ".."
            or "/../" in normalized_rel
            or normalized_rel.startswith("/")
        ):
            return None
        if not normalized_rel.lower().endswith((".jpg", ".jpeg")):
            return None
        base_dir = os.path.join(cc.storage_path, "timelapse")
        full_path = self._safe_join_under(base_dir, normalized_rel)
        if not full_path or not os.path.isfile(full_path):
            return None
        try:
            with open(full_path, "rb") as f:
                return f.read()
        except Exception:
            return None

    def list_motion(self, gh_id: str) -> List[str]:
        cc = self.configs.get(gh_id)
        if not cc:
            return []
        base = os.path.join(cc.storage_path, "motion")
        if not os.path.isdir(base):
            return []
        out = []
        for date_dir in sorted(os.listdir(base)):
            full_date = os.path.join(base, date_dir)
            if not os.path.isdir(full_date):
                continue
            for f in sorted(os.listdir(full_date)):
                if f.lower().endswith(".mp4"):
                    out.append(os.path.join(date_dir, f))
        return out

    def get_motion_video(self, gh_id: str, rel_path: str) -> Optional[bytes]:
        cc = self.configs.get(gh_id)
        if not cc:
            return None
        base_dir = os.path.join(cc.storage_path, "motion")
        full_path = self._safe_join_under(base_dir, rel_path)
        if not full_path or not os.path.isfile(full_path):
            return None
        try:
            with open(full_path, "rb") as f:
                return f.read()
        except Exception:
            return None
