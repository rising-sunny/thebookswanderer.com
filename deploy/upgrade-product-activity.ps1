# Upgrade only the reviewed product-activity change; keep all credentials on the VPS.
param([string]$HostName = 'root@5.78.125.169')

$ErrorActionPreference = 'Stop'
$deploymentScript = @'
set -euo pipefail
shop=/var/www/thebookswanderer.com
revision=d542fbb02db9ffc5bce00d65048baf15ae0fd812
stage=$(mktemp -d /root/tbw-product-activity.XXXXXX)
backup=/var/backups/tbw-product-activity/$(date -u +%Y%m%dT%H%M%S)-$$

command -v git >/dev/null
command -v curl >/dev/null
test -x "$shop/server/.venv/bin/python"
test -x /opt/tbw-mcp/.venv/bin/python
systemctl is-active --quiet thebookswanderer.service
systemctl is-active --quiet tbw-admin-api.service
systemctl is-active --quiet tbw-mcp.service

curl -fsSL --retry 3 "https://github.com/rising-sunny/thebookswanderer.com/archive/$revision.tar.gz" | tar -xz -C "$stage" --strip-components=1
curl -fsSL --retry 3 "https://github.com/rising-sunny/thebookswanderer.com/commit/$revision.patch" -o "$stage/change.patch"
cd "$shop"
# Refuse conflicting deployed edits rather than replace whole source files.
git apply --check --include=server/main.py --include=server/models.py "$stage/change.patch"
"$shop/server/.venv/bin/python" "$stage/deploy/admin-api/install.py" --upgrade --check
/opt/tbw-mcp/.venv/bin/python "$stage/deploy/mcp/install.py" --upgrade --check

install -d -m 700 "$backup"
cp -p server/main.py server/models.py "$backup/"
git apply --include=server/main.py --include=server/models.py "$stage/change.patch"
for file in main.py models.py; do
    chown --reference="$backup/$file" "server/$file"
    chmod --reference="$backup/$file" "server/$file"
done
if ! systemctl restart thebookswanderer.service || ! curl -fsS --retry 15 --retry-delay 1 --retry-connrefused http://127.0.0.1:8010/api/health -o /dev/null; then
    cp -p "$backup/main.py" "$backup/models.py" server/
    systemctl restart thebookswanderer.service
    echo 'Storefront upgrade failed; previous source restored.' >&2
    exit 1
fi

# These existing installers back up and roll back their own service on failure.
"$shop/server/.venv/bin/python" "$stage/deploy/admin-api/install.py" --upgrade
/opt/tbw-mcp/.venv/bin/python "$stage/deploy/mcp/install.py" --upgrade
systemctl is-active --quiet thebookswanderer.service tbw-admin-api.service tbw-mcp.service
echo "Upgrade complete. Storefront source backup: $backup"
echo 'Refresh tool discovery in the existing The Books Wanderer plugin.'
'@

# Windows PowerShell can send CRLF through native stdin; normalize it remotely.
$deploymentScript | ssh $HostName "tr -d '\r' | bash -se"
if ($LASTEXITCODE -ne 0) {
    throw "The VPS upgrade stopped (exit code $LASTEXITCODE). Do not retry blindly; share the error, without credentials."
}
