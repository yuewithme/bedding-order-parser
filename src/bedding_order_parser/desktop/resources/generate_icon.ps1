param(
    [string]$OutputPath = (Join-Path $PSScriptRoot "app.ico")
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class NativeIconMethods {
    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    public static extern bool DestroyIcon(IntPtr handle);
}
"@

$output = [System.IO.Path]::GetFullPath($OutputPath)
$directory = [System.IO.Path]::GetDirectoryName($output)
[System.IO.Directory]::CreateDirectory($directory) | Out-Null

$bitmap = New-Object System.Drawing.Bitmap 256, 256
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.Clear([System.Drawing.Color]::Transparent)

$black = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(22, 24, 22))
$white = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::White)
$fold = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(223, 227, 223))
$green = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(47, 168, 79))
$grayPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(113, 118, 113)), 10
$grayPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
$grayPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
$checkPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::White), 12
$checkPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
$checkPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
$checkPen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round

$graphics.FillRectangle($black, 0, 0, 256, 256)
$graphics.FillRectangle($white, 66, 42, 124, 170)
$graphics.FillPolygon($fold, @(
    (New-Object System.Drawing.Point 148, 42),
    (New-Object System.Drawing.Point 190, 84),
    (New-Object System.Drawing.Point 148, 84)
))
$graphics.DrawLine($grayPen, 91, 112, 165, 112)
$graphics.DrawLine($grayPen, 91, 137, 143, 137)
$graphics.DrawLine($grayPen, 91, 162, 129, 162)
$graphics.FillEllipse($green, 126, 130, 82, 82)
$checkPoints = [System.Drawing.Point[]]@(
    (New-Object System.Drawing.Point 145, 171),
    (New-Object System.Drawing.Point 159, 185),
    (New-Object System.Drawing.Point 188, 154)
)
$graphics.DrawLines($checkPen, $checkPoints)

$handle = $bitmap.GetHicon()
$icon = [System.Drawing.Icon]::FromHandle($handle)
$stream = [System.IO.File]::Create($output)
try {
    $icon.Save($stream)
}
finally {
    $stream.Dispose()
    $icon.Dispose()
    [NativeIconMethods]::DestroyIcon($handle) | Out-Null
    $grayPen.Dispose()
    $checkPen.Dispose()
    $black.Dispose()
    $white.Dispose()
    $fold.Dispose()
    $green.Dispose()
    $graphics.Dispose()
    $bitmap.Dispose()
}

Write-Host "Generated icon: $output"
