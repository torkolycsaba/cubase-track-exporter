"""
STEP 3 - Find all Solo buttons, de-solo any that are active, classify all tracks
---------------------------------------------------------------------------------
The S button has three visual states:
  normal   = dark grey  → track is not selected for export
  selected = bright     → track is selected for export
  soloed   = red/orange → solo is currently active (overlays the true state)

"Soloed" is a sub-state — it hides whether the track is selected or normal.
To reveal the true state we click the soloed button to de-solo it,
then re-read the same position to see what it actually is underneath.

After this script runs:
  - No tracks will be soloed anymore (pre-flight cleanup done)
  - Every track will be correctly classified as selected or normal
  - We have a clean ordered list ready for the export loop

Run with Cubase open:
    python step3_find_solo_buttons.py
"""

import cv2
import numpy as np
import pyautogui
import time

# ── Tuning ─────────────────────────────────────────────────────────────────────

HEADER_HEIGHT    = 30    # pixels to skip below anchor before searching
SEARCH_WIDTH     = 260   # width of the search area
MATCH_THRESHOLD  = 0.85  # minimum confidence to count as a real match
CLICK_SETTLE_TIME = 0.4  # seconds to wait after clicking before re-reading
                          # increase this if Cubase is slow to update its UI

# ── Load templates ─────────────────────────────────────────────────────────────

anchor_template   = cv2.imread("templates/track_list_anchor.png")
template_normal   = cv2.imread("templates/solo_button_normal.png")
template_selected = cv2.imread("templates/solo_button_selected.png")
template_soloed   = cv2.imread("templates/solo_button_soloed.png")

# ── Helper: take a fresh screenshot ───────────────────────────────────────────

def take_screenshot():
    return cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)

# ── Helper: find the anchor and return the search rectangle coordinates ────────

def find_search_area(screenshot):
    result = cv2.matchTemplate(screenshot, anchor_template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val < 0.80:
        print(f"Anchor not found (confidence {max_val:.3f}). Is Cubase visible?")
        exit()

    anchor_x, anchor_y = max_loc
    anchor_h, anchor_w = anchor_template.shape[:2]

    search_x1 = anchor_x
    search_y1 = anchor_y + anchor_h + HEADER_HEIGHT
    search_x2 = anchor_x + SEARCH_WIDTH
    search_y2 = screenshot.shape[0] - 50

    return search_x1, search_y1, search_x2, search_y2

# ── Helper: find all matches of one template inside a region ───────────────────

def find_all_matches(region, template, threshold, label):
    th, tw = template.shape[:2]
    result = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED)

    ys, xs = np.where(result >= threshold)
    if len(xs) == 0:
        return []

    scores = result[ys, xs]
    order  = np.argsort(scores)[::-1]

    matches = []
    used    = set()

    for i in order:
        x, y  = int(xs[i]), int(ys[i])
        score = float(scores[i])

        too_close = any(
            abs(x - kx) < tw // 2 and abs(y - ky) < th // 2
            for kx, ky in used
        )
        if too_close:
            continue

        used.add((x, y))
        matches.append({
            "region_x":   x + tw // 2,
            "region_y":   y + th // 2,
            "state":      label,
            "confidence": score
        })

    return matches

# ── Helper: check what state a single button position is in ───────────────────
#
# After de-soloing we take a fresh screenshot and check a small area
# around the known button position to re-classify it.

def read_button_state(screen_x, screen_y, screenshot):
    """
    Given the screen coordinates of an S button centre,
    crop a small area around it and check which template matches best.
    Returns "selected", "normal", or "soloed".
    """
    # Crop a 40x40 area centred on the button
    pad = 20
    x1  = max(0, screen_x - pad)
    y1  = max(0, screen_y - pad)
    x2  = min(screenshot.shape[1], screen_x + pad)
    y2  = min(screenshot.shape[0], screen_y + pad)
    area = screenshot[y1:y2, x1:x2]

    best_state = "normal"
    best_score = 0.0

    for template, label in [
        (template_normal,   "normal"),
        (template_selected, "selected"),
        (template_soloed,   "soloed"),
    ]:
        th, tw = template.shape[:2]
        # Only try matching if the crop is big enough for the template
        if area.shape[0] < th or area.shape[1] < tw:
            continue

        result = cv2.matchTemplate(area, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, _ = cv2.minMaxLoc(result)

        if score > best_score:
            best_score = score
            best_state = label

    return best_state, best_score

# ── MAIN FLOW ──────────────────────────────────────────────────────────────────

print("Taking screenshot and scanning for S buttons...")
screenshot = take_screenshot()
search_x1, search_y1, search_x2, search_y2 = find_search_area(screenshot)
search_region = screenshot[search_y1:search_y2, search_x1:search_x2]

# Initial scan for all three states
hits_normal   = find_all_matches(search_region, template_normal,   MATCH_THRESHOLD, "normal")
hits_selected = find_all_matches(search_region, template_selected, MATCH_THRESHOLD, "selected")
hits_soloed   = find_all_matches(search_region, template_soloed,   MATCH_THRESHOLD, "soloed")

# Combine and convert to full screen coordinates
all_buttons = []
for hit in hits_normal + hits_selected + hits_soloed:
    all_buttons.append({
        "screen_x":   hit["region_x"] + search_x1,
        "screen_y":   hit["region_y"] + search_y1,
        "state":      hit["state"],
        "confidence": hit["confidence"]
    })

all_buttons.sort(key=lambda b: b["screen_y"])

# Report initial findings
soloed_buttons = [b for b in all_buttons if b["state"] == "soloed"]
print(f"Initial scan: {len(all_buttons)} total buttons found, "
      f"{len(soloed_buttons)} currently soloed")

# ── PRE-FLIGHT: de-solo any active solo buttons ────────────────────────────────

if soloed_buttons:
    print(f"\nPre-flight cleanup: clicking {len(soloed_buttons)} soloed button(s)...")

    for btn in soloed_buttons:
        print(f"  Clicking soloed button at ({btn['screen_x']}, {btn['screen_y']})...")
        pyautogui.click(btn["screen_x"], btn["screen_y"])

        # Wait for Cubase to update its UI
        time.sleep(CLICK_SETTLE_TIME)

        # Take a fresh screenshot and re-read just this button position
        fresh_screenshot = take_screenshot()
        new_state, new_confidence = read_button_state(
            btn["screen_x"], btn["screen_y"], fresh_screenshot
        )

        print(f"    Was: soloed  →  Now: {new_state} (confidence {new_confidence:.3f})")

        # Update the button record with its true state
        btn["state"]      = new_state
        btn["confidence"] = new_confidence

else:
    print("No soloed buttons found — pre-flight cleanup not needed.")

# ── Final summary ──────────────────────────────────────────────────────────────

queued_export = [b for b in all_buttons if b["state"] == "selected"]

print(f"\nAll S buttons after cleanup (top to bottom):\n")
for i, btn in enumerate(all_buttons):
    print(f"  Track {i+1:2d}:  ({btn['screen_x']:4d}, {btn['screen_y']:4d})  "
          f"state={btn['state']:10s}  confidence={btn['confidence']:.3f}")

print(f"\nSummary:")
print(f"  {len(queued_export)} track(s) selected for export")
print(f"  {len(all_buttons)} total track(s) found")
print(f"  0 tracks soloed (cleanup complete)")

# ── Debug image ────────────────────────────────────────────────────────────────

# Take one final screenshot to draw on (reflects the clean state)
final_screenshot = take_screenshot()
debug = final_screenshot.copy()

cv2.rectangle(debug, (search_x1, search_y1), (search_x2, search_y2), (0, 255, 0), 1)

for i, btn in enumerate(all_buttons):
    cx, cy = btn["screen_x"], btn["screen_y"]
    color  = (255, 180, 0) if btn["state"] == "selected" else (140, 140, 140)
    cv2.circle(debug, (cx, cy), 10, color, 2)
    cv2.putText(debug, f"T{i+1}", (cx + 12, cy + 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

cv2.imwrite("debug_solo_buttons.png", debug)
print(f"\nSaved debug_solo_buttons.png")
print(f"  BLUE circles = selected for export")
print(f"  GREY circles = normal (not selected)")