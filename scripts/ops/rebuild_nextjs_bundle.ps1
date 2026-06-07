# Reassemble Next.js standalone build into desktop bundle (resources/nextjs).
# Run AFTER: cd admin-web && npm run build  (output:standalone -> .next/standalone + .next/static)
# Copies standalone + .next/static + public; preserves existing .env.production.
$root = "C:\work\01. haehan-ai-orchestrator"
$res  = "$root\dist-installer\win-unpacked\resources\nextjs"
$sa   = "$root\admin-web\.next\standalone"
$static = "$root\admin-web\.next\static"
$pub  = "$root\admin-web\public"

if (@(Get-Process -Name 'Haehan AI' -EA SilentlyContinue).Count -gt 0) { Write-Host "[ABORT] app running - close it first"; exit 1 }
if (-not (Test-Path (Join-Path $sa 'server.js'))) { Write-Host "[ABORT] no standalone build - run npm run build first"; exit 1 }

$envBak = Join-Path $env:TEMP 'nextjs_env_prod.bak'
$envSrc = Join-Path $res '.env.production'
if (Test-Path $envSrc) { Copy-Item $envSrc $envBak -Force }

$bak = $res + '.bak'
if (Test-Path $bak) { Remove-Item $bak -Recurse -Force }
Rename-Item $res $bak

robocopy $sa $res /E /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
robocopy $static (Join-Path $res '.next\static') /E /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
robocopy $pub (Join-Path $res 'public') /E /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
if (Test-Path $envBak) { Copy-Item $envBak $envSrc -Force }

$ok = (Test-Path (Join-Path $res 'server.js')) -and (Test-Path (Join-Path $res '.next\static\chunks')) -and (Test-Path (Join-Path $res 'node_modules\next'))
Write-Host ("server.js=" + (Test-Path (Join-Path $res 'server.js')))
Write-Host ("static/chunks=" + (Test-Path (Join-Path $res '.next\static\chunks')))
Write-Host ("public/sw.js=" + (Test-Path (Join-Path $res 'public\sw.js')))
Write-Host ("node_modules/next=" + (Test-Path (Join-Path $res 'node_modules\next')))
Write-Host ("env.production=" + (Test-Path $envSrc))
Write-Host ("RESULT=" + $(if ($ok) { 'OK' } else { 'INCOMPLETE' }))
