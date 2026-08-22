import json
import logging
import sys
import os
import time
from datetime import datetime

# Captured before any heavy import/work — everything the script does counts
# into total_s of the cycle telemetry.
script_start = time.monotonic()

from camera import capture_photo, add_text_to_image

# Wire up logging so logger.info() in human_detection.py reaches systemd
# journal (default level is WARNING, which would silently drop our detection
# stats). Format mirrors print() output so existing journalctl scrapes still
# work.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
from blynk import get_blynk_property, get_sys_property, update_blynk_url, update_blynk_batch, update_blynk_pin_value
from cloudinary import upload_to_cloudinary
from telemetry import get_boot_uptime, get_input_voltage, get_throttled, queue_cycle_log, send_cycle_logs
from utils import generate_text, get_wifi_signal_strength, get_ip_address, get_current_time, is_connected_to_internet, get_next_start_time_from_start, is_in_time_interval, current_time, delete_photo, get_next_start_time, shutdown_device
from witty_sheduler import schedule_deep_sleep, sync_time
from update_repository import check_and_update_repository

version = "3.5.2"
sleep_interval_person_detected = 1
default_deep_sleep_interval = 300

# Hardcoded fallback — keeps working on Pis whose local config.json (gitignored)
# hasn't been updated to include sys_temperature_url.
DEFAULT_SYS_TEMPERATURE_URL = "https://sys.zaoral.cz/api/public/outdoor/temperature"
# Fallback for force-sync Blynk pin — every camera uses V23, no need to add it
# to config.json after `git pull` (configs are gitignored).
DEFAULT_FORCE_SYNC_PIN = "v23"

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# Load config
with open("config.json", "r") as config_file:
    config = json.load(config_file)

use_person_detection = config.get("use_person_detection", False)
if use_person_detection:
    import cv2
    from human_detection import (
        detect_persons,
        draw_detections,
        DRAW_REJECTED_CANDIDATES,
    )

witty_pi_path = config["witty_pi_path"]
blynk_camera_auth = config["blynk_camera_auth"]

# --- Cycle telemetry -----------------------------------------------------
# Phase timings collected along the way and POSTed to beeSys at the end of
# the cycle (or queued locally when there's no internet). Diagnoses slow
# cycles without SSH access to the Pi.
timings = {}
warm_start = "--warm" in sys.argv  # execv restart po detekci — bez bootu a WiFi asociace
boot_uptime = get_boot_uptime()


def make_cycle_log(status, error="", person=False):
    return {
        "measured_at": datetime.now().isoformat(),
        "version": version,
        "status": status,
        "error": error,
        "warm_start": warm_start,
        # monotonic on Linux counts from boot, so the raw script_start value is
        # the uptime when Python got past stdlib imports ≈ when systemd started
        # the service. boot_uptime − svc_start = time spent importing libraries
        # from the SD card (the prime suspect for slow cycles).
        "svc_start_s": round(script_start, 1),
        "boot_uptime_s": boot_uptime,
        "internet_wait_s": timings.get("internet_wait_s"),
        "internet_attempts": timings.get("internet_attempts"),
        "wifi_rekicks": timings.get("wifi_rekicks"),
        "rtc_sync_s": timings.get("rtc_sync_s"),
        "blynk_fetch_s": timings.get("blynk_fetch_s"),
        "capture_s": timings.get("capture_s"),
        "detection_s": timings.get("detection_s"),
        "upload_s": timings.get("upload_s"),
        "total_s": round(time.monotonic() - script_start, 1),
        "wifi_dbm": get_wifi_signal_strength(),
        "throttled": get_throttled(),
        # None na Witty Pi 4 Mini (nemá Vin ADC); plný Witty Pi 4 / L3V7 posílá
        # reálné vstupní napětí — na bateriových kamerách ukazuje stav baterie.
        "vin_v": get_input_voltage(witty_pi_path),
        "person_detected": person,
    }

def handle_deep_sleep(interval, startup_time_str=None):
    """Schedule next wakeup, then shut down. Pass an explicit startup_time_str
    to wake at a specific moment (e.g. the next working-window start); otherwise
    it's computed as now+interval. On schedule failure, force a fresh RTC sync
    and retry once — schedule fails almost always trace back to RTC drift, so
    re-syncing usually fixes it and avoids the device going dark.
    """
    if startup_time_str is None:
        startup_time_str = get_next_start_time(interval)
    success, error = schedule_deep_sleep(startup_time_str, witty_pi_path)

    if not success:
        print("⚠️ schedule_deep_sleep failed — forcing RTC sync and retrying once.")
        sync_ok, _, _ = sync_time(witty_pi_path, last_sync_iso=None, force=True)
        if sync_ok:
            success, error = schedule_deep_sleep(startup_time_str, witty_pi_path)

    if not success:
        update_blynk_pin_value(error, blynk_camera_auth, config["blynk_camera_error_pin"])

    shutdown_device()
    # Always exit 0 to prevent systemd restart loop — if GPIO didn't cut power,
    # restarting the script won't help and would drain the battery.
    sys.exit(0)


def push_telemetry(status, error, interval, time_range_val=""):
    """Push the standard dashboard telemetry (time, wifi, ip, version, schedule,
    status, error) in one Blynk batch. Called both on camera-fail and on the
    happy path so the sys dashboard never shows a stale cycle-old snapshot.
    """
    startup_time_str = get_next_start_time(interval) or ""
    updates = {
        config["blynk_camera_wifi_signal_pin"]: get_wifi_signal_strength(),
        config["blynk_camera_ip_pin"]: get_ip_address(),
        config["blynk_camera_pin_current_time"]: get_current_time(),
        config["blynk_camera_pin_setted_working_time"]: time_range_val,
        config["blynk_camera_deep_sleep_interval_setted_pin"]: interval,
        config["blynk_camera_version_pin"]: version,
        config["blynk_camera_next_start_time_pin"]: startup_time_str,
        config["blynk_camera_status_pin"]: status,
        config["blynk_camera_error_pin"]: error,
    }
    updates = {pin: value for pin, value in updates.items() if value is not None}
    update_blynk_batch(updates, blynk_camera_auth)

# Check internet connection
connected, net_stats = is_connected_to_internet()
timings["internet_wait_s"] = net_stats["waited_s"]
timings["internet_attempts"] = net_stats["attempts"]
timings["wifi_rekicks"] = net_stats["rekicks"]
if not connected:
    print("No internet connection. Exiting.")
    # Can't POST without internet — queue to SD, flushed by the next
    # successful cycle. These offline cycles are exactly the ones we need
    # to see in the diagnostics.
    queue_cycle_log(make_cycle_log(status="no_internet"))
    handle_deep_sleep(default_deep_sleep_interval)

settings_fetch_start = time.monotonic()
last_sync_date = get_blynk_property(blynk_camera_auth, config["blynk_camera_pin_last_sync_date"])

# Force-sync button (Blynk V23): when the user toggles it on, ignore the
# "already synced today" shortcut and run a full sync-and-verify cycle. The
# pin is reset back to 0 after a successful sync so it doesn't keep firing.
force_sync_pin = config.get("blynk_camera_force_sync_pin", DEFAULT_FORCE_SYNC_PIN)
raw = get_blynk_property(blynk_camera_auth, force_sync_pin)
try:
    force_sync = bool(int(raw or "0"))
except (ValueError, TypeError):
    force_sync = False
if force_sync:
    print("🔧 Force sync requested via Blynk pin.")

sync_start = time.monotonic()
sync_success, sync_message, new_sync_iso = sync_time(witty_pi_path, last_sync_date, force=force_sync)
timings["rtc_sync_s"] = round(time.monotonic() - sync_start, 1)

if new_sync_iso:
    update_blynk_pin_value(new_sync_iso, blynk_camera_auth, config["blynk_camera_pin_last_sync_date"])

if force_sync and sync_success:
    update_blynk_pin_value(0, blynk_camera_auth, force_sync_pin)

if not sync_success:
    update_blynk_pin_value(sync_message, blynk_camera_auth, config["blynk_camera_error_pin"])
    
# Get Blynk settings
encoded_time = get_blynk_property(blynk_camera_auth, config["blynk_camera_pin_working_time"])
deep_sleep_interval = get_blynk_property(blynk_camera_auth, config["blynk_camera_deep_sleep_interval_pin"])
run_update = get_blynk_property(blynk_camera_auth, config["blynk_camera_run_update_pin"])

# Everything since settings_fetch_start minus the RTC sync = time spent on
# Blynk round-trips (property reads/writes around sync + the settings block).
timings["blynk_fetch_s"] = round(
    time.monotonic() - settings_fetch_start - timings["rtc_sync_s"], 1
)

if None in (encoded_time, deep_sleep_interval, run_update):
    print("Error: One or more Blynk properties could not be retrieved. Exiting.")
    send_cycle_logs(config, make_cycle_log(status="blynk_fail"))
    handle_deep_sleep(default_deep_sleep_interval)

try:
    if int(run_update):
        check_and_update_repository(config)
except (ValueError, TypeError):
    print("Error: Invalid run_update value from Blynk.")

# Check working time. We no longer bail out early when outside the window —
# the camera still takes & uploads one photo this cycle (e.g. the boundary
# frame just after 20:00, or any stray wake), and only the *sleep target*
# differs: out-of-hours wakes sleep until the next working-window start instead
# of the normal interval. Decision is applied after capture/upload below.
is_within, start_time, time_range = is_in_time_interval(encoded_time)
out_of_hours = not is_within
if out_of_hours:
    print("Outside working hours — taking one photo, then sleeping until the window reopens.")


def next_wake_for_cycle():
    """(interval, explicit_startup_time) for handle_deep_sleep at the end of a
    cycle. Out-of-hours → wake at the next working-window start; in-hours →
    the normal now+interval (explicit None)."""
    if out_of_hours:
        morning = get_next_start_time_from_start(start_time) if start_time is not None else None
        return default_deep_sleep_interval, morning
    return deep_sleep_interval, None


# Capture photo
temp_photo_path = "/tmp/photo.jpg"
capture_start = time.monotonic()
capture_photo_success, error_message = capture_photo(temp_photo_path, config["use_tuning_file"])
timings["capture_s"] = round(time.monotonic() - capture_start, 1)
if not capture_photo_success:
    # Camera hardware is dead — still push the rest of the telemetry so the
    # dashboard shows fresh time/wifi/ip/version, not stale values from the
    # last cycle when capture was still working.
    push_telemetry(
        status="Camera hardware error",
        error=f"Camera fail: {(error_message or '')[:180]}",
        interval=deep_sleep_interval,
        time_range_val=time_range,
    )
    send_cycle_logs(config, make_cycle_log(
        status="camera_fail", error=(error_message or "")[:500]
    ))
    fail_interval, fail_startup = next_wake_for_cycle()
    handle_deep_sleep(fail_interval, startup_time_str=fail_startup)

# Person detection
person_detected = False
max_confidence = 0.0
upload_tags = []

detection_start = time.monotonic()
if use_person_detection:
    image, accepted, rejected = detect_persons(temp_photo_path)
    person_detected = bool(accepted)

    # Draw boxes on the photo so the gallery shows what was detected. While
    # tuning is active (DRAW_REJECTED_CANDIDATES=True), call draw_detections
    # unconditionally so the yellow zone-of-interest line is visible on every
    # frame — that's our reference marker for the `above_zone` filter, and
    # without it the user has no way to verify where the cutoff sits when no
    # candidates were found in the frame.
    if image is not None and (accepted or DRAW_REJECTED_CANDIDATES):
        image = draw_detections(image, accepted, rejected)
        cv2.imwrite(temp_photo_path, image)

    if person_detected:
        max_confidence = max(d.confidence for d in accepted)
        # Cloudinary tags travel out of the camera — these are how the dashboard
        # filters hits and shows the confidence badge in the gallery.
        upload_tags = ["person", f"conf_{int(max_confidence * 100):02d}"]

    # Persist info about rejected candidates (úl, strom, větev, ...) to
    # Cloudinary tags so we can analyse false-positive sources later without
    # SSHing into the camera. Tags don't trigger the gallery "Pouze
    # detekované" filter (that's tags:person), so they're invisible by
    # default — opt-in for debug / tuning.
    if rejected:
        max_rejected_conf = max(d.confidence for d in rejected)
        upload_tags.append("candidate")
        upload_tags.append(f"cand_conf_{int(max_rejected_conf * 100):02d}")
        for reason in sorted({d.rejected_reason for d in rejected}):
            upload_tags.append(f"cand_{reason}")

if use_person_detection:
    timings["detection_s"] = round(time.monotonic() - detection_start, 1)

deep_sleep_interval = sleep_interval_person_detected if person_detected else deep_sleep_interval
result_photo_path = f"DETECTED_{current_time}.jpg" if person_detected else f"{current_time}.jpg"

# Upload photo
temperature = get_sys_property(config.get("sys_temperature_url", DEFAULT_SYS_TEMPERATURE_URL))
text = generate_text(temperature, config["camera_number"])
add_text_to_image(temp_photo_path, result_photo_path, text)
upload_start = time.monotonic()
secure_url = upload_to_cloudinary(
    result_photo_path,
    config["cloudinary_url"],
    config["cloudinary_upload_preset"],
    config["camera_number"],
    tags=upload_tags or None,
)
timings["upload_s"] = round(time.monotonic() - upload_start, 1)

wifi_signal = get_wifi_signal_strength()
ip_address = get_ip_address()

if secure_url:
    update_blynk_url(secure_url, blynk_camera_auth, config["blynk_camera_image_pin"])

# Delete the photo
delete_photo(result_photo_path)

# Decide the next wakeup (used both for the dashboard and the actual sleep).
cycle_interval, cycle_startup = next_wake_for_cycle()
startup_time_str = cycle_startup or get_next_start_time(cycle_interval)
updates = {
    config["blynk_camera_human_detected_pin"]: 1 if person_detected else 0,
    config["blynk_camera_wifi_signal_pin"]: wifi_signal if wifi_signal else None,
    config["blynk_camera_ip_pin"]: ip_address if ip_address else None,
    config["blynk_camera_pin_current_time"]: get_current_time(),
    config["blynk_camera_pin_setted_working_time"]: time_range,
    config["blynk_camera_deep_sleep_interval_setted_pin"]: deep_sleep_interval,
    config["blynk_camera_version_pin"]: version,
    config["blynk_camera_next_start_time_pin"]: startup_time_str,
    config["blynk_camera_status_pin"]: "OK (mimo pracovní dobu)" if out_of_hours else "OK",
    config["blynk_camera_error_pin"]: ""
}
updates = {pin: value for pin, value in updates.items() if value is not None}
update_blynk_batch(updates, config["blynk_camera_auth"])

send_cycle_logs(config, make_cycle_log(
    status="OK (mimo pracovní dobu)" if out_of_hours else "OK",
    person=person_detected,
))

# Handle script restart or deep sleep. Person-triggered continuous monitoring
# only makes sense within working hours; outside the window we always take the
# single photo above and then sleep until the window reopens.
if person_detected and not out_of_hours:
    print("Person detected! Restarting script")
    # --warm marks the next run as an execv restart (no boot, no WiFi
    # association) so its telemetry isn't mixed into cold-cycle stats.
    argv = [sys.executable] + sys.argv
    if "--warm" not in argv:
        argv.append("--warm")
    os.execv(sys.executable, argv)
else:
    handle_deep_sleep(cycle_interval, startup_time_str=cycle_startup)