' 콘솔 창 없이 명령 실행 (시작프로그램 바로가기·작업 스케줄러용 공용 런처, 2026-09-23)
' powershell.exe 를 직접 실행하면 -WindowStyle Hidden 이어도 콘솔이 잠깐 번쩍인다.
' wscript 는 콘솔이 없고 Run(..., 0) 으로 자식도 숨김 → 번쩍임 없음.
' 사용: wscript.exe run_hidden.vbs <exe> [args...]
'   WScript.Arguments 는 바깥 따옴표를 벗기므로 공백 포함 인자는 다시 따옴표로 감싼다.
'   종료코드는 자식 프로세스의 종료코드를 그대로 돌려준다(작업 스케줄러 결과에 반영).
Option Explicit
Dim sh, i, a, cmd
If WScript.Arguments.Count = 0 Then WScript.Quit 2
Set sh = CreateObject("WScript.Shell")
cmd = ""
For i = 0 To WScript.Arguments.Count - 1
    a = WScript.Arguments(i)
    If a = "" Or InStr(a, " ") > 0 Or InStr(a, vbTab) > 0 Then a = """" & a & """"
    If cmd <> "" Then cmd = cmd & " "
    cmd = cmd & a
Next
WScript.Quit sh.Run(cmd, 0, True)
