import subprocess
from PIL import Image, ImageDraw, ImageFont

def capture_photo(temp_path):
    try:
        subprocess.run(["libcamera-still", "--nopreview", "-o", temp_path], check=True)
        print("Photo captured successfully.")
    except subprocess.CalledProcessError as e:
        print(f"An error occurred: {e}")
        exit(1)

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
