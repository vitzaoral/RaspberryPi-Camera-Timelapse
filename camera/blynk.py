"""Blynk HTTP API client + beeSys public API helper.

Cycle settings are read with ONE multi-pin request (with retries) instead of
five sequential single-pin GETs that each had to succeed — on a lossy link
the old approach failed in half of the cycles and the camera went back to
sleep without a photo.
"""
import os
import time

import requests

from net import session

# Overridable for local end-to-end tests against a fake server.
BLYNK_BASE_URL = os.environ.get("BLYNK_BASE_URL", "https://blynk.cloud/external/api")

# (connect, read): connect fails fast on a dead link, read tolerates a slow one.
TIMEOUT = (5, 15)
GET_ATTEMPTS = 3
UPDATE_ATTEMPTS = 2
RETRY_DELAY_S = 2
# Once the settings read has exhausted its retries, Blynk is considered down
# for the rest of the cycle: dashboard writes then get a single short attempt
# so a dead link costs seconds, not minutes of battery.
DOWN_TIMEOUT = (5, 8)
_blynk_down = False


def _retrying(label, attempts, fn):
    """Run fn() up to `attempts` times; returns its result, or None when every
    attempt failed. A 4xx other than 429 is definitive (bad token / pin), so
    it is not retried."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            print(f"{label}: attempt {attempt}/{attempts} failed: {e}")
            if status is not None and 400 <= status < 500 and status != 429:
                return None
        except Exception as e:
            print(f"{label}: attempt {attempt}/{attempts} failed: {e}")
        if attempt < attempts:
            time.sleep(RETRY_DELAY_S)
    return None


def get_sys_response(url):
    """GET a beeSys public endpoint. Returns the Response (the caller reads
    the text and the headers — the Date header doubles as our clock
    reference) or None when unreachable."""
    def fetch():
        response = session.get(url, timeout=(5, 10))
        response.raise_for_status()
        return response
    return _retrying("sys get", 2, fetch)


def get_sys_property(url):
    """Fetch a plain-text value from the beesys public API."""
    response = get_sys_response(url)
    return None if response is None else response.text.strip()


def get_blynk_properties(blynk_token, pins):
    """Read several datastreams in one request -> {pin: str | None}.

    Returns None when Blynk could not be reached at all (the caller falls back
    to cached settings). Pins that were never written come back as None.
    """
    pins = [p.lower() for p in pins]
    url = f"{BLYNK_BASE_URL}/get?token={blynk_token}&" + "&".join(pins)

    def fetch():
        response = session.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError(f"unexpected Blynk payload: {str(data)[:80]}")
        lowered = {str(k).lower(): v for k, v in data.items()}
        return {pin: (None if lowered.get(pin) is None else str(lowered[pin])) for pin in pins}

    global _blynk_down
    result = _retrying("Blynk get", GET_ATTEMPTS, fetch)
    if result is not None:
        print(f"Blynk settings: {result}")
    else:
        _blynk_down = True
        print("Blynk unreachable — dashboard writes limited to one short attempt this cycle.")
    return result


def _write_attempts():
    return 1 if _blynk_down else UPDATE_ATTEMPTS


def _write_timeout():
    return DOWN_TIMEOUT if _blynk_down else TIMEOUT


def get_blynk_property(blynk_token, blynk_pin):
    result = get_blynk_properties(blynk_token, [blynk_pin])
    return None if result is None else result.get(blynk_pin.lower())


def update_blynk_url(secure_url, blynk_auth, blynk_pin):
    url = f"{BLYNK_BASE_URL}/update/property?token={blynk_auth}&pin={blynk_pin}&urls={secure_url}"

    def do():
        response = session.get(url, timeout=_write_timeout())
        response.raise_for_status()
        return True

    if _retrying(f"Blynk property {blynk_pin}", _write_attempts(), do):
        print(f"Blynk property updated successfully for pin {blynk_pin}.")


def update_blynk_pin_value(value, blynk_auth, blynk_pin):
    url = f"{BLYNK_BASE_URL}/update?token={blynk_auth}&pin={blynk_pin}&value={value}"

    def do():
        response = session.get(url, timeout=_write_timeout())
        response.raise_for_status()
        return True

    if _retrying(f"Blynk pin {blynk_pin}", _write_attempts(), do):
        print(f"Blynk pin {blynk_pin} updated successfully with value {value}.")


def update_blynk_batch(updates, blynk_auth):
    params = {"token": blynk_auth}
    params.update({f"{pin}": value for pin, value in updates.items()})

    def do():
        response = session.get(f"{BLYNK_BASE_URL}/batch/update", params=params, timeout=_write_timeout())
        response.raise_for_status()
        return True

    if _retrying("Blynk batch update", _write_attempts(), do):
        print(f"Blynk batch update successful with values: {updates}")
