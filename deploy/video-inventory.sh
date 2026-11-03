#!/bin/bash
# One-time, read-only: which video projects on the VPS match videos already public on YouTube.
# For each project folder: size, last change, big media files, and any published video id or
# title word found in its small text files (json/txt/md/yaml). Changes nothing.
IDS="bXZ-XCLw5_k fUXqm3Bwsm4 G4TCwnqGEOU gHTWjlb2RZY Xz7fmC8a-00 mpknQRr5DKs sfxCOw74AY4 3d5MUi75ay4 7zneyyFQdOk CDCfH1w2f0I mMKSYKUGxcA COIdhPZtR10 th4FDI6RJ6A g0nihDBs34Q 5Kcd_mHlBGk kTmr8P2zYqE miTS04gp_gg mvgGXbPompA 8bSKxMfllbk THQDwFb5_hw XAmdCZxlVwg F_6Npdzv0Ow SSWQ77K6fVw jj82pI_Myd4 4LgWHZX51q4 SsGy6SQAEgs a-gpxugnxqg R2AVlqOAMw4 6QaFqR5WcMI 04T9zfinsQs"
for base in /home/videoagent/video-projects /home/videoagent/video-automation/runtime; do
  echo "#### $base ($(du -sh "$base" 2>/dev/null | cut -f1))"
  for d in "$base"/*/; do
    [ -d "$d" ] || continue
    size=$(du -sh "$d" 2>/dev/null | cut -f1)
    last=$(find "$d" -type f -printf '%TY-%Tm-%Td\n' 2>/dev/null | sort | tail -1)
    found=""
    for id in $IDS; do
      grep -rqs --include='*.json' --include='*.txt' --include='*.md' --include='*.yaml' --include='*.yml' --include='*.log' -- "$id" "$d" && found="$found $id"
    done
    echo "== $(basename "$d")  $size  last $last  ids:${found:- none}"
    find "$d" -type f \( -name '*.mp4' -o -name '*.mov' -o -name '*.mkv' -o -name '*.wav' -o -name '*.zip' \) -size +50M \
      -printf '   %s\t%TY-%Tm-%Td\t%P\n' 2>/dev/null | sort -rn | head -8 | awk -F'\t' '{printf "   %6.0f MB  %s  %s\n", $1/1048576, $2, $3}'
  done
done
echo "#### other big folders in /home/videoagent"
du -xh --max-depth=1 /home/videoagent 2>/dev/null | sort -rh | head -12
echo "== done"
