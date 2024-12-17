import subprocess
from datetime import datetime, timedelta
import re
import os

current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

def generate_text(temperature):
    return f"CAM 1   {current_time}   {temperature}°C"

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
    except subprocess.CalledProcessError:
        print("Not connected to the internet.")
        return False

def is_in_time_interval(encoded_time):
    try:
        clean_time = re.sub(r'[^\x20-\x7E]', '', encoded_time)

        start_seconds = int(clean_time[:5])
        end_seconds = int(clean_time[5:10])

        start_time = timedelta(seconds=start_seconds)
        end_time = timedelta(seconds=end_seconds)

        start_time_str = str(datetime.min + start_time).split(" ")[1][:5]
        end_time_str = str(datetime.min + end_time).split(" ")[1][:5]

        print(f"Camera working time: {start_time_str} - {end_time_str}")

        now = datetime.now()
        current_seconds = timedelta(
            hours=now.hour,
            minutes=now.minute,
            seconds=now.second
        )

        is_within_interval = start_time <= current_seconds <= end_time
        return is_within_interval, start_time, f"{start_time_str}-{end_time_str}"
    except Exception as e:
        print(f"Error decoding time interval: {e}")
        return False, "Error"

def delete_photo(path):
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            print(f"Failed to delete photo: {e}")

def get_next_start_time(deep_sleep_interval):
    deep_sleep_interval = int(deep_sleep_interval)
    now = datetime.now()
    
    shutdown_time = now + timedelta(seconds=2)
    startup_time = shutdown_time + timedelta(seconds=deep_sleep_interval)
    
    shutdown_time_str = shutdown_time.strftime("%d %H:%M:%S")
    startup_time_str = startup_time.strftime("%d %H:%M:%S")
    
    return shutdown_time_str, startup_time_str

def get_next_start_time_from_start(start_time):
    try:
        now = datetime.now()
        current_date = now.date()

        # Calculate the potential startup time for today
        potential_start_time = datetime.combine(current_date, (datetime.min + start_time).time())

        # If the calculated start time is in the past, move it to the next day
        if potential_start_time <= now:
            potential_start_time += timedelta(days=1)

        shutdown_time = now + timedelta(seconds=10)

        shutdown_time_str = shutdown_time.strftime("%d %H:%M:%S")
        startup_time_str = potential_start_time.strftime("%d %H:%M:%S")

        return shutdown_time_str, startup_time_str

    except Exception as e:
        print(f"Error calculating next start time: {e}")
        return "Error", "Error"