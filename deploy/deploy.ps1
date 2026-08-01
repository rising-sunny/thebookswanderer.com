# Deploy static site + API to Hetzner VPS
param(
    [string]$HostName = "root@5.78.125.169",
    [string]$RemotePath = "/var/www/thebookswanderer.com"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host "==> Directories" -ForegroundColor Cyan
ssh -o BatchMode=yes $HostName "mkdir -p $RemotePath/assets $RemotePath/server/services $RemotePath/server/data $RemotePath/deploy"

Write-Host "==> Static" -ForegroundColor Cyan
scp -o BatchMode=yes `
    "$Root\index.html" `
    "$Root\styles.css" `
    "$Root\app.js" `
    "$Root\product.html" `
    "$Root\product.js" `
    "$Root\cart.html" `
    "$Root\cart.js" `
    "$Root\checkout.html" `
    "$Root\checkout.js" `
    "$Root\affiliate-data.js" `
    "$Root\pick.html" `
    "$Root\pick.js" `
    "$Root\robots.txt" `
    "$Root\sitemap.xml" `
    "$Root\affiliate-products.json" `
    "$Root\track.js" `
    "${HostName}:${RemotePath}/"
# Google Search Console HTML verification (keep name stable)
if (Test-Path "$Root\googleca903f9ea8fb8e9e.html") {
    scp -o BatchMode=yes "$Root\googleca903f9ea8fb8e9e.html" "${HostName}:${RemotePath}/"
}
scp -o BatchMode=yes "$Root\assets\logo.png" "${HostName}:${RemotePath}/assets/"
if (Test-Path "$Root\assets\logo-email.png") {
    scp -o BatchMode=yes "$Root\assets\logo-email.png" "${HostName}:${RemotePath}/assets/"
}
if (Test-Path "$Root\assets\products") {
    ssh -o BatchMode=yes $HostName "mkdir -p $RemotePath/assets/products"
    scp -o BatchMode=yes -r "$Root\assets\products\*" "${HostName}:${RemotePath}/assets/products/"
}

Write-Host "==> Server" -ForegroundColor Cyan
scp -o BatchMode=yes `
    "$Root\server\main.py" `
    "$Root\server\database.py" `
    "$Root\server\models.py" `
    "$Root\server\requirements.txt" `
    "$Root\server\.env.example" `
    "${HostName}:${RemotePath}/server/"
scp -o BatchMode=yes `
    "$Root\server\services\__init__.py" `
    "$Root\server\services\cj.py" `
    "$Root\server\services\paypal.py" `
    "$Root\server\services\pricing.py" `
    "$Root\server\services\categories.py" `
    "$Root\server\services\email.py" `
    "${HostName}:${RemotePath}/server/services/"
if (Test-Path "$Root\server\ssr.py") {
    scp -o BatchMode=yes "$Root\server\ssr.py" "${HostName}:${RemotePath}/server/"
}
if (Test-Path "$Root\server\live.py") {
    scp -o BatchMode=yes "$Root\server\live.py" "${HostName}:${RemotePath}/server/"
}
if (Test-Path "$Root\server\templates") {
    ssh -o BatchMode=yes $HostName "mkdir -p $RemotePath/server/templates"
    scp -o BatchMode=yes "$Root\server\templates\*.html" "${HostName}:${RemotePath}/server/templates/"
}
if (Test-Path "$Root\server\services\geo.py") {
    scp -o BatchMode=yes "$Root\server\services\geo.py" "${HostName}:${RemotePath}/server/services/"
}
if (Test-Path "$Root\server\services\live_events.py") {
    scp -o BatchMode=yes "$Root\server\services\live_events.py" "${HostName}:${RemotePath}/server/services/"
}
if (Test-Path "$Root\server\scripts") {
    ssh -o BatchMode=yes $HostName "mkdir -p $RemotePath/server/scripts"
    scp -o BatchMode=yes "$Root\server\scripts\*.py" "${HostName}:${RemotePath}/server/scripts/"
}

scp -o BatchMode=yes "$PSScriptRoot\thebookswanderer.service" "${HostName}:/etc/systemd/system/thebookswanderer.service"
scp -o BatchMode=yes "$PSScriptRoot\remote-setup.sh" "${HostName}:${RemotePath}/deploy/remote-setup.sh"

Write-Host "==> Setup on VPS" -ForegroundColor Cyan
ssh -o BatchMode=yes $HostName "chmod +x $RemotePath/deploy/remote-setup.sh; bash $RemotePath/deploy/remote-setup.sh"

Write-Host ""
Write-Host "Deploy done. Health: https://thebookswanderer.com/api/health" -ForegroundColor Green
