import os
import shutil
import subprocess
import sys
import time
from blynk import update_blynk_pin_value

FETCH_ATTEMPTS = 2
FETCH_RETRY_DELAY_S = 5
# Abort a fetch that crawls below 1 kB/s for 20 s instead of sitting on the
# 60 s subprocess timeout — on the marginal apiary link a stalled TLS
# handshake is the common failure and a fresh attempt usually gets through.
GIT_LOW_SPEED = ["-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=20"]


def _run(cmd, cwd=None):
    """Run a subprocess, return (ok, combined_output). Captures both streams."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return True, (result.stdout or "") + (result.stderr or "")
    except subprocess.CalledProcessError as e:
        return False, f"{' '.join(cmd)} exit={e.returncode}: {(e.stderr or e.stdout or '').strip()}"
    except subprocess.TimeoutExpired:
        return False, f"{' '.join(cmd)} timed out"
    except Exception as e:
        return False, f"{' '.join(cmd)} raised {e}"


def _report_error(config, message):
    """Surface update failures on the Blynk error pin so the user can see them."""
    try:
        update_blynk_pin_value(
            f"OTA: {message[:180]}",
            config["blynk_camera_auth"],
            config["blynk_camera_error_pin"],
        )
    except Exception as e:
        print(f"Also failed to report error to Blynk: {e}")


def _wipe_pycache(root):
    for dirpath, dirnames, _ in os.walk(root):
        for d in list(dirnames):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)


def check_and_update_repository(config):
    """
    Fetch origin, and if there is a newer commit, hard-reset the working tree
    to origin/main and restart the script.

    Uses --hard reset instead of `git pull` so local edits on the Pi (common
    source of silent failures) don't block the update. Errors are written to
    the Blynk error pin so they're visible without SSH access.

    The trigger flag is cleared up front so a broken update can't loop, but a
    fetch that fails on the network re-arms it: the request must survive a
    bad-link cycle, otherwise an update silently never happens.
    """
    repo_path = config["repo_path"]
    blynk_camera_auth = config["blynk_camera_auth"]
    blynk_camera_run_update_pin = config["blynk_camera_run_update_pin"]

    # Clear the trigger flag first so we don't keep retrying on every wake-up
    # even when the actual update fails.
    update_blynk_pin_value(0, blynk_camera_auth, blynk_camera_run_update_pin)

    original_dir = os.getcwd()
    try:
        os.chdir(repo_path)

        ok, out = False, ""
        for attempt in range(1, FETCH_ATTEMPTS + 1):
            ok, out = _run(["git"] + GIT_LOW_SPEED + ["fetch", "origin"])
            if ok:
                break
            print(f"git fetch failed (attempt {attempt}/{FETCH_ATTEMPTS}): {out}")
            if attempt < FETCH_ATTEMPTS:
                time.sleep(FETCH_RETRY_DELAY_S)
        if not ok:
            _report_error(config, f"fetch failed, will retry next cycle: {out}")
            update_blynk_pin_value(1, blynk_camera_auth, blynk_camera_run_update_pin)
            return

        local = subprocess.check_output(["git", "rev-parse", "@"], text=True).strip()
        try:
            remote = subprocess.check_output(
                ["git", "rev-parse", "origin/main"], text=True
            ).strip()
        except subprocess.CalledProcessError as e:
            print(f"git rev-parse origin/main failed: {e}")
            _report_error(config, "cannot resolve origin/main")
            return

        if local == remote:
            print("No updates available. Continuing...")
            return

        print(f"New version detected (local={local[:8]} remote={remote[:8]}). Resetting...")

        ok, out = _run(["git", "reset", "--hard", "origin/main"])
        if not ok:
            print(f"git reset failed: {out}")
            _report_error(config, f"reset failed: {out}")
            return

        _wipe_pycache(repo_path)

        main_script = os.path.join(repo_path, "camera/main.py")
        if not (os.path.isfile(main_script) and os.access(main_script, os.R_OK)):
            _report_error(config, "main.py missing after reset")
            return

        print("Restarting script with the new version...")
        os.execv(sys.executable, [sys.executable, main_script])

    except Exception as e:
        print(f"Unexpected error during update: {e}")
        _report_error(config, f"unexpected: {e}")
    finally:
        os.chdir(original_dir)
