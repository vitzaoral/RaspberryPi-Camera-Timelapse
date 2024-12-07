from datetime import datetime
import subprocess

def generate_text(temperature):
    current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
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



