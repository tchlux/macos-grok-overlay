import argparse
import ctypes
import getpass
import os
import objc
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path
from AppKit import *
from WebKit import *
from Quartz import *
from Foundation import NSDictionary
from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt


WEBSITE = "https://grok.com?referrer=macos-grok-overlay"
LOGO_WHITE_PATH = "grok_logo_white.png"
LOGO_BLACK_PATH = "grok_logo_black.png"
FRAME_SAVE_NAME = "GrokWindowFrame"
APP_TITLE = "Grok"
CORNER_RADIUS = 15.0
DRAG_AREA_HEIGHT = 30
STATUS_ITEM_CONTEXT = 1


# Custom window (contains entire application).
class AppWindow(NSWindow):
    # Explicitly allow key window status
    def canBecomeKeyWindow(self):
        return True

    # Required to capture "Command+..." sequences.
    def keyDown_(self, event):
        self.delegate().keyDown_(event)


# Custom view (contains click-and-drag area on top sliver of overlay).
class DragArea(NSView):
    def initWithFrame_(self, frame):
        objc.super(DragArea, self).initWithFrame_(frame)
        self.setWantsLayer_(True)
        return self
    
    # Used to update top-bar background to (roughly) match app color.
    def setBackgroundColor_(self, color):
        self.layer().setBackgroundColor_(color.CGColor())

    # Used to capture the click-and-drag event.
    def mouseDown_(self, event):
        self.window().performWindowDragWithEvent_(event)


# The main delegate for running the overlay app.
class AppDelegate(NSObject):
    # The main application setup.
    def applicationDidFinishLaunching_(self, notification):
        # Run as accessory app
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        # Create a borderless, floating, resizable window
        self.window = AppWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(500, 200, 550, 580),
            NSBorderlessWindowMask | NSResizableWindowMask,
            NSBackingStoreBuffered,
            False
        )
        self.window.setLevel_(NSFloatingWindowLevel)
        self.window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
        )
        # Save the last position and size
        self.window.setFrameAutosaveName_(FRAME_SAVE_NAME)
        # Make window transparent so that the corners can be rounded
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(NSColor.clearColor())
        # Set up content view with rounded corners
        content_view = NSView.alloc().initWithFrame_(self.window.contentView().bounds())
        content_view.setWantsLayer_(True)
        content_view.layer().setCornerRadius_(CORNER_RADIUS)
        content_view.layer().setBackgroundColor_(NSColor.whiteColor().CGColor())
        self.window.setContentView_(content_view)
        # Set up drag area (top sliver, full width)
        content_bounds = content_view.bounds()
        self.drag_area = DragArea.alloc().initWithFrame_(
            NSMakeRect(0, content_bounds.size.height - DRAG_AREA_HEIGHT, content_bounds.size.width, DRAG_AREA_HEIGHT)
        )
        content_view.addSubview_(self.drag_area)
        # Add close button to the drag area
        close_button = NSButton.alloc().initWithFrame_(NSMakeRect(5, 5, 20, 20))
        close_button.setBordered_(False)
        close_button.setImage_(NSImage.imageWithSystemSymbolName_accessibilityDescription_("xmark.circle.fill", None))
        close_button.setTarget_(self)
        close_button.setAction_("hideWindow:")
        self.drag_area.addSubview_(close_button)
        # Set up WebKit view (below drag area)
        self.webview = WKWebView.alloc().initWithFrame_(
            NSMakeRect(0, 0, content_bounds.size.width, content_bounds.size.height - DRAG_AREA_HEIGHT)
        )
        self.webview.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)  # Resizes with window
        content_view.addSubview_(self.webview)
        url = NSURL.URLWithString_(WEBSITE)
        request = NSURLRequest.requestWithURL_(url)
        self.webview.loadRequest_(request)
        # Set up script message handler for background color changes
        configuration = self.webview.configuration()
        user_content_controller = configuration.userContentController()
        user_content_controller.addScriptMessageHandler_name_(self, "backgroundColorHandler")
        # Inject JavaScript to monitor background color changes
        script = """
            function sendBackgroundColor() {
                var bgColor = window.getComputedStyle(document.body).backgroundColor;
                window.webkit.messageHandlers.backgroundColorHandler.postMessage(bgColor);
            }
            window.addEventListener('load', sendBackgroundColor);
            new MutationObserver(sendBackgroundColor).observe(document.body, { attributes: true, attributeFilter: ['style'] });
        """
        user_script = WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(script, WKUserScriptInjectionTimeAtDocumentEnd, True)
        user_content_controller.addUserScript_(user_script)
        # Set the delegate of the window to this parent application.
        self.window.setDelegate_(self)
        # Create status bar item with logo
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSSquareStatusItemLength)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        logo_white_path = os.path.join(script_dir, LOGO_WHITE_PATH)
        self.logo_white = NSImage.alloc().initWithContentsOfFile_(logo_white_path)
        self.logo_white.setSize_(NSSize(18, 18))
        logo_black_path = os.path.join(script_dir, LOGO_BLACK_PATH)
        self.logo_black = NSImage.alloc().initWithContentsOfFile_(logo_black_path)
        self.logo_black.setSize_(NSSize(18, 18))
        # Set the initial logo image based on the current appearance
        self.updateStatusItemImage()
        # Observe system appearance changes
        self.status_item.button().addObserver_forKeyPath_options_context_(
            self, "effectiveAppearance", NSKeyValueObservingOptionNew, STATUS_ITEM_CONTEXT
        )
        # Create status bar menu
        menu = NSMenu.alloc().init()
        # Create and configure menu items with explicit targets
        show_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Show "+APP_TITLE, "showWindow:", "")
        show_item.setTarget_(self)  # Set target to self (AppDelegate)
        menu.addItem_(show_item)
        hide_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Hide "+APP_TITLE, "hideWindow:", "h")
        hide_item.setTarget_(self)  # Set target to self (AppDelegate)
        menu.addItem_(hide_item)
        home_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Home", "goToWebsite:", "g")
        home_item.setTarget_(self)  # Set target to self (AppDelegate)
        menu.addItem_(home_item)
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit", "terminate:", "q")
        quit_item.setTarget_(NSApp)  # Set target to NSApp for terminate:
        menu.addItem_(quit_item)
        uninstall_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Uninstall and Quit", "uninstallAndQuit:", "")
        uninstall_item.setTarget_(self)  # Set target to self (AppDelegate)
        menu.addItem_(uninstall_item)
        # Set the menu for the status item
        self.status_item.setMenu_(menu)
        # Add resize observer
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self, 'windowDidResize:', NSWindowDidResizeNotification, self.window
        )
        # Add local mouse event monitor for left mouse down
        self.local_mouse_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSEventMaskLeftMouseDown,  # Monitor left mouse-down events
            self.handleLocalMouseEvent  # Handler method
        )
        # Create the event tap for key-down events
        tap = CGEventTapCreate(
            kCGSessionEventTap, # Tap at the session level
            kCGHeadInsertEventTap, # Insert at the head of the event queue
            kCGEventTapOptionDefault, # Actively filter events
            CGEventMaskBit(kCGEventKeyDown), # Capture key-down events
            self.global_show_hide_listener, # Your callback function
            None # Optional user info (refcon)
        )
        if tap:
            # Integrate the tap into the run loop
            source = CFMachPortCreateRunLoopSource(None, tap, 0)
            CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopCommonModes)
            CGEventTapEnable(tap, True)
            CFRunLoopRun() # Start the run loop
        else:
            print("Failed to create event tap. Check Accessibility permissions.")
        # Make sure this window is shown and focused.
        self.showWindow_(None)
    
    # Logic to show the overlay, make it the key window, and focus on the typing area.
    def showWindow_(self, sender):
        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)
        # Execute the JavaScript to focus the textarea in the WKWebView
        self.webview.evaluateJavaScript_completionHandler_(
            "document.querySelector('textarea').focus();", None
        )

    # Hide the overlay and allow focus to return to the next visible application.
    def hideWindow_(self, sender):
        NSApp.hide_(None)
    
    # Go to the default landing website for the overlay (in case accidentally navigated away).
    def goToWebsite_(self, sender):
        url = NSURL.URLWithString_(WEBSITE)
        request = NSURLRequest.requestWithURL_(url)
        self.webview.loadRequest_(request)
    
    # Go to the default landing website for the overlay (in case accidentally navigated away).
    def uninstallAndQuit_(self, sender):
        uninstall_startup()
        NSApp.terminate_(None)

    # For capturing key commands while the key window (in focus).
    def keyDown_(self, event):
        modifiers = event.modifierFlags()
        key_command = modifiers & NSCommandKeyMask
        key_alt = modifiers & NSAlternateKeyMask
        key_shift = modifiers & NSShiftKeyMask
        key_control = modifiers & NSControlKeyMask
        key = event.charactersIgnoringModifiers()
        # Command (NOT alt)
        if (key_command or key_control) and (not key_alt):
            # Select all
            if key == 'a':
                self.window.firstResponder().selectAll_(None)
            # Copy
            elif key == 'c':
                self.window.firstResponder().copy_(None)
            # Cut
            elif key == 'x':
                self.window.firstResponder().cut_(None)
            # Paste
            elif key == 'v':
                self.window.firstResponder().paste_(None)
            # Hide
            elif key == 'h':
                self.hideWindow_(None)
            # Quit
            elif key == 'q':
                NSApp.terminate_(None)
            # # Undo (causes crash for some reason)
            # elif key == 'z':
            #     self.window.firstResponder().undo_(None)

    # Handler for capturing a click-and-drag event when not already the key window.
    @objc.python_method
    def handleLocalMouseEvent(self, event):
        if event.window() == self.window:
            # Get the click location in window coordinates
            click_location = event.locationInWindow()
            # Use hitTest_ to determine which view receives the click
            hit_view = self.window.contentView().hitTest_(click_location)
            # Check if the hit view is the drag area
            if hit_view == self.drag_area:
                # Bring the window to the front and make it key
                self.showWindow_(None)
                # Initiate window dragging with the event
                self.window.performWindowDragWithEvent_(event)
                return None  # Consume the event
        return event  # Pass unhandled events along

    # Handler for when the window resizes (adjusts the drag area).
    def windowDidResize_(self, notification):
        bounds = self.window.contentView().bounds()
        w, h = bounds.size.width, bounds.size.height
        self.drag_area.setFrame_(NSMakeRect(0, h - DRAG_AREA_HEIGHT, w, DRAG_AREA_HEIGHT))
        self.webview.setFrame_(NSMakeRect(0, 0, w, h - DRAG_AREA_HEIGHT))

    # Handler for setting the background color based on the web page background color.
    def userContentController_didReceiveScriptMessage_(self, userContentController, message):
        if message.name() == "backgroundColorHandler":
            bg_color_str = message.body()
            # Convert CSS color to NSColor (assuming RGB for simplicity)
            if bg_color_str.startswith("rgb"):
                rgb_values = [float(val) for val in bg_color_str[4:-1].split(",")]
                r, g, b = [val / 255.0 for val in rgb_values[:3]]
                color = NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 1.0)
                self.drag_area.setBackgroundColor_(color)

    # The logic for the global event listener for showing and hiding the application.
    def global_show_hide_listener(self, proxy, event_type, event, refcon):
        # Handle only key-down events
        if event_type == kCGEventKeyDown:
            # Extract the keycode (Space is 49)
            keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            # Extract modifier flags (e.g., Option, Shift, etc.)
            flags = CGEventGetFlags(event)
            key_command = flags & kCGEventFlagMaskCommand
            key_control = flags & kCGEventFlagMaskControl
            key_alt = flags & kCGEventFlagMaskAlternate
            key_shift = flags & kCGEventFlagMaskShift
            # Check for Option + Space (no other modifiers)
            if key_alt and (not key_shift) and (not key_control) and (not key_command) and (keycode == 49):
                if self.window.isKeyWindow():
                    self.hideWindow_(None)
                else:
                    self.showWindow_(None)
                # Return None to consume the event and prevent propagation
                return None
        # Return the event unchanged if it’s not Option + Space
        return event

    # Logic for checking what color the logo in the status bar should be, and setting appropriate logo.
    def updateStatusItemImage(self):
        appearance = self.status_item.button().effectiveAppearance()
        if appearance.bestMatchFromAppearancesWithNames_([NSAppearanceNameAqua, NSAppearanceNameDarkAqua]) == NSAppearanceNameDarkAqua:
            self.status_item.button().setImage_(self.logo_white)
        else:
            self.status_item.button().setImage_(self.logo_black)

    # Observer that is triggered whenever the color of the status bar logo might need to be updated.
    def observeValueForKeyPath_ofObject_change_context_(self, keyPath, object, change, context):
        if context == STATUS_ITEM_CONTEXT and keyPath == "effectiveAppearance":
            self.updateStatusItemImage()

    # System triggered appearance changes that might affect logo color.
    def appearanceDidChange_(self, notification):
        # Update the logo image when the system appearance changes
        self.updateStatusItemImage()


# Install the app as a startup application using a Launch Agent.
def install_startup():
    # Get the absolute path to the macos-*-overlay script
    script_path = os.path.abspath(sys.argv[0])
    username = os.getlogin()
    plist = {
        "Label": f"com.{username}.macos{APP_TITLE.lower()}overlay",
        "ProgramArguments": [script_path],  # Use the script directly
        "RunAtLoad": True,
        "KeepAlive": True,  # Will be restarted automatically on failure.
    }
    launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
    launch_agents_dir.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agents_dir / f"com.{username}.macos{APP_TITLE.lower()}overlay.plist"
    with open(plist_path, "wb") as f:
        plistlib.dump(plist, f)
    os.system(f"launchctl load {plist_path}")
    print(f"Installed as startup app. Launch Agent created at {plist_path}.")
    print(f"To disable, run: macos-{APP_TITLE.lower()}-overlay --uninstall-startup")

# Uninstall the app from running at login.
def uninstall_startup():
    username = os.getlogin()
    launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
    plist_path = launch_agents_dir / f"com.{username}.macos{APP_TITLE.lower()}overlay.plist"
    if plist_path.exists():
        os.system(f"launchctl unload {plist_path}")
        os.remove(plist_path)
        print(f"Uninstalled Launch Agent. Removed {plist_path}.")
    else:
        print("Launch Agent not found. Nothing to uninstall.")

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
        [sys.executable, sys.argv[0], "--check-permissions"],
        capture_output=True,
        text=True
    )
    return result.returncode == 0

# Wait for permissions to be granted, checking periodically.
def wait_for_permissions(max_wait_sec=120, wait_interval_sec=5):
    elapsed = 0
    while elapsed < max_wait_sec:
        if get_updated_permission_status():
            return True
        time.sleep(wait_interval_sec)
        elapsed += wait_interval_sec
    return False

# Relaunch the application with the same command used to start it.
def relaunch_application():
    if os.access(sys.argv[0], os.X_OK):
        # If sys.argv[0] is executable (e.g., an installed script), run it directly
        command = [sys.argv[0]] + sys.argv[1:]
    else:
        # Otherwise, assume it’s a Python script and run with the original interpreter
        command = [sys.executable] + sys.argv
    # Launch the new process
    subprocess.Popen(command, start_new_session=True)
    # Exit the current process (the child should continue regardless)
    sys.exit(0)

# Ensure Accessibility permissions are granted, relaunching if necessary.
def ensure_accessibility_permissions():
    # Prompt the user (this also triggers the macOS permission dialog)
    if check_permissions():  # Initial call to prompt
        return
    # Wait for permissions to be granted
    if wait_for_permissions():
        print("Permissions granted, exiting application (to be restarted automatically)...")
        sys.exit(0)
    else:
        print("Permissions not granted within the time limit. Uninstalling application, since this installation must have failed.")
        uninstall_startup()


# Main executable for running the application from the command line.
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
        sys.exit(0 if is_trusted else 1)

    # Ensure permissions before proceeding
    ensure_accessibility_permissions()

    # Default behavior: run the app and inform user of startup options
    print(f"Starting macos-{APP_TITLE.lower()}-overlay.")
    print(f"To run at login, use: macos-{APP_TITLE.lower()}-overlay --install-startup")
    print(f"To remove from login, use: macos-{APP_TITLE.lower()}-overlay --uninstall-startup")
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
