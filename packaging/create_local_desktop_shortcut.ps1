param(
    [string]$ProjectRoot = (Join-Path $PSScriptRoot ".."),
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function New-UnicodeText {
    param([int[]]$CodePoints)
    return (-join ($CodePoints | ForEach-Object { [char]$_ }))
}

$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
    throw "Project root does not exist: $ProjectRoot"
}

$PythonwPath = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path -LiteralPath $PythonwPath -PathType Leaf)) {
    throw "pythonw.exe was not found: $PythonwPath"
}

$DesktopModulePath = Join-Path $ProjectRoot "src\bedding_order_parser\desktop"
if (-not (Test-Path -LiteralPath $DesktopModulePath -PathType Container)) {
    throw "Desktop entry module was not found: $DesktopModulePath"
}

$DesktopPath = [Environment]::GetFolderPath("Desktop")
if (-not $DesktopPath) {
    throw "Could not resolve the current user's Desktop path."
}

$ShortcutBaseName = New-UnicodeText @(0x8BA2, 0x5355, 0x89E3, 0x6790, 0x52A9, 0x624B)
$ShortcutPath = Join-Path $DesktopPath ($ShortcutBaseName + ".lnk")
$Arguments = "-m bedding_order_parser.desktop"
$Description = New-UnicodeText @(0x5E8A, 0x54C1, 0x8BA2, 0x5355, 0x667A, 0x80FD, 0x89E3, 0x6790, 0x4E0E, 0x7269, 0x6599, 0x5339, 0x914D, 0x7CFB, 0x7EDF)
$IconPath = Join-Path $ProjectRoot "src\bedding_order_parser\desktop\resources\app.ico"
if (-not (Test-Path -LiteralPath $IconPath -PathType Leaf)) {
    $IconPath = $PythonwPath
}

$Shell = New-Object -ComObject WScript.Shell

if (Test-Path -LiteralPath $ShortcutPath -PathType Leaf) {
    $ExistingShortcut = $Shell.CreateShortcut($ShortcutPath)
    $ExistingTarget = [string]$ExistingShortcut.TargetPath
    $ExistingWorkingDirectory = [string]$ExistingShortcut.WorkingDirectory

    $ExistingTargetFull = ""
    if ($ExistingTarget) {
        try {
            $ExistingTargetFull = [System.IO.Path]::GetFullPath($ExistingTarget)
        } catch {
            $ExistingTargetFull = $ExistingTarget
        }
    }

    $ExpectedTargetFull = [System.IO.Path]::GetFullPath($PythonwPath)
    $ExpectedWorkDirFull = [System.IO.Path]::GetFullPath($ProjectRoot)
    $ExistingWorkDirFull = ""
    if ($ExistingWorkingDirectory) {
        try {
            $ExistingWorkDirFull = [System.IO.Path]::GetFullPath($ExistingWorkingDirectory)
        } catch {
            $ExistingWorkDirFull = $ExistingWorkingDirectory
        }
    }

    $PointsToThisProject = (
        [string]::Equals($ExistingTargetFull, $ExpectedTargetFull, [System.StringComparison]::OrdinalIgnoreCase) -and
        [string]::Equals($ExistingWorkDirFull, $ExpectedWorkDirFull, [System.StringComparison]::OrdinalIgnoreCase)
    )
    if (-not $PointsToThisProject) {
        throw "Desktop shortcut already exists but does not point to this project: $ShortcutPath"
    }
    if (-not $Force) {
        throw "Desktop shortcut already exists for this project. Re-run with -Force to update it."
    }
}

$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $PythonwPath
$Shortcut.Arguments = $Arguments
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.WindowStyle = 1
$Shortcut.Description = $Description
$Shortcut.IconLocation = "$IconPath,0"
$Shortcut.Save()

Write-Host "ShortcutPath=$ShortcutPath"
Write-Host "TargetPath=$($Shortcut.TargetPath)"
Write-Host "Arguments=$($Shortcut.Arguments)"
Write-Host "WorkingDirectory=$($Shortcut.WorkingDirectory)"
Write-Host "IconLocation=$($Shortcut.IconLocation)"
