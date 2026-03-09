"""
pre_cleanup.py — Phase 1 & 2: De-solo sweep + track classification
-------------------------------------------------------------------
Call run_preflight(config) from main.py.
Returns export_queue: list of track name strings in top-to-bottom order.

Can also be run standalone:
    python pre_cleanup.py
"""

import cv2
import numpy as np
import pyautogui
import time
import json
from cpr_parser import get_audio_track_names

# ── Settings ───────────────────────────────────────────────────────────────────

HEADER_HEIGHT      = 30
SEARCH_WIDTH       = 260
MATCH_THRESHOLD    = 0.85
SOLOED_THRESHOLD   = 0.90
SCROLL_AMOUNT      = 15
SCROLL_SETTLE      = 0.3
SCROLL_TO_TOP      = 40
CLICK_SETTLE       = 0.5
STOP_THRESHOLD     = 3.0
MIN_TRACK_GAP      = 15

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
    hits = find_all_matches(region, template_soloed, SOLOED_THRESHOLD, "soloed")
    return [{"screen_x": h["region_x"]+offset_x,
             "screen_y": h["region_y"]+offset_y,
             "confidence": h["confidence"]} for h in hits]

def scan_all_buttons(region, offset_x, offset_y):
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

# ── Main function ──────────────────────────────────────────────────────────────

def run_preflight(config):
    """
    Phase 1: scroll top to bottom, click any soloed buttons to de-solo them.
    Phase 2: scroll back to top, take a clean scan, classify every track.
    Returns export_queue: list of track name strings marked for export.
    """
    cpr_path    = config["project_file"]
    track_names = get_audio_track_names(cpr_path)
    TOTAL_TRACKS = len(track_names)

    print(f"Loaded {TOTAL_TRACKS} track names from: {cpr_path}")
    for i, name in enumerate(track_names):
        print(f"  {i+1}. {name}")
    print()

    # Find search area and position mouse
    print("Finding track list...")
    screenshot = take_screenshot()
    search_x1, search_y1, search_x2, search_y2 = find_search_area(screenshot)
    center_x = (search_x1 + search_x2) // 2
    center_y = search_y1 + (search_y2 - search_y1) // 5
    print(f"Search area: ({search_x1},{search_y1}) to ({search_x2},{search_y2})")

    pyautogui.moveTo(center_x, center_y)
    time.sleep(0.2)

    # Scroll to top
    print("Scrolling to top...")
    for _ in range(SCROLL_TO_TOP):
        pyautogui.scroll(SCROLL_AMOUNT)
    time.sleep(0.5)

    # ── PHASE 1: De-solo sweep ─────────────────────────────────────────────────

    print("\n── Phase 1: De-solo sweep ──────────────────────────────────────────")
    prev_region  = None
    scroll_count = 0

    while True:
        screenshot    = take_screenshot()
        search_region = screenshot[search_y1:search_y2, search_x1:search_x2]

        soloed = find_soloed_buttons(search_region, search_x1, search_y1)
        for btn in soloed:
            print(f"  Soloed at ({btn['screen_x']}, {btn['screen_y']}) "
                  f"conf={btn['confidence']:.3f} — clicking...")
            pyautogui.click(btn["screen_x"], btn["screen_y"])
            time.sleep(CLICK_SETTLE)

            fresh        = take_screenshot()
            fresh_region = fresh[search_y1:search_y2, search_x1:search_x2]
            still_soloed = find_soloed_buttons(fresh_region, search_x1, search_y1)
            still_at_pos = [b for b in still_soloed
                            if abs(b["screen_y"] - btn["screen_y"]) < 10]
            if still_at_pos:
                print(f"    Still soloed — clicking again...")
                pyautogui.click(btn["screen_x"], btn["screen_y"])
                time.sleep(CLICK_SETTLE)
            else:
                print(f"    De-soloed successfully.")

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

    print("Phase 1 complete.")

    # ── PHASE 2: Clean scan ────────────────────────────────────────────────────

    print("\n── Phase 2: Clean scan ─────────────────────────────────────────────")
    print("Scrolling back to top...")
    for _ in range(SCROLL_TO_TOP):
        pyautogui.scroll(SCROLL_AMOUNT)
    time.sleep(0.5)

    # Calibration scroll
    screenshot    = take_screenshot()
    search_region = screenshot[search_y1:search_y2, search_x1:search_x2]
    initial_btns  = scan_all_buttons(search_region, search_x1, search_y1)
    top_y_before  = initial_btns[0]["screen_y"] if initial_btns else search_y1

    pyautogui.scroll(-SCROLL_AMOUNT)
    time.sleep(SCROLL_SETTLE)
    screenshot    = take_screenshot()
    search_region = screenshot[search_y1:search_y2, search_x1:search_x2]
    after_btns    = scan_all_buttons(search_region, search_x1, search_y1)
    shift         = top_y_before - after_btns[0]["screen_y"] if after_btns else 30
    pixel_per_scroll = shift if shift > 0 else 30
    print(f"Calibrated: {pixel_per_scroll}px per scroll step")

    for _ in range(SCROLL_TO_TOP):
        pyautogui.scroll(SCROLL_AMOUNT)
    time.sleep(0.5)

    all_tracks   = []
    prev_region  = None
    scroll_count = 0

    while len(all_tracks) < TOTAL_TRACKS:
        screenshot    = take_screenshot()
        search_region = screenshot[search_y1:search_y2, search_x1:search_x2]
        visible       = scan_all_buttons(search_region, search_x1, search_y1)

        if not all_tracks:
            all_tracks = list(visible)
            for i, b in enumerate(all_tracks):
                print(f"  Track {i+1:2d}: ({b['screen_x']}, {b['screen_y']})  "
                      f"state={b['state']}")
        else:
            last_y   = all_tracks[-1]["screen_y"] - pixel_per_scroll
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

    # ── Pair names with scan results and build export queue ────────────────────

    queued = [b for b in all_tracks if b["state"] == "selected"]

    print(f"\n{'='*50}")
    print(f"Tracks paired with names:")
    print(f"{'='*50}")

    export_queue = []
    for i, (btn, name) in enumerate(zip(all_tracks, track_names)):
        status = "→ EXPORT" if btn["state"] == "selected" else "   skip"
        print(f"  {i+1:2d}. {name:30s}  {status}")
        if btn["state"] == "selected":
            export_queue.append(name)

    print(f"\nExport queue ({len(export_queue)} tracks):")
    for name in export_queue:
        print(f"  → {name}")

    return export_queue


if __name__ == "__main__":
    with open("config.json", "r") as f:
        config = json.load(f)
    export_queue = run_preflight(config)
