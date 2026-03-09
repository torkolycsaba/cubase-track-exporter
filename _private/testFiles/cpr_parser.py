"""
cpr_parser.py
-------------
Parses Steinberg Cubase .cpr project files to extract audio track names
in their visual top-to-bottom order, without any OCR.

How it works:
    Cubase stores track names in a binary format with a consistent structure:
        [8-byte signature: 00 e7 00 00 00 00 00 00]
        [2 bytes: internal track ID]
        [4 bytes: 00 00 00 <string_length>]
        [<string_length - 1> bytes: UTF-8 track name]
        [4 bytes: 00 ef bb bf  (UTF-8 BOM marker used as terminator)]

    Track names appear in file offset order, which matches the visual
    top-to-bottom order in the Cubase track list.

Usage:
    from cpr_parser import get_audio_track_names

    names = get_audio_track_names("MyProject.cpr")
    # Returns: ["Guitar Left", "Guitar Right", "Bass", "Vocals"]
"""

import re
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────

# Binary pattern discovered by inspecting .cpr file structure.
# The \x00\xe7 bytes appear to be a Cubase internal field type marker
# specifically for track name strings.
_NAME_PATTERN = re.compile(
    b"\x00\xe7\x00\x00\x00\x00\x00\x00"   # 8-byte field type signature
    b".."                                    # 2-byte internal track ID
    b"\x00\x00\x00([\x01-\x50])"            # 4-byte length prefix (max 80 chars)
    b"([^\x00]{1,80})"                       # the track name string
    b"\x00\xef\xbb\xbf",                    # UTF-8 BOM used as terminator
    re.DOTALL,
)

# Cubase system/internal strings that use the same storage format
# as track names but are NOT user-defined track names.
_SYSTEM_NAMES = {
    "No Picture", "Automation", "Panner", "Quick Controls", "EQ",
    "Input Filter", "Wave File", "Audio", "Video", "Trash", "Media",
    "Markers", "Mixer", "Transport", "FocusedQuickControlsFollower",
    "Video Player", "Focus Quick Controls", "MIDI Device Manager Project Data",
    "inputs", "outputs", "audio", "synth", "sampler", "midi", "group", "effect",
    "Stereo In", "Stereo Out", "Left", "Right",
    "GM Map", "Piano Player", "Guitar Player",
    "Event Colors", "New Attribute",
}

# File extension suffixes that indicate a media file reference, not a track name
_MEDIA_EXTENSIONS = (".wav", ".aiff", ".aif", ".mp3", ".flac", ".ogg", ".cpr")

# Hex strings (GUIDs) that Cubase stores in the same format
_GUID_PATTERN = re.compile(r"^[A-F0-9]{32}$")


# ── Core Parser ──────────────────────────────────────────────────────────────

def get_audio_track_names(cpr_path: str | Path) -> list[str]:
    """
    Extract user-defined track names from a Cubase .cpr file in track order.

    Parameters
    ----------
    cpr_path : str or Path
        Path to the .cpr project file.

    Returns
    -------
    list[str]
        Track names in top-to-bottom visual order as they appear in the
        Cubase project. Returns an empty list if no tracks are found.

    Raises
    ------
    FileNotFoundError
        If the .cpr file does not exist.
    ValueError
        If the file does not appear to be a valid Cubase project.
    """
    cpr_path = Path(cpr_path)

    if not cpr_path.exists():
        raise FileNotFoundError(f"Project file not found: {cpr_path}")

    with open(cpr_path, "rb") as f:
        data = f.read()

    # Sanity check: Cubase .cpr files start with the RIFF2 header
    if not data.startswith(b"RIF2"):
        raise ValueError(
            f"{cpr_path.name} does not appear to be a valid Cubase project file."
        )

    seen_names: set[str] = set()
    track_names: list[str] = []

    for match in _NAME_PATTERN.finditer(data):
        raw_bytes = match.group(2)

        # Decode — track names in Cubase are UTF-8
        try:
            name = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            name = raw_bytes.decode("latin-1")

        if _is_system_string(name):
            continue

        # De-duplicate: each track name appears multiple times in the file
        # (track header, mixer strip, pool). We only want the first occurrence,
        # which corresponds to the track definition in the track list.
        if name not in seen_names:
            seen_names.add(name)
            track_names.append(name)

    return track_names


def _is_system_string(name: str) -> bool:
    """Return True if this string is a Cubase internal value, not a track name."""
    if name in _SYSTEM_NAMES:
        return True
    if any(name.lower().endswith(ext) for ext in _MEDIA_EXTENSIONS):
        return True
    if name.startswith("VST"):
        return True
    if _GUID_PATTERN.match(name):
        return True
    if len(name) <= 1:
        return True
    return False


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python cpr_parser.py <path_to_project.cpr>")
        sys.exit(1)

    path = sys.argv[1]
    try:
        names = get_audio_track_names(path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    if not names:
        print("No track names found.")
    else:
        print(f"Found {len(names)} track(s) in project order:\n")
        for i, name in enumerate(names, 1):
            print(f"  {i}. {name}")
