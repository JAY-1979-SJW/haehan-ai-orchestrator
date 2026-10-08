<#
.SYNOPSIS
  데스크톱 앱(portable exe)을 '빈 PC처럼' 실행하고, 끝난 뒤 임시 폴더 결과를 요약한다 (첫 빌드 점검 9~16번용).

.DESCRIPTION
  실제 사용자 데이터(%APPDATA%\Haehan AI)와 Claude 설정을 건드리지 않도록, 앱을 임시 사용자 데이터 폴더로 실행한다.
  방식: Electron/Chromium 의 `--user-data-dir=<임시폴더>` 스위치. main.js·lib/config.js 어디에도 userData 를 따로 고정하는 코드가
  없어 app.getPath("userData") 가 이 스위치를 따른다(W2 의 E2E fresh_install_signup.spec.ts 도 같은 방식).
  → config.json · data · storage · logs · run · mcp(Claude 연결용 고정 폴더) 가 전부 임시 폴더 안에 생긴다.

  기본(격리) 모드는 임시 config.json 에 {"claude_mcp":{"prompted":true}} 를 미리 넣어 'Claude 연결' 동의 창이 뜨지 않게 한다.
  Claude Desktop 설정 위치(app.getPath("appData"))는 --user-data-dir 로 바꿀 수 없어서, 동의 창에서 [연결]을 누르면 **실제**
  %APPDATA%\Claude\claude_desktop_config.json 이 바뀌기 때문이다. 연결 점검(14·15번)은 -RealClaude 로만 한다.

.PARAMETER ExePath
  내려받은 HaehanAI-<버전>-portable.exe 경로.
.PARAMETER WorkDir
  임시 작업 폴더(기본 %TEMP%\haehan-fresh-<시각>). **이미 있는 폴더를 주면 데이터를 지우지 않고 그대로 이어서 실행**한다
  (앱을 껐다 다시 켜는 10번 점검용: 같은 -WorkDir 로 한 번 더 실행).
.PARAMETER SummaryOnly
  앱을 실행하지 않고 -WorkDir 의 결과만 요약한다(앱이 이미 꺼졌거나 중간에 이 창을 닫았을 때).
.PARAMETER DryRun
  실행하지 않고 무엇을 할지(경로·명령·포트 점검)만 출력한다.
.PARAMETER RealClaude
  Claude 연결 점검용. 임시 userData 는 그대로 쓰되 동의 창을 막지 않는다 → [연결]을 누르면 실제 Claude 설정이 바뀐다.
  실행 전에 claude_desktop_config.json 과 ~\.claude.json 을 <WorkDir>\backup 에 복사하고 백업 경로·복원 명령을 출력한다.
.PARAMETER ImportFromOldApp
  예전 앱 설치 폴더(예: C:\Users\skyjw\Haehan AI). 새 앱의 **자동 가져오기**(paths/legacy_import.py)가 이 폴더의 storage 를 임시
  userData 로 **복사**(덮어쓰기 없음, 원본 읽기만)하도록 HAEHAN_LEGACY_INSTALL_DIRS 로 알려 준다 → '예전 데이터가 있는 PC' 시나리오
  (이행된 계정 → "사용자 정보" 화면 없이 자동 로그인)를 임시 폴더에서 시험한다. 이 옵션이 없으면 격리 실행은 예전 앱 폴더를
  **탐색하지 않게** 막는다(빈 PC 시나리오 9번이 대표님의 실제 예전 계정으로 오염되지 않도록). 예전 앱은 먼저 종료해야 한다.
.PARAMETER Cleanup
  요약을 출력한 뒤 임시 작업 폴더를 지운다(기본은 남겨 둔다 — 직접 열어 보기 위해).

.EXAMPLE
  .\scripts\ops\desktop_fresh_run.ps1 -ExePath "D:\Downloads\HaehanAI-20261008-abc1234-portable.exe"
.EXAMPLE
  # 껐다 다시 켜기(10번) — 같은 폴더로 한 번 더
  .\scripts\ops\desktop_fresh_run.ps1 -ExePath "...\HaehanAI-...-portable.exe" -WorkDir "$env:TEMP\haehan-fresh-20261008-0930"
.EXAMPLE
  .\scripts\ops\desktop_fresh_run.ps1 -SummaryOnly -WorkDir "$env:TEMP\haehan-fresh-20261008-0930"
#>
[CmdletBinding()]
param(
    [string]$ExePath,
    [string]$WorkDir,
    [switch]$SummaryOnly,
    [switch]$DryRun,
    [switch]$RealClaude,
    [string]$ImportFromOldApp,
    [switch]$Cleanup,
    [int]$StartTimeoutSec = 180
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Ports = @(8401, 3000, 9333)   # FastAPI · Next · Electron 원격 디버깅 — 앱이 고정으로 쓰는 포트

function Write-Section($title) { Write-Host ""; Write-Host "== $title" -ForegroundColor Cyan }

function Test-PortListening([int]$port) {
    try {
        return @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop).Count -gt 0
    } catch {
        return [bool](netstat -ano | Select-String -Pattern ":$port\s+.*LISTENING")
    }
}

function Get-PortOwner([int]$port) {
    try {
        $c = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop | Select-Object -First 1
        $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
        return "$($p.ProcessName) (PID $($c.OwningProcess))"
    } catch { return "(알 수 없음)" }
}

function Format-Size([long]$bytes) {
    if ($bytes -ge 1MB) { return ("{0:N1} MB" -f ($bytes / 1MB)) }
    if ($bytes -ge 1KB) { return ("{0:N1} KB" -f ($bytes / 1KB)) }
    return "$bytes B"
}

function Show-Dir([string]$path, [string]$label, [int]$max = 30) {
    if (-not (Test-Path -LiteralPath $path)) { Write-Host ("  {0,-34} 없음" -f $label); return }
    $files = @(Get-ChildItem -LiteralPath $path -Recurse -File -ErrorAction SilentlyContinue)
    $size = ($files | Measure-Object -Property Length -Sum).Sum
    Write-Host ("  {0,-34} 파일 {1}개, {2}" -f $label, $files.Count, (Format-Size ([long]$size)))
    $shown = 0
    foreach ($f in ($files | Sort-Object FullName)) {
        if ($shown -ge $max) { Write-Host ("    ... 외 {0}개" -f ($files.Count - $max)); break }
        $rel = $f.FullName.Substring($path.Length).TrimStart('\')
        Write-Host ("    {0}  ({1})" -f $rel, (Format-Size $f.Length))
        $shown++
    }
}

function Show-Config([string]$userData) {
    $cfgPath = Join-Path $userData "config.json"
    Write-Host "  config.json"
    if (-not (Test-Path -LiteralPath $cfgPath)) { Write-Host "    없음"; return }
    try {
        $cfg = Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch { Write-Host "    ⚠ JSON 으로 읽을 수 없음(손상?) — 같은 폴더의 config.json.corrupt-* 확인"; return }
    $secretKey = '(secret|token|password|license|key)'
    foreach ($p in $cfg.PSObject.Properties) {
        $v = $p.Value
        if ($p.Name -match $secretKey -and $v -is [string]) {
            $shown = if ($v.Length -eq 0) { "(빈 값)" } else { "(설정됨, $($v.Length)자)" }
        } elseif ($v -is [string] -or $v -is [bool] -or $v -is [int] -or $null -eq $v) {
            $shown = "$v"
        } else {
            $shown = ($v | ConvertTo-Json -Compress -Depth 5)
        }
        Write-Host ("    {0,-22} {1}" -f $p.Name, $shown)
    }
}

function Show-UsersDb([string]$dbPath) {
    if (-not (Test-Path -LiteralPath $dbPath)) { Write-Host "  users.db                           없음"; return }
    Write-Host ("  users.db                           {0}" -f (Format-Size (Get-Item -LiteralPath $dbPath).Length))
    $py = Get-Command py -ErrorAction SilentlyContinue
    if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
    if (-not $py) { Write-Host "    (python 이 없어 계정 요약은 생략)"; return }
    $code = @'
import sqlite3, sys
con = sqlite3.connect("file:" + sys.argv[1].replace("\\", "/") + "?mode=ro", uri=True)
con.row_factory = sqlite3.Row
cols = [r[1] for r in con.execute("PRAGMA table_info(users)")]
rows = con.execute("SELECT * FROM users ORDER BY created_at").fetchall()
def mask(e):
    local, _, dom = (e or "").partition("@")
    return (local[:1] + "***@" + dom) if dom else "?"
print("    계정 %d명 (컬럼: %s)" % (len(rows), ", ".join(cols)))
for r in rows:
    d = dict(r)
    print("    - %s  role=%s enabled=%s last_session_at=%s" % (mask(d.get("email")), d.get("role"), d.get("enabled"), d.get("last_session_at", "(컬럼 없음)")))
'@
    # 여러 줄 코드를 -c 로 넘기면 Windows PowerShell 5.1 이 따옴표를 깨뜨리므로 임시 .py 파일로 실행한다.
    $tmpPy = Join-Path $env:TEMP ("haehan-users-summary-" + [guid]::NewGuid().ToString("N") + ".py")
    try {
        Set-Content -LiteralPath $tmpPy -Value $code -Encoding UTF8
        $pyArgs = @(); if ($py.Name -like "py*") { $pyArgs += "-3" }
        $pyArgs += $tmpPy; $pyArgs += $dbPath
        $env:PYTHONIOENCODING = "utf-8"
        & $py.Source @pyArgs 2>&1 | ForEach-Object { Write-Host $_ }
    } catch { Write-Host "    (계정 요약 실패: $($_.Exception.Message))" }
    finally { Remove-Item -LiteralPath $tmpPy -Force -ErrorAction SilentlyContinue }
}

function Show-Summary([string]$userData) {
    Write-Section "임시 userData 요약 — $userData"
    if (-not (Test-Path -LiteralPath $userData)) { Write-Host "  폴더 없음"; return }
    Show-Config $userData
    Write-Host ""
    Show-Dir (Join-Path $userData "data") "data  (업무 데이터)" 20
    Show-Dir (Join-Path $userData "storage") "storage  (DB·감사/승인 기록)" 30
    Show-UsersDb (Join-Path $userData "storage\users.db")
    $mig = Join-Path $userData ".bundle-migration.json"
    if (Test-Path -LiteralPath $mig) {
        Write-Host "  .bundle-migration.json  (예전 위치 → 새 위치 이행 표시)"
        Get-Content -LiteralPath $mig -Raw -Encoding UTF8 | ForEach-Object { $_.Trim() } | ForEach-Object { Write-Host "    $_" }
    } else { Write-Host "  .bundle-migration.json             없음 (이행할 예전 데이터가 없었거나 아직 실행 전)" }
    $leg = Join-Path $userData ".legacy-import.json"
    if (Test-Path -LiteralPath $leg) {
        Write-Host "  .legacy-import.json  (예전 설치 폴더 자동 가져오기 완료 표식)"
        Get-Content -LiteralPath $leg -Raw -Encoding UTF8 | ForEach-Object { $_.Trim() } | ForEach-Object { Write-Host "    $_" }
    } else { Write-Host "  .legacy-import.json                없음 (예전 설치 폴더 가져오기를 하지 않았거나 건너뜀 — logs\fastapi.log 의 [legacy-import] 확인)" }
    Write-Host ""
    $mcp = Join-Path $userData "mcp"
    Write-Host "  mcp (Claude 연결용 고정 폴더)"
    if (Test-Path -LiteralPath $mcp) {
        foreach ($d in Get-ChildItem -LiteralPath $mcp -Directory -ErrorAction SilentlyContinue) {
            $exe = Get-ChildItem -LiteralPath $d.FullName -Recurse -Filter "haehan-mcp*.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1
            Write-Host ("    {0}  → exe {1}" -f $d.Name, $(if ($exe) { "있음 ($($exe.FullName))" } else { "없음" }))
        }
        if (-not (Get-ChildItem -LiteralPath $mcp -Directory -ErrorAction SilentlyContinue)) { Write-Host "    (비어 있음)" }
    } else { Write-Host "    없음 (Claude 연결을 하지 않았다면 정상 — 14·16번은 -RealClaude 로 점검)" }
    Write-Host ""
    $run = Join-Path $userData "run"
    $pids = @(Get-ChildItem -LiteralPath $run -Filter "*.pid" -ErrorAction SilentlyContinue)
    Write-Host ("  run\*.pid  (정상 종료면 없어야 함)  {0}" -f $(if ($pids.Count) { "남아 있음: " + ($pids.Name -join ", ") } else { "없음" }))
    $corrupt = @(Get-ChildItem -LiteralPath $userData -Filter "config.json.corrupt-*" -ErrorAction SilentlyContinue)
    Write-Host ("  config.json.corrupt-*              {0}" -f $(if ($corrupt.Count) { "⚠ 있음: " + ($corrupt.Name -join ", ") } else { "없음" }))
    Write-Host ""
    $lp0 = Join-Path $userData "logs\fastapi.log"
    if (Test-Path -LiteralPath $lp0) {
        $li = @(Select-String -LiteralPath $lp0 -Pattern "\[legacy-import\]" -ErrorAction SilentlyContinue)
        if ($li.Count) { Write-Host "  [legacy-import] 로그:"; $li | Select-Object -Last 3 | ForEach-Object { Write-Host ("      " + $_.Line.Trim()) } }
    }
    foreach ($log in @("fastapi.log", "nextjs.log")) {
        $lp = Join-Path $userData "logs\$log"
        if (Test-Path -LiteralPath $lp) {
            $errs = @(Select-String -LiteralPath $lp -Pattern "Traceback|ERROR|Error:" -ErrorAction SilentlyContinue)
            Write-Host ("  logs\{0,-14} {1}  오류성 줄 {2}개" -f $log, (Format-Size (Get-Item -LiteralPath $lp).Length), $errs.Count)
            $errs | Select-Object -Last 3 | ForEach-Object { Write-Host ("      " + $_.Line.Trim().Substring(0, [Math]::Min(150, $_.Line.Trim().Length))) }
        } else { Write-Host ("  logs\{0,-14} 없음" -f $log) }
    }
}

function Show-RealClaudeState {
    Write-Section "실제 Claude 설정 현황 (-RealClaude)"
    $cfg = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
    if (Test-Path -LiteralPath $cfg) {
        try {
            $j = Get-Content -LiteralPath $cfg -Raw -Encoding UTF8 | ConvertFrom-Json
            $names = @(); if ($j.mcpServers) { $names = @($j.mcpServers.PSObject.Properties.Name) }
            Write-Host "  claude_desktop_config.json  MCP 항목: $($names -join ', ')"
            if ($j.mcpServers.'haehan-orchestrator') {
                $cmd = $j.mcpServers.'haehan-orchestrator'.command
                Write-Host "  haehan-orchestrator.command = $cmd  ($(if (Test-Path -LiteralPath $cmd) { '파일 있음' } else { '⚠ 파일 없음' }))"
            } else { Write-Host "  haehan-orchestrator 항목 없음" }
        } catch { Write-Host "  ⚠ 읽기 실패: $($_.Exception.Message)" }
        $baks = @(Get-ChildItem -LiteralPath (Split-Path $cfg) -Filter "claude_desktop_config.json.bak-*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 3)
        foreach ($b in $baks) { Write-Host "  앱이 만든 백업: $($b.FullName)" }
    } else { Write-Host "  claude_desktop_config.json 없음 (Claude Desktop 미설치?)" }
    $claude = Get-Command claude -ErrorAction SilentlyContinue
    if ($claude) { Write-Host "  claude mcp get haehan-orchestrator:"; & claude mcp get haehan-orchestrator 2>&1 | ForEach-Object { Write-Host "    $_" } }
    else { Write-Host "  (claude 명령 없음 — Claude Code 확인 생략)" }
}

# ── 요약만 ────────────────────────────────────────────────────────────────
if ($SummaryOnly) {
    if (-not $WorkDir) { throw "-SummaryOnly 에는 -WorkDir 이 필요합니다." }
    Show-Summary (Join-Path $WorkDir "userData")
    if ($RealClaude) { Show-RealClaudeState }
    return
}

# ── 점검 ──────────────────────────────────────────────────────────────────
if (-not $ExePath) { throw "-ExePath(HaehanAI-<버전>-portable.exe)를 주세요." }
if (-not (Test-Path -LiteralPath $ExePath -PathType Leaf)) { throw "exe 를 찾을 수 없습니다: $ExePath" }
$ExePath = (Resolve-Path -LiteralPath $ExePath).Path
if (-not $WorkDir) { $WorkDir = Join-Path $env:TEMP ("haehan-fresh-" + (Get-Date -Format "yyyyMMdd-HHmm")) }
$resume = Test-Path -LiteralPath $WorkDir
$userData = Join-Path $WorkDir "userData"
$realUserData = Join-Path $env:APPDATA "Haehan AI"
if ($userData.TrimEnd('\') -ieq $realUserData.TrimEnd('\')) { throw "실제 사용자 데이터 폴더($realUserData)는 -WorkDir 로 쓸 수 없습니다." }

Write-Section "실행 계획"
Write-Host "  앱(exe)        : $ExePath"
Write-Host "  임시 userData  : $userData $(if ($resume) { '(기존 폴더 재사용 — 데이터 유지)' } else { '(새로 만듦 — 빈 PC)' })"
Write-Host "  실제 데이터    : $realUserData  ← 건드리지 않음"
Write-Host "  Claude 연결    : $(if ($RealClaude) { '⚠ 실제 Claude 설정을 바꿀 수 있음(-RealClaude)' } else { '막음(동의 창 미표시) — 14·15번은 -RealClaude 로 따로' })"
if ($ImportFromOldApp) { Write-Host "  예전 앱 가져오기: $ImportFromOldApp → 새 앱이 첫 실행 때 임시 userData 로 자동 복사(원본 읽기 전용, 예전 앱은 먼저 종료)" }
else { Write-Host "  예전 앱 가져오기: 막음(빈 PC 시나리오) — 새 앱의 자동 가져오기가 실제 예전 설치 폴더를 보지 않게 함" }
Write-Host "  실행 명령      : `"$ExePath`" --user-data-dir=`"$userData`""

$busy = @(); foreach ($p in $Ports) { if (Test-PortListening $p) { $busy += "$p ← $(Get-PortOwner $p)" } }
if ($busy.Count) {
    Write-Host ""
    Write-Host "⚠ 앱이 쓰는 고정 포트가 이미 사용 중입니다(다른 Haehan AI 가 켜져 있을 수 있음):" -ForegroundColor Yellow
    $busy | ForEach-Object { Write-Host "    $_" }
    Write-Host "  이 창은 다른 프로세스를 종료하지 않습니다. 켜져 있는 앱을 직접 종료(트레이 우클릭 → 종료)한 뒤 다시 실행하세요."
    if (-not $DryRun) { exit 2 }
}
if ($DryRun) { Write-Host ""; Write-Host "(DryRun — 실행하지 않았습니다)"; return }

# ── 준비 ──────────────────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $userData | Out-Null
$cfgPath = Join-Path $userData "config.json"
if (-not $RealClaude -and -not (Test-Path -LiteralPath $cfgPath)) {
    # 'Claude 연결' 동의 창 억제 — syncClaudeOnStart() 는 claude_mcp.prompted 가 true 면 묻지 않는다.
    '{"claude_mcp":{"prompted":true}}' | Set-Content -LiteralPath $cfgPath -Encoding UTF8
    Write-Host "  임시 config.json 에 claude_mcp.prompted=true 를 넣어 동의 창을 막았습니다."
}
# 새 앱의 자동 가져오기(예전 설치 폴더 탐색)는 환경변수 HAEHAN_LEGACY_INSTALL_DIRS 로 탐색 위치를 바꿀 수 있다(앱 → 서버로 상속).
if ($ImportFromOldApp) {
    if (-not (Test-Path -LiteralPath $ImportFromOldApp)) { throw "-ImportFromOldApp 폴더를 찾을 수 없습니다: $ImportFromOldApp" }
    $env:HAEHAN_LEGACY_INSTALL_DIRS = (Resolve-Path -LiteralPath $ImportFromOldApp).Path
} else {
    $env:HAEHAN_LEGACY_INSTALL_DIRS = (Join-Path $WorkDir "no-legacy-install")   # 존재하지 않는 폴더 = 가져오기 대상 없음
}
if ($RealClaude) {
    $backup = Join-Path $WorkDir "backup"
    New-Item -ItemType Directory -Force -Path $backup | Out-Null
    Write-Section "Claude 설정 백업 (-RealClaude)"
    $claudeCfg = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
    $claudeJson = Join-Path $env:USERPROFILE ".claude.json"
    foreach ($src in @($claudeCfg, $claudeJson)) {
        if (Test-Path -LiteralPath $src) {
            $dst = Join-Path $backup ((Split-Path $src -Leaf) + ".pre-test")
            Copy-Item -LiteralPath $src -Destination $dst -Force
            Write-Host "  백업: $src"
            Write-Host "     →  $dst"
            Write-Host "  복원: Copy-Item -LiteralPath `"$dst`" -Destination `"$src`" -Force   (Claude 를 종료한 뒤)"
        } else { Write-Host "  (없음: $src)" }
    }
    Write-Host "  앱도 변경 직전에 같은 폴더에 claude_desktop_config.json.bak-<시각> 백업을 남깁니다."
}

# ── 실행 ──────────────────────────────────────────────────────────────────
Write-Section "앱 실행 — 점검을 마치면 앱을 종료(트레이 우클릭 → 종료)하세요. 종료되면 자동으로 요약합니다."
$proc = Start-Process -FilePath $ExePath -ArgumentList @("--user-data-dir=`"$userData`"") -PassThru
$deadline = (Get-Date).AddSeconds($StartTimeoutSec)
while ((Get-Date) -lt $deadline -and -not (Test-PortListening 8401)) {
    if ($proc.HasExited -and -not (Test-PortListening 8401)) { break }
    Start-Sleep -Seconds 2
}
if (Test-PortListening 8401) { Write-Host "  서버가 떴습니다(8401). 이제 점검하세요." -ForegroundColor Green }
elseif ($proc.HasExited) { Write-Host "  ⚠ 서버(8401)가 뜨기 전에 앱 프로세스가 종료되었습니다(종료 코드 $($proc.ExitCode)). 요약의 logs 를 확인하세요." -ForegroundColor Yellow }
else { Write-Host "  ⚠ $StartTimeoutSec 초 안에 서버(8401)가 뜨지 않았습니다. 요약의 logs 를 확인하세요." -ForegroundColor Yellow }
while ((Test-PortListening 8401) -or (-not $proc.HasExited)) { Start-Sleep -Seconds 2 }
Start-Sleep -Seconds 2
Write-Host "  앱이 종료되었습니다."

Show-Summary $userData
if ($RealClaude) { Show-RealClaudeState }
Write-Host ""
Write-Host "임시 폴더: $WorkDir"
Write-Host "  다시 켜기(10번): 같은 -WorkDir 로 이 스크립트를 한 번 더 실행"
Write-Host "  지우기: Remove-Item -LiteralPath `"$WorkDir`" -Recurse -Force"
if ($Cleanup) { Remove-Item -LiteralPath $WorkDir -Recurse -Force; Write-Host "  (-Cleanup) 임시 폴더를 지웠습니다." }
