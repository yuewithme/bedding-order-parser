param(
    [string]$ProjectRoot = (Join-Path $PSScriptRoot ".."),
    [string]$DataDir = "",
    [string]$ModelCache = "",
    [string]$ConfigPath = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot "pyproject.toml") -PathType Leaf)) {
    throw "Project root is not a Bedding Order Parser source directory: $ProjectRoot"
}
if (-not $DataDir) {
    $DataDir = Join-Path $ProjectRoot "data"
}
$DataDir = [System.IO.Path]::GetFullPath($DataDir)
$OutputDir = Join-Path $DataDir "output"
$IndexDir = Join-Path $OutputDir "material_vector_index"

if (-not $ModelCache) {
    $ModelCache = Join-Path ([Environment]::GetFolderPath("UserProfile")) ".cache\huggingface"
}
$ModelCache = [System.IO.Path]::GetFullPath($ModelCache)

$AppRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "BeddingOrderParser"
if (-not $ConfigPath) {
    $ConfigPath = Join-Path $AppRoot "config\app_config.json"
}
$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)
$ConfigDirectory = Split-Path -Parent $ConfigPath
if ((Test-Path -LiteralPath $ConfigPath -PathType Leaf) -and -not $Force) {
    throw "Desktop configuration already exists. Re-run with -Force to replace it: $ConfigPath"
}
[System.IO.Directory]::CreateDirectory($ConfigDirectory) | Out-Null

$Config = [ordered]@{
    project_root = $ProjectRoot
    data_dir = $DataDir
    material_store = Join-Path $OutputDir "material_store\material_master.sqlite3"
    index_dir = $IndexDir
    faiss_index = Join-Path $IndexDir "duvet_cover.faiss"
    faiss_mapping = Join-Path $IndexDir "duvet_cover_mapping.jsonl"
    vector_manifest = Join-Path $IndexDir "vector_index_manifest.json"
    rules_path = Join-Path $DataDir "reference\PI单提取规则.xlsx"
    styles_path = Join-Path $DataDir "reference\款式表_structured.xlsx"
    model_cache = $ModelCache
    task_root = Join-Path $AppRoot "tasks"
}

$Json = $Config | ConvertTo-Json
$TemporaryConfig = Join-Path $ConfigDirectory (".app_config." + [guid]::NewGuid().ToString("N") + ".tmp")
[System.IO.File]::WriteAllText(
    $TemporaryConfig,
    $Json + [Environment]::NewLine,
    (New-Object System.Text.UTF8Encoding($false))
)
Move-Item -LiteralPath $TemporaryConfig -Destination $ConfigPath -Force:$Force
Write-Host "Desktop configuration written to: $ConfigPath"
