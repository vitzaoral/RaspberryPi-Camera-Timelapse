import subprocess
import os
import requests
import json
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

def load_config(file_path):
    try:
        with open(file_path, "r") as config_file:
            return json.load(config_file)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        exit(1)

def capture_photo(temp_path):
    try:
        subprocess.run(["libcamera-still", "-o", temp_path], check=True)
        print("Photo captured successfully.")
    except subprocess.CalledProcessError as e:
        print(f"An error occurred: {e}")
        exit(1)

def get_temperature(blynk_get_url, blynk_token, blynk_pin):
    url = f"{blynk_get_url}?token={blynk_token}&pin={blynk_pin}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException as e:
        print(f"Error fetching temperature: {e}")
        return "N/A"

def generate_text(temperature):
    current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    return f"CAM 1   {current_time}   {temperature}°C"

def add_text_to_image(input_path, output_path, text):
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font_size = 70
    padding = 20
    extra_padding_top = 10
    extra_padding_bottom = 20

    try:
        img = Image.open(input_path)
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(font_path, font_size)
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width, text_height = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
        background_position = (
            padding,
            padding,
            padding + text_width + 20,
            padding + text_height + extra_padding_top + extra_padding_bottom
        )
        draw.rectangle(background_position, fill="white")
        text_position = (padding + 10, padding + extra_padding_top)
        draw.text(text_position, text, fill="black", font=font)
        img.save(output_path)
        print(f"Photo with text saved to {output_path}")
    except Exception as e:
        print(f"An error occurred while processing the image: {e}")

def upload_to_cloudinary(file_path, cloudinary_url, cloudinary_upload_preset, camera_number):
    try:
        files = {
            "file": open(file_path, "rb"),
        }
        data = {
            "upload_preset": cloudinary_upload_preset,
            "folder": f"camera_{camera_number}"
        }
        response = requests.post(cloudinary_url, files=files, data=data)
        response.raise_for_status()
        response_data = response.json()
        image_url = response_data.get("secure_url", "No URL returned")
        print(f"Image uploaded successfully. URL: {image_url}")
        return image_url
    except requests.RequestException as e:
        print(f"Error uploading to Cloudinary: {e}")
        return None

def update_blynk_property(secure_url, blynk_auth, blynk_pin):
    base_url = "https://fra1.blynk.cloud/external/api/update/property"
    try:
        url = f"{base_url}?token={blynk_auth}&pin={blynk_pin}&urls={secure_url}"
        response = requests.get(url)
        response.raise_for_status()
        print(f"Blynk property updated successfully for pin {blynk_pin}.")
    except requests.RequestException as e:
        print(f"Error updating Blynk property: {e}")

config = load_config("config.json")

desktop_path = os.path.expanduser("~/Desktop")
temp_photo_path = "/tmp/photo.jpg"
photo_with_text_path = os.path.join(desktop_path, "photo_with_text.jpg")

capture_photo(temp_photo_path)

temperature = get_temperature(config["blynk_get_url"], config["blynk_token_temperature"], config["blynk_pin_temperature"])
text = generate_text(temperature)
add_text_to_image(temp_photo_path, photo_with_text_path, text)

secure_url = upload_to_cloudinary(
    photo_with_text_path,
    config["cloudinary_url"],
    config["cloudinary_upload_preset"],
    config["camera_number"]
)

if secure_url:
    update_blynk_property(secure_url, config["blynk_camera_auth"], config["blynk_camera_image_pin"])

print("BYE")
