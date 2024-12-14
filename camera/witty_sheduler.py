import subprocess

def schedule_deep_sleep(shutdown_time_str, startup_time_str, wittypi_path):
    """
    Schedule the next shutdown and startup using WittyPi 4 Mini.

    Parameters:
        deep_sleep_interval (int or str): Duration in seconds to stay in deep sleep mode.
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

        # Send "4" for 'Schedule next shutdown'
        process.stdin.write("4\n")
        process.stdin.flush()

        # Send shutdown time
        process.stdin.write(f"{shutdown_time_str}\n")
        process.stdin.flush()

        # Send "5" for 'Schedule next startup'
        process.stdin.write("5\n")
        process.stdin.flush()

        # Send startup time
        process.stdin.write(f"{startup_time_str}\n")
        process.stdin.flush()

        # Exit the script with "13"
        process.stdin.write("13\n")
        process.stdin.flush()

        # Capture output
        stdout, stderr = process.communicate()

        # Print outputs for debugging
        print("WittyPi stdout:")
        print(stdout)
        print("WittyPi stderr:")
        print(stderr)

        if process.returncode == 0:
            print(f"Scheduled next shutdown at {shutdown_time_str} and startup at {startup_time_str}.")
        else:
            print(f"WittyPi script exited with error code {process.returncode}.")

    except Exception as e:
        print(f"Error scheduling deep sleep via WittyPi: {e}")
