param(
    [string]$ExePath = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $ExePath) {
    $Onefile = Join-Path $ProjectRoot "dist-onefile\订单解析助手.exe"
    $Onedir = Join-Path $ProjectRoot "dist\订单解析助手\订单解析助手.exe"
    $ExePath = if (Test-Path -LiteralPath $Onefile) { $Onefile } else { $Onedir }
}
$ExePath = [System.IO.Path]::GetFullPath($ExePath)
if (-not (Test-Path -LiteralPath $ExePath -PathType Leaf)) {
    throw "未找到已验收的桌面应用：$ExePath"
}

$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "订单解析助手.lnk"
if ((Test-Path -LiteralPath $ShortcutPath) -and -not $Force) {
    throw "桌面快捷方式已存在。确认覆盖时请使用 -Force。"
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $ExePath
$Shortcut.WorkingDirectory = [System.IO.Path]::GetDirectoryName($ExePath)
$Shortcut.IconLocation = "$ExePath,0"
$Shortcut.Description = "订单解析助手"
$Shortcut.Save()
Write-Host "Desktop shortcut created: $ShortcutPath"
