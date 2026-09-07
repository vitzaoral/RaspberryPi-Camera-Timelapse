import shutil
import subprocess
import time
from PIL import Image, ImageDraw, ImageFont

CAPTURE_ATTEMPTS = 2
CAPTURE_RETRY_DELAY_S = 5


def capture_photo(temp_path, use_tuning_file):
    """rpicam-still into temp_path. One retry: right after an OTA restart (or
    any other quick re-run) the camera stack can still be busy and rpicam-still
    exits 255 although the sensor is fine a few seconds later."""
    tuning_file = "imx219_160d.json"

    command = [
    "rpicam-still",
    "-o", temp_path,
    "--awb", "auto",
    "--nopreview"]

    if use_tuning_file:
        command.extend(["--tuning-file", tuning_file])

    error_message = None
    for attempt in range(1, CAPTURE_ATTEMPTS + 1):
        try:
            subprocess.run(command, check=True, timeout=30)
            print("Photo captured successfully.")
            return True, None
        except Exception as e:
            error_message = f"An error occurred while capturing the photo: {e}"
            print(f"{error_message} (attempt {attempt}/{CAPTURE_ATTEMPTS})")
            if attempt < CAPTURE_ATTEMPTS:
                time.sleep(CAPTURE_RETRY_DELAY_S)
    return False, error_message

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
        # A photo without the overlay still beats no photo — give the upload a file.
        try:
            shutil.copyfile(input_path, output_path)
        except Exception as copy_error:
            print(f"Fallback copy failed: {copy_error}")
