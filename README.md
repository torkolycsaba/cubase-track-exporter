# Cubase Track Exporter

A Python automation script that exports individual audio tracks from a Steinberg Cubase project — automatically, without any manual clicking.

Select the tracks you want to export in Cubase, run the script, and it solos and exports each one in sequence.

---

## What it does

1. **Pre-cleanup** — scans the track list top to bottom, clears any accidentally active solo buttons, then reads which tracks you've marked for export (the highlighted track state in Cubase)
2. **Export loop** — for each selected track: solos it, opens the Export Audio Mixdown dialog, sets the filename to the track name, triggers the export, waits for it to finish, then un-solos and moves to the next one

Track names and their order are read directly from the `.cpr` project file.

---

## Requirements

- Windows (uses `pyautogui` for screen control — tested on Windows 10/11)
- Steinberg Cubase (tested on Cubase 14 Elements)
- Python 3.10+

---

## Installation

```bash
git clone https://github.com/yourusername/cubase-track-exporter.git
cd cubase-track-exporter
pip install -r requirements.txt
```

---

## Setup

### 1. Configure your project path and hotkey

Edit `config.json`:

```json
{
    "project_file": "C:/path/to/your/project.cpr",
    "export_hotkey": ["ctrl", "shift", "e"],
    "pause_key": "p",
    "stop_key": "f10",
    "pixel_per_scroll": 30
}
```

| Key | Description |
|-----|-------------|
| `project_file` | Full path to your `.cpr` Cubase project file - Make sure that it is saved!|
| `export_hotkey` | The keyboard shortcut you have set in Cubase for *Export Audio Mixdown* |
| `pause_key` | Key or combo to pause/resume the script (e.g. `"p"`, `"ctrl+f8"`) |
| `stop_key` | Key or combo to immediately stop (e.g. `"f10"`, `"ctrl+f9"`) |
| `pixel_per_scroll` | How many pixels the track list scrolls per step — adjust if track detection is unreliable |

> ⚠️ **Avoid using simple letter keys for `pause_key` / `stop_key`** — the script types track names during export, so a letter like `"s"` would trigger if any track name contains that letter. Use F-keys or combos like `ctrl+f8`.

#### Finding your pixel_per_scroll value

The default is `30`, which works for most standard Cubase setups. If tracks are being skipped or exported twice, your value is off. Here's how to find the right one:

1. Open your Cubase project and make sure the track list is visible
2. Take a screenshot (e.g. with Snipping Tool) and note the Y position of any solo button
3. Scroll the track list down by exactly one scroll step (one tick of your mouse wheel)
4. Take another screenshot and note the new Y position of the same button
5. The difference between the two Y values is your `pixel_per_scroll`

In general: If you see the same track exported twice, your value is too low — increase it by 5 and try again. If a track gets skipped entirely, it may be too high — decrease by 5.

---

### 2. Set your export folder in Cubase

Open the Export Audio Mixdown dialog in Cubase once and set your output folder manually. Cubase remembers it — the script only sets the filename, not the path.

### 3. If default images fail on your system - Capture template images 

The script uses template matching to find buttons on screen. You need to provide four small screenshots of your Cubase UI:

| File | What to capture |
|------|----------------|
| `templates/track_list_anchor.png` | The top-left corner of the track list panel (used to locate the panel on screen) |
| `templates/solo_button_normal.png` | An S button in its default (inactive) state |
| `templates/solo_button_selected.png` | An S button in its *selected for export* state (highlighted) |
| `templates/solo_button_soloed.png` | An S button while actively soloed (the red/orange state) |
| `templates/export_audio_button.png` | The Export button inside the Export Audio Mixdown dialog |
| `templates/export_abort_button.png` | The Abort button in the export progress window |

Crop these tightly — 20–40px wide is enough. Use the same UI scale you'll run the script at.

---

## Usage

In Cubase, select the tracks you want to export (highlighted as light gray). Then:

```bash
python main.py
```

If you have manually made sure no tracks are soloed before running, you can skip the de-solo sweep with the --cleaned flag for a slightly faster start:

```bash
python main.py --cleaned
```

The script will print its progress to the terminal. You can monitor it or minimise the window — just don't move the Cubase window or change your screen layout while it runs.

**Controls while running:**

| Key | Action |
|-----|--------|
| `pause_key` (default: `ctrl+f9`) | Pause / resume |
| `stop_key` (default: `ctrl+f10`) | Quit |

---

## Project structure

```
cubase-track-exporter/
├── main.py                  # Entry point — runs pre-cleanup then export loop
├── pre_cleanup.py           # Phase 1: de-solo sweep  Phase 2: build export queue
├── export_process.py        # Export loop
├── controller.py            # Pause/stop keyboard listener (background thread)
├── cpr_parser.py            # Reads track names from .cpr binary
├── config.json              # Your settings
├── templates/               # Button/UI screenshots for template matching
├── requirements.txt
└── README.md
```

---

## Troubleshooting

**Script doesn't find the track list**
- Make sure Cubase is visible and not minimised when you start the script
- Re-capture `track_list_anchor.png` — it needs to match your current UI exactly

**Wrong tracks are being exported / duplicates**
- Adjust `pixel_per_scroll` in config — it should match how far your track list actually moves per scroll step. You can measure this by scrolling once and comparing button positions before and after.

**Export dialog doesn't open**
- Check that `export_hotkey` in config matches the shortcut set in Cubase (*File > Key Commands > Export Audio Mixdown*)

**Script stops at random track**
- Check that your `pause_key or stop_key` isn't a letter that appears in any track name. Rename the key binding to an F-key or combo.

---

## How the `.cpr` parser works

Cubase stores track names in a binary format inside the `.cpr` file. The parser scans for two known byte signatures that precede track name strings, extracts the name, and filters out internal Cubase system strings. This gives track names in their top-to-bottom visual order without any OCR or Cubase API calls.

---

## Limitations

- Windows only (pyautogui screen control)
- Tested on Cubase 14 Elements — other versions likely work but are untested
- Requires the Cubase window to remain visible and at a fixed position during the run
- UI scaling changes between template capture and script execution will break template matching
