import requests

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
