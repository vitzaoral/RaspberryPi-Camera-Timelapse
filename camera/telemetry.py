"""Push per-cycle diagnostics to the beeSys backend (sys.zaoral.cz).

Every cycle POSTs its phase timings (boot, internet wait, RTC sync, capture,
detection, upload) so slow cycles can be diagnosed without SSH access to the
Pi. Cycles that never got internet are queued to a local JSON file (survives
the WittyPi power cut) and flushed with the next successful cycle.

Auth: the camera's Blynk token from config.json, verified server-side against
the camera record in the beeSys DB — no extra secret needed in this repo.
"""
import json
import os
import subprocess

import requests

# Hardcoded fallback — keeps working on Pis whose local config.json (gitignored)
# doesn't include sys_telemetry_url.
DEFAULT_SYS_TELEMETRY_URL = "https://sys.zaoral.cz/api/public/cameras/cycle-log"

PENDING_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "pending_telemetry.json"
)
MAX_PENDING = 48  # ~4h of offline 5-min cycles; older ones aren't worth keeping


def get_boot_uptime():
    """Seconds since power-on — read at script start it approximates boot time."""
    try:
        with open("/proc/uptime") as f:
            return round(float(f.read().split()[0]), 1)
    except Exception:
        return None


def get_throttled():
    """Raw `vcgencmd get_throttled` value, e.g. '0x0' or '0x50005'.

    Nonzero means the firmware throttled the SoC — bit 0 = under-voltage now,
    bit 16 = under-voltage occurred since boot. Empty string when unavailable.
    """
    try:
        out = subprocess.run(
            ["vcgencmd", "get_throttled"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip().split("=")[-1]
    except Exception:
        return ""


def get_input_voltage(wittypi_path="/root/wittypi"):
    """WittyPi input voltage in volts, or None when the board can't measure it.

    Sources the WittyPi utilities in a bash subshell — the same I2C access the
    WittyPi scripts use, so no extra Python I2C dependency. Witty Pi 4 Mini has
    no Vin ADC and reads ~0.2 V of noise; anything below 2 V is treated as
    "not supported" so only boards with a real measurement (Witty Pi 4 /
    L3V7 battery models) report a value.
    """
    try:
        out = subprocess.run(
            ["bash", "-c",
             f"cd {wittypi_path} && . ./utilities.sh >/dev/null 2>&1 && get_input_voltage"],
            capture_output=True, text=True, timeout=10,
        )
        vin = round(float(out.stdout.strip()), 2)
        return vin if vin >= 2.0 else None
    except Exception:
        return None


def _load_pending():
    try:
        with open(PENDING_PATH) as f:
            logs = json.load(f)
            return logs if isinstance(logs, list) else []
    except Exception:
        return []


def _save_pending(logs):
    try:
        with open(PENDING_PATH, "w") as f:
            json.dump(logs[-MAX_PENDING:], f)
    except Exception as e:
        print(f"Failed to save pending telemetry: {e}")


def queue_cycle_log(log):
    """Store a log locally for cycles that can't reach the internet."""
    _save_pending(_load_pending() + [log])


def send_cycle_logs(config, log):
    """POST the current log plus any queued offline ones; queue all on failure.

    Never raises — telemetry must not break the photo cycle.
    """
    logs = (_load_pending() + [log])[-MAX_PENDING:]
    payload = {
        "camera_number": config["camera_number"],
        "token": config["blynk_camera_auth"],
        "logs": logs,
    }
    url = config.get("sys_telemetry_url", DEFAULT_SYS_TELEMETRY_URL)
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        if os.path.exists(PENDING_PATH):
            os.remove(PENDING_PATH)
        print(f"Telemetry sent ({len(logs)} log(s)).")
    except Exception as e:
        print(f"Failed to send telemetry, queueing: {e}")
        _save_pending(logs)
