import requests

def get_blynk_property(blynk_token, blynk_pin):
    blynk_get_url = "https://blynk.cloud/external/api/get"
    url = f"{blynk_get_url}?token={blynk_token}&pin={blynk_pin}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException as e:
        print(f"Error fetching temperature: {e}")
        return "N/A"

def update_blynk_url(secure_url, blynk_auth, blynk_pin):
    base_url = "https://fra1.blynk.cloud/external/api/update/property"
    try:
        url = f"{base_url}?token={blynk_auth}&pin={blynk_pin}&urls={secure_url}"
        response = requests.get(url)
        response.raise_for_status()
        print(f"Blynk property updated successfully for pin {blynk_pin}.")
    except requests.RequestException as e:
        print(f"Error updating Blynk property: {e}")


def update_blynk_pin_value(value, blynk_auth, blynk_pin):
    base_url = "https://fra1.blynk.cloud/external/api/update"
    try:
        url = f"{base_url}?token={blynk_auth}&pin={blynk_pin}&value={value}"
        response = requests.get(url)
        response.raise_for_status()
        print(f"Blynk pin {blynk_pin} updated successfully with value {value}.")
    except requests.RequestException as e:
        print(f"Error updating Blynk pin value: {e}")

