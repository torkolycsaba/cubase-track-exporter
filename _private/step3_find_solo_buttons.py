"""
STEP 3 - Scroll through all tracks, de-solo, then classify cleanly
-------------------------------------------------------------------
Two completely separate phases:

  PHASE 1 - De-solo sweep:
    Scrolls from top to bottom.
    Clicks any soloed S button it finds.
    Does NOT try to record track states yet.
    Stops when pixel diff says we hit the bottom.

  PHASE 2 - Clean scan:
    Scrolls back to top.
    Takes ONE stable screenshot with nothing soloed and nothing scrolling.
    Scans all visible buttons and records their true states.
    Scrolls down only if needed to find tracks not visible on screen.

Keeping these phases separate means state detection always happens on a
clean, stable image — no partial tracks, no mid-scroll artifacts.

Run with Cubase open:
    python step3_find_solo_buttons.py
"""

import cv2
import numpy as np
import pyautogui
import time
from cpr_parser import get_audio_track_names

# ── Settings ───────────────────────────────────────────────────────────────────

# Path to your Cubase project file — update this to match your machine
CPR_PATH = r"E:/Cubase 14 Projects/Untitled-03/balatonmixed.cpr"

HEADER_HEIGHT      = 30
SEARCH_WIDTH       = 260
MATCH_THRESHOLD    = 0.85   # threshold for normal and selected templates
SOLOED_THRESHOLD   = 0.90   # higher threshold for soloed — reduces false positives
SCROLL_AMOUNT      = 15     # wheel units per scroll step
SCROLL_SETTLE      = 0.3    # seconds to wait after each scroll
SCROLL_TO_TOP      = 40     # scroll-up bursts to reach the top
CLICK_SETTLE       = 0.5    # seconds after clicking a solo button
STOP_THRESHOLD     = 3.0    # pixel diff below this = hit the bottom
MIN_TRACK_GAP      = 15     # px gap needed to count a button as a new track

# ── Load track names from project file ────────────────────────────────────────

track_names  = get_audio_track_names(CPR_PATH)
TOTAL_TRACKS = len(track_names)
print(f"Loaded {TOTAL_TRACKS} track names from project file:")
for i, name in enumerate(track_names):
    print(f"  {i+1}. {name}")
print()

# ── Load templates ─────────────────────────────────────────────────────────────

anchor_template   = cv2.imread("templates/track_list_anchor.png")
template_normal   = cv2.imread("templates/solo_button_normal.png")
template_selected = cv2.imread("templates/solo_button_selected.png")
template_soloed   = cv2.imread("templates/solo_button_soloed.png")

# ── Helpers ────────────────────────────────────────────────────────────────────

def take_screenshot():
    return cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)

def find_search_area(screenshot):
    result = cv2.matchTemplate(screenshot, anchor_template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val < 0.80:
        print(f"Anchor not found ({max_val:.3f}). Is Cubase visible?")
        exit()
    anchor_x, anchor_y = max_loc
    anchor_h, anchor_w = anchor_template.shape[:2]
    return (anchor_x,
            anchor_y + anchor_h + HEADER_HEIGHT,
            anchor_x + SEARCH_WIDTH,
            screenshot.shape[0] - 50)

def find_all_matches(region, template, threshold, label):
    th, tw = template.shape[:2]
    result = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(result >= threshold)
    if len(xs) == 0:
        return []
    scores = result[ys, xs]
    order  = np.argsort(scores)[::-1]
    matches = []
    used = set()
    for i in order:
        x, y  = int(xs[i]), int(ys[i])
        score = float(scores[i])
        if any(abs(x-kx) < tw//2 and abs(y-ky) < th//2 for kx, ky in used):
            continue
        used.add((x, y))
        matches.append({"region_x": x+tw//2, "region_y": y+th//2,
                        "state": label, "confidence": score})
    return matches

def find_soloed_buttons(region, offset_x, offset_y):
    """Only look for soloed buttons — uses the higher SOLOED_THRESHOLD."""
    hits = find_all_matches(region, template_soloed, SOLOED_THRESHOLD, "soloed")
    return [{"screen_x": h["region_x"]+offset_x,
             "screen_y": h["region_y"]+offset_y,
             "confidence": h["confidence"]} for h in hits]

def scan_all_buttons(region, offset_x, offset_y):
    """Scan for normal and selected only — used in Phase 2 clean scan."""
    all_hits = (
        find_all_matches(region, template_normal,   MATCH_THRESHOLD, "normal")   +
        find_all_matches(region, template_selected, MATCH_THRESHOLD, "selected")
    )
    buttons = [{"screen_x": h["region_x"]+offset_x,
                "screen_y": h["region_y"]+offset_y,
                "state":    h["state"],
                "confidence": h["confidence"]} for h in all_hits]
    buttons.sort(key=lambda b: b["screen_y"])
    return buttons

# ── Setup ──────────────────────────────────────────────────────────────────────

print("Finding track list...")
screenshot = take_screenshot()
search_x1, search_y1, search_x2, search_y2 = find_search_area(screenshot)
center_x = (search_x1 + search_x2) // 2
center_y = (search_y1 + search_y2) // 2
print(f"Search area: ({search_x1},{search_y1}) to ({search_x2},{search_y2})")

pyautogui.moveTo(center_x, center_y)
time.sleep(0.2)

# ── Scroll to top ──────────────────────────────────────────────────────────────

print("Scrolling to top...")
for _ in range(SCROLL_TO_TOP):
    pyautogui.scroll(SCROLL_AMOUNT)
time.sleep(0.5)

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1: De-solo sweep — scroll top to bottom, click any soloed button
# ══════════════════════════════════════════════════════════════════════════════

print("\n── Phase 1: De-solo sweep ──────────────────────────────────────────")

prev_region  = None
scroll_count = 0

while True:
    screenshot    = take_screenshot()
    search_region = screenshot[search_y1:search_y2, search_x1:search_x2]

    # Find and click any soloed buttons in the current view
    soloed = find_soloed_buttons(search_region, search_x1, search_y1)
    for btn in soloed:
        print(f"  Soloed at ({btn['screen_x']}, {btn['screen_y']}) "
              f"conf={btn['confidence']:.3f} — clicking...")
        pyautogui.click(btn["screen_x"], btn["screen_y"])
        time.sleep(CLICK_SETTLE)

        # Verify it actually de-soloed
        fresh         = take_screenshot()
        fresh_region  = fresh[search_y1:search_y2, search_x1:search_x2]
        still_soloed  = find_soloed_buttons(fresh_region, search_x1, search_y1)
        still_at_pos  = [b for b in still_soloed
                         if abs(b["screen_y"] - btn["screen_y"]) < 10]
        if still_at_pos:
            print(f"    Still soloed after click — clicking again...")
            pyautogui.click(btn["screen_x"], btn["screen_y"])
            time.sleep(CLICK_SETTLE)
        else:
            print(f"    De-soloed successfully.")

    # Check stop condition AFTER de-soloing so the pixel diff reflects
    # actual track content movement, not button colour changes
    if prev_region is not None:
        pixel_diff = cv2.absdiff(prev_region, search_region).mean()
        if pixel_diff < STOP_THRESHOLD:
            print(f"  [scroll {scroll_count}] diff={pixel_diff:.2f} → bottom reached.")
            break
        print(f"  [scroll {scroll_count}] diff={pixel_diff:.2f}")

    prev_region = search_region.copy()
    pyautogui.scroll(-SCROLL_AMOUNT)
    time.sleep(SCROLL_SETTLE)
    scroll_count += 1

print("Phase 1 complete — no tracks should be soloed now.")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2: Clean scan — scroll back to top and read all states from scratch
# ══════════════════════════════════════════════════════════════════════════════

print("\n── Phase 2: Clean scan ─────────────────────────────────────────────")

print("Scrolling back to top...")
for _ in range(SCROLL_TO_TOP):
    pyautogui.scroll(SCROLL_AMOUNT)
time.sleep(0.5)

# Calibration scroll to measure pixel movement per scroll step
screenshot     = take_screenshot()
search_region  = screenshot[search_y1:search_y2, search_x1:search_x2]
initial_btns   = scan_all_buttons(search_region, search_x1, search_y1)
top_y_before   = initial_btns[0]["screen_y"] if initial_btns else search_y1

pyautogui.scroll(-SCROLL_AMOUNT)
time.sleep(SCROLL_SETTLE)
screenshot    = take_screenshot()
search_region = screenshot[search_y1:search_y2, search_x1:search_x2]
after_btns    = scan_all_buttons(search_region, search_x1, search_y1)

if after_btns:
    shift = top_y_before - after_btns[0]["screen_y"]
    pixel_per_scroll = shift if shift > 0 else 30
else:
    pixel_per_scroll = 30

print(f"Calibrated: {pixel_per_scroll}px per scroll step")

# Scroll back to top again for the actual clean scan
for _ in range(SCROLL_TO_TOP):
    pyautogui.scroll(SCROLL_AMOUNT)
time.sleep(0.5)

# Now do the clean scan collecting all track states
all_tracks   = []
prev_region  = None
scroll_count = 0

while len(all_tracks) < TOTAL_TRACKS:
    screenshot    = take_screenshot()
    search_region = screenshot[search_y1:search_y2, search_x1:search_x2]
    visible       = scan_all_buttons(search_region, search_x1, search_y1)

    if not all_tracks:
        # First scan — take everything
        all_tracks = list(visible)
        for i, b in enumerate(all_tracks):
            print(f"  Track {i+1:2d}: ({b['screen_x']}, {b['screen_y']})  "
                  f"state={b['state']}")
    else:
        # Subsequent scans — only add buttons that appear below last known track
        last_y = all_tracks[-1]["screen_y"] - pixel_per_scroll
        new_here = [b for b in visible
                    if b["screen_y"] > last_y + MIN_TRACK_GAP]
        for t in new_here:
            if len(all_tracks) < TOTAL_TRACKS:
                all_tracks.append(t)
                print(f"  Track {len(all_tracks):2d}: ({t['screen_x']}, {t['screen_y']})  "
                      f"state={t['state']}  [scroll {scroll_count}]")

    if len(all_tracks) >= TOTAL_TRACKS:
        break

    if prev_region is not None:
        pixel_diff = cv2.absdiff(prev_region, search_region).mean()
        if pixel_diff < STOP_THRESHOLD:
            print(f"  Bottom reached. Found {len(all_tracks)}/{TOTAL_TRACKS}.")
            break

    prev_region = search_region.copy()
    pyautogui.scroll(-SCROLL_AMOUNT)
    time.sleep(SCROLL_SETTLE)
    scroll_count += 1

# ── Final report ───────────────────────────────────────────────────────────────

queued = [b for b in all_tracks if b["state"] == "selected"]

print(f"\n{'='*50}")
print(f"Final track list:")
print(f"{'='*50}")
for i, btn in enumerate(all_tracks):
    print(f"  Track {i+1:2d}: ({btn['screen_x']:4d}, {btn['screen_y']:4d})  "
          f"state={btn['state']:10s}  confidence={btn['confidence']:.3f}")
print(f"\n  {len(queued)} track(s) selected for export")
print(f"  {len(all_tracks)} total track(s) found")
print(f"  0 tracks soloed (Phase 1 complete)")

# ── Pair track names with scan results ────────────────────────────────────────
#
# both lists are in top-to-bottom order so we can zip them directly

print(f"\n{'='*50}")
print(f"Tracks paired with names:")
print(f"{'='*50}")

export_queue = []

for i, (btn, name) in enumerate(zip(all_tracks, track_names)):
    status = "→ EXPORT" if btn["state"] == "selected" else "   skip"
    print(f"  {i+1:2d}. {name:30s}  {status}")
    if btn["state"] == "selected":
        export_queue.append({"name": name, "screen_x": btn["screen_x"],
                             "screen_y": btn["screen_y"]})

print(f"\nExport queue ({len(export_queue)} tracks):")
for item in export_queue:
    print(f"  → {item['name']}")