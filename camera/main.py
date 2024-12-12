import json
import sys
from camera import capture_photo, add_text_to_image
from blynk import get_blynk_property, update_blynk_url, update_blynk_pin_value
from cloudinary import upload_to_cloudinary
from utils import generate_text, get_wifi_signal_strength, get_ip_address, get_current_time, is_connected_to_internet, is_in_time_interval, current_time
from human_detection import detect_and_draw_person
from witty_sheduler import schedule_deep_sleep

# TODO: use more efficient Raspbery distribution, DietPi https://dietpi.com/#download 32 vs 64 bit version (https://dietpi.com/docs/hardware/)
# TODO: start script immediately after system start

# load config
with open("config.json", "r") as config_file:
    config = json.load(config_file)

if not is_connected_to_internet():
    # TODO: save photo to SD card
    print("No internet connection. Exiting.")
    schedule_deep_sleep(300, config["witty_pi_path"])
    sys.exit()

# check if is time for taking pictures
encoded_time = get_blynk_property(config["blynk_camera_auth"], config["blynk_camera_pin_working_time"])
deep_sleep_interval = get_blynk_property(config["blynk_camera_auth"], config["blynk_camera_deep_sleep_interval_pin"])

is_within, time_range = is_in_time_interval(encoded_time)
if not is_within:
    print("Time is over, exit")
    # TODO: deep_sleep_interval should be longer to the next start time interval? Or use other pin to set
    schedule_deep_sleep(deep_sleep_interval, config["witty_pi_path"])
    sys.exit()

temp_photo_path = "/tmp/photo.jpg"
result_photo_path = f"{current_time}.jpg"

# main program
capture_photo(temp_photo_path)

person_detected = detect_and_draw_person(temp_photo_path)
temperature = get_blynk_property(config["blynk_temperature_auth"], config["blynk_temperature_pin"])
text = generate_text(temperature)
add_text_to_image(temp_photo_path, result_photo_path, text)

secure_url = upload_to_cloudinary(
    result_photo_path,
    config["cloudinary_url"],
    config["cloudinary_upload_preset"],
    config["camera_number"]
)

wifi_signal = get_wifi_signal_strength()
ip_address = get_ip_address()

update_blynk_pin_value(1 if person_detected else 0, config["blynk_camera_auth"], config["blynk_camera_human_detected_pin"])

if secure_url:
    update_blynk_url(secure_url, config["blynk_camera_auth"], config["blynk_camera_image_pin"])

if wifi_signal:
    update_blynk_pin_value(wifi_signal, config["blynk_camera_auth"], config["blynk_camera_wifi_signal_pin"])

if ip_address:
    update_blynk_pin_value(ip_address, config["blynk_camera_auth"], config["blynk_camera_ip_pin"])
    
update_blynk_pin_value(get_current_time(), config["blynk_camera_auth"], config["blynk_camera_pin_current_time"])
update_blynk_pin_value(time_range, config["blynk_camera_auth"], config["blynk_camera_pin_setted_working_time"])
update_blynk_pin_value(deep_sleep_interval, config["blynk_camera_auth"], config["blynk_camera_deep_sleep_interval_setted_pin"])

# Bye, go to sleep
schedule_deep_sleep(deep_sleep_interval, config["witty_pi_path"])