#!/bin/bash
# One-time, owner-approved (2026-11-03): allow Meta ad objects to be created through the store,
# paused only, with a daily budget cap of 15,000 (account currency CLP, which has no subunit).
ENV=/var/www/thebookswanderer.com/server/.env
if grep -q '^TBW_META_ADS_MAX_DAILY_BUDGET=' "$ENV"; then
  echo "meta ads cap already set"
else
  printf '\n# Meta ads via the store: paused only, daily budget cap (account currency, minor units)\nTBW_META_ADS_MAX_DAILY_BUDGET=15000\n' >> "$ENV"
  echo "meta ads cap set"
fi
systemctl restart thebookswanderer.service && sleep 3 && echo "store: $(systemctl is-active thebookswanderer.service)"
