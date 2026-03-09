"""
controller.py — Pause / resume / stop controller
--------------------------------------------------
Runs a keyboard listener in a background thread.
Both pre_cleanup.py and export_process.py import this and call
check_control() at each loop iteration.

Default keybinds (configurable in config.json):
    pause_key: "ctrl+f9"   → toggle pause/resume
    stop_key:  "ctrl+f10"  → emergency stop (raises StopRequested)

Usage in a loop:
    from controller import check_control, start_listener, stop_listener, StopRequested

    start_listener(config)
    try:
        while True:
            check_control()   # blocks here while paused, raises if stopped
            ... do work ...
    except StopRequested:
        print("Stopped by user.")
    finally:
        stop_listener()
"""

import threading
import time
from pynput import keyboard

# ── Shared state ───────────────────────────────────────────────────────────────

_is_paused   = False
_should_stop = False
_listener    = None
_lock        = threading.Lock()

# ── Exception ──────────────────────────────────────────────────────────────────

class StopRequested(Exception):
    """Raised by check_control() when the user presses the stop key."""
    pass

# ── Public API ─────────────────────────────────────────────────────────────────

def check_control():
    """
    Call this at the top of every loop iteration.
    - If stopped: raises StopRequested immediately.
    - If paused:  blocks here (printing a one-time message) until resumed.
    - If running: returns instantly.
    """
    if _should_stop:
        raise StopRequested("Stop key pressed.")

    if _is_paused:
        print("\n  ⏸  PAUSED — press Space to resume, Esc to stop.")
        while _is_paused and not _should_stop:
            time.sleep(0.1)
        if _should_stop:
            raise StopRequested("Stop key pressed while paused.")
        print("  ▶  RESUMED.\n")


def start_listener(config):
    """Start the background keyboard listener. Call once before your main loop."""
    global _listener, _is_paused, _should_stop

    # Reset state for fresh run
    _is_paused   = False
    _should_stop = False

    pause_combo = _parse_combo(config.get("pause_key", "ctrl+f9"))
    stop_combo  = _parse_combo(config.get("stop_key",  "ctrl+f10"))

    # Track which modifier keys are currently held
    _held_modifiers = set()
    MODIFIER_KEYS = {
        keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
        keyboard.Key.shift,  keyboard.Key.shift_r,
        keyboard.Key.alt_l,  keyboard.Key.alt_r,
    }
    MODIFIER_NAMES = {
        keyboard.Key.ctrl_l:  "ctrl",
        keyboard.Key.ctrl_r:  "ctrl",
        keyboard.Key.shift:   "shift",
        keyboard.Key.shift_r: "shift",
        keyboard.Key.alt_l:   "alt",
        keyboard.Key.alt_r:   "alt",
    }

    def modifiers_match(required_mods):
        """Check that exactly the required modifiers (and no others) are held."""
        held_names = {MODIFIER_NAMES[k] for k in _held_modifiers if k in MODIFIER_NAMES}
        return held_names == required_mods

    def on_press(key):
        global _is_paused, _should_stop
        if key in MODIFIER_KEYS:
            _held_modifiers.add(key)
            return
        trigger_key = _resolve_key(key) if isinstance(key, keyboard.KeyCode) else key
        if trigger_key == pause_combo["key"] and modifiers_match(pause_combo["mods"]):
            with _lock:
                _is_paused = not _is_paused
            state = "PAUSED" if _is_paused else "RESUMED"
            print(f"\n  [{state}]")
        elif trigger_key == stop_combo["key"] and modifiers_match(stop_combo["mods"]):
            with _lock:
                _should_stop = True
            print("\n  [STOP REQUESTED]")

    def on_release(key):
        _held_modifiers.discard(key)

    _listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    _listener.daemon = True
    _listener.start()

    pause_label = config.get("pause_key", "ctrl+f9").upper()
    stop_label  = config.get("stop_key",  "ctrl+f10").upper()
    print(f"Controls: [{pause_label}] pause/resume   [{stop_label}] emergency stop")


def stop_listener():
    """Stop the background keyboard listener. Call in a finally block."""
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None


def _resolve_key(name_or_keycode):
    """Convert a string key name OR a pynput KeyCode to a comparable pynput key."""
    if isinstance(name_or_keycode, keyboard.KeyCode):
        return name_or_keycode
    name = name_or_keycode.lower()
    special = {
        "space":  keyboard.Key.space,
        "escape": keyboard.Key.esc,
        "esc":    keyboard.Key.esc,
        "enter":  keyboard.Key.enter,
        "tab":    keyboard.Key.tab,
        "f1":     keyboard.Key.f1,
        "f2":     keyboard.Key.f2,
        "f3":     keyboard.Key.f3,
        "f4":     keyboard.Key.f4,
        "f5":     keyboard.Key.f5,
        "f6":     keyboard.Key.f6,
        "f7":     keyboard.Key.f7,
        "f8":     keyboard.Key.f8,
        "f9":     keyboard.Key.f9,
        "f10":    keyboard.Key.f10,
        "f11":    keyboard.Key.f11,
        "f12":    keyboard.Key.f12,
    }
    if name in special:
        return special[name]
    return keyboard.KeyCode.from_char(name)


def _parse_combo(combo_string):
    """
    Parse a key combo string like "ctrl+f9" or "ctrl+shift+f8" into
    {"mods": {"ctrl"}, "key": keyboard.Key.f9}.
    Also handles plain keys like "f9" with no modifiers.
    """
    parts = [p.strip().lower() for p in combo_string.split("+")]
    mod_names = {"ctrl", "shift", "alt"}
    mods = {p for p in parts if p in mod_names}
    keys = [p for p in parts if p not in mod_names]
    if not keys:
        raise ValueError(f"No trigger key found in combo: {combo_string!r}")
    return {"mods": mods, "key": _resolve_key(keys[0])}