import subprocess
from datetime import datetime, timedelta
import re
import os
import sys
import time

current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

def generate_text(temperature, camera_number):
    return f"CAM {camera_number}   {current_time}   {temperature}°C"

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

def is_connected_to_internet():
    try:
        # try ping 8.8.8.8 (Google DNS)
        subprocess.run(["ping", "-c", "1", "8.8.8.8"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        print("Connected to the internet.")
        return True
    except Exception as e:
        print("Not connected to the internet.")
        return False

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
        
        is_within_interval = start_time <= current_seconds <= end_time
        return is_within_interval, start_time, f"{start_time_str}-{end_time_str}"
    except Exception as e:
        print(f"Error decoding time interval: {e}")
        return False, "", f"Error {e}"


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
    startup_time = now + timedelta(seconds=int(deep_sleep_interval))
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
        return "Error", "Error"