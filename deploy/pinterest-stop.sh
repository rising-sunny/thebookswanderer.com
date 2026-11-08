#!/bin/bash
# One-time, owner-approved (2026-11-08): stop every automatic Pinterest publication (daily drip, launch pin
# on product publish, and the Pinterest part of the daily Facebook/Instagram reel). Pins stay as they are;
# the cron entries keep running but do nothing while these flags are off. Prints only flag names and values.
ENV=/var/www/thebookswanderer.com/server/.env
set_flag() {
  if grep -q "^$1=" "$ENV"; then sed -i "s/^$1=.*/$1=$2/" "$ENV"; else printf '\n%s=%s\n' "$1" "$2" >> "$ENV"; fi
  echo "pinterest stop: $1=$2"
}
set_flag PINTEREST_AUTO_PIN_ENABLED 0
set_flag PINTEREST_LAUNCH_PIN_ENABLED 0
set_flag PINTEREST_PINS_PER_DAY 0
systemctl restart thebookswanderer.service && sleep 3 && echo "store: $(systemctl is-active thebookswanderer.service)"
