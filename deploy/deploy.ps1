# Deploy static site + API to Hetzner VPS
param(
    [string]$HostName = "root@5.78.125.169",
    [string]$RemotePath = "/var/www/thebookswanderer.com"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

# $ErrorActionPreference does not apply to native executables: a failing ssh or
# scp sets $LASTEXITCODE but does not stop the script, so the deploy used to
# print "Deploy done" in green even when the remote setup had failed and the
# service was never restarted. Check after every native call instead.
function Assert-Ok([string]$What) {
    if ($LASTEXITCODE -ne 0) {
        throw "$What failed (exit code $LASTEXITCODE)"
    }
}

Write-Host "==> Directories" -ForegroundColor Cyan
ssh -o BatchMode=yes $HostName "mkdir -p $RemotePath/assets $RemotePath/server/services $RemotePath/server/data $RemotePath/deploy"
Assert-Ok "mkdir on remote"

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
    "$Root\about.html" `
    "$Root\contact.html" `
    "$Root\privacy.html" `
    "$Root\shipping-returns.html" `
    "$Root\robots.txt" `
    "$Root\sitemap.xml" `
    "$Root\affiliate-products.json" `
    "$Root\track.js" `
    "${HostName}:${RemotePath}/"
Assert-Ok "static upload"
# Google Search Console HTML verification (keep name stable)
if (Test-Path "$Root\googleca903f9ea8fb8e9e.html") {
    scp -o BatchMode=yes "$Root\googleca903f9ea8fb8e9e.html" "${HostName}:${RemotePath}/"
    Assert-Ok "search console file upload"
}
# Brand / SEO images (logo optimized, OG 1200×630, favicons)
$brandAssets = @(
    "logo.png", "logo.webp", "logo-hero.webp", "logo-email.png", "og-default.jpg",
    "favicon.ico", "favicon-32.png", "favicon-48.png", "apple-touch-icon.png"
)
foreach ($f in $brandAssets) {
    if (Test-Path "$Root\assets\$f") {
        scp -o BatchMode=yes "$Root\assets\$f" "${HostName}:${RemotePath}/assets/"
    }
}
Assert-Ok "brand assets upload"
if (Test-Path "$Root\assets\products") {
    ssh -o BatchMode=yes $HostName "mkdir -p $RemotePath/assets/products"
    Assert-Ok "mkdir assets/products"
    scp -o BatchMode=yes -r "$Root\assets\products\*" "${HostName}:${RemotePath}/assets/products/"
    Assert-Ok "product images upload"
}

Write-Host "==> Server" -ForegroundColor Cyan
scp -o BatchMode=yes `
    "$Root\server\main.py" `
    "$Root\server\database.py" `
    "$Root\server\models.py" `
    "$Root\server\requirements.txt" `
    "$Root\server\.env.example" `
    "${HostName}:${RemotePath}/server/"
Assert-Ok "server upload"
scp -o BatchMode=yes `
    "$Root\server\services\__init__.py" `
    "$Root\server\services\cj.py" `
    "$Root\server\services\paypal.py" `
    "$Root\server\services\pricing.py" `
    "$Root\server\services\categories.py" `
    "$Root\server\services\email.py" `
    "$Root\server\services\meta_capi.py" `
    "$Root\server\services\health.py" `
    "$Root\server\services\pinterest.py" `
    "$Root\server\services\pinterest_jobs.py" `
    "$Root\server\services\printify.py" `
    "${HostName}:${RemotePath}/server/services/"
Assert-Ok "services upload"
if (Test-Path "$Root\server\routers") {
    ssh -o BatchMode=yes $HostName "mkdir -p $RemotePath/server/routers"
    Assert-Ok "mkdir server/routers"
    scp -o BatchMode=yes `
        "$Root\server\routers\__init__.py" `
        "$Root\server\routers\pinterest.py" `
        "${HostName}:${RemotePath}/server/routers/"
    Assert-Ok "routers upload"
}
if (Test-Path "$Root\server\ssr.py") {
    scp -o BatchMode=yes "$Root\server\ssr.py" "${HostName}:${RemotePath}/server/"
    Assert-Ok "ssr.py upload"
}
if (Test-Path "$Root\server\urls.py") {
    scp -o BatchMode=yes "$Root\server\urls.py" "${HostName}:${RemotePath}/server/"
}
if (Test-Path "$Root\server\live.py") {
    scp -o BatchMode=yes "$Root\server\live.py" "${HostName}:${RemotePath}/server/"
    Assert-Ok "live.py upload"
}
if (Test-Path "$Root\server\templates") {
    ssh -o BatchMode=yes $HostName "mkdir -p $RemotePath/server/templates"
    Assert-Ok "mkdir server/templates"
    scp -o BatchMode=yes "$Root\server\templates\*.html" "${HostName}:${RemotePath}/server/templates/"
    Assert-Ok "templates upload"
}
if (Test-Path "$Root\server\services\geo.py") {
    scp -o BatchMode=yes "$Root\server\services\geo.py" "${HostName}:${RemotePath}/server/services/"
    Assert-Ok "geo.py upload"
}
if (Test-Path "$Root\server\services\live_events.py") {
    scp -o BatchMode=yes "$Root\server\services\live_events.py" "${HostName}:${RemotePath}/server/services/"
    Assert-Ok "live_events.py upload"
}
if (Test-Path "$Root\server\scripts") {
    ssh -o BatchMode=yes $HostName "mkdir -p $RemotePath/server/scripts"
    Assert-Ok "mkdir server/scripts"
    scp -o BatchMode=yes "$Root\server\scripts\*.py" "${HostName}:${RemotePath}/server/scripts/"
    Assert-Ok "scripts upload"
}

scp -o BatchMode=yes "$PSScriptRoot\thebookswanderer.service" "${HostName}:/etc/systemd/system/thebookswanderer.service"
Assert-Ok "systemd unit upload"
scp -o BatchMode=yes "$PSScriptRoot\remote-setup.sh" "${HostName}:${RemotePath}/deploy/remote-setup.sh"
Assert-Ok "remote-setup.sh upload"

Write-Host "==> Setup on VPS" -ForegroundColor Cyan
# sed guards against a CRLF checkout reaching the VPS: bash rejects a shebang
# ending in \r. .gitattributes pins these files to LF, this is the belt.
ssh -o BatchMode=yes $HostName "sed -i 's/\r`$//' $RemotePath/deploy/remote-setup.sh; chmod +x $RemotePath/deploy/remote-setup.sh; bash $RemotePath/deploy/remote-setup.sh"
Assert-Ok "remote setup"

Write-Host ""
Write-Host "Deploy done. Health: https://thebookswanderer.com/api/health" -ForegroundColor Green
