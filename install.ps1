# ============================================================
#  安装 FreeToken Cache Bar 到桌面 + 任务栏
# ============================================================
#  把这个脚本放到任意位置，右键「使用 PowerShell 运行」。
#  它会：
#    1. 在桌面生成一个图标（FreeToken Cache Bar.lnk）
#    2. 把同一图标钉到任务栏
#    3. 可选：开机自启
# ============================================================

$ErrorActionPreference = 'Stop'

$BarCmd   = 'C:\Users\Fang\.freetoken\cache-bar\ft_cache_bar.cmd'
$BarPyw   = 'C:\Users\Fang\.freetoken\cache-bar\ft_cache_bar.pyw'
$BarDir   = Split-Path -Parent $BarCmd
$IconPath = Join-Path $BarDir 'cache-bar.ico'

# 1) 生成 .ico（用系统 stockicon + 简单 PNG）。FreeToken 自带 cmd 做图标。
if (-not (Test-Path $IconPath)) {
    Add-Type -AssemblyName System.Drawing
    $bmp = New-Object System.Drawing.Bitmap 32, 32
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = 'AntiAlias'
    $g.Clear([System.Drawing.Color]::FromArgb(15, 17, 21))
    $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(124, 156, 255))
    $g.FillEllipse($brush, 4, 4, 24, 24)
    $g.Dispose()
    $icon = [System.Drawing.Icon]::FromHandle($bmp.GetHicon())
    $fs = [System.IO.File]::OpenWrite($IconPath)
    $icon.Save($fs)
    $fs.Close()
    $bmp.Dispose()
    Write-Host "[icon] created $IconPath"
}

# 2) 桌面快捷方式
$shell = New-Object -ComObject WScript.Shell
$desktopLnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'FreeToken Cache Bar.lnk'
$lnk = $shell.CreateShortcut($desktopLnk)
$lnk.TargetPath = $BarCmd
$lnk.WorkingDirectory = $BarDir
$lnk.IconLocation = "$IconPath,0"
$lnk.Description = 'FreeToken cache config quick-switch toolbar'
$lnk.WindowStyle = 7  # minimized
$lnk.Save()
Write-Host "[desktop] $desktopLnk"

# 3) 任务栏：把同一条 cmd 路径作为 Pin 添加。
#    通过任务栏 schema 文件实现（无需 explorer 二次确认）。
$taskbarDir = Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'
if (-not (Test-Path $taskbarDir)) {
    New-Item -ItemType Directory -Path $taskbarDir -Force | Out-Null
}
$tbLnk = Join-Path $taskbarDir 'FreeToken Cache Bar.lnk'
Copy-Item -Path $desktopLnk -Destination $tbLnk -Force
# 通知 explorer 刷新
$signature = @'
[DllImport("shell32.dll")]
public static extern void ChangeNotify(uint wEventId, uint uFlags, IntPtr dwItem1, IntPtr dwItem2);
'@
try {
    Add-Type -MemberDefinition $signature -Name 'WinAPI' -Namespace 'PInvoke' -ErrorAction Stop
    [PInvoke.WinAPI]::ChangeNotify(0x08000000, 0x0005, [IntPtr]::Zero, [IntPtr]::Zero)
    Write-Host "[taskbar] pinned $tbLnk"
} catch {
    Write-Host "[taskbar] shortcut copied to $tbLnk — restart explorer to see it"
}

# 4) 询问是否加入开机自启
$ans = Read-Host "Add to Windows startup? (y/N)"
if ($ans -eq 'y' -or $ans -eq 'Y') {
    $runDir = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    Set-ItemProperty -Path $runDir -Name 'FreeTokenCacheBar' -Value "`"$BarCmd`"" -Force
    Write-Host "[startup] registered"
}

Write-Host ""
Write-Host "Done. Double-click the desktop shortcut, or click the taskbar icon."
