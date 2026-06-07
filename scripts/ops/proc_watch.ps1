# 프로세스 생성 실시간 감시 — npm/node/next/cmd 가 뜨는 순간 명령줄+부모 기록
# next dev nextjs.log 의 호출자(부모)를 색출하기 위함. 읽기 전용(아무 것도 죽이지 않음).
$ErrorActionPreference = "SilentlyContinue"
$log = "C:\work\01. haehan-ai-orchestrator\data\proc_watch.log"
New-Item -ItemType Directory -Path (Split-Path $log) -Force | Out-Null
Add-Content -Path $log -Value ("===== watch start {0} =====" -f (Get-Date -Format o))

# __InstanceCreationEvent: TargetInstance 에 CommandLine, ParentProcessId 직접 포함(사용자 권한 OK)
$query = "SELECT * FROM __InstanceCreationEvent WITHIN 0.3 WHERE TargetInstance ISA 'Win32_Process'"

Register-CimIndicationEvent -Query $query -SourceIdentifier ProcWatch -Action {
    $t = $Event.SourceEventArgs.NewEvent.TargetInstance
    $name = [string]$t.Name
    $cmd  = [string]$t.CommandLine
    # 관심 대상: node/npm/next/cmd/powershell 또는 명령줄에 dev/nextjs 포함
    if ($name -match 'node|npm|next|cmd\.exe|powershell|conhost' -or $cmd -match 'run dev|next dev|nextjs') {
        $ppid = $t.ParentProcessId
        $par = Get-CimInstance Win32_Process -Filter "ProcessId=$ppid" -ErrorAction SilentlyContinue
        $line = "{0}`n  PID={1} NAME={2}`n  CMD={3}`n  PPID={4} PARENT={5}`n  PCMD={6}`n" -f `
            (Get-Date -Format "HH:mm:ss"), $t.ProcessId, $name, $cmd, $ppid, $par.Name, $par.CommandLine
        Add-Content -Path $log -Value $line
    }
} | Out-Null

# 이벤트 펌프 유지
while ($true) { Start-Sleep -Seconds 2 }
