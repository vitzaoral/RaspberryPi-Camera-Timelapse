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

def sync_time(wittypi_path, max_attempts=5):
    """
    Synchronizes the system and RTC time using WittyPi 4 Mini.
    Tries up to max_attempts times until the time difference is less than 5 seconds.
    
    Parameters:
        wittypi_path (str): Path to the WittyPi directory.
        max_attempts (int): Maximum number of synchronization attempts.
    
    Returns:
        tuple: (True, "") if synchronization is successful,
               (False, error_message) if all attempts fail.
    """

    for attempt in range(1, max_attempts + 1):
        print(f"🔄 Attempt {attempt}/{max_attempts} to synchronize time.")
        synchronized = False  # Flag to check if synchronization succeeded
        diff = None
        try:
            process, send_command = start_wittypi_process(wittypi_path)
            sys_time = None
            rtc_time = None

            # Read the output line by line from the process
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

                # Once both times are read, check the difference
                if sys_time and rtc_time:
                    diff = abs((sys_time - rtc_time).total_seconds())
                    print(f"🕒 System time: {sys_time_str}, RTC time: {rtc_time_str} (Difference: {diff} seconds)")
                    if diff < 5:
                        print("✅ Times are synchronized.")
                        synchronized = True
                    else:
                        print("⚠️ Time difference is 5 seconds or more. Sending synchronization command...")
                        # Send the synchronization command and wait for 5 seconds
                        send_command("3", 5)
                    break

            # End the script regardless of synchronization state
            send_command("13", 0.5)
            stdout, stderr = process.communicate()
            # We check the process termination result, but this does not determine synchronization success.
            result = handle_process_result(process, stdout, stderr)
            if not result[0]:
                print(f"Error terminating process: {result[1]}")

            # Only return success if the time difference is acceptable
            if synchronized:
                return (True, "")
            else:
                print(f"❌ Attempt {attempt} did not successfully synchronize (diff: {diff} seconds).")
        except Exception as e:
            print(f"❌ Attempt {attempt} failed with error: {e}")

        print("⏳ Waiting 5 seconds before next attempt...")
        time.sleep(5)

    return (False, "Time synchronization failed!")


def schedule_deep_sleep(startup_time_str, wittypi_path, max_attempts=5):
    """
    Schedules the next startup using WittyPi 4 Mini.
    Tries up to max_attempts times until the scheduled startup time matches startup_time_str.
    
    Expected output from wittyPi.sh after scheduling:
    ... 
    5. Schedule next startup  [30 09:00:00]
    ...
    Where the time in square brackets is the current auto startup time.
    
    Parameters:
        startup_time_str (str): Startup time in the format "dd HH:MM:SS".
        wittypi_path (str): Path to the WittyPi directory.
        max_attempts (int): Maximum number of scheduling attempts.
    
    Returns:
        tuple: (True, "") if scheduling is successful,
               (False, error_message) if all attempts fail.
    """
    for attempt in range(1, max_attempts + 1):
        print(f"🔄 Scheduling startup time, attempt {attempt}/{max_attempts}...")
        try:
            # First, schedule the startup time
            process, send_command = start_wittypi_process(wittypi_path)
            send_command("5")                    # Command to schedule startup
            send_command(startup_time_str)         # Send the desired startup time
            print(f'Setting startup time to "{startup_time_str}"')
            send_command("13", 0.5)                # Exit the wittyPi script
            stdout, stderr = process.communicate()
            result = handle_process_result(process, stdout, stderr)
            if not result[0]:
                print("Error during scheduling: " + result[1])
                time.sleep(5)
                continue

            # Now, verify that the scheduled startup time is correct
            process_verify, _ = start_wittypi_process(wittypi_path)
            scheduled_startup = None
            # Look for the line with "Schedule next startup" and the time in square brackets.
            # For example: "5. Schedule next startup  [30 09:00:00]"
            for line in iter(process_verify.stdout.readline, ""):
                line = line.strip()
                match = re.search(r'Schedule next startup\s+\[([0-9]{2}\s[0-9]{2}:[0-9]{2}:[0-9]{2})\]', line)
                if match:
                    scheduled_startup = match.group(1)
                    break
            process_verify.terminate()

            if scheduled_startup is None:
                print("Could not read the scheduled startup time from the output.")
            elif scheduled_startup == startup_time_str:
                print("✅ Startup schedule verified successfully.")
                return (True, "")
            else:
                print(f"⚠️ Verification failed. Expected startup time {startup_time_str}, but got {scheduled_startup}.")
        except Exception as e:
            print(f"❌ Attempt {attempt} failed with error: {e}")
        
        print("⏳ Waiting 5 seconds before next scheduling attempt...")
        time.sleep(5)
    
    return (False, "Startup schedule verification failed after multiple attempts!")