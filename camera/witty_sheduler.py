import subprocess
import time
import datetime
import re

PROCESS_TIMEOUT = 30


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


def communicate_with_timeout(process, timeout=PROCESS_TIMEOUT):
    """
    Calls process.communicate() with a timeout. Kills the process on timeout.
    Returns (stdout, stderr, timed_out).
    """
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return stdout, stderr, False
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        return stdout, stderr, True


def sync_time(wittypi_path, last_sync_iso=None, max_attempts=5):
    """
    Synchronizes the system and RTC time using WittyPi 4 Mini.

    If no synchronization has occurred today (last_sync_iso is None or from a previous date),
    performs a one-shot sync by sending the sync command and returns immediately.

    If synchronization has already occurred today, runs the original retry logic up to
    max_attempts, verifying that the time difference is less than 5 seconds.

    Parameters:
        wittypi_path (str): Path to the WittyPi directory.
        last_sync_iso (str or None): ISO-8601 timestamp of the last synchronization from Blynk.
        max_attempts (int): Maximum number of synchronization attempts when retrying.

    Returns:
        tuple:
          - success (bool)
          - error_message (str)
          - new_sync_iso (str): ISO-8601 timestamp of the new synchronization (or original last_sync_iso if skipped).
    """
    today = datetime.date.today()

    # Determine if a synchronization has already occurred today
    if last_sync_iso:
        try:
            last_dt = datetime.datetime.fromisoformat(last_sync_iso)
        except ValueError:
            last_dt = None
    else:
        last_dt = None

    # 1) If no sync today, perform one-shot sync and return
    if not last_dt or last_dt.date() != today:
        print("🔧 No sync recorded today, performing one-shot synchronization...")
        try:
            process, send_command = start_wittypi_process(wittypi_path)
            # Send sync command and wait 5 seconds
            send_command("3", 5)
            # Exit interactive mode
            send_command("13", 0.5)
            stdout, stderr, timed_out = communicate_with_timeout(process)
            if timed_out:
                return False, "One-shot sync timed out", None

            new_iso = datetime.datetime.now().isoformat()
            print(f"✅ One-shot synchronization completed at {new_iso}")
            return True, "", new_iso
        except Exception as e:
            print("❌ Error during one-shot synchronization:", e)
            return False, str(e), None

    # 2) If already synced today, run retry logic
    print("ℹ️ Synchronization already performed today, running retry logic...")
    for attempt in range(1, max_attempts + 1):
        print(f"🔄 Attempt {attempt}/{max_attempts} to synchronize time.")
        try:
            # Phase 1: Read current times
            process, send_command = start_wittypi_process(wittypi_path)
            send_command("13", 0.5)  # exit immediately to prevent hang
            stdout, stderr, timed_out = communicate_with_timeout(process)

            if timed_out:
                print(f"❌ WittyPi process timed out on attempt {attempt}")
                time.sleep(5)
                continue

            sys_time = rtc_time = None
            for line in stdout.split("\n"):
                line = line.strip()
                sys_match = re.search(r'Your system time is:\s+([0-9-]+ [0-9:]+)', line)
                rtc_match = re.search(r'Your RTC time is:\s+([0-9-]+ [0-9:]+)', line)
                if sys_match:
                    sys_time = datetime.datetime.strptime(sys_match.group(1), '%Y-%m-%d %H:%M:%S')
                if rtc_match:
                    rtc_time = datetime.datetime.strptime(rtc_match.group(1), '%Y-%m-%d %H:%M:%S')

            if sys_time and rtc_time:
                diff = abs((sys_time - rtc_time).total_seconds())
                print(f"🕒 System time: {sys_time}, RTC time: {rtc_time} (Δ {diff}s)")
                if diff < 5:
                    print("✅ Times are already synchronized.")
                    return True, "", None
                else:
                    # Phase 2: Sync needed
                    print("⚠️ Δ ≥ 5s, sending sync command...")
                    process2, send_command2 = start_wittypi_process(wittypi_path)
                    send_command2("3", 5)
                    send_command2("13", 0.5)
                    _, _, timed_out2 = communicate_with_timeout(process2)
                    if timed_out2:
                        print(f"❌ Sync process timed out on attempt {attempt}")
            else:
                print(f"❌ Could not parse time from WittyPi output on attempt {attempt}")

        except Exception as e:
            print(f"❌ Exception during attempt {attempt}: {e}")

        print("⏳ Waiting 5s before next attempt...")
        time.sleep(5)

    print("❌ All synchronization attempts failed.")
    return False, "Time synchronization failed!", None


def schedule_deep_sleep(startup_time_str, wittypi_path, max_attempts=5):
    """
    Schedules the next startup using WittyPi 4 Mini.

    Tries up to max_attempts times until the scheduled startup time matches startup_time_str.

    Parameters:
        startup_time_str (str): Startup time in the format "dd HH:MM:SS".
        wittypi_path (str): Path to the WittyPi directory.
        max_attempts (int): Maximum number of scheduling attempts.

    Returns:
        tuple:
          - True, "" if scheduling is successful,
          - False, error_message if all attempts fail. error_message contains per-attempt diagnostics.
    """
    errors = []

    for attempt in range(1, max_attempts + 1):
        print(f"🔄 Attempt {attempt}/{max_attempts} to schedule startup at {startup_time_str}...")
        try:
            # 1) Send the schedule command
            process, send_command = start_wittypi_process(wittypi_path)
            send_command("5")                    # enter "schedule startup" menu
            send_command(startup_time_str)       # send desired time, e.g. "30 09:00:00"
            print(f"  → setting startup time to {startup_time_str}")
            send_command("13", 0.5)              # exit the menu
            stdout, stderr, timed_out = communicate_with_timeout(process)

            if timed_out:
                reason = "scheduling process timed out"
                print("  ❌", reason)
                errors.append((attempt, reason))
                time.sleep(5)
                continue

            ok, msg = handle_process_result(process, stdout, stderr)
            if not ok:
                reason = f"scheduling command failed: {msg}"
                print("  ❌", reason)
                errors.append((attempt, reason))
                time.sleep(5)
                continue

            # 2) Verify the newly scheduled time
            process_verify, send_verify = start_wittypi_process(wittypi_path)
            send_verify("13", 0.5)  # exit immediately to prevent hang
            stdout_verify, _, timed_out_verify = communicate_with_timeout(process_verify)

            if timed_out_verify:
                reason = "verification process timed out"
                print("  ❌", reason)
                errors.append((attempt, reason))
                time.sleep(5)
                continue

            scheduled_startup = None
            for line in stdout_verify.split("\n"):
                m = re.search(r'Schedule next startup\s+\[([0-9]{2}\s[0-9]{2}:[0-9]{2}:[0-9]{2})\]', line.strip())
                if m:
                    scheduled_startup = m.group(1)
                    break

            if scheduled_startup is None:
                reason = "could not read scheduled startup from output"
                print("  ❌", reason)
                errors.append((attempt, reason))
            elif scheduled_startup != startup_time_str:
                reason = (f"verification mismatch: expected {startup_time_str}, "
                          f"got {scheduled_startup}")
                print("  ⚠️", reason)
                errors.append((attempt, reason))
            else:
                print("✅ Startup schedule verified successfully.")
                return True, ""

        except Exception as e:
            reason = f"exception during attempt: {e}"
            print("❌", reason)
            errors.append((attempt, reason))

        print("⏳ Waiting 5 seconds before next attempt...")
        time.sleep(5)

    # All attempts failed — build a combined error message
    detailed = "; ".join(f"Attempt {i}: {msg}" for i, msg in errors)
    return False, f"Scheduling failed after {max_attempts} attempts: {detailed}"
