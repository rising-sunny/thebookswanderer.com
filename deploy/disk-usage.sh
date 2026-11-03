#!/bin/bash
# One-time, read-only: what fills the root disk. Prints sizes and paths only (no file contents),
# and changes nothing.
echo "== df"
df -h / | tail -1
echo "== top directories (2 levels)"
du -xh --max-depth=2 / 2>/dev/null | sort -rh | head -25
echo "== inside /var, /opt, /root, /home, /var/www (3 levels)"
for d in /var /opt /root /home /var/www; do
  du -xh --max-depth=3 "$d" 2>/dev/null | sort -rh | head -12
done
echo "== largest files over 100 MB"
find / -xdev -type f -size +100M -printf '%s\t%TY-%Tm-%Td\t%p\n' 2>/dev/null | sort -rn | head -25 \
  | awk -F'\t' '{printf "%7.0f MB  %s  %s\n", $1/1048576, $2, $3}'
echo "== caches and logs"
journalctl --disk-usage 2>/dev/null
du -sh /var/log /var/cache/apt /root/.cache /var/lib/docker /tmp /var/tmp /var/backups 2>/dev/null
ls /var/log/*.gz /var/log/*.[0-9] 2>/dev/null | wc -l | sed 's/^/rotated log files: /'
echo "== deleted files still held open"
find /proc/[0-9]*/fd -lname '*(deleted)' -printf '%l\n' 2>/dev/null | sort | uniq -c | sort -rn | head -10
echo "== done"
