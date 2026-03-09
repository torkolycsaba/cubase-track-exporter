"""
STEP 4 - Export loop
--------------------
For each track in the export queue:
  1. Scroll until a selected S button is visible that we haven't done yet
  2. Click it to solo that track
  3. Open Export Audio Mixdown dialog via hotkey
  4. Confirm dialog opened by finding the Export Audio button
  5. Type the track name into the Name field
  6. Click Export Audio
  7. Wait for export to finish by watching for the progress window to
     appear and then disappear
  8. De-solo the track

HOW SKIP TRACKING WORKS:
  After export + de-solo the track is still "selected" visually.
  We keep a list of track names we've already exported and skip any
  button whose track name we've already processed.
  Since we know the order from export_queue, we skip the first N buttons
  where N = number already exported.

BEFORE RUNNING:
  - Open your project in Cubase
  - Manually open Export Audio Mixdown once, set your export folder,
    close it — Cubase remembers the path
  - Run step3 first to confirm your export_queue is correct
  - Run this script

Run:
    python step4_export.py
"""

import cv2
import numpy as np
import pyautogui
import time
import json

# ── Load config ────────────────────────────────────────────────────────────────

with open("config.json", "r") as f:
    config = json.load(f)

EXPORT_HOTKEY = config["export_hotkey"]  # list e.g. ["ctrl", "shift", "o"]

# ── Settings ───────────────────────────────────────────────────────────────────

SCROLL_AMOUNT        = 15
SCROLL_SETTLE        = 0.3
SCROLL_TO_TOP        = 40
SOLO_SETTLE          = 0.8    # wait after clicking solo before opening dialog
DIALOG_OPEN_WAIT     = 1.5    # wait after hotkey for dialog to appear
EXPORT_WAIT_POLL     = 0.3    # how often to poll during export wait
EXPORT_WAIT_MAX      = 120    # max seconds to wait per export
PROGRESS_APPEAR_WAIT = 3.0    # max seconds to wait for progress window to appear
DIALOG_THRESHOLD     = 0.80
MATCH_THRESHOLD      = 0.85
CLICK_SETTLE         = 0.3

NAME_FIELD_OFFSET_Y  = -498   # pixels above Export Audio button to Name field
NAME_FIELD_OFFSET_X  = -100

# ── Load templates ─────────────────────────────────────────────────────────────

anchor_template      = cv2.imread("templates/track_list_anchor.png")
template_selected    = cv2.imread("templates/solo_button_selected.png")
template_soloed      = cv2.imread("templates/solo_button_soloed.png")
export_btn_template  = cv2.imread("templates/export_audio_button.png")
# Optional: crop the progress window Cancel button and save as
# templates/export_cancel_button.png — enables bulletproof export detection
# If the file doesn't exist we fall back to Export Audio button disappearing
import os
progress_template = None
if os.path.exists("templates/export_abort_button.png"):
    progress_template = cv2.imread("templates/export_abort_button.png")
    print("Abort button template loaded — using progress window for export detection.")
else:
    print("No abort button template found — using Export Audio button disappearance as fallback.")

# ── Helpers ────────────────────────────────────────────────────────────────────

def take_screenshot():
    return cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)

def press_export_hotkey():
    for key in EXPORT_HOTKEY:
        pyautogui.keyDown(key)
    time.sleep(0.05)
    for key in reversed(EXPORT_HOTKEY):
        pyautogui.keyUp(key)

def find_search_area(screenshot):
    result = cv2.matchTemplate(screenshot, anchor_template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val < 0.80:
        print(f"Anchor not found ({max_val:.3f}). Is Cubase visible?")
        exit()
    anchor_x, anchor_y = max_loc
    anchor_h, anchor_w = anchor_template.shape[:2]
    return (anchor_x,
            anchor_y + anchor_h + 30,
            anchor_x + 260,
            screenshot.shape[0] - 50)

def find_template_on_screen(template, threshold):
    """Find a template anywhere on screen. Returns (cx, cy, conf) or None."""
    screenshot = take_screenshot()
    result     = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val < threshold:
        return None
    tw, th = template.shape[1], template.shape[0]
    return (max_loc[0] + tw // 2, max_loc[1] + th // 2, max_val)

def find_next_selected_button(search_x1, search_y1, search_x2, search_y2,
                               done_y_positions, scroll_offset_px,
                               skip_radius=15):
    """
    Find the topmost selected S button that we have NOT already exported.

    done_y_positions:  list of screen_y values recorded when the view was
                       at the TOP (before any scrolling in this iteration).
    scroll_offset_px:  how many pixels the view has shifted downward from
                       the top position (scroll_steps * pixel_per_scroll).
                       We subtract this from each done_y before comparing,
                       so the skip check stays accurate as we scroll down.

    Returns (screen_x, screen_y) or None if nothing found in current view.
    """
    screenshot    = take_screenshot()
    search_region = screenshot[search_y1:search_y2, search_x1:search_x2]
    result        = cv2.matchTemplate(search_region, template_selected,
                                      cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(result >= MATCH_THRESHOLD)
    if len(xs) == 0:
        return None

    scores = result[ys, xs]
    order  = np.argsort(scores)[::-1]
    unique = []
    used   = set()
    for i in order:
        x, y = int(xs[i]), int(ys[i])
        if not any(abs(x-kx) < 10 and abs(y-ky) < 10 for kx, ky in used):
            used.add((x, y))
            unique.append((x, y))

    unique.sort(key=lambda p: p[1])  # top to bottom

    tw = template_selected.shape[1]
    th = template_selected.shape[0]

    for x, y in unique:
        screen_y = y + th // 2 + search_y1
        # Adjust each done Y for how far we've scrolled down.
        # If we scrolled 60px down, a button originally at Y=266
        # is now visible at Y=206 — so we compare against 206.
        already_done = any(
            abs(screen_y - (done_y - scroll_offset_px)) < skip_radius
            for done_y in done_y_positions
        )
        if not already_done:
            return (x + tw // 2 + search_x1, screen_y)

    return None

def find_soloed_button(search_x1, search_y1, search_x2, search_y2):
    screenshot    = take_screenshot()
    search_region = screenshot[search_y1:search_y2, search_x1:search_x2]
    result        = cv2.matchTemplate(search_region, template_soloed,
                                      cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val < MATCH_THRESHOLD:
        return None
    tw, th = template_soloed.shape[1], template_soloed.shape[0]
    return (max_loc[0] + tw // 2 + search_x1,
            max_loc[1] + th // 2 + search_y1)

def wait_for_export_to_finish():
    """
    Waits for the Cubase export to complete.

    The Cubase export flow after clicking Export Audio:
      1. Main dialog closes immediately
      2. ~1 second pause
      3. "Perform Audio Export" progress window fades in slowly
      4. Abort button becomes visible as it fades in
      5. Window disappears when export is done

    We wait for the Abort button to APPEAR first (handles the fade-in delay),
    then wait for it to DISAPPEAR (export done).
    Falls back to Export Audio button disappearance if no abort template.
    """
    if progress_template is not None:
        # Phase A: wait for Abort button to appear (the window fades in)
        print(f"  Waiting for progress window to appear...")
        appeared = False
        waited   = 0
        while waited < PROGRESS_APPEAR_WAIT:
            time.sleep(EXPORT_WAIT_POLL)
            waited += EXPORT_WAIT_POLL
            if find_template_on_screen(progress_template, DIALOG_THRESHOLD):
                appeared = True
                print(f"  Progress window visible ({waited:.1f}s)")
                break

        if not appeared:
            print(f"  Progress window never appeared — may have been very fast.")

        # Phase B: wait for Abort button to disappear (export done)
        print(f"  Waiting for export to complete...")
        waited = 0
        while waited < EXPORT_WAIT_MAX:
            time.sleep(EXPORT_WAIT_POLL)
            waited += EXPORT_WAIT_POLL
            if find_template_on_screen(progress_template, DIALOG_THRESHOLD) is None:
                print(f"  Export complete ({waited:.1f}s)")
                return
        print(f"  WARNING: Export timed out after {EXPORT_WAIT_MAX}s")

    else:
        # Fallback: wait for Export Audio button to disappear
        print(f"  Waiting for export dialog to close...")
        waited = 0
        while waited < EXPORT_WAIT_MAX:
            time.sleep(EXPORT_WAIT_POLL)
            waited += EXPORT_WAIT_POLL
            if find_template_on_screen(export_btn_template, DIALOG_THRESHOLD) is None:
                time.sleep(1.5)  # buffer for Cubase to finish writing the file
                print(f"  Export complete ({waited:.1f}s)")
                return
        print(f"  WARNING: Export timed out after {EXPORT_WAIT_MAX}s")

# ── Export queue ───────────────────────────────────────────────────────────────
# Replace with your actual queue from step 3

export_queue = [
    "Guitar Left",
    "Guitar Right",
    "guitarrandom_right",
    "guitarleft",
    "mockBass",
]

print(f"Export queue: {len(export_queue)} tracks")
for name in export_queue:
    print(f"  → {name}")

# ── Setup ──────────────────────────────────────────────────────────────────────

print("\nFinding track list...")
screenshot = take_screenshot()
search_x1, search_y1, search_x2, search_y2 = find_search_area(screenshot)
center_x   = (search_x1 + search_x2) // 2
center_y   = search_y1 + (search_y2 - search_y1) // 5

print(f"Search area: ({search_x1},{search_y1}) to ({search_x2},{search_y2})")

pyautogui.moveTo(center_x, center_y)
for _ in range(SCROLL_TO_TOP):
    pyautogui.scroll(SCROLL_AMOUNT)
time.sleep(0.5)

# ── Calibrate scroll offset ───────────────────────────────────────────────────
#
# Measure how many pixels one SCROLL_AMOUNT scroll step moves the content.
# We use this to adjust done_y_positions as we scroll down during searching.

print("Calibrating scroll offset...")
screenshot    = take_screenshot()
search_region = screenshot[search_y1:search_y2, search_x1:search_x2]
result        = cv2.matchTemplate(search_region, cv2.imread("templates/solo_button_selected.png"),
                                  cv2.TM_CCOEFF_NORMED)
ys, xs = np.where(result >= MATCH_THRESHOLD)
top_y_before = int(ys[np.argmin(xs)]) if len(ys) > 0 else 0  # topmost match Y in region

pyautogui.scroll(-SCROLL_AMOUNT)
time.sleep(SCROLL_SETTLE)

screenshot    = take_screenshot()
search_region = screenshot[search_y1:search_y2, search_x1:search_x2]
result        = cv2.matchTemplate(search_region, cv2.imread("templates/solo_button_selected.png"),
                                  cv2.TM_CCOEFF_NORMED)
ys2, xs2 = np.where(result >= MATCH_THRESHOLD)
top_y_after = int(ys2[np.argmin(xs2)]) if len(ys2) > 0 else 0

pixel_per_scroll = max(top_y_before - top_y_after, 10)  # how much one step moves content
print(f"Calibrated: {pixel_per_scroll}px per scroll step")

# Scroll back to top
pyautogui.moveTo(center_x, center_y)
for _ in range(SCROLL_TO_TOP):
    pyautogui.scroll(SCROLL_AMOUNT)
time.sleep(0.5)

# ── Export loop ────────────────────────────────────────────────────────────────
#
# done_y_positions: Y values recorded at the top scroll position.
# scroll_steps: how many steps down we've scrolled in the current search.
# We pass scroll_steps * pixel_per_scroll into find_next_selected_button
# so it can adjust done_y values to match current scroll position.

done_y_positions = []   # grows by one each iteration

for track_num, name in enumerate(export_queue, 1):
    print(f"\n── Track {track_num}/{len(export_queue)}: {name} ──────────────────")

    # ── Step 1: Scroll to top, then find next undone selected button ──────────

    print(f"  Looking for next selected button (skipping {len(done_y_positions)} done)...")
    pyautogui.moveTo(center_x, center_y)
    for _ in range(SCROLL_TO_TOP):
        pyautogui.scroll(SCROLL_AMOUNT)
    time.sleep(0.4)

    solo_pos  = None
    scroll_steps = 0   # reset for each track search

    while solo_pos is None:
        scroll_offset_px = scroll_steps * pixel_per_scroll
        solo_pos = find_next_selected_button(search_x1, search_y1,
                                             search_x2, search_y2,
                                             done_y_positions,
                                             scroll_offset_px)
        if solo_pos is None:
            pyautogui.scroll(-SCROLL_AMOUNT)
            time.sleep(SCROLL_SETTLE)
            scroll_steps += 1

    solo_btn_x, solo_btn_y = solo_pos
    # Record the Y as it would appear at the top (add back the scroll offset)
    solo_btn_y_at_top = solo_btn_y + scroll_steps * pixel_per_scroll
    print(f"  Found at ({solo_btn_x}, {solo_btn_y})  [top-Y={solo_btn_y_at_top}]")

    # ── Step 2: Click solo ────────────────────────────────────────────────────

    print(f"  Clicking solo button...")
    pyautogui.click(solo_btn_x, solo_btn_y)
    time.sleep(SOLO_SETTLE)

    # Verify solo activated
    screenshot    = take_screenshot()
    search_region = screenshot[search_y1:search_y2, search_x1:search_x2]
    result        = cv2.matchTemplate(search_region, template_soloed,
                                      cv2.TM_CCOEFF_NORMED)
    _, solo_conf, _, _ = cv2.minMaxLoc(result)
    if solo_conf < 0.80:
        print(f"  WARNING: Solo may not have activated (conf={solo_conf:.3f}). Retrying...")
        pyautogui.click(solo_btn_x, solo_btn_y)
        time.sleep(SOLO_SETTLE)

    # ── Step 3: Open export dialog ────────────────────────────────────────────

    print(f"  Opening export dialog...")
    press_export_hotkey()
    time.sleep(DIALOG_OPEN_WAIT)

    # ── Step 4: Confirm dialog opened ────────────────────────────────────────

    found = find_template_on_screen(export_btn_template, DIALOG_THRESHOLD)
    if not found:
        print(f"  ERROR: Dialog not found. De-soloing and skipping.")
        pos = find_soloed_button(search_x1, search_y1, search_x2, search_y2)
        pyautogui.click(pos[0] if pos else solo_btn_x,
                        pos[1] if pos else solo_btn_y)
        time.sleep(CLICK_SETTLE)
        continue

    btn_cx, btn_cy, conf = found
    print(f"  Dialog open (button at {btn_cx},{btn_cy}, conf={conf:.3f})")

    # ── Step 5: Type track name ───────────────────────────────────────────────

    name_x = btn_cx + NAME_FIELD_OFFSET_X
    name_y = btn_cy + NAME_FIELD_OFFSET_Y
    print(f"  Setting name: {name}")
    pyautogui.click(name_x, name_y)
    time.sleep(CLICK_SETTLE)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.typewrite(name, interval=0.05)
    time.sleep(CLICK_SETTLE)

    # ── Step 6: Click Export Audio ────────────────────────────────────────────

    print(f"  Exporting...")
    pyautogui.click(btn_cx, btn_cy)

    # ── Step 7: Wait for export to finish ─────────────────────────────────────

    wait_for_export_to_finish()

    # ── Step 8: De-solo ───────────────────────────────────────────────────────

    print(f"  De-soloing...")
    pos = find_soloed_button(search_x1, search_y1, search_x2, search_y2)
    if pos:
        pyautogui.click(pos[0], pos[1])
        print(f"  De-soloed at {pos}")
    else:
        pyautogui.click(solo_btn_x, solo_btn_y)
        print(f"  De-soloed (fallback)")
    time.sleep(CLICK_SETTLE)

    # Record the top-normalised Y so the offset adjustment works correctly
    # in future iterations regardless of how far we had scrolled to find it
    done_y_positions.append(solo_btn_y_at_top)
    print(f"  Marked top-Y={solo_btn_y_at_top} as done. Done list: {done_y_positions}")

# ── Done ───────────────────────────────────────────────────────────────────────

print(f"\n{'='*50}")
print(f"All done! {len(export_queue)} tracks exported.")
print(f"{'='*50}")