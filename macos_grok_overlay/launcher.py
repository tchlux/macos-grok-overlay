# Python libraries.
import getpass
import os
import subprocess
import sys
import time
from pathlib import Path

# Apple libraries.
import plistlib
from Foundation import NSDictionary
from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt

# Local libraries
from .constants import APP_TITLE
from .health_checks import reset_crash_counter


# Get the executable path.
def get_executable():
    if getattr(sys, "frozen", False):  # Running from a py2app bundle
        assert (".app" in sys.argv[0]), f"Expected the first command line argument to have a directory ending in `.app`, but none do. {sys.argv[0]}"
        # Locate the executable within the .app bundle
        app_path = sys.argv[0]
        while not app_path.endswith(".app"):
            app_path = os.path.dirname(app_path)
        executable = os.path.join(app_path, "Contents", "MacOS", f"macos-{APP_TITLE.lower()}-overlay")
        program_args = [executable]
    else:  # Running from pip installation
        program_args = [sys.executable, "-m", f"macos_{APP_TITLE.lower()}_overlay"]
    return program_args

# Install the app as a startup application using a Launch Agent.
def install_startup():
    # Get the absolute path to the macos-*-overlay script
    username = getpass.getuser()
    program_args = get_executable()
    # Define the PLIST data..
    plist = {
        "Label": f"com.{username}.macos{APP_TITLE.lower()}overlay",
        "ProgramArguments": program_args,
        "RunAtLoad": True,
        "KeepAlive": True,  # Will be restarted automatically on failure.
    }
    launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
    launch_agents_dir.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agents_dir / f"com.{username}.macos{APP_TITLE.lower()}overlay.plist"
    with open(plist_path, "wb") as f:
        plistlib.dump(plist, f)
    result = os.system(f"launchctl load {plist_path}")
    if result != 0:
        print(f"Failed to load Launch Agent with exit code {result}")
        return False
    else:
        print(f"Installed as startup app. Launch Agent created at {plist_path}.")
        print(f"To disable, run: macos-{APP_TITLE.lower()}-overlay --uninstall-startup")
        return True

# Uninstall the app from running at login.
def uninstall_startup():
    username = getpass.getuser()
    launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
    plist_path = launch_agents_dir / f"com.{username}.macos{APP_TITLE.lower()}overlay.plist"
    if plist_path.exists():
        try:
            os.system(f"launchctl unload {plist_path}")
            print(f"Uninstalled Launch Agent.")
        except Exception as e:
            print(f"Failed to uninstall launch agent. Encountered exception when running `launchctl unload {plist_path}`.\n{e}\n")
        print(f"Removed {plist_path}.")
        os.remove(plist_path)
        return True
    else:
        print("Launch Agent not found. Nothing to uninstall.")
        return False

# Check if the current process has Accessibility permissions.
def check_permissions(ask=True):
    print("\nChecking permission to utilize macOS Accessibility features to listen for the Option+Space keyboard sequence. If permission is not currently granted, a request will be made through the dialogue for the current executor (e.g., Terminal, python3, ...).\n", flush=True)
    options = NSDictionary.dictionaryWithObject_forKey_(
        True,
        kAXTrustedCheckOptionPrompt
    )
    is_trusted = AXIsProcessTrustedWithOptions(options if ask else None)
    return is_trusted

# Spawn a child process to check the latest permission status.
def get_updated_permission_status():
    result = subprocess.run(
        get_executable() + ["--check-permissions"],
        capture_output=True,
        text=True
    )
    return result.returncode == 0

# Wait for permissions to be granted, checking periodically.
def wait_for_permissions(max_wait_sec=60, wait_interval_sec=5):
    elapsed = 0
    while elapsed < max_wait_sec:
        if get_updated_permission_status():
            return True
        time.sleep(wait_interval_sec)
        elapsed += wait_interval_sec
        reset_crash_counter()
    return False

# Ensure Accessibility permissions are granted, relaunching if necessary.
def ensure_accessibility_permissions():
    # Prompt the user (this also triggers the macOS permission dialog)
    if check_permissions():  # Initial call to prompt
        return
    # Wait for permissions to be granted
    if wait_for_permissions():
        print("Permissions granted, exiting application (to be restarted automatically)...")
        return
    else:
        print("Permissions not granted within the time limit. Uninstalling application, since this installation must have failed.")
        uninstall_startup()

