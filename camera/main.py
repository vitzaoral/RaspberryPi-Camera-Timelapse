import json
import logging
import sys
import os
import time
import traceback
from datetime import datetime, timedelta

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
from blynk import failure_notes, get_blynk_properties, get_sys_response, update_blynk_url, update_blynk_batch, update_blynk_pin_value
from clock import CLOCK_FIX_THRESHOLD_S, clock_offset_from_response, fix_system_clock, format_offset
import cloudinary
from cloudinary import upload_to_cloudinary
from settings_cache import load_cached_settings, save_cached_settings
from telemetry import get_boot_uptime, get_input_voltage, get_throttled, queue_cycle_log, send_cycle_logs
from utils import (
    DEFAULT_WIFI_MTU,
    delete_photo,
    disable_wifi_power_save,
    format_photo_time,
    generate_text,
    get_current_time,
    get_ip_address,
    get_next_start_time,
    get_next_start_time_from_start,
    get_wifi_signal_strength,
    harden_dns,
    is_connected_to_internet,
    is_in_time_interval,
    set_wifi_mtu,
    shutdown_device,
)
from witty_sheduler import schedule_deep_sleep, sync_time
from update_repository import check_and_update_repository

version = "3.6.2"
sleep_interval_person_detected = 1
default_deep_sleep_interval = 300
TEMP_PHOTO_PATH = "/tmp/photo.jpg"

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
# Filled in during the cycle; reported with the cycle log.
cycle_extra = {"clock_adjust_s": None, "settings_source": None}


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
        # Seconds the system clock was shifted after the Date-header check
        # (None = clock was fine) and where the cycle settings came from
        # (blynk / cache / default). Unknown to older beeSys versions, which
        # simply ignore them.
        "clock_adjust_s": cycle_extra["clock_adjust_s"],
        "settings_source": cycle_extra["settings_source"],
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


def read_settings():
    """Cycle settings from Blynk in one request, with the SD cache as fallback.

    Returns (settings, source, blynk_reachable). `settings` has string-or-None
    values for working_time, deep_sleep_interval, run_update, last_sync_date
    and force_sync; `source` is "blynk", "cache" or "default" and says where
    the window/interval came from. The OTA flag and the sync pins are never
    served from the cache — acting on a stale update request or force-sync
    would be wrong, and skipping them for a cycle is harmless.
    """
    pin_map = {
        "last_sync_date": config["blynk_camera_pin_last_sync_date"],
        "force_sync": config.get("blynk_camera_force_sync_pin", DEFAULT_FORCE_SYNC_PIN),
        "working_time": config["blynk_camera_pin_working_time"],
        "deep_sleep_interval": config["blynk_camera_deep_sleep_interval_pin"],
        "run_update": config["blynk_camera_run_update_pin"],
    }
    live = get_blynk_properties(blynk_camera_auth, list(pin_map.values()))
    blynk_reachable = live is not None
    settings = {name: None for name in pin_map}
    if blynk_reachable:
        settings = {name: live.get(pin.lower()) for name, pin in pin_map.items()}

    missing = [key for key in ("working_time", "deep_sleep_interval") if settings[key] is None]
    if not missing:
        save_cached_settings({
            "working_time": settings["working_time"],
            "deep_sleep_interval": settings["deep_sleep_interval"],
        })
        return settings, "blynk", blynk_reachable

    cached = load_cached_settings()
    filled = 0
    for key in missing:
        if cached.get(key) is not None:
            settings[key] = str(cached[key])
            filled += 1
    source = "cache" if filled == len(missing) else "default"
    print(f"⚠️ Blynk settings incomplete ({', '.join(missing)}) — using {source} values.")
    return settings, source, blynk_reachable


def run_person_detection(photo_path):
    """YOLO pass over the captured photo. Returns (person_detected, upload_tags)."""
    image, accepted, rejected = detect_persons(photo_path)
    person_detected = bool(accepted)
    upload_tags = []

    # Draw boxes on the photo so the gallery shows what was detected. While
    # tuning is active (DRAW_REJECTED_CANDIDATES=True), call draw_detections
    # unconditionally so the yellow zone-of-interest line is visible on every
    # frame — that's our reference marker for the `above_zone` filter, and
    # without it the user has no way to verify where the cutoff sits when no
    # candidates were found in the frame.
    if image is not None and (accepted or DRAW_REJECTED_CANDIDATES):
        image = draw_detections(image, accepted, rejected)
        cv2.imwrite(photo_path, image)

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

    return person_detected, upload_tags


def run():
    # --- 1. Photo first ---------------------------------------------------
    # Nothing below needs the network to take the picture, and the network is
    # the part that fails on this site. Shoot now, sort out the cloud later.
    capture_start = time.monotonic()
    capture_ok, capture_error = capture_photo(TEMP_PHOTO_PATH, config["use_tuning_file"])
    capture_end = time.monotonic()
    timings["capture_s"] = round(capture_end - capture_start, 1)

    person_detected = False
    upload_tags = []
    if capture_ok and use_person_detection:
        detection_start = time.monotonic()
        person_detected, upload_tags = run_person_detection(TEMP_PHOTO_PATH)
        timings["detection_s"] = round(time.monotonic() - detection_start, 1)

    # --- 2. Internet ------------------------------------------------------
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
    disable_wifi_power_save()
    net_notes = [set_wifi_mtu(config.get("wifi_mtu", DEFAULT_WIFI_MTU)), harden_dns()]

    # --- 3. beeSys: temperature for the overlay + clock reference ---------
    settings_fetch_start = time.monotonic()
    sys_response = get_sys_response(config.get("sys_temperature_url", DEFAULT_SYS_TEMPERATURE_URL))
    temperature = sys_response.text.strip() if sys_response is not None else None

    clock_offset = clock_offset_from_response(sys_response)
    clock_fixed = False
    clock_note = ""
    if clock_offset is not None and abs(clock_offset) > CLOCK_FIX_THRESHOLD_S:
        print(f"⏰ System clock is off by {format_offset(clock_offset)} vs beeSys — fixing.")
        clock_fixed, fix_error = fix_system_clock(clock_offset, witty_pi_path)
        if clock_fixed:
            cycle_extra["clock_adjust_s"] = clock_offset
            clock_note = f"Hodiny opraveny o {format_offset(clock_offset)} podle serveru"
        else:
            clock_note = f"Hodiny mimo o {format_offset(clock_offset)}, oprava selhala: {fix_error}"
            print(f"❌ {clock_note}")
    elif clock_offset is not None:
        print(f"⏰ Clock OK (Δ {clock_offset:+.1f} s vs beeSys).")

    # --- 4. Cycle settings ------------------------------------------------
    settings, settings_source, blynk_reachable = read_settings()
    cycle_extra["settings_source"] = settings_source
    try:
        deep_sleep_interval = int(settings["deep_sleep_interval"])
    except (TypeError, ValueError):
        deep_sleep_interval = default_deep_sleep_interval

    # --- 5. RTC sync ------------------------------------------------------
    try:
        force_sync = bool(int(settings["force_sync"] or "0"))
    except (TypeError, ValueError):
        force_sync = False
    if force_sync:
        print("🔧 Force sync requested via Blynk pin.")

    sync_start = time.monotonic()
    if clock_fixed:
        # System clock and RTC were just set from the server reference —
        # that is today's sync.
        sync_success, sync_message, new_sync_iso = True, "", datetime.now().isoformat()
    elif not blynk_reachable and clock_offset is not None and not force_sync:
        # Blynk is down but the clock is verified against beeSys: skip Witty
        # Pi's network sync, which on a link this bad can retry for minutes.
        print("⏰ Blynk unreachable, clock verified — skipping WittyPi sync this cycle.")
        sync_success, sync_message, new_sync_iso = True, "", None
    else:
        sync_success, sync_message, new_sync_iso = sync_time(
            witty_pi_path, settings["last_sync_date"], force=force_sync
        )
    timings["rtc_sync_s"] = round(time.monotonic() - sync_start, 1)

    if new_sync_iso:
        update_blynk_pin_value(new_sync_iso, blynk_camera_auth, config["blynk_camera_pin_last_sync_date"])
    if force_sync and sync_success:
        update_blynk_pin_value(0, blynk_camera_auth, config.get("blynk_camera_force_sync_pin", DEFAULT_FORCE_SYNC_PIN))
    if not sync_success:
        update_blynk_pin_value(sync_message, blynk_camera_auth, config["blynk_camera_error_pin"])

    # Everything since settings_fetch_start minus the RTC sync = time spent on
    # cloud round-trips (beeSys reference, Blynk settings, sync pin writes).
    timings["blynk_fetch_s"] = round(
        time.monotonic() - settings_fetch_start - timings["rtc_sync_s"], 1
    )

    # --- 6. OTA -----------------------------------------------------------
    if settings["run_update"] is not None:
        try:
            if int(settings["run_update"]):
                check_and_update_repository(config)
        except (ValueError, TypeError):
            print("Error: Invalid run_update value from Blynk.")

    # --- 7. Working window ------------------------------------------------
    # We never bail out early when outside the window — the camera still
    # uploads the photo it already took (e.g. the boundary frame just after
    # 20:00, or any stray wake); only the *sleep target* differs: out-of-hours
    # wakes sleep until the next working-window start instead of the normal
    # interval.
    if settings["working_time"] is not None:
        is_within, start_time, time_range = is_in_time_interval(settings["working_time"])
    else:
        # No window known at all (no Blynk, no cache): shooting beats guessing
        # that we're off duty.
        is_within, start_time, time_range = True, None, "?"
    out_of_hours = not is_within
    if out_of_hours:
        print("Outside working hours — uploading this photo, then sleeping until the window reopens.")

    def next_wake_for_cycle():
        """(interval, explicit_startup_time) for handle_deep_sleep at the end of a
        cycle. Out-of-hours → wake at the next working-window start; in-hours →
        the normal now+interval (explicit None)."""
        if out_of_hours:
            morning = get_next_start_time_from_start(start_time) if start_time is not None else None
            return default_deep_sleep_interval, morning
        return deep_sleep_interval, None

    # --- 8. Capture failure (reported now that we are online) -------------
    if not capture_ok:
        # Camera hardware is dead — still push the rest of the telemetry so the
        # dashboard shows fresh time/wifi/ip/version, not stale values from the
        # last cycle when capture was still working.
        push_telemetry(
            status="Camera hardware error",
            error=f"Camera fail: {(capture_error or '')[:180]}",
            interval=deep_sleep_interval,
            time_range_val=time_range,
        )
        send_cycle_logs(config, make_cycle_log(
            status="camera_fail", error=(capture_error or "")[:500]
        ))
        fail_interval, fail_startup = next_wake_for_cycle()
        handle_deep_sleep(fail_interval, startup_time_str=fail_startup)

    # --- 9. Overlay + upload ----------------------------------------------
    # The photo was taken before the clock check; derive its wall-clock time
    # from the (possibly corrected) clock and the monotonic time elapsed since.
    captured_at = datetime.now() - timedelta(seconds=time.monotonic() - capture_end)
    photo_stamp = format_photo_time(captured_at)
    if person_detected:
        deep_sleep_interval = sleep_interval_person_detected
    result_photo_path = f"DETECTED_{photo_stamp}.jpg" if person_detected else f"{photo_stamp}.jpg"

    text = generate_text(temperature, config["camera_number"], when=captured_at)
    add_text_to_image(TEMP_PHOTO_PATH, result_photo_path, text)
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

    delete_photo(result_photo_path)

    # --- 10. Dashboard + cycle log, then sleep or keep watching -----------
    cycle_interval, cycle_startup = next_wake_for_cycle()
    startup_time_str = cycle_startup or get_next_start_time(cycle_interval)
    status = "OK (mimo pracovní dobu)" if out_of_hours else "OK"
    if not secure_url:
        status = "upload_fail"
    if settings_source == "cache":
        status += " [cache]"
    elif settings_source == "default":
        status += " [bez Blynku]"
    updates = {
        config["blynk_camera_human_detected_pin"]: 1 if person_detected else 0,
        config["blynk_camera_wifi_signal_pin"]: wifi_signal if wifi_signal else None,
        config["blynk_camera_ip_pin"]: ip_address if ip_address else None,
        config["blynk_camera_pin_current_time"]: get_current_time(),
        config["blynk_camera_pin_setted_working_time"]: time_range,
        config["blynk_camera_deep_sleep_interval_setted_pin"]: deep_sleep_interval,
        config["blynk_camera_version_pin"]: version,
        config["blynk_camera_next_start_time_pin"]: startup_time_str,
        config["blynk_camera_status_pin"]: status,
        config["blynk_camera_error_pin"]: clock_note,
    }
    updates = {pin: value for pin, value in updates.items() if value is not None}
    update_blynk_batch(updates, blynk_camera_auth)

    # Diagnostics for the cycle log: clock fix, DNS note and what failed on
    # the network and how (only when something did) — the dashboard tooltip is
    # the only window into the link quality without SSH access to the Pi.
    if cloudinary.last_error:
        net_notes.append(f"upload: {cloudinary.last_error}")
    net_notes.extend(failure_notes())
    problems = [n for n in net_notes if not (n.startswith("dns ") or n.startswith("mtu "))]
    diagnostics = "; ".join(net_notes) if problems else ""
    error_text = "; ".join(part for part in (clock_note, diagnostics) if part)

    send_cycle_logs(config, make_cycle_log(status=status, error=error_text, person=person_detected))

    # Person-triggered continuous monitoring only makes sense within working
    # hours; outside the window we always upload the single photo above and
    # then sleep until the window reopens.
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


def main():
    """Whatever goes wrong inside a cycle, the camera must still schedule its
    next wake-up and power off — a crash that leaves the Pi running would
    drain the battery, and systemd restarting the script would not help."""
    try:
        run()
    except SystemExit:
        raise
    except Exception as e:
        details = traceback.format_exc()
        print(f"💥 Unhandled error in cycle:\n{details}")
        summary = f"{type(e).__name__}: {e}"
        try:
            send_cycle_logs(config, make_cycle_log(status="crash", error=f"{summary}\n{details[-1500:]}"))
        except Exception as log_error:
            print(f"Also failed to log the crash: {log_error}")
        try:
            update_blynk_pin_value(f"Crash: {summary[:170]}", blynk_camera_auth, config["blynk_camera_error_pin"])
        except Exception:
            pass
        handle_deep_sleep(default_deep_sleep_interval)


if __name__ == "__main__":
    main()
