import time

import requests

from blynk import describe_error

UPLOAD_ATTEMPTS = 3
UPLOAD_TIMEOUT = (15, 120)   # connect, read — a stalled upload must not keep the camera awake for good
RETRY_DELAY_S = 3

# Why the last upload failed ('ConnectTimeout', 'ConnectionError/resolve', ...);
# empty after a successful upload. Reported in the cycle log.
last_error = ""


def upload_to_cloudinary(file_path, cloudinary_url, cloudinary_upload_preset, camera_number, tags=None):
    """Upload a photo to Cloudinary. `tags` is an optional iterable of strings
    that get attached to the resource — used by the dashboard to filter
    detection hits and surface confidence in the UI without parsing filenames.

    The photo is the whole point of the cycle, so it gets more patience than
    anything else on the network: several attempts, generous connect timeout.
    """
    global last_error
    kinds = []
    for attempt in range(1, UPLOAD_ATTEMPTS + 1):
        try:
            with open(file_path, "rb") as f:
                files = {"file": f}
                data = {
                    "upload_preset": cloudinary_upload_preset,
                    "folder": f"camera_{camera_number}",
                }
                if tags:
                    data["tags"] = ",".join(tags)
                response = requests.post(cloudinary_url, files=files, data=data, timeout=UPLOAD_TIMEOUT)
            response.raise_for_status()
            image_url = response.json().get("secure_url", "No URL returned")
            print(f"Image uploaded successfully. URL: {image_url}")
            last_error = "+".join(kinds) + " then ok" if kinds else ""
            return image_url
        except Exception as e:
            kinds.append(describe_error(e))
            print(f"Error uploading to Cloudinary (attempt {attempt}/{UPLOAD_ATTEMPTS}): {e}")
            if attempt < UPLOAD_ATTEMPTS:
                time.sleep(RETRY_DELAY_S)
    last_error = "+".join(kinds)
    return None
