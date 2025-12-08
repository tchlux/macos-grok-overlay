# Python libraries
import json
import time
from pathlib import Path

# Apple libraries
from AppKit import (
    NSColor,
    NSEvent,
    NSFont,
    NSKeyDown,
    NSMakeRect,
    NSRoundedBezelStyle,
    NSTextAlignmentCenter,
    NSTextField,
    NSView,
)
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventKeyboardGetUnicodeString,
    CGEventGetFlags,
    CGEventGetIntegerValueField,
    kCGEventKeyDown,
    kCGKeyboardEventKeycode,
)
from AppKit import (
    NSEventModifierFlagOption,
    NSEventModifierFlagCommand,
    NSEventModifierFlagControl,
    NSEventModifierFlagShift,
)


# Local libraries
from .constants import LAUNCHER_TRIGGER, LAUNCHER_TRIGGER_MASK
from .health_checks import LOG_DIR

# File for storing the custom trigger
TRIGGER_FILE = LOG_DIR / "custom_trigger.json"
SPECIAL_KEY_NAMES = {
    49: "Space", 36: "Return", 53: "Escape",
    122: "F1", 120: "F2", 99: "F3", 118: "F4",
    96: "F5", 97: "F6", 98: "F7", 100: "F8",
    101: "F9", 109: "F10", 103: "F11", 111: "F12",
    123: "Left Arrow", 124: "Right Arrow",
    125: "Down Arrow", 126: "Up Arrow"
}
handle_new_trigger = None


# Update the trigger menu item label.
def update_menu_trigger_label(app):
    flags = LAUNCHER_TRIGGER.get("flags", 0)
    key = LAUNCHER_TRIGGER.get("key", "")
    app.updateTriggerMenu(get_trigger_string(None, flags, key))


# Load trigger from JSON file if it exists
def load_custom_launcher_trigger(app):
    if TRIGGER_FILE.exists():
        try:
            with open(TRIGGER_FILE, "r") as f:
                data = json.load(f)
                launcher_trigger = {"flags": data["flags"], "key": data["key"]}
            print(f"Overwriting default with a custom launch trigger:\n  {launcher_trigger}", flush=True)
            print(f"Disable custom override and return to default by deleting the file:\n  {TRIGGER_FILE}", flush=True)
            LAUNCHER_TRIGGER.update(launcher_trigger)
            update_menu_trigger_label(app)
        except (json.JSONDecodeError, KeyError):
            pass


# Set the custom trigger.
def set_custom_launcher_trigger(app):
    app.showWindow_(None)
    print("Setting new launcher trigger.", flush=True)
    # Disable the current trigger
    LAUNCHER_TRIGGER["flags"] = None
    LAUNCHER_TRIGGER["key"] = None
    # Get the content view bounds
    content_view = app.window.contentView()
    content_bounds = content_view.bounds()
    # Create the overlay view to shade the main application
    overlay_view = NSView.alloc().initWithFrame_(content_bounds)
    overlay_view.setWantsLayer_(True)
    overlay_view.layer().setBackgroundColor_(NSColor.colorWithWhite_alpha_(0.0, 0.5).CGColor())  # Semi-transparent black
    # Define container dimensions
    container_width = 400
    container_height = 180
    container_x = (content_bounds.size.width - container_width) / 2
    container_y = (content_bounds.size.height - container_height) / 2
    container_frame = NSMakeRect(container_x, container_y, container_width, container_height)
    container_view = NSView.alloc().initWithFrame_(container_frame)
    container_view.setWantsLayer_(True)
    container_view.layer().setBackgroundColor_(app.drag_area.layer().backgroundColor())  # Match app.drag_area
    container_view.layer().setCornerRadius_(10)  # Rounded corners for overlay
    # Define message label dimensions
    message_label_width = container_width
    message_label_height = 40
    message_label_x = 0
    message_label_y = container_height - message_label_height - 30
    # Define minimum separation
    min_separation = 20
    # Define trigger display container dimensions
    trigger_display_container_width = 280
    trigger_display_container_height = 38
    trigger_display_container_x = (container_width - trigger_display_container_width) / 2
    trigger_display_container_y = message_label_y - min_separation - trigger_display_container_height
    # Define trigger display dimensions (inside the container)
    trigger_display_width = trigger_display_container_width
    trigger_display_height = trigger_display_container_height  # Match container height for vertical centering
    trigger_display_x = 0
    trigger_display_y = -10
    # Create the static message label
    message_label_frame = NSMakeRect(message_label_x, message_label_y, message_label_width, message_label_height)
    message_label = NSTextField.alloc().initWithFrame_(message_label_frame)
    message_label.setStringValue_("Press the new trigger key combination now.")  # Static text
    message_label.setBezeled_(False)
    message_label.setDrawsBackground_(False)
    message_label.setEditable_(False)
    message_label.setSelectable_(False)
    message_label.setAlignment_(NSTextAlignmentCenter)
    message_label.setFont_(NSFont.boldSystemFontOfSize_(17))  # Large regular font
    # Create the trigger display container with lighter color and rounded corners
    trigger_display_container_frame = NSMakeRect(trigger_display_container_x, trigger_display_container_y, trigger_display_container_width, trigger_display_container_height)
    trigger_display_container = NSView.alloc().initWithFrame_(trigger_display_container_frame)
    trigger_display_container.setWantsLayer_(True)
    trigger_display_container.layer().setBackgroundColor_(NSColor.lightGrayColor().CGColor())  # Lighter color
    trigger_display_container.layer().setCornerRadius_(5)  # Rounded corners
    # Create the trigger display inside the container
    trigger_display_frame = NSMakeRect(trigger_display_x, trigger_display_y, trigger_display_width, trigger_display_height)
    trigger_display = NSTextField.alloc().initWithFrame_(trigger_display_frame)
    trigger_display.setStringValue_("Waiting for key press...")  # Initial "waiting" text
    trigger_display.setBezeled_(False)
    trigger_display.setDrawsBackground_(False)  # Transparent to show container's background
    trigger_display.setEditable_(False)
    trigger_display.setSelectable_(False)
    trigger_display.setAlignment_(NSTextAlignmentCenter)
    trigger_display.setFont_(NSFont.systemFontOfSize_(16))  # Large regular font
    # Assemble the view hierarchy
    trigger_display_container.addSubview_(trigger_display)
    container_view.addSubview_(message_label)
    container_view.addSubview_(trigger_display_container)
    overlay_view.addSubview_(container_view)
    content_view.addSubview_(overlay_view)
    # Define the handler for the new trigger
    def custom_handle_new_trigger(event, flags, keycode):
        launcher_trigger = {"flags": flags, "key": keycode}
        with open(TRIGGER_FILE, "w") as f:
            json.dump(launcher_trigger, f)
        LAUNCHER_TRIGGER.update(launcher_trigger)
        try:
            update_menu_trigger_label(app)
        except Exception:
            pass
        trigger_str = get_trigger_string(event, flags, keycode)
        print("New launcher trigger set:", flush=True)
        print(f"  {launcher_trigger}", flush=True)
        print(f"  {trigger_str}", flush=True)
        # Update only the trigger display, not the message label
        trigger_display.setStringValue_(trigger_str)
        # Remove the overlay after 3 seconds
        overlay_view.performSelector_withObject_afterDelay_("removeFromSuperview", None, 1.5)
        # Reset the handler
        global handle_new_trigger
        handle_new_trigger = None
        app.showWindow_(None)
        return None
    # Set the global handler
    global handle_new_trigger
    handle_new_trigger = custom_handle_new_trigger

# Helper function to get modifier names
def get_modifier_names(flags):
    modifier_names = []
    if flags & NSEventModifierFlagShift:
        modifier_names.append("Shift")
    if flags & NSEventModifierFlagControl:
        modifier_names.append("Control")
    if flags & NSEventModifierFlagOption:
        modifier_names.append("Option")
    if flags & NSEventModifierFlagCommand:
        modifier_names.append("Command")
    return modifier_names

# Get human-readable string for the trigger
def get_trigger_string(event, flags, keycode):
    modifier_names = get_modifier_names(flags)
    key_name = SPECIAL_KEY_NAMES.get(keycode)
    if not key_name:
        if event is not None:
            key_name = NSEvent.eventWithCGEvent_(event).characters()
        else:
            key_name = {
                0:"A",1:"S",2:"D",3:"F",4:"H",5:"G",6:"Z",7:"X",8:"C",9:"V",
                11:"B",12:"Q",13:"W",14:"E",15:"R",16:"Y",17:"T",
                31:"O",35:"P",32:"U",34:"I",46:"M",45:"N",47:"?",44:",",
                18:"1",19:"2",20:"3",21:"4",22:"6",23:"5",25:"9",29:"0",
                27:"7",24:"=",26:"-",28:"8",43:";",41:"'",42:"\\",39:"L",38:"J",37:"K"
            }.get(keycode, str(keycode))
    return " + ".join(modifier_names + [key_name]) if modifier_names else key_name

# Global event listener for showing/hiding the application and setting new triggers
def global_show_hide_listener(app):
    def listener(proxy, event_type, event, refcon):
        if event_type == kCGEventKeyDown:
            keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            flags = CGEventGetFlags(event) & LAUNCHER_TRIGGER_MASK
            if (None in set(LAUNCHER_TRIGGER.values())) and handle_new_trigger:
                print("  received keys, establishing new trigger..", flush=True)
                handle_new_trigger(event, flags, keycode)
                return None
            elif (flags == LAUNCHER_TRIGGER["flags"]) and (keycode == LAUNCHER_TRIGGER["key"]):
                if app.window.isKeyWindow():
                    app.hideWindow_(None)
                else:
                    app.showWindow_(None)
                return None
        return event
    return listener
