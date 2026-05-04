import subprocess
import time
import datetime
import re

PROCESS_TIMEOUT = 30
ACCEPTABLE_DRIFT_SECONDS = 5


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


def _read_times(wittypi_path):
    """
    Open wittyPi.sh, exit immediately, and parse system + RTC time from the
    banner. Returns (sys_time, rtc_time) as datetimes, or (None, None) on error.
    """
    process, send_command = start_wittypi_process(wittypi_path)
    send_command("13", 0.5)  # exit interactive menu
    stdout, _, timed_out = communicate_with_timeout(process)
    if timed_out:
        return None, None

    sys_time = rtc_time = None
    for line in stdout.split("\n"):
        line = line.strip()
        sys_match = re.search(r'Your system time is:\s+([0-9-]+ [0-9:]+)', line)
        rtc_match = re.search(r'Your RTC time is:\s+([0-9-]+ [0-9:]+)', line)
        if sys_match:
            sys_time = datetime.datetime.strptime(sys_match.group(1), '%Y-%m-%d %H:%M:%S')
        if rtc_match:
            rtc_time = datetime.datetime.strptime(rtc_match.group(1), '%Y-%m-%d %H:%M:%S')
    return sys_time, rtc_time


def _send_sync(wittypi_path):
    """
    Send the wittyPi.sh "synchronize time" command (menu item 3) and exit.
    Returns True if the process completed cleanly, False on timeout.
    """
    process, send_command = start_wittypi_process(wittypi_path)
    send_command("3", 5)     # synchronize time
    send_command("13", 0.5)  # exit menu
    _, _, timed_out = communicate_with_timeout(process)
    return not timed_out


def sync_time(wittypi_path, last_sync_iso=None, max_attempts=5, force=False):
    """
    Synchronizes system and RTC time via WittyPi 4 Mini, always with verification.

    Decision tree:
    - force=True → always run sync-and-verify loop
    - last sync today AND current drift < 5s → no-op (already in sync)
    - otherwise → run sync-and-verify loop up to max_attempts

    Each sync attempt: send wittyPi.sh "3" (sync), then re-read times and check
    that |system - RTC| < 5s. Returns success only after verification passes.

    Parameters:
        wittypi_path (str): Path to the WittyPi directory.
        last_sync_iso (str or None): ISO-8601 timestamp of last sync (from Blynk).
        max_attempts (int): Maximum sync+verify attempts.
        force (bool): If True, skip the "already synced today" shortcut and always sync.

    Returns:
        tuple (success: bool, error_message: str, new_sync_iso: str or None)
    """
    today = datetime.date.today()
    last_dt = None
    if last_sync_iso:
        try:
            last_dt = datetime.datetime.fromisoformat(last_sync_iso)
        except ValueError:
            pass

    already_synced_today = last_dt is not None and last_dt.date() == today

    # Shortcut: already synced today and drift is small → no-op
    if not force and already_synced_today:
        sys_time, rtc_time = _read_times(wittypi_path)
        if sys_time and rtc_time:
            drift = abs((sys_time - rtc_time).total_seconds())
            if drift < ACCEPTABLE_DRIFT_SECONDS:
                print(f"✅ RTC already in sync (Δ {drift}s) — skipping.")
                return True, "", None
            print(f"⚠️ Synced today but drift is {drift}s — re-syncing.")
        else:
            print("⚠️ Could not read times — running full sync.")

    # Sync-and-verify loop
    for attempt in range(1, max_attempts + 1):
        print(f"🔄 Sync attempt {attempt}/{max_attempts}")

        if not _send_sync(wittypi_path):
            print(f"❌ Sync command timed out on attempt {attempt}")
            time.sleep(5)
            continue

        sys_time, rtc_time = _read_times(wittypi_path)
        if sys_time is None or rtc_time is None:
            print(f"❌ Could not parse times after sync on attempt {attempt}")
            time.sleep(5)
            continue

        drift = abs((sys_time - rtc_time).total_seconds())
        print(f"🕒 Post-sync: system={sys_time}, RTC={rtc_time} (Δ {drift}s)")

        if drift < ACCEPTABLE_DRIFT_SECONDS:
            new_iso = datetime.datetime.now().isoformat()
            print(f"✅ Sync verified at {new_iso}")
            return True, "", new_iso

        print(f"⚠️ Drift still {drift}s — retrying in 5s.")
        time.sleep(5)

    return False, f"Time synchronization failed after {max_attempts} attempts (RTC still off)", None


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
