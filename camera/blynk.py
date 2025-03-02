import requests

def get_blynk_property(blynk_token, blynk_pin):
    blynk_get_url = "https://blynk.cloud/external/api/get"
    url = f"{blynk_get_url}?token={blynk_token}&pin={blynk_pin}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        content = response.text.strip()
        return content
    except Exception as e:
        print(f"Error fetching blynk property: {e}")
        return None

def update_blynk_url(secure_url, blynk_auth, blynk_pin):
    base_url = "https://fra1.blynk.cloud/external/api/update/property"
    try:
        url = f"{base_url}?token={blynk_auth}&pin={blynk_pin}&urls={secure_url}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        print(f"Blynk property updated successfully for pin {blynk_pin}.")
    except Exception as e:
        print(f"Error updating Blynk property: {e}")


def update_blynk_pin_value(value, blynk_auth, blynk_pin):
    base_url = "https://fra1.blynk.cloud/external/api/update"
    try:
        url = f"{base_url}?token={blynk_auth}&pin={blynk_pin}&value={value}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        print(f"Blynk pin {blynk_pin} updated successfully with value {value}.")
    except Exception as e:
        print(f"Error updating Blynk pin value: {e}")

def update_blynk_batch(updates, blynk_auth):
    base_url = "https://blynk.cloud/external/api/batch/update"
    try:
        # Format updates for batch request
        params = {'token': blynk_auth}
        params.update({f'{pin}': value for pin, value in updates.items()})

        # Send batch request
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        print(f"Blynk batch update successful with values: {updates}")
    except Exception as e:
        print(f"Error during Blynk batch update: {e}")