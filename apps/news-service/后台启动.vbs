' 静默后台启动投资资讯助手（无任何窗口）
' 此文件会在开机时自动运行，请勿删除

Dim WShell, oFSO, projectDir
Set WShell = CreateObject("WScript.Shell")
Set oFSO  = CreateObject("Scripting.FileSystemObject")
projectDir = oFSO.GetParentFolderName(WScript.ScriptFullName)

' 检查服务是否已在运行（端口 8888）
Dim oExec
Set oExec = WShell.Exec("cmd /c netstat -an 2>nul")
Dim sOut, lines, line, isRunning
sOut = oExec.StdOut.ReadAll()
isRunning = False

lines = Split(sOut, vbCrLf)
For Each line In lines
    If InStr(line, ":8888") > 0 And InStr(line, "LISTENING") > 0 Then
        isRunning = True
        Exit For
    End If
Next

If Not isRunning Then
    ' 完全隐藏窗口，后台运行
    WShell.Run "cmd /c cd /d """ & projectDir & """ && python server.py", 0, False
End If
