"""
diagnose_cpr.py — CPR parser diagnostic
----------------------------------------
Finds which track names the current parser is missing and shows
the raw bytes surrounding them so we can see what's structurally different.

Usage:
    python diagnose_cpr.py "E:/path/to/project.cpr" "MissingTrackName" "AnotherMissing"

Or just the file path to compare all parsed names vs raw string search:
    python diagnose_cpr.py "E:/path/to/project.cpr"
"""

import sys
import re
from pathlib import Path

# ── Current parser pattern (copy from cpr_parser.py) ─────────────────────────

_NAME_PATTERN = re.compile(
    b"\x00\xe7\x00\x00\x00\x00\x00\x00"
    b".."
    b"\x00\x00\x00([\x01-\x50])"
    b"([^\x00]{1,80})"
    b"\x00\xef\xbb\xbf",
    re.DOTALL,
)

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
_MEDIA_EXTENSIONS = (".wav", ".aiff", ".aif", ".mp3", ".flac", ".ogg", ".cpr")
_GUID_PATTERN = re.compile(r"^[A-F0-9]{32}$")

def is_system_string(name):
    if name in _SYSTEM_NAMES: return True
    if any(name.lower().endswith(ext) for ext in _MEDIA_EXTENSIONS): return True
    if name.startswith("VST"): return True
    if _GUID_PATTERN.match(name): return True
    if len(name) <= 1: return True
    return False

def hex_dump(data, offset, before=16, after=32):
    """Show hex and ASCII around a position in the file."""
    start = max(0, offset - before)
    end   = min(len(data), offset + after)
    chunk = data[start:end]
    marker_pos = offset - start

    hex_str = " ".join(f"{b:02x}" for b in chunk)
    asc_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)

    # Mark the position
    marker = " " * (marker_pos * 3) + "^^"

    return (f"  offset {offset} (0x{offset:08x}):\n"
            f"  hex: {hex_str}\n"
            f"       {marker}\n"
            f"  asc: {asc_str}")

# ── Main ──────────────────────────────────────────────────────────────────────

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)

cpr_path = Path(sys.argv[1])
if not cpr_path.exists():
    print(f"File not found: {cpr_path}")
    sys.exit(1)

with open(cpr_path, "rb") as f:
    data = f.read()

print(f"File: {cpr_path.name}  ({len(data):,} bytes)")
print()

# ── What the current parser finds ─────────────────────────────────────────────

parsed_names = []
for m in _NAME_PATTERN.finditer(data):
    try:    name = m.group(2).decode("utf-8")
    except: name = m.group(2).decode("latin-1")
    if not is_system_string(name) and name not in parsed_names:
        parsed_names.append(name)

print(f"Current parser finds {len(parsed_names)} track(s):")
for i, n in enumerate(parsed_names, 1):
    print(f"  {i}. {n}")
print()

# ── Names to investigate (from command line, or auto-detect gaps) ─────────────

missing_names = sys.argv[2:] if len(sys.argv) > 2 else []

if not missing_names:
    print("No specific names given — searching for all non-null string occurrences")
    print("that look like track names but weren't found by the parser.\n")
    print("Tip: run with extra args to investigate specific names:")
    print(f'  python diagnose_cpr.py "{cpr_path}" "MissingTrack"\n')

# ── For each name to investigate, find ALL occurrences in the raw binary ───────

for name in missing_names:
    encoded = name.encode("utf-8")
    print(f"{'='*60}")
    print(f"Looking for: '{name}' ({encoded.hex()})")
    print()

    positions = []
    start = 0
    while True:
        pos = data.find(encoded, start)
        if pos == -1:
            break
        positions.append(pos)
        start = pos + 1

    if not positions:
        print(f"  NOT FOUND anywhere in the file — check spelling/encoding.")
        print()
        continue

    print(f"  Found {len(positions)} occurrence(s):")
    for pos in positions:
        print()
        print(hex_dump(data, pos, before=20, after=len(encoded)+12))

        # Show what's 20 bytes before — this is where the signature should be
        look_back = max(0, pos - 20)
        pre_bytes = data[look_back:pos]
        print(f"\n  Pre-bytes (up to 20 before name):")
        print(f"  {' '.join(f'{b:02x}' for b in pre_bytes)}")

        # Check if the known signature is present nearby
        sig = b"\x00\xe7\x00\x00\x00\x00\x00\x00"
        sig_pos = data.rfind(sig, look_back, pos)
        if sig_pos != -1:
            gap = pos - sig_pos
            print(f"  Signature \\x00\\xe7... found {gap} bytes before name (expected ~14)")
        else:
            print(f"  Signature \\x00\\xe7... NOT found in the 20 bytes before — DIFFERENT FORMAT")

        # Show post-bytes (terminator area)
        post = data[pos + len(encoded): pos + len(encoded) + 8]
        print(f"  Post-bytes (8 after name end):")
        print(f"  {' '.join(f'{b:02x}' for b in post)}")
        expected_term = bytes([0x00, 0xef, 0xbb, 0xbf])
        if post[:4] == expected_term:
            print(f"  Terminator \\x00\\xef\\xbb\\xbf: PRESENT ✓")
        else:
            print(f"  Terminator \\x00\\xef\\xbb\\xbf: MISSING — terminator is different!")
    print()

# ── Also: show ALL occurrences of the \x00\xe7 signature to spot patterns ────

print(f"{'='*60}")
print(f"All \\x00\\xe7 signature locations in file:")
sig = b"\x00\xe7\x00\x00\x00\x00\x00\x00"
sig_positions = []
start = 0
while True:
    pos = data.find(sig, start)
    if pos == -1:
        break
    sig_positions.append(pos)
    start = pos + 1

print(f"  {len(sig_positions)} total occurrences\n")
for pos in sig_positions[:30]:  # cap at 30 to avoid flooding output
    # What string follows?
    # skip 2 ID bytes + 4 length bytes = 6 bytes after signature
    name_start = pos + 8 + 2 + 4
    name_end   = data.find(b"\x00", name_start)
    if name_end == -1 or name_end - name_start > 80:
        continue
    try:    candidate = data[name_start:name_end].decode("utf-8")
    except: candidate = data[name_start:name_end].decode("latin-1", errors="replace")

    length_byte = data[pos+10] if pos+10 < len(data) else 0
    term        = data[name_end:name_end+4]
    term_ok     = "✓" if term == bytes([0x00,0xef,0xbb,0xbf]) else f"✗ ({term.hex()})"
    print(f"  0x{pos:08x}  len_byte=0x{length_byte:02x}  term={term_ok}  → '{candidate}'")
