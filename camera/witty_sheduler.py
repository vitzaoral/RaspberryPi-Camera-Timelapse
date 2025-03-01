import subprocess
import time
import datetime
import re

def start_wittypi_process(wittypi_path):
    """
    Starts the WittyPi process and returns the process along with a send_command function.
    """
    wittypi_script = "wittyPi.sh"
    process = subprocess.Popen(
        ["bash", wittypi_script],
        cwd=wittypi_path,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    def send_command(command, delay=1):
        process.stdin.write(command + "\n")
        process.stdin.flush()
        time.sleep(delay)

    return process, send_command

def handle_process_result(process, stdout, stderr):
    """
    Checks the process output for errors and returns a tuple (bool, message).
    """
    if stderr.strip():
        error_msg = stderr.strip()
        print("WittyPi stderr:")
        print(error_msg)
        return (False, error_msg)
    if process.returncode != 0:
        error_msg = f"WittyPi script failed with error code {process.returncode}."
        print(error_msg)
        return (False, error_msg)
    return (True, "")

def sync_time(wittypi_path):
    """
    Synchronizes the time using WittyPi 4 Mini.

    Parameters:
        wittypi_path (str): Path to the WittyPi directory.
    
    Returns:
        tuple: (True, "") if synchronization is successful,
               (False, error_message) if an error occurs.
    """
    try:
        process, send_command = start_wittypi_process(wittypi_path)

        sys_time = None
        rtc_time = None

        # Read output and check times
        for line in iter(process.stdout.readline, ""):
            line = line.strip()
            sys_time_match = re.search(r'Your system time is:\s+([0-9-]+ [0-9:]+)', line)
            rtc_time_match = re.search(r'Your RTC time is:\s+([0-9-]+ [0-9:]+)', line)

            if sys_time_match:
                sys_time_str = sys_time_match.group(1)
                sys_time = datetime.datetime.strptime(sys_time_str, '%Y-%m-%d %H:%M:%S')
            if rtc_time_match:
                rtc_time_str = rtc_time_match.group(1)
                rtc_time = datetime.datetime.strptime(rtc_time_str, '%Y-%m-%d %H:%M:%S')

            if sys_time and rtc_time:
                diff = abs((sys_time - rtc_time).total_seconds())
                print(f"🕒 System time: {sys_time_str}, RTC time: {rtc_time_str} (Difference: {diff} seconds)")
                if diff >= 5:
                    print("⚠️ Time difference is 5 seconds or more. Synchronizing...")
                    send_command("3", 3)
                else:
                    print("✅ Times are synchronized (difference is less than 5 seconds).")
                break

        # End the script
        send_command("13", 0.5)
        stdout, stderr = process.communicate()

        return handle_process_result(process, stdout, stderr)
    except Exception as e:
        error_msg = f"⚠️ Error during time synchronization: {e}"
        print(error_msg)
        return (False, error_msg)

def schedule_deep_sleep(startup_time_str, wittypi_path):
    """
    Schedules the next shutdown and startup using WittyPi 4 Mini.

    Parameters:
        startup_time_str (str): Startup time in the format "dd HH:MM:SS".
        wittypi_path (str): Path to the WittyPi directory.
    
    Returns:
        tuple: (True, "") if scheduling is successful, or (False, error_message) if an error occurs.
    """
    try:
        process, send_command = start_wittypi_process(wittypi_path)

        # Send commands to schedule startup
        send_command("5")
        send_command(startup_time_str)
        print("Startup schedule set.")
        send_command("13", 0.5)

        stdout, stderr = process.communicate()
        print(stdout)

        return handle_process_result(process, stdout, stderr)
    except Exception as e:
        error_msg = f"⚠️ Error while scheduling WittyPi: {e}"
        print(error_msg)
        return (False, error_msg)
