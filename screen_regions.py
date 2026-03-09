"""
screen_regions.py
-----------------
Locates Cubase UI elements on screen using OpenCV template matching.
No hardcoded pixel coordinates — everything is found dynamically at runtime
from the actual screen content.

WHAT THIS FILE IS RESPONSIBLE FOR:
  - Taking a screenshot of the current screen
  - Finding all Solo (S) buttons in the Cubase track list
  - Determining whether each track row is "selected" (user pre-selected for export)
  - Returning structured results that cubase_controller.py can act on

HOW TEMPLATE MATCHING WORKS (plain language):
  We have a small reference image of what the S button looks like (solo_button_normal.png).
  OpenCV slides this reference image across the full screenshot pixel by pixel,
  computing a "similarity score" at each position. Where the score crosses our
  confidence threshold, we've found a match. Multiple matches = multiple S buttons.
  Sorting those matches by Y coordinate gives us top-to-bottom track order.

TEMPLATES NEEDED (place in the same folder as this file):
  - solo_button_normal.png   : The S button in its inactive/normal state (provided)
  - track_selected.png       : A crop of a SELECTED track row background
                               ** YOU NEED TO PROVIDE THIS **
                               Take a screenshot with one track selected (clicked),
                               crop a ~60x12 pixel strip of the row background
                               (NOT the buttons, just the grey area to the right),
                               and save it as track_selected.png next to this file.

DEPENDENCIES:
  pip install opencv-python pyautogui numpy
"""

import cv2
import numpy as np
import pyautogui
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ── Configuration ─────────────────────────────────────────────────────────────

# How confident OpenCV needs to be before it says "yes, I found the button".
# 0.85 = 85% match. Too high = misses buttons. Too low = false positives.
# 0.80–0.88 is a good range for Cubase's UI.
SOLO_MATCH_THRESHOLD   = 0.82

# Threshold for detecting a selected track row background.
SELECTED_MATCH_THRESHOLD = 0.75

# How many pixels to the LEFT of an S button's centre to sample the
# row background for selection detection.
# The background strip we want is in the track name area, which in
# Cubase's default layout is ~80-120px to the right of the S button.
# Adjust this if your Cubase panel layout is wider or narrower.
SELECTION_SAMPLE_OFFSET_X = 80   # px to the RIGHT of S button centre
SELECTION_SAMPLE_STRIP_W  = 60   # width of the background strip to sample
SELECTION_SAMPLE_STRIP_H  = 12   # height of the strip (small = faster matching)

# Where to look for templates (same folder as this script by default)
TEMPLATE_DIR = Path(__file__).parent / "templates"


# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class SoloButton:
    """Represents one found Solo button on screen."""
    x: int                  # centre x of the button on screen
    y: int                  # centre y of the button on screen
    track_index: int        # 0-based index, top-to-bottom visual order
    is_selected: bool       # True if this track's row is selected for export
    confidence: float       # OpenCV match confidence (0.0 – 1.0)


@dataclass
class TrackListScan:
    """The full result of scanning the screen for track controls."""
    all_buttons: list[SoloButton]       # Every S button found, in Y order
    selected_buttons: list[SoloButton]  # Only the ones marked for export
    screenshot_shape: tuple             # (height, width) of the screenshot taken


# ── Template Loading ──────────────────────────────────────────────────────────

def _load_template(filename: str) -> Optional[np.ndarray]:
    """
    Load a template image from the templates folder.
    Returns None if the file doesn't exist (instead of crashing).
    """
    path = TEMPLATE_DIR / filename
    if not path.exists():
        return None
    template = cv2.imread(str(path))
    if template is None:
        raise ValueError(f"Could not read template image: {path}")
    return template


# ── Core Functions ────────────────────────────────────────────────────────────

def take_screenshot() -> np.ndarray:
    """
    Capture the current screen and return it as an OpenCV (BGR) numpy array.
    This is the 'live frame' that all template searches run against.
    """
    screenshot = pyautogui.screenshot()
    # pyautogui returns RGB; OpenCV works in BGR — convert
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)


def find_solo_buttons(
    screenshot: Optional[np.ndarray] = None,
    check_selection: bool = True,
) -> TrackListScan:
    """
    Scan the screen for all Solo (S) buttons in the Cubase track list.

    Parameters
    ----------
    screenshot : np.ndarray, optional
        Pre-taken screenshot (BGR). If None, a fresh screenshot is taken.
        Pass one in if you're calling this multiple times in quick succession
        to avoid taking redundant screenshots.

    check_selection : bool
        If True, also check each found button's row for the "selected" state.
        Set to False if you want to process ALL tracks regardless of selection.

    Returns
    -------
    TrackListScan
        Contains all found buttons and the filtered selected-only list.

    Raises
    ------
    FileNotFoundError
        If solo_button_normal.png template is missing.
    RuntimeError
        If no Solo buttons are found at all (Cubase may not be visible).
    """
    # ── Load the S button template ──
    solo_template = _load_template("solo_button_normal.png")
    if solo_template is None:
        raise FileNotFoundError(
            "Template not found: templates/solo_button_normal.png\n"
            "Make sure the templates folder is next to this script."
        )

    # ── Load selection template (optional) ──
    selected_template = None
    if check_selection:
        selected_template = _load_template("track_selected.png")
        if selected_template is None:
            print(
                "[screen_regions] WARNING: templates/track_selected.png not found.\n"
                "  Selection detection is disabled — all tracks will be treated as selected.\n"
                "  See the docstring at the top of screen_regions.py for instructions\n"
                "  on how to create this template."
            )

    # ── Take screenshot ──
    if screenshot is None:
        screenshot = take_screenshot()

    h, w = screenshot.shape[:2]
    th, tw = solo_template.shape[:2]

    # ── Run template matching ──
    # cv2.TM_CCOEFF_NORMED: returns values from -1.0 to 1.0.
    # Values near 1.0 = strong match. This method handles brightness variation
    # better than simpler methods.
    result = cv2.matchTemplate(screenshot, solo_template, cv2.TM_CCOEFF_NORMED)

    # Find all locations where the match score exceeds our threshold
    match_locations = np.where(result >= SOLO_MATCH_THRESHOLD)

    if len(match_locations[0]) == 0:
        raise RuntimeError(
            "No Solo buttons found on screen.\n"
            "Make sure Cubase is open and the track list is visible."
        )

    # ── Deduplicate overlapping matches ──
    # Template matching can return multiple adjacent hits for the same button.
    # We cluster them by proximity and keep only the best match per cluster.
    raw_points = list(zip(match_locations[1], match_locations[0]))  # (x, y)
    raw_scores = result[match_locations]
    deduped = _deduplicate_matches(raw_points, raw_scores, min_distance=tw // 2)

    # ── Sort by Y coordinate (top-to-bottom = track order) ──
    deduped.sort(key=lambda item: item[1])  # sort by y

    # ── Build SoloButton objects ──
    all_buttons: list[SoloButton] = []
    for track_idx, (x, y, confidence) in enumerate(deduped):
        # Convert top-left corner of template match to button centre
        cx = x + tw // 2
        cy = y + th // 2

        # Check if this track is selected
        is_selected = _is_track_selected(
            screenshot, cx, cy, selected_template, check_selection
        )

        all_buttons.append(SoloButton(
            x=cx,
            y=cy,
            track_index=track_idx,
            is_selected=is_selected,
            confidence=confidence,
        ))

    selected_buttons = [b for b in all_buttons if b.is_selected]

    return TrackListScan(
        all_buttons=all_buttons,
        selected_buttons=selected_buttons,
        screenshot_shape=(h, w),
    )


def _deduplicate_matches(
    points: list[tuple[int, int]],
    scores: np.ndarray,
    min_distance: int,
) -> list[tuple[int, int, float]]:
    """
    Cluster nearby match points and keep only the highest-scoring one per cluster.

    When OpenCV finds a match, the surrounding pixels also score highly,
    giving us many hits for what is actually one button. This function
    collapses those clusters down to a single point each.

    Parameters
    ----------
    points : list of (x, y)
    scores : parallel array of confidence scores
    min_distance : int
        Points within this many pixels of each other are the same button.

    Returns
    -------
    list of (x, y, score) — one entry per unique button found
    """
    if not points:
        return []

    used = [False] * len(points)
    result = []

    # Sort by score descending so we always pick the best hit in each cluster
    order = np.argsort(scores)[::-1]

    for i in order:
        if used[i]:
            continue
        xi, yi = points[i]
        used[i] = True
        result.append((xi, yi, float(scores[i])))

        # Mark nearby points as belonging to the same cluster
        for j in range(len(points)):
            if not used[j]:
                xj, yj = points[j]
                if abs(xi - xj) < min_distance and abs(yi - yj) < min_distance:
                    used[j] = True

    return result


def _is_track_selected(
    screenshot: np.ndarray,
    button_cx: int,
    button_cy: int,
    selected_template: Optional[np.ndarray],
    check_selection: bool,
) -> bool:
    """
    Determine if the track row containing a Solo button is selected.

    Strategy: sample a small horizontal strip of the track name background
    area (to the right of the S button) and compare it against the
    'selected track' template using template matching.

    If no template is available, returns True (treat all tracks as selected).

    Parameters
    ----------
    screenshot : full screen BGR image
    button_cx, button_cy : centre coordinates of the S button
    selected_template : the track_selected.png template, or None
    check_selection : overall flag — if False, always return True
    """
    if not check_selection or selected_template is None:
        return True  # No template = include all tracks

    # Define the strip region to sample
    strip_x = button_cx + SELECTION_SAMPLE_OFFSET_X
    strip_y = button_cy - SELECTION_SAMPLE_STRIP_H // 2
    strip_x2 = strip_x + SELECTION_SAMPLE_STRIP_W
    strip_y2 = strip_y + SELECTION_SAMPLE_STRIP_H

    # Clamp to image boundaries
    img_h, img_w = screenshot.shape[:2]
    strip_x  = max(0, strip_x)
    strip_y  = max(0, strip_y)
    strip_x2 = min(img_w, strip_x2)
    strip_y2 = min(img_h, strip_y2)

    strip = screenshot[strip_y:strip_y2, strip_x:strip_x2]

    # Strip must be at least the size of the template
    th, tw = selected_template.shape[:2]
    if strip.shape[0] < th or strip.shape[1] < tw:
        return True  # Strip too small to compare — default to include

    # Run matching against the selected-background template
    match_result = cv2.matchTemplate(strip, selected_template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(match_result)

    return max_val >= SELECTED_MATCH_THRESHOLD


# ── Diagnostic Tool ───────────────────────────────────────────────────────────

def debug_visualize(scan: TrackListScan, screenshot: np.ndarray) -> None:
    """
    Draw found buttons onto the screenshot and save it for inspection.
    Useful for verifying that buttons are being found in the right positions.

    Green circle = found S button (selected track)
    Grey circle  = found S button (not selected / no selection template)
    """
    vis = screenshot.copy()
    for btn in scan.all_buttons:
        color = (0, 200, 0) if btn.is_selected else (120, 120, 120)
        cv2.circle(vis, (btn.x, btn.y), 10, color, 2)
        cv2.putText(
            vis,
            f"T{btn.track_index + 1} {btn.confidence:.2f}",
            (btn.x + 12, btn.y + 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
        )

    out_path = Path(__file__).parent / "debug_scan.png"
    cv2.imwrite(str(out_path), vis)
    print(f"[debug] Visualization saved to: {out_path}")


# ── CLI / Quick Test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Taking screenshot and scanning for Solo buttons...")
    print("Make sure Cubase is visible on screen before running this.\n")

    try:
        screenshot = take_screenshot()
        scan = find_solo_buttons(screenshot=screenshot, check_selection=True)

        print(f"Found {len(scan.all_buttons)} Solo button(s) total:")
        for btn in scan.all_buttons:
            status = "SELECTED" if btn.is_selected else "not selected"
            print(f"  Track {btn.track_index + 1}: position ({btn.x}, {btn.y}) | "
                  f"confidence {btn.confidence:.3f} | {status}")

        print(f"\n{len(scan.selected_buttons)} track(s) queued for export.")
        debug_visualize(scan, screenshot)

    except (FileNotFoundError, RuntimeError) as e:
        print(f"\nError: {e}")
