# Python libraries
import argparse
import sys

# Local libraries.
from .constants import (
    APP_TITLE,
    LAUNCHER_TRIGGER,
    LAUNCHER_TRIGGER_MASK,
    PERMISSION_CHECK_EXIT,
)
from .app import (
    AppDelegate,
    NSApplication
)
from .launcher import (
    check_permissions,
    ensure_accessibility_permissions,
    install_startup,
    uninstall_startup
)
from .health_checks import (
    health_check_decorator
)


# Main executable for running the application from the command line.
@health_check_decorator
def main():
    parser = argparse.ArgumentParser(description=f"macOS {APP_TITLE} Overlay App - Dedicated window that can be summoned and dismissed with the keyboard command Option+Space.")
    parser.add_argument(
        "--install-startup",
        action="store_true",
        help="Install the app to run at login",
    )
    parser.add_argument(
        "--uninstall-startup",
        action="store_true",
        help="Uninstall the app from running at login",
    )
    parser.add_argument(
        "--check-permissions",
        action="store_true",
        help="Check Accessibility permissions only"
    )
    args = parser.parse_args()

    if args.install_startup:
        install_startup()
        return

    if args.uninstall_startup:
        uninstall_startup()
        return

    if args.check_permissions:
        is_trusted = check_permissions(ask=False)
        print("Permissions granted:", is_trusted)
        sys.exit(0 if is_trusted else PERMISSION_CHECK_EXIT)

    # Ensure permissions before proceeding
    ensure_accessibility_permissions()
    # Default behavior: run the app and inform user of startup options
    print()
    print(f"Starting macos-{APP_TITLE.lower()}-overlay.")
    print()
    print(f"To run at login, use:      macos-{APP_TITLE.lower()}-overlay --install-startup")
    print(f"To remove from login, use: macos-{APP_TITLE.lower()}-overlay --uninstall-startup")
    print()
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()



if __name__ == "__main__":
    # Execute the decorated main function.
    main()
