#!/bin/bash
# One-time, approved by the owner on 2026-11-03: delete the large video files of three projects
# already public on YouTube (Stunning Revelations: bXZ-XCLw5_k, fUXqm3Bwsm4, G4TCwnqGEOU).
# Only the exact files below; scripts, notes, music and small files stay.
P=/home/videoagent/video-projects
echo "== before"; df -h / | tail -1
for f in \
  "$P/sea-peoples-1177bc/sea_peoples_final.mp4" \
  "$P/sea-peoples-1177bc/sea_peoples_upload.mp4" \
  "$P/starfish-prime-1962/starfish_upload.mp4" \
  "$P/molasses-1919/molasses_final.mp4" \
  "$P/molasses-1919/raw/boston1920.mp4" \
  "$P/molasses-1919/raw/boston1917.mp4"; do
  if [ -f "$f" ]; then
    if fuser -s "$f" 2>/dev/null; then echo "  kept (in use) $f"; continue; fi
    s=$(du -h "$f" | cut -f1); rm -f -- "$f" && echo "  deleted $s  $f"
  else
    echo "  not found $f"
  fi
done
du -sh "$P"/* 2>/dev/null
echo "== after"; df -h / | tail -1
