import subprocess
import time
import re

def schedule_deep_sleep(shutdown_time_str, startup_time_str, wittypi_path):
    """
    Schedule the next shutdown and startup using WittyPi 4 Mini.

    Parameters:
        shutdown_time_str (str): Time for shutdown in format "dd HH:MM:SS".
        startup_time_str (str): Time for startup in format "dd HH:MM:SS".
        wittypi_path (str): Path to the WittyPi directory.
    """
    try:
        # Path to wittyPi.sh
        wittypi_script = "wittyPi.sh"

        # Start wittyPi.sh with bash
        process = subprocess.Popen(
            ["bash", wittypi_script],
            cwd=wittypi_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        def send_command(command, delay=1):
            """
            Send a command to the WittyPi script.
            """
            process.stdin.write(command + "\n")
            process.stdin.flush()
            time.sleep(delay)

        def check_time_difference():
            """
            Reads output line by line and checks if system time and RTC time differ.
            If they differ, triggers synchronization.
            """

            sys_time = None
            rtc_time = None

            try:
                # Iterujeme přes výstup po řádcích
                for line in iter(process.stdout.readline, ""):
                    line = line.strip()

                    # Match system time and RTC time
                    sys_time_match = re.search(r'Your system time is:\s+([0-9-]+ [0-9:]+)', line)
                    rtc_time_match = re.search(r'Your RTC time is:\s+([0-9-]+ [0-9:]+)', line)

                    if sys_time_match:
                        sys_time = sys_time_match.group(1)
                    if rtc_time_match:
                        rtc_time = rtc_time_match.group(1)

                    if sys_time and rtc_time:
                        print(f"🕒 System Time: {sys_time}, RTC Time: {rtc_time}")

                        if sys_time != rtc_time:
                            print("⚠️ Time is not synchronized. Synchronizing...")
                            send_command("3", 3)
                        else:
                            print("✅ Time is synchronized.")
                        return
            except Exception as e:
                print(f"⚠️ Error in sync time: {e}")

        # Send "4" for 'Schedule next shutdown'
        send_command("4")
        send_command(shutdown_time_str)

        print("Shutdown scheduled.")

        # Send "5" for 'Schedule next startup'
        send_command("5")
        send_command(startup_time_str)

        print("Startup scheduled.")

        check_time_difference()    
        print("Time sync done")

        # Exit the script with "13"
        send_command("13", 0.5)

        # Capture output
        stdout, stderr = process.communicate()

        # Print outputs for debugging
        print("WittyPi stdout:")
        print(stdout)
        if stderr.strip():
            print("⚠️ WittyPi stderr:")
            print(stderr)

        if process.returncode == 0:
            print(f"✅ Scheduled: shutdown at {shutdown_time_str}, startup at {startup_time_str}.")
        else:
            print(f"❌ WittyPi script failed with error code {process.returncode}.")
    except Exception as e:
        print(f"⚠️ Error while scheduling WittyPi: {e}")
