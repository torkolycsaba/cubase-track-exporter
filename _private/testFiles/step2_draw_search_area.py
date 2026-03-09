"""
STEP 2 - Define the track list search area
-------------------------------------------
Builds on step 1. Now that we know WHERE the anchor is,
we use it to define a rectangle — the area where we will
later search for S buttons.

This script does ONE thing:
  - Finds the anchor (same as step 1)
  - Calculates the search rectangle below it
  - Draws that rectangle on a debug image so you can verify it looks right

Run with Cubase open and track list visible:
    python step2_draw_search_area.py
"""

import cv2
import numpy as np
import pyautogui
from pathlib import Path

# ── Load anchor template ───────────────────────────────────────────────────────

anchor_template = cv2.imread("templates/track_list_anchor.png")

# ── Take screenshot ────────────────────────────────────────────────────────────

screenshot = cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)

# ── Find the anchor ────────────────────────────────────────────────────────────

result = cv2.matchTemplate(screenshot, anchor_template, cv2.TM_CCOEFF_NORMED)
min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

if max_val < 0.80:
    print(f"Anchor not found confidently enough (got {max_val:.3f})")
    print("Make sure Cubase is open and the track list is visible")
    exit()

anchor_x = max_loc[0]
anchor_y = max_loc[1]
anchor_h, anchor_w = anchor_template.shape[:2]

print(f"Anchor found at x={anchor_x}, y={anchor_y} with confidence {max_val:.3f}")

# ── Define the search rectangle ────────────────────────────────────────────────
#
# The anchor sits in the header bar of the track list.
# Everything we care about (the S buttons) lives BELOW that header.
#
# HEADER_HEIGHT: how many pixels tall is the header row that contains
# the anchor? We skip this many pixels downward before starting our search.
# If the rectangle starts too high (cuts into the header), increase this.
# If it starts too low (misses the first track), decrease it.
HEADER_HEIGHT = 30

# WIDTH: how wide is the track list button area?
# We only need to cover from the left edge up to and including the S buttons.
# The track names to the right don't matter for button searching.
# If your S buttons are getting cut off on the right, increase this.
SEARCH_WIDTH = 260

# The top-left corner of our search area
search_x1 = anchor_x
search_y1 = anchor_y + anchor_h + HEADER_HEIGHT

# The bottom-right corner — we go all the way to the bottom of the screen
# because we don't know how many tracks there are yet
screen_height = screenshot.shape[0]
search_x2 = anchor_x + SEARCH_WIDTH
search_y2 = screen_height - 50  # leave a small margin at the very bottom

print(f"Search area: top-left=({search_x1}, {search_y1})  bottom-right=({search_x2}, {search_y2})")

# ── Draw both rectangles on the debug image ────────────────────────────────────

debug = screenshot.copy()

# Red box around the anchor itself
cv2.rectangle(debug, (anchor_x, anchor_y),
              (anchor_x + anchor_w, anchor_y + anchor_h), (0, 0, 255), 2)

# Green box showing the search area
cv2.rectangle(debug, (search_x1, search_y1),
              (search_x2, search_y2), (0, 255, 0), 2)

# Labels so it's clear which box is which
cv2.putText(debug, "ANCHOR", (anchor_x + 2, anchor_y - 4),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
cv2.putText(debug, "SEARCH AREA", (search_x1 + 2, search_y1 + 16),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

cv2.imwrite("debug_search_area.png", debug)
print("Saved debug_search_area.png")
print("Open it and check:")
print("  RED box  = anchor (the + and hamburger icon)")
print("  GREEN box = where we will search for S buttons")
print("")
print("The GREEN box should cover ALL your track rows and nothing below them.")
print("If it is off, adjust HEADER_HEIGHT or SEARCH_WIDTH at the top of this script.")
