"""一次性运行：把后台启动.vbs 注册到 Windows 开机启动项"""
import os
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
VBS_PATH    = os.path.join(PROJECT_DIR, "后台启动.vbs")

PS_SCRIPT = f"""
$ws  = New-Object -ComObject WScript.Shell
$startup = $ws.SpecialFolders('Startup')
$lnk = $ws.CreateShortcut($startup + '\\资讯助手.lnk')
$lnk.TargetPath      = '{VBS_PATH}'
$lnk.WorkingDirectory = '{PROJECT_DIR}'
$lnk.Description     = '投资资讯助手后台服务'
$lnk.Save()
Write-Host "已注册到开机启动：$startup\\资讯助手.lnk"
"""

# 写入临时 UTF-8 BOM 文件（PowerShell 能正确读中文路径）
tmp = tempfile.NamedTemporaryFile(
    suffix=".ps1", delete=False, mode="w", encoding="utf-8-sig"
)
tmp.write(PS_SCRIPT)
tmp.close()

try:
    result = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", tmp.name],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    print(stdout)
    if stderr:
        print("stderr:", stderr)
    print("返回码:", result.returncode)
finally:
    os.unlink(tmp.name)
