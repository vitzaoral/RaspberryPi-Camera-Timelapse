"""Last known cycle settings from Blynk, persisted on the SD card.

When Blynk is unreachable the camera used to abort the whole cycle without a
photo. Now it keeps shooting with the last working window and sleep interval
it saw — both change rarely (the window shifts about a minute a day).
"""
import json
import os
from datetime import datetime

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings_cache.json")


def load_cached_settings():
    try:
        with open(CACHE_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cached_settings(settings):
    """Merge non-None values into the cache. Written atomically so a power cut
    mid-write can't leave a truncated file behind."""
    merged = load_cached_settings()
    merged.update({key: value for key, value in settings.items() if value is not None})
    merged["saved_at"] = datetime.now().isoformat(timespec="seconds")
    tmp_path = CACHE_PATH + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(merged, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, CACHE_PATH)
    except Exception as e:
        print(f"Failed to save settings cache: {e}")
