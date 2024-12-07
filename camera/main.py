import json
import sys
from camera import capture_photo, add_text_to_image
from blynk import get_blynk_property, update_blynk_url, update_blynk_pin_value
from cloudinary import upload_to_cloudinary
from utils import generate_text, get_wifi_signal_strength, get_ip_address, get_current_time, is_connected_to_internet, is_in_time_interval

if not is_connected_to_internet():
    print("No internet connection. Exiting.")
    sys.exit()

# load config
with open("../config.json", "r") as config_file:
    config = json.load(config_file)

# check if is time for taking pictures
working_time = get_blynk_property(config["blynk_camera_auth"], config["blynk_camera_pin_working_time"])
if not is_in_time_interval(working_time):
    print("Time is over, exit")
    sys.exit()

temp_photo_path = "/tmp/photo.jpg"
photo_with_text_path = "result.jpg"

# main program
capture_photo(temp_photo_path)
temperature = get_blynk_property(config["blynk_temperature_auth"], config["blynk_temperature_pin"])
text = generate_text(temperature)
add_text_to_image(temp_photo_path, photo_with_text_path, text)

secure_url = upload_to_cloudinary(
    photo_with_text_path,
    config["cloudinary_url"],
    config["cloudinary_upload_preset"],
    config["camera_number"]
)

wifi_signal = get_wifi_signal_strength()
ip_address = get_ip_address()

if secure_url:
    update_blynk_url(secure_url, config["blynk_camera_auth"], config["blynk_camera_image_pin"])

if wifi_signal:
    update_blynk_pin_value(wifi_signal, config["blynk_camera_auth"], config["blynk_camera_wifi_signal_pin"])

if wifi_signal:
    update_blynk_pin_value(ip_address, config["blynk_camera_auth"], config["blynk_camera_ip_pin"])

update_blynk_pin_value(get_current_time(), config["blynk_camera_auth"], config["blynk_camera_ip_pin"])