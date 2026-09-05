' 一键设置开机自启（只需运行一次）
' 运行后，每次开机服务自动启动，直接打开浏览器即可使用

Dim WShell, oFSO, projectDir, startupDir
Set WShell = CreateObject("WScript.Shell")
Set oFSO   = CreateObject("Scripting.FileSystemObject")
projectDir = oFSO.GetParentFolderName(WScript.ScriptFullName)
startupDir = WShell.SpecialFolders("Startup")

' 在开机启动目录创建快捷方式
Dim sLinkPath
sLinkPath = startupDir & "\资讯助手.lnk"
Dim oLink
Set oLink = WShell.CreateShortcut(sLinkPath)
oLink.TargetPath      = projectDir & "\后台启动.vbs"
oLink.WorkingDirectory = projectDir
oLink.Description     = "投资资讯助手后台服务"
oLink.Save

' 立即启动一次（不用等重启）
WShell.Run "wscript.exe """ & projectDir & "\后台启动.vbs""", 0, False
WScript.Sleep 3000

MsgBox "设置完成！" & vbCrLf & vbCrLf _
     & "以后每次开机，服务自动在后台启动。" & vbCrLf _
     & "直接打开浏览器，访问：" & vbCrLf & vbCrLf _
     & "  http://localhost:8888" & vbCrLf & vbCrLf _
     & "建议现在把这个地址加到浏览器书签。", _
     64, "投资资讯助手"
