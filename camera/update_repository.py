import os
import shutil
import subprocess
import sys
from blynk import update_blynk_pin_value


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

        ok, out = _run(["git", "fetch", "origin"])
        if not ok:
            print(f"git fetch failed: {out}")
            _report_error(config, f"fetch failed: {out}")
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
