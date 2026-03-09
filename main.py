"""
main.py — Cubase Export Automation
------------------------------------
Usage:
    python main.py              — full run (de-solo sweep + export)
    python main.py --cleaned    — skip de-solo sweep, go straight to export
"""

import json
import sys
from pre_cleanup import run_preflight
from export_process import run_export
from controller import StopRequested

def main():
    with open("config.json", "r") as f:
        config = json.load(f)

    skip_desolo = "--cleaned" in sys.argv

    print("=" * 50)
    print("  Cubase Export Automation")
    if skip_desolo:
        print("  Mode: --cleaned (skipping de-solo sweep)")
    print("=" * 50)

    try:
        print("\n[ Step 1: Pre-cleanup & Queue Builder ]\n")
        export_queue = run_preflight(config, skip_desolo=skip_desolo)

        if not export_queue:
            print("\nNo tracks selected for export. Nothing to do.")
            return

        print("\n[ Step 2: Export Process ]\n")
        run_export(export_queue, config)

    except StopRequested:
        print("\n" + "=" * 50)
        print("  Process stopped by user.")
        print("=" * 50)

if __name__ == "__main__":
    main()