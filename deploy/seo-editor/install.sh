#!/bin/sh
# Installs code and units, never creates a secret, enables a timer or calls an API.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run on the VPS as root.'; exit 1; }
SEO_SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ -d /var/www/thebookswanderer.com/guides ] || { echo 'Missing live guides directory'; exit 1; }
if ! id tbw-editor >/dev/null 2>&1; then
    useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin tbw-editor
fi
# Membership grants read access to the existing public report, if group-readable.
usermod -a -G www-data tbw-editor
install -d -m 755 /opt/tbw-seo-editor
# The worker needs traversal to config.json; the key itself stays root-only 0600.
install -d -m 711 /etc/tbw-seo-editor
install -d -o tbw-editor -g www-data -m 700 /var/lib/tbw-seo-editor
install -m 644 "$SEO_SOURCE/editor.py" /opt/tbw-seo-editor/editor.py
if [ ! -f /etc/tbw-seo-editor/config.json ]; then
    install -m 644 "$SEO_SOURCE/config.example.json" /etc/tbw-seo-editor/config.json
fi
# Keep credentials, existing configuration and editorial state on upgrades.
chgrp www-data /var/www/thebookswanderer.com/guides
chmod g+ws /var/www/thebookswanderer.com/guides
install -m 644 "$SEO_SOURCE/tbw-seo-editor.service" /etc/systemd/system/
install -m 644 "$SEO_SOURCE/tbw-seo-editor.timer" /etc/systemd/system/
systemctl daemon-reload
runuser -u tbw-editor -- test -r /var/lib/tbw-seo-reports/latest.json || {
    echo 'Installed but not activated: grant read-only access to the exported GSC summary.'; exit 2;
}
echo 'Installed, not activated. Configure the DeepSeek credential on the VPS; see README.'
