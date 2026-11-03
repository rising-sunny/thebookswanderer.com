#!/bin/bash
# One-time disk cleanup approved by the owner on 2026-11-03 (root disk alert at 85%).
# Only regenerable or superseded data: old journal entries (with a permanent 500 MB cap),
# disabled snap revisions and unreferenced snap cache, superseded VS Code server builds,
# pip and apt caches. Videos, backups, /tmp and the Playwright browsers are not touched.
echo "== before"; df -h / | tail -1

echo "== 1. journal: cap at 500 MB"
mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=500M\n' > /etc/systemd/journald.conf.d/size.conf
systemctl restart systemd-journald
journalctl --vacuum-size=500M 2>&1 | tail -1
journalctl --disk-usage

echo "== 2. snaps: keep 2 revisions, drop disabled ones and unreferenced cache"
snap set system refresh.retain=2 2>/dev/null
snap list --all 2>/dev/null | awk '/disabled/{print $1, $3}' | while read -r name rev; do
  snap remove "$name" --revision="$rev" >/dev/null 2>&1 && echo "  removed $name r$rev"
done
find /var/lib/snapd/cache -type f -links 1 -delete 2>/dev/null
du -sh /var/lib/snapd

echo "== 3. VS Code server: keep the newest build"
S=/root/.vscode/cli/servers
if [ -d "$S" ]; then
  ls -1dt "$S"/*/ 2>/dev/null | tail -n +2 | while read -r d; do rm -rf "$d" && echo "  removed $(basename "$d")"; done
  du -sh /root/.vscode
fi

echo "== 4. pip and apt caches"
rm -rf /root/.cache/pip
apt-get clean
du -sh /root/.cache /var/cache/apt 2>/dev/null

echo "== after"; df -h / | tail -1
