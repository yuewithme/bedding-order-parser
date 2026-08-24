param(
    [switch]$SkipOnedir,
    [switch]$SkipOnefile
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Set-Location $ProjectRoot

& (Join-Path $ProjectRoot "src\bedding_order_parser\desktop\resources\generate_icon.ps1")

if (-not $SkipOnedir) {
    uv run pyinstaller --noconfirm --clean `
        --distpath (Join-Path $ProjectRoot "dist") `
        --workpath (Join-Path $ProjectRoot "build\onedir") `
        (Join-Path $PSScriptRoot "bedding_order_parser_onedir.spec")
    if ($LASTEXITCODE -ne 0) {
        throw "Onedir构建失败。"
    }
}

if (-not $SkipOnefile) {
    uv run pyinstaller --noconfirm --clean `
        --distpath (Join-Path $ProjectRoot "dist-onefile") `
        --workpath (Join-Path $ProjectRoot "build\onefile") `
        (Join-Path $PSScriptRoot "bedding_order_parser_onefile.spec")
    if ($LASTEXITCODE -ne 0) {
        throw "Onefile构建失败。"
    }
}

Write-Host "Desktop builds completed."
