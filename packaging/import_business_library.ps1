param(
    [Parameter(Mandatory = $true)]
    [string]$ArchivePath,
    [string]$ProjectRoot = (Join-Path $PSScriptRoot ".."),
    [string]$DataDir = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ArchivePath = [System.IO.Path]::GetFullPath($ArchivePath)
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
if (-not $DataDir) {
    $DataDir = Join-Path $ProjectRoot "data"
}
$DataDir = [System.IO.Path]::GetFullPath($DataDir)

if (-not (Test-Path -LiteralPath $ArchivePath -PathType Leaf)) {
    throw "Business library archive does not exist: $ArchivePath"
}
if ([System.IO.Path]::GetExtension($ArchivePath) -ne ".zip") {
    throw "Business library archive must be a .zip file: $ArchivePath"
}
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot "pyproject.toml") -PathType Leaf)) {
    throw "Project root is not a Bedding Order Parser source directory: $ProjectRoot"
}

$DataPrefix = $DataDir.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
$Targets = [ordered]@{
    reference = Join-Path $DataDir "reference"
    input = Join-Path $DataDir "input\pi"
    golden = Join-Path $DataDir "golden"
    docs = Join-Path $DataDir "reference\docs"
}
foreach ($Target in $Targets.Values) {
    $ResolvedTarget = [System.IO.Path]::GetFullPath($Target)
    if (-not $ResolvedTarget.StartsWith($DataPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Import target escaped the configured data directory: $ResolvedTarget"
    }
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$Archive = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
$StagingRoot = Join-Path $DataDir (".library-import-" + [guid]::NewGuid().ToString("N") + ".tmp")
$StagingRoot = [System.IO.Path]::GetFullPath($StagingRoot)
if (-not $StagingRoot.StartsWith($DataPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    $Archive.Dispose()
    throw "Temporary import directory escaped the configured data directory."
}

try {
    $Entries = @($Archive.Entries | Where-Object { $_.Length -gt 0 })
    $RequiredNames = @(
        "PI单提取规则.xlsx",
        "款式表_structured.xlsx",
        "material_info.csv",
        "cover_res_template.xlsx"
    )
    foreach ($RequiredName in $RequiredNames) {
        $Matches = @($Entries | Where-Object { [System.IO.Path]::GetFileName($_.FullName) -eq $RequiredName })
        if ($Matches.Count -ne 1) {
            throw "Business library must contain exactly one $RequiredName; found $($Matches.Count)."
        }
    }

    $Plan = @()
    foreach ($Entry in $Entries) {
        $Name = [System.IO.Path]::GetFileName($Entry.FullName)
        $Category = ""
        if ($Name -in $RequiredNames) {
            $Category = "reference"
        } elseif ($Entry.FullName -like "*/PI-销售订单对照数据/*") {
            if ($Name -like "*_解析结果.json" -or $Name -like "*系统下单语言*.xlsx") {
                $Category = "golden"
            } elseif ($Name -like "PI被套产品行-下单语言部分参考数据*.xlsx") {
                $Category = "reference"
            } elseif ([System.IO.Path]::GetExtension($Name) -eq ".xlsx") {
                $Category = "input"
            }
        } elseif ([System.IO.Path]::GetExtension($Name) -eq ".docx") {
            $Category = "docs"
        }
        if (-not $Category) {
            continue
        }

        $Destination = [System.IO.Path]::GetFullPath((Join-Path $Targets[$Category] $Name))
        if (-not $Destination.StartsWith($DataPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Import destination escaped the configured data directory: $Destination"
        }
        $Plan += [pscustomobject]@{
            Entry = $Entry
            Category = $Category
            Destination = $Destination
        }
    }

    $DuplicateDestinations = @($Plan | Group-Object Destination | Where-Object { $_.Count -gt 1 })
    if ($DuplicateDestinations) {
        throw "Business library contains duplicate destination file names."
    }
    $Existing = @($Plan | Where-Object { Test-Path -LiteralPath $_.Destination })
    if ($Existing -and -not $Force) {
        throw "Business library files already exist. Re-run with -Force to replace them: $($Existing[0].Destination)"
    }

    [System.IO.Directory]::CreateDirectory($StagingRoot) | Out-Null
    foreach ($Category in $Targets.Keys) {
        [System.IO.Directory]::CreateDirectory((Join-Path $StagingRoot $Category)) | Out-Null
    }
    foreach ($Item in $Plan) {
        $StagedPath = Join-Path (Join-Path $StagingRoot $Item.Category) ([System.IO.Path]::GetFileName($Item.Destination))
        $InputStream = $Item.Entry.Open()
        $OutputStream = [System.IO.File]::Open($StagedPath, [System.IO.FileMode]::CreateNew)
        try {
            $InputStream.CopyTo($OutputStream)
        } finally {
            $OutputStream.Dispose()
            $InputStream.Dispose()
        }
        $Item | Add-Member -NotePropertyName StagedPath -NotePropertyValue $StagedPath
    }

    foreach ($Target in $Targets.Values) {
        [System.IO.Directory]::CreateDirectory($Target) | Out-Null
    }
    foreach ($Item in $Plan) {
        Move-Item -LiteralPath $Item.StagedPath -Destination $Item.Destination -Force:$Force
    }

    $ArchiveHash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $Counts = $Plan | Group-Object Category | ForEach-Object {
        [pscustomobject]@{ category = $_.Name; files = $_.Count }
    }
    [pscustomobject]@{
        archive_sha256 = $ArchiveHash
        data_dir = $DataDir
        imported_files = $Plan.Count
        categories = @($Counts)
    } | ConvertTo-Json -Depth 4
} finally {
    $Archive.Dispose()
    if (Test-Path -LiteralPath $StagingRoot) {
        $VerifiedStagingRoot = [System.IO.Path]::GetFullPath($StagingRoot)
        if (-not $VerifiedStagingRoot.StartsWith($DataPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean a temporary directory outside the data directory."
        }
        Remove-Item -LiteralPath $VerifiedStagingRoot -Recurse -Force
    }
}
