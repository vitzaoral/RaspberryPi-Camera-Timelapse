import subprocess
from PIL import Image, ImageDraw, ImageFont

def capture_photo(temp_path, use_tuning_file):
    tuning_file = "imx219_160d.json"

    command = [
    "rpicam-still",
    "-o", temp_path,
    "--awb", "auto",
    "--nopreview"]

    if use_tuning_file:
        command.extend(["--tuning-file", tuning_file])

    try:
        subprocess.run(command, check=True)
        print("Photo captured successfully.")
        return True, None
    except Exception as e:
        error_message = f"An error occurred while capturing the photo: {e}"
        print(error_message)
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
