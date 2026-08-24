param(
    [string]$OnedirExe = "",
    [string]$OnefileExe = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OnedirExe) {
    $OnedirExe = Join-Path $ProjectRoot "dist\订单解析助手\订单解析助手.exe"
}
if (-not $OnefileExe) {
    $OnefileExe = Join-Path $ProjectRoot "dist-onefile\订单解析助手.exe"
}

$Results = foreach ($Path in @($OnedirExe, $OnefileExe)) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "发布产物不存在：$Path"
    }
    $Item = Get-Item -LiteralPath $Path
    [ordered]@{
        path = $Item.FullName
        size_bytes = $Item.Length
        sha256 = (Get-FileHash -LiteralPath $Item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$Results | ConvertTo-Json
