"""
STEP 1 - Find the track list anchor on screen
----------------------------------------------
This script does ONE thing:
  - Takes a screenshot
  - Searches for the + and hamburger icon (top-left of Cubase's track list)
  - Prints where it found it
  - Saves a debug image so you can visually verify it's correct

Run this with Cubase open and the track list visible:
    python step1_find_anchor.py
"""

import cv2
import numpy as np
import pyautogui
from pathlib import Path

# Load the anchor template image
anchor_template = cv2.imread("templates/track_list_anchor.png")

# Take a screenshot of your current screen
screenshot_rgb = pyautogui.screenshot()

# pyautogui gives us RGB, OpenCV needs BGR - so we convert
screenshot = cv2.cvtColor(np.array(screenshot_rgb), cv2.COLOR_RGB2BGR)

# Ask OpenCV: "where in the screenshot does the anchor template appear?"
# TM_CCOEFF_NORMED gives us a score from -1.0 to 1.0 for every pixel position
# 1.0 = perfect match, we set 0.80 as our minimum "yes I found it" threshold
result = cv2.matchTemplate(screenshot, anchor_template, cv2.TM_CCOEFF_NORMED)

# Find the single best match location
min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

print(f"Best match confidence: {max_val:.3f}")
print(f"Found anchor at pixel position: x={max_loc[0]}, y={max_loc[1]}")

if max_val < 0.80:
    print("WARNING: Confidence is low - anchor may not have been found correctly")
    print("Make sure Cubase is open and the track list panel is visible")
else:
    print("Anchor found successfully!")

    # The anchor top-left corner is at max_loc
    anchor_x = max_loc[0]
    anchor_y = max_loc[1]

    # Draw a red circle on the screenshot at that position so you can see it
    anchor_h, anchor_w = anchor_template.shape[:2]
    cv2.rectangle(
        screenshot,
        (anchor_x, anchor_y),
        (anchor_x + anchor_w, anchor_y + anchor_h),
        (0, 0, 255),  # red box
        2
    )

    # Save the debug image - open this file to verify visually
    cv2.imwrite("debug_anchor_found.png", screenshot)
    print("Saved debug_anchor_found.png - open it to visually check the red box position")
