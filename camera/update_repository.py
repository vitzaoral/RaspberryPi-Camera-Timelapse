import os
import subprocess
import sys

def check_and_update_repository(repo_path):
    """
    Checks for updates in the repository, pulls changes if available,
    and restarts the script.
    """
    try:
        # Change to the repository directory
        os.chdir(repo_path)

        # Fetch the latest changes
        subprocess.run(["git", "fetch"], check=True)

        # Check if the local branch is behind
        local_commit = subprocess.check_output(["git", "rev-parse", "@"]).strip()
        remote_commit = subprocess.check_output(["git", "rev-parse", "@{u}"]).strip()

        if local_commit != remote_commit:
            print("New version detected. Pulling changes...")
            # Pull the latest changes
            subprocess.run(["git", "pull"], check=True)

            # Ensure the updated script exists and is readable
            main_script = os.path.join(repo_path, "main.py")
            if os.path.isfile(main_script) and os.access(main_script, os.R_OK):
                print("Restarting script with the new version...")
                os.execv(sys.executable, [sys.executable, main_script])
            else:
                print("Error: Updated main.py is not accessible or missing.")
                sys.exit(1)

        else:
            print("No updates available. Continuing...")
    except subprocess.CalledProcessError as e:
        print(f"Error checking for updates: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

# Path to your camera directory where main.py resides
repo_path = "/path/to/your/repository/camera"

# Call the function at the start of your script
check_and_update_repository(repo_path)

# Continue with the rest of your script
print("Running the main program...")
