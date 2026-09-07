import subprocess
from datetime import datetime, timedelta
import re
import os
import sys
import time

# WittyPi cuts power ~20-30s after GPIO-4 is pulled (it halts all processes
# first). A startup armed less than that in the future fires *during* shutdown
# while power is still on, so WittyPi misses it — and because the schedule
# format is "%d HH:MM:SS" (no month), a missed alarm rolls to the SAME day NEXT
# MONTH, leaving the camera dark for weeks. Never arm a startup closer than this
# safe margin, regardless of the configured interval.
MIN_STARTUP_MARGIN_SECONDS = 60

def format_photo_time(when=None):
    """Timestamp used in the photo name and overlay. Pass the capture moment
    explicitly — the photo is taken before the clock check, so the name must
    be derived after a possible clock fix, not at import time."""
    return (when or datetime.now()).strftime("%d.%m.%Y %H:%M:%S")


def generate_text(temperature, camera_number, when=None):
    shown = temperature if temperature not in (None, "") else "?"
    return f"CAM {camera_number}   {format_photo_time(when)}   {shown}°C"


# Public resolvers used for the cycle. The phone hotspot's own DNS forwarder is
# the prime suspect for "ping works, every HTTPS request stalls ~10 s": glibc
# retries a dead resolver 2x5 s before giving up, and Python has no DNS cache,
# so every request pays it again. The hotspot resolver stays as last resort.
PUBLIC_RESOLVERS = ("8.8.8.8", "1.1.1.1")
RESOLV_CONF = "/etc/resolv.conf"


def harden_dns():
    """Put public resolvers with short timeouts first in resolv.conf for this
    cycle (DHCP rewrites the file on the next boot). Returns a short note for
    the cycle log, e.g. 'dns 10.80.1.1>8.8.8.8' or the reason it was skipped."""
    try:
        with open(RESOLV_CONF) as f:
            original = f.read()
    except Exception as e:
        return f"dns: resolv read failed ({type(e).__name__})"
    current = [line.split()[1] for line in original.splitlines()
               if line.startswith("nameserver") and len(line.split()) > 1]
    keep = [ns for ns in current if ns not in PUBLIC_RESOLVERS][:1]
    lines = [
        "# rewritten by the camera cycle — DHCP restores it on the next boot",
        "options timeout:2 attempts:2",
    ]
    lines += [f"nameserver {ns}" for ns in PUBLIC_RESOLVERS]
    lines += [f"nameserver {ns}" for ns in keep]
    try:
        with open(RESOLV_CONF, "w") as f:
            f.write("\n".join(lines) + "\n")
    except Exception as e:
        return f"dns: resolv write failed ({type(e).__name__})"
    note = f"dns {','.join(current) or '?'}>{PUBLIC_RESOLVERS[0]}"
    print(note)
    return note


def disable_wifi_power_save(interface="wlan0"):
    """Turn off 802.11 power saving for this cycle.

    brcmfmac's power save on a marginal link adds latency and drops: the
    radio naps between beacons and the AP has to buffer our traffic. The
    camera is awake for under a minute, so keeping the radio fully on costs
    nothing measurable. The setting resets with the next boot.
    """
    for cmd in (["iw", "dev", interface, "set", "power_save", "off"],
                ["iwconfig", interface, "power", "off"]):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except Exception:
            continue
        if result.returncode == 0:
            print(f"WiFi power save off ({cmd[0]}).")
            return True
    print("WiFi power save: could not change (iw/iwconfig unavailable).")
    return False

def get_wifi_signal_strength():
    try:
        result = subprocess.run(["iwconfig"], capture_output=True, text=True)
        output = result.stdout
        for line in output.split("\n"):
            if "Signal level" in line:
                signal_part = line.split("Signal level=")[1]
                signal_strength = int(signal_part.split(" ")[0])
                print(f"WiFi Signal Strength: {signal_strength} dBm")
                return signal_strength
    except Exception as e:
        print(f"Error getting WiFi signal strength: {e}")
        return None

def get_ip_address():
    try:
        result = subprocess.run(["hostname", "-I"], capture_output=True, text=True)
        ip_address = result.stdout.strip().split(" ")[0]
        print(f"IP Address: {ip_address}")
        return ip_address
    except Exception as e:
        print(f"Error getting IP address: {e}")
        return None
    
def get_current_time():
    current_time = datetime.now().strftime("%H:%M:%S")
    return current_time

def _ping_ok():
    """One quick ping to 8.8.8.8; -W 2 caps the wait so a dead link fails fast."""
    try:
        subprocess.run(["ping", "-c", "1", "-W", "2", "8.8.8.8"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except Exception:
        return False


def _rekick_wlan0():
    """Force a fresh ifdown/ifup on wlan0 to recover a stuck cold-boot link."""
    try:
        subprocess.run(["ifdown", "wlan0"], timeout=25,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["ifup", "wlan0"], timeout=60,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        print(f"  wlan0 re-kick failed: {e}")


def is_connected_to_internet(timeout_seconds=150, retry_delay=5, grace_seconds=25):
    """Wait for connectivity, actively re-kicking WiFi if it gets stuck.

    The camera cold-boots every cycle, so the brcmfmac chip is power-cycled each
    time. On a weak-ish signal (~-66 dBm here) the FIRST cold association after
    power-up sometimes never completes within dhclient's window — wlan0 ends up
    with no IP and nothing retrying, so the old single-ping check skipped the
    photo and slept ("boots once, connects; next boot, nothing"). Testing showed
    a *warm* re-association is fast and 100% reliable (3-12s). So: ping for a
    short grace period to let the normal boot association finish, and if we're
    still offline, force an ifdown/ifup every ~30s to actively recover instead of
    passively waiting on a link that already gave up.

    Returns (connected, stats) where stats feeds the cycle telemetry:
    {"waited_s": float, "attempts": int, "rekicks": int}.
    """
    start = time.monotonic()
    deadline = start + timeout_seconds
    attempt = 0
    rekicks = 0
    last_kick = 0.0

    def stats():
        return {
            "waited_s": round(time.monotonic() - start, 1),
            "attempts": attempt,
            "rekicks": rekicks,
        }

    while True:
        attempt += 1
        if _ping_ok():
            print(f"Connected to the internet (attempt {attempt}).")
            return True, stats()
        now = time.monotonic()
        if now >= deadline:
            print(f"Not connected to the internet after {timeout_seconds}s "
                  f"({attempt} attempts).")
            return False, stats()
        # Let the normal cold-boot association finish first; only force a
        # re-kick once past the grace window, then at most every 30s.
        if now - start > grace_seconds and now - last_kick > 30:
            last_kick = now
            rekicks += 1
            print(f"Still offline after {int(now - start)}s — re-kicking wlan0...")
            _rekick_wlan0()
        else:
            print(f"No internet yet (attempt {attempt}) — waiting for WiFi...")
        time.sleep(retry_delay)

def is_in_time_interval(encoded_time):
    try:
        clean_input = re.sub(r'[^\x20-\x7E]', '', f"{encoded_time}")
        match = re.match(r'^(\d+)', clean_input)
        
        if not match:
            raise ValueError(f"Not match from {encoded_time}")
        digits = match.group(1)
        
        if len(digits) == 9:
            digits = '0' + digits
        elif len(digits) != 10:
            raise ValueError(f"Invalid digits {digits} from input {encoded_time}")
        
        start_seconds = int(digits[:5])
        end_seconds = int(digits[5:10])
        
        start_time = timedelta(seconds=start_seconds)
        end_time = timedelta(seconds=end_seconds)
        
        start_time_str = str(datetime.min + start_time).split()[1][:5]
        end_time_str = str(datetime.min + end_time).split()[1][:5]
        
        print(f"Camera working time: {start_time_str} - {end_time_str}")
        
        now = datetime.now()
        current_seconds = timedelta(hours=now.hour, minutes=now.minute, seconds=now.second)

        # Grace window: wakes are scheduled from the *previous* day's window
        # start, and a sunrise-tracking window moves ~1-2 min later each day,
        # so the camera can wake just before today's start. Without the grace
        # such a wake counts as out-of-hours, the cycle crosses the boundary
        # and get_next_start_time_from_start rolls the next start a whole day
        # forward - the camera then skips every day while sunrise advances.
        grace_before_start = timedelta(minutes=5)
        is_within_interval = (start_time - grace_before_start) <= current_seconds <= end_time
        return is_within_interval, start_time, f"{start_time_str}-{end_time_str}"
    except Exception as e:
        print(f"Error decoding time interval: {e}")
        return False, None, f"Error {e}"


def delete_photo(path):
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            print(f"Failed to delete photo: {e}")

def get_next_start_time(deep_sleep_interval):
    """
    Calculate the next startup time based on the deep sleep interval.
    
    Parameters:
        deep_sleep_interval (str): Time in seconds until the next startup.

    Returns:
        (str): Next startup time in format "dd HH:MM:SS".
    """
    now = datetime.now()
    interval = int(deep_sleep_interval)
    if interval < MIN_STARTUP_MARGIN_SECONDS:
        print(f"⚠️ interval {interval}s below safe margin — clamping to "
              f"{MIN_STARTUP_MARGIN_SECONDS}s to avoid WittyPi missing the alarm.")
        interval = MIN_STARTUP_MARGIN_SECONDS
    startup_time = now + timedelta(seconds=interval)
    return startup_time.strftime("%d %H:%M:%S")


def shutdown_device(retries=3, delay=10):
    """
    Attempts to shut down the device by setting the GPIO pin.
    If the device does not shut down within 10 seconds, it assumes the shutdown failed and tries again.
    """
    for attempt in range(1, retries + 1):
        print(f"🔻 Attempting to shut down the device via GPIO, attempt {attempt}...")
        try:
            # Set GPIO pin 4 as output
            subprocess.run(["gpio", "-g", "mode", "4", "out"], check=True)
            # Write a value of 0 to GPIO pin 4, which should trigger device shutdown
            subprocess.run(["gpio", "-g", "write", "4", "0"], check=True)
        except Exception as e:
            print(f"⚠️ Error on attempt {attempt} during GPIO setup: {e}")
            time.sleep(delay)
            continue

        # Wait for the shutdown process to complete
        time.sleep(delay)
        print("⚠️ Device did not shut down after the delay, retrying...")

    print("⚠️ All attempts to shut down have failed. The device remains on.")
    return False


def get_next_start_time_from_start(start_time):
    try:
        now = datetime.now()
        current_date = now.date()

        # Calculate the potential startup time for today
        potential_start_time = datetime.combine(current_date, (datetime.min + start_time).time())

        # If the calculated start time is in the past, move it to the next day
        if potential_start_time <= now:
            potential_start_time += timedelta(days=1)

        startup_time_str = potential_start_time.strftime("%d %H:%M:%S")
        return startup_time_str

    except Exception as e:
        print(f"Error calculating next start time: {e}")
        return None