import json
import sys
import os
from camera import capture_photo, add_text_to_image
from blynk import get_blynk_property, update_blynk_url, update_blynk_batch, update_blynk_pin_value
from cloudinary import upload_to_cloudinary
from utils import generate_text, get_wifi_signal_strength, get_ip_address, get_current_time, is_connected_to_internet, get_next_start_time_from_start, is_in_time_interval, current_time, delete_photo, get_next_start_time, shutdown_device
from witty_sheduler import schedule_deep_sleep, sync_time
from update_repository import check_and_update_repository

version = "3.0.8"
sleep_interval_person_detected = 1
default_deep_sleep_interval = 300

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# Load config
with open("config.json", "r") as config_file:
    config = json.load(config_file)

use_person_detection = config.get("use_person_detection", False)
if use_person_detection:
    from human_detection import detect_and_draw_person

witty_pi_path = config["witty_pi_path"]
blynk_camera_auth = config["blynk_camera_auth"]

def handle_deep_sleep(interval):
    """Handles scheduling deep sleep and updating Blynk on failure."""
    startup_time_str = get_next_start_time(interval)
    success, error = schedule_deep_sleep(startup_time_str, witty_pi_path)
    if not success:
        update_blynk_pin_value(error, blynk_camera_auth, config["blynk_camera_error_pin"])
    
    shutdown_result = shutdown_device()
    if not shutdown_result:
        update_blynk_pin_value("Device shut down have failed.", blynk_camera_auth, config["blynk_camera_error_pin"])
        sys.exit(1)
    sys.exit(0)

# Check internet connection
if not is_connected_to_internet():
    print("No internet connection. Exiting.")
    handle_deep_sleep(default_deep_sleep_interval)

sync_success, sync_message = sync_time(witty_pi_path)

if not sync_success:
     update_blynk_pin_value(sync_message, blynk_camera_auth, config["blynk_camera_error_pin"])
    
# Get Blynk settings
encoded_time = get_blynk_property(blynk_camera_auth, config["blynk_camera_pin_working_time"])
deep_sleep_interval = get_blynk_property(blynk_camera_auth, config["blynk_camera_deep_sleep_interval_pin"])
run_update = get_blynk_property(blynk_camera_auth, config["blynk_camera_run_update_pin"])

if None in (encoded_time, deep_sleep_interval, run_update):
    print("Error: One or more Blynk properties could not be retrieved. Exiting.")
    handle_deep_sleep(default_deep_sleep_interval)

if int(run_update):
    check_and_update_repository(config)

# Check working time
is_within, start_time, time_range = is_in_time_interval(encoded_time)
if not is_within:
    print("Time is over, bye")
    startup_time_str = get_next_start_time_from_start(start_time)
    
    updates = {
    config["blynk_camera_pin_current_time"]: get_current_time(),
    config["blynk_camera_pin_setted_working_time"]: time_range,
    config["blynk_camera_deep_sleep_interval_setted_pin"]: deep_sleep_interval,
    config["blynk_camera_version_pin"]: version,
    config["blynk_camera_next_start_time_pin"]: startup_time_str,
    config["blynk_camera_status_pin"]: "Time is over, going to sleep"}
    update_blynk_batch(updates, config["blynk_camera_auth"])

    success, error = schedule_deep_sleep(startup_time_str, witty_pi_path)
    if not success:
        update_blynk_pin_value(error, blynk_camera_auth, config["blynk_camera_error_pin"])
    
    shutdown_result = shutdown_device()
    if not shutdown_result:
        update_blynk_pin_value("Device shut down have failed.", blynk_camera_auth, config["blynk_camera_error_pin"])
        sys.exit(1)
    
    sys.exit(0)

# Capture photo
temp_photo_path = "/tmp/photo.jpg"
capture_photo_success, error_message = capture_photo(temp_photo_path, config["use_tuning_file"])
if not capture_photo_success:
    handle_deep_sleep(deep_sleep_interval)

# Person detection
person_detected = detect_and_draw_person(temp_photo_path) if use_person_detection else False

deep_sleep_interval = sleep_interval_person_detected if person_detected else deep_sleep_interval
result_photo_path = f"DETECTED_{current_time}.jpg" if person_detected else f"{current_time}.jpg"

# Upload photo
temperature = get_blynk_property(config["blynk_temperature_auth"], config["blynk_temperature_pin"])
text = generate_text(temperature, config["camera_number"])
add_text_to_image(temp_photo_path, result_photo_path, text)
secure_url = upload_to_cloudinary(result_photo_path, config["cloudinary_url"], config["cloudinary_upload_preset"], config["camera_number"])

wifi_signal = get_wifi_signal_strength()
ip_address = get_ip_address()

if secure_url:
    update_blynk_url(secure_url, blynk_camera_auth, config["blynk_camera_image_pin"])

# Delete the photo
delete_photo(result_photo_path)

# Update Blynk status
startup_time_str = get_next_start_time(deep_sleep_interval)
updates = {
    config["blynk_camera_human_detected_pin"]: 1 if person_detected else 0,
    config["blynk_camera_wifi_signal_pin"]: wifi_signal if wifi_signal else None,
    config["blynk_camera_ip_pin"]: ip_address if ip_address else None,
    config["blynk_camera_pin_current_time"]: get_current_time(),
    config["blynk_camera_pin_setted_working_time"]: time_range,
    config["blynk_camera_deep_sleep_interval_setted_pin"]: deep_sleep_interval,
    config["blynk_camera_version_pin"]: version,
    config["blynk_camera_next_start_time_pin"]: startup_time_str,
    config["blynk_camera_status_pin"]: "OK"
}
updates = {pin: value for pin, value in updates.items() if value is not None}
update_blynk_batch(updates, config["blynk_camera_auth"])

# Handle script restart or deep sleep
if person_detected:
    print("Person detected! Restarting script")
    os.execv(sys.executable, [sys.executable] + sys.argv)
else:
    handle_deep_sleep(deep_sleep_interval)